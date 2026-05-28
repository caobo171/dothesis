#!/usr/bin/env bash
# Bring up the OpenDraft dev stack:
#   1. Postgres in Docker (docker compose)
#   2. FastAPI (uvicorn --reload)
#   3. Next.js (next dev)
#
# Requires .env at repo root (see docs/superpowers/plans/2026-05-23-web-engine-mvp.md).

set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "Missing .env at repo root."
  echo "Create one with DATABASE_URL + AWS_* + SESSION_SECRET + GEMINI_API_KEY etc."
  echo "See docs/superpowers/plans/2026-05-23-web-engine-mvp.md for the full template."
  exit 1
fi

# Export env to subprocesses
set -a
# shellcheck disable=SC1091
source .env
# Orchestrator (chat + M5 editor + SP6.5 surface) is shipped — default it on for
# the dev stack. Override by setting ORCHESTRATOR_ENABLED=false in .env explicitly.
export ORCHESTRATOR_ENABLED="${ORCHESTRATOR_ENABLED:-true}"

# LangSmith tracing — auto-enable in dev when an API key is present. Skipped
# silently when no key is configured so the stack still boots without it.
# Tracing failures never affect runtime (the SDK is fire-and-forget), but we
# avoid enabling it without a key to skip the constant 401 retries.
if [ -n "${LANGSMITH_API_KEY:-}" ]; then
  export LANGSMITH_TRACING="${LANGSMITH_TRACING:-true}"
  export LANGSMITH_PROJECT="${LANGSMITH_PROJECT:-dothesis-dev}"
  echo "==> langsmith tracing enabled (project: ${LANGSMITH_PROJECT})"
fi
set +a

# --- 0. Postgres via docker compose ---
if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found on PATH. Install Docker Desktop, then re-run." >&2
  exit 1
fi

# Confirm the docker daemon is actually reachable BEFORE we try anything else.
# Without this, compose hangs/errors deep in a stack trace.
if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon is not reachable." >&2
  echo "  - On Windows/macOS: start Docker Desktop and wait for the whale icon to stop animating." >&2
  echo "  - Then verify with: docker version" >&2
  exit 1
fi

DOCKER_COMPOSE=(docker compose)
if ! docker compose version >/dev/null 2>&1; then
  DOCKER_COMPOSE=(docker-compose)
fi

echo "==> ensuring postgres is up"
"${DOCKER_COMPOSE[@]}" up -d postgres

echo "==> waiting for postgres to accept connections"
for i in {1..30}; do
  if docker exec opendraft-postgres pg_isready -U opendraft -d opendraft >/dev/null 2>&1; then
    break
  fi
  sleep 1
  if [ "$i" = 30 ]; then
    echo "postgres did not become ready in 30s; check 'docker logs opendraft-postgres'" >&2
    exit 1
  fi
done

# --- 1. API ---
# Detect Windows venv layout
if [ -d api/.venv/Scripts ]; then
  VENV_BIN="api/.venv/Scripts"
else
  VENV_BIN="api/.venv/bin"
fi

if [ ! -d api/.venv ]; then
  echo "==> creating api/.venv and installing deps (one-time, ~2 min)"
  (cd api && python3 -m venv .venv)
  "$VENV_BIN/pip" install --upgrade pip
  "$VENV_BIN/pip" install -e "api[dev]"
  # Engine deps so `python -m engine` subprocess can import draft_generator.
  "$VENV_BIN/pip" install -r engine/requirements.txt
fi

# Make sure engine deps are present even if the venv was created on an older dev.sh.
if ! "$VENV_BIN/python" -c "import google.genai" >/dev/null 2>&1; then
  echo "==> installing engine deps into api/.venv (one-time)"
  "$VENV_BIN/pip" install -r engine/requirements.txt
fi

echo "==> running alembic migrations"
(cd api && "../$VENV_BIN/alembic" upgrade head)

echo "==> starting api on port ${API_PORT:-7100}"
# Watch api/, engine/ AND orchestrator/ — the chat router + LangGraph agents
# import from orchestrator/, and uvicorn's --reload only picks up directories
# explicitly listed via --reload-dir. Without orchestrator/ in the list, edits
# to agent/tool code (model names, prompts, graph topology) need a manual
# kill + restart to take effect.
(cd api && "../$VENV_BIN/uvicorn" app.main:app --reload \
  --reload-dir app --reload-dir ../engine --reload-dir ../orchestrator \
  --port "${API_PORT:-7100}") &
API_PID=$!

# --- 2. Web ---
if [ ! -d web/node_modules ]; then
  echo "==> installing web deps (one-time, ~1 min)"
  (cd web && npm install)
fi

echo "==> starting web on port ${WEB_PORT:-3000}"
(cd web && npm run dev) &
WEB_PID=$!

# --- 3. LangGraph Studio (optional visualizer) ---
# Boots the local Agent Server that LangSmith Studio talks to so we can see
# the orchestrator graph + step through state at
#   https://smith.langchain.com/studio/?baseUrl=http://localhost:${STUDIO_PORT:-8123}
# Auto-detected: skipped when langgraph-cli isn't installed in the venv.
# To install: api/.venv/bin/pip install 'langgraph-cli[inmem]'
STUDIO_PID=""
if [ -x "$VENV_BIN/langgraph" ] && [ "${STUDIO_ENABLED:-true}" = "true" ]; then
  echo "==> starting langgraph studio on port ${STUDIO_PORT:-8123}"
  "$VENV_BIN/langgraph" dev --no-browser --port "${STUDIO_PORT:-8123}" &
  STUDIO_PID=$!
  echo "    → studio UI: https://smith.langchain.com/studio/?baseUrl=http://localhost:${STUDIO_PORT:-8123}"
elif [ ! -x "$VENV_BIN/langgraph" ]; then
  echo "==> skipping langgraph studio (langgraph-cli not installed in api/.venv)"
fi

cleanup() {
  echo
  echo "==> shutting down (api=$API_PID web=$WEB_PID studio=${STUDIO_PID:-none})"
  kill "$API_PID" "$WEB_PID" ${STUDIO_PID:+"$STUDIO_PID"} 2>/dev/null || true
  wait 2>/dev/null || true
  # Postgres is left running on purpose — it persists across restarts.
  # Stop it explicitly with: docker compose down
}
trap cleanup EXIT INT TERM

wait

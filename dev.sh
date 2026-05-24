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
  (cd api && python -m venv .venv)
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
# Watch both api/ and engine/ — the regenerate-exports endpoint pulls in engine
# code, and without --reload-dir uvicorn won't pick up edits to engine/.
(cd api && "../$VENV_BIN/uvicorn" app.main:app --reload \
  --reload-dir app --reload-dir ../engine \
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

cleanup() {
  echo
  echo "==> shutting down (api=$API_PID web=$WEB_PID)"
  kill "$API_PID" "$WEB_PID" 2>/dev/null || true
  wait 2>/dev/null || true
  # Postgres is left running on purpose — it persists across restarts.
  # Stop it explicitly with: docker compose down
}
trap cleanup EXIT INT TERM

wait

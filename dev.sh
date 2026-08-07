#!/usr/bin/env bash
# Bring up the DoThesis dev stack:
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
# --remove-orphans cleans up containers from a renamed/removed service (e.g. the
# old opendraft-postgres left over after the opendraft→dothesis rename) so they
# can't linger and hold the host port.
"${DOCKER_COMPOSE[@]}" up -d --remove-orphans postgres

echo "==> waiting for postgres to accept connections"
# 90s, not 30s: the FIRST run after the volume is (re)created has to run initdb
# and create the dothesis role/db, which routinely takes >30s — so a fresh
# checkout / a volume rename used to fail here. Steady-state startup is seconds.
PG_READY=0
for _ in $(seq 1 90); do
  if docker exec dothesis-postgres pg_isready -U dothesis -d dothesis >/dev/null 2>&1; then
    PG_READY=1
    break
  fi
  sleep 1
done
if [ "$PG_READY" != "1" ]; then
  echo "postgres did not become ready in 90s; check 'docker logs dothesis-postgres'" >&2
  exit 1
fi

# --- 1. API ---
# Pick a python interpreter — `python3` on macOS/Linux, `python` on Windows
# (the Microsoft Store / python.org installers ship `python.exe` but no
# `python3.exe`).
if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo "python3 / python not found on PATH. Install Python 3.11+ and re-run." >&2
  exit 1
fi

# Force venv tooling onto arm64 when possible (same reason as api/run.sh).
#
# Why: api/.venv's compiled wheels (pydantic_core, numpy, scipy, ...) are arm64,
# but the venv's python is a *universal* binary. When dev.sh is launched from a
# Rosetta / x86_64 shell (an x86_64 terminal, an agent harness, `arch -x86_64
# zsh`), macOS propagates that CPU preference to every universal child — so the
# interpreter loads as x86_64 and the first import dies with
#   ImportError: ... incompatible architecture (have 'arm64', need 'x86_64')
# which is exactly what `alembic upgrade head` used to blow up on.
#
# `arch -arm64` is a no-op on a native arm64 shell, and the probe below simply
# fails on Intel macs / Linux / Windows, leaving ARCH_PREFIX empty so tools run
# directly as before.
ARCH_PREFIX=()
if arch -arm64 true >/dev/null 2>&1; then
  ARCH_PREFIX=(arch -arm64)
fi
# Bash 3.2 (the /bin/bash macOS ships) errors on "${arr[@]}" for an empty array
# under `set -u`, so expand through this guard everywhere.
venv_run() { "${ARCH_PREFIX[@]+"${ARCH_PREFIX[@]}"}" "$@"; }

if [ ! -d api/.venv ]; then
  echo "==> creating api/.venv and installing deps (one-time, ~2 min)"
  # Create the venv under the same arch the wheels will be installed for,
  # otherwise a fresh venv made from a Rosetta shell pulls x86_64 wheels.
  (cd api && venv_run "$PYTHON" -m venv .venv)
fi

# Detect venv layout AFTER (possibly) creating it: Windows uses Scripts/,
# everything else uses bin/.
if [ -d api/.venv/Scripts ]; then
  VENV_BIN="api/.venv/Scripts"
elif [ -d api/.venv/bin ]; then
  VENV_BIN="api/.venv/bin"
else
  echo "api/.venv exists but has neither Scripts/ nor bin/ — delete it and re-run." >&2
  exit 1
fi

# Install / refresh deps. Idempotent — pip is fast when nothing changes, and
# this also covers the case where the venv pre-existed but deps drifted.
if ! venv_run "$VENV_BIN/python" -c "import app" >/dev/null 2>&1; then
  echo "==> installing api deps into api/.venv"
  venv_run "$VENV_BIN/pip" install --upgrade pip
  venv_run "$VENV_BIN/pip" install -e "api[dev]"
  venv_run "$VENV_BIN/pip" install -r engine/requirements.txt
fi

# Make sure engine deps are present even if the venv was created on an older dev.sh.
if ! venv_run "$VENV_BIN/python" -c "import google.genai" >/dev/null 2>&1; then
  echo "==> installing engine deps into api/.venv (one-time)"
  venv_run "$VENV_BIN/pip" install -r engine/requirements.txt
fi

# orchestrator/ and agent/ are sibling packages at the repo root, each with their
# own pyproject.toml that maps the package onto its directory. The api process
# imports both at module load (api/app/routers/m5_editor.py → orchestrator.*),
# so without these editable installs the API blows up at boot with
# ModuleNotFoundError: No module named 'orchestrator'.
if ! venv_run "$VENV_BIN/python" -c "import orchestrator" >/dev/null 2>&1; then
  echo "==> installing orchestrator into api/.venv (one-time)"
  venv_run "$VENV_BIN/pip" install -e orchestrator
fi

if ! venv_run "$VENV_BIN/python" -c "import agent" >/dev/null 2>&1; then
  echo "==> installing agent into api/.venv (one-time)"
  venv_run "$VENV_BIN/pip" install -e agent
fi

# quality/ holds the model-eval + rubric packages (F9/F3). Same editable-install
# pattern; without it `import quality.model_eval` fails in the api process/tests.
if ! venv_run "$VENV_BIN/python" -c "import quality" >/dev/null 2>&1; then
  echo "==> installing quality into api/.venv (one-time)"
  venv_run "$VENV_BIN/pip" install -e quality
fi

# thesis-stats: the shared statistics engine (PLS-SEM/EFA/mediation/moderation
# behind run_stats), vendored as a git submodule at libs/thesis-stats. Ensure
# it's checked out, then editable-install so local edits to the engine apply
# immediately — no reinstall, in either project that submodules it.
if [ ! -f libs/thesis-stats/pyproject.toml ]; then
  echo "==> fetching thesis-stats submodule"
  git submodule update --init --recursive libs/thesis-stats
fi
# Dual-import guard: semopy is the optional CB-SEM estimator (the [cbsem] extra).
# Guarding on it too means a stale env that predates CB-SEM gets the extra
# installed on the next run instead of silently lacking the cb_sem op.
if ! venv_run "$VENV_BIN/python" -c "import thesis_stats, semopy" >/dev/null 2>&1; then
  echo "==> installing thesis-stats[cbsem] into api/.venv (one-time)"
  venv_run "$VENV_BIN/pip" install -e "libs/thesis-stats[cbsem]"
fi

# Check the M5 export toolchain. LibreOffice is MANDATORY — the PDF needs it for
# its Table of Contents + clickable citations; without it the PDF silently
# degrades (WeasyPrint, no TOC/links). So this HARD-FAILS the dev boot when
# LibreOffice is missing — install it per the printed hint, then re-run.
# pandoc/mmdc stay informational. Escape hatch for a quick UI-only session:
#   REQUIRE_LIBREOFFICE=0 ./dev.sh
bash scripts/check-export-deps.sh --require-libreoffice

# Alembic runs on every dev boot, which is fine against a throwaway local
# database and catastrophic against a remote one — pointing .env at production
# for a debugging session would silently migrate production on the next
# ./dev.sh. So the migration step is gated on the DB actually being local.
#
# The check is on the host in DATABASE_URL, not on a "is this prod" flag,
# because the failure we're guarding against is exactly the case where someone
# forgot to set such a flag. Override deliberately when you really do mean to
# migrate a remote database:
#   ALLOW_REMOTE_MIGRATIONS=1 ./dev.sh
_db_host=$(printf '%s' "${DATABASE_URL:-}" | sed -E 's#^[^:]+://([^/@]*@)?([^:/?]+).*#\2#')
case "${_db_host}" in
  localhost|127.0.0.1|::1|"") _db_is_local=1 ;;
  *)                          _db_is_local=0 ;;
esac

if [ "${_db_is_local}" = "1" ] || [ "${ALLOW_REMOTE_MIGRATIONS:-0}" = "1" ]; then
  echo "==> running alembic migrations"
  (cd api && venv_run "../$VENV_BIN/alembic" upgrade head)
else
  echo "==> SKIPPING alembic migrations — DATABASE_URL points at a remote host (${_db_host})"
  echo "    Schema drift will surface as runtime errors, not a failed boot."
  echo "    Re-run with ALLOW_REMOTE_MIGRATIONS=1 if you really mean to migrate it."
fi

# Refuse to boot on top of a listener that is already there.
#
# uvicorn cannot bind a taken port, so it exits — but it exits into the
# background, the script sails on, and the web app keeps talking to whatever
# ALREADY owns the port. That failure is completely silent and it cost a full
# afternoon: an orphaned worker from hours earlier answered every request while
# fix after fix appeared to change nothing, because nothing new was ever
# serving. Better to stop here and say so.
if command -v lsof >/dev/null 2>&1; then
  _held_by=$(lsof -nP -tiTCP:"${API_PORT:-7100}" -sTCP:LISTEN 2>/dev/null | head -1 || true)
  if [ -n "${_held_by}" ]; then
    echo "Port ${API_PORT:-7100} is already in use by pid ${_held_by}:" >&2
    ps -o pid,lstart,command -p "${_held_by}" 2>/dev/null | tail -n +2 >&2
    echo >&2
    echo "That process would keep serving — including code from before your last edit." >&2
    echo "Stop it first:  kill -9 ${_held_by}" >&2
    exit 1
  fi
fi

echo "==> starting api on port ${API_PORT:-7100}"
# Watch api/, engine/, orchestrator/, and the v3 deep agent runtime (agent/) —
# uvicorn's --reload only picks up directories listed via --reload-dir.
# NOT skills/: SKILL.md files are plain markdown the agent reads from disk at
# turn time (via the filesystem backend), so they take effect WITHOUT a worker
# restart. Watching them was actively harmful — saving a skill file mid-turn
# restarted the worker and killed the in-flight SSE stream, so the bootstrap
# analysis turn saved the user message but never reached commit_slice/_finalize
# (empty module_status, no assistant reply). Drop it.
(cd api && venv_run "../$VENV_BIN/uvicorn" app.main:app --reload \
  --reload-dir app --reload-dir ../engine --reload-dir ../orchestrator \
  --reload-dir ../agent \
  --port "${API_PORT:-7100}") &
API_PID=$!

# --- 2. Web ---
if [ ! -d web/node_modules ]; then
  echo "==> installing web deps (one-time, ~1 min)"
  (cd web && npm install)
fi

echo "==> starting web on port ${WEB_PORT:-3000}"
# Clear Next.js's incremental build cache before every boot. The api side
# (uvicorn + langgraph CLI watchfiles) emits "N changes detected" repeatedly
# during development, which trips Next.js dev's route-map regenerator and
# sometimes leaves it serving a 404 for legitimate routes (e.g.
# /chat/projects/[pid]/threads/[tid]). Wiping .next costs ~100ms and the
# first compile after restart pays for itself within seconds.
(cd web && rm -rf .next && npm run dev) &
WEB_PID=$!

# --- 3. LangGraph Studio (optional visualizer) ---
# Boots the local Agent Server that LangSmith Studio talks to so we can see
# the orchestrator graph + step through state at
#   https://smith.langchain.com/studio/?baseUrl=http://localhost:${STUDIO_PORT:-8123}
# Auto-detected: skipped when langgraph-cli isn't installed in the venv.
# To install: api/.venv/bin/pip install 'langgraph-cli[inmem]'
STUDIO_PID=""
# Windows venv binaries are .exe; macOS/Linux are bare names. Resolve once.
if [ -f "$VENV_BIN/langgraph.exe" ]; then
  LANGGRAPH_BIN="langgraph.exe"
elif [ -f "$VENV_BIN/langgraph" ]; then
  LANGGRAPH_BIN="langgraph"
else
  LANGGRAPH_BIN=""
fi
if [ -n "$LANGGRAPH_BIN" ] && [ "${STUDIO_ENABLED:-true}" = "true" ]; then
  echo "==> starting langgraph studio on port ${STUDIO_PORT:-8123}"
  # The "N changes detected" log spam comes from langgraph_runtime_inmem's
  # checkpoint pickles (.langgraph_api/*.pckl) being written every graph
  # step and watchfiles narrating them at INFO. The checkpoint dir is
  # hardcoded to cwd; a previous attempt to relocate it via cwd-switching
  # broke graph loading (langgraph.json's `./orchestrator/...` paths
  # resolve against the process cwd, not the config file). The lever
  # that actually works: langgraph_api/logging.py reads LOG_LEVEL (default
  # INFO) and pins it on the ROOT logger, which is what makes the
  # third-party watchfiles.main INFO logs leak. Setting LOG_LEVEL=WARNING
  # only on the langgraph dev process silences root INFO without
  # affecting the rest of the dev stack — warnings/errors still surface,
  # so a real graph reload failure won't be hidden.
  LOG_LEVEL=WARNING venv_run "$VENV_BIN/$LANGGRAPH_BIN" dev --no-browser \
    --port "${STUDIO_PORT:-8123}" &
  STUDIO_PID=$!
  echo "    → studio UI: https://smith.langchain.com/studio/?baseUrl=http://localhost:${STUDIO_PORT:-8123}"
elif [ -z "$LANGGRAPH_BIN" ]; then
  echo "==> skipping langgraph studio (langgraph-cli not installed in api/.venv)"
fi

# Kill a process and everything under it, deepest first.
#
# `kill $API_PID` is not enough and the difference is not academic. Each service
# is launched in a subshell, which runs `arch -arm64`, which runs uvicorn, whose
# --reload forks a worker of its own. Signalling only the pid we recorded leaves
# the real server ORPHANED and still holding the port: a 7-hour-old worker kept
# serving stale code while every "restart" bound nothing and died quietly, so
# every code change looked like it did nothing.
#
# Walks by PPID rather than signalling the process group: -$$ would be wrong,
# and dangerous, if this script is ever not its own group leader.
kill_tree() {
  local pid="$1" sig="${2:-TERM}" child
  for child in $(pgrep -P "$pid" 2>/dev/null || true); do
    kill_tree "$child" "$sig"
  done
  kill "-$sig" "$pid" 2>/dev/null || true
}

cleanup() {
  # The trap fires for INT and then again for EXIT; without this the second
  # pass reports pids that are already gone.
  [ -n "${_DEV_CLEANING_UP:-}" ] && return
  _DEV_CLEANING_UP=1
  echo
  echo "==> shutting down (api=$API_PID web=$WEB_PID studio=${STUDIO_PID:-none})"
  for pid in "$API_PID" "$WEB_PID" ${STUDIO_PID:+"$STUDIO_PID"}; do
    kill_tree "$pid" TERM
  done

  # uvicorn's reloader ignores SIGTERM often enough to matter — plain `kill`
  # left it running every time. Give it a moment, then stop asking.
  sleep 2
  for pid in "$API_PID" "$WEB_PID" ${STUDIO_PID:+"$STUDIO_PID"}; do
    kill_tree "$pid" KILL
  done
  wait 2>/dev/null || true

  # Last resort: anything still holding the API port is an orphan from this run
  # or an earlier one. Leaving it is what makes the NEXT boot serve stale code.
  if command -v lsof >/dev/null 2>&1; then
    local stale
    stale=$(lsof -nP -tiTCP:"${API_PORT:-7100}" -sTCP:LISTEN 2>/dev/null || true)
    if [ -n "$stale" ]; then
      echo "==> force-killing leftover listener on ${API_PORT:-7100}: $stale"
      # shellcheck disable=SC2086
      kill -9 $stale 2>/dev/null || true
    fi
  fi
  # Postgres is left running on purpose — it persists across restarts.
  # Stop it explicitly with: docker compose down
}
trap cleanup EXIT INT TERM

wait

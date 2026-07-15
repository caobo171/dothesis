#!/usr/bin/env bash
# Production deploy for DoThesis on a single Ubuntu server (native, systemd-supervised).
#
# What this does, idempotently, against the CURRENT checkout:
#   0. Preflight — sanity-check the host, .env, and required tooling
#   1. System deps — pandoc + libreoffice-writer (M5 export toolchain)
#   2. API     — (re)build api/.venv, install api + engine deps, run alembic
#   3. Web     — npm ci + `next build` (NEXT_PUBLIC_* baked in here)
#   4. systemd — install/refresh dothesis-api + dothesis-web units, restart, verify
#
# The orchestrator (LangGraph auto-run) is NOT a separate service: the API spawns
# it as a subprocess per run (ORCHESTRATOR_ENABLED), so there is nothing to
# supervise for it here. LangGraph Studio is dev-only and never deployed.
#
# Re-runnable: run it again after `git pull` to ship a new release. Each step is
# idempotent; systemd restarts the services at the end.
#
# Usage:
#   sudo -E ./scripts/deploy.sh             # full deploy (needs root for apt + systemd)
#   APP_USER=deploy ./scripts/deploy.sh     # run services as a non-root user
#
# Tunables (env or .env):
#   APP_USER       unix user the services run as            (default: invoking user)
#   API_HOST       uvicorn bind address                     (default: 127.0.0.1)
#   API_PORT       uvicorn port                             (default: 7100)
#   API_WORKERS    uvicorn worker processes                 (default: nproc, capped 4)
#   WEB_PORT       next start port                          (default: 3006)
#   NEXT_PUBLIC_API_BASE  baked into the web bundle          (default: /api/v1)
#   SKIP_APT=1     skip system-package install (CI / locked-down hosts)
#   SKIP_WEB=1     skip the web build (api-only deploy)
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31mxx\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 0. Preflight
# ---------------------------------------------------------------------------
log "deploying from ${REPO_DIR}"

[ "$(uname -s)" = "Linux" ] || die "this deploy script targets Linux (Ubuntu); for macOS dev use ./dev.sh"

APP_USER="${APP_USER:-${SUDO_USER:-$(id -un)}}"
id "$APP_USER" >/dev/null 2>&1 || die "APP_USER '$APP_USER' does not exist"
log "services will run as: ${APP_USER}"

# systemd + apt steps need root. Allow a non-root dry run that still builds, but
# fail loudly before we try to write to /etc.
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  command -v sudo >/dev/null 2>&1 || die "not root and no sudo available — re-run with sudo -E"
  SUDO="sudo"
fi

[ -f .env ] || die "missing .env at repo root. Copy .env.example and fill in DATABASE_URL, SESSION_SECRET, GOOGLE_API_KEY, AWS_* — see .env.example"

# Load .env so we can validate required vars and reuse API_PORT etc.
set -a; # shellcheck disable=SC1091
source .env; set +a

API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-7100}"
WEB_PORT="${WEB_PORT:-3006}"
API_WORKERS="${API_WORKERS:-$(( $(nproc) < 4 ? $(nproc) : 4 ))}"
NEXT_PUBLIC_API_BASE="${NEXT_PUBLIC_API_BASE:-/api/v1}"

# Fail fast on missing prod-critical config rather than after a 3-minute build.
missing_env=0
require_env() {
  local name="$1"
  if [ -z "${!name:-}" ]; then warn "required env not set: ${name}"; missing_env=1; fi
}
require_env DATABASE_URL
require_env SESSION_SECRET
# Model-provider preflight. The LLM route decides which key is prod-critical:
# the Ofox gateway (ORCHESTRATOR_LLM_ROUTE / DOTHESIS_MODEL_ROUTE = "ofox") needs
# OFOX_API_KEY — the route raises "ofox route needs OFOX_API_KEY" at the FIRST
# LLM call, so a keyless ofox deploy crash-loops. The native route needs a
# Gemini key. Fail fast at deploy instead of at runtime.
if [ "${ORCHESTRATOR_LLM_ROUTE:-}" = "ofox" ] || [ "${DOTHESIS_MODEL_ROUTE:-}" = "ofox" ]; then
  if [ -z "${OFOX_API_KEY:-}" ]; then
    warn "LLM route is 'ofox' but OFOX_API_KEY is unset — the route will crash at the first LLM call"
    missing_env=1
  fi
  # Vision on the ofox route uses OFOX_API_KEY; a Gemini key is only a nice-to-have
  # native fallback, so don't hard-fail on it here.
  [ -z "${GOOGLE_API_KEY:-}" ] && [ -z "${GEMINI_API_KEY:-}" ] && \
    warn "ofox route without GOOGLE_API_KEY/GEMINI_API_KEY — fine, but there is no native Gemini fallback"
elif [ -z "${GOOGLE_API_KEY:-}" ] && [ -z "${GEMINI_API_KEY:-}" ]; then
  warn "no GOOGLE_API_KEY / GEMINI_API_KEY set — the native LLM route has no provider"
  missing_env=1
fi
# S3 is where uploads + exported DOCX/PDF live. Warn but don't hard-fail (some
# deploys point at a local MinIO via AWS_* anyway).
[ -z "${S3_BUCKET:-}" ] && warn "S3_BUCKET unset — uploads/exports will fail at runtime"
[ "$missing_env" -eq 0 ] || die "fix the missing .env values above and re-run"

# Toolchain presence.
command -v python3 >/dev/null 2>&1 || die "python3 not found — apt-get install -y python3 python3-venv"
python3 -c 'import venv' 2>/dev/null || die "python3-venv missing — apt-get install -y python3-venv"
if [ "${SKIP_WEB:-0}" != "1" ]; then
  command -v node >/dev/null 2>&1 || die "node not found — install Node 20 LTS (Next.js 15 needs >=18.18)"
  command -v npm  >/dev/null 2>&1 || die "npm not found"
  node_major="$(node -p 'process.versions.node.split(".")[0]')"
  [ "$node_major" -ge 18 ] || die "Node ${node_major} too old — Next.js 15 needs Node >=18.18 (20 LTS recommended)"
fi

# ---------------------------------------------------------------------------
# 1. System packages — M5 export toolchain (pandoc + libreoffice + Chrome runtime)
# ---------------------------------------------------------------------------
if [ "${SKIP_APT:-0}" = "1" ]; then
  log "SKIP_APT=1 — skipping system package install"
else
  log "installing system export deps (pandoc, libreoffice-writer, Chrome runtime libs)"
  $SUDO apt-get update -qq
  # Chrome-for-Testing (managed by puppeteer for the mermaid CLI) needs a
  # handful of shared libraries to launch headless on a bare Ubuntu server —
  # otherwise `mmdc` times out with "TimeoutError waiting for WS endpoint".
  # Package list from the official Puppeteer troubleshooting doc.
  # Ubuntu 24.04's 64-bit time_t transition renamed libasound2 -> libasound2t64
  # and left the old name as a virtual package with no install candidate. Pick
  # whichever the target's apt actually offers so this works on 22.04 and 24.04.
  if apt-cache show libasound2t64 >/dev/null 2>&1; then
    ASOUND_PKG=libasound2t64
  else
    ASOUND_PKG=libasound2
  fi
  $SUDO apt-get install -y --no-install-recommends \
    pandoc libreoffice-writer \
    ca-certificates fonts-liberation "$ASOUND_PKG" libatk-bridge2.0-0 libatk1.0-0 \
    libc6 libcairo2 libcups2 libdbus-1-3 libexpat1 libfontconfig1 libgbm1 \
    libgcc-s1 libglib2.0-0 libgtk-3-0 libnspr4 libnss3 libpango-1.0-0 \
    libx11-6 libx11-xcb1 libxcb1 libxcomposite1 libxdamage1 libxext6 libxfixes3 \
    libxrandr2 libxrender1 libxss1 libxtst6 lsb-release wget xdg-utils
fi

# ---------------------------------------------------------------------------
# 1b. Mermaid CLI — conceptual-model diagrams (Node-based)
# ---------------------------------------------------------------------------
# The M5 export renders the agent's `flowchart LR` block to a PNG and embeds
# it. Missing tools = fall back to a text relationship list (still ships), so
# any failure here is warned but never blocks the deploy. Skipped when Node
# isn't available (matches the SKIP_WEB gate — same runtime).
if [ "${SKIP_WEB:-0}" != "1" ] && command -v npm >/dev/null 2>&1; then
  MMDC_DIR="engine/tools/mermaid_cli"
  if [ -f "$MMDC_DIR/package.json" ]; then
    log "installing mermaid CLI + managed Chrome (conceptual-model diagrams)"
    ( cd "$MMDC_DIR" && npm install --no-audit --no-fund --silent ) || \
      warn "mermaid CLI install failed — conceptual-model diagrams will fall back to text"
    # puppeteer's own Chrome for Testing. Written under $PUPPETEER_CACHE_DIR
    # (or ~/.cache/puppeteer). Idempotent — noop when already at the pinned version.
    export PUPPETEER_CACHE_DIR="${PUPPETEER_CACHE_DIR:-$HOME/.cache/puppeteer}"
    if [ ! -d "$PUPPETEER_CACHE_DIR/chrome" ] || \
       [ -z "$(ls -A "$PUPPETEER_CACHE_DIR/chrome" 2>/dev/null || true)" ]; then
      ( cd "$MMDC_DIR" && npx --yes puppeteer browsers install chrome ) || \
        warn "puppeteer chrome install failed — mermaid → PNG will fall back to text"
    else
      log "puppeteer chrome already installed in ${PUPPETEER_CACHE_DIR}"
    fi
    # Give the service user access to the cache (Chrome writes profile files
    # under here on first launch).
    if [ "$APP_USER" != "$(id -un)" ] && [ -d "$PUPPETEER_CACHE_DIR" ]; then
      $SUDO chown -R "$APP_USER":"$APP_USER" "$PUPPETEER_CACHE_DIR" || true
    fi
  fi
fi

# Verify; --strict makes a degraded toolchain a hard failure in prod, and
# --require-libreoffice makes LibreOffice explicitly MANDATORY (the PDF needs it
# for its Table of Contents + clickable citations — WeasyPrint fallback has
# neither). mmdc is informational-only so it never trips the check.
bash scripts/check-export-deps.sh --strict --require-libreoffice \
  || die "export toolchain incomplete (LibreOffice is required) — see hints above"

# ---------------------------------------------------------------------------
# 2. API — venv, deps, migrations
# ---------------------------------------------------------------------------
VENV_BIN="api/.venv/bin"
if [ ! -d api/.venv ]; then
  log "creating api/.venv"
  python3 -m venv api/.venv
fi
log "installing api + engine deps (prod)"
"$VENV_BIN/pip" install --quiet --upgrade pip
"$VENV_BIN/pip" install --quiet -e ./api                       # api package (no [dev])
"$VENV_BIN/pip" install --quiet -r engine/requirements.txt      # engine subprocess imports

log "running database migrations (alembic upgrade head)"
( cd api && "../$VENV_BIN/alembic" upgrade head )

# ---------------------------------------------------------------------------
# 3. Web — install + build (NEXT_PUBLIC_* are inlined HERE, at build time)
# ---------------------------------------------------------------------------
if [ "${SKIP_WEB:-0}" = "1" ]; then
  log "SKIP_WEB=1 — skipping web build"
else
  log "installing web deps (npm ci)"
  ( cd web && npm ci )
  log "building web bundle (NEXT_PUBLIC_API_BASE=${NEXT_PUBLIC_API_BASE})"
  # These must be present at BUILD time — Next inlines NEXT_PUBLIC_* into the
  # client bundle. Setting them only in the systemd unit would be too late.
  ( cd web && \
    NEXT_PUBLIC_API_BASE="$NEXT_PUBLIC_API_BASE" \
    NEXT_PUBLIC_API_PROXY_TARGET="${NEXT_PUBLIC_API_PROXY_TARGET:-http://${API_HOST}:${API_PORT}}" \
    npm run build )
fi

# Files were written as the deploying user; make sure the service user can read
# the venv, build output, and node_modules.
if [ "$APP_USER" != "$(id -un)" ]; then
  log "chown app tree to ${APP_USER}"
  $SUDO chown -R "$APP_USER":"$APP_USER" "$REPO_DIR/api/.venv" "$REPO_DIR/web/.next" "$REPO_DIR/web/node_modules" 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
# 4. systemd units
# ---------------------------------------------------------------------------
NODE_BIN_DIR="$(dirname "$(command -v node 2>/dev/null || echo /usr/bin/node)")"

log "installing systemd unit: dothesis-api.service"
$SUDO tee /etc/systemd/system/dothesis-api.service >/dev/null <<UNIT
[Unit]
Description=DoThesis API (FastAPI + deep agent + orchestrator subprocess)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${REPO_DIR}/api
EnvironmentFile=${REPO_DIR}/.env
# ORCHESTRATOR runs as an in-process subprocess of the API; enable it here so a
# bare .env without the flag still gets the chat + auto-run surface.
Environment=ORCHESTRATOR_ENABLED=true
# WorkingDirectory is api/, but the API imports the repo-root packages
# (orchestrator/, engine/, agent/) at import time -- e.g. routers/m5_editor.py
# imports from orchestrator. Put the repo root on PYTHONPATH so those resolve;
# without it uvicorn crash-loops with ModuleNotFoundError. (No backticks here:
# this heredoc is unquoted, so backticks would trigger command substitution.)
Environment=PYTHONPATH=${REPO_DIR}
# Where puppeteer's Chrome-for-Testing was installed by the deploy step.
# _render_mermaid_png reads this to locate the browser mmdc needs.
Environment=PUPPETEER_CACHE_DIR=${PUPPETEER_CACHE_DIR:-${REPO_DIR}/api/.cache/puppeteer}
ExecStart=${REPO_DIR}/${VENV_BIN}/uvicorn app.main:app --host ${API_HOST} --port ${API_PORT} --workers ${API_WORKERS}
Restart=on-failure
RestartSec=3
# Exports shell out to libreoffice which writes temp files — give it a writable home.
Environment=HOME=${REPO_DIR}/api

[Install]
WantedBy=multi-user.target
UNIT

if [ "${SKIP_WEB:-0}" != "1" ]; then
  log "installing systemd unit: dothesis-web.service"
  $SUDO tee /etc/systemd/system/dothesis-web.service >/dev/null <<UNIT
[Unit]
Description=DoThesis Web (Next.js 15)
After=network-online.target dothesis-api.service
Wants=network-online.target

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${REPO_DIR}/web
EnvironmentFile=${REPO_DIR}/.env
Environment=NODE_ENV=production
Environment=PATH=${NODE_BIN_DIR}:/usr/local/bin:/usr/bin:/bin
ExecStart=${REPO_DIR}/web/node_modules/.bin/next start -p ${WEB_PORT}
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
fi

log "reloading systemd + (re)starting services"
$SUDO systemctl daemon-reload
$SUDO systemctl enable --now dothesis-api.service
$SUDO systemctl restart dothesis-api.service
if [ "${SKIP_WEB:-0}" != "1" ]; then
  $SUDO systemctl enable --now dothesis-web.service
  $SUDO systemctl restart dothesis-web.service
fi

# ---------------------------------------------------------------------------
# 5. Health check
# ---------------------------------------------------------------------------
log "waiting for API health on http://${API_HOST}:${API_PORT}/api/v1/health"
ok=0
for _ in $(seq 1 30); do
  if curl -fsS "http://${API_HOST}:${API_PORT}/api/v1/health" >/dev/null 2>&1; then ok=1; break; fi
  sleep 1
done
if [ "$ok" = "1" ]; then
  log "API is healthy ✓"
else
  warn "API did not pass health check in 30s — inspect: journalctl -u dothesis-api -n 80 --no-pager"
fi

cat <<DONE

Deploy complete.

  API   : http://${API_HOST}:${API_PORT}   (workers=${API_WORKERS})
  Web   : http://0.0.0.0:${WEB_PORT}
  user  : ${APP_USER}

Manage:
  systemctl status  dothesis-api dothesis-web
  journalctl -u dothesis-api -f
  journalctl -u dothesis-web -f
  systemctl restart dothesis-api dothesis-web

Reverse proxy (nginx/Caddy) note:
  Route /api/v1/  -> http://${API_HOST}:${API_PORT}   (DIRECT — do NOT buffer; SSE/streaming)
  Route /         -> http://127.0.0.1:${WEB_PORT}      (Next.js)
  For SSE, disable proxy buffering on /api/v1/ (nginx: proxy_buffering off;).
DONE

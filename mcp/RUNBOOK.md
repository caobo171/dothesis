# DoThesis + MCP — run behind the webkaze tunnel (dev)

The exact steps to bring the whole stack up so the MCP is reachable at
`https://dothesislocal-api.webkaze.com/mcp`. All commands run from the repo root
(`.../learning_app/dothesis`) unless noted. This is the DEV setup (Mac +
Cloudflare tunnel); production hosting is a later step.

Ports / hosts:

| Piece | Local | Public (tunnel) |
|---|---|---|
| Postgres (docker) | `:5432` | — |
| API (FastAPI) | `:7100` | `dothesislocal-api.webkaze.com` |
| Frontend (Next.js) | `:3006` | `dothesislocal.webkaze.com` |
| **MCP server** | `:9000` | **`dothesislocal-api.webkaze.com/mcp`** (path-routed) |
| cloudflared tunnel | — | routes all of the above (`webkaze-local`) |

## 0. Prereqs (one-time)

- `.env` at repo root with at least: `DATABASE_URL`, `SESSION_SECRET`,
  `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `OFOX_API_KEY`, `AWS_*`, `WEB_ORIGIN`.
- Python venv: `python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt`
- Frontend deps: `cd web && npm install && npm run build` (prod build for `next start`).
- Docker Desktop running.

## 1. Postgres

```bash
docker compose up -d --remove-orphans postgres    # dev.sh does this + waits for ready
```

## 2. API (:7100) — with the /humanize endpoint on Gemini

The API must have the FULL `.env` in its process environment (langchain reads
`GOOGLE_API_KEY` from `os.environ`, not from pydantic-settings). Export, then run:

```bash
set -a; . ./.env; set +a
export ORCHESTRATOR_ENABLED=true \
       HUMANIZE_LLM_ROUTE=native HUMANIZE_LLM_MODEL=gemini-2.5-flash
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 7100 --app-dir api
```

Verify: `curl -s localhost:7100/api/v1/health` → `{"ok":true}` and
`curl -s -o/dev/null -w '%{http_code}' -XPOST localhost:7100/api/v1/humanize -d '{"text":"x x x x x"}'`
→ `401` (endpoint loaded, needs auth).

## 3. Frontend (:3006)

```bash
cd web
NEXT_PUBLIC_API_BASE=https://dothesislocal-api.webkaze.com/api/v1 \
  ./node_modules/.bin/next start -p 3006
```

## 4. MCP server (:9000)

Phase-1 uses a static access token (one real user). Mint one:

```bash
TOK=$(cd . && PYTHONPATH="$(pwd)/api" ORCHESTRATOR_ENABLED=true ./.venv/bin/python - <<'PY'
from app.settings import get_settings
from app.db import db_session
from app.models import User
from app.jwt_auth import sign_access_token
s=get_settings(); u=next(db_session()).query(User).first()
print(sign_access_token(str(u.id), secret=s.session_secret)[0])
PY
)
```

Run the SDK-free server (uses DoThesis's venv — Starlette only, no fastmcp):

```bash
cd mcp
DOTHESIS_API_URL=http://localhost:7100 DOTHESIS_ACCESS_TOKEN="$TOK" DOTHESIS_MCP_PORT=9000 \
  ../.venv/bin/python server_lite.py
```

(Production later: `server.py` + `fastmcp` in `mcp/.venv`, and OAuth instead of the static token.)

## 5. Cloudflare tunnel

MCP is PATH-ROUTED onto the existing API host rather than given its own
subdomain. What MCP actually requires is a publicly reachable HTTPS URL (Claude
cannot reach localhost) — not a hostname of its own. Sharing the host means one
DNS record and one certificate, and it keeps the process isolation that matters:
the MCP server still runs in its own venv and still talks to DoThesis over HTTP,
so the conflicting `fastmcp` / pinned-pydantic dependency trees never meet
(see `README.md`). Separate PROCESS, same ORIGIN.

Ingress rules in `~/.cloudflared/config.yml` — ORDER MATTERS, cloudflared takes
the first match, so the `/mcp` and `.well-known` rules must come BEFORE the
catch-all for the same hostname:

```yaml
  - hostname: dothesislocal-api.webkaze.com
    path: ^/mcp
    service: http://localhost:9000
  # OAuth discovery is fetched near the ORIGIN ROOT, not under /mcp, so these
  # must reach the MCP process too once the OAuth façade lands
  # (MCP_OAUTH_PLAN.md). Until then they 404 harmlessly.
  - hostname: dothesislocal-api.webkaze.com
    path: ^/.well-known/oauth-
    service: http://localhost:9000
  - hostname: dothesislocal-api.webkaze.com
    service: http://localhost:7100
```

No new DNS route is needed — `dothesislocal-api.webkaze.com` already resolves.

Run / reload the tunnel (a config change needs a RESTART — SIGHUP does not reload ingress):

```bash
cloudflared tunnel run webkaze-local
```

## 6. Verify end-to-end (public)

```bash
curl -s -XPOST https://dothesislocal-api.webkaze.com/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

Should list the `humanize` tool. A `tools/call` runs the real humanize (Gemini, ~20-30s).

⚠️ The path-routed URL above is NOT yet verified end-to-end — the ingress rules
in §5 changed from a dedicated `dothesis-mcp.webkaze.com` hostname to a `/mcp`
path on the API host, and cloudflared needs a RESTART (SIGHUP does not reload
ingress) before this curl can pass. Run it after restarting; if it returns the
API's 404 instead of a JSON-RPC result, the catch-all rule is matching first —
the `/mcp` rule must be listed BEFORE it.

## Notes / gotchas

- **API needs `.env` EXPORTED**, not just present — else Gemini calls 500 with
  "API key required" (pydantic-settings ≠ os.environ).
- **Tunnel reload = restart** `cloudflared tunnel run`, not SIGHUP. It briefly
  blips ALL webkaze sites (~seconds), then restores.
- **Persistence:** everything above is foreground/nohup today → dies on reboot.
  For the campaign, wrap steps 2/4/5 in `launchd` (macOS) or `pm2` so they auto-start.
- **Claude connector needs OAuth** — the static-token setup works with MCP
  Inspector / curl, but claude.ai's custom connector requires the OAuth façade
  (see `MCP_OAUTH_PLAN.md`) before it can be added there.

# DoThesis + MCP — run behind the webkaze tunnel (dev)

The exact steps to bring the whole stack up so the MCP is reachable at
`https://dothesislocal.webkaze.com/mcp`. All commands run from the repo root
(`.../learning_app/dothesis`) unless noted. This is the DEV setup (Mac +
Cloudflare tunnel). Production (app.dothesis.com, nginx + systemd) is §5b.

Ports / hosts:

| Piece | Local | Public (tunnel) |
|---|---|---|
| Postgres (docker) | `:5432` | — |
| API (FastAPI) | `:7100` | `dothesislocal-api.webkaze.com` |
| Frontend (Next.js) | `:3006` | `dothesislocal.webkaze.com` |
| **MCP server + OAuth** | `:9000` | **`/mcp`, `/oauth/*`, `/.well-known/oauth-*`** (path-routed on the WEB host) |
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

## 4. MCP server + OAuth façade (:9000)

No token to mint any more — the façade signs users in with the DoThesis session
their browser already has. It needs `SESSION_SECRET`, because the tokens it
issues must be the same shape the API verifies:

```bash
cd mcp
set -a; . ../.env; set +a          # SESSION_SECRET + DATABASE_URL
DOTHESIS_API_URL=http://localhost:7100 DOTHESIS_MCP_PORT=9000 \
  ../api/.venv/bin/python server_lite.py
```

Grants are stored in DoThesis's Postgres, so step 1 must be up and
`alembic upgrade head` must have run (`20260803_mcpoauth01` creates the tables).

Verify it is up and refusing anonymous callers *correctly* — the
`WWW-Authenticate` header is what sends a client into the OAuth flow, so its
absence is a silent failure:

```bash
curl -si -XPOST localhost:9000/mcp -d '{"jsonrpc":"2.0","id":1,"method":"initialize"}' \
  | grep -i www-authenticate
# -> Bearer realm="DoThesis", resource_metadata=".../.well-known/oauth-protected-resource/mcp"
```

The old static `DOTHESIS_ACCESS_TOKEN` still works behind
`DOTHESIS_MCP_REQUIRE_AUTH=0`, for poking at the tool with curl without a
browser. It acts as one real user and has no auth in front of it — never set it
on a public host.

## 5. Cloudflare tunnel

MCP is PATH-ROUTED onto the existing API host rather than given its own
subdomain. What MCP actually requires is a publicly reachable HTTPS URL (Claude
cannot reach localhost) — not a hostname of its own. Sharing the host means one
DNS record and one certificate, and it keeps the isolation that matters: the MCP
server is a separate PROCESS that talks to DoThesis over HTTP and never imports
it. Separate PROCESS, same ORIGIN.

Sharing the origin is not merely tolerable here, it is what makes per-user login
work: the DoThesis session cookie is same-origin, so `/oauth/authorize` can read
it and skip a second sign-in entirely (see `README.md` → Auth).

Ingress rules in `~/.cloudflared/config.yml` — ORDER MATTERS, cloudflared takes
the first match, so the `/mcp` and `.well-known` rules must come BEFORE the
catch-all for the same hostname:

```yaml
  - hostname: dothesislocal.webkaze.com
    path: ^/mcp
    service: http://localhost:9000
  # OAuth discovery is fetched near the ORIGIN ROOT, not under /mcp, so these
  # must reach the MCP process too. The façade is built now, so these rules are
  # load-bearing rather than placeholders: without them the client gets the web
  # app's HTML and fails dynamic client registration.
  - hostname: dothesislocal.webkaze.com
    path: ^/.well-known/oauth-
    service: http://localhost:9000
  - hostname: dothesislocal.webkaze.com
    path: ^/oauth/
    service: http://localhost:9000
  - hostname: dothesislocal.webkaze.com
    service: http://localhost:3006
```

Routed on the WEB host, not the API host. From a browser the whole product is
already ONE origin — `web/proxy.js` shows `/api/v1/*` is a Next rewrite onto
FastAPI — so putting `/mcp` there too means the connector URL is simply the
address the student is already looking at. That is what lets the setup page read
it off `window.location` with nothing to configure per environment.

No new DNS route is needed — `dothesislocal-api.webkaze.com` already resolves.

Run / reload the tunnel (a config change needs a RESTART — SIGHUP does not reload ingress):

```bash
cloudflared tunnel run webkaze-local
```

## 5b. Production (app.dothesis.com) — nginx, not cloudflared

`scripts/deploy.sh` installs `dothesis-mcp.service` and starts it on :9000.
nginx then has to route the same four paths, which `deploy/nginx/dothesis.conf`
now does:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

⚠️ Do NOT copy the template over the installed vhost. The file on the server is
the certbot-modified copy that owns the 443 listener and the certificate paths;
overwriting it drops TLS for the whole site. Paste just the new
`location ~ ^/(mcp$|mcp/|oauth/|\.well-known/oauth-)` block into the existing
443 server block, ABOVE `location /`.

## 6. Verify end-to-end (public)

Three checks, in order. Each fails differently, and the first one that fails
tells you which layer is wrong:

```bash
BASE=https://app.dothesis.com          # or the tunnel host in dev

# 1. ROUTING — does /mcp reach the MCP process at all?
curl -si -XPOST $BASE/mcp -d '{"jsonrpc":"2.0","id":1,"method":"initialize"}' | head -1
# 401 = correct, it wants a token. 404 + HTML = the proxy is still sending this
# to Next.js, which is the entire "couldn't register" bug.

# 2. DISCOVERY — can a client find the authorization server?
curl -s $BASE/.well-known/oauth-protected-resource/mcp
curl -s $BASE/.well-known/oauth-authorization-server
# Both must be JSON, and every URL inside must start with https://app.dothesis.com.
# http:// or 127.0.0.1 means nginx isn't passing Host / X-Forwarded-Proto.

# 3. REGISTRATION — the exact step Claude reported failing.
curl -s -XPOST $BASE/oauth/register -H 'Content-Type: application/json' \
  -d '{"client_name":"probe","redirect_uris":["https://claude.ai/api/mcp/auth_callback"]}'
# -> 201 with a client_id. Anything else and the connector cannot be added.
```

Then add the connector in Claude by URL. It registers itself, bounces you
through DoThesis login + consent, and `humanize` appears. A `tools/call` runs
the real humanize (Gemini, ~20-30s) against YOUR credits.

⚠️ Verified locally against a real uvicorn process (register → login bounce →
consent → PKCE exchange → authenticated `tools/list`) and by 27 tests in
`tests/test_mcp_oauth.py`. NOT yet verified on app.dothesis.com — that needs the
deploy + nginx reload above.

## Notes / gotchas

- **API needs `.env` EXPORTED**, not just present — else Gemini calls 500 with
  "API key required" (pydantic-settings ≠ os.environ).
- **Tunnel reload = restart** `cloudflared tunnel run`, not SIGHUP. It briefly
  blips ALL webkaze sites (~seconds), then restores.
- **Persistence:** everything above is foreground/nohup today → dies on reboot.
  For the campaign, wrap steps 2/4/5 in `launchd` (macOS) or `pm2` so they auto-start.
- **Claude connector needs OAuth** — built (`mcp/oauth.py`). The failure mode to
  recognise: "Couldn't register with dothesis's sign-in service" is dynamic
  client registration failing, and it is almost always a PROXY ROUTING problem
  (one of the four paths falling through to Next.js), not a code one. §6 check 3
  isolates it in one curl.
- **`SESSION_SECRET` must match the API's.** The façade signs the tokens the API
  verifies. A mismatch produces a connector that completes the whole OAuth
  handshake and then 401s on every tool call.
- **Connector grants are in Postgres**, not a file — `mcp_oauth_clients`,
  `mcp_oauth_codes`, `mcp_oauth_refresh_tokens`. They are covered by the normal
  database backup. Truncating `mcp_oauth_clients` de-registers every connector
  and users must re-add DoThesis in their client. A leftover `mcp/oauth.db` from
  before the move is dead weight — delete it.

# DoThesis MCP

Connect DoThesis into Claude (claude.ai / Claude Desktop) as a **connector**. The
end user adds "DoThesis", logs in once, and gets DoThesis tools in their chat.
Powers the giveaway/marketing campaign.

**Honest claim (must match everywhere, incl. campaign copy):** the `humanize`
tool reduces the **AI-detection** "smell" of already-written academic prose while
freezing all numbers/tables/terms/citations. It is **not** a plagiarism
(similarity) tool and does **not** guarantee passing any detector. See `SKILL.md`.

## Layout

| File | What |
|---|---|
| `server_lite.py` | The MCP server in production: `humanize` tool + bearer auth. Thin adapter → DoThesis API. |
| `oauth.py` | OAuth 2.1 façade — discovery, dynamic client registration, `/authorize`, `/token`, `/revoke`. Stores grants in DoThesis's Postgres. |
| `audit.py` | Records every tool call to `mcp_tool_calls`. Never raises — bookkeeping must not veto the tool result. |
| `tools.py` | The tool registry — one entry per tool: schema, tier, and the DoThesis endpoint it forwards to. |
| `ratelimit.py` | Per-user, per-tier throttle counted off `mcp_tool_calls`. Fails open. |
| `server.py` | fastmcp variant, unused in production. Kept for the day the protocol surface outgrows `server_lite.py`. |
| `requirements.txt` | Isolated deps (`fastmcp`, `httpx`). **Own venv, not DoThesis's.** |
| `SKILL.md` | End-user Claude skill packaging the humanize workflow. |
| `MCP_OAUTH_PLAN.md` | The original build plan. Historical now — items 1-5 are built. |

## Architecture

```
Claude ──MCP (Streamable-HTTP)──▶ mcp/server_lite.py ──HTTP──▶ DoThesis API /api/v1/humanize
          + OAuth 2.1              (tiny adapter,               (does the real work: anchor,
            handshake               forwards the caller's        frozen-token verify, model)
                                    own bearer)
                          ▲
                          └── mcp/oauth.py issues that bearer, reusing the
                              DoThesis browser session as the identity source
```

The server never imports DoThesis in-process — it calls the API — so its deps
stay isolated and DoThesis's pinned pydantic is safe.

## Auth

Per-user OAuth 2.1, implemented in `oauth.py`. The short version of how it
works, because the shape is unusual:

- **No new identity provider.** DoThesis already knows who the user is.
  `web/app/lib/tokenStore.ts` mirrors the session JWT into a non-HTTPOnly
  `dothesis_access_token` cookie so the Next middleware can gate routes. MCP is
  path-routed onto the SAME origin, so that cookie reaches `/oauth/authorize` on
  top-level navigation — which is exactly the navigation Claude performs.
  "Log the user in" therefore means "read the session the browser already has",
  and only a browser without one gets bounced to `/login`.
- **The access token we issue IS a DoThesis access token** — same HS256 secret,
  same `sub` claim, plus `typ: "mcp"`. `api/app/deps.py` already accepts
  `Authorization: Bearer`, so `server_lite.py` forwards the caller's token
  straight to `/api/v1/humanize` and the call runs as that user with that
  user's credits. No metering or ownership logic is duplicated.
- **The honest cost:** an MCP token carries full account authority, not a
  humanize-only capability. It is contained by TIME (1 hour, vs 7 days for a web
  session) behind a rotating, revocable 30-day refresh token. Narrowing it
  further means teaching `verify_access_token` about `typ="mcp"` — a change to
  the API's auth core, which is a bigger blast radius than this needs today.

### Where the grants live

DoThesis's own Postgres — `mcp_oauth_clients`, `mcp_oauth_codes`,
`mcp_oauth_refresh_tokens` (migration `20260803_mcpoauth01`, models in
`api/app/models.py`). The MCP process reaches them with plain psycopg and
hand-written SQL; it still imports nothing from `app.*`.

They started in a process-local SQLite file. Moving them was worth it because
the data is not private to that process:

- connector installs are a campaign metric (`MCP_OAUTH_PLAN.md` item 6), so
  they should be a query rather than an SSH session;
- `POST /api/v1/connectors/list` + `/revoke` let a student see and disconnect a
  connected app from DoThesis itself — impossible while the API couldn't see
  the grants;
- a foreign key to `users` means deleting an account takes its grants with it.

⚠️ **Two couplings to keep in sync by hand**, both the deliberate price of an
import-free MCP process:

1. **Token format.** `oauth.py` re-implements JWT sign/verify with PyJWT rather
   than importing `api/app/jwt_auth.py`. Same secret (`SESSION_SECRET`), same
   algorithm (HS256), same `sub` claim.
2. **Schema.** The SQL in `oauth.py` is written against `api/app/models.py`.
   Change a column there and change it here.

## Run locally

```bash
cd mcp
export DOTHESIS_API_URL=http://localhost:7100   # DoThesis API (orchestrator_enabled)
export SESSION_SECRET=<the same secret the API uses>
export DATABASE_URL=<the same Postgres the API uses>
../api/.venv/bin/python server_lite.py          # http://127.0.0.1:9000
```

Uses the API's venv: `server_lite.py` needs only
starlette/uvicorn/httpx/PyJWT/psycopg, all already there. The separate `mcp/.venv` exists for `server.py`, whose
`fastmcp` dependency wants a pydantic DoThesis pins away from.

Then point an MCP client at `http://127.0.0.1:9000/mcp`. It will 401 and follow
the `WWW-Authenticate` header into the OAuth flow.

## What the proxy must route

Four paths have to reach this process, not the Next.js app. Three of them sit at
the ORIGIN ROOT rather than under `/mcp`, because that is where OAuth clients
look for them — the one genuine cost of sharing an origin with the web app:

| Path | Why |
|---|---|
| `/mcp` | the protocol endpoint |
| `/.well-known/oauth-protected-resource*` | RFC 9728 — tells the client an authorization server exists |
| `/.well-known/oauth-authorization-server*` | RFC 8414 — the endpoint directory |
| `/oauth/*` | register / authorize / token / revoke |

`deploy/nginx/dothesis.conf` does this in production; RUNBOOK §5 has the
cloudflared equivalent for dev. If any of them falls through to Next.js, the
client gets an HTML 404 where it expected JSON and reports **"Couldn't register
with dothesis's sign-in service"** — that message is dynamic client
registration failing, and it is almost always a routing problem, not a code one.

Two smaller traps, both already paid for:

- `web/proxy.js` must exclude these paths from page middleware, or they 307 to
  `/login` and produce the same error (fixed in a0c01d3).
- Nothing else may claim `/mcp`. The setup guide originally lived there and
  shadowed the endpoint; it now lives at `/connect`.

## Two server variants

| File | Deps | Use |
|---|---|---|
| `server_lite.py` | `starlette` only (already in the API's venv) | **What runs in production.** Minimal Streamable-HTTP MCP: `initialize`, `tools/list`, `tools/call`, `ping`, plus bearer auth and the OAuth routes. |
| `server.py` | `fastmcp`, needs `mcp/.venv` | Unused. The fuller protocol surface (server-initiated SSE, sessions) if `humanize` ever needs it. It has NO auth — do not expose it as-is. |

`server_lite.py` won because the protocol surface a single synchronous tool
needs is small, and keeping it in the API's venv removes the `fastmcp` /
pinned-pydantic conflict entirely rather than working around it.

## Status (2026-08-03)

- ✅ DoThesis API `POST /api/v1/humanize` (existing Bearer/JWT auth) — built, mapping
  unit-tested, verified end-to-end (real Gemini rewrite, frozen tokens preserved).
- ✅ `oauth.py` — OAuth 2.1 façade: discovery (both bare and path-aware forms),
  dynamic client registration, PKCE-only `/authorize` + `/token`, rotating
  refresh tokens, `/revoke`. Grants in Postgres. 27 tests in
  `api/tests/test_mcp_oauth.py`.
- ✅ `POST /api/v1/connectors/list` + `/revoke` — see and disconnect a connected
  AI app from DoThesis itself. 8 tests in `api/tests/test_connectors.py`.
- ✅ **Usage is audited.** Every tool call writes a `mcp_tool_calls` row (user,
  connector, tool, ok/error, duration, input/output SIZES — never the prose).
  Admin view at `/admin/connectors`; API is `POST /api/v1/admin/connectors/calls`
  and `/summary`. 10 tests in `api/tests/test_admin_connectors.py`, 5 more in
  `test_mcp_oauth.py`.
- ✅ **Metered and billed.** `humanize_prose` reports per-call token usage
  (`usage`), and the endpoint writes a `token_ledger` row per LLM call and
  debits the caller at each model's own rate (`credit_multiplier`), the same way
  `job_runner._charge_auto_run` prices auto runs. `token_ledger.user_id` was
  added so a project-less call is attributable. Metering commits SEPARATELY from
  billing: an unbillable call must not erase its own cost record.
  `credits_charged` comes back in the response.
  **Known trade:** the charge is capped at the balance rather than refused
  up-front, matching auto runs — a user at zero gets the rewrite and is
  under-billed (logged, and visible in `token_ledger`). A hard pre-flight gate
  is a pricing decision, not a metering one; say so if you want it.
- ✅ **Nine tools** (`tools.py`): `humanize`, `writing_rhythm`, `verify_citation`,
  `check_credits`, `list_projects`, `project_status`, `get_artifacts`,
  `start_thesis`, `check_thesis_run`. Each is a thin forward to an existing
  DoThesis endpoint carrying the caller's own bearer, so auth, ownership,
  quotas and credit debits all apply unchanged.
- ✅ **Rate limited** per user per tier (`ratelimit.py`): light 120/10min,
  model 20/10min, heavy 5/hr. Counted off `mcp_tool_calls`, so the limit is
  enforced against exactly the history `/admin/connectors` shows. Fails open.

### Two honesty constraints baked into the tools

- **`writing_rhythm` is not a detector.** It runs `StylometricScorer`, whose own
  docstring calls it "a WEAK signal ... must not be read as a verdict" — it sees
  burstiness, not perplexity. The tool description and the endpoint both say so,
  and `test_tools_router.py` asserts the response never names a detector or
  implies flagging. If that ever needs to become a real prediction, wire a
  scorer backend (`HUMANIZE_SCORER=originality`) rather than re-wording this.
- **`verify_citation` distinguishes proof from evidence.** A DOI hit is exact; a
  bibliographic search is fuzzy and says so, because CrossRef returns a best
  guess for any query. A network failure returns `ok=false`, never
  `found=false` — telling a student a real source is fabricated because an API
  blipped is the worst error this tool could make.
- ✅ `server_lite.py` — bearer-protected; 401s carry the `resource_metadata`
  hint that starts the OAuth flow. The static `DOTHESIS_ACCESS_TOKEN` path is
  now off by default (`DOTHESIS_MCP_REQUIRE_AUTH=0` to restore it, dev only).
- ✅ Full handshake verified locally against a real uvicorn process: register →
  login bounce → consent → code → PKCE token exchange → authenticated
  `tools/list`.
- ✅ `dothesis-mcp.service` + nginx routing land via `scripts/deploy.sh` and
  `deploy/nginx/dothesis.conf`.
- ⏳ **Not yet verified in production.** The deploy has to actually run on the
  app.dothesis.com host — nginx needs the new locations and a reload — before
  `https://app.dothesis.com/mcp` answers anything but a Next.js 404. RUNBOOK §6
  is the check.
- ⏳ Later: `tools/call humanize` over the public URL end-to-end; phase-2 tools
  (`generate_outline`, `export_docx`).

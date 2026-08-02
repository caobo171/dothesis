# DoThesis MCP server + OAuth — build plan (for the "connect DoThesis in Claude" campaign)

Goal: end users add a **"DoThesis" connector** in Claude (claude.ai / Claude Desktop),
log in once, and get DoThesis tools — first `humanize`, later `generate` — usable
straight from their Claude chat. Powers the giveaway/marketing campaign.

## What already exists (so we don't rebuild it)

DoThesis API (`api/app/`) already has the identity layer:
- **Google OAuth login** → `google_auth.py` (verifies Google id_token).
- **JWT / access tokens** → `jwt_auth.py`, `auth_tokens.py`.
- **Bearer-token auth on endpoints** → `deps.py` accepts `Authorization: Bearer <token>`.
- Users, credits, quotas, S3, SSE jobs — all there.

So we do **not** need a new OAuth provider (Auth0/Clerk). We wrap the existing
login as the identity source and add only the thin MCP-spec OAuth layer on top.

## The gap: MCP remote servers need an OAuth 2.1 *authorization-server* handshake

Claude's remote-MCP connector flow (per the MCP auth spec) expects the server to expose:
- `GET /.well-known/oauth-protected-resource` (resource metadata)
- `GET /.well-known/oauth-authorization-server` (AS metadata)
- **Dynamic Client Registration** (`POST /register`) — Claude registers itself
- `GET /authorize` (user consent → we bounce to DoThesis Google login) + `POST /token` (PKCE)
- The MCP endpoint itself, protected by the issued access token.

DoThesis's current Google/JWT login is *user* auth, not this AS handshake — that's
the one piece to add. Recommended: a small **OAuth 2.1 façade** that delegates the
actual human login to the existing Google flow, then issues our own short-lived
MCP access token bound to the DoThesis user.

## Transport & tools

- **Transport:** Streamable HTTP MCP (the current remote-MCP standard; SSE is legacy).
- **Tools exposed (phase 1):**
  - `humanize(text, user_anchor?)` → wraps `orchestrator.tools.humanize.humanize_prose`
    (frozen-token guarantee already built in). The campaign hook.
  - `humanize_status`/quota read (so users see credits) — optional.
- **Phase 2:** `generate_outline`, `generate_chapter`, `export_docx` — the full DoThesis
  pipeline (these are tool-heavy + long-running → return a job id + SSE/poll).

## Build checklist

1. **MCP server** (`mcp/server.py`): Streamable-HTTP MCP app (Python MCP SDK / FastMCP),
   mounted alongside FastAPI or as a sibling service. Register `humanize` tool → calls
   `humanize_prose`. Per-call: resolve DoThesis user from the MCP access token, check
   credits (`credit_ledger`/`quotas`), meter usage.
2. **OAuth 2.1 façade** (`mcp/oauth.py`): the `.well-known` metadata + `/register`
   (dynamic client reg) + `/authorize` (→ Google login → consent) + `/token` (PKCE).
   Issue MCP access tokens tied to the existing user record.
3. **Wire humanize as an HTTP-callable** if not already — currently humanize lives in
   the orchestrator, not as a REST route; expose it internally for the MCP tool.
4. **Deploy:** public HTTPS endpoint — REQUIRED, Claude connects
   over the internet, localhost won't work. Terminate TLS, reverse-proxy to the MCP app.
5. **Register in Claude:** add connector by URL → OAuth handshake → tools appear.
6. **Guardrails:** rate limits + credits per user (giveaway = free tier with a cap);
   log usage for the campaign metrics.

## Two things only the owner can provide (everything else I can build)

- **A public HTTPS endpoint** for the MCP server. A dedicated subdomain works,
  but so does path-routing (`dothesis.xyz/mcp`) on the existing host — MCP needs
  reachability, not a hostname. If path-routed, the proxy must ALSO send
  `/.well-known/oauth-protected-resource` and `/.well-known/oauth-authorization-server`
  to the MCP process: clients look for those near the ORIGIN ROOT, not under the
  `/mcp` path, so the web app must not claim them. Verify the exact discovery
  path convention against the current MCP spec when implementing — it defines a
  path-aware form for exactly this case.
- **Confirm the auth approach:** reuse DoThesis Google login as the identity source
  (recommended, no new vendor) — vs. plug an external IdP. Default = reuse Google.

## Honest scope note

This is a multi-step build (server + OAuth façade + deploy), not a one-shot. The
`humanize` MCP tool + local run is the fast first milestone; the OAuth façade + public
deploy is the longer pole and depends on the domain above. Campaign claims must match
`mcp/SKILL.md` — "giảm mùi AI, giữ số liệu", never "pass đạo văn / guaranteed detector".

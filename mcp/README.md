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
| `server.py` | The MCP server (phase 1: `humanize` tool). Thin adapter → DoThesis API. |
| `requirements.txt` | Isolated deps (`fastmcp`, `httpx`). **Own venv, not DoThesis's.** |
| `SKILL.md` | End-user Claude skill packaging the humanize workflow. |
| `MCP_OAUTH_PLAN.md` | Build plan for the OAuth 2.1 façade + public deploy (phase 2). |

## Architecture

```
Claude  ──MCP (Streamable-HTTP)──▶  mcp/server.py  ──HTTP──▶  DoThesis API /api/v1/humanize
                                    (tiny adapter)            (does the real work: anchor,
                                                               frozen-token verify, model)
```

The server never imports DoThesis in-process — it calls the API — so its deps
stay isolated and DoThesis's pinned pydantic is safe.

## Run locally (phase 1, no OAuth yet)

```bash
cd mcp
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export DOTHESIS_API_URL=http://localhost:7100          # DoThesis API (orchestrator_enabled)
export DOTHESIS_ACCESS_TOKEN=<a dev user's access token>   # temporary, phase-1 only
.venv/bin/python server.py                              # http://127.0.0.1:9000
```

Then point an MCP client at `http://127.0.0.1:9000` and call `humanize`.

## Go public (phase 2) — what's needed

1. **A public HTTPS domain** (e.g. `mcp.dothesis.xyz`) — the ONE external thing
   the owner must provide. Claude connects over the internet; localhost won't work.
2. The **OAuth 2.1 façade** (`MCP_OAUTH_PLAN.md`): `.well-known` metadata, dynamic
   client registration, `/authorize` → DoThesis Google login, `/token` (PKCE),
   minting a per-user token (drops the static `DOTHESIS_ACCESS_TOKEN`).
3. Add the connector in Claude by URL → OAuth handshake → `humanize` appears.

## Two server variants

| File | Deps | Use |
|---|---|---|
| `server.py` | `fastmcp` | Production path (proper protocol/SSE/sessions). Needs the SDK. |
| `server_lite.py` | `starlette` only (already in DoThesis's venv) | SDK-free minimal Streamable-HTTP MCP for hosts where `fastmcp` can't be installed. What's running on the live dev tunnel now. |

## Status (2026-08-02)

- ✅ DoThesis API `POST /api/v1/humanize` (existing Bearer/JWT auth) — built, mapping
  unit-tested, verified end-to-end (real Gemini rewrite, frozen tokens preserved).
- ✅ `server_lite.py` — running on `127.0.0.1:9000`, tunneled at
  **`https://dothesis-mcp.webkaze.com/mcp`** (Cloudflare tunnel `webkaze-local`).
  `initialize` / `tools/list` / `tools/call humanize` all verified over the public URL.
- ⚠️ **DEV ONLY, NOT SECURE YET:** the tunnel uses a single static `DOTHESIS_ACCESS_TOKEN`
  (acts as one real user) and has no auth in front — do not publish the URL. Claude's
  connector also *requires* OAuth for remote MCP, so it can't be added to claude.ai
  until the OAuth façade lands.
- ⏳ Next: OAuth 2.1 façade (reuse Google login) → per-user tokens → add to Claude.
  Then run all three (API, MCP, tunnel) under a process manager for persistence.

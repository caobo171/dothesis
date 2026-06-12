# Project conventions

## HTTP: POST-only, no GET endpoints

Every new endpoint in `api/app/routers/` is `@router.post(...)` regardless of
semantics. No `@router.get(...)`. Read-only operations also go through POST
with the lookup parameters in the JSON body.

Why:
- Auth tokens travel in the request body (no cookies, no header negotiation).
  Forcing POST means there is always a body to attach the token to.
- Uniform fetch surface on the web client — one helper, one error path.
- SSE / streaming endpoints already require POST; making everything POST
  removes the GET/POST split mid-flow.

How to apply:
- New routes: `@router.post("/path")`. Body schema (Pydantic) holds any
  filters/ids/pagination that would have lived in the query string.
- Existing GET routes get migrated to POST when next edited. Don't bulk-
  rewrite — touch them when they're already in flight for another change.
- Tests + frontend fetchers update at the same time as the route they call.
- `GET /api/v1/health` is the one allowed exception — load balancers and
  probes expect GET.

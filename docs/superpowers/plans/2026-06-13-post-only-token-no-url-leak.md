# POST-Only Migration + No-Token-In-URL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the long-lived JWT from ever appearing in a URL (and the server access log) by migrating every read GET endpoint to POST (token in body) and replacing the query-param JWT on the few browser-GET-only endpoints (downloads + EventSource SSE) with short-lived, resource-scoped stream tokens.

**Architecture:**
- **Category A (≈25 routes)** — JSON reads consumed via `swrFetcher`/`apiFetch`/fetch-streaming. These become `@router.post`, the token rides in the JSON body, and any `Query(...)`/extra params move into a Pydantic body that inherits `AuthedBody`. The keystone frontend change is making `swrFetcher` (and the SWR default path) issue POSTs, folding the SWR key's `?query` into the body so call-site SWR keys stay unchanged.
- **Category B (3 routes)** — `jobs/{job_id}/events` (EventSource), `papers/{paper_id}/exports/{fmt}` and `exports/projects/{project_id}/exports/{filename}` (anchor downloads). Browser `EventSource` and `<a download>` are GET-only and cannot carry a body or custom header. These keep GET but stop accepting the JWT in the URL; instead the client first mints a **stream token** (`POST /auth/stream-token`) scoped to one resource with a ~120s TTL, and passes that in `?st=`.
- **Single-use caveat:** `EventSource` auto-reconnects by reopening the *same* URL on every network blip, so a strictly single-use token would break SSE reconnection. The stream token is therefore short-TTL + resource-scoped (`typ=stream`, `scope=<resource>`) rather than strictly one-time. This still removes the long-lived JWT from URLs/logs and caps blast radius to one resource for ~2 minutes. True one-time semantics (nonce store) is deferred — see "Deferred / out of scope".
- **Final hardening:** once A is POST and B uses stream tokens, the `?access_token=` query fallback in `deps.py:_extract_token` is removed, killing the leak vector for the JWT entirely.

**Tech Stack:** FastAPI + Pydantic v2 (`AuthedBody`), PyJWT (HS256), SQLAlchemy; Next.js + SWR + a `useStream` fetch-streaming hook + `EventSource`; pytest (backend), vitest + MSW (frontend).

**Test commands:**
- Backend: `cd api && .venv/bin/python -m pytest <path> -v`
- Frontend: `cd web && npm test -- <path>` (vitest run)

**Conventions to honor (CLAUDE.md + memory):**
- All endpoints POST except the one allowed `GET /api/v1/health`. Category B GETs are the documented narrow exception (browser primitives), now hardened with stream tokens.
- Every code change carries a short comment explaining the *why/decision* (project rule).

---

## File Structure

**Backend (create/modify):**
- `api/app/jwt_auth.py` — add `sign_stream_token` / `verify_stream_token` + `STREAM_TOKEN_TTL_SECONDS`. (Modify)
- `api/app/deps.py` — add `stream_user_factory(scope_builder)` dependency for Category B; later remove the `?access_token=` query fallback from `_extract_token`. (Modify)
- `api/app/routers/auth.py` — add `POST /auth/stream-token` mint endpoint. (Modify)
- `api/app/routers/{chat,papers,runs,uploads,credit,announcements,m5_editor,jobs,admin_users,admin_papers,admin_orders,admin_jobs,admin_announcements,exports}.py` — GET→POST (Category A) or GET+stream_user (Category B). (Modify)
- `api/tests/test_stream_token.py` — new unit + endpoint tests for the token machinery. (Create)
- Existing `api/tests/test_*.py` — switch the affected calls from `client.get(...?access_token=)` to `client.post(..., json={...})` or `?st=`. (Modify)

**Frontend (modify):**
- `web/app/lib/api.js` — `swrFetcher`/`apiFetch` POST + query-fold; `openEventStream` becomes async + mints a stream token; add `mintStreamToken(scope)` + `buildDownloadHref(url, scope)` helpers. 
- `web/app/components/chat/hooks/useProjectState.ts` — `/state` via POST body.
- `web/app/components/chat/ChatPane.tsx` — upload token into FormData, not query.
- `web/app/components/chat/ContextPanel.tsx`, `ChatHeader.tsx` — download links mint a stream token (onClick) instead of embedding the JWT.
- `web/app/components/agent-run.jsx` — inherits `openEventStream` change (await).
- `web/app/components/editor/CitePopover.tsx` — `apiFetch` GET → POST (direct caller).
- Frontend test files using MSW `http.get(...)` for migrated routes → `http.post(...)`.

---

## Phase 1 — Stream-token machinery (backend)

### Task 1: `sign_stream_token` / `verify_stream_token`

**Files:**
- Modify: `api/app/jwt_auth.py`
- Test: `api/tests/test_stream_token.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_stream_token.py
import time
import pytest
from app.jwt_auth import sign_stream_token, verify_stream_token

SECRET = "x" * 32

def test_roundtrip_ok():
    tok, exp = sign_stream_token("user-1", scope="job:abc", secret=SECRET)
    claims = verify_stream_token(tok, expected_scope="job:abc", secret=SECRET)
    assert claims.user_id == "user-1"
    assert claims.scope == "job:abc"
    assert exp > int(time.time())

def test_wrong_scope_rejected():
    tok, _ = sign_stream_token("user-1", scope="job:abc", secret=SECRET)
    with pytest.raises(ValueError, match="scope"):
        verify_stream_token(tok, expected_scope="job:other", secret=SECRET)

def test_expired_rejected():
    tok, _ = sign_stream_token("u", scope="job:abc", secret=SECRET, ttl_seconds=-1)
    with pytest.raises(ValueError, match="expired"):
        verify_stream_token(tok, expected_scope="job:abc", secret=SECRET)

def test_access_token_not_accepted_as_stream():
    # An ordinary access token (no typ=stream) must not pass stream verification.
    from app.jwt_auth import sign_access_token
    tok, _ = sign_access_token("u", secret=SECRET)
    with pytest.raises(ValueError):
        verify_stream_token(tok, expected_scope="job:abc", secret=SECRET)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd api && .venv/bin/python -m pytest tests/test_stream_token.py -v`
Expected: FAIL — `ImportError: cannot import name 'sign_stream_token'`.

- [ ] **Step 3: Implement in `api/app/jwt_auth.py`**

Add near `ACCESS_TOKEN_TTL_SECONDS`:

```python
# Stream tokens ride in the URL of browser-GET-only endpoints (EventSource SSE
# + <a download>), which cannot carry a JSON body. Decision: keep them very
# short-lived (120s) and bound to ONE resource via `scope`, so a leaked URL is
# useful only for that resource for ~2 min and can NOT unlock the JSON API
# (verify_stream_token requires typ=="stream"). Not strictly single-use:
# EventSource reconnects reopen the same URL, so one-time use would break SSE.
STREAM_TOKEN_TTL_SECONDS = 120
```

Add a claims dataclass + the two functions:

```python
@dataclass(slots=True)
class StreamTokenClaims:
    user_id: str
    scope: str
    expires_at: int


def sign_stream_token(user_id: str, *, scope: str, secret: str,
                      ttl_seconds: int = STREAM_TOKEN_TTL_SECONDS) -> tuple[str, int]:
    """Sign a short-lived, resource-scoped token for a browser-GET endpoint.

    `scope` binds the token to one resource+action (e.g. "job:<id>",
    "paper-export:<id>:<fmt>", "project-export:<id>/<filename>"). Returns
    (token, expires_at_epoch).
    """
    now = int(time.time())
    exp = now + ttl_seconds
    payload: dict[str, Any] = {
        "sub": str(user_id), "scope": scope, "typ": "stream",
        "iat": now, "exp": exp,
    }
    return _jwt.encode(payload, secret, algorithm=_JWT_ALGO), exp


def verify_stream_token(token: str, *, expected_scope: str,
                        secret: str) -> StreamTokenClaims:
    """Verify a stream token AND that it was minted for `expected_scope`.

    Raises ValueError on bad signature / malformed / expired / wrong typ /
    scope mismatch. Scope is checked here (not just by the caller) so a token
    minted for resource A can never be replayed against resource B.
    """
    try:
        payload = _jwt.decode(token, secret, algorithms=[_JWT_ALGO])
    except _jwt.ExpiredSignatureError as e:
        raise ValueError("stream token expired") from e
    except _jwt.InvalidTokenError as e:
        raise ValueError(f"bad stream token: {e}") from e
    if payload.get("typ") != "stream":
        raise ValueError("not a stream token")
    sub = payload.get("sub")
    scope = payload.get("scope")
    exp = payload.get("exp")
    if not isinstance(sub, str) or not isinstance(scope, str) or not isinstance(exp, int):
        raise ValueError("malformed stream token claims")
    if scope != expected_scope:
        raise ValueError(f"stream token scope mismatch: {scope!r} != {expected_scope!r}")
    return StreamTokenClaims(user_id=sub, scope=scope, expires_at=exp)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd api && .venv/bin/python -m pytest tests/test_stream_token.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add api/app/jwt_auth.py api/tests/test_stream_token.py
git commit -m "feat(auth): add short-lived resource-scoped stream tokens"
```

---

### Task 2: `stream_user` dependency

**Files:**
- Modify: `api/app/deps.py`
- Test: `api/tests/test_stream_token.py` (append)

- [ ] **Step 1: Write the failing test** (append to `test_stream_token.py`)

```python
def test_stream_user_dependency(monkeypatch):
    # stream_user_factory builds a FastAPI dependency that reads ?st=, verifies
    # scope (computed from the request path params), and returns the User.
    from app.deps import stream_user_factory
    assert callable(stream_user_factory(lambda **kw: f"job:{kw['job_id']}"))
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd api && .venv/bin/python -m pytest tests/test_stream_token.py::test_stream_user_dependency -v`
Expected: FAIL — `ImportError: cannot import name 'stream_user_factory'`.

- [ ] **Step 3: Implement in `api/app/deps.py`**

```python
from typing import Callable
from .jwt_auth import verify_stream_token  # add to existing imports

def stream_user_factory(scope_builder: Callable[..., str]):
    """Build a dependency for browser-GET-only endpoints (SSE / downloads).

    The endpoint can't carry a JSON body, so auth rides in `?st=<stream_token>`.
    `scope_builder(**path_params)` returns the scope the token MUST match —
    binding the token to exactly the resource in the URL. We still return the
    User so the endpoint's existing ownership checks (_owned_project etc.) run
    as a second gate (defense in depth).
    """
    async def _dep(
        request: Request,
        settings: Settings = Depends(get_settings),
        db: Session = Depends(db_session),
    ) -> User:
        token = request.query_params.get("st")
        if not token:
            raise _401("no_token", "missing stream token (?st=)")
        expected_scope = scope_builder(**request.path_params)
        try:
            claims = verify_stream_token(
                token, expected_scope=expected_scope, secret=settings.session_secret)
        except ValueError as e:
            code = "expired" if "expired" in str(e) else "bad_token"
            raise _401(code, str(e))
        user = db.get(User, claims.user_id)
        if user is None:
            raise _401("no_user", "user not found")
        return user
    return _dep
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd api && .venv/bin/python -m pytest tests/test_stream_token.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/app/deps.py api/tests/test_stream_token.py
git commit -m "feat(auth): add stream_user dependency for GET-only endpoints"
```

---

### Task 3: `POST /auth/stream-token` mint endpoint

**Files:**
- Modify: `api/app/routers/auth.py`
- Test: `api/tests/test_stream_token.py` (append)

- [ ] **Step 1: Write the failing test** (append)

```python
def test_mint_stream_token_endpoint(client, auth_token):
    # client + auth_token come from conftest (existing fixtures). Mint a token
    # scoped to a job, then verify it decodes with that scope.
    from app.jwt_auth import verify_stream_token
    from app.settings import get_settings
    r = client.post("/api/v1/auth/stream-token",
                    json={"access_token": auth_token, "scope": "job:abc"})
    assert r.status_code == 200
    st = r.json()["stream_token"]
    claims = verify_stream_token(st, expected_scope="job:abc",
                                 secret=get_settings().session_secret)
    assert claims.scope == "job:abc"

def test_mint_requires_valid_access_token(client):
    r = client.post("/api/v1/auth/stream-token",
                    json={"access_token": "garbage", "scope": "job:abc"})
    assert r.status_code == 401
```

> If `client` / `auth_token` fixtures differ in `api/tests/conftest.py`, match the existing naming used by e.g. `test_jobs.py`.

- [ ] **Step 2: Run to verify it fails**

Run: `cd api && .venv/bin/python -m pytest tests/test_stream_token.py -k mint -v`
Expected: FAIL — 404 (route not defined).

- [ ] **Step 3: Implement in `api/app/routers/auth.py`**

```python
from ..jwt_auth import AuthedBody, sign_stream_token  # extend existing import

class StreamTokenIn(AuthedBody):
    # `scope` names the single resource+action this token may unlock, e.g.
    # "job:<id>". The endpoint trusts the caller's scope string; the consuming
    # route re-checks it against its own path + runs ownership checks, so a
    # mismatched scope simply yields a token that won't open anything.
    scope: str = Field(..., min_length=1, max_length=200)

class StreamTokenOut(BaseModel):
    stream_token: str
    expires_at: int

@router.post("/stream-token", response_model=StreamTokenOut)
def mint_stream_token(body: StreamTokenIn,
                      user: User = Depends(current_user),
                      settings: Settings = Depends(get_settings)):
    """Mint a short-lived, resource-scoped token for a browser-GET endpoint
    (SSE / file download) that can't carry the JWT in a body."""
    tok, exp = sign_stream_token(str(user.id), scope=body.scope,
                                 secret=settings.session_secret)
    return StreamTokenOut(stream_token=tok, expires_at=exp)
```

> Confirm `current_user`, `Settings`, `get_settings`, `Field`, `BaseModel`, `User` are imported in `auth.py`; add any missing.

- [ ] **Step 4: Run to verify it passes**

Run: `cd api && .venv/bin/python -m pytest tests/test_stream_token.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/auth.py api/tests/test_stream_token.py
git commit -m "feat(auth): add POST /auth/stream-token mint endpoint"
```

---

## Phase 2 — Category B backend routes use `stream_user`

### Task 4: `jobs/{job_id}/events` → stream token

**Files:**
- Modify: `api/app/routers/jobs.py:60` (`stream_events`)
- Test: `api/tests/test_jobs.py`

- [ ] **Step 1: Update the test first** — find the test that hits `/jobs/{id}/events?access_token=` and change it to mint a stream token (`POST /auth/stream-token` scope `job:<id>`) then call `/jobs/{id}/events?st=<token>&since=0`. Assert 200 and that `?access_token=` no longer authenticates (now 401).

- [ ] **Step 2: Run to verify it fails**

Run: `cd api && .venv/bin/python -m pytest tests/test_jobs.py -v`
Expected: FAIL (route still uses `current_user`, rejects `?st=`).

- [ ] **Step 3: Implement** — swap the dependency (keep GET; SSE stays GET):

```python
from ..deps import stream_user_factory  # add import

@router.get("/{job_id}/events")
async def stream_events(
    job_id: uuid.UUID, since: int = 0,
    # GET-only (EventSource). Auth via short-lived ?st= token scoped to this
    # job, NOT the long-lived JWT — keeps the JWT out of URLs/logs.
    user: User = Depends(stream_user_factory(lambda job_id: f"job:{job_id}")),
    db: Session = Depends(db_session),
):
```

> `request.path_params` gives `job_id` as a string; the lambda receives it as such, which matches the scope minted client-side from the same string. Keep the existing body (ownership check stays).

- [ ] **Step 4: Run to verify it passes**

Run: `cd api && .venv/bin/python -m pytest tests/test_jobs.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/jobs.py api/tests/test_jobs.py
git commit -m "feat(jobs): authenticate SSE events with scoped stream token"
```

---

### Task 5: download routes → stream token

**Files:**
- Modify: `api/app/routers/papers.py:485` (`download_export`), `api/app/routers/exports.py:35` (`download_export`)
- Test: `api/tests/test_papers.py`, `api/tests/test_exports.py`

- [ ] **Step 1: Update both tests** to mint a scoped stream token and call with `?st=`. Scopes:
  - papers: `paper-export:<paper_id>:<fmt>`
  - exports: `project-export:<project_id>/<filename>`
  Also assert `?access_token=` now returns 401 on these routes.

- [ ] **Step 2: Run to verify they fail**

Run: `cd api && .venv/bin/python -m pytest tests/test_papers.py tests/test_exports.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement** — keep GET, swap dependency:

`papers.py`:
```python
from ..deps import stream_user_factory  # add import

@router.get("/{paper_id}/exports/{fmt}")
def download_export(
    paper_id: uuid.UUID, fmt: str,
    # GET (browser <a download>). Scoped stream token keeps the JWT out of the URL.
    user: User = Depends(stream_user_factory(
        lambda paper_id, fmt: f"paper-export:{paper_id}:{fmt}")),
    db: Session = Depends(db_session),
):
```

`exports.py`:
```python
from ..deps import stream_user_factory  # add import

@router.get("/projects/{project_id}/exports/{filename}")
def download_export(
    project_id: uuid.UUID, filename: str,
    user: User = Depends(stream_user_factory(
        lambda project_id, filename: f"project-export:{project_id}/{filename}")),
    db: Session = Depends(db_session),
):
```

- [ ] **Step 4: Run to verify they pass**

Run: `cd api && .venv/bin/python -m pytest tests/test_papers.py tests/test_exports.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/papers.py api/app/routers/exports.py api/tests/test_papers.py api/tests/test_exports.py
git commit -m "feat(exports): authenticate downloads with scoped stream token"
```

---

## Phase 3 — Category A backend routes GET → POST

**Transformation recipe (applies to every route in this phase):**
1. Change `@router.get("...")` → `@router.post("...")`. Keep path params in the path.
2. If the handler had `Query(...)`-style params (function args with defaults that aren't `Depends`), move them into a Pydantic body class that inherits `AuthedBody`, and add `body: <Name>Body` to the signature. If it had no such params, add `body: AuthedBody` so the token is validated (still required — `current_user` reads it from the body).
3. `user: User = Depends(current_user)` and `db` stay unchanged.
4. Read former query values from `body.<field>` inside the handler.
5. Update the matching test(s): `client.get("/x?foo=1&access_token=T")` → `client.post("/x", json={"foo": 1, "access_token": T})`.

> `AuthedBody` already requires `access_token`, so even no-param routes get a typed body. Pydantic v2 coerces JSON numbers/bools to the declared types.

The three distinct shapes — **(a)** no extra params, **(b)** path params only, **(c)** path + query params — are shown in full in Task 6. Subsequent tasks list each route with its concrete new body class + signature (the genuinely-varying content); apply the recipe identically.

---

### Task 6: chat.py reads → POST (reference task, full code)

**Files:**
- Modify: `api/app/routers/chat.py` (lines 152, 170, 178, 194, 311, 356, 367, 722)
- Test: `api/tests/test_chat_router.py`, `api/tests/test_chat_messages.py`, `api/tests/test_artifacts_endpoint.py`, `api/tests/test_thread_state_stream.py`

Routes and their conversions:

```python
# (a) no extra params — add `body: AuthedBody`
@router.post("/projects", response_model=list[ProjectOut])
def list_projects(body: AuthedBody,
                  user: User = Depends(current_user),
                  db: Session = Depends(db_session)):
    ...

# (b) path-only — add `body: AuthedBody`
@router.post("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: uuid.UUID, body: AuthedBody,
                user: User = Depends(current_user),
                db: Session = Depends(db_session)):
    ...

@router.post("/projects/{project_id}/artifacts")
def get_artifacts(project_id: uuid.UUID, body: AuthedBody,
                  user: User = Depends(current_user),
                  db: Session = Depends(db_session)) -> dict[str, str]:
    ...

@router.post("/projects/{project_id}/impact/{artifact}")
def get_impact(project_id: uuid.UUID, artifact: str, body: AuthedBody,
               user: User = Depends(current_user),
               db: Session = Depends(db_session)) -> dict[str, list[str]]:
    ...

# list_threads COLLIDES with create-thread POST /projects/{id}/threads
# (chat.py:319) -> rename the LIST to /threads/list
@router.post("/projects/{project_id}/threads/list", response_model=list[ThreadOut])
def list_threads(project_id: uuid.UUID, body: AuthedBody,
                 user: User = Depends(current_user),
                 db: Session = Depends(db_session)):
    ...

@router.post("/threads/{thread_id}", response_model=ThreadOut)
def get_thread(thread_id: uuid.UUID, body: AuthedBody,
               user: User = Depends(current_user),
               db: Session = Depends(db_session)):
    ...

@router.post("/threads/{thread_id}/state")
async def state_stream(thread_id: uuid.UUID, body: AuthedBody,
                       user: User = Depends(current_user),
                       db: Session = Depends(db_session)):
    ...

# (c) path + query. list_messages COLLIDES with send-message POST
# /threads/{id}/messages (chat.py:406) -> rename the LIST to /messages/list
class ListMessagesBody(AuthedBody):
    before_id: int | None = None
    limit: int = 50

@router.post("/threads/{thread_id}/messages/list")
def list_messages(thread_id: uuid.UUID, body: ListMessagesBody,
                  user: User = Depends(current_user),
                  db: Session = Depends(db_session)):
    before_id = body.before_id   # was the query param
    limit = body.limit
    ...
```

> **Confirmed collisions in chat.py (verified against the router):** `POST /projects` (create, chat.py:137), `POST /projects/{project_id}/threads` (create thread, chat.py:319), and `POST /threads/{thread_id}/messages` (send, chat.py:406) all already exist. So the three corresponding *reads* must move to distinct paths:
> - `GET /projects` (list) → `POST /projects/list`
> - `GET /projects/{project_id}/threads` (list) → `POST /projects/{project_id}/threads/list`
> - `GET /threads/{thread_id}/messages` (list) → `POST /threads/{thread_id}/messages/list`
>
> `get_project` (`POST /projects/{project_id}`), `get_thread` (`POST /threads/{thread_id}`), `get_artifacts`, `get_impact`, `state_stream` have NO POST collision and keep their natural paths. Frontend SWR-key updates for the renames: `"/projects"`→`"/projects/list"` (HomeDashboard.tsx:108, papers/page.tsx:46 — note Credit.tsx:26 uses `/papers`, unaffected); `/projects/${pid}/threads`→`/projects/${pid}/threads/list` (layout.tsx:35, page.tsx:12); `/threads/${threadId}/messages?...`→`/threads/${threadId}/messages/list?...` (useChat.ts:29). `/threads/${threadId}` (ChatPane.tsx:165) is unchanged.

- [ ] **Step 1:** Update the four chat test files: convert each `client.get(...)` for these routes to `client.post(path, json={...})`; for `list_messages` pass `before_id`/`limit` in the JSON body. For the `/projects` list, update path to `/projects/list`.
- [ ] **Step 2:** Run `cd api && .venv/bin/python -m pytest tests/test_chat_router.py tests/test_chat_messages.py tests/test_artifacts_endpoint.py tests/test_thread_state_stream.py -v` — expect FAIL.
- [ ] **Step 3:** Apply the conversions above in `chat.py` (confirm `AuthedBody` imported from `..jwt_auth`).
- [ ] **Step 4:** Re-run the same tests — expect PASS.
- [ ] **Step 5:** Commit `feat(chat): migrate read endpoints to POST (token in body)`.

---

### Task 7: papers.py reads → POST

Routes (all shape (b), path-only → `body: AuthedBody`), per the recipe:
- `GET ""` → `POST ""` `list_papers(body: AuthedBody, ...)`
- `GET /{paper_id}` → `POST /{paper_id}` `get_paper(paper_id, body: AuthedBody, ...)`
- `GET /{paper_id}/draft` → `POST /{paper_id}/draft`
- `GET /{paper_id}/citations` → `POST /{paper_id}/citations`
- `GET /{paper_id}/exports` → `POST /{paper_id}/exports`

> Do **not** touch `/{paper_id}/exports/{fmt}` (Task 5, stays GET). Watch the path overlap: `POST /{paper_id}/exports` (list) vs `GET /{paper_id}/exports/{fmt}` (download) — different methods/paths, no collision.

- [ ] **Step 1:** Update `api/tests/test_papers.py` (+ `test_papers_credit.py`, `test_outputs.py` if they hit these) — GET→POST with `json={"access_token": T}`.
- [ ] **Step 2:** `cd api && .venv/bin/python -m pytest tests/test_papers.py tests/test_papers_credit.py -v` → FAIL.
- [ ] **Step 3:** Apply recipe to the 5 routes.
- [ ] **Step 4:** Re-run → PASS.
- [ ] **Step 5:** Commit `feat(papers): migrate read endpoints to POST`.

---

### Task 8: runs.py reads → POST

```python
class EstimateRunBody(AuthedBody):
    topic: str = ""

@router.post("/projects/{project_id}/runs/estimate")
def estimate_run(project_id: uuid.UUID, body: EstimateRunBody, ...):
    topic = body.topic

class ListRunsBody(AuthedBody):
    latest: bool = False
    limit: int = 50

@router.post("/projects/{project_id}/runs")
def list_runs(project_id: uuid.UUID, body: ListRunsBody, ...):
    ...

@router.post("/runs/{run_id}")
def get_run(run_id: uuid.UUID, body: AuthedBody, ...):
    ...
```

> Collision check: `POST /projects/{project_id}/runs` (list) vs the existing run-creation `apiFetch("/projects/${projectId}/runs", POST)` in ChatPane.tsx:201 — **`POST /projects/{id}/runs` ALREADY EXISTS for creating a run.** Same collision pattern as `/projects`. **Decision:** convert the list to `POST /projects/{project_id}/runs/list`; update frontend (no SWR key currently for the list besides `/runs/{id}` and estimate — verify; AutoDraftDrawer uses `/runs/{runId}`). Confirm the create-run route path before finalizing.

- [ ] Steps 1–5 per recipe. Tests: `test_runs_router.py`, `test_runs_estimate.py`, `test_runs_latest.py`. Commit `feat(runs): migrate read endpoints to POST`.

---

### Task 9: uploads.py reads → POST

```python
@router.post("/projects/{project_id}/uploads", response_model=list[UploadListItem])
def list_uploads(project_id: uuid.UUID, body: AuthedBody, ...): ...

@router.post("/uploads/{upload_id}/text", response_class=PlainTextResponse)
def get_upload_text(upload_id: uuid.UUID, body: AuthedBody, ...): ...
```

> Collision check: the file-upload endpoint (`POST /projects/{project_id}/uploads`, multipart) in ChatPane.tsx:251 **already exists**. The list is the same path+method → collision. **Decision:** convert list to `POST /projects/{project_id}/uploads/list`; update the SWR key in `(chat)/.../layout.tsx:38` (`/projects/${pid}/uploads` → `/projects/${pid}/uploads/list`). The multipart upload POST stays as-is (Task 14 only moves its token into FormData).

- [ ] Steps 1–5. Tests: `test_uploads_router.py`. Commit `feat(uploads): migrate read endpoints to POST`.

---

### Task 10: credit.py reads → POST

```python
@router.post("/packages")
def packages():        # public — no auth param needed; no token leak today,
    ...                # but convert for POST-only uniformity (no body required)

@router.post("/orders")
def list_my_orders(body: AuthedBody, user=..., db=...): ...

@router.post("/transactions")
def list_my_transactions(body: AuthedBody, user=..., db=...): ...
```

> `/packages` has no `current_user` and no params; give it no body (it's public). swrFetcher will still POST with an empty/`{access_token}` body — harmless since FastAPI ignores an unexpected body when none is declared. Collision check: `/credit/checkout` is the existing POST; `/orders`,`/transactions`,`/packages` are distinct. No rename needed.

- [ ] Steps 1–5. Tests: `test_credit_routes.py`, `test_credit_ledger.py`, `test_pricing.py`. Commit `feat(credit): migrate read endpoints to POST`.

---

### Task 11: announcements.py + m5_editor.py reads → POST

```python
# announcements.py
@router.post("/me")
def announcements_for_me(body: AuthedBody, user=..., db=...): ...

# m5_editor.py
@router.post("/projects/{project_id}/m5/chapters")
def list_chapters(project_id: uuid.UUID, body: AuthedBody, ...): ...

@router.post("/projects/{project_id}/m5/references")
def list_references(project_id: uuid.UUID, body: AuthedBody, ...): ...
```

- [ ] Steps 1–5. Tests: `test_announcements_me.py`, `test_m5_editor_router.py`, `test_m5_editor_auth.py`. Commit `feat(announcements,m5): migrate read endpoints to POST`.

---

### Task 12: jobs.py `get_job` → POST

```python
@router.post("/{job_id}")
def get_job(job_id: uuid.UUID, body: AuthedBody, user=..., db=...): ...
```

> Leave `/{job_id}/events` as GET (Task 4). No collision (`/{job_id}` GET→POST; `/{job_id}/cancel` is already POST).

- [ ] Steps 1–5. Tests: `test_jobs.py`. Commit `feat(jobs): migrate get_job to POST`.

---

### Task 13: admin routers → POST

Admin routers use a router-level `Depends(require_admin)` (which depends on `current_user`), so the token must still be in the body. Add `body: AuthedBody`/body class to each handler.

```python
# admin_users.py
class ListUsersBody(AuthedBody):
    page: int = 1
    page_size: int = 20
    q: str | None = None
@router.post("")
def list_users(body: ListUsersBody, db=...): ...   # require_admin still applies
@router.post("/{user_id}")
def get_user(user_id: uuid.UUID, body: AuthedBody, db=...): ...

# admin_papers.py
class ListPapersBody(AuthedBody):
    page: int = 1
    page_size: int = 20
    status: str | None = None
    user_id: str | None = None
@router.post("")
def list_papers(body: ListPapersBody, db=...): ...

# admin_orders.py
class ListOrdersBody(AuthedBody):
    page: int = 1
    page_size: int = 20
    status: str | None = None
@router.post("")
def list_orders(body: ListOrdersBody, db=...): ...

# admin_jobs.py
class ListJobsBody(AuthedBody):
    page: int = 1
    page_size: int = 20
    status: str | None = None
@router.post("")
def list_jobs(body: ListJobsBody, db=...): ...

# admin_announcements.py
@router.post("")        # NOTE: list_all GET on "" — but a create POST "" may exist.
def list_all(body: AuthedBody, db=...): ...
```

> **Collision check (admin_announcements):** `AnnouncementsAdmin.tsx:38` does `apiFetch(KEY, {method:"POST"})` to create — so `POST /admin/announcements` (`""`) likely already exists for creation. If so, convert the list to `POST /admin/announcements/list` and update `KEY`-based `useSWR` to use `/admin/announcements/list` for the read while keeping create at `""`. Same for any other admin `""` that already has a create POST — verify each router file before converting and rename the *list* to `/list`.

- [ ] Steps 1–5 per router (one commit per router or one combined). Tests: `test_admin_users.py`, `test_admin_papers.py`, `test_admin_orders.py`, `test_admin_jobs.py`, `test_admin_announcements.py`, `test_require_admin.py`. Commit `feat(admin): migrate list/read endpoints to POST`.

- [ ] **After all of Phase 3:** run the full backend suite: `cd api && .venv/bin/python -m pytest -q`. Expected: all green (frontend not yet updated — that's Phase 4).

---

## Phase 4 — Frontend Category A (POST reads)

### Task 14: `swrFetcher`/`apiFetch` POST + query-fold; upload FormData

**Files:**
- Modify: `web/app/lib/api.js`, `web/app/components/chat/ChatPane.tsx`, `web/app/components/chat/hooks/useProjectState.ts`, `web/app/components/editor/CitePopover.tsx`
- Test: `web/app/lib/api.test.js` (create if absent), affected component tests

- [ ] **Step 1: Write/extend api.test.js**

```js
import { describe, it, expect, vi, beforeEach } from "vitest";
import { swrFetcher } from "./api";
import { tokenStore } from "./tokenStore";

describe("swrFetcher", () => {
  beforeEach(() => { tokenStore.set?.("TOK"); globalThis.fetch = vi.fn()
    .mockResolvedValue({ ok: true, json: async () => ({}) }); });

  it("POSTs reads with token in body and no token in URL", async () => {
    await swrFetcher("/projects/list");
    const [url, init] = fetch.mock.calls[0];
    expect(url).not.toContain("access_token");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toMatchObject({ access_token: "TOK" });
  });

  it("folds query string from the SWR key into the body", async () => {
    await swrFetcher("/admin/users?page=2&q=ann");
    const [url, init] = fetch.mock.calls[0];
    expect(url.endsWith("/admin/users")).toBe(true);
    expect(JSON.parse(init.body)).toMatchObject({ page: "2", q: "ann", access_token: "TOK" });
  });
});
```

- [ ] **Step 2:** `cd web && npm test -- app/lib/api.test.js` → FAIL.

- [ ] **Step 3: Implement in `web/app/lib/api.js`**

Change `swrFetcher` to POST, and teach `apiFetch` to fold a query string into the body for POSTs:

```js
// Reads now go out as POST (CLAUDE.md POST-only): the token rides in the body
// so it never lands in a URL or the server access log. The SWR key keeps its
// familiar `path?query` shape; we split the query off and fold it into the
// JSON body so call sites don't change.
export function swrFetcher(path) {
  return apiFetch(path, { method: "POST" });
}
```

In `apiFetch`, in the POST branch, before injecting the token, split any query string off `url` and merge its params into `body`:

```js
  } else {
    // POST family — fold the token (and any ?query from the path) into the body.
    const qIndex = url.indexOf("?");
    let qparams = {};
    if (qIndex >= 0) {
      qparams = Object.fromEntries(new URLSearchParams(url.slice(qIndex + 1)));
      url = url.slice(0, qIndex);
    }
    if (typeof body === "string") { try { body = JSON.parse(body); } catch { body = {}; } }
    else if (body == null) { body = {}; }
    body = { ...qparams, ...body, access_token: token };
  }
```

> Backend body classes use typed fields; Pydantic v2 coerces the string values from `URLSearchParams` (`"2"`→`int`, `"true"`→`bool`). Verify each migrated route's body type accepts string coercion (all do: int/bool/str/optional).

Fix the upload call in `ChatPane.tsx:244` — drop the query token, append it to FormData:

```js
    const token = tokenStore.get();
    // Multipart can't carry a JSON body; put the token in a form field instead
    // of the URL so it stays out of logs (deps.py _extract_token reads body JSON
    // OR — for multipart — we add an explicit access_token field the route reads).
    const base = process.env.NEXT_PUBLIC_API_BASE || "/api/v1";
    // ...inside map:
        const fd = new FormData();
        fd.append("file", f);
        if (token) fd.append("access_token", token);
        const res = await fetch(`${base}/projects/${projectId}/uploads`, { method: "POST", body: fd, ... });
```

> **Backend follow-up for multipart:** `_extract_token` parses JSON bodies; a multipart body is not JSON, so it won't find the token there. Add to the uploads *create* route an explicit `access_token: str = Form(...)` (or read `request.form()`), OR keep the upload route reading the token via the Authorization header. **Decision:** add `access_token: str = Form(...)` to the upload create handler and pass it to a manual `verify_access_token` (don't use `current_user` for the multipart route), since `_extract_token` can't see form fields. Add a backend test in `test_uploads_router.py` for the form-field token. (This is the one route where the token legitimately can't be JSON-body.)

Update `useProjectState.ts:13` to POST with the token in the body:

```ts
    const token = tokenStore.get();
    void stream.start(`/api/v1/threads/${threadId}/state`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ access_token: token }),
    });
```

Update `CitePopover.tsx:25` direct GET caller:

```ts
    apiFetch(`/projects/${projectId}/m5/references`, { method: "POST" })
```

And update the renamed read paths from Phase 3 collisions: SWR keys `"/projects"` → `"/projects/list"` (HomeDashboard.tsx:108, papers/page.tsx:46), `/projects/${pid}/uploads` → `/projects/${pid}/uploads/list` (layout.tsx:38), admin list keys → `/list` where renamed, and any runs list key.

- [ ] **Step 4:** `cd web && npm test` → PASS (update MSW handlers: any `http.get("/api/v1/...")` for migrated routes → `http.post(...)`; e.g. `useProjectState.test.tsx:12` `http.get(".../state")` → `http.post(...)`).

- [ ] **Step 5:** Commit `feat(web): POST reads with token in body; upload token via FormData`.

---

## Phase 5 — Frontend Category B (stream tokens) + final hardening

### Task 15: `openEventStream` + download links mint stream tokens

**Files:**
- Modify: `web/app/lib/api.js`, `web/app/components/chat/ContextPanel.tsx`, `web/app/components/chat/ChatHeader.tsx`, `web/app/components/agent-run.jsx`

- [ ] **Step 1:** Add helpers to `api.js` and make `openEventStream` async:

```js
/** Mint a short-lived token scoped to one resource for a browser-GET endpoint. */
export async function mintStreamToken(scope) {
  const { stream_token } = await apiFetch("/auth/stream-token", {
    method: "POST", body: { scope },
  });
  return stream_token;
}

// EventSource is GET-only and can't set a body/header, so it needs the token in
// the URL. We now use a short-lived, job-scoped stream token instead of the
// long-lived JWT — a leaked URL is useless after ~2 min and only for this job.
export async function openEventStream(jobId, { since = 0, onEvent, onDone, onError } = {}) {
  const st = await mintStreamToken(`job:${jobId}`);
  const url = `${BASE}/jobs/${jobId}/events?since=${since}&st=${encodeURIComponent(st)}`;
  const es = new EventSource(url);
  // ...rest unchanged...
  return () => es.close();
}
```

> `openEventStream` is now async. Update `agent-run.jsx` (and any other caller) to `await openEventStream(...)` inside the effect and store the returned closer (e.g. via a ref, since the effect cleanup can't be async directly — capture the promise and close in cleanup).

- [ ] **Step 2:** Convert the download anchors to mint-on-click. In `ContextPanel.tsx` and `ChatHeader.tsx`, replace the static `href` (with `?access_token=`) by an `onClick` that mints a scoped token then triggers the download:

```tsx
// Download needs the token in the URL (browser <a download>), so mint a
// short-lived token scoped to exactly this artifact instead of leaking the JWT.
const onDownload = async (e: React.MouseEvent) => {
  e.preventDefault();
  // Derive scope from the download_url path. exports route:
  //   /projects/{projectId}/exports/{filename} -> scope project-export:{projectId}/{filename}
  const m = url.match(/\/projects\/([^/]+)\/exports\/([^/?]+)/);
  if (!m) return;
  const st = await mintStreamToken(`project-export:${m[1]}/${m[2]}`);
  window.location.href = `${url}?st=${encodeURIComponent(st)}`;
};
// <a href={url} download onClick={onDownload}> ... </a>
```

> If a download anchor instead targets the papers route `/papers/{id}/exports/{fmt}`, use scope `paper-export:{id}:{fmt}`. Verify which route each `download_url` points to (m5 export artifacts → exports route).

- [ ] **Step 3:** Update affected component tests/MSW: mock `POST /api/v1/auth/stream-token` returning `{stream_token:"st",expires_at:...}`; assert the EventSource/download URL contains `st=` and not `access_token=`.

- [ ] **Step 4:** `cd web && npm test` → PASS.

- [ ] **Step 5:** Commit `feat(web): mint scoped stream tokens for SSE + downloads`.

---

### Task 16: Remove the `?access_token=` JWT query fallback

**Files:**
- Modify: `api/app/deps.py:_extract_token`
- Test: `api/tests/test_auth_tokens.py` (or wherever `_extract_token`/query-auth is asserted)

- [ ] **Step 1:** Update the test that asserts query-param auth works — invert it: a JWT in `?access_token=` must now yield 401 (`no_token`) on a normal POST route; body and Bearer still work.

- [ ] **Step 2:** `cd api && .venv/bin/python -m pytest tests/test_auth_tokens.py -v` → FAIL.

- [ ] **Step 3:** Delete the query block from `_extract_token` (keep body + Bearer):

```python
    # NOTE: the legacy `?access_token=` query fallback was removed once all
    # reads moved to POST (token in body) and the GET-only download/SSE routes
    # switched to scoped stream tokens (?st=). The long-lived JWT must never
    # appear in a URL/log again. Body wins; Bearer remains for tooling.
```

Remove lines reading `request.query_params.get("access_token")`. Update the no-token 401 message to drop "query".

- [ ] **Step 4:** `cd api && .venv/bin/python -m pytest -q` → all green.

- [ ] **Step 5:** Commit `feat(auth): drop access_token query fallback — JWT never in URL`.

---

## Phase 6 — Verification

### Task 17: Full suite + manual smoke

- [ ] **Step 1:** `cd api && .venv/bin/python -m pytest -q` — all pass.
- [ ] **Step 2:** `cd web && npm test` — all pass.
- [ ] **Step 3:** With `dev.sh` running, exercise in the browser (do NOT run `next build` while `next dev` is up — memory rule): load a project chat (threads/messages/state stream), upload a file, open the auto-draft run (EventSource), download a docx export. Tail the API log and confirm **no** `access_token=` appears in any GET line; only `?st=` on `/events` and the download routes, and those JWT-free.
- [ ] **Step 4:** `grep -rn "access_token=" web/app | grep -v node_modules` returns nothing (all moved to body/FormData/`?st=`).
- [ ] **Step 5:** Commit any test fixups; open PR.

---

## Self-Review notes

- **Spec coverage:** every GET in `api/app/routers/` is accounted for — Category A migrated to POST (Tasks 6–13), Category B hardened with stream tokens (Tasks 4–5, 15), query fallback removed (Task 16). The `GET /api/v1/health` exception is intentionally left untouched.
- **Path collisions (must verify during execution):** `POST /projects`, `POST /projects/{id}/runs`, `POST /projects/{id}/uploads`, and admin `POST ""` likely already exist as *create* endpoints. Where they do, the *list/read* migration uses a `/list` suffix and the frontend SWR key is updated to match. Each task flags this; confirm against the actual router file before converting.
- **Multipart token:** the upload create route is the one place the token can't be JSON; it uses a `Form(...)` field + manual verify (Task 14). 
- **EventSource vs single-use:** documented — stream tokens are short-TTL + scoped, not strictly one-time, because EventSource reopens the same URL on reconnect.

## Deferred / out of scope
- Strict one-time stream tokens (nonce/jti store) — conflicts with EventSource reconnect; revisit if a one-shot download path is isolated from SSE.
- A refresh-token flow for the 7-day JWT (already noted as a separate follow-up in `jwt_auth.py`).

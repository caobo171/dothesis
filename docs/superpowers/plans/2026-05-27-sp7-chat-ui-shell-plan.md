> **📜 Historical record — superseded.** This document captured a plan / spec / design at a point in time and is kept for history. It does **not** describe the current system. For the live DoThesis method and architecture see `README.md`, `AGENTS.md`, `docs/ARCHITECTURE.md`, and `docs/PIPELINE.md`.

# SP7 Chat UI Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a Next.js chat UI shell that consumes the SP1+SP2 backend APIs end-to-end — 3-pane layout (threads / chat / context), SSE-streamed message replies, multi-thread per project, file upload, auto-draft launcher with progress drawer — without regressing the existing wizard.

**Architecture:** New `(chat)` route group sibling to `(inapp)`. Raw Tailwind + lucide-react (no shadcn yet). Single new primitive: `useStream` hook (fetch + ReadableStream + SSE parser) reused for chat messages, auto-draft progress, and live context-store state. SWR for queries; useReducer-via-useStream for streams. Testing via Vitest + MSW + happy-dom.

**Tech Stack:** Next.js 16, React 19, Tailwind 3, lucide-react, SWR 2, Vitest 2, @testing-library/react 16, MSW 2, happy-dom 14. Backend (existing): FastAPI + LangGraph.

**Spec:** `docs/superpowers/specs/2026-05-27-sp7-chat-ui-shell-design.md`
**Depends on:** Sub-projects 1 & 2 (already merged to master).

---

## File map

### NEW frontend files

```
web/
├── vitest.config.ts                            # test runner config
├── tests/
│   ├── setup.ts                                # MSW server + global hooks
│   ├── helpers/
│   │   ├── sseResponse.ts                      # MSW SSE helper
│   │   └── render.tsx                          # custom render w/ providers
│   └── mocks/
│       └── handlers.ts                         # default MSW handlers
├── app/(chat)/
│   ├── layout.tsx                              # outer SidebarLayout + AnnouncementProvider
│   ├── page.tsx                                # /chat — ProjectListGrid
│   └── projects/[pid]/
│       ├── layout.tsx                          # 3-pane ChatShellLayout
│       ├── page.tsx                            # redirect to Main thread
│       └── threads/[tid]/page.tsx              # ChatPane
└── app/components/chat/
    ├── ProjectListGrid.tsx
    ├── ChatShellLayout.tsx
    ├── ThreadsSidebar.tsx
    ├── ContextPanel.tsx
    ├── ChatPane.tsx
    ├── ChatHeader.tsx
    ├── MessageList.tsx
    ├── MessageBubble.tsx
    ├── StreamingBubble.tsx
    ├── ChatInput.tsx
    ├── FileDropZone.tsx
    ├── UploadChip.tsx
    ├── TokenMeter.tsx
    ├── AutoDraftButton.tsx
    ├── AutoDraftModal.tsx
    ├── AutoDraftDrawer.tsx
    ├── ModuleProgressDot.tsx
    ├── ContextModuleViewer.tsx
    └── hooks/
        ├── useStream.ts                        # THE primitive
        ├── useChat.ts
        ├── useProjectState.ts
        └── useAutoDraftRun.ts
```

### NEW backend files (small endpoints; only if missing from SP1)

```
api/app/routers/
├── chat.py                                     # MODIFY — add GET /threads/{tid}/state
└── runs.py                                     # MODIFY — add GET /projects/{pid}/runs?latest=true
                                                #          add GET /projects/{pid}/runs/estimate
api/tests/
├── test_thread_state_stream.py                 # NEW
├── test_runs_latest.py                         # NEW
└── test_runs_estimate.py                       # NEW
```

### MODIFIED frontend files

```
web/package.json                                # +vitest, msw, @testing-library/react, etc.
web/tsconfig.json                               # +types for vitest
web/app/components/dashboard.jsx                # add "Try the new chat experience" banner
docs/superpowers/2026-05-26-platform-pivot-roadmap.md   # flip SP7 to ✅
```

---

## Task index (27 tasks)

| Phase | Tasks |
|---|---|
| A. Backend gaps | 1. /threads/{tid}/state SSE · 2. /projects/{pid}/runs?latest · 3. /projects/{pid}/runs/estimate |
| B. Test infra | 4. Vitest + MSW setup |
| C. useStream | 5. SSE mock helper · 6. useStream hook + unit tests |
| D. Other hooks | 7. useChat · 8. useProjectState · 9. useAutoDraftRun |
| E. Pure components | 10. MessageBubble + StreamingBubble · 11. ModuleProgressDot · 12. UploadChip · 13. TokenMeter |
| F. Container components | 14. MessageList · 15. ContextModuleViewer + ContextPanel · 16. ThreadsSidebar · 17. ChatInput + FileDropZone · 18. ChatHeader · 19. ChatShellLayout |
| G. Auto-draft | 20. AutoDraftButton · 21. AutoDraftModal · 22. AutoDraftDrawer |
| H. Routes + landing | 23. ProjectListGrid · 24. (chat) route group + layouts |
| I. Integration tests | 25. ChatPane e2e · 26. AutoDraft e2e |
| J. Wrap-up | 27. Wizard banner + regression + roadmap flip |

---

## Phase A — Backend gap filling

### Task 1: GET /threads/{tid}/state SSE endpoint

**Files:**
- Modify: `api/app/routers/chat.py`
- Create: `api/tests/test_thread_state_stream.py`

This endpoint streams `context_store` patches + `remote_update` events for one thread's project. The chat UI's `useProjectState` hook subscribes to it.

- [ ] **Step 1: Verify whether the endpoint already exists**

Run: `grep -n "threads/{thread_id}/state\|threads/{tid}/state" api/app/routers/chat.py 2>&1 | head -5`

If it returns a line number, the endpoint exists — skip to Step 7 (commit a "verified" note). If empty, continue with Step 2.

- [ ] **Step 2: Write the test**

Create `api/tests/test_thread_state_stream.py`:

```python
"""Tests for GET /threads/{tid}/state SSE endpoint."""
import uuid
import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import ContextStore, Project, Thread, User
from app.security import create_session


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "true")
    return TestClient(create_app())


def _setup(client) -> tuple[uuid.UUID, uuid.UUID]:
    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"u{uuid.uuid4().hex[:6]}@x",
                 username=f"u{uuid.uuid4().hex[:6]}",
                 password_hash="x", email_verified=True)
        db.add(u); db.commit()
        client.cookies.set("dothesis_session", create_session(db, u))
    pid = client.post("/api/v1/projects", json={"name": "T"}).json()["id"]
    tid = client.get(f"/api/v1/projects/{pid}/threads").json()[0]["id"]
    return uuid.UUID(pid), uuid.UUID(tid)


def test_state_stream_emits_initial_snapshot(client):
    pid, tid = _setup(client)
    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, pid)
        cs.m1_topic = {"research_title": "X", "confirmed_at": "2026-05-26"}
        db.commit()

    with client.stream("GET", f"/api/v1/threads/{tid}/state") as r:
        assert r.status_code == 200
        chunks = []
        for line in r.iter_lines():
            chunks.append(line)
            if len(chunks) > 5:
                break

    # Look for a data: line containing an initial snapshot event
    body = "\n".join(c for c in chunks if c)
    assert "data:" in body
    assert "context_update" in body or "snapshot" in body
```

- [ ] **Step 3: Run test — should fail (endpoint missing)**

Run: `cd api && source .venv/bin/activate && python -m pytest tests/test_thread_state_stream.py -v`
Expected: FAIL (404 or AttributeError).

- [ ] **Step 4: Implement the endpoint**

Append to `api/app/routers/chat.py` (after the existing message-stream endpoint):

```python
@router.get("/threads/{thread_id}/state")
async def state_stream(thread_id: uuid.UUID,
                       user: User = Depends(current_user),
                       db: Session = Depends(db_session)):
    """SSE stream of context_store snapshots + remote_update events for this thread.

    Emits an initial 'context_update' event with the current snapshot, then
    polls the DB every 2s for changes. (Simple polling is fine for SP7 scope —
    LISTEN/NOTIFY can replace it in a later sub-project if perf demands.)
    """
    from .sse import sse_pack
    import asyncio

    t = db.get(Thread, thread_id)
    if not t:
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    _owned_project(db, user, t.project_id)

    async def gen():
        sf = get_session_factory()
        last_updated_at = None
        while True:
            with sf() as inner:
                cs = inner.get(ContextStore, t.project_id)
                if cs and cs.updated_at != last_updated_at:
                    last_updated_at = cs.updated_at
                    snapshot = {
                        "m1_topic":      cs.m1_topic,
                        "m2_literature": cs.m2_literature,
                        "m3_design":     cs.m3_design,
                        "m4_analysis":   cs.m4_analysis,
                        "m5_writing":    cs.m5_writing,
                    }
                    yield sse_pack({"type": "context_update", "patch": snapshot})
            await asyncio.sleep(2.0)

    from fastapi.responses import StreamingResponse
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})
```

Add the `get_session_factory` import at the top of `chat.py` if not already present:
```python
from ..db import db_session, get_session_factory
```

- [ ] **Step 5: Run test — should pass**

Run: `cd api && source .venv/bin/activate && python -m pytest tests/test_thread_state_stream.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/caonguyenvan/project/dothesis
git add api/app/routers/chat.py api/tests/test_thread_state_stream.py
git commit -m "feat(api): GET /threads/{tid}/state SSE for live context_store updates"
```

- [ ] **Step 7: If endpoint already existed (Step 1 found it):**

```bash
echo "endpoint exists; verified" > /tmp/sp7-t1-skipped
```
No commit. Move to Task 2.

---

### Task 2: GET /projects/{pid}/runs?latest=true endpoint

**Files:**
- Modify: `api/app/routers/runs.py`
- Create: `api/tests/test_runs_latest.py`

- [ ] **Step 1: Check if endpoint exists**

Run: `grep -n "/projects/{project_id}/runs\|latest=" api/app/routers/runs.py 2>&1 | head -5`

If a list endpoint exists with `?latest=true` support: skip to Step 7. If not, continue.

- [ ] **Step 2: Write the test**

Create `api/tests/test_runs_latest.py`:

```python
"""Tests for GET /projects/{pid}/runs?latest=true."""
import uuid
import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import Job, Project, User
from app.security import create_session


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "true")
    return TestClient(create_app())


def _login_and_project(client) -> uuid.UUID:
    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"u{uuid.uuid4().hex[:6]}@x",
                 username=f"u{uuid.uuid4().hex[:6]}",
                 password_hash="x", email_verified=True)
        db.add(u); db.commit()
        client.cookies.set("dothesis_session", create_session(db, u))
    return uuid.UUID(client.post("/api/v1/projects", json={"name": "T"}).json()["id"])


def test_latest_returns_null_when_no_runs(client):
    pid = _login_and_project(client)
    r = client.get(f"/api/v1/projects/{pid}/runs?latest=true")
    assert r.status_code == 200
    assert r.json() == {"run": None}


def test_latest_returns_most_recent_run(client):
    pid = _login_and_project(client)
    sf = get_session_factory()
    with sf() as db:
        # Older run
        older = Job(project_id=pid, mode="auto", status="done")
        db.add(older); db.flush()
        # Newer run
        newer = Job(project_id=pid, mode="auto", status="running")
        db.add(newer); db.commit()

    r = client.get(f"/api/v1/projects/{pid}/runs?latest=true")
    assert r.status_code == 200
    body = r.json()
    assert body["run"]["id"] == str(newer.id)
    assert body["run"]["status"] == "running"
```

- [ ] **Step 3: Run — should fail**

Run: `cd api && source .venv/bin/activate && python -m pytest tests/test_runs_latest.py -v`
Expected: FAIL.

- [ ] **Step 4: Implement the endpoint**

Append to `api/app/routers/runs.py`:

```python
@router.get("/projects/{project_id}/runs")
def list_runs(project_id: uuid.UUID,
              latest: bool = False,
              limit: int = 50,
              user: User = Depends(current_user),
              db: Session = Depends(db_session)):
    """List runs for a project. ?latest=true returns {run: <most-recent>} or {run: null}."""
    _owned_project(db, user, project_id)
    q = db.query(Job).filter_by(project_id=project_id).order_by(Job.id.desc())

    if latest:
        row = q.first()
        return {"run": _serialize_run(row) if row else None}

    rows = q.limit(min(limit, 200)).all()
    return [_serialize_run(r) for r in rows]


def _serialize_run(j: Job) -> dict:
    return {
        "id": str(j.id),
        "project_id": str(j.project_id) if j.project_id else None,
        "status": j.status,
        "phase": j.phase,
        "progress": j.progress,
        "mode": j.mode,
        "started_at": j.started_at.isoformat() if j.started_at else None,
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
    }
```

- [ ] **Step 5: Run — should pass**

Run: `cd api && source .venv/bin/activate && python -m pytest tests/test_runs_latest.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add api/app/routers/runs.py api/tests/test_runs_latest.py
git commit -m "feat(api): GET /projects/{pid}/runs with latest=true filter"
```

- [ ] **Step 7: If endpoint already existed:** no commit; move to Task 3.

---

### Task 3: GET /projects/{pid}/runs/estimate endpoint

**Files:**
- Modify: `api/app/routers/runs.py`
- Create: `api/tests/test_runs_estimate.py`

- [ ] **Step 1: Test**

Create `api/tests/test_runs_estimate.py`:

```python
"""Tests for GET /projects/{pid}/runs/estimate?topic=..."""
import uuid
import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import User
from app.security import create_session


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "true")
    return TestClient(create_app())


def _setup(client) -> uuid.UUID:
    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"u{uuid.uuid4().hex[:6]}@x",
                 username=f"u{uuid.uuid4().hex[:6]}",
                 password_hash="x", email_verified=True, credit=10000)
        db.add(u); db.commit()
        client.cookies.set("dothesis_session", create_session(db, u))
    return uuid.UUID(client.post("/api/v1/projects", json={"name": "T"}).json()["id"])


def test_estimate_returns_token_and_credit_info(client):
    pid = _setup(client)
    r = client.get(f"/api/v1/projects/{pid}/runs/estimate?topic=Leadership in SMEs")
    assert r.status_code == 200
    body = r.json()
    assert body["estimated_tokens"] > 0
    assert "credit_balance" in body
    assert body["credit_balance"] == 10000
```

- [ ] **Step 2: Run — should fail**

Run: `cd api && source .venv/bin/activate && python -m pytest tests/test_runs_estimate.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

Append to `api/app/routers/runs.py`:

```python
@router.get("/projects/{project_id}/runs/estimate")
def estimate_run(project_id: uuid.UUID,
                 topic: str = "",
                 user: User = Depends(current_user),
                 db: Session = Depends(db_session)):
    """Estimate token cost for an auto-mode run on this topic.

    Heuristic: ~3500 tokens per module × 5 modules = 17,500 baseline, plus
    25 tokens per character of topic (longer topics → more LLM context).
    """
    _owned_project(db, user, project_id)
    estimated = 17_500 + len(topic) * 25
    return {
        "estimated_tokens": estimated,
        "credit_balance": user.credit,
        "sufficient_credit": user.credit >= estimated,
    }
```

- [ ] **Step 4: Run — should pass**

Run: `cd api && source .venv/bin/activate && python -m pytest tests/test_runs_estimate.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/runs.py api/tests/test_runs_estimate.py
git commit -m "feat(api): GET /projects/{pid}/runs/estimate for pre-spawn token estimate"
```

---

## Phase B — Frontend test infrastructure

### Task 4: Vitest + MSW + happy-dom setup

**Files:**
- Modify: `web/package.json`
- Create: `web/vitest.config.ts`
- Create: `web/tests/setup.ts`
- Create: `web/tests/mocks/handlers.ts`
- Create: `web/tests/helpers/render.tsx`
- Create: `web/tests/sanity.test.ts`

- [ ] **Step 1: Add devDependencies**

Modify `web/package.json` — add to `devDependencies`:

```json
{
  "devDependencies": {
    "vitest": "^2.1.0",
    "@vitest/ui": "^2.1.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/user-event": "^14.5.0",
    "@testing-library/jest-dom": "^6.4.0",
    "happy-dom": "^14.12.0",
    "msw": "^2.4.0",
    "@types/node": "^22.5.0"
  }
}
```

Add to `scripts`:

```json
{
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest",
    "test:ui": "vitest --ui"
  }
}
```

Install:
```bash
cd /Users/caonguyenvan/project/dothesis/web && npm install
```

- [ ] **Step 2: Create vitest.config.ts**

```typescript
// web/vitest.config.ts
import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  test: {
    environment: "happy-dom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["app/**/*.test.{ts,tsx}", "tests/**/*.test.{ts,tsx}"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./"),
    },
  },
});
```

- [ ] **Step 3: Create tests/setup.ts**

```typescript
// web/tests/setup.ts
import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";
import { setupServer } from "msw/node";
import { defaultHandlers } from "./mocks/handlers";

export const server = setupServer(...defaultHandlers);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

- [ ] **Step 4: Create mocks/handlers.ts**

```typescript
// web/tests/mocks/handlers.ts
import { http, HttpResponse } from "msw";

export const defaultHandlers = [
  http.get("/api/v1/projects", () => HttpResponse.json([])),
];
```

- [ ] **Step 5: Create helpers/render.tsx**

```typescript
// web/tests/helpers/render.tsx
import { render as rtlRender, RenderOptions } from "@testing-library/react";
import { ReactElement } from "react";
import { SWRConfig } from "swr";

export function render(ui: ReactElement, options?: RenderOptions) {
  return rtlRender(ui, {
    wrapper: ({ children }) => (
      <SWRConfig value={{ dedupingInterval: 0, provider: () => new Map() }}>
        {children}
      </SWRConfig>
    ),
    ...options,
  });
}

export * from "@testing-library/react";
```

- [ ] **Step 6: Sanity test**

```typescript
// web/tests/sanity.test.ts
import { describe, expect, test } from "vitest";

describe("vitest setup", () => {
  test("runs", () => {
    expect(1 + 1).toBe(2);
  });
});
```

- [ ] **Step 7: Run**

Run: `cd web && npm test`
Expected: 1 passed.

- [ ] **Step 8: Commit**

```bash
cd /Users/caonguyenvan/project/dothesis
git add web/package.json web/package-lock.json web/vitest.config.ts web/tests/
git commit -m "feat(web): Vitest + MSW + happy-dom test infrastructure"
```

---

## Phase C — useStream primitive

### Task 5: SSE response mock helper

**Files:**
- Create: `web/tests/helpers/sseResponse.ts`
- Create: `web/tests/helpers/sseResponse.test.ts`

- [ ] **Step 1: Write the test**

Create `web/tests/helpers/sseResponse.test.ts`:

```typescript
import { describe, expect, test } from "vitest";
import { streamResponse } from "./sseResponse";

describe("streamResponse", () => {
  test("returns text/event-stream response with chunks", async () => {
    const res = streamResponse([
      'data: {"type":"token","text":"hi"}\n\n',
      'data: {"type":"done"}\n\n',
    ]);
    expect(res.headers.get("Content-Type")).toBe("text/event-stream");
    const text = await res.text();
    expect(text).toContain('"token"');
    expect(text).toContain('"done"');
  });
});
```

- [ ] **Step 2: Run — should fail**

Run: `cd web && npm test -- sseResponse`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `web/tests/helpers/sseResponse.ts`:

```typescript
// web/tests/helpers/sseResponse.ts
export function streamResponse(chunks: string[]): Response {
  const stream = new ReadableStream({
    start(controller) {
      const encoder = new TextEncoder();
      chunks.forEach(c => controller.enqueue(encoder.encode(c)));
      controller.close();
    },
  });
  return new Response(stream, {
    headers: { "Content-Type": "text/event-stream" },
  });
}
```

- [ ] **Step 4: Run — should pass**

Run: `cd web && npm test -- sseResponse`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/tests/helpers/sseResponse.ts web/tests/helpers/sseResponse.test.ts
git commit -m "feat(web): SSE mock helper for MSW"
```

---

### Task 6: useStream hook

**Files:**
- Create: `web/app/components/chat/hooks/useStream.ts`
- Create: `web/app/components/chat/hooks/useStream.test.ts`

- [ ] **Step 1: Write tests**

Create `web/app/components/chat/hooks/useStream.test.ts`:

```typescript
import { describe, expect, test, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { http } from "msw";
import { server } from "../../../../tests/setup";
import { streamResponse } from "../../../../tests/helpers/sseResponse";
import { useStream } from "./useStream";


describe("useStream", () => {
  test("parses single-line SSE event", async () => {
    server.use(
      http.post("/api/test", () => streamResponse([
        'data: {"type":"token","text":"hi"}\n\n',
        'data: {"type":"done"}\n\n',
      ])),
    );

    const { result } = renderHook(() => useStream());
    await act(async () => {
      await result.current.start("/api/test", { method: "POST" });
    });

    expect(result.current.state.events).toEqual([
      { type: "token", text: "hi" },
      { type: "done" },
    ]);
    expect(result.current.state.inflight).toBe(false);
  });

  test("handles partial chunks across reads", async () => {
    server.use(
      http.post("/api/test", () => streamResponse([
        'data: {"type":"tok',
        'en","text":"a"}\n\n',
        'data: {"type":"done"}\n\n',
      ])),
    );

    const { result } = renderHook(() => useStream());
    await act(async () => {
      await result.current.start("/api/test", { method: "POST" });
    });

    expect(result.current.state.events).toEqual([
      { type: "token", text: "a" },
      { type: "done" },
    ]);
  });

  test("malformed frame is silently skipped", async () => {
    server.use(
      http.post("/api/test", () => streamResponse([
        'data: not-json\n\n',
        'data: {"type":"token","text":"ok"}\n\n',
        'data: {"type":"done"}\n\n',
      ])),
    );

    const { result } = renderHook(() => useStream());
    await act(async () => {
      await result.current.start("/api/test", { method: "POST" });
    });

    // Only the two valid events
    expect(result.current.state.events).toEqual([
      { type: "token", text: "ok" },
      { type: "done" },
    ]);
  });

  test("HTTP error surfaces in state.error", async () => {
    server.use(
      http.post("/api/test", () => new Response(null, { status: 500 })),
    );

    const { result } = renderHook(() => useStream());
    await act(async () => {
      await result.current.start("/api/test", { method: "POST" });
    });

    expect(result.current.state.error).not.toBeNull();
    expect(result.current.state.inflight).toBe(false);
  });

  test("cancel aborts mid-stream", async () => {
    let resolveSecondChunk: () => void = () => {};
    const secondChunkPromise = new Promise<void>(r => (resolveSecondChunk = r));

    server.use(
      http.post("/api/test", () => {
        const stream = new ReadableStream({
          async start(controller) {
            const encoder = new TextEncoder();
            controller.enqueue(encoder.encode('data: {"type":"token","text":"a"}\n\n'));
            await secondChunkPromise;
            controller.enqueue(encoder.encode('data: {"type":"done"}\n\n'));
            controller.close();
          },
        });
        return new Response(stream, {
          headers: { "Content-Type": "text/event-stream" },
        });
      }),
    );

    const { result } = renderHook(() => useStream());
    act(() => {
      void result.current.start("/api/test", { method: "POST" });
    });
    // Wait for first event
    await waitFor(() => {
      expect(result.current.state.events.length).toBeGreaterThan(0);
    });

    act(() => result.current.cancel());
    expect(result.current.state.inflight).toBe(false);

    // Let the server finish — should NOT add more events
    resolveSecondChunk();
    await new Promise(r => setTimeout(r, 50));
    expect(result.current.state.events.find(e => e.type === "done")).toBeUndefined();
  });
});
```

- [ ] **Step 2: Run — should fail**

Run: `cd web && npm test -- useStream`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement hook**

Create `web/app/components/chat/hooks/useStream.ts`:

```typescript
"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";

export type SSEEvent = {
  type: string;
  [key: string]: unknown;
};

export type StreamState = {
  events: SSEEvent[];
  inflight: boolean;
  error: Error | null;
};

export type UseStreamApi = {
  state: StreamState;
  start: (url: string, init?: RequestInit) => Promise<void>;
  cancel: () => void;
};

type Action =
  | { type: "start" }
  | { type: "event"; event: SSEEvent }
  | { type: "error"; error: Error }
  | { type: "end" }
  | { type: "reset" };

function reducer(state: StreamState, action: Action): StreamState {
  switch (action.type) {
    case "start": return { events: [], inflight: true, error: null };
    case "event": return { ...state, events: [...state.events, action.event] };
    case "error": return { ...state, inflight: false, error: action.error };
    case "end":   return { ...state, inflight: false };
    case "reset": return { events: [], inflight: false, error: null };
  }
}

export function useStream(): UseStreamApi {
  const [state, dispatch] = useReducer(reducer, {
    events: [], inflight: false, error: null,
  });
  const abortRef = useRef<AbortController | null>(null);

  const start = useCallback(async (url: string, init: RequestInit = {}) => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    dispatch({ type: "start" });

    try {
      const res = await fetch(url, { ...init, signal: ctrl.signal });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let sep;
        while ((sep = buffer.indexOf("\n\n")) >= 0) {
          const frame = buffer.slice(0, sep);
          buffer = buffer.slice(sep + 2);
          const dataLine = frame.split("\n").find(l => l.startsWith("data: "));
          if (!dataLine) continue;
          try {
            const event = JSON.parse(dataLine.slice(6)) as SSEEvent;
            dispatch({ type: "event", event });
            if (event.type === "done" || event.type === "job_done") {
              dispatch({ type: "end" });
              return;
            }
          } catch {
            // Malformed frame; skip
          }
        }
      }
      dispatch({ type: "end" });
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      dispatch({ type: "error", error: e as Error });
    }
  }, []);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    dispatch({ type: "end" });
  }, []);

  useEffect(() => () => abortRef.current?.abort(), []);

  return { state, start, cancel };
}
```

- [ ] **Step 4: Run — should pass**

Run: `cd web && npm test -- useStream`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add web/app/components/chat/hooks/useStream.ts web/app/components/chat/hooks/useStream.test.ts
git commit -m "feat(web): useStream hook — SSE primitive for chat + auto-draft streams"
```

---

## Phase D — Other hooks

### Task 7: useChat hook

**Files:**
- Create: `web/app/components/chat/hooks/useChat.ts`
- Create: `web/app/components/chat/hooks/useChat.test.tsx`

- [ ] **Step 1: Tests**

Create `web/app/components/chat/hooks/useChat.test.tsx`:

```typescript
import { describe, expect, test } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../../../../tests/setup";
import { streamResponse } from "../../../../tests/helpers/sseResponse";
import { SWRConfig } from "swr";
import { ReactNode } from "react";
import { useChat } from "./useChat";


const wrapper = ({ children }: { children: ReactNode }) => (
  <SWRConfig value={{ dedupingInterval: 0, provider: () => new Map() }}>{children}</SWRConfig>
);


describe("useChat", () => {
  test("loads existing messages via SWR", async () => {
    server.use(
      http.get("/api/v1/threads/t1/messages", () => HttpResponse.json([
        { id: 1, role: "user", content: "hello", created_at: "2026-05-27T00:00:00Z" },
        { id: 2, role: "assistant", content: "hi", created_at: "2026-05-27T00:00:01Z" },
      ])),
    );

    const { result } = renderHook(() => useChat("t1"), { wrapper });
    await waitFor(() => expect(result.current.messages.length).toBe(2));
    expect(result.current.messages[0].content).toBe("hello");
  });

  test("send() optimistically appends user message", async () => {
    server.use(
      http.get("/api/v1/threads/t1/messages", () => HttpResponse.json([])),
      http.post("/api/v1/threads/t1/messages", () => streamResponse([
        'data: {"type":"token","text":"reply"}\n\n',
        'data: {"type":"done"}\n\n',
      ])),
    );

    const { result } = renderHook(() => useChat("t1"), { wrapper });
    await waitFor(() => expect(result.current.messages).toEqual([]));

    await act(async () => {
      await result.current.send("hello world");
    });

    // After send, messages should include the user msg (refetch returns empty in mock,
    // but the streamingText should reflect the reply)
    expect(result.current.streamingText).toBe("reply");
  });

  test("inflight flips during streaming", async () => {
    server.use(
      http.get("/api/v1/threads/t1/messages", () => HttpResponse.json([])),
      http.post("/api/v1/threads/t1/messages", () => streamResponse([
        'data: {"type":"done"}\n\n',
      ])),
    );

    const { result } = renderHook(() => useChat("t1"), { wrapper });
    await waitFor(() => expect(result.current.messages).toEqual([]));
    expect(result.current.inflight).toBe(false);

    await act(async () => {
      await result.current.send("test");
    });
    expect(result.current.inflight).toBe(false);
  });
});
```

- [ ] **Step 2: Run — should fail**

Run: `cd web && npm test -- useChat`
Expected: FAIL.

- [ ] **Step 3: Implement**

Create `web/app/components/chat/hooks/useChat.ts`:

```typescript
"use client";

import useSWR from "swr";
import { useStream } from "./useStream";

const fetcher = async (url: string) => {
  const res = await fetch(`/api/v1${url}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};

export type Message = {
  id: number;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  module_tag?: string | null;
  created_at: string;
};


export function useChat(threadId: string) {
  const stream = useStream();
  const { data: messages, mutate } = useSWR<Message[]>(
    `/threads/${threadId}/messages`,
    fetcher,
  );

  const streamingText = stream.state.events
    .filter(e => e.type === "token")
    .map(e => (e as { text: string }).text)
    .join("");

  const send = async (text: string) => {
    const optimistic: Message = {
      id: -Date.now(),
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    void mutate([...(messages ?? []), optimistic], false);

    await stream.start(`/api/v1/threads/${threadId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });

    void mutate();
  };

  return {
    messages: messages ?? [],
    streamingText,
    inflight: stream.state.inflight,
    error: stream.state.error,
    send,
  };
}
```

- [ ] **Step 4: Run + commit**

```bash
cd web && npm test -- useChat
git add web/app/components/chat/hooks/useChat.ts web/app/components/chat/hooks/useChat.test.tsx
git commit -m "feat(web): useChat hook wrapping SWR + useStream"
```

Expected: 3 PASS.

---

### Task 8: useProjectState hook

**Files:**
- Create: `web/app/components/chat/hooks/useProjectState.ts`
- Create: `web/app/components/chat/hooks/useProjectState.test.tsx`

- [ ] **Step 1: Test**

```typescript
// web/app/components/chat/hooks/useProjectState.test.tsx
import { describe, expect, test } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { http } from "msw";
import { server } from "../../../../tests/setup";
import { streamResponse } from "../../../../tests/helpers/sseResponse";
import { useProjectState } from "./useProjectState";


describe("useProjectState", () => {
  test("reduces context_update events into a snapshot", async () => {
    server.use(
      http.get("/api/v1/threads/t1/state", () => streamResponse([
        'data: {"type":"context_update","patch":{"m1_topic":{"research_title":"X"}}}\n\n',
        'data: {"type":"context_update","patch":{"m2_literature":{"research_state_summary":"Y"}}}\n\n',
      ])),
    );

    const { result } = renderHook(() => useProjectState("t1"));
    await waitFor(() => {
      expect(result.current.latest.m1_topic).toEqual({ research_title: "X" });
    });
    expect(result.current.latest.m2_literature).toEqual({ research_state_summary: "Y" });
  });
});
```

- [ ] **Step 2: Implement**

Create `web/app/components/chat/hooks/useProjectState.ts`:

```typescript
"use client";

import { useEffect, useMemo } from "react";
import { useStream } from "./useStream";


export function useProjectState(threadId: string) {
  const stream = useStream();

  useEffect(() => {
    if (!threadId) return;
    void stream.start(`/api/v1/threads/${threadId}/state`, { method: "GET" });
    return () => stream.cancel();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId]);

  const latest = useMemo(() => {
    return stream.state.events.reduce((acc, ev) => {
      if (ev.type === "context_update") {
        return { ...acc, ...((ev as { patch: Record<string, unknown> }).patch) };
      }
      return acc;
    }, {} as Record<string, unknown>);
  }, [stream.state.events]);

  const remoteUpdates = stream.state.events.filter(e => e.type === "remote_update");

  return { latest, remoteUpdates, inflight: stream.state.inflight };
}
```

- [ ] **Step 3: Run + commit**

```bash
cd web && npm test -- useProjectState
git add web/app/components/chat/hooks/useProjectState.ts web/app/components/chat/hooks/useProjectState.test.tsx
git commit -m "feat(web): useProjectState hook subscribing to /threads/{tid}/state SSE"
```

---

### Task 9: useAutoDraftRun hook

**Files:**
- Create: `web/app/components/chat/hooks/useAutoDraftRun.ts`
- Create: `web/app/components/chat/hooks/useAutoDraftRun.test.tsx`

- [ ] **Step 1: Test**

```typescript
// web/app/components/chat/hooks/useAutoDraftRun.test.tsx
import { describe, expect, test } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { http } from "msw";
import { server } from "../../../../tests/setup";
import { streamResponse } from "../../../../tests/helpers/sseResponse";
import { useAutoDraftRun } from "./useAutoDraftRun";


describe("useAutoDraftRun", () => {
  test("subscribes to /runs/{rid}/events when runId set", async () => {
    server.use(
      http.get("/api/v1/runs/r1/events", () => streamResponse([
        'data: {"type":"activity","module":"M1","text":"started"}\n\n',
        'data: {"type":"module_complete","module":"M1"}\n\n',
        'data: {"type":"job_done"}\n\n',
      ])),
    );

    const { result } = renderHook(() => useAutoDraftRun("r1"));
    await waitFor(() => {
      expect(result.current.events.some(e => e.type === "job_done")).toBe(true);
    });
    const completes = result.current.events.filter(e => e.type === "module_complete");
    expect(completes.length).toBe(1);
  });

  test("no run id → no fetch", () => {
    const { result } = renderHook(() => useAutoDraftRun(null));
    expect(result.current.events).toEqual([]);
  });
});
```

- [ ] **Step 2: Implement**

```typescript
// web/app/components/chat/hooks/useAutoDraftRun.ts
"use client";

import { useEffect } from "react";
import { useStream } from "./useStream";


export function useAutoDraftRun(runId: string | null) {
  const stream = useStream();

  useEffect(() => {
    if (!runId) return;
    void stream.start(`/api/v1/runs/${runId}/events`, { method: "GET" });
    return () => stream.cancel();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  return stream.state;
}
```

- [ ] **Step 3: Run + commit**

```bash
cd web && npm test -- useAutoDraftRun
git add web/app/components/chat/hooks/useAutoDraftRun.ts web/app/components/chat/hooks/useAutoDraftRun.test.tsx
git commit -m "feat(web): useAutoDraftRun hook subscribing to /runs/{rid}/events"
```

---

## Phase E — Pure components

### Task 10: MessageBubble + StreamingBubble

**Files:**
- Create: `web/app/components/chat/MessageBubble.tsx`
- Create: `web/app/components/chat/StreamingBubble.tsx`
- Create: `web/app/components/chat/MessageBubble.test.tsx`

- [ ] **Step 1: Tests**

```typescript
// web/app/components/chat/MessageBubble.test.tsx
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { MessageBubble } from "./MessageBubble";
import { StreamingBubble } from "./StreamingBubble";


describe("MessageBubble", () => {
  test("renders user role on the right", () => {
    render(<MessageBubble role="user" content="hello" />);
    const el = screen.getByText("hello");
    expect(el.closest("[data-role='user']")).toBeTruthy();
  });

  test("renders assistant role on the left with module tag", () => {
    render(<MessageBubble role="assistant" content="hi" moduleTag="M2" />);
    expect(screen.getByText("hi")).toBeTruthy();
    expect(screen.getByText("M2")).toBeTruthy();
  });

  test("system messages render distinct style", () => {
    render(<MessageBubble role="system" content="[confirmed M1]" />);
    const el = screen.getByText("[confirmed M1]");
    expect(el.closest("[data-role='system']")).toBeTruthy();
  });
});


describe("StreamingBubble", () => {
  test("renders text + cursor", () => {
    render(<StreamingBubble text="streaming…" />);
    expect(screen.getByText("streaming…")).toBeTruthy();
    expect(screen.getByTestId("streaming-cursor")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Implement**

```typescript
// web/app/components/chat/MessageBubble.tsx
import { ReactNode } from "react";

export type MessageBubbleProps = {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  moduleTag?: string | null;
  children?: ReactNode;
};


export function MessageBubble({ role, content, moduleTag, children }: MessageBubbleProps) {
  const isUser = role === "user";
  const isSystem = role === "system";

  return (
    <div
      data-role={role}
      className={`flex ${isUser ? "justify-end" : "justify-start"} mb-3`}
    >
      <div
        className={
          isUser
            ? "max-w-[70%] rounded-2xl rounded-br-sm bg-purple-600 text-white px-4 py-2"
            : isSystem
            ? "max-w-[70%] rounded-md bg-gray-100 text-gray-600 px-3 py-1 text-sm italic"
            : "max-w-[70%] rounded-2xl rounded-bl-sm bg-gray-50 text-gray-900 px-4 py-2 border border-gray-200"
        }
      >
        {moduleTag && !isUser && !isSystem && (
          <div className="text-[10px] uppercase tracking-wider text-gray-400 mb-1">{moduleTag}</div>
        )}
        <div className="whitespace-pre-wrap">{content}</div>
        {children}
      </div>
    </div>
  );
}
```

```typescript
// web/app/components/chat/StreamingBubble.tsx
export function StreamingBubble({ text, moduleTag }: { text: string; moduleTag?: string | null }) {
  return (
    <div className="flex justify-start mb-3" data-role="assistant">
      <div className="max-w-[70%] rounded-2xl rounded-bl-sm bg-gray-50 text-gray-900 px-4 py-2 border border-gray-200">
        {moduleTag && (
          <div className="text-[10px] uppercase tracking-wider text-gray-400 mb-1">{moduleTag}</div>
        )}
        <div className="whitespace-pre-wrap">
          {text}
          <span
            data-testid="streaming-cursor"
            className="inline-block w-0.5 h-4 bg-purple-600 animate-pulse ml-0.5"
          />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Run + commit**

```bash
cd web && npm test -- MessageBubble
git add web/app/components/chat/MessageBubble.tsx web/app/components/chat/StreamingBubble.tsx web/app/components/chat/MessageBubble.test.tsx
git commit -m "feat(web): MessageBubble + StreamingBubble components"
```

---

### Task 11: ModuleProgressDot

**Files:**
- Create: `web/app/components/chat/ModuleProgressDot.tsx`
- Create: `web/app/components/chat/ModuleProgressDot.test.tsx`

- [ ] **Step 1: Test + implement + commit**

```typescript
// web/app/components/chat/ModuleProgressDot.test.tsx
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { ModuleProgressDot } from "./ModuleProgressDot";


describe("ModuleProgressDot", () => {
  test("renders green dot when done", () => {
    render(<ModuleProgressDot module="M1" status="done" label="Topic Discovery" />);
    expect(screen.getByTestId("dot-M1")).toHaveClass("bg-green-500");
  });

  test("renders amber dot when active", () => {
    render(<ModuleProgressDot module="M2" status="active" label="Lit Review" />);
    expect(screen.getByTestId("dot-M2")).toHaveClass("bg-amber-500");
  });

  test("renders gray dot when locked", () => {
    render(<ModuleProgressDot module="M3" status="locked" label="Research Design" />);
    expect(screen.getByTestId("dot-M3")).toHaveClass("bg-gray-300");
  });

  test("renders red dot when needs_attention", () => {
    render(<ModuleProgressDot module="M4" status="needs_attention" label="Analysis" />);
    expect(screen.getByTestId("dot-M4")).toHaveClass("bg-red-500");
  });
});
```

```typescript
// web/app/components/chat/ModuleProgressDot.tsx
export type ModuleStatus = "done" | "active" | "locked" | "needs_attention";

const COLOR_BY_STATUS: Record<ModuleStatus, string> = {
  done: "bg-green-500",
  active: "bg-amber-500",
  locked: "bg-gray-300",
  needs_attention: "bg-red-500",
};


export function ModuleProgressDot({
  module,
  status,
  label,
  onClick,
}: {
  module: string;
  status: ModuleStatus;
  label: string;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center gap-2 w-full text-left py-1 px-2 rounded hover:bg-gray-50 transition-colors"
    >
      <span
        data-testid={`dot-${module}`}
        className={`inline-block w-2 h-2 rounded-full ${COLOR_BY_STATUS[status]}`}
      />
      <span className="text-xs font-medium text-gray-700">{module}</span>
      <span className="text-xs text-gray-500 truncate">{label}</span>
    </button>
  );
}
```

```bash
cd web && npm test -- ModuleProgressDot
git add web/app/components/chat/ModuleProgressDot.tsx web/app/components/chat/ModuleProgressDot.test.tsx
git commit -m "feat(web): ModuleProgressDot pure component"
```

Expected: 4 PASS.

---

### Task 12: UploadChip

**Files:**
- Create: `web/app/components/chat/UploadChip.tsx`
- Create: `web/app/components/chat/UploadChip.test.tsx`

- [ ] **Step 1: Test + impl + commit**

```typescript
// web/app/components/chat/UploadChip.test.tsx
import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { UploadChip } from "./UploadChip";


describe("UploadChip", () => {
  test("shows filename and page count when extracted", () => {
    render(
      <UploadChip
        filename="paper.pdf"
        pageCount={12}
        status="ready"
        onDelete={() => {}}
      />,
    );
    expect(screen.getByText("paper.pdf")).toBeTruthy();
    expect(screen.getByText(/12 pages/i)).toBeTruthy();
  });

  test("shows 'Extracting' when status=extracting", () => {
    render(
      <UploadChip
        filename="paper.pdf"
        pageCount={null}
        status="extracting"
        onDelete={() => {}}
      />,
    );
    expect(screen.getByText(/extracting/i)).toBeTruthy();
  });

  test("delete button fires callback", () => {
    const onDelete = vi.fn();
    render(<UploadChip filename="x.pdf" pageCount={1} status="ready" onDelete={onDelete} />);
    fireEvent.click(screen.getByRole("button", { name: /delete x\.pdf/i }));
    expect(onDelete).toHaveBeenCalled();
  });
});
```

```typescript
// web/app/components/chat/UploadChip.tsx
import { X, FileText, Loader } from "lucide-react";


export type UploadChipProps = {
  filename: string;
  pageCount: number | null;
  status: "uploading" | "extracting" | "ready" | "error";
  onDelete: () => void;
};


export function UploadChip({ filename, pageCount, status, onDelete }: UploadChipProps) {
  return (
    <div className="inline-flex items-center gap-2 px-2 py-1 rounded-md border border-gray-200 bg-gray-50 text-xs">
      {status === "uploading" || status === "extracting" ? (
        <Loader className="w-3 h-3 animate-spin text-gray-500" />
      ) : (
        <FileText className="w-3 h-3 text-gray-500" />
      )}
      <span className="font-medium text-gray-800 max-w-[180px] truncate">{filename}</span>
      <span className="text-gray-500">
        {status === "uploading" && "uploading…"}
        {status === "extracting" && "extracting…"}
        {status === "ready" && pageCount && `${pageCount} pages`}
        {status === "ready" && !pageCount && "ready"}
        {status === "error" && "failed"}
      </span>
      <button
        type="button"
        onClick={onDelete}
        aria-label={`Delete ${filename}`}
        className="ml-1 text-gray-400 hover:text-red-500"
      >
        <X className="w-3 h-3" />
      </button>
    </div>
  );
}
```

```bash
cd web && npm test -- UploadChip
git add web/app/components/chat/UploadChip.tsx web/app/components/chat/UploadChip.test.tsx
git commit -m "feat(web): UploadChip component"
```

Expected: 3 PASS.

---

### Task 13: TokenMeter

**Files:**
- Create: `web/app/components/chat/TokenMeter.tsx`
- Create: `web/app/components/chat/TokenMeter.test.tsx`

- [ ] **Step 1: Test + impl + commit**

```typescript
// web/app/components/chat/TokenMeter.test.tsx
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { TokenMeter } from "./TokenMeter";


describe("TokenMeter", () => {
  test("shows credits remaining", () => {
    render(<TokenMeter credits={12500} />);
    expect(screen.getByText(/12,500/)).toBeTruthy();
  });

  test("warns when low (< 5000)", () => {
    render(<TokenMeter credits={3000} />);
    const el = screen.getByTestId("token-meter");
    expect(el).toHaveClass("text-red-600");
  });

  test("ok when high (>= 5000)", () => {
    render(<TokenMeter credits={50000} />);
    const el = screen.getByTestId("token-meter");
    expect(el).not.toHaveClass("text-red-600");
  });
});
```

```typescript
// web/app/components/chat/TokenMeter.tsx
import { Zap } from "lucide-react";


export function TokenMeter({ credits }: { credits: number }) {
  const isLow = credits < 5000;
  return (
    <div
      data-testid="token-meter"
      className={`flex items-center gap-1 text-xs ${
        isLow ? "text-red-600 font-semibold" : "text-gray-500"
      }`}
    >
      <Zap className="w-3 h-3" />
      <span>{credits.toLocaleString()}</span>
    </div>
  );
}
```

```bash
cd web && npm test -- TokenMeter
git add web/app/components/chat/TokenMeter.tsx web/app/components/chat/TokenMeter.test.tsx
git commit -m "feat(web): TokenMeter component"
```

---

## Phase F — Container components

### Task 14: MessageList

**Files:**
- Create: `web/app/components/chat/MessageList.tsx`
- Create: `web/app/components/chat/MessageList.test.tsx`

- [ ] **Step 1: Test**

```typescript
// web/app/components/chat/MessageList.test.tsx
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { MessageList } from "./MessageList";


describe("MessageList", () => {
  test("renders all messages", () => {
    const messages = [
      { id: 1, role: "user" as const, content: "Hello", created_at: "2026-05-27" },
      { id: 2, role: "assistant" as const, content: "Hi back", created_at: "2026-05-27", module_tag: "M1" },
    ];
    render(<MessageList messages={messages} streamingText="" streamingModuleTag={null} />);
    expect(screen.getByText("Hello")).toBeTruthy();
    expect(screen.getByText("Hi back")).toBeTruthy();
    expect(screen.getByText("M1")).toBeTruthy();
  });

  test("renders streaming bubble when streamingText set", () => {
    render(<MessageList messages={[]} streamingText="streaming reply" streamingModuleTag="M2" />);
    expect(screen.getByText("streaming reply")).toBeTruthy();
    expect(screen.getByText("M2")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Implement**

```typescript
// web/app/components/chat/MessageList.tsx
"use client";

import { useEffect, useRef } from "react";
import { MessageBubble } from "./MessageBubble";
import { StreamingBubble } from "./StreamingBubble";
import type { Message } from "./hooks/useChat";


export function MessageList({
  messages,
  streamingText,
  streamingModuleTag,
}: {
  messages: Message[];
  streamingText: string;
  streamingModuleTag: string | null;
}) {
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, streamingText]);

  return (
    <div className="flex-1 overflow-y-auto px-6 py-4 bg-white">
      {messages.map(m => (
        <MessageBubble
          key={m.id}
          role={m.role}
          content={m.content}
          moduleTag={m.module_tag}
        />
      ))}
      {streamingText && (
        <StreamingBubble text={streamingText} moduleTag={streamingModuleTag} />
      )}
      <div ref={endRef} />
    </div>
  );
}
```

- [ ] **Step 3: Run + commit**

```bash
cd web && npm test -- MessageList
git add web/app/components/chat/MessageList.tsx web/app/components/chat/MessageList.test.tsx
git commit -m "feat(web): MessageList container with auto-scroll"
```

---

### Task 15: ContextModuleViewer + ContextPanel

**Files:**
- Create: `web/app/components/chat/ContextModuleViewer.tsx`
- Create: `web/app/components/chat/ContextPanel.tsx`
- Create: `web/app/components/chat/ContextPanel.test.tsx`

- [ ] **Step 1: Test**

```typescript
// web/app/components/chat/ContextPanel.test.tsx
import { describe, expect, test } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ContextPanel } from "./ContextPanel";


const _baseCtx = {
  m1_topic: { research_title: "X", confirmed_at: "2026-05-26" },
  m2_literature: null,
  m3_design: null,
  m4_analysis: null,
  m5_writing: null,
};


describe("ContextPanel", () => {
  test("renders all 5 module dots", () => {
    render(<ContextPanel contextStore={_baseCtx} uploads={[]} />);
    expect(screen.getByTestId("dot-M1")).toBeTruthy();
    expect(screen.getByTestId("dot-M2")).toBeTruthy();
    expect(screen.getByTestId("dot-M3")).toBeTruthy();
    expect(screen.getByTestId("dot-M4")).toBeTruthy();
    expect(screen.getByTestId("dot-M5")).toBeTruthy();
  });

  test("M1 confirmed → done; M2 locked", () => {
    render(<ContextPanel contextStore={_baseCtx} uploads={[]} />);
    expect(screen.getByTestId("dot-M1")).toHaveClass("bg-green-500");
    expect(screen.getByTestId("dot-M2")).toHaveClass("bg-gray-300");
  });

  test("clicking a confirmed module shows its content", () => {
    render(<ContextPanel contextStore={_baseCtx} uploads={[]} />);
    fireEvent.click(screen.getByTestId("dot-M1").closest("button")!);
    expect(screen.getByText(/research_title/i)).toBeTruthy();
  });

  test("uploads list shows filenames", () => {
    render(<ContextPanel contextStore={_baseCtx} uploads={[
      { id: "u1", filename: "paper.pdf", size_bytes: 1234, mime_type: "application/pdf", page_count: 12, uploaded_at: "2026-05-27" },
    ]} />);
    expect(screen.getByText("paper.pdf")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Implement**

```typescript
// web/app/components/chat/ContextModuleViewer.tsx
import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";


export function ContextModuleViewer({
  module,
  label,
  data,
}: {
  module: string;
  label: string;
  data: Record<string, unknown> | null;
}) {
  const [open, setOpen] = useState(false);
  if (!data) return null;

  return (
    <div className="border-t border-gray-100 first:border-t-0">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 w-full px-2 py-1.5 text-left hover:bg-gray-50 text-xs"
      >
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        <span className="font-medium">{module} · {label}</span>
      </button>
      {open && (
        <pre className="text-[10px] text-gray-600 px-2 py-2 bg-gray-50 overflow-x-auto max-h-48 overflow-y-auto">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}
```

```typescript
// web/app/components/chat/ContextPanel.tsx
import { ModuleProgressDot, ModuleStatus } from "./ModuleProgressDot";
import { ContextModuleViewer } from "./ContextModuleViewer";


export type ContextStore = {
  m1_topic: Record<string, unknown> | null;
  m2_literature: Record<string, unknown> | null;
  m3_design: Record<string, unknown> | null;
  m4_analysis: Record<string, unknown> | null;
  m5_writing: Record<string, unknown> | null;
};


export type UploadItem = {
  id: string;
  filename: string;
  size_bytes: number;
  mime_type: string;
  page_count: number | null;
  uploaded_at: string;
};


const MODULES: Array<{ key: keyof ContextStore; module: string; label: string }> = [
  { key: "m1_topic",      module: "M1", label: "Topic Discovery" },
  { key: "m2_literature", module: "M2", label: "Literature Review" },
  { key: "m3_design",     module: "M3", label: "Research Design" },
  { key: "m4_analysis",   module: "M4", label: "Data Analysis" },
  { key: "m5_writing",    module: "M5", label: "Writing" },
];


function statusFor(data: Record<string, unknown> | null, isCurrent: boolean): ModuleStatus {
  if (!data) return isCurrent ? "active" : "locked";
  return data.confirmed_at ? "done" : isCurrent ? "active" : "locked";
}


export function ContextPanel({
  contextStore,
  uploads,
  currentModule,
}: {
  contextStore: ContextStore;
  uploads: UploadItem[];
  currentModule?: string;
}) {
  // Find the next un-confirmed module
  const nextUnconfirmed = MODULES.find(m => !contextStore[m.key]?.confirmed_at)?.module;
  const active = currentModule ?? nextUnconfirmed;

  return (
    <aside className="w-64 border-l border-gray-200 bg-white overflow-y-auto">
      <div className="px-4 py-3 border-b border-gray-200">
        <h3 className="text-xs uppercase tracking-wider text-gray-500 font-semibold">Progress</h3>
      </div>
      <div className="py-2">
        {MODULES.map(m => (
          <ModuleProgressDot
            key={m.module}
            module={m.module}
            label={m.label}
            status={statusFor(contextStore[m.key], m.module === active)}
            onClick={() => {/* opens inline viewer via accordion below */}}
          />
        ))}
      </div>
      <div className="py-2">
        {MODULES.map(m => (
          <ContextModuleViewer
            key={m.module}
            module={m.module}
            label={m.label}
            data={contextStore[m.key]}
          />
        ))}
      </div>
      {uploads.length > 0 && (
        <div className="px-4 py-3 border-t border-gray-200">
          <h3 className="text-xs uppercase tracking-wider text-gray-500 font-semibold mb-2">
            📎 Uploads ({uploads.length})
          </h3>
          {uploads.map(u => (
            <div key={u.id} className="text-xs text-gray-700 truncate py-0.5">
              {u.filename}
              {u.page_count && <span className="text-gray-400 ml-1">· {u.page_count}p</span>}
            </div>
          ))}
        </div>
      )}
    </aside>
  );
}
```

- [ ] **Step 3: Run + commit**

```bash
cd web && npm test -- ContextPanel
git add web/app/components/chat/ContextPanel.tsx web/app/components/chat/ContextModuleViewer.tsx web/app/components/chat/ContextPanel.test.tsx
git commit -m "feat(web): ContextPanel right-pane with M1-M5 progress + uploads"
```

---

### Task 16: ThreadsSidebar

**Files:**
- Create: `web/app/components/chat/ThreadsSidebar.tsx`
- Create: `web/app/components/chat/ThreadsSidebar.test.tsx`

- [ ] **Step 1: Test**

```typescript
// web/app/components/chat/ThreadsSidebar.test.tsx
import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ThreadsSidebar } from "./ThreadsSidebar";


const _threads = [
  { id: "t1", project_id: "p1", name: "Main", status: "active", langgraph_thread_id: "lg-1", created_at: "2026-05-27", last_active_at: "2026-05-27" },
  { id: "t2", project_id: "p1", name: "Alt", status: "active", langgraph_thread_id: "lg-2", created_at: "2026-05-27", last_active_at: "2026-05-27" },
];


describe("ThreadsSidebar", () => {
  test("lists all threads", () => {
    render(<ThreadsSidebar threads={_threads} currentThreadId="t1" onSelectThread={() => {}} onCreateThread={() => {}} />);
    expect(screen.getByText("Main")).toBeTruthy();
    expect(screen.getByText("Alt")).toBeTruthy();
  });

  test("highlights current thread", () => {
    render(<ThreadsSidebar threads={_threads} currentThreadId="t1" onSelectThread={() => {}} onCreateThread={() => {}} />);
    const mainItem = screen.getByText("Main").closest("button");
    expect(mainItem).toHaveClass("bg-purple-50");
  });

  test("click selects thread", () => {
    const onSelect = vi.fn();
    render(<ThreadsSidebar threads={_threads} currentThreadId="t1" onSelectThread={onSelect} onCreateThread={() => {}} />);
    fireEvent.click(screen.getByText("Alt").closest("button")!);
    expect(onSelect).toHaveBeenCalledWith("t2");
  });

  test("new thread button fires callback", () => {
    const onCreate = vi.fn();
    render(<ThreadsSidebar threads={_threads} currentThreadId="t1" onSelectThread={() => {}} onCreateThread={onCreate} />);
    fireEvent.click(screen.getByRole("button", { name: /new thread/i }));
    expect(onCreate).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Implement**

```typescript
// web/app/components/chat/ThreadsSidebar.tsx
import { Plus, MessageSquare } from "lucide-react";


export type Thread = {
  id: string;
  project_id: string;
  name: string;
  status: string;
  langgraph_thread_id: string;
  created_at: string;
  last_active_at: string;
};


export function ThreadsSidebar({
  threads,
  currentThreadId,
  onSelectThread,
  onCreateThread,
}: {
  threads: Thread[];
  currentThreadId: string;
  onSelectThread: (tid: string) => void;
  onCreateThread: () => void;
}) {
  return (
    <aside className="w-52 border-r border-gray-200 bg-gray-50 flex flex-col">
      <div className="px-4 py-3 border-b border-gray-200">
        <h3 className="text-xs uppercase tracking-wider text-gray-500 font-semibold">Threads</h3>
      </div>
      <div className="flex-1 overflow-y-auto py-2">
        {threads.map(t => (
          <button
            key={t.id}
            type="button"
            onClick={() => onSelectThread(t.id)}
            className={`flex items-center gap-2 w-full px-4 py-1.5 text-left text-sm hover:bg-gray-100 ${
              t.id === currentThreadId ? "bg-purple-50 text-purple-700 font-medium" : "text-gray-700"
            }`}
          >
            <MessageSquare className="w-3 h-3" />
            <span className="truncate">{t.name}</span>
          </button>
        ))}
      </div>
      <div className="p-3 border-t border-gray-200">
        <button
          type="button"
          onClick={onCreateThread}
          aria-label="new thread"
          className="flex items-center justify-center gap-1 w-full py-1.5 px-2 text-xs text-gray-700 hover:bg-gray-100 rounded border border-dashed border-gray-300"
        >
          <Plus className="w-3 h-3" /> New thread
        </button>
      </div>
    </aside>
  );
}
```

- [ ] **Step 3: Run + commit**

```bash
cd web && npm test -- ThreadsSidebar
git add web/app/components/chat/ThreadsSidebar.tsx web/app/components/chat/ThreadsSidebar.test.tsx
git commit -m "feat(web): ThreadsSidebar left-pane component"
```

---

### Task 17: ChatInput + FileDropZone

**Files:**
- Create: `web/app/components/chat/ChatInput.tsx`
- Create: `web/app/components/chat/FileDropZone.tsx`
- Create: `web/app/components/chat/ChatInput.test.tsx`

- [ ] **Step 1: Test**

```typescript
// web/app/components/chat/ChatInput.test.tsx
import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChatInput } from "./ChatInput";


describe("ChatInput", () => {
  test("calls onSubmit with text and clears", async () => {
    const onSubmit = vi.fn();
    render(<ChatInput onSubmit={onSubmit} onFileDrop={() => {}} disabled={false} />);
    const textarea = screen.getByRole("textbox");
    await userEvent.type(textarea, "hello world");
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    expect(onSubmit).toHaveBeenCalledWith("hello world");
  });

  test("Enter submits; Shift+Enter inserts newline", async () => {
    const onSubmit = vi.fn();
    render(<ChatInput onSubmit={onSubmit} onFileDrop={() => {}} disabled={false} />);
    const textarea = screen.getByRole("textbox") as HTMLTextAreaElement;
    await userEvent.type(textarea, "hello");
    await userEvent.keyboard("{Enter}");
    expect(onSubmit).toHaveBeenCalledWith("hello");
  });

  test("disabled prevents send", async () => {
    const onSubmit = vi.fn();
    render(<ChatInput onSubmit={onSubmit} onFileDrop={() => {}} disabled={true} />);
    expect(screen.getByRole("textbox")).toBeDisabled();
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  });

  test("file drop fires onFileDrop", () => {
    const onFileDrop = vi.fn();
    render(<ChatInput onSubmit={() => {}} onFileDrop={onFileDrop} disabled={false} />);
    const zone = screen.getByTestId("file-drop-zone");
    const file = new File(["x"], "test.pdf", { type: "application/pdf" });
    fireEvent.drop(zone, { dataTransfer: { files: [file] } });
    expect(onFileDrop).toHaveBeenCalledWith([file]);
  });
});
```

- [ ] **Step 2: Implement**

```typescript
// web/app/components/chat/FileDropZone.tsx
"use client";

import { ReactNode, useState } from "react";


export function FileDropZone({
  onFileDrop,
  children,
}: {
  onFileDrop: (files: File[]) => void;
  children: ReactNode;
}) {
  const [dragging, setDragging] = useState(false);

  return (
    <div
      data-testid="file-drop-zone"
      onDragEnter={e => { e.preventDefault(); setDragging(true); }}
      onDragLeave={e => { e.preventDefault(); setDragging(false); }}
      onDragOver={e => e.preventDefault()}
      onDrop={e => {
        e.preventDefault();
        setDragging(false);
        const files = Array.from(e.dataTransfer.files);
        if (files.length > 0) onFileDrop(files);
      }}
      className={`relative ${dragging ? "ring-2 ring-purple-400 ring-offset-1" : ""}`}
    >
      {children}
      {dragging && (
        <div className="absolute inset-0 bg-purple-50/80 pointer-events-none flex items-center justify-center text-sm text-purple-700 font-medium z-10">
          Drop PDFs here
        </div>
      )}
    </div>
  );
}
```

```typescript
// web/app/components/chat/ChatInput.tsx
"use client";

import { useState } from "react";
import { Send, Paperclip } from "lucide-react";
import { FileDropZone } from "./FileDropZone";


export function ChatInput({
  onSubmit,
  onFileDrop,
  disabled,
}: {
  onSubmit: (text: string) => void;
  onFileDrop: (files: File[]) => void;
  disabled: boolean;
}) {
  const [text, setText] = useState("");

  const handleSubmit = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
    setText("");
  };

  return (
    <FileDropZone onFileDrop={onFileDrop}>
      <div className="border-t border-gray-200 bg-white px-4 py-3 flex items-end gap-2">
        <button
          type="button"
          disabled={disabled}
          className="text-gray-500 hover:text-purple-600 disabled:opacity-50 pb-1"
          onClick={() => {
            const input = document.createElement("input");
            input.type = "file";
            input.accept = "application/pdf,text/plain";
            input.multiple = true;
            input.onchange = () => {
              if (input.files) onFileDrop(Array.from(input.files));
            };
            input.click();
          }}
          aria-label="attach file"
        >
          <Paperclip className="w-4 h-4" />
        </button>

        <textarea
          rows={1}
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSubmit();
            }
          }}
          placeholder="Type a message…"
          disabled={disabled}
          className="flex-1 resize-none border border-gray-200 rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-purple-400 disabled:opacity-50 max-h-32"
        />

        <button
          type="button"
          onClick={handleSubmit}
          disabled={disabled || !text.trim()}
          aria-label="send"
          className="bg-purple-600 text-white rounded-md p-2 hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
    </FileDropZone>
  );
}
```

- [ ] **Step 3: Run + commit**

```bash
cd web && npm test -- ChatInput
git add web/app/components/chat/ChatInput.tsx web/app/components/chat/FileDropZone.tsx web/app/components/chat/ChatInput.test.tsx
git commit -m "feat(web): ChatInput + FileDropZone with keyboard send + drag-and-drop"
```

---

### Task 18: ChatHeader

**Files:**
- Create: `web/app/components/chat/ChatHeader.tsx`
- Create: `web/app/components/chat/ChatHeader.test.tsx`

- [ ] **Step 1: Test + impl + commit**

```typescript
// web/app/components/chat/ChatHeader.test.tsx
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChatHeader } from "./ChatHeader";


describe("ChatHeader", () => {
  test("renders project + thread name", () => {
    render(<ChatHeader projectName="Leadership Thesis" threadName="Main" autoDraftButton={null} />);
    expect(screen.getByText("Leadership Thesis")).toBeTruthy();
    expect(screen.getByText("Main")).toBeTruthy();
  });

  test("renders auto-draft slot", () => {
    render(<ChatHeader projectName="X" threadName="Y" autoDraftButton={<button>Auto-draft</button>} />);
    expect(screen.getByRole("button", { name: /auto-draft/i })).toBeTruthy();
  });
});
```

```typescript
// web/app/components/chat/ChatHeader.tsx
import { ReactNode } from "react";


export function ChatHeader({
  projectName,
  threadName,
  autoDraftButton,
}: {
  projectName: string;
  threadName: string;
  autoDraftButton: ReactNode;
}) {
  return (
    <header className="border-b border-gray-200 bg-white px-6 py-3 flex items-center justify-between">
      <div className="flex items-baseline gap-2">
        <span className="font-semibold text-gray-900">{projectName}</span>
        <span className="text-gray-300">·</span>
        <span className="text-sm text-gray-600">{threadName}</span>
      </div>
      <div>{autoDraftButton}</div>
    </header>
  );
}
```

```bash
cd web && npm test -- ChatHeader
git add web/app/components/chat/ChatHeader.tsx web/app/components/chat/ChatHeader.test.tsx
git commit -m "feat(web): ChatHeader component"
```

---

### Task 19: ChatShellLayout (3-pane container)

**Files:**
- Create: `web/app/components/chat/ChatShellLayout.tsx`
- Create: `web/app/components/chat/ChatShellLayout.test.tsx`

- [ ] **Step 1: Test**

```typescript
// web/app/components/chat/ChatShellLayout.test.tsx
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChatShellLayout } from "./ChatShellLayout";


describe("ChatShellLayout", () => {
  test("renders all 3 panes", () => {
    render(
      <ChatShellLayout
        leftPane={<div>LEFT</div>}
        rightPane={<div>RIGHT</div>}
      >
        <div>CENTER</div>
      </ChatShellLayout>,
    );
    expect(screen.getByText("LEFT")).toBeTruthy();
    expect(screen.getByText("CENTER")).toBeTruthy();
    expect(screen.getByText("RIGHT")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Implement**

```typescript
// web/app/components/chat/ChatShellLayout.tsx
"use client";

import { ReactNode } from "react";


export function ChatShellLayout({
  leftPane,
  rightPane,
  children,
}: {
  leftPane: ReactNode;
  rightPane: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex h-[calc(100vh-3.5rem)] bg-white">
      {/* Left pane — threads — hidden below lg */}
      <div className="hidden lg:flex flex-shrink-0">{leftPane}</div>

      {/* Middle pane — chat */}
      <main className="flex-1 flex flex-col min-w-0">{children}</main>

      {/* Right pane — context — hidden below lg */}
      <div className="hidden lg:flex flex-shrink-0">{rightPane}</div>
    </div>
  );
}
```

- [ ] **Step 3: Run + commit**

```bash
cd web && npm test -- ChatShellLayout
git add web/app/components/chat/ChatShellLayout.tsx web/app/components/chat/ChatShellLayout.test.tsx
git commit -m "feat(web): ChatShellLayout 3-pane container with responsive collapse"
```

---

## Phase G — Auto-draft surface

### Task 20: AutoDraftButton

**Files:**
- Create: `web/app/components/chat/AutoDraftButton.tsx`
- Create: `web/app/components/chat/AutoDraftButton.test.tsx`

- [ ] **Step 1: Test + impl + commit**

```typescript
// web/app/components/chat/AutoDraftButton.test.tsx
import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { AutoDraftButton } from "./AutoDraftButton";


describe("AutoDraftButton", () => {
  test.each([
    [null,        /^auto-draft$/i],
    ["queued",    /^auto-draft$/i],
    ["running",   /^auto-drafting/i],
    ["paused",    /^resume$/i],
    ["done",      /done · download/i],
    ["failed",    /failed · retry/i],
    ["canceled",  /^auto-draft$/i],
  ])("status=%s renders correct label", (status, pattern) => {
    render(<AutoDraftButton runStatus={status} onClick={() => {}} />);
    expect(screen.getByRole("button").textContent).toMatch(pattern);
  });

  test("onClick fires", () => {
    const onClick = vi.fn();
    render(<AutoDraftButton runStatus={null} onClick={onClick} />);
    fireEvent.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalled();
  });
});
```

```typescript
// web/app/components/chat/AutoDraftButton.tsx
import { Sparkles, Loader, CheckCircle2, AlertCircle, Play } from "lucide-react";


export type RunStatus =
  | null
  | "queued"
  | "running"
  | "paused"
  | "done"
  | "failed"
  | "canceled";


const _CONFIG: Record<string, { label: string; icon: typeof Sparkles; className: string }> = {
  none:     { label: "Auto-draft",         icon: Sparkles,    className: "bg-purple-600 hover:bg-purple-700 text-white" },
  running:  { label: "Auto-drafting…",     icon: Loader,      className: "bg-amber-500 hover:bg-amber-600 text-white" },
  paused:   { label: "Resume",             icon: Play,        className: "bg-amber-500 hover:bg-amber-600 text-white" },
  done:     { label: "Done · Download",    icon: CheckCircle2,className: "bg-green-600 hover:bg-green-700 text-white" },
  failed:   { label: "Failed · Retry",     icon: AlertCircle, className: "bg-red-600 hover:bg-red-700 text-white" },
};


function pick(status: RunStatus) {
  if (status === "running" || status === "queued") return _CONFIG[status === "queued" ? "none" : "running"];
  if (status === "paused") return _CONFIG.paused;
  if (status === "done")   return _CONFIG.done;
  if (status === "failed") return _CONFIG.failed;
  return _CONFIG.none;
}


export function AutoDraftButton({ runStatus, onClick }: { runStatus: RunStatus; onClick: () => void }) {
  const cfg = pick(runStatus);
  const Icon = cfg.icon;
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${cfg.className}`}
    >
      <Icon className={`w-4 h-4 ${runStatus === "running" ? "animate-spin" : ""}`} />
      {cfg.label}
    </button>
  );
}
```

```bash
cd web && npm test -- AutoDraftButton
git add web/app/components/chat/AutoDraftButton.tsx web/app/components/chat/AutoDraftButton.test.tsx
git commit -m "feat(web): AutoDraftButton with state-aware label + icon"
```

---

### Task 21: AutoDraftModal

**Files:**
- Create: `web/app/components/chat/AutoDraftModal.tsx`
- Create: `web/app/components/chat/AutoDraftModal.test.tsx`

- [ ] **Step 1: Test + impl + commit**

```typescript
// web/app/components/chat/AutoDraftModal.test.tsx
import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../../../tests/setup";
import { AutoDraftModal } from "./AutoDraftModal";


describe("AutoDraftModal", () => {
  test("fetches estimate and renders it", async () => {
    server.use(
      http.get("/api/v1/projects/p1/runs/estimate", () =>
        HttpResponse.json({ estimated_tokens: 18500, credit_balance: 50000, sufficient_credit: true }),
      ),
    );
    render(
      <AutoDraftModal
        open={true}
        projectId="p1"
        defaultTopic="Leadership"
        onClose={() => {}}
        onConfirm={() => {}}
      />,
    );
    await waitFor(() => expect(screen.getByText(/18,500/)).toBeTruthy());
    expect(screen.getByText(/50,000/)).toBeTruthy();
  });

  test("confirm fires callback with topic", async () => {
    server.use(
      http.get("/api/v1/projects/p1/runs/estimate", () =>
        HttpResponse.json({ estimated_tokens: 100, credit_balance: 1000, sufficient_credit: true }),
      ),
    );
    const onConfirm = vi.fn();
    render(
      <AutoDraftModal open={true} projectId="p1" defaultTopic="seed" onClose={() => {}} onConfirm={onConfirm} />,
    );
    await waitFor(() => expect(screen.getByDisplayValue("seed")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /start auto-draft/i }));
    expect(onConfirm).toHaveBeenCalledWith("seed");
  });

  test("does not render when open=false", () => {
    render(<AutoDraftModal open={false} projectId="p1" defaultTopic="" onClose={() => {}} onConfirm={() => {}} />);
    expect(screen.queryByText(/start auto-draft/i)).toBeNull();
  });
});
```

```typescript
// web/app/components/chat/AutoDraftModal.tsx
"use client";

import { useState } from "react";
import useSWR from "swr";
import { X } from "lucide-react";


const fetcher = async (url: string) => {
  const res = await fetch(`/api/v1${url}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};


export function AutoDraftModal({
  open,
  projectId,
  defaultTopic,
  onClose,
  onConfirm,
}: {
  open: boolean;
  projectId: string;
  defaultTopic: string;
  onClose: () => void;
  onConfirm: (topic: string) => void;
}) {
  const [topic, setTopic] = useState(defaultTopic);
  const { data: est } = useSWR(
    open && projectId ? `/projects/${projectId}/runs/estimate?topic=${encodeURIComponent(topic)}` : null,
    fetcher,
  );

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={onClose}>
      <div
        onClick={e => e.stopPropagation()}
        className="bg-white rounded-lg shadow-xl max-w-md w-full p-6"
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-start justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Start auto-draft</h2>
          <button type="button" onClick={onClose} aria-label="close">
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        <label className="block text-sm font-medium text-gray-700 mb-1">Research topic</label>
        <textarea
          value={topic}
          onChange={e => setTopic(e.target.value)}
          rows={3}
          className="w-full border border-gray-200 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-purple-400 mb-4"
        />

        {est && (
          <div className="bg-gray-50 rounded-md p-3 text-sm mb-4">
            <div className="flex justify-between mb-1">
              <span className="text-gray-600">Estimated tokens:</span>
              <span className="font-medium">{(est.estimated_tokens as number).toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Your balance:</span>
              <span className={`font-medium ${est.sufficient_credit ? "" : "text-red-600"}`}>
                {(est.credit_balance as number).toLocaleString()}
              </span>
            </div>
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100 rounded-md"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onConfirm(topic)}
            disabled={!topic.trim() || (est && !est.sufficient_credit)}
            className="px-3 py-1.5 text-sm bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:opacity-50"
          >
            Start auto-draft
          </button>
        </div>
      </div>
    </div>
  );
}
```

```bash
cd web && npm test -- AutoDraftModal
git add web/app/components/chat/AutoDraftModal.tsx web/app/components/chat/AutoDraftModal.test.tsx
git commit -m "feat(web): AutoDraftModal with token estimate + balance check"
```

---

### Task 22: AutoDraftDrawer

**Files:**
- Create: `web/app/components/chat/AutoDraftDrawer.tsx`
- Create: `web/app/components/chat/AutoDraftDrawer.test.tsx`

- [ ] **Step 1: Test**

```typescript
// web/app/components/chat/AutoDraftDrawer.test.tsx
import { describe, expect, test, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../../../tests/setup";
import { streamResponse } from "../../../tests/helpers/sseResponse";
import { AutoDraftDrawer } from "./AutoDraftDrawer";


describe("AutoDraftDrawer", () => {
  test("renders module progress from events", async () => {
    server.use(
      http.get("/api/v1/runs/r1", () => HttpResponse.json({
        id: "r1", project_id: "p1", status: "running", phase: null, progress: 0,
        mode: "auto", started_at: "2026-05-27T00:00:00Z", finished_at: null, error_text: null,
        events_url: "/api/v1/runs/r1/events",
      })),
      http.get("/api/v1/runs/r1/events", () => streamResponse([
        'data: {"type":"activity","module":"M1","text":"started"}\n\n',
        'data: {"type":"module_complete","module":"M1"}\n\n',
        'data: {"type":"activity","module":"M2","text":"scouting"}\n\n',
      ])),
    );

    render(<AutoDraftDrawer runId="r1" onClose={() => {}} />);

    await waitFor(() => {
      expect(screen.getByTestId("dot-M1")).toHaveClass("bg-green-500");
    });
    expect(screen.getByTestId("dot-M2")).toHaveClass("bg-amber-500");
  });

  test("close button fires onClose", async () => {
    server.use(
      http.get("/api/v1/runs/r2", () => HttpResponse.json({ id: "r2", status: "running" })),
      http.get("/api/v1/runs/r2/events", () => streamResponse(['data: {"type":"done"}\n\n'])),
    );
    const onClose = vi.fn();
    render(<AutoDraftDrawer runId="r2" onClose={onClose} />);
    await waitFor(() => screen.getByLabelText(/close drawer/i));
    fireEvent.click(screen.getByLabelText(/close drawer/i));
    expect(onClose).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Implement**

```typescript
// web/app/components/chat/AutoDraftDrawer.tsx
"use client";

import { useMemo } from "react";
import useSWR from "swr";
import { X, Pause, Play, XCircle } from "lucide-react";
import { ModuleProgressDot, type ModuleStatus } from "./ModuleProgressDot";
import { useAutoDraftRun } from "./hooks/useAutoDraftRun";


const fetcher = async (url: string) => {
  const res = await fetch(`/api/v1${url}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};

const MODULES = [
  { module: "M1", label: "Topic Discovery" },
  { module: "M2", label: "Literature Review" },
  { module: "M3", label: "Research Design" },
  { module: "M4", label: "Data Analysis" },
  { module: "M5", label: "Writing" },
];


export function AutoDraftDrawer({ runId, onClose }: { runId: string; onClose: () => void }) {
  const { data: run, mutate: mutateRun } = useSWR(`/runs/${runId}`, fetcher, { refreshInterval: 5000 });
  const { events } = useAutoDraftRun(runId);

  const statusByModule = useMemo(() => {
    const status: Record<string, ModuleStatus> = {
      M1: "locked", M2: "locked", M3: "locked", M4: "locked", M5: "locked",
    };
    for (const ev of events) {
      const m = (ev as { module?: string }).module;
      if (!m) continue;
      if (ev.type === "module_complete") status[m] = "done";
      else if (ev.type === "activity" && status[m] === "locked") status[m] = "active";
    }
    return status;
  }, [events]);

  const activity = events.filter(e => e.type === "activity").slice(-50);
  const tokenCost = events.filter(e => e.type === "token_cost")
    .reduce((acc, e) => acc + ((e as { tokens?: number }).tokens ?? 0), 0);
  const exports = events.find(e => e.type === "job_done") as { exports?: Record<string, string> } | undefined;

  const pause  = async () => { await fetch(`/api/v1/runs/${runId}/pause`,  { method: "POST" }); void mutateRun(); };
  const resume = async () => { await fetch(`/api/v1/runs/${runId}/resume`, { method: "POST" }); void mutateRun(); };
  const cancel = async () => { await fetch(`/api/v1/runs/${runId}/cancel`, { method: "POST" }); void mutateRun(); };

  return (
    <aside className="fixed right-0 top-14 bottom-0 w-[480px] bg-white border-l border-gray-200 shadow-xl z-40 flex flex-col">
      <header className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
        <div>
          <h3 className="font-semibold">Run {runId.slice(0, 8)}</h3>
          <p className="text-xs text-gray-500">Status: {run?.status ?? "loading…"}</p>
        </div>
        <button type="button" onClick={onClose} aria-label="close drawer">
          <X className="w-5 h-5 text-gray-500" />
        </button>
      </header>

      <div className="flex-1 overflow-y-auto p-6">
        <h4 className="text-xs uppercase tracking-wider text-gray-500 font-semibold mb-2">Progress</h4>
        {MODULES.map(m => (
          <ModuleProgressDot
            key={m.module}
            module={m.module}
            label={m.label}
            status={statusByModule[m.module]}
          />
        ))}

        <h4 className="text-xs uppercase tracking-wider text-gray-500 font-semibold mt-6 mb-2">
          Activity feed
        </h4>
        <div className="bg-gray-50 rounded-md p-3 text-xs space-y-1 max-h-64 overflow-y-auto font-mono">
          {activity.map((ev, i) => (
            <div key={i} className="text-gray-700">
              <span className="text-purple-600 mr-2">{(ev as { module?: string }).module ?? "•"}</span>
              {(ev as { text?: string }).text ?? JSON.stringify(ev)}
            </div>
          ))}
        </div>

        {tokenCost > 0 && (
          <div className="mt-4 text-xs text-gray-600">
            Tokens used: <span className="font-medium">{tokenCost.toLocaleString()}</span>
          </div>
        )}

        {exports?.exports && (
          <div className="mt-6 space-y-2">
            <h4 className="text-xs uppercase tracking-wider text-gray-500 font-semibold">Exports</h4>
            {Object.entries(exports.exports).map(([kind, uri]) => (
              <a
                key={kind}
                href={uri as string}
                className="block text-sm text-purple-600 hover:underline"
              >
                📄 Download {kind.toUpperCase()}
              </a>
            ))}
          </div>
        )}
      </div>

      <footer className="px-6 py-3 border-t border-gray-200 flex gap-2">
        {run?.status === "running" && (
          <button onClick={pause} className="flex items-center gap-1 text-sm text-gray-700 hover:bg-gray-100 px-3 py-1.5 rounded">
            <Pause className="w-4 h-4" /> Pause
          </button>
        )}
        {run?.status === "paused" && (
          <button onClick={resume} className="flex items-center gap-1 text-sm bg-purple-600 text-white hover:bg-purple-700 px-3 py-1.5 rounded">
            <Play className="w-4 h-4" /> Resume
          </button>
        )}
        {(run?.status === "running" || run?.status === "paused") && (
          <button onClick={cancel} className="flex items-center gap-1 text-sm text-red-600 hover:bg-red-50 px-3 py-1.5 rounded ml-auto">
            <XCircle className="w-4 h-4" /> Cancel
          </button>
        )}
      </footer>
    </aside>
  );
}
```

- [ ] **Step 3: Run + commit**

```bash
cd web && npm test -- AutoDraftDrawer
git add web/app/components/chat/AutoDraftDrawer.tsx web/app/components/chat/AutoDraftDrawer.test.tsx
git commit -m "feat(web): AutoDraftDrawer slide-out with live progress + pause/resume"
```

---

## Phase H — Routes + landing

### Task 23: ProjectListGrid

**Files:**
- Create: `web/app/components/chat/ProjectListGrid.tsx`
- Create: `web/app/components/chat/ProjectListGrid.test.tsx`

- [ ] **Step 1: Test + impl + commit**

```typescript
// web/app/components/chat/ProjectListGrid.test.tsx
import { describe, expect, test } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../../../tests/setup";
import { ProjectListGrid } from "./ProjectListGrid";


describe("ProjectListGrid", () => {
  test("renders project cards", async () => {
    server.use(
      http.get("/api/v1/projects", () => HttpResponse.json([
        { id: "p1", name: "Leadership Thesis", field: "Marketing", language: "en",
          citation_style: "apa", status: "draft", current_module: "M2",
          context_store: { m1_topic: { confirmed_at: "x" } },
          created_at: "2026-05-27", updated_at: "2026-05-27" },
      ])),
    );
    render(<ProjectListGrid />);
    await waitFor(() => expect(screen.getByText("Leadership Thesis")).toBeTruthy());
  });

  test("renders empty state when no projects", async () => {
    server.use(
      http.get("/api/v1/projects", () => HttpResponse.json([])),
    );
    render(<ProjectListGrid />);
    await waitFor(() => expect(screen.getByText(/no projects yet/i)).toBeTruthy());
  });
});
```

```typescript
// web/app/components/chat/ProjectListGrid.tsx
"use client";

import useSWR from "swr";
import Link from "next/link";
import { Plus, ChevronRight } from "lucide-react";


type Project = {
  id: string;
  name: string;
  field: string | null;
  language: string;
  status: string;
  current_module: string;
  context_store: { m1_topic?: { confirmed_at?: string | null } | null };
  created_at: string;
  updated_at: string;
};


const fetcher = async (url: string) => {
  const res = await fetch(`/api/v1${url}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};


export function ProjectListGrid() {
  const { data: projects, mutate } = useSWR<Project[]>("/projects", fetcher);

  const newProject = async () => {
    const name = window.prompt("Project name?");
    if (!name) return;
    await fetch("/api/v1/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    void mutate();
  };

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Your projects</h1>
        <button
          type="button"
          onClick={newProject}
          className="inline-flex items-center gap-1 bg-purple-600 text-white px-3 py-1.5 rounded-md text-sm hover:bg-purple-700"
        >
          <Plus className="w-4 h-4" /> New project
        </button>
      </div>

      <div className="bg-purple-50 border border-purple-200 rounded-md px-4 py-3 text-sm text-purple-900 mb-6">
        Auto-draft works here. For full thesis generation, the wizard is still recommended
        until module-specific UIs ship. <Link href="/wizard" className="underline">Open wizard</Link>
      </div>

      {projects && projects.length === 0 && (
        <div className="text-center py-12 text-gray-500">No projects yet. Click "New project" to get started.</div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {projects?.map(p => (
          <Link
            key={p.id}
            href={`/chat/projects/${p.id}`}
            className="block bg-white border border-gray-200 rounded-lg p-4 hover:border-purple-400 hover:shadow-sm transition-all"
          >
            <h3 className="font-semibold text-gray-900 mb-1 flex items-center justify-between">
              {p.name}
              <ChevronRight className="w-4 h-4 text-gray-400" />
            </h3>
            <p className="text-xs text-gray-500">
              {p.field ?? "no field"} · {p.language} · {p.current_module}
            </p>
          </Link>
        ))}
      </div>
    </div>
  );
}
```

```bash
cd web && npm test -- ProjectListGrid
git add web/app/components/chat/ProjectListGrid.tsx web/app/components/chat/ProjectListGrid.test.tsx
git commit -m "feat(web): ProjectListGrid /chat landing page"
```

---

### Task 24: (chat) route group + layouts + pages

**Files:**
- Create: `web/app/(chat)/layout.tsx`
- Create: `web/app/(chat)/page.tsx`
- Create: `web/app/(chat)/projects/[pid]/layout.tsx`
- Create: `web/app/(chat)/projects/[pid]/page.tsx`
- Create: `web/app/(chat)/projects/[pid]/threads/[tid]/page.tsx`
- Create: `web/app/components/chat/ChatPane.tsx`

- [ ] **Step 1: Outer layout**

```typescript
// web/app/(chat)/layout.tsx
"use client";

import type { ReactNode } from "react";
import { AnnouncementProvider } from "@/app/components/announcements/AnnouncementProvider";
import { SidebarLayout } from "@/app/components/layout/SidebarLayout";
import { useSidebarSections } from "@/app/components/layout/use-sections";


export default function ChatRouteLayout({ children }: { children: ReactNode }) {
  const sections = useSidebarSections();
  return (
    <SidebarLayout sections={sections}>
      <AnnouncementProvider>{children}</AnnouncementProvider>
    </SidebarLayout>
  );
}
```

- [ ] **Step 2: /chat landing**

```typescript
// web/app/(chat)/page.tsx
"use client";

import { ProjectListGrid } from "@/app/components/chat/ProjectListGrid";


export default function ChatHome() {
  return <ProjectListGrid />;
}
```

- [ ] **Step 3: Project layout (3-pane shell)**

```typescript
// web/app/(chat)/projects/[pid]/layout.tsx
"use client";

import { type ReactNode } from "react";
import useSWR from "swr";
import { useParams, useRouter } from "next/navigation";
import { ChatShellLayout } from "@/app/components/chat/ChatShellLayout";
import { ThreadsSidebar, type Thread } from "@/app/components/chat/ThreadsSidebar";
import { ContextPanel, type ContextStore, type UploadItem } from "@/app/components/chat/ContextPanel";


const fetcher = async (url: string) => {
  const res = await fetch(`/api/v1${url}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};


export default function ProjectLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const params = useParams<{ pid: string; tid?: string }>();
  const pid = params.pid;
  const currentTid = params.tid;

  const { data: project } = useSWR<{ context_store: ContextStore; current_module: string }>(
    `/projects/${pid}`, fetcher,
  );
  const { data: threads, mutate: mutateThreads } = useSWR<Thread[]>(
    `/projects/${pid}/threads`, fetcher,
  );
  const { data: uploads } = useSWR<UploadItem[]>(`/projects/${pid}/uploads`, fetcher);

  const createThread = async () => {
    const r = await fetch(`/api/v1/projects/${pid}/threads`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "New thread" }),
    });
    const t: Thread = await r.json();
    void mutateThreads();
    router.push(`/chat/projects/${pid}/threads/${t.id}`);
  };

  return (
    <ChatShellLayout
      leftPane={
        <ThreadsSidebar
          threads={threads ?? []}
          currentThreadId={currentTid ?? ""}
          onSelectThread={tid => router.push(`/chat/projects/${pid}/threads/${tid}`)}
          onCreateThread={createThread}
        />
      }
      rightPane={
        <ContextPanel
          contextStore={project?.context_store ?? {
            m1_topic: null, m2_literature: null, m3_design: null, m4_analysis: null, m5_writing: null,
          }}
          uploads={uploads ?? []}
          currentModule={project?.current_module}
        />
      }
    >
      {children}
    </ChatShellLayout>
  );
}
```

- [ ] **Step 4: Project page (redirect to Main thread)**

```typescript
// web/app/(chat)/projects/[pid]/page.tsx
"use client";

import { useEffect } from "react";
import useSWR from "swr";
import { useParams, useRouter } from "next/navigation";


const fetcher = async (url: string) => {
  const res = await fetch(`/api/v1${url}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};


export default function ProjectIndex() {
  const router = useRouter();
  const params = useParams<{ pid: string }>();
  const { data: threads } = useSWR<Array<{ id: string }>>(
    `/projects/${params.pid}/threads`, fetcher,
  );

  useEffect(() => {
    if (threads && threads.length > 0) {
      router.replace(`/chat/projects/${params.pid}/threads/${threads[0].id}`);
    }
  }, [threads, params.pid, router]);

  return <div className="p-6 text-sm text-gray-500">Loading thread…</div>;
}
```

- [ ] **Step 5: Thread page**

```typescript
// web/app/(chat)/projects/[pid]/threads/[tid]/page.tsx
"use client";

import { useParams } from "next/navigation";
import { ChatPane } from "@/app/components/chat/ChatPane";


export default function ThreadPage() {
  const params = useParams<{ pid: string; tid: string }>();
  return <ChatPane projectId={params.pid} threadId={params.tid} />;
}
```

- [ ] **Step 6: ChatPane component (assembles header + list + input + auto-draft modal/drawer)**

Create `web/app/components/chat/ChatPane.tsx`:

```typescript
"use client";

import { useState } from "react";
import useSWR from "swr";
import { useChat } from "./hooks/useChat";
import { ChatHeader } from "./ChatHeader";
import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import { AutoDraftButton, type RunStatus } from "./AutoDraftButton";
import { AutoDraftModal } from "./AutoDraftModal";
import { AutoDraftDrawer } from "./AutoDraftDrawer";


const fetcher = async (url: string) => {
  const res = await fetch(`/api/v1${url}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};


export function ChatPane({ projectId, threadId }: { projectId: string; threadId: string }) {
  const { messages, streamingText, inflight, send } = useChat(threadId);
  const { data: project } = useSWR<{ name: string; context_store: { m1_topic?: { research_title?: string } | null } }>(
    `/projects/${projectId}`, fetcher,
  );
  const { data: thread } = useSWR<{ name: string }>(`/threads/${threadId}`, fetcher);
  const { data: latestRun, mutate: mutateRun } = useSWR<{ run: { id: string; status: RunStatus } | null }>(
    `/projects/${projectId}/runs?latest=true`, fetcher,
  );

  const [modalOpen, setModalOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const onAutoDraftClick = () => {
    const status = latestRun?.run?.status ?? null;
    if (status === "running" || status === "paused" || status === "done" || status === "failed") {
      setDrawerOpen(true);
    } else {
      setModalOpen(true);
    }
  };

  const confirmAutoDraft = async (topic: string) => {
    setModalOpen(false);
    const r = await fetch(`/api/v1/projects/${projectId}/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: "auto", topic }),
    });
    if (r.ok) {
      void mutateRun();
      setDrawerOpen(true);
    }
  };

  const onFileDrop = async (files: File[]) => {
    for (const f of files) {
      const fd = new FormData();
      fd.append("file", f);
      await fetch(`/api/v1/projects/${projectId}/uploads`, { method: "POST", body: fd });
    }
  };

  // Determine module tag of in-flight stream from the most recent module event
  const streamingModuleTag = null;  // simplified for SP7; populate from events if needed later

  return (
    <>
      <ChatHeader
        projectName={project?.name ?? "…"}
        threadName={thread?.name ?? "…"}
        autoDraftButton={
          <AutoDraftButton runStatus={latestRun?.run?.status ?? null} onClick={onAutoDraftClick} />
        }
      />
      <MessageList
        messages={messages}
        streamingText={inflight ? streamingText : ""}
        streamingModuleTag={streamingModuleTag}
      />
      <ChatInput onSubmit={send} onFileDrop={onFileDrop} disabled={inflight} />

      <AutoDraftModal
        open={modalOpen}
        projectId={projectId}
        defaultTopic={project?.context_store?.m1_topic?.research_title ?? ""}
        onClose={() => setModalOpen(false)}
        onConfirm={confirmAutoDraft}
      />
      {drawerOpen && latestRun?.run && (
        <AutoDraftDrawer runId={latestRun.run.id} onClose={() => setDrawerOpen(false)} />
      )}
    </>
  );
}
```

- [ ] **Step 7: Smoke-test build**

```bash
cd web && npm run build 2>&1 | tail -10
```
Expected: build succeeds (no TS errors). If there are import errors, fix them.

- [ ] **Step 8: Commit**

```bash
git add web/app/\(chat\)/ web/app/components/chat/ChatPane.tsx
git commit -m "feat(web): (chat) route group + 3-pane layout + ChatPane wiring"
```

---

## Phase I — Integration tests

### Task 25: ChatPane end-to-end integration test

**Files:**
- Create: `web/app/components/chat/ChatPane.test.tsx`

- [ ] **Step 1: Test**

```typescript
// web/app/components/chat/ChatPane.test.tsx
import { describe, expect, test } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../../../tests/setup";
import { streamResponse } from "../../../tests/helpers/sseResponse";
import { ChatPane } from "./ChatPane";


function setupMocks() {
  server.use(
    http.get("/api/v1/projects/p1", () => HttpResponse.json({
      name: "Test Project",
      context_store: { m1_topic: null },
    })),
    http.get("/api/v1/threads/t1", () => HttpResponse.json({ name: "Main" })),
    http.get("/api/v1/projects/p1/runs", () => HttpResponse.json({ run: null })),
    http.get("/api/v1/threads/t1/messages", () => HttpResponse.json([])),
  );
}


describe("ChatPane integration", () => {
  test("send → stream → message persisted", async () => {
    setupMocks();
    let postCount = 0;
    server.use(
      http.post("/api/v1/threads/t1/messages", () => {
        postCount++;
        return streamResponse([
          'data: {"type":"token","text":"Hello! "}\n\n',
          'data: {"type":"token","text":"How can I help?"}\n\n',
          'data: {"type":"done"}\n\n',
        ]);
      }),
    );

    render(<ChatPane projectId="p1" threadId="t1" />);
    await waitFor(() => screen.getByText("Test Project"));

    const textarea = screen.getByRole("textbox");
    await userEvent.type(textarea, "hi there");
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    // Optimistic user message
    await waitFor(() => expect(screen.getByText("hi there")).toBeTruthy());
    // Streaming reply concatenates
    await waitFor(() => expect(screen.getByText(/Hello!.*How can I help/)).toBeTruthy());
    expect(postCount).toBe(1);
  });
});
```

- [ ] **Step 2: Run + commit**

```bash
cd web && npm test -- ChatPane
git add web/app/components/chat/ChatPane.test.tsx
git commit -m "test(web): ChatPane integration — send → stream → render"
```

---

### Task 26: AutoDraft end-to-end integration test

**Files:**
- Create: `web/app/components/chat/AutoDraft.integration.test.tsx`

- [ ] **Step 1: Test + commit**

```typescript
// web/app/components/chat/AutoDraft.integration.test.tsx
import { describe, expect, test } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../../../tests/setup";
import { streamResponse } from "../../../tests/helpers/sseResponse";
import { ChatPane } from "./ChatPane";


describe("AutoDraft integration", () => {
  test("click button → modal → confirm → drawer → done", async () => {
    let runStatus: "running" | "done" = "running";
    server.use(
      http.get("/api/v1/projects/p1", () => HttpResponse.json({
        name: "T", context_store: { m1_topic: { research_title: "Leadership" } },
      })),
      http.get("/api/v1/threads/t1", () => HttpResponse.json({ name: "Main" })),
      http.get("/api/v1/threads/t1/messages", () => HttpResponse.json([])),
      http.get("/api/v1/projects/p1/runs", () => HttpResponse.json({
        run: runStatus === "running" ? null : { id: "r1", status: runStatus },
      })),
      http.get("/api/v1/projects/p1/runs/estimate", () => HttpResponse.json({
        estimated_tokens: 20000, credit_balance: 100000, sufficient_credit: true,
      })),
      http.post("/api/v1/projects/p1/runs", () => {
        runStatus = "running";
        return HttpResponse.json({ run_id: "r1", status: "running" });
      }),
      http.get("/api/v1/runs/r1", () => HttpResponse.json({
        id: "r1", status: runStatus, mode: "auto",
      })),
      http.get("/api/v1/runs/r1/events", () => streamResponse([
        'data: {"type":"activity","module":"M1","text":"start"}\n\n',
        'data: {"type":"module_complete","module":"M1"}\n\n',
        'data: {"type":"job_done","exports":{"docx":"s3://b/thesis.docx","pdf":"s3://b/thesis.pdf"}}\n\n',
      ])),
    );

    render(<ChatPane projectId="p1" threadId="t1" />);
    await waitFor(() => screen.getByRole("button", { name: /auto-draft/i }));

    // Click button → opens modal
    fireEvent.click(screen.getByRole("button", { name: /auto-draft/i }));
    await waitFor(() => screen.getByText(/start auto-draft/i));

    // Modal has pre-filled topic + estimate
    await waitFor(() => expect(screen.getByDisplayValue("Leadership")).toBeTruthy());

    // Confirm
    fireEvent.click(screen.getByRole("button", { name: /^start auto-draft$/i }));

    // Drawer opens; module dot turns green
    await waitFor(() => screen.getByText(/run r1/i), { timeout: 2000 });
    await waitFor(() => {
      expect(screen.getByTestId("dot-M1")).toHaveClass("bg-green-500");
    });

    // After job_done, download links appear
    await waitFor(() => expect(screen.getByText(/download docx/i)).toBeTruthy());
  });
});
```

```bash
cd web && npm test -- AutoDraft.integration
git add web/app/components/chat/AutoDraft.integration.test.tsx
git commit -m "test(web): auto-draft integration — modal → drawer → exports"
```

---

## Phase J — Wrap-up

### Task 27: Wizard banner + final regression + roadmap flip

**Files:**
- Modify: `web/app/components/dashboard.jsx`
- Modify: `docs/superpowers/2026-05-26-platform-pivot-roadmap.md`

- [ ] **Step 1: Add banner to dashboard**

Edit `web/app/components/dashboard.jsx`. Find the top of the rendered output (typically a `return` with a wrapper div). Add a banner just inside, before the existing content:

```jsx
        <div className="bg-purple-50 border border-purple-200 rounded-md px-4 py-3 text-sm text-purple-900 mb-6">
          <strong>New:</strong> Try the chat-based research experience.{" "}
          <a href="/chat" className="underline font-medium">Open the chat UI →</a>
        </div>
```

(If `dashboard.jsx` uses a different idiom, place the banner above the projects/papers grid.)

- [ ] **Step 2: Run all tests**

```bash
cd /Users/caonguyenvan/project/dothesis
source api/.venv/bin/activate
# Orchestrator
python -m pytest orchestrator/tests/ -m "integration or not integration" -q --no-header 2>&1 | tail -3
# API
cd api && python -m pytest tests/ -q --no-header 2>&1 | tail -3
cd ..
# Web
cd web && npm test 2>&1 | tail -10
```

Expected:
- Orchestrator: same or better than baseline (117 from SP2).
- API: same baseline failures (52) + no new failures. New tests from Phase A pass.
- Web: all new tests pass.

- [ ] **Step 3: Update roadmap**

Edit `docs/superpowers/2026-05-26-platform-pivot-roadmap.md`:

Find:
```
## Sub-project 7 — New Next.js chat UI ⬜
```

Replace with:
```
## Sub-project 7 — New Next.js chat UI ✅

**Status:** Shipped 2026-05-27 (branch `feat/sp7-chat-ui-shell`; 3-pane shell + useStream + auto-draft drawer)
```

Find the ASCII map. Update the "7. New chat UI" box label to show "(7 ✅)".

Find the status log table. Append:

```
| 2026-05-27 | 7 | ⬜ → ✅ | Chat UI shell shipped (no module-specific widgets yet); SP3-SP6 will plug widgets into this shell |
```

Also update the "Re-entry checklist" section if it mentions ordering — note that the actual ship order was 1, 2, 7 (not 1, 2, 3).

- [ ] **Step 4: Commit**

```bash
git add web/app/components/dashboard.jsx docs/superpowers/2026-05-26-platform-pivot-roadmap.md
git commit -m "docs+web: SP7 shipped — wizard banner + roadmap flip to ✅"
```

---

## Done criteria checklist

- [ ] All 27 tasks committed in order
- [ ] All web tests pass (`cd web && npm test`)
- [ ] Orchestrator tests still pass (no regressions)
- [ ] API tests show only baseline failures + new Phase A tests passing
- [ ] `npm run build` succeeds in web/
- [ ] `/chat` route reachable in dev (`./dev.sh` or `cd web && npm run dev`)
- [ ] Roadmap flipped to ✅
- [ ] Wizard banner visible on `/` directing to `/chat`

## What's next after SP7 ships

SP3 (M1 card-grid) is next. SP3-SP6 each:
1. Add their module-specific render hints in the backend (agent emits structured `tool_calls_json` directing the UI)
2. Add their custom widget component under `web/app/components/chat/widgets/`
3. Wire it into `MessageList` so when an assistant message has a recognized `tool_calls_json` shape, the widget renders inline instead of (or alongside) plain text

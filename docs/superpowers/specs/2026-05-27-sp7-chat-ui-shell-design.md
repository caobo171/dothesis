> **📜 Historical record — superseded.** This document captured a plan / spec / design at a point in time and is kept for history. It does **not** describe the current system. For the live DoThesis method and architecture see `README.md`, `AGENTS.md`, `docs/ARCHITECTURE.md`, and `docs/PIPELINE.md`.

# SP7 — Chat UI shell (Next.js)

**Date:** 2026-05-27
**Status:** Draft — pending user review
**Depends on:** Sub-project 1 (orchestration foundation) + Sub-project 2 (M2 chat-first + uploads). Both shipped on master.

## Context

Sub-projects 1 and 2 shipped the backend for chat-based research (LangGraph orchestrator + 5 module agents + PDF upload subsystem + per-thread SSE streaming endpoint). The existing wizard frontend (`web/app/(inapp)/wizard`) does not exercise any of that — it only triggers the legacy synchronous `python -m engine` path.

The original roadmap had SP7 (chat UI) at position 7, with module-specific UX redesigns (SP3 card-grid for M1, SP4 model builder for M3, etc.) coming first. **We re-ordered: SP7 now comes next, as the "chat shell" carrier for SP3-SP6's widgets.** Doing it the other way produces module-specific render hints with no frontend to display them.

SP7's job is to ship a working chat UI — text-only, no module-specific widgets — that consumes the SP1+SP2 backend APIs end-to-end. Each subsequent sub-project (SP3-SP6) will plug its own widget into this shell.

## Goal

Ship a new Next.js route group (`web/app/(chat)/`) with:

- 3-pane layout (threads / chat / persistent progress + context panel)
- Full chat experience: send message, stream assistant reply via SSE, persistent history
- Multi-thread per project (matches SP1's design)
- File upload via drag-and-drop (consumes SP2's `POST /projects/{id}/uploads`)
- Auto-draft launcher + slide-out progress drawer (consumes SP1's `runs` API)
- Read-only context_store viewer in the right panel
- No regressions in existing wizard flow

## Non-goals

- Module-specific widgets — card grids, drag-and-drop model builder, outline editor, WYSIWYG section editor. These are SP3-SP6.
- Editing confirmed context_store outputs from the right panel. SP3-SP6.
- Markdown / LaTeX rendering inside messages. Plain text + linebreaks only.
- Mobile-pretty layout. Tablet+ works (graceful 1-pane collapse below 1024px); phone polish is a follow-on.
- Dark mode toggle. Inherits whatever theming exists (none today).
- Keyboard shortcuts (cmd+k, autocomplete, etc.).
- Cross-thread message search.
- Citing inline via `/cite [doi]` chat command.
- Wizard deprecation — old wizard stays alive and reachable.
- "Pause auto-mode and switch to interactive" mid-run. Deferred since SP1.
- Real-time multi-user collab on the same thread.
- Frontend Sentry / error reporting. `console.error` + in-UI error bubbles for now.
- i18n. Hard-coded EN strings.

## Decisions (locked from brainstorming)

- **Layout:** 3-pane (threads / chat / persistent progress + context). Mobile collapses to 1-pane with drawer toggles for the side panes.
- **Component approach:** Raw Tailwind + lucide-react. Match the existing `(inapp)` pattern. Revisit shadcn after SP3-SP6 reveal which primitives we actually need.
- **Streaming:** Hand-rolled `useStream(url, init)` React hook backed by `fetch` + `ReadableStream.getReader()` + SSE-frame parser. Reusable for chat messages AND auto-draft drawer.
- **State management:** SWR for queries; `useState`/reducer + `useStream` for in-flight streams. No new global state library.
- **Auto-draft:** Launcher button in chat header. Click → confirmation modal → spawn run → slide-out drawer subscribes to `/runs/{id}/events`.
- **Routing:** New `(chat)` route group; routes are `/chat`, `/chat/projects/[pid]`, `/chat/projects/[pid]/threads/[tid]`. `(inapp)` and existing wizard untouched.
- **Auth:** Reuses existing `dothesis_session` cookie + redirect-to-login behavior in `swrFetcher`.

---

## Architecture & route structure

The chat UI lives in a new route group, sibling to existing `(inapp)`. Same Next.js app, same auth, same outer `SidebarLayout` (so the app-wide left nav stays consistent). Inside the chat route, a local 3-pane layout takes over the content area.

```
web/app/
├── (inapp)/                           # existing — wizard, papers, paper/[id], etc.
│   └── (unchanged)
└── (chat)/                            # NEW
    ├── layout.tsx                     # outer SidebarLayout + AnnouncementProvider (mirrors (inapp))
    ├── page.tsx                       # /chat — project list grid
    └── projects/
        └── [pid]/
            ├── layout.tsx             # 3-pane shell (threads sidebar + main + context panel)
            ├── page.tsx               # /chat/projects/[pid] — auto-redirects to Main thread
            └── threads/
                └── [tid]/
                    └── page.tsx       # /chat/projects/[pid]/threads/[tid] — the actual chat
```

### Routes

| Route | Component | Purpose |
|---|---|---|
| `/chat` | `ProjectListGrid` | Card grid of the user's projects; "+ new project" button |
| `/chat/projects/{pid}` | redirect | Auto-redirects to the project's Main thread |
| `/chat/projects/{pid}/threads/{tid}` | `ChatShellLayout` + `ChatPane` | The 3-pane chat experience |

### Component tree under `web/app/components/chat/`

```
web/app/components/chat/
├── ProjectListGrid.tsx                # /chat landing
├── ChatShellLayout.tsx                # 3-pane container
├── ThreadsSidebar.tsx                 # left pane — thread list + "new thread"
├── ContextPanel.tsx                   # right pane — M1-M5 progress + read-only output viewer
├── ChatPane.tsx                       # middle pane container
├── ChatHeader.tsx                     # project name + thread name + AutoDraftButton
├── MessageList.tsx                    # scrollable history; auto-scroll on new message
├── MessageBubble.tsx                  # one bubble (role-aware: user / assistant / system / tool)
├── StreamingBubble.tsx                # specialized bubble showing the in-flight stream
├── ChatInput.tsx                      # textarea + send button + token meter
├── FileDropZone.tsx                   # wraps ChatInput; HTML5 drag-and-drop → upload
├── UploadChip.tsx                     # one uploaded paper, with delete affordance
├── TokenMeter.tsx                     # credits remaining indicator
├── AutoDraftButton.tsx                # chat header — state-aware ("Auto-draft" / "Running…" / "Done")
├── AutoDraftModal.tsx                 # confirm before spawning
├── AutoDraftDrawer.tsx                # slide-out from the right; live progress
├── ModuleProgressDot.tsx              # one dot (M1..M5) with status colors
├── ContextModuleViewer.tsx            # expandable accordion showing one module's confirmed output
└── hooks/
    ├── useStream.ts                   # THE streaming primitive — fetch + ReadableStream + SSE parse
    ├── useChat.ts                     # wraps useStream + SWR for /threads/{tid}/messages
    ├── useProjectState.ts             # subscribes to /threads/{tid}/state SSE
    └── useAutoDraftRun.ts             # SWR for run metadata + useStream for events tail
```

### Data flow (send message)

```
                              user types message
                                    │
                                    ▼
                            ChatInput onSubmit
                                    │
                                    ▼
                            useChat.send(text)
                                    │
                          optimistic: push user msg
                                    │
                                    ▼
                useStream.start("POST /threads/{tid}/messages", {text})
                                    │
                            ReadableStream chunks
                                    │
                            parse SSE event lines
                                    │
                ┌───────────────────┼────────────────────┐
                ▼                   ▼                    ▼
            type=token         type=token_cost      type=done
       (append to streaming   (TokenMeter         (finalize, mutate
        bubble)               updates)            SWR /messages)
```

Parallel: `useProjectState(tid)` subscribes to `/threads/{tid}/state` SSE. When the underlying `context_store` changes (this thread confirmed a module, OR another thread of the same project did), the right-pane `ContextPanel` re-renders.

---

## The `useStream` hook (the new primitive)

Single most important new abstraction in SP7. Reused twice: chat message streams, auto-draft progress drawer.

```typescript
// web/app/components/chat/hooks/useStream.ts
"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";

export type SSEEvent = {
  type: string;                      // "token" | "module" | "done" | "token_cost" | "remote_update" | "paused" | "job_done" | "error"
  [key: string]: unknown;            // event-shape varies; consumers narrow by `type`
};

export type StreamState = {
  events: SSEEvent[];                // all events received this stream
  inflight: boolean;                 // true while the stream is open
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
  const [state, dispatch] = useReducer(reducer, { events: [], inflight: false, error: null });
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

        // SSE frames are separated by \n\n; each frame can have multiple lines.
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
            /* malformed frame; skip */
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

### Chat usage

```typescript
// web/app/components/chat/hooks/useChat.ts
export function useChat(threadId: string) {
  const stream = useStream();
  const { data: messages, mutate } = useSWR(`/threads/${threadId}/messages`, swrFetcher);

  const streamingText = stream.state.events
    .filter(e => e.type === "token")
    .map(e => (e as { text: string }).text)
    .join("");

  const send = async (text: string) => {
    // Optimistic user message
    mutate([...(messages ?? []), { role: "user", content: text, id: -1 }], false);
    await stream.start(`/api/v1/threads/${threadId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    mutate();  // re-fetch authoritative history
  };

  return { messages: messages ?? [], streamingText, inflight: stream.state.inflight, send };
}
```

### Auto-draft usage

```typescript
// web/app/components/chat/hooks/useAutoDraftRun.ts
export function useAutoDraftRun(runId: string | null) {
  const stream = useStream();
  useEffect(() => {
    if (!runId) return;
    stream.start(`/api/v1/runs/${runId}/events`, { method: "GET" });
    return stream.cancel;
  }, [runId]);
  return stream.state;
}
```

---

## State management & data fetching

Existing repo uses SWR. SP7 sticks with SWR for queries; uses `useState`/reducer via `useStream` for streams.

### SWR endpoints

```
useSWR("/projects",                          swrFetcher)   // GET /api/v1/projects
useSWR(`/projects/${pid}`,                   swrFetcher)   // GET /api/v1/projects/{pid}
useSWR(`/projects/${pid}/threads`,           swrFetcher)   // GET /api/v1/projects/{pid}/threads
useSWR(`/threads/${tid}/messages`,           swrFetcher)   // GET /api/v1/threads/{tid}/messages
useSWR(`/projects/${pid}/uploads`,           swrFetcher)   // GET /api/v1/projects/{pid}/uploads
useSWR(`/projects/${pid}/runs/latest`,       swrFetcher)   // GET — latest run only
useSWR(`/runs/${rid}`,                       swrFetcher, { refreshInterval: 5000 })
```

### Mutations & optimistic updates

| Action | Approach |
|---|---|
| Create project | POST then `mutate("/projects")`; navigate to new project |
| Create thread | POST then `mutate(\`/projects/${pid}/threads\`)`; navigate |
| Send message | Optimistic local push; stream reply; `mutate(\`/threads/${tid}/messages\`)` on done |
| Upload file | Optimistic "Uploading…" chip; `mutate(\`/projects/${pid}/uploads\`)` after POST |
| Delete upload | Optimistic filter-out; `mutate` to confirm |

### Backend additions needed by SP7

Three small endpoints called out for the implementer to verify against the SP1 + SP2 reality and add if missing:

1. **`GET /api/v1/threads/{tid}/state`** — SSE stream of `context_store` updates + remote-update events. Listed in SP1 spec; may not be fully implemented. Add if missing.
2. **`GET /api/v1/projects/{pid}/runs?latest=true&limit=1`** — latest run for a project (drives `AutoDraftButton` state). Add if missing.
3. **`GET /api/v1/projects/{pid}/runs/estimate?topic=...`** — token-cost estimate before spawning a run. Add if missing.

These are small (< 50 LoC each) backend additions; included in SP7's plan because the chat UI directly depends on them.

---

## Auto-draft launcher + drawer

### State machine

```
[no run yet] ──click──▶ AutoDraftModal ──confirm──▶ POST /runs ──▶ [running]
                                                                       │
[running] ──click──▶ AutoDraftDrawer (live)                            │
                                                                       │
[running] ──auto──▶ [done | failed | paused] ──user resumes──▶ [running]
```

### `AutoDraftButton` states

| Run state | Button label | Action on click |
|---|---|---|
| no run | "Auto-draft" | Open modal |
| running | "Auto-drafting…" (spinner) | Open drawer |
| paused | "Resume" | Open drawer with Resume CTA |
| done | "Done · Download" | Open drawer with downloads |
| failed | "Failed · Retry" | Open drawer with retry/error |

### `AutoDraftModal`

- Fetches estimate via `GET /projects/{pid}/runs/estimate?topic=<seed>`
- Pre-fills topic from `m1_topic.research_title` if confirmed
- Shows: estimated tokens, current credit balance, topic textarea
- "Start auto-draft" button → `POST /projects/{pid}/runs` body `{mode: "auto", topic}`
- "Cancel" button → close

### `AutoDraftDrawer`

Slides in from the right (~480px wide on desktop). Overlays the context panel temporarily; closing restores it.

```
┌─ AutoDraftDrawer ────────────────────────────┐
│  Run #abc12 · Started 4 min ago    [✕ close] │
├──────────────────────────────────────────────┤
│  Status: Running                              │
│  Current module: M3 Research Design           │
│                                               │
│  [●] M1 Topic               ✓ complete        │
│  [●] M2 Literature          ✓ complete        │
│  [◐] M3 Research Design     in progress       │
│  [○] M4 Data Analysis       waiting           │
│  [○] M5 Writing             waiting           │
│                                               │
│  Activity feed (last 50):                     │
│  ┌──────────────────────────────────────────┐ │
│  │ 12:42 M3 Agent · Recommending PLS-SEM   │ │
│  │ 12:41 M3 Agent · Building conceptual…   │ │
│  │ 12:40 M2 Agent · 42 citations found     │ │
│  └──────────────────────────────────────────┘ │
│                                               │
│  Token cost so far: 12,840 / ~45,000          │
│                                               │
│  [Pause]                              [Cancel]│
└──────────────────────────────────────────────┘
```

On `job_done`:

```
│  Status: Done ✓                               │
│  All 5 modules completed in 38 min            │
│                                               │
│  Exports:                                     │
│    [📄 Download Chapter 1-5 DOCX] (1.2 MB)    │
│    [📄 Download PDF]              (3.8 MB)    │
│                                               │
│  [Start new run]              [View results]  │
```

### Pause / Resume / Cancel

```typescript
const pause  = () => fetch(`/api/v1/runs/${runId}/pause`,  { method: "POST" });
const resume = () => fetch(`/api/v1/runs/${runId}/resume`, { method: "POST" });
const cancel = () => fetch(`/api/v1/runs/${runId}/cancel`, { method: "POST" });
```

After any of these, SWR re-fetches `/runs/{runId}`; drawer re-renders.

### Drawer reconnect / persistence

Closing the drawer does NOT cancel the run. Re-opening re-attaches to the same SSE stream from the current event position via `?since=<last_event_id>` (relies on SP1's `/jobs/{id}/events` route honoring this — verify, add if missing).

---

## Testing

### Stack additions

- **Vitest** (new) + **@testing-library/react** + **@testing-library/user-event**
- **MSW (mock service worker)** for HTTP + SSE mocking
- **happy-dom** as the test environment

Configured in a new `web/vitest.config.ts` + `web/tests/setup.ts`.

### Test categories

| Layer | What's tested |
|---|---|
| Unit — pure components | `MessageBubble`, `ModuleProgressDot`, `UploadChip` render the right thing |
| Unit — `useStream` hook | Single-line events, multi-line events, partial chunks, malformed frames, cancel, HTTP errors |
| Unit — `useChat` hook | Optimistic user message, streamingText concatenation, SWR re-fetch on done |
| Integration — ChatPane | Type → stream → persist; file drop → upload chip |
| Integration — AutoDraftDrawer | Module dots advance; token meter updates; "Done" → download buttons |
| E2E (Playwright) | Deferred to follow-on |

### `useStream` critical tests

```typescript
describe("useStream", () => {
  test("parses single-line SSE event", async () => { /* ... */ });
  test("handles partial chunks across reads", async () => { /* ... */ });
  test("cancel aborts mid-stream", async () => { /* ... */ });
  test("malformed frame is silently skipped", async () => { /* ... */ });
  test("HTTP error surfaces in state.error", async () => { /* ... */ });
});
```

### MSW SSE helper

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

### Coverage targets

- `useStream`: **95%+**
- Other hooks: **80%+**
- Pure components: **70%+**
- Integration: covers each major flow's happy path

---

## Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Backend SSE bridge from SP1 doesn't survive chunked POST cleanly (FastAPI buffering) | Medium | Smoke-test as the first SP7 task: `curl --no-buffer` against the messages endpoint |
| `useStream` SSE parser miscounts `\n\n` boundaries straddling chunks | High | The 5 unit tests in the section above cover the edge cases; ship them first |
| `/threads/{tid}/state` SSE endpoint not yet implemented | Medium | First SP7 task includes the backend addition if missing |
| `/jobs/{id}/events?since=<id>` query param not honored for orchestrator runs | Medium | Verify; add the handler if missing |
| `(chat)` and `(inapp)` share `SidebarLayout` — sidebar items don't fit chat context | Low | Chat-specific `useSidebarSections()` variant |
| Synchronous PDF extraction (SP2 design) makes upload feel slow | Medium | Upload chip shows "Extracting text…" sub-state; expect 1-3s typical |
| User uploads 20 PDFs at once → serial extraction blocks | Low | Chip badges show queue position; UI doesn't block |
| Optimistic user-message ID collisions on rapid sends | Low | Client-side `nanoid` for optimistic IDs; reconcile on `done` |
| `useStream` re-renders per-token cause perf issues | Medium | Reducer-based state; flagged for profiling. If hot, batch with `requestIdleCallback` |
| 3-pane on tablet feels cramped | Medium | Below 1024px collapse to 1-pane + drawer toggles; phone polish is a follow-on |

---

## Success criteria

SP7 ships when **all** of these hold:

1. **Two-click chat start.** Wizard dashboard → "Try the new chat experience" → `/chat` → click project → 3-pane shell with Main thread.
2. **Send + stream.** User types → user msg appears immediately → assistant reply streams in token-by-token → page reload shows the full history persisted.
3. **Multi-thread.** User clicks "+ new thread" → fresh thread → right panel still shows the project's `context_store` (proves shared context).
4. **Upload + reflect.** Drag PDF → "Uploading…" chip → "✓ filename · N pages" → next message references the upload.
5. **Auto-draft launcher.** Click "Auto-draft" → modal → confirm → drawer slides in → dots advance → final state shows DOCX + PDF download buttons → clicking downloads from S3.
6. **Pause/resume.** Pause mid-run → drawer shows Paused → Resume → stream re-attaches → completes.
7. **No regression.** Wizard flow, engine subprocess, api/orchestrator tests — all unchanged and passing.
8. **Test coverage.** `useStream` 95%+; integration tests cover the happy paths above.
9. **Mobile-not-broken.** No horizontal scroll on tablet; 3-pane collapses to 1-pane below 1024px via media query.
10. **Wizard banner.** A banner on `/chat` directs users to the wizard for full thesis generation until SP3-SP6 ship.

## Explicit non-commitments

- Module-specific widgets (card grids, model builders, outline editors, section editors) — SP3-SP6.
- Markdown / LaTeX rendering inside chat. Plain text only.
- Dark mode toggle.
- Mobile-pretty layout.
- Keyboard shortcuts.
- Cross-thread message search.
- `/cite [doi]` chat commands.
- Real-time multi-user collab on the same thread.
- Frontend Sentry / error reporting.
- i18n.

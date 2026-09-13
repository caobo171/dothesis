# Thread Context Usage Indicator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the current thread context usage and remaining tokens before automatic compaction below the chat composer.

**Architecture:** Derive the compaction threshold from the same model-profile rule as deepagents, carry it on each runtime usage event, and persist the latest model-step input count separately from accumulated billing tokens. The frontend selects the live or latest persisted snapshot and renders an informational localized indicator.

**Tech Stack:** Python 3.13, LangChain/deepagents, FastAPI, SQLAlchemy/Alembic, Next.js 16, React 19, TypeScript, pytest, Vitest

**Spec:** `docs/superpowers/specs/2026-09-12-thread-context-usage-indicator-design.md`

## Global Constraints

- `total_tokens` remains accumulated billing usage; never reuse it as context occupancy.
- `context_tokens` is the latest model step's provider-reported input count.
- The automatic compaction trigger remains unchanged: 85% of a valid model profile or 170,000 tokens without one.
- The indicator is hidden when no valid usage snapshot exists.
- All API routes remain POST-only.

---

### Task 1: Context threshold and runtime metadata

**Files:**
- Create: `agent/context_usage.py`
- Create: `agent/tests/test_context_usage.py`
- Modify: `agent/runtime.py`
- Test: `agent/tests/test_build_agent_gates.py`

**Interfaces:**
- Produces: `compact_at_tokens(model: object) -> int`
- Produces: `register_agent_compact_threshold(agent: object, tokens: int) -> None`
- Produces: `agent_compact_at_tokens(agent: object) -> int`
- Extends runtime `usage` events with `compact_at_tokens: int`

- [ ] Write failing tests for a 1,000,000-token profile → 850,000, malformed/missing profiles → 170,000, and a registered agent threshold.
- [ ] Run `python3 -m pytest agent/tests/test_context_usage.py -q` and confirm the expected failures.
- [ ] Implement the pure threshold helper and an id-keyed registry for compiled agents.
- [ ] Register the threshold immediately after `create_deep_agent`, then include it on every emitted `usage` event.
- [ ] Run `python3 -m pytest agent/tests/test_context_usage.py agent/tests/test_build_agent_gates.py -q`.

### Task 2: Persist the latest context snapshot

**Files:**
- Create: `api/migrations/versions/20260912_message_context_usage.py`
- Modify: `api/app/models.py`
- Modify: `api/app/routers/chat_v3.py`
- Modify: `api/app/routers/chat.py`
- Test: `api/tests/test_chat_v3_intent.py`

**Interfaces:**
- Adds: `Message.context_tokens: int`
- Adds: `Message.compact_at_tokens: int`
- Extends SSE `done` with `context_tokens` and `compact_at_tokens`
- Extends `/threads/{id}/messages/list` rows with both fields

- [ ] Add failing tests proving two usage events sum for `total_tokens` while only the second input count becomes `context_tokens`.
- [ ] Run the focused API test and confirm it fails for the missing fields.
- [ ] Add the two non-null integer columns with server default `0`, chained after `20260912_toolrunproj01`.
- [ ] Track `_context_tokens` and `_compact_at_tokens` in `chat_v3`; overwrite them per usage event, persist them on assistant messages, and emit them in `done`.
- [ ] Return both fields from the message-list endpoint.
- [ ] Run the focused API tests and migration import checks.

### Task 3: Composer context indicator

**Files:**
- Create: `web/app/components/chat/ContextUsageIndicator.tsx`
- Create: `web/app/components/chat/ContextUsageIndicator.test.tsx`
- Modify: `web/app/components/chat/hooks/useChat.ts`
- Modify: `web/app/components/chat/ChatPane.tsx`
- Modify: `web/app/components/chat/ChatInput.tsx`
- Modify: `web/app/lib/i18n/messages/en.ts`
- Modify: `web/app/lib/i18n/messages/vi.ts`

**Interfaces:**
- Produces: `ContextUsageSnapshot = { contextTokens: number; compactAtTokens: number }`
- Produces: `formatContextTokens(value: number) -> string`
- `useChat` exposes `contextUsage: ContextUsageSnapshot | null`
- `ChatInput` accepts `contextUsage?: ContextUsageSnapshot | null`

- [ ] Write failing component tests for `Context 88K · compact in 82K · 52%`, threshold state, and hidden unavailable state.
- [ ] Write a failing hook test proving live `done` metadata overrides the newest persisted assistant snapshot.
- [ ] Run the focused Vitest files and confirm the expected failures.
- [ ] Implement compact token formatting and the localized indicator component.
- [ ] Derive the latest snapshot in `useChat`, preferring the latest valid `done` event over persisted assistant messages.
- [ ] Pass the snapshot through `ChatPane` to `ChatInput` and render it below composer actions.
- [ ] Run the focused Vitest files.

### Task 4: Documentation and verification

**Files:**
- Modify: `docs/DEEP_AGENT_AND_STREAMING.md`

**Interfaces:**
- Documents the distinction between billing tokens and context occupancy.

- [ ] Document deepagents automatic compaction, threshold fallback, persisted context snapshots, and composer display.
- [ ] Run backend focused tests and frontend focused tests.
- [ ] Run `npm run build` in `web/`.
- [ ] Run `git diff --check` and review the diff for unrelated changes.

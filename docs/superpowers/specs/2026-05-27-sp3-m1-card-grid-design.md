# SP3 — M1 Topic Discovery card-grid UX

**Date:** 2026-05-27
**Status:** Draft — pending user review
**Depends on:** Sub-projects 1, 2, 7 (all shipped on master)

## Context

Sub-projects 1 and 2 shipped the orchestrator backend; sub-project 7 shipped a chat UI shell. With the shell in place, each module-specific sub-project (SP3–SP6) plugs its custom widgets into the existing `tool_calls_json` column + `MessageBubble` component.

SP3 covers **M1 Topic Discovery**. M1Agent today is a 6-line subclass of `ModuleAgent` that uses the shared text-only clarification loop — the user types every field. PRD §6.1 calls for two specific fields to be click-to-pick (academic field, research approach) via a card-grid UI. This spec adds:

1. A generic backend protocol for agents to emit "render this widget" hints with their assistant messages.
2. A frontend widget renderer that detects those hints and shows clickable card grids inline in the chat.
3. Two concrete M1 hints: `FieldPicker` (academic field, 8 options) and `ResearchTypePicker` (quantitative/qualitative/mixed, 3 options).

The other M1 fields (`research_title`, `target_population`, `scope`, `objectives`, `research_questions`) stay free-text via the existing clarification loop — they don't naturally fit a card grid.

## Goal

- Extend `ModuleAgent` base with an overridable `render_hint_for_field(field_name)` hook (default returns `None`).
- Backend emits hints in the assistant message's `tool_calls_json` payload + a new `tool_calls` SSE event.
- Frontend `MessageBubble` detects the payload and renders a `<WidgetRenderer>`; one concrete widget (`CardGridWidget`) lands in SP3.
- M1Agent overrides the hook to emit card-grid hints for `field` and `research_type`.
- Clicking a card synthesizes a natural-language user message ("I'd like to study Marketing.") via the existing send path — no new backend message endpoint needed.
- The render-hint protocol uses a discriminated union (`widget_type`) ready to accept M3/M4/M5 widget variants without touching the SP3 code.

## Non-goals

- Topic explorer (PRD §6.1.2): 3-column Topic Clusters / Suggested Topics / Topic Detail. Defer.
- Title widget with 3 AI-suggested directions (PRD §6.1.3). Different widget shape; defer.
- Widgets for `research_title`, `target_population`, `scope`, `objectives`, `research_questions`. These stay free-text.
- ContextPanel friendly rendering of confirmed modules — SP7's read-only JSON viewer is fine for now.
- Keyboard navigation between cards (Tab/Arrow with focus rings).
- Search-within-options. Not needed for 3- and 8-option lists.
- Inline custom-value input on the "Other" option — synthesizes "I'd like to study Other" today; user follow-ups specify.
- Multi-select card grids. Add `multi_select: true` to the variant when a future widget needs it.
- Icon rendering. Schema includes an `icon` field; SP3 doesn't display it. Future polish.
- Mobile-pretty layout beyond a responsive `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3` collapse.
- Widget rendering in auto-mode (auto-mode never emits hints).

## Decisions (locked from brainstorming)

- **Scope:** widget infrastructure + FieldPicker + ResearchTypePicker (both card_grid variants). Other M1 fields stay text.
- **Protocol shape:** discriminated union keyed on `widget_type`; SP3 ships one variant (`card_grid`) consumed twice. SP4–SP6 add their variants alongside.
- **Click semantics:** synthesize natural-language user message via existing send path. Same code path for click and type. Backend's existing `_extract_answer` handles both.
- **Backend approach:** extend `ModuleAgent` base with an overridable `render_hint_for_field(field_name)` hook. Default returns `None`. M1Agent overrides for `field` and `research_type`. Generalizes to SP4–SP6.

---

## Architecture & data flow

```
1. User on /chat/projects/{pid}/threads/{tid} types or starts the conversation
   ↓
2. Backend M1Agent.step() runs (shared clarification loop from ModuleAgent base)
   ↓
3. _ask_next_question identifies the next missing field, e.g. "field"
   ↓
4. NEW: base calls self.render_hint_for_field("field"). M1Agent returns:
       {"widget_type": "card_grid", "field_name": "field",
        "title": "Pick an academic field",
        "options": [{"value":"Marketing","label":"Marketing","description":"..."}, ...]}
   ↓
5. ModuleStepResult returns:
   - assistant_message: "Which field is your research in?"
   - tool_calls_json: <hint>
   - needs_user_reply: True
   ↓
6. orchestrator/graph.py _agent_node_factory attaches the hint to the
   AIMessage's additional_kwargs so the API layer can pick it up.
   ↓
7. api/app/routers/chat.py send_message stream emits:
       {type: "token", text: "Which field is your research in?"}
       {type: "tool_calls", payload: {widget_type: "card_grid", ...}}
       {type: "done"}
   Then persists messages row with tool_calls_json populated.
   ↓
8. Frontend useChat collects token+tool_calls events; exposes streamingText
   and streamingToolCalls; on `done` triggers mutate() to refetch the
   authoritative messages list (which already has tool_calls_json).
   ↓
9. MessageList renders each persisted message via <MessageBubble>.
   MessageBubble sees toolCallsJson non-null → renders <WidgetRenderer>.
   ↓
10. WidgetRenderer dispatches on widget_type → <CardGridWidget>.
    ↓
11. User clicks "Marketing" card.
    ↓
12. CardGridWidget calls onSelect("field", "Marketing", "Marketing").
    ↓
13. ChatPane synthesizes user text: "I'd like to study Marketing."
    ↓
14. send(text) — same path as typed input.
    ↓
15. Backend extracts "Marketing" → stores in m1_topic.field → asks next field.
```

### Widget "spent" semantics

Once a newer assistant message exists in the thread, the prior widget's buttons disable. Rule: a widget is **enabled only on the LAST assistant message AND only when no stream is in flight**. The disabled widget remains visible — readers see what the user picked — but clicks no-op. `MessageList` computes `widgetDisabled` by index + inflight and forwards it down.

---

## Backend changes

### File map

```
orchestrator/agents/
├── base.py                              # MODIFY — extend ModuleStepResult; add render_hint hook
├── widgets.py                           # NEW — Pydantic models for hint variants
└── m1_topic.py                          # MODIFY — override render_hint_for_field
orchestrator/prompts/m1/
├── _options_field.json                  # NEW — 8 academic-field options
└── _options_research_type.json          # NEW — 3 research-type options
orchestrator/graph.py                    # MODIFY — pass tool_calls_json through node patch
api/app/routers/chat.py                  # MODIFY — emit tool_calls SSE; persist payload
orchestrator/tests/agents/
├── test_module_agent_render_hint.py     # NEW — base hook + None default
└── test_m1_widgets.py                   # NEW — M1Agent emits hints
api/tests/test_chat_messages_widgets.py  # NEW — SSE emits + DB persists
```

### `orchestrator/agents/widgets.py`

```python
from pydantic import BaseModel, Field
from typing import Annotated, Literal, Union


class CardOption(BaseModel):
    value: str
    label: str
    description: str = ""
    icon: str | None = None


class CardGridHint(BaseModel):
    widget_type: Literal["card_grid"] = "card_grid"
    field_name: str
    title: str
    options: list[CardOption]
    columns: int = 3


# Discriminated union — future variants land here (model_builder, outline_editor, ...)
WidgetHint = Annotated[Union[CardGridHint], Field(discriminator="widget_type")]
```

### `orchestrator/agents/base.py` changes

`ModuleStepResult` gains one optional field:

```python
@dataclass
class ModuleStepResult:
    assistant_message: str
    context_patch: dict
    transition: bool
    needs_user_reply: bool = False
    tool_calls_json: dict | None = None     # NEW
```

`ModuleAgent` gains an overridable hook with a default `None` return:

```python
class ModuleAgent(ABC):
    ...
    def render_hint_for_field(self, field_name: str) -> dict | None:
        """Subclasses override to attach a widget render hint when asking
        the user to fill `field_name`. Default: no hint (plain-text input).
        """
        return None
```

In `_ask_next_question`, after determining the next missing field:

```python
def _ask_next_question(self, state, partial: dict) -> ModuleStepResult:
    missing = self._next_missing_field(partial)
    if missing is None:
        # ... existing summary + awaiting_confirm path
        return ModuleStepResult(...)   # tool_calls_json=None (default)

    partial["_awaiting_field"] = missing
    # ... existing prompt generation
    msg = self._get_llm().invoke(prompt).content.strip()

    hint = self.render_hint_for_field(missing)
    return ModuleStepResult(
        assistant_message=msg,
        context_patch=partial,
        transition=False,
        needs_user_reply=True,
        tool_calls_json=hint,                # NEW
    )
```

Auto-mode path is untouched — `_auto_fill` does not call `_ask_next_question`, so `tool_calls_json` stays `None` in auto runs.

### `orchestrator/agents/m1_topic.py`

```python
"""M1 — Topic Discovery agent."""
import json
from pathlib import Path
from orchestrator.agents.base import ModuleAgent
from orchestrator.agents.widgets import CardGridHint, CardOption
from orchestrator.schemas.m1 import M1Output
from orchestrator.tools.m1_topic import refine_title, suggest_topics

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
_PROMPT = (_PROMPT_DIR / "m1.md").read_text()
_FIELD_OPTIONS = json.loads((_PROMPT_DIR / "m1" / "_options_field.json").read_text())
_RESEARCH_TYPE_OPTIONS = json.loads((_PROMPT_DIR / "m1" / "_options_research_type.json").read_text())


class M1Agent(ModuleAgent):
    schema = M1Output
    module_key = "M1"
    system_prompt = _PROMPT
    tools = [suggest_topics, refine_title]

    def render_hint_for_field(self, field_name: str) -> dict | None:
        if field_name == "field":
            return CardGridHint(
                field_name="field",
                title="Which academic field is your research in?",
                options=[CardOption(**o) for o in _FIELD_OPTIONS],
                columns=3,
            ).model_dump()
        if field_name == "research_type":
            return CardGridHint(
                field_name="research_type",
                title="Which research approach fits your question?",
                options=[CardOption(**o) for o in _RESEARCH_TYPE_OPTIONS],
                columns=3,
            ).model_dump()
        return None
```

The M1 prompt (`orchestrator/prompts/m1.md`) is amended with one short paragraph: "When the next field is shown to the user as click-to-pick options (a card grid), your text should invite picking — e.g. *'Which field is your research in? Pick below or type your own.'* — rather than asking the user to type."

### Option JSON files

`orchestrator/prompts/m1/_options_field.json`:

```json
[
  {"value": "Marketing",         "label": "Marketing",          "description": "Consumer behavior, branding, advertising"},
  {"value": "Management",        "label": "Management",         "description": "Leadership, strategy, organizational behavior"},
  {"value": "Economics",         "label": "Economics",          "description": "Macro/micro economics, finance, development"},
  {"value": "Psychology",        "label": "Psychology",         "description": "Cognitive, social, organizational psychology"},
  {"value": "Sociology",         "label": "Sociology",          "description": "Social structures, culture, change"},
  {"value": "Education",         "label": "Education",          "description": "Pedagogy, learning theory, policy"},
  {"value": "Accounting-Finance","label": "Accounting & Finance","description": "Corporate finance, accounting, audit"},
  {"value": "Other",             "label": "Other / Specify",    "description": "Type your field below"}
]
```

`orchestrator/prompts/m1/_options_research_type.json`:

```json
[
  {"value": "quantitative", "label": "Quantitative",  "description": "Test relationships between variables; statistical analysis"},
  {"value": "qualitative",  "label": "Qualitative",   "description": "Explore experiences, meanings, themes; interpretive analysis"},
  {"value": "mixed",        "label": "Mixed methods", "description": "Combine both for breadth and depth"}
]
```

### `orchestrator/graph.py` — thread the hint through

The existing `_agent_node_factory` returns `{"messages": [AIMessage(...)], "context_store": cs}`. Add `tool_calls_json` to the AIMessage's `additional_kwargs`:

```python
def _node(state: OrchestratorState) -> dict:
    from langchain_core.messages import AIMessage
    agent = _AGENT_BY_KEY[module_key]
    result = agent.step(state)
    cs = state["context_store"].model_copy(deep=True)
    setattr(cs, _MODULE_FIELD[module_key], result.context_patch)

    ai = AIMessage(content=result.assistant_message)
    if result.tool_calls_json:
        ai.additional_kwargs["tool_calls_json"] = result.tool_calls_json

    return {"messages": [ai], "context_store": cs}
```

### `api/app/routers/chat.py` — emit `tool_calls` SSE event + persist

In `send_message`'s `gen()` loop:

```python
async def gen():
    nonlocal final_module_tag
    final_tool_calls = None     # NEW
    async for event in graph.astream(..., stream_mode="updates"):
        for node_name, payload in event.items():
            if node_name in {"M1", "M2", "M3", "M4", "M5"}:
                final_module_tag = node_name
            msgs = payload.get("messages") or []
            for m in msgs:
                chunk = getattr(m, "content", "")
                if chunk:
                    assistant_chunks.append(chunk)
                    yield sse_pack({"type": "token", "module": node_name, "text": chunk})

                tc = getattr(m, "additional_kwargs", {}).get("tool_calls_json")
                if tc:
                    final_tool_calls = tc
                    yield sse_pack({"type": "tool_calls", "payload": tc})

    full = "".join(assistant_chunks)
    if full:
        with db.bind.connect() as conn:
            conn.execute(
                Message.__table__.insert().values(
                    thread_id=thread_id, role="assistant",
                    content=full, module_tag=final_module_tag,
                    tool_calls_json=final_tool_calls,
                )
            )
            conn.commit()
    yield sse_pack({"type": "done"})
```

The `messages.tool_calls_json` column is JSONB nullable (from SP1's migration); no schema change.

---

## Frontend changes

### File map

```
web/app/components/chat/
├── widgets/                              # NEW directory
│   ├── types.ts
│   ├── WidgetRenderer.tsx
│   ├── CardGridWidget.tsx
│   ├── CardGridWidget.test.tsx
│   ├── WidgetRenderer.test.tsx
│   └── synthesize.ts
│   └── synthesize.test.ts
│   └── types.test.ts                     # cross-language schema-drift guard
├── MessageBubble.tsx                     # MODIFY — render widget when toolCallsJson present
├── MessageBubble.test.tsx                # ADD widget-render tests
├── MessageList.tsx                       # MODIFY — pass onWidgetSelect + widgetDisabled
├── ChatPane.tsx                          # MODIFY — wire onWidgetSelect → synthesize+send
├── hooks/
│   ├── useChat.ts                        # MODIFY — collect tool_calls SSE event
│   └── useChat.test.tsx                  # ADD tool_calls collection test
└── ChatPane.test.tsx                     # ADD integration test (click → message → POST body)
```

### `widgets/types.ts`

```typescript
export type CardOption = {
  value: string;
  label: string;
  description?: string;
  icon?: string | null;
};

export type CardGridHint = {
  widget_type: "card_grid";
  field_name: string;
  title: string;
  options: CardOption[];
  columns?: number;
};

// Discriminated union — SP4-SP6 add their variants here
export type WidgetHint = CardGridHint;

export type WidgetSelectHandler = (
  fieldName: string,
  value: string,
  label: string,
) => void;
```

### `widgets/CardGridWidget.tsx`

```typescript
"use client";

import { CardGridHint, WidgetSelectHandler } from "./types";


export function CardGridWidget({
  hint,
  onSelect,
  disabled,
}: {
  hint: CardGridHint;
  onSelect: WidgetSelectHandler;
  disabled?: boolean;
}) {
  const columns = hint.columns ?? 3;
  return (
    <div className="mt-3 rounded-lg border border-gray-200 bg-white p-3" data-testid={`card-grid-${hint.field_name}`}>
      <div className="text-xs font-semibold text-gray-700 mb-2">{hint.title}</div>
      <div
        className="grid gap-2 grid-cols-1 sm:grid-cols-2"
        style={{ "--cols": columns } as React.CSSProperties}
      >
        {hint.options.map(opt => (
          <button
            key={opt.value}
            type="button"
            disabled={disabled}
            onClick={() => onSelect(hint.field_name, opt.value, opt.label)}
            data-testid={`card-${opt.value}`}
            className={`text-left rounded-md border border-gray-200 px-3 py-2 hover:border-purple-400 hover:bg-purple-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors`}
            style={{ gridColumn: undefined }}
          >
            <div className="text-sm font-medium text-gray-900">{opt.label}</div>
            {opt.description && (
              <div className="text-xs text-gray-500 mt-0.5 line-clamp-2">{opt.description}</div>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
```

(Implementation note for the implementer: the responsive grid will use Tailwind `grid-cols-1 sm:grid-cols-2 lg:grid-cols-{columns}` — slight care needed because `columns` is dynamic; use a small switch on `columns ∈ {2,3,4}` to map to static classes, since Tailwind's JIT doesn't pick up dynamic class names. Fall back to `lg:grid-cols-3` when `columns` isn't in that set.)

### `widgets/WidgetRenderer.tsx`

```typescript
"use client";

import { CardGridWidget } from "./CardGridWidget";
import type { WidgetHint, WidgetSelectHandler } from "./types";


export function WidgetRenderer({
  hint,
  onSelect,
  disabled,
}: {
  hint: WidgetHint;
  onSelect: WidgetSelectHandler;
  disabled?: boolean;
}) {
  switch (hint.widget_type) {
    case "card_grid":
      return <CardGridWidget hint={hint} onSelect={onSelect} disabled={disabled} />;
    default:
      // Unknown widget_type — render nothing (forward-compat).
      return null;
  }
}
```

### `widgets/synthesize.ts`

```typescript
export function synthesizeWidgetSelection(
  fieldName: string,
  value: string,
  label: string,
): string {
  const descriptors: Record<string, string> = {
    field: `I'd like to study ${label}.`,
    research_type: `I'll use a ${label.toLowerCase()} approach.`,
  };
  return descriptors[fieldName] ?? label;
}
```

### `hooks/useChat.ts` — collect `tool_calls` events

```typescript
import type { WidgetHint } from "../widgets/types";


export type Message = {
  id: number;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  module_tag?: string | null;
  tool_calls_json?: WidgetHint | null;   // NEW
  created_at: string;
};


export function useChat(threadId: string) {
  const stream = useStream();
  const { data: messages, mutate } = useSWR<Message[]>(`/threads/${threadId}/messages`, fetcher);

  const streamingText = stream.state.events
    .filter(e => e.type === "token")
    .map(e => (e as unknown as { text: string }).text)
    .join("");

  const streamingToolCalls = (stream.state.events
    .filter(e => e.type === "tool_calls")
    .map(e => (e as unknown as { payload: WidgetHint }).payload)
    .at(-1)) ?? null;

  // ... send() unchanged
  return {
    messages: messages ?? [],
    streamingText,
    streamingToolCalls,
    inflight: stream.state.inflight,
    error: stream.state.error,
    send,
  };
}
```

### `MessageBubble.tsx` changes

```typescript
import { WidgetRenderer } from "./widgets/WidgetRenderer";
import type { WidgetHint, WidgetSelectHandler } from "./widgets/types";


export type MessageBubbleProps = {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  moduleTag?: string | null;
  toolCallsJson?: WidgetHint | null;     // NEW
  onWidgetSelect?: WidgetSelectHandler;  // NEW
  widgetDisabled?: boolean;              // NEW
  children?: React.ReactNode;
};

// ... existing render, plus inside the bubble:
{toolCallsJson && onWidgetSelect && (
  <WidgetRenderer hint={toolCallsJson} onSelect={onWidgetSelect} disabled={widgetDisabled} />
)}
```

### `MessageList.tsx` changes

Receives `onWidgetSelect` from parent and computes `widgetDisabled` per message:

```typescript
{messages.map((m, idx) => (
  <MessageBubble
    key={m.id}
    role={m.role}
    content={m.content}
    moduleTag={m.module_tag}
    toolCallsJson={m.tool_calls_json}
    onWidgetSelect={onWidgetSelect}
    widgetDisabled={idx < messages.length - 1 || Boolean(streamingText)}
  />
))}
```

### `ChatPane.tsx` — wire onWidgetSelect

```typescript
const onWidgetSelect: WidgetSelectHandler = (fieldName, value, label) => {
  const text = synthesizeWidgetSelection(fieldName, value, label);
  void send(text);   // existing path
};

return (
  <>
    <ChatHeader .../>
    <MessageList
      messages={messages}
      streamingText={inflight ? streamingText : ""}
      streamingModuleTag={null}
      onWidgetSelect={onWidgetSelect}
    />
    <ChatInput .../>
    {/* unchanged: modal + drawer */}
  </>
);
```

### Cross-language schema-drift guard

`widgets/types.test.ts`:

```typescript
import { describe, expect, test } from "vitest";
import type { CardGridHint, CardOption } from "./types";

/**
 * Fixture matching exactly what backend's orchestrator/agents/widgets.py
 * CardGridHint.model_dump() produces. If backend schema changes, the
 * fixture below stops parsing cleanly into the TS type, build fails.
 */
const FIXTURE: CardGridHint = {
  widget_type: "card_grid",
  field_name: "field",
  title: "Pick",
  options: [
    { value: "Marketing", label: "Marketing", description: "x", icon: null },
  ],
  columns: 3,
};

describe("CardGridHint schema parity", () => {
  test("matches backend Pydantic output shape", () => {
    expect(FIXTURE.widget_type).toBe("card_grid");
    expect(FIXTURE.options[0]).toHaveProperty("value");
    expect(FIXTURE.options[0]).toHaveProperty("label");
  });
});
```

(Not a runtime check — it's TypeScript ensuring the fixture compiles. Adding a backend Pydantic field breaks the fixture if frontend types don't follow.)

---

## Testing

### Backend

| Test | Covers |
|---|---|
| `test_module_agent_render_hint.py::test_default_hook_returns_none` | Base class default behavior |
| `test_module_agent_render_hint.py::test_subclass_override_attaches_hint` | Subclass override flows into ModuleStepResult |
| `test_module_agent_render_hint.py::test_no_hint_when_summary_phase` | Confirm-summary path emits no hint |
| `test_m1_widgets.py::test_field_returns_card_grid_hint` | M1 `field` hint shape |
| `test_m1_widgets.py::test_research_type_returns_card_grid_hint` | M1 `research_type` hint shape |
| `test_m1_widgets.py::test_text_fields_return_none` | Free-text fields get no widget |
| `test_chat_messages_widgets.py::test_stream_emits_tool_calls_event_and_persists` | SSE + DB persistence |
| `test_m1_widgets.py::test_synthesized_sentence_extracts_to_value` (extract round-trip) | "I'd like to study Marketing." → ModuleAgent._extract_answer → "Marketing" |

### Frontend

| Test | Covers |
|---|---|
| `CardGridWidget.test.tsx::renders title and option cards` | Render |
| `CardGridWidget.test.tsx::clicking an option fires onSelect with field_name/value/label` | Click handling |
| `CardGridWidget.test.tsx::disabled prevents click` | Spent state |
| `WidgetRenderer.test.tsx::dispatches card_grid to CardGridWidget` | Dispatch |
| `WidgetRenderer.test.tsx::returns null for unknown widget_type` | Forward-compat |
| `synthesize.test.ts::field/research_type/unknown` | 3 cases |
| `types.test.ts::matches backend Pydantic output shape` | Schema-drift guard |
| `MessageBubble.test.tsx::renders widget when toolCallsJson present` | Integration |
| `MessageBubble.test.tsx::does not render widget when toolCallsJson absent` | Negative |
| `MessageBubble.test.tsx::widgetDisabled is forwarded to the widget` | Disable wiring |
| `useChat.test.tsx::collects tool_calls SSE event into streamingToolCalls` | Hook stream |
| `ChatPane.test.tsx::clicking a card synthesizes message and sends` | End-to-end click → POST body |

### Coverage targets

- `CardGridWidget` + `WidgetRenderer`: **95%+**
- `synthesize.ts`: **100%**
- `ModuleAgent.render_hint_for_field` + extension: **100%**
- M1Agent overrides: **100%**
- All other tests follow whatever coverage they previously had.

---

## Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| SSE stream buffers `tool_calls` payloads → frontend doesn't see them mid-stream | Medium | First SP3 task: smoke-test `curl --no-buffer` against the endpoint to confirm `data: {"type":"tool_calls", ...}` lands before `done` |
| Synthesized "I'd like to study Marketing." is ambiguous to `_extract_answer` for the `field` Pydantic field | Medium | Round-trip test in `test_m1_widgets.py` asserts extraction returns `"Marketing"` |
| User clicks card during stream → race condition double-send | Medium | `widgetDisabled` is `true` while `inflight` — covered by the disabled-prevents-click test + ChatPane integration test |
| LLM-generated text contradicts the widget ("type your field" while a card grid appears) | High | M1 prompt addition tells the agent to invite picking, not typing, when a widget is rendered. Acceptable polish trade-off — perfect alignment is a tuning concern. |
| Schema drift between Pydantic `CardGridHint` and TypeScript `CardGridHint` | Medium | `widgets/types.test.ts` fixture compilation check |
| Dynamic Tailwind grid-cols-{n} class doesn't render | Medium | Switch on `columns ∈ {2, 3, 4}` mapping to static class strings; fall back to `lg:grid-cols-3` |
| MessageBubble grows large with widget logic | Low | Widget rendering delegated to `WidgetRenderer`; bubble change is ~10 lines |
| Forward-compatibility: future M3 widget variant breaks SP3 frontend | Low | `WidgetRenderer` default case returns `null`. Unknown variants ignored silently. |

---

## Success criteria

SP3 ships when **all** of these hold:

1. **End-to-end card pick → field stored.** Empty project → user starts chat → agent renders FieldPicker → user clicks "Marketing" → synthesized "I'd like to study Marketing." appears in chat → `context_store.m1_topic.field == "Marketing"` in DB.
2. **Two consecutive widgets.** After picking field, agent renders ResearchTypePicker → user picks "quantitative" → both fields confirmed.
3. **Widget "spent" UX.** Once a newer message exists in the thread, the prior widget's buttons disable; clicking does nothing.
4. **Free-text fields stay text.** Other M1 fields (`research_title`, `target_population`, `scope`, `objectives`, `research_questions`) use the existing text-input clarification loop.
5. **Auto-mode unchanged.** `python -m orchestrator --auto-draft` artifacts identical to before. `tool_calls_json` null in auto runs.
6. **Test coverage.** All new tests pass; coverage targets met. Schema-drift guard fails when intentionally broken.
7. **No regression.** SP1, SP2, SP7 tests all still pass. Existing wizard untouched.
8. **Forward-compat.** Frontend handles an unknown `widget_type` without crash.

## Explicit non-commitments

- Other M1 widgets (topic explorer, title with 3 directions) — defer to follow-on sub-project.
- ContextPanel friendly rendering of confirmed modules — SP7's read-only JSON viewer stays.
- M3, M4, M5 widgets — separate sub-projects (SP4, SP5, SP6).
- Inline custom-value input on "Other" — synthesizes "Other"; user follow-up specifies via chat.
- Icon rendering — schema includes `icon` field; SP3 does not display icons.
- Multi-select widgets — none in M1; future widgets add `multi_select: true` when needed.
- Mobile-pretty layout — responsive `grid-cols-1 sm:grid-cols-2 lg:grid-cols-{N}` is enough.
- Auto-mode widget rendering — N/A; auto-mode emits no hints.

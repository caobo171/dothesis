# Guided Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evolve the orchestrator from a linear M1→M5 pipeline into a guided process over an artifact dependency graph — enter at any step, assess existing work, backfill prerequisites, drive to done with lowest effort — *without* a framework migration.

**Architecture:** Keep LangGraph. Add an artifact DAG + definition-of-done validators, an intake/triage node, a planner that replaces `next_unconfirmed_module`, a conversation-resilience dispatcher, and progressive autonomy. See the design docs: [`docs/design/guided-agent-architecture.md`](../../design/guided-agent-architecture.md) (EN) and [`.vi.md`](../../design/guided-agent-architecture.vi.md) (VI).

**Tech Stack:** Python 3.13, LangGraph 1.x (Postgres checkpointer), FastAPI, Pydantic v2, pytest. LLM = Gemini 2.5 Flash via `langchain-google-genai`. Frontend Next.js (not touched until later phases).

---

## How to read this plan

This is a **7-phase roadmap** matching the migration plan in the design doc. The phases are largely **independent subsystems**, so per the writing-plans convention each phase that touches code gets its own fully-bite-sized plan **authored at the moment we start it** — because the later phases' exact code depends on earlier phases' outcomes (and Phase 3's backfill logic is research-novel and uncited, so writing complete code for it now would be fabrication).

**Phase A (conversation resilience) is fully bite-sized below and is what we implement first** — it ships on the *current* graph, is low-risk, and fixes a live UX dead-end. The remaining phases give goal / dependencies / files / task list / acceptance criteria, enough to sequence and estimate, with a "detailed plan authored here" hook.

### Execution sequence (dependency-ordered)

| Order | Phase | Depends on | Ships independently? | Risk |
|-------|-------|-----------|----------------------|------|
| **1st** | **A. Conversation resilience** (§3.6/3.7) | nothing — current graph | ✅ yes | low |
| 2nd | 0. Native `interrupt()` | nothing | ✅ yes | low |
| 3rd | 1. Artifact DAG + DoD | nothing (additive) | ✅ yes (invisible) | low |
| 4th | 2. Import + start-at endpoints | Phase 1 | ✅ yes | medium |
| 5th | 3. 🔬 Backfill vertical slice | Phases 1, 2 | partial | **high (novel)** |
| 6th | 4. Intake / triage subgraph | Phases 1, 3 | ✅ yes | medium |
| 7th | 5. Planner replaces `next_unconfirmed_module` | Phases 1, 3 | ✅ yes | medium |
| 8th | 7. Stale flags + autonomy slider + memory | Phases 1, 5 | ✅ yes | medium |

Each phase ends green (all tests pass) and is committed before the next starts.

---

# ▶ Phase A — Conversation resilience (IMPLEMENT FIRST)

**Goal:** When the user goes off-script mid-flow (random question, process/meta question, or venting), the agent answers like a human and steers back to the pending field — instead of silently re-asking. Plus: feed the intent classifier a window of recent turns so short replies ("yes", "the second one") resolve correctly.

**Why first:** independent of the DAG, ships on the current graph, fixes a live dead-end (`base.py` currently handles `off_topic` by *ignoring the reply and re-asking*).

**Files:**
- Modify: `orchestrator/agents/base.py` (the `ModuleAgent` clarification loop)
- Test: `orchestrator/tests/test_agent_base.py`

**Test harness note:** `_ToyAgent` (in the test file) has schema `_ToyOutput{title, answer}` and **no** `card_fields`/`list_fields`, so `render_hint_for_field` returns `None` — meaning `step()` makes exactly the LLM calls we mock, no surprise card-generation call.

**Run all tests for this phase with:**
```bash
set -a && source .env && set +a && api/.venv/bin/python -m pytest orchestrator/tests/test_agent_base.py -q
```

---

### Task A1: `_recent_dialogue()` — windowed transcript helper

**Files:**
- Modify: `orchestrator/agents/base.py`
- Test: `orchestrator/tests/test_agent_base.py`

- [ ] **Step 1: Write the failing test**

```python
def test_recent_dialogue_windows_last_turns_and_labels_roles():
    agent = _ToyAgent()
    msgs = [
        HumanMessage(content="m1"), AIMessage(content="a1"),
        HumanMessage(content="m2"), AIMessage(content="a2"),
        HumanMessage(content="m3"),
    ]
    transcript = agent._recent_dialogue(msgs, max_msgs=3)
    # Only the last 3 messages, oldest-first, labelled by role.
    assert "m1" not in transcript
    assert transcript == "User: m2\nAssistant: a2\nUser: m3"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `... pytest orchestrator/tests/test_agent_base.py::test_recent_dialogue_windows_last_turns_and_labels_roles -q`
Expected: FAIL — `AttributeError: '_ToyAgent' object has no attribute '_recent_dialogue'`

- [ ] **Step 3: Write minimal implementation**

Add to `ModuleAgent` in `base.py` (near the other helpers):

```python
def _recent_dialogue(self, messages: list[BaseMessage], max_msgs: int = 8) -> str:
    """Compact transcript of the last few turns, for reference resolution.

    The conversation layer (intent classifier, concierge) needs recent context —
    "the second one", "yes", "like I said" are meaningless from one message. We
    pass a WINDOW (last `max_msgs`), never the whole thread, to cap cost and
    avoid the LLM latching onto stale instructions. The AUTHORITATIVE task state
    still comes from the structured partial, not from this transcript.
    """
    recent = [m for m in messages if isinstance(m, (HumanMessage, AIMessage))][-max_msgs:]
    lines = []
    for m in recent:
        role = "User" if isinstance(m, HumanMessage) else "Assistant"
        lines.append(f"{role}: {text_of(m)}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: same as Step 2. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/agents/base.py orchestrator/tests/test_agent_base.py
git commit -m "feat(orchestrator): add _recent_dialogue windowed-transcript helper"
```

---

### Task A2: classifier recognizes `meta` and `frustration`

**Files:**
- Modify: `orchestrator/agents/base.py` (`_classify_user_intent`)
- Test: `orchestrator/tests/test_agent_base.py`

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.parametrize("intent_value", ["meta", "frustration"])
def test_classify_recognizes_meta_and_frustration(monkeypatch, intent_value):
    agent = _ToyAgent()
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = AIMessage(
        content=f'{{"intent": "{intent_value}", "value": null}}'
    )
    monkeypatch.setattr(_ToyAgent, "_get_llm", lambda self: fake_llm)

    state = _state([HumanMessage(content="how long will this take?")])
    out = agent._classify_user_intent(state, "title", {"answer": "Y"})
    assert out["intent"] == intent_value
```

- [ ] **Step 2: Run test to verify it fails**

Run: `... pytest orchestrator/tests/test_agent_base.py::test_classify_recognizes_meta_and_frustration -q`
Expected: FAIL — current allow-list is `{answer, clarification, delegation, navigation, off_topic}`, so `meta`/`frustration` fall through to the `{"intent": "answer", "value": None}` fallback; assert fails.

- [ ] **Step 3: Write minimal implementation**

In `_classify_user_intent`, (a) add the two intents to the validation set, and (b) describe them in the prompt. Change the allow-list check:

```python
            if intent in {"answer", "clarification", "delegation",
                          "navigation", "off_topic", "meta", "frustration"}:
                return {"intent": intent, "value": data.get("value")}
```

And add to the intent-options text in the prompt (after the `off_topic` bullet):

```python
            f'- "meta": the user is asking about the PROCESS itself — how long\n'
            f"  this will take, what you're doing, how many steps remain, whether\n"
            f"  they can save and come back.\n"
            f'- "frustration": the user is venting, stressed, anxious, or\n'
            f"  expressing doubt/overwhelm rather than answering the question.\n"
```

- [ ] **Step 4: Run test to verify it passes**

Run: same as Step 2. Expected: PASS (both params).

- [ ] **Step 5: Commit**

```bash
git add orchestrator/agents/base.py orchestrator/tests/test_agent_base.py
git commit -m "feat(orchestrator): classify meta and frustration intents"
```

---

### Task A3: `_answer_and_anchor()` — the concierge reply

**Files:**
- Modify: `orchestrator/agents/base.py`
- Test: `orchestrator/tests/test_agent_base.py`

- [ ] **Step 1: Write the failing test**

```python
def test_answer_and_anchor_returns_concierge_message(monkeypatch):
    agent = _ToyAgent()
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = AIMessage(
        content="Good question! I'll handle citations later. "
                "Back to it — what's your title?"
    )
    monkeypatch.setattr(_ToyAgent, "_get_llm", lambda self: fake_llm)

    state = _state([HumanMessage(content="does APA need a DOI?")])
    msg = agent._answer_and_anchor(state, "off_topic", "title", {"answer": "Y"})
    assert "title" in msg.lower()
    # The intent guidance must reach the LLM prompt.
    prompt = fake_llm.invoke.call_args[0][0]
    assert "title" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `... pytest orchestrator/tests/test_agent_base.py::test_answer_and_anchor_returns_concierge_message -q`
Expected: FAIL — `AttributeError: ... '_answer_and_anchor'`.

- [ ] **Step 3: Write minimal implementation**

Add to `ModuleAgent`:

```python
def _answer_and_anchor(self, state, intent: str, field_name: str, partial: dict) -> str:
    """Concierge reply: address the user's digression, then steer back.

    Handles off_topic / meta / frustration the human way — never ignore, never
    just re-ask. One LLM call produces: a brief acknowledgement/answer suited to
    the intent, a bridge, and a re-ask of the pending field. The caller re-attaches
    the field's widget so returning is a one-click action.
    """
    desc = self._field_description(field_name)
    context = json.dumps(
        {k: v for k, v in partial.items() if not k.startswith("_")},
        default=str, ensure_ascii=False,
    )
    recent = self._recent_dialogue(state.get("messages") or [])
    guidance = {
        "off_topic": (
            "The user asked something off-topic. Answer it in ONE short sentence "
            "(or say you'll handle it automatically later if it's a downstream "
            "concern), then gently bring them back."
        ),
        "meta": (
            "The user asked a process/meta question (how long, what are you doing, "
            "how many steps left). Answer briefly and reassuringly from the "
            "context, then bring them back."
        ),
        "frustration": (
            "The user sounds frustrated or anxious. Reply with brief, genuine "
            "empathy and remind them you can do the heavy lifting (offer to draft "
            "or pick sensible defaults so it's low-effort), then gently bring "
            "them back."
        ),
    }.get(intent, "Acknowledge briefly, then bring them back to the question.")
    prompt = (
        f"{self.system_prompt}\n\n"
        f"You are guiding a student through a research-project intake and are "
        f"currently waiting for them to provide the field '{field_name}' "
        f"({desc}).\n"
        f"Recent conversation:\n{recent}\n\n"
        f"Already-filled context:\n{context}\n\n"
        f"{guidance}\n\n"
        f"Write a SHORT, warm, human reply (2-3 sentences max). End by re-asking "
        f"for '{field_name}' in one friendly line. Match the user's language "
        f"(English or Vietnamese). Prose only — no markdown headers or bullets."
    )
    return self._get_llm().invoke(prompt).content.strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: same as Step 2. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/agents/base.py orchestrator/tests/test_agent_base.py
git commit -m "feat(orchestrator): add _answer_and_anchor concierge reply"
```

---

### Task A4: route off_topic / meta / frustration through answer-then-anchor in `step()`

**Files:**
- Modify: `orchestrator/agents/base.py` (`step()`, the `awaiting_field` block)
- Test: `orchestrator/tests/test_agent_base.py`

- [ ] **Step 1: Write the failing test**

```python
def test_off_topic_answers_then_reasks_same_field(monkeypatch):
    """A digression while awaiting a field → concierge reply + re-ask the SAME
    field (not advance, not silently re-ask)."""
    agent = _ToyAgent()
    fake_llm = MagicMock()
    fake_llm.invoke.side_effect = [
        AIMessage(content='{"intent": "off_topic", "value": null}'),     # classify
        AIMessage(content="Ha, good one. Anyway — what's your title?"),   # concierge
    ]
    monkeypatch.setattr(_ToyAgent, "_get_llm", lambda self: fake_llm)

    state = _state(
        [AIMessage(content="What is the title?"),
         HumanMessage(content="btw what's the weather?")],
        partial={"_awaiting_field": "title"},
    )
    result = agent.step(state)
    assert result.transition is False
    assert result.needs_user_reply is True
    assert "title" in result.assistant_message.lower()
    # The field is still pending so the next turn resumes correctly.
    assert result.context_patch.get("_awaiting_field") == "title"
    # And it did NOT get stored as the field value.
    assert "title" not in {k: v for k, v in result.context_patch.items()
                           if k == "title"} or result.context_patch.get("title") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `... pytest orchestrator/tests/test_agent_base.py::test_off_topic_answers_then_reasks_same_field -q`
Expected: FAIL — currently `off_topic` falls through to `_ask_next_question`, which re-asks via a freshly generated prompt (no concierge call); the `side_effect` list won't match the call sequence and/or `assistant_message` won't be the concierge text. (Likely `StopIteration`/assertion failure.)

- [ ] **Step 3: Write minimal implementation**

In `step()`, inside `if awaiting_field:`, right after computing `intent`/`value` and before the `clarification` branch (or grouped with it), add:

```python
            if intent in {"off_topic", "meta", "frustration"}:
                # Concierge: address the digression like a human, then steer back
                # to the same field. Re-attach the field's widget so returning is
                # one click. The field stays pending (we did NOT capture a value).
                message = self._answer_and_anchor(state, intent, awaiting_field, partial)
                partial["_awaiting_field"] = awaiting_field
                return ModuleStepResult(
                    assistant_message=message,
                    context_patch=partial,
                    transition=False,
                    needs_user_reply=True,
                    tool_calls_json=self.render_hint_for_field(awaiting_field, partial),
                )
```

Then update the trailing comment in that block from `# off_topic: ignore the reply, _ask_next_question re-asks below.` to note that off_topic/meta/frustration are now handled above.

- [ ] **Step 4: Run test to verify it passes**

Run: same as Step 2. Expected: PASS.
Then run the whole file to confirm no regression:
`... pytest orchestrator/tests/test_agent_base.py -q` → all PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/agents/base.py orchestrator/tests/test_agent_base.py
git commit -m "feat(orchestrator): answer-then-anchor for off_topic/meta/frustration"
```

---

### Task A5: classifier prompt includes the recent-dialogue window

**Files:**
- Modify: `orchestrator/agents/base.py` (`_classify_user_intent`)
- Test: `orchestrator/tests/test_agent_base.py`

- [ ] **Step 1: Write the failing test**

```python
def test_classifier_prompt_includes_recent_window(monkeypatch):
    agent = _ToyAgent()
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = AIMessage(content='{"intent": "answer", "value": "X"}')
    monkeypatch.setattr(_ToyAgent, "_get_llm", lambda self: fake_llm)

    state = _state([
        AIMessage(content="Pick one: survey or interview?"),
        HumanMessage(content="the first one"),
    ])
    agent._classify_user_intent(state, "title", {})
    prompt = fake_llm.invoke.call_args[0][0]
    # The classifier must see the prior assistant turn to resolve "the first one".
    assert "survey or interview" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `... pytest orchestrator/tests/test_agent_base.py::test_classifier_prompt_includes_recent_window -q`
Expected: FAIL — current prompt only embeds the single last user message, not the window.

- [ ] **Step 3: Write minimal implementation**

In `_classify_user_intent`, build the window and insert it into the prompt. After computing `last_user`, add:

```python
        recent = self._recent_dialogue(state.get("messages") or [])
```

and in the prompt string, replace the single `User's reply:` block with a recent-conversation block, e.g. insert before `"User's reply:\n{last_user}"`:

```python
            f"Recent conversation (for resolving references like 'the first one'):\n"
            f"{recent}\n\n"
```

(Keep the explicit `User's reply: {last_user}` line — the window is *context*, the last message is still the thing being classified.)

- [ ] **Step 4: Run test to verify it passes**

Run: same as Step 2. Expected: PASS.
Then: `... pytest orchestrator/tests/test_agent_base.py -q` → all PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/agents/base.py orchestrator/tests/test_agent_base.py
git commit -m "feat(orchestrator): feed recent-dialogue window to intent classifier"
```

---

### Phase A acceptance criteria

- [ ] A digression (off_topic/meta/frustration) while awaiting a field yields a warm reply that re-asks the same field; the field stays pending.
- [ ] The intent classifier prompt includes a window of recent turns (not just the last message).
- [ ] `meta` and `frustration` are recognized intents.
- [ ] Full suite green: `... pytest orchestrator/tests --ignore=orchestrator/tests/integration -q` (expect 281 + new tests).
- [ ] Manual smoke (optional): in the live app, mid-M1 ask "how long does this take?" → agent answers + re-asks; ask something random → answered + re-asked.

> **Deferred (note in commit, not in scope for Phase A):** the *confirm* screen (`_awaiting_confirm`) still treats a non-affirmative reply as "let me edit". Routing a digression at the confirm step through the same concierge is a small follow-up once Phase A is in.

---

# Phase 0 — Adopt native LangGraph `interrupt()`

**Goal:** Replace the hand-rolled `_module_paused` pause signal with LangGraph's native `interrupt()` / `Command(resume=...)` for human gates.

**Depends on:** nothing. **Risk:** low. **Ships independently:** yes.

**Files:** `orchestrator/graph.py`, `orchestrator/agents/base.py` (where modules pause), `api/app/routers/chat.py` (resume path), tests in `orchestrator/tests/test_graph.py`.

**Task outline:**
1. Spike: confirm `interrupt()` semantics against the **live** LangGraph 1.x docs (API moves fast; `NodeInterrupt`/static breakpoints are deprecated).
2. Replace the `_make_route_after_module` "end vs supervisor" decision so a paused module raises `interrupt(payload)` instead of routing to END via `_module_paused`.
3. Update the chat router to resume with `Command(resume=user_message)` instead of re-invoking with a fresh `{messages:[...]}`.
4. Keep `_module_paused` until parity is proven, then delete.

**Acceptance:** M1→M5 interactive flow behaves identically (all `test_graph.py` + integration interactive tests pass), with pauses now driven by `interrupt()`.

**Detailed bite-sized plan:** authored here when Phase 0 starts (depends on the live-docs spike in task 1).

---

# Phase 1 — Artifact DAG + definition-of-done validators

**Goal:** Model deliverables as a dependency DAG; each artifact has `depends_on` and a `dod(slice) -> DoD` validator (returns `done?` + `gaps[]`), independent of the generator.

**Depends on:** nothing (additive — nothing routes on it yet). **Risk:** low. **Ships independently:** yes (invisible until Phase 5 uses it).

**Files:**
- Create: `orchestrator/artifacts.py` — `Artifact`, `DoD` dataclasses + `ARTIFACTS` list + `dod_*` validators.
- Create: `orchestrator/tests/test_artifacts.py`.
- (Read-only) reference `orchestrator/schemas/m{1..5}.py` for field names.

**Artifact list — AS BUILT (decision D5: M1–M4 single artifacts, M5 split per chapter):**
`topic`, `literature`, `design`, `analysis`, `ch_intro`, `ch_lit_review`, `ch_methodology`, `ch_results`, `ch_discussion`, `ch_conclusion`. Dependencies wired in `orchestrator/artifacts.py:ARTIFACTS`. (Splitting M2 into `framework`/`gaps` — per [design §3.1](../../design/guided-agent-architecture.md#31-model-the-thesis-as-an-artifact-dag-not-a-5-step-line) — is a later refinement; v1 keeps `literature` as one artifact.)

**STATUS: ✅ DONE** — `orchestrator/artifacts.py` + `orchestrator/tests/test_artifacts.py` (20 tests). `DoD`/`Artifact` dataclasses, `dod_topic/literature/design/analysis/chapter` validators, `ARTIFACTS` registry, and `readiness(context_store) -> {key: done|ready|blocked}`. Purely additive; nothing routes on it yet.

**Task outline (each TDD):**
1. `DoD` dataclass (`done: bool`, `gaps: list[str]`) + test.
2. `Artifact` dataclass (`key`, `slice`, `depends_on`, `dod`) + test.
3. One `dod_*` validator per artifact — deterministic checks first (required fields present/non-empty), each with a test for a complete slice (done) and an incomplete slice (gaps). Start with `dod_topic`, `dod_design` (paradigm-conditional), `dod_chapter`.
4. `ARTIFACTS` registry + a `readiness(context_store) -> dict[key, "done"|"ready"|"blocked"]` pure function (topo over `depends_on`) + test.

**Acceptance:** `readiness()` returns correct done/ready/blocked for: empty project (only `topic` ready), partial project, fully-confirmed project (all done). No change to runtime behavior.

**Detailed bite-sized plan:** authored here when Phase 1 starts. **Decision needed:** D3 (Python-only vs +LLM-judge DoD) — default Python-only for v1, add LLM-judge for prose chapters in a follow-up.

---

# Phase 2 — Import + start-at endpoints

**Goal:** Let a student drop in existing work and target a step. `POST /projects/{id}/import` seeds `context_store` slices; `POST /threads/start-at/{artifact}`; `GET /projects/{id}/artifacts` returns the readiness map.

**Depends on:** Phase 1 (`readiness`, artifact keys). **Risk:** medium. **Ships independently:** yes.

**Files:** `api/app/routers/chat.py` (new routes), `api/app/models.py` (if a column is needed), `orchestrator/state.py` / `orchestrator/agents/m2/translation.py` (slice-merge helpers), tests under `orchestrator/tests/` and `api` tests.

**Task outline:**
1. `GET /projects/{id}/artifacts` → call `readiness()` over the project's `context_store`; test with a seeded project.
2. `POST /projects/{id}/import` → validate the blob against artifact slices, merge with conflict policy (first-write vs overwrite — reuse `orchestrator/concurrency.py`), mark `_source="imported"`; test round-trip.
3. `POST /threads/start-at/{artifact}` → create a thread whose first planner tick targets that artifact; test it routes there.

**Acceptance:** import a partial thesis (topic+design only) → `GET artifacts` shows topic/design done, `analysis` ready, chapters blocked; start-at `analysis` opens there.

**Detailed bite-sized plan:** authored here when Phase 2 starts.

---

# Phase 3 — 🔬 Backfill vertical slice (HIGH RISK / NOVEL)

**Goal:** When the target artifact depends on a `empty` prerequisite, reconstruct that prerequisite from downstream evidence, gate it behind DoD + one user confirm, then unblock the target. Prove it for ONE case: enter at `analysis`, reconstruct `design`.

**Depends on:** Phases 1, 2. **Risk:** HIGH — no cited source demonstrates generating never-started artifacts ([design doc §5](../../design/guided-agent-architecture.md#5-the-hard-part-prerequisite-backfill-flagged-risky)). **Ships independently:** partial (one case).

**Files:** `orchestrator/agents/m3_design.py` (a `reconstruct(evidence)` mode), a new `orchestrator/backfill.py` helper, tests.

**Task outline:**
1. Define "reconstruct mode" for M3: given the student's pasted analysis + topic, propose a `design` candidate marked `_source="assessed"`.
2. Gate: run `dod_design` on the candidate + emit a single confirm widget ("we inferred X — correct?").
3. On confirm, mark `design` done and unblock `analysis`.
4. **Evaluation harness** (this is the real deliverable): a small fixture set of "enter-at-analysis" cases scored for reconstruction quality. If quality is poor, STOP and revisit the approach with the user before widening.

**Acceptance:** for the fixture cases, reconstructed `design` passes `dod_design` and a human rates it plausible ≥ N% of the time (set the bar with product). Explicitly a **go/no-go gate** for the rest of "enter anywhere".

**Detailed bite-sized plan:** authored here when Phase 3 starts — **and** expect to iterate on approach, not just code.

---

# Phase 4 — Intake / triage subgraph

**Goal:** A front-door node that, for new projects or pasted work, asks "where are you / what do you have?" (cards) or ingests an upload, runs an assessment agent to map artifacts into the DAG, seeds slices, and hands off to the planner.

**Depends on:** Phases 1, 3. **Risk:** medium. **Ships independently:** yes.

**Files:** `orchestrator/agents/intake.py` (new node), wire into `orchestrator/graph.py` before the planner, prompts under `orchestrator/prompts/`, tests.

**Task outline:**
1. Assessment agent: given uploaded/pasted text, classify which artifacts are present + their `_status`; test with fixtures.
2. Seed the matching slices (reuse Phase 2 import merge).
3. Graph wiring: `START → _seed → intake → planner`; intake is a no-op when the project already has progress.

**Acceptance:** paste a Chapter-3 draft → intake seeds `design` (and maybe `topic`), planner places the user at `analysis`/writing.

**Detailed bite-sized plan:** authored here when Phase 4 starts.

---

# Phase 5 — Planner replaces `next_unconfirmed_module`

**Goal:** Routing decided by a planner over the DAG (done/ready/blocked + chosen target), with backfill, not by "first slice without `confirmed_at`". Deterministic topo-sort; LLM only for genuinely ambiguous redirects.

**Depends on:** Phases 1, 3. **Risk:** medium. **Ships independently:** yes.

**Files:** `orchestrator/agents/supervisor.py` (or a new `orchestrator/planner.py`), `orchestrator/graph.py` (route function), `orchestrator/state.py`, tests in `test_supervisor.py` / `test_graph.py`.

**Task outline:**
1. `plan_next(context_store, target=None) -> decision` pure function (topo over `readiness`, backfill blocked deps); exhaustive unit tests.
2. Swap `route_from_supervisor`/`next_unconfirmed_module` for the planner; keep the LLM nav-classifier only as a fuzzy override for explicit redirects (gate ≥ confidence).
3. Wire the **dispatcher** (Phase A's concierge) to sit in front of the planner so digressions don't trigger re-planning.

**Acceptance:** all existing flow tests pass with the planner; targeting an artifact with missing deps triggers backfill; "first ready" matches old sequential behavior when no target is set.

**Detailed bite-sized plan:** authored here when Phase 5 starts.

---

# Phase 7 — Stale flags + autonomy slider + project memory

**Goal:** (a) Editing an upstream artifact marks dependents `stale` (saga-style minimal affected set) with a "N steps may need review" nudge; (b) per-artifact autonomy level (draft-first/approve vs guided); (c) project memory (field, style, prior decisions) so the agent stops re-asking.

**Depends on:** Phases 1, 5. **Risk:** medium. **Ships independently:** yes.

**Files:** `orchestrator/artifacts.py` (stale propagation), `orchestrator/agents/base.py` + workers (`auto_fill` vs `propose_then_confirm`), a memory store (`orchestrator/memory.py` + a DB table), frontend autonomy control (later), tests.

**Task outline:**
1. `mark_stale(context_store, changed_key)` → set `_status="stale"` on the transitive dependents; test.
2. Autonomy level on each slice (`_autonomy`), planner picks `auto_fill` vs `propose_then_confirm`; test both paths.
3. Project memory read/write + inject into worker/concierge prompts; test that a remembered value isn't re-asked.

**Acceptance:** change RQs in `topic` → `framework`/`design`/chapters flagged stale; set a project to high-autonomy → steps auto-draft then ask one approval; a remembered citation style isn't re-asked.

**Detailed bite-sized plan:** authored here when Phase 7 starts. **Decision needed:** D2 (default autonomy level), D6 (history window size) — defaults in the design doc's decision table.

---

## Self-review (against the design doc)

- **Spec coverage:** every numbered migration step (0–7) + the §3.6/§3.7 conversation-resilience design maps to a phase here. ✅
- **Open decisions surfaced at the phase that needs them:** D3→Phase 1, D1→Phase 3, D5→Phase 1, D2/D6→Phase 7. ✅
- **No fabricated code in unproven phases:** Phases 0–7 (except A) give task outlines + acceptance, with detailed bite-sized code authored at execution time — deliberately, because Phase 3's logic is research-novel and later phases depend on earlier outcomes. Phase A is fully bite-sized because it ships now on known code. ✅
- **Type/name consistency:** `readiness()`, `Artifact{key,slice,depends_on,dod}`, `DoD{done,gaps}`, `_status`, `_source`, `_autonomy`, `_phase_state` used consistently across phases.

---

## Execution handoff

**Plan saved to `docs/superpowers/plans/2026-05-30-guided-agent-implementation.md`.**

We start with **Phase A (conversation resilience)** — fully bite-sized above. Two ways to execute:

1. **Subagent-Driven (recommended)** — a fresh subagent per task (A1…A5), reviewed between tasks.
2. **Inline Execution** — run A1…A5 here with commit checkpoints.

Subsequent phases (0–7) get their detailed bite-sized plans authored just-in-time when each begins.

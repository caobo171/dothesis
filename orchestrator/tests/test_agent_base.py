"""Tests for ModuleAgent's clarification loop (shared by all 5 module agents)."""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from orchestrator.agents.base import ModuleAgent, ModuleStepResult
from orchestrator.state import ContextStore, OrchestratorState


class _ToyOutput(BaseModel):
    title: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)
    confirmed_at: datetime | None = None


class _ToyAgent(ModuleAgent):
    schema = _ToyOutput
    module_key = "M1"
    tools = []
    system_prompt = "You are a toy agent."


def _state(messages, partial=None, mode="interactive"):
    cs = ContextStore()
    if partial:
        cs.m1_topic = partial
    return {
        "project_id": None,
        "thread_id": None,
        "messages": messages,
        "current_module": "M1",
        "context_store": cs,
        "mode": mode,
        "user_intent": None,
        "pending_confirmations": [],
    }


def test_step_does_not_hang_when_get_llm_invoke_stalls(monkeypatch):
    """Regression for the 'simple Hello hangs forever' bug. The first
    interactive turn calls _ask_next_question -> _get_llm().invoke(prompt),
    and Gemini can stall there too. step() must return in bounded wall-clock
    even when the LLM hangs indefinitely (falls back to a deterministic
    question)."""
    import time as _t
    agent = _ToyAgent()

    fake_llm = MagicMock()
    def _hang(_p):
        _t.sleep(60)
    fake_llm.invoke.side_effect = _hang
    monkeypatch.setattr(_ToyAgent, "_get_llm", lambda self: fake_llm)
    # tighten the wall-clock cap so the test finishes fast
    monkeypatch.setenv("ORCHESTRATOR_LLM_MAX_SECONDS", "1")

    state = _state([HumanMessage(content="start")])
    t0 = _t.time()
    result = agent.step(state)
    elapsed = _t.time() - t0
    assert elapsed < 5, f"step() blocked {elapsed:.1f}s on hung LLM"
    assert result.transition is False
    assert result.assistant_message, "must produce SOME question even on LLM hang"


def test_bounded_invoke_returns_value_when_fast(monkeypatch):
    from orchestrator.agents.base import bounded_invoke
    llm = MagicMock()
    resp = MagicMock(); resp.content = "ok"
    llm.invoke.return_value = resp
    out = bounded_invoke(llm, "p", max_seconds=2)
    assert out.content == "ok"


def test_bounded_invoke_times_out_after_max_seconds():
    import time as _t
    from orchestrator.agents.base import BoundedInvokeTimeout, bounded_invoke
    llm = MagicMock()
    def _slow(_):
        _t.sleep(5)
        return MagicMock(content="late")
    llm.invoke.side_effect = _slow
    with pytest.raises(BoundedInvokeTimeout):
        bounded_invoke(llm, "p", max_seconds=1, retries=0)


def test_bounded_invoke_retries_then_succeeds(monkeypatch):
    from orchestrator.agents.base import bounded_invoke
    llm = MagicMock()
    attempts = {"n": 0}
    def _maybe(_):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("transient")
        return MagicMock(content="recovered")
    llm.invoke.side_effect = _maybe
    out = bounded_invoke(llm, "p", max_seconds=2, retries=1, backoff_s=0.01)
    assert out.content == "recovered"
    assert attempts["n"] == 2


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
    # The pending field must reach the LLM prompt.
    prompt = fake_llm.invoke.call_args[0][0]
    assert "title" in prompt


def test_off_topic_answers_then_reasks_same_field(monkeypatch):
    """A digression while awaiting a field → concierge reply that re-asks the
    SAME field (not advance, not silently re-ask, not store the digression)."""
    agent = _ToyAgent()
    fake_llm = MagicMock()
    fake_llm.invoke.side_effect = [
        AIMessage(content='{"intent": "off_topic", "value": null}'),          # classify
        AIMessage(content="Ha, weather's nice! Anyway — what's your title?"),  # concierge
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
    # Field stays pending so the next turn resumes correctly...
    assert result.context_patch.get("_awaiting_field") == "title"
    # ...and the digression was NOT stored as the field value.
    assert result.context_patch.get("title") is None
    # The reply must come from the concierge (answer-then-anchor), whose prompt
    # uniquely carries the user's digression (recent dialogue) AND the bridge
    # guidance — the old silent-re-ask path (_ask_next_question) carries neither.
    concierge_prompt = fake_llm.invoke.call_args_list[1][0][0]
    assert "weather" in concierge_prompt
    assert "bring them back" in concierge_prompt


def test_answer_and_anchor_includes_cross_module_context(monkeypatch):
    """Regression: 'show me M3's questionnaire as a table' (asked while M4 is
    awaiting data_paste) used to get a generic 'I'll handle that later'
    deflection — _answer_and_anchor only saw the current module's empty
    partial, not the prior confirmed slices that actually contain the
    questionnaire text. The prompt must now carry every module slice from
    context_store so the LLM can answer follow-ups from real data.

    Why we don't assert on the *reply* text: with a real LLM the reply would
    be the formatted table; with a mock we can only verify the data reached
    the prompt. That's the contract that mattered for the bug.
    """
    agent = _ToyAgent()
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = AIMessage(
        content="Sure — here's the questionnaire... Anyway, what's your title?"
    )
    monkeypatch.setattr(_ToyAgent, "_get_llm", lambda self: fake_llm)

    cs = ContextStore()
    cs.m3_design = {
        "design": "PLS-SEM",
        "questionnaire_text": "Q1: I find this system useful.",
    }
    state = {
        "project_id": None, "thread_id": None,
        "messages": [HumanMessage(content="Show me the questionnaire as a table")],
        "current_module": "M1", "context_store": cs, "mode": "interactive",
        "user_intent": None, "pending_confirmations": [],
    }
    agent._answer_and_anchor(state, "off_topic", "title", {})
    prompt = fake_llm.invoke.call_args[0][0]
    # The cross-module data must reach the LLM, keyed under its module slice
    # so the model knows which module it belongs to.
    assert "m3_design" in prompt
    assert "questionnaire" in prompt.lower()
    assert "PLS-SEM" in prompt


def test_answer_and_anchor_appends_deterministic_field_reask_when_llm_drifts(monkeypatch):
    """Live bug: when noisy prior context (e.g. a leaked sibling-module
    bubble) confuses the LLM into ignoring `field_name`, the assistant text
    used to disagree with the widget — text said 'choose the software tool'
    while the rendered card grid asked 'Which design fits your study?'
    (thread 6bdf934f). The user clicked a design option, the agent treated
    it as if they'd answered 'software tool', and the conversation de-railed.

    Defense: after the LLM-generated ack, the wrapper deterministically
    appends the canonical question for `field_name` (the same title the
    widget uses, when defined). Even if the LLM drifts completely off the
    field, the user-visible text still names the right one so it can never
    silently disagree with the widget below it.
    """
    class _CardAgent(_ToyAgent):
        card_fields = {"design"}
        card_field_titles = {"design": "Which design fits your study?"}

    agent = _CardAgent()
    fake_llm = MagicMock()
    # Drifted LLM output — no mention of 'design' anywhere.
    fake_llm.invoke.return_value = AIMessage(
        content="Apologies for the confusion — let's pick the software tool first."
    )
    monkeypatch.setattr(_CardAgent, "_get_llm", lambda self: fake_llm)

    state = _state([HumanMessage(content="where's my questions list?")])
    msg = agent._answer_and_anchor(
        state, "off_topic", "design", {"paradigm": "quantitative"}
    )
    # The deterministic re-ask must use the SAME canonical title as the
    # widget so the bubble text and widget agree on what's being asked.
    assert "Which design fits your study?" in msg, (
        f"deterministic re-ask missing from message: {msg!r}"
    )


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


def test_interactive_asks_for_first_missing_field(monkeypatch):
    agent = _ToyAgent()
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = AIMessage(content="What is the title?")
    monkeypatch.setattr(_ToyAgent, "_get_llm", lambda self: fake_llm)

    state = _state([HumanMessage(content="start")])
    result = agent.step(state)
    assert isinstance(result, ModuleStepResult)
    assert result.transition is False
    assert "title" in result.assistant_message.lower()


def test_interactive_fills_field_from_user_answer(monkeypatch):
    """When the agent has just asked for 'title' and user replies, it stores 'title'.

    Post-refactor flow per turn:
      1. _classify_user_intent  → JSON with intent + extracted value
      2. _ask_next_question     → prose prompt for the next field
    """
    agent = _ToyAgent()
    fake_llm = MagicMock()
    fake_llm.invoke.side_effect = [
        AIMessage(content='{"intent": "answer", "value": "My Title"}'),  # classify+extract
        AIMessage(content="Got it. What is the answer?"),                # next question
    ]
    monkeypatch.setattr(_ToyAgent, "_get_llm", lambda self: fake_llm)

    state = _state(
        [HumanMessage(content="start"),
         AIMessage(content="What is the title?"),
         HumanMessage(content="My Title")],
        partial={"_awaiting_field": "title"},
    )
    result = agent.step(state)
    new_partial = result.context_patch
    assert new_partial.get("title") == "My Title"


def test_auto_mode_autofills_silently(monkeypatch):
    agent = _ToyAgent()
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = AIMessage(
        content='{"title": "Auto Title", "answer": "Auto Answer"}'
    )
    monkeypatch.setattr(_ToyAgent, "_get_llm", lambda self: fake_llm)

    state = _state([HumanMessage(content="seed topic")], mode="auto")
    result = agent.step(state)
    assert result.transition is True
    patch = result.context_patch
    assert patch["title"] == "Auto Title"
    assert patch["answer"] == "Auto Answer"
    assert "confirmed_at" in patch


def test_interactive_transition_after_confirm(monkeypatch):
    agent = _ToyAgent()
    fake_llm = MagicMock()
    monkeypatch.setattr(_ToyAgent, "_get_llm", lambda self: fake_llm)

    state = _state(
        [AIMessage(content="Summary: title=X, answer=Y. Confirm?"),
         HumanMessage(content="yes")],
        partial={"title": "X", "answer": "Y", "_awaiting_confirm": True},
    )
    result = agent.step(state)
    assert result.transition is True
    assert "confirmed_at" in result.context_patch


def test_structured_widget_payload_bypasses_llm_extraction(monkeypatch):
    """A widget that emits a structured payload (FlowChart's {nodes,edges},
    ListEditor's [{text,sub_items}], ...) must skip _classify_user_intent +
    _extract_answer entirely and use the JSON value as the field value
    verbatim.

    Why: LLM round-trip through a prose summary is lossy. Repro: M3's
    conceptual_model widget Confirmed {nodes:[{label,questions}], edges:[]}
    but state ended up with only {paths:[...]} — the LLM extractor saw the
    bullet-list label and reconstructed a simpler shape than the widget
    actually emitted. The fix: when the request carries a
    `pending_widget_payload` whose field_name matches the awaiting field,
    trust it as the source of truth.
    """
    agent = _ToyAgent()
    fake_llm = MagicMock()
    # _ask_next_question (after the bypass) will look for the next missing
    # required field. `title` is still missing, so we mock the question prompt.
    fake_llm.invoke.return_value = AIMessage(content="What's the title?")
    monkeypatch.setattr(_ToyAgent, "_get_llm", lambda self: fake_llm)

    # Track whether the classifier was called — it must NOT be.
    classify_calls = {"n": 0}
    orig_classify = _ToyAgent._classify_user_intent
    def _spy(self, *a, **kw):
        classify_calls["n"] += 1
        return orig_classify(self, *a, **kw)
    monkeypatch.setattr(_ToyAgent, "_classify_user_intent", _spy)

    structured_value = {"nested": ["a", "b"], "n": 2}
    state = _state(
        [AIMessage(content="What's your answer?"),
         HumanMessage(content="My answer is ...")],
        partial={"_awaiting_field": "answer"},
    )
    state["pending_widget_payload"] = {
        "field_name": "answer",
        "value": structured_value,
    }

    result = agent.step(state)

    # Value stored verbatim, no LLM extraction.
    assert result.context_patch.get("answer") == structured_value
    assert classify_calls["n"] == 0, "classifier must be bypassed when payload matches"


def test_structured_widget_payload_ignored_when_field_mismatch(monkeypatch):
    """A payload whose field_name doesn't match the awaiting field is stale
    (e.g. user clicked an earlier widget then typed a free-text reply). It
    must NOT be consumed — fall through to the normal classify path so the
    typed reply still gets processed.
    """
    agent = _ToyAgent()
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = AIMessage(
        content='{"intent": "answer", "value": "typed-reply"}'
    )
    monkeypatch.setattr(_ToyAgent, "_get_llm", lambda self: fake_llm)

    state = _state(
        [HumanMessage(content="typed-reply")],
        partial={"_awaiting_field": "answer"},
    )
    state["pending_widget_payload"] = {
        "field_name": "title",  # mismatched — stale from prior turn
        "value": "stale",
    }

    result = agent.step(state)
    # The stale payload must not have overwritten the awaiting field.
    assert result.context_patch.get("answer") == "typed-reply"


def test_widget_payload_normalizes_list_str_field(monkeypatch):
    """Regression: ListEditor confirms emit list[{id,text,sub_items,meta}],
    but schemas like M1Output.research_questions are list[str]. Without
    normalization the dict shape leaks into the slice and downstream tools
    that take `research_question: str` (e.g. M3's build_conceptual_model)
    receive a dict and crash pydantic.

    Decision: normalize at the widget bypass site against the schema
    annotation — flatten ListItem dicts to their .text when the field is
    list[str]. list[dict] fields (M3 themes, purposive_criteria) must be
    left untouched.
    """
    class _StrListOutput(BaseModel):
        research_questions: list[str] = Field(..., min_length=1)
        confirmed_at: datetime | None = None

    class _StrListAgent(ModuleAgent):
        schema = _StrListOutput
        module_key = "M1"
        tools = []
        system_prompt = "agent"

    agent = _StrListAgent()
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = AIMessage(content="next question")
    monkeypatch.setattr(_StrListAgent, "_get_llm", lambda self: fake_llm)

    cs = ContextStore(m1_topic={"_awaiting_field": "research_questions"})
    state = {
        "project_id": None, "thread_id": None,
        "messages": [HumanMessage(content="confirmed via widget")],
        "current_module": "M1", "context_store": cs,
        "mode": "interactive", "user_intent": None,
        "pending_confirmations": [],
        "pending_widget_payload": {
            "field_name": "research_questions",
            "value": [
                {"id": "rq_0", "text": "How does X affect Y?",
                 "sub_items": [], "meta": None},
                {"id": "rq_1", "text": "What moderates Z?",
                 "sub_items": [], "meta": None},
            ],
        },
    }
    result = agent.step(state)
    stored = result.context_patch.get("research_questions")
    assert stored == ["How does X affect Y?", "What moderates Z?"], (
        f"list[str] field must be flattened from ListItem dicts; got {stored!r}"
    )


def test_widget_payload_preserves_list_dict_field(monkeypatch):
    """Counterpart to the list[str] test: when a schema field IS list[dict]
    (M3 themes, purposive_criteria), the ListItem dicts must be stored
    verbatim — flattening to text would discard sub_items/meta."""
    class _DictListOutput(BaseModel):
        themes: list[dict] = Field(...)
        confirmed_at: datetime | None = None

    class _DictListAgent(ModuleAgent):
        schema = _DictListOutput
        module_key = "M3"
        tools = []
        system_prompt = "agent"

    agent = _DictListAgent()
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = AIMessage(content="next question")
    monkeypatch.setattr(_DictListAgent, "_get_llm", lambda self: fake_llm)

    items = [
        {"id": "t_0", "text": "Theme A",
         "sub_items": [{"id": "t_0_s0", "text": "sub"}], "meta": None},
    ]
    cs = ContextStore(m3_design={"_awaiting_field": "themes"})
    state = {
        "project_id": None, "thread_id": None,
        "messages": [HumanMessage(content="confirmed")],
        "current_module": "M3", "context_store": cs,
        "mode": "interactive", "user_intent": None,
        "pending_confirmations": [],
        "pending_widget_payload": {"field_name": "themes", "value": items},
    }
    result = agent.step(state)
    assert result.context_patch.get("themes") == items


def test_navigation_intent_clears_awaiting_field(monkeypatch):
    """Architectural fix: when the user's reply is classified as 'navigation'
    mid-question, the module must clear _awaiting_field so the supervisor's
    nav classifier can fire on the next turn. Previously navigation was
    silently dropped — _awaiting_field stayed set, supervisor's mid_question
    gate skipped the nav classifier, and the user was stuck. Locks in the
    'I cannot claim it again' fix at the module layer."""
    agent = _ToyAgent()
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = AIMessage(
        content='{"intent": "navigation", "value": null}'
    )
    monkeypatch.setattr(_ToyAgent, "_get_llm", lambda self: fake_llm)

    state = _state(
        [AIMessage(content="What is the title?"),
         HumanMessage(content="actually let me revisit M2")],
        partial={"_awaiting_field": "title"},
    )
    result = agent.step(state)
    # _awaiting_field MUST be cleared so the next supervisor pass can route
    # cross-module without being silenced by the mid_question gate.
    assert "_awaiting_field" not in result.context_patch
    assert result.needs_user_reply is True
    assert result.transition is False
    # The handoff message points the user at module names so the next
    # supervisor turn has an unambiguous nav signal.
    assert "M2" in result.assistant_message or "module" in result.assistant_message.lower()


def test_confirm_refuses_when_required_field_missing(monkeypatch):
    """Completeness contract: even if `_awaiting_confirm` is set and the user
    types 'yes', the module MUST NOT stamp `confirmed_at` while a required
    field is missing. Reported pain: M3 reached confirm with empty
    `scale_items`, transitioned, then M4 had no questionnaire to show the
    user ('M3 missing data … I cannot claim it again'). The fix makes
    transition a contract — _next_missing_field must return None or we
    re-ask instead of confirming."""
    agent = _ToyAgent()
    fake_llm = MagicMock()
    # _ask_next_question will fire after the gate refuses confirm; mock its
    # LLM call so the test isn't sensitive to prompt phrasing.
    fake_llm.invoke.return_value = AIMessage(content="What is the answer?")
    monkeypatch.setattr(_ToyAgent, "_get_llm", lambda self: fake_llm)

    # Partial has title filled but `answer` missing — _next_missing_field
    # should surface 'answer' and block transition.
    state = _state(
        [AIMessage(content="Summary: title=X, answer=?. Confirm?"),
         HumanMessage(content="yes")],
        partial={"title": "X", "_awaiting_confirm": True},
    )
    result = agent.step(state)
    assert result.transition is False, "must NOT transition with missing required field"
    assert "confirmed_at" not in result.context_patch
    # The follow-up question is for the missing field.
    assert "answer" in result.assistant_message.lower()

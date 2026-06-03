from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage

from orchestrator.agents.supervisor import (
    IntentClassification, RouteDecision, route_from_supervisor, supervisor_node,
)
from orchestrator.state import ContextStore


def test_supervisor_skips_nav_classifier_on_cold_start(monkeypatch):
    """Cold-start (no module confirmed yet): the classifier has nothing to do —
    every artifact is unconfirmed, so the only sensible decision is rule-based
    (M1 first). Skip the LLM call entirely. This is the fast-path for 'Hello'."""
    from langchain_core.messages import HumanMessage
    from unittest.mock import MagicMock
    from orchestrator.agents import supervisor as sup

    fake_structured = MagicMock()
    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value = fake_structured
    monkeypatch.setattr(sup, "_intent_llm", lambda: fake_llm)

    out = supervisor_node({
        "messages": [HumanMessage(content="Hello")],
        "current_module": "M1", "context_store": ContextStore(),  # cold start
        "mode": "interactive",
        "user_intent": None, "pending_confirmations": [],
    })
    assert out["current_module"] == "M1"
    # Classifier must not have been called — no module to navigate FROM.
    fake_structured.invoke.assert_not_called()
    fake_llm.with_structured_output.assert_not_called()


def test_supervisor_nav_classifier_does_not_block_on_llm_hang(monkeypatch):
    """The headline live-product fix: when Gemini stalls inside the nav
    classifier, the supervisor must still produce a routing decision in
    bounded wall-clock so the turn doesn't hang forever. The classifier's
    bounded_invoke has a short cap; on timeout we degrade to the rule-based
    decision rather than blocking."""
    import time as _t
    from langchain_core.messages import HumanMessage
    from unittest.mock import MagicMock
    from orchestrator.agents import supervisor as sup

    # Real LangChain-shape: with_structured_output(...).invoke(...) — and that
    # invoke HANGS. The supervisor must not wait for it.
    fake_structured = MagicMock()
    def _hang(*_a, **_kw):
        _t.sleep(60)  # would have hung the turn
    fake_structured.invoke.side_effect = _hang
    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value = fake_structured
    monkeypatch.setattr(sup, "_intent_llm", lambda: fake_llm)
    # Tight cap so the test finishes quickly.
    monkeypatch.setenv("ORCHESTRATOR_NAV_MAX_SECONDS", "1")

    cs = ContextStore(m1_topic={"confirmed_at": "x"})
    t0 = _t.time()
    out = supervisor_node({
        "messages": [HumanMessage(content="hello")],
        "current_module": "M1", "context_store": cs, "mode": "interactive",
        "user_intent": None, "pending_confirmations": [],
    })
    elapsed = _t.time() - t0
    assert elapsed < 5, f"supervisor blocked {elapsed:.1f}s on hung classifier"
    # Still produces a sensible decision (rule-based fallback).
    assert out["current_module"] == "M2"  # M1 is confirmed → next is M2


def test_supervisor_rejects_same_module_nav_pick(monkeypatch):
    """Self-route guard: the nav classifier now runs even mid-question (so the
    user is never locked into a module they want to leave), but if the
    classifier returns the SAME module the rules already picked, treat as
    no-nav. This protects against the domain-answer false-positive: typing
    'PLS-SEM' for the `design` field while rules already route to M3 — the
    classifier may say wants_navigation=M3, which is meaningless (we're
    already going there) and almost certainly a domain-answer mis-classify."""
    from langchain_core.messages import HumanMessage
    from unittest.mock import MagicMock
    from orchestrator.agents import supervisor as sup

    cs = ContextStore(m1_topic={"confirmed_at": "x"}, m2_literature={"confirmed_at": "x"},
                      m3_design={"_awaiting_field": "design"})
    fake_structured = MagicMock()
    # Classifier mis-fires — picks M3, the same module rules already routed to.
    fake_structured.invoke.return_value = IntentClassification(
        wants_navigation=True, target_module="M3", confidence=0.95)
    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value = fake_structured
    monkeypatch.setattr(sup, "_intent_llm", lambda: fake_llm)

    out = supervisor_node({
        "messages": [HumanMessage(content="PLS-SEM")], "current_module": "M3",
        "context_store": cs, "mode": "interactive",
        "user_intent": None, "pending_confirmations": [],
    })
    assert out["current_module"] == "M3"           # stayed (self-route rejected)


def test_supervisor_honors_cross_module_nav_mid_question(monkeypatch):
    """Architectural fix: when a module is mid-question (`_awaiting_field` set)
    and the user explicitly asks to revisit a different module, the supervisor
    MUST honor that nav request. Previously the mid-question gate silenced the
    classifier entirely, locking the user in. The new defense is narrower —
    high confidence (>=0.85) + cross-module pick — which catches the domain-
    answer false-positives without blocking legitimate revisit requests.

    Concretely reproduces the user-reported 'I cannot claim it again' bug:
    while M3 was awaiting a field, the user wanted to go back to (say) M2
    and the system kept them stuck on M3."""
    from langchain_core.messages import HumanMessage
    from unittest.mock import MagicMock
    from orchestrator.agents import supervisor as sup

    cs = ContextStore(m1_topic={"confirmed_at": "x"}, m2_literature={"confirmed_at": "x"},
                      # conceptual_model (post-2026-06 merge) replaces the
                      # prior scale_items example here.
                      m3_design={"_awaiting_field": "conceptual_model"})
    fake_structured = MagicMock()
    fake_structured.invoke.return_value = IntentClassification(
        wants_navigation=True, target_module="M2", confidence=0.92)
    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value = fake_structured
    monkeypatch.setattr(sup, "_intent_llm", lambda: fake_llm)

    out = supervisor_node({
        "messages": [HumanMessage(content="hold on, let me revise M2 first")],
        "current_module": "M3", "context_store": cs, "mode": "interactive",
        "user_intent": None, "pending_confirmations": [],
    })
    assert out["current_module"] == "M2"           # rerouted mid-question


def test_supervisor_nav_prompt_includes_awaiting_field_context(monkeypatch):
    """Regression: when a module is mid-question, the nav classifier MUST be
    told what field is currently being asked so it can correctly recognize the
    user's reply as an ANSWER rather than a navigation request.

    Live bug this pins: user picked the 'PLS-SEM' card while M3 was asking for
    `design` and was kicked into M4. With only the user's bare message ("PLS-
    SEM") the classifier sees a M4-flavored term (PLS-SEM is analyzed in
    SmartPLS, an M4 tool) and returns target_module=M4 with high confidence.
    The cross-module guard then honors it — bug. Giving the classifier the
    mid-question context ("M3 is asking for `design`") lets it correctly
    classify PLS-SEM as an answer to that question. The user explicitly asked
    for a prompt fix here; this test pins the prompt's contract so the wire
    can't silently rot.
    """
    from unittest.mock import MagicMock
    from langchain_core.messages import HumanMessage
    from orchestrator.agents import supervisor as sup

    captured_prompts: list[str] = []
    fake_structured = MagicMock()
    def _capture(prompt, *_a, **_kw):
        captured_prompts.append(prompt)
        return IntentClassification(
            wants_navigation=False, target_module=None, confidence=0.0,
        )
    fake_structured.invoke.side_effect = _capture
    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value = fake_structured
    monkeypatch.setattr(sup, "_intent_llm", lambda: fake_llm)

    cs = ContextStore(
        m1_topic={"confirmed_at": "x"}, m2_literature={"confirmed_at": "x"},
        m3_design={"_awaiting_field": "design"},
    )
    supervisor_node({
        "messages": [HumanMessage(content="PLS-SEM")],
        "current_module": "M3", "context_store": cs, "mode": "interactive",
        "user_intent": None, "pending_confirmations": [],
    })
    assert captured_prompts, "nav classifier was not invoked"
    sent = captured_prompts[0]
    assert "PLS-SEM" in sent, "user message must reach the classifier"
    # The new prompt block must explicitly state the mid-question context.
    # The buggy version only included the module legend ("M3=design") and
    # the bare user message, with no anchoring of the pending question — so
    # checking for substrings like "M3" or "design" wasn't enough (they
    # appeared incidentally in the legend). Anchor on a phrase that ONLY
    # the awaiting-field block would emit.
    lower = sent.lower()
    assert "awaiting_field" in lower or "currently asking" in lower, (
        "prompt must explicitly anchor the awaiting-field context — without "
        "it the classifier has no way to distinguish 'PLS-SEM as a design "
        "answer' from 'user wants to navigate to M4'."
    )
    # And the awaiting context must name THIS field + module, not just "some
    # field is pending". Use single-quote/backtick framing so the assertion
    # still works whether the prompt uses 'design' or `design`.
    assert ("'design'" in sent or "`design`" in sent), (
        "the awaiting block must name the field the user is being asked for "
        "(`design`), not just mention that some field is pending."
    )


def test_supervisor_nav_prompt_has_no_awaiting_context_when_no_field_pending(monkeypatch):
    """Symmetric guard: when no module is awaiting a field (e.g. between
    modules, post-confirm), the mid-question hint must NOT be in the prompt
    — otherwise the classifier would invent a phantom answering-context and
    suppress legitimate nav requests. Pins that the awaiting block is
    conditional, not always-on."""
    from unittest.mock import MagicMock
    from langchain_core.messages import HumanMessage
    from orchestrator.agents import supervisor as sup

    captured_prompts: list[str] = []
    fake_structured = MagicMock()
    def _capture(prompt, *_a, **_kw):
        captured_prompts.append(prompt)
        return IntentClassification(
            wants_navigation=False, target_module=None, confidence=0.0,
        )
    fake_structured.invoke.side_effect = _capture
    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value = fake_structured
    monkeypatch.setattr(sup, "_intent_llm", lambda: fake_llm)

    # M1 confirmed, no other module mid-question → classifier sees a plain
    # cross-module choice with no answering bias.
    cs = ContextStore(m1_topic={"confirmed_at": "x"})
    supervisor_node({
        "messages": [HumanMessage(content="go back to M1")],
        "current_module": "M2", "context_store": cs, "mode": "interactive",
        "user_intent": None, "pending_confirmations": [],
    })
    assert captured_prompts, "nav classifier was not invoked"
    sent = captured_prompts[0]
    assert "go back to M1" in sent
    # The "currently asking" / awaiting-field paragraph is conditional. When
    # absent, the classifier should NOT see any awaiting hint at all — using
    # the exact phrase from the prompt template as the anchor.
    assert "currently asking the user for" not in sent.lower(), (
        "no module is mid-question — the awaiting-field hint block must "
        "not be in the prompt, or the classifier will hallucinate a "
        "pending answer and reject legitimate nav requests."
    )


def test_supervisor_nav_threshold_is_strict(monkeypatch):
    """Confidence threshold protects against borderline mis-classifications.
    A 0.80 confidence (below the new 0.85 floor) is NOT honored."""
    from langchain_core.messages import HumanMessage
    from unittest.mock import MagicMock
    from orchestrator.agents import supervisor as sup

    cs = ContextStore(m1_topic={"confirmed_at": "x"})  # rules → M2
    fake_structured = MagicMock()
    fake_structured.invoke.return_value = IntentClassification(
        wants_navigation=True, target_module="M5", confidence=0.80)
    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value = fake_structured
    monkeypatch.setattr(sup, "_intent_llm", lambda: fake_llm)

    out = supervisor_node({
        "messages": [HumanMessage(content="something ambiguous")],
        "current_module": "M2", "context_store": cs, "mode": "interactive",
        "user_intent": None, "pending_confirmations": [],
    })
    # 0.80 < 0.85 → fall back to rules (M2, the next unconfirmed).
    assert out["current_module"] == "M2"


def _state(messages, cs=None, mode="interactive"):
    return {
        "messages": messages, "current_module": "M1",
        "context_store": cs or ContextStore(), "mode": mode,
        "user_intent": None, "pending_confirmations": [],
    }


def test_supervisor_target_routes_to_ready_chapter_skipping_modules():
    # topic + literature confirmed. Target = ch_lit_review (needs only literature,
    # which is done) → ready → route M5. The sequential rule would go to M3.
    cs = ContextStore(m1_topic={"confirmed_at": "x"},
                      m2_literature={"confirmed_at": "x"})
    state = _state([], cs=cs)
    state["target_artifact"] = "ch_lit_review"
    out = supervisor_node(state)
    assert out["current_module"] == "M5"


def test_supervisor_target_methodology_skips_analysis():
    # topic + literature + design confirmed. Target = ch_methodology (needs only
    # design) → ready → M5. Sequential would route to M4 (analysis).
    cs = ContextStore(m1_topic={"confirmed_at": "x"},
                      m2_literature={"confirmed_at": "x"},
                      m3_design={"confirmed_at": "x"})
    state = _state([], cs=cs)
    state["target_artifact"] = "ch_methodology"
    out = supervisor_node(state)
    assert out["current_module"] == "M5"


def test_supervisor_target_backfills_blocked_prerequisite():
    # Target = analysis, nothing done → backfill topic first → M1.
    state = _state([], cs=ContextStore())
    state["target_artifact"] = "analysis"
    out = supervisor_node(state)
    assert out["current_module"] == "M1"


def test_supervisor_clears_target_once_reached():
    # Target = analysis, already confirmed → reached → clear + resume sequential.
    cs = ContextStore(m4_analysis={"confirmed_at": "x"})
    state = _state([], cs=cs)
    state["target_artifact"] = "analysis"
    out = supervisor_node(state)
    assert "target_artifact" in out and out["target_artifact"] is None
    assert out["current_module"] == "M1"


def test_supervisor_routes_to_first_unconfirmed_in_auto():
    cs = ContextStore(m1_topic={"confirmed_at": "2026-05-26"},
                      m2_literature={"confirmed_at": "2026-05-26"})
    state = _state([HumanMessage(content="...")], cs=cs, mode="auto")
    out = supervisor_node(state)
    assert out["current_module"] == "M3"


def test_supervisor_all_done_routes_to_done():
    cs = ContextStore(**{m: {"confirmed_at": "2026-05-26"} for m in
                         ("m1_topic", "m2_literature", "m3_design",
                          "m4_analysis", "m5_writing")})
    state = _state([HumanMessage(content="...")], cs=cs)
    out = supervisor_node(state)
    assert out["current_module"] == "DONE"


def test_supervisor_honors_navigation_request(monkeypatch):
    cs = ContextStore(m1_topic={"confirmed_at": "2026-05-26"},
                      m2_literature={"confirmed_at": "2026-05-26"})
    state = _state(
        [HumanMessage(content="actually go back to M2 and redo it")],
        cs=cs,
    )
    # Stub the structured-output LLM to return a navigation intent.
    fake = MagicMock()
    fake.with_structured_output.return_value.invoke.return_value = type(
        "X", (), {"wants_navigation": True, "target_module": "M2", "confidence": 0.9}
    )()
    monkeypatch.setattr("orchestrator.agents.supervisor._intent_llm", lambda: fake)
    out = supervisor_node(state)
    assert out["current_module"] == "M2"


def test_supervisor_auto_mode_skips_llm_classifier(monkeypatch):
    """Auto mode should never call the LLM classifier — only rules."""
    counter = {"calls": 0}
    def fake_llm():
        counter["calls"] += 1
        return MagicMock()
    monkeypatch.setattr("orchestrator.agents.supervisor._intent_llm", fake_llm)

    cs = ContextStore()
    state = _state([HumanMessage(content="go back to M3")], cs=cs, mode="auto")
    supervisor_node(state)
    assert counter["calls"] == 0


def test_route_from_supervisor_returns_state_module():
    cs = ContextStore()
    state = {**_state([], cs=cs), "current_module": "M2"}
    assert route_from_supervisor(state) == "M2"

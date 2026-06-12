"""Brief §1.5 read intent tests.

read_slice MUST never write the slice and MUST never shift focus. The
intent classifier picks read for cross-module question-shape messages
(brief §4 worked example: "remind me what gap 2 was while I'm in M4").
"""
from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage

from orchestrator import graph_v2
from orchestrator.agents import read_handler, router_agent
from orchestrator.agents.base import ModuleStepResult
from orchestrator.agents.read_handler import (
    classify_intent_heuristic, read_slice,
)
from orchestrator.state import ContextStore


def _fake_llm(content: str) -> MagicMock:
    llm = MagicMock()
    llm.invoke.return_value.content = content
    return llm


# --- classify_intent_heuristic ----------------------------------------------

def test_classify_focus_module_always_continue():
    # Brief §1.5 — same-module work is `continue` regardless of phrasing.
    # "what's my topic" while focused on M1 is still M1's job.
    assert classify_intent_heuristic("what's my topic?", target_is_focus=True) == "continue"
    assert classify_intent_heuristic("add a gap", target_is_focus=True) == "continue"


def test_classify_question_shape_is_read():
    # Brief §4 worked example: cross-module question → read.
    assert classify_intent_heuristic(
        "remind me what gap 2 was", target_is_focus=False,
    ) == "read"
    assert classify_intent_heuristic(
        "what is the methodology?", target_is_focus=False,
    ) == "read"
    assert classify_intent_heuristic(
        "Show me the research gaps", target_is_focus=False,
    ) == "read"


def test_classify_edit_verb_is_mutate():
    # Brief §4 worked example: "add a gap about remote work" → mutate.
    assert classify_intent_heuristic(
        "add a gap about remote work", target_is_focus=False,
    ) == "mutate"
    assert classify_intent_heuristic(
        "change the methodology to qualitative", target_is_focus=False,
    ) == "mutate"


def test_classify_ambiguous_returns_none():
    # Caller falls back to default (mutate) for safety — heuristic stays
    # conservative so false-positive reads can't silently drop mutations.
    assert classify_intent_heuristic("hmm", target_is_focus=False) is None


# --- read_slice (pure, no writes) -------------------------------------------

def test_read_slice_returns_llm_content():
    cs = ContextStore(m2_literature={"research_gaps": ["gap A", "gap B"]})
    llm = _fake_llm("Gap 2 is about labor markets.")
    out = read_slice("M2", "what was gap 2?", cs, llm=llm)
    assert "Gap 2" in out


def test_read_slice_does_not_mutate_context_store():
    # Brief §1.5 contract: "change nothing". read_slice MUST leave the
    # ContextStore byte-for-byte intact — any future change here is a
    # regression in the contract. (We compare by value, not identity:
    # Pydantic v2 may copy dicts on model construction, so an identity
    # check would pass/fail based on Pydantic internals, not our code.)
    expected = {"research_gaps": ["g1"], "confirmed_at": "2026-06-03T00:00:00"}
    cs = ContextStore(m2_literature=dict(expected))
    llm = _fake_llm("ok")
    _ = read_slice("M2", "show me the gaps", cs, llm=llm)
    assert cs.m2_literature == expected


def test_read_slice_empty_module_returns_friendly_message():
    # Brief §8.4 soft-lock UX: don't pretend there's data, don't reroute —
    # just tell the user the module is empty and offer the option.
    cs = ContextStore()
    out = read_slice("M2", "what was gap 2?", cs)  # no LLM needed
    assert "M2" in out
    assert "hasn't been" in out.lower() or "no data" in out.lower()


def test_read_slice_fallback_summary_on_llm_failure():
    # If the LLM raises, we DON'T raise back up — turn-level robustness.
    # The fallback summarizes the slice deterministically so the user gets
    # at least the data, even if not the polished prose.
    cs = ContextStore(m2_literature={"research_gaps": ["g1"],
                                       "_awaiting_field": "ignore_me"})
    llm = MagicMock()
    llm.invoke.side_effect = RuntimeError("Gemini down")
    out = read_slice("M2", "show gaps", cs, llm=llm, max_seconds=1)
    assert "M2" in out
    assert "g1" in out
    # Meta keys must NOT appear in the fallback prose.
    assert "_awaiting_field" not in out
    assert "ignore_me" not in out


# --- route_turn intent + graph_v2 read dispatch ------------------------------

def _state(*, cs, focus, message="show me the gaps"):
    return {
        "project_id": None,
        "thread_id": None,
        "messages": [HumanMessage(content=message)],
        "current_module": focus or "M1",
        "context_store": cs,
        "focus": focus,
        "mode": "interactive",
    }


def test_route_turn_returns_intent_tuple(monkeypatch):
    # Backward-compat-breaking change pinned: route_turn returns 3-tuple now.
    # graph_v2 handles both shapes, but downstream callers that read the
    # tuple unpacked must see (picked, result, intent).
    cs = ContextStore(m1_topic={"confirmed_at": "2026-06-03T00:00:00",
                                 "research_title": "X"})
    # cold-start short-circuit DOESN'T fire — M1 already confirmed —
    # so the LLM picker runs. Stub it to return M1 and stub the agent.
    monkeypatch.setattr(router_agent, "_pick_module_via_llm", lambda _s: "M1")
    stub = MagicMock()
    stub.step.return_value = ModuleStepResult(
        assistant_message="ok", context_patch={"research_title": "X"},
        transition=True,
    )
    monkeypatch.setitem(router_agent._AGENT_BY_KEY, "M1", stub)

    out = router_agent.route_turn(_state(cs=cs, focus="M1"))
    assert len(out) == 3
    _, _, intent = out
    assert intent == "continue"   # target == focus


def test_route_turn_cross_module_question_is_read(monkeypatch):
    # Brief §4 worked example: focus=M4, user asks "what was gap 2?" →
    # router picks M2, intent=read. The module step is NOT called; the
    # read_handler answers from the slice directly.
    cs = ContextStore(
        m1_topic={"confirmed_at": "2026-06-03T00:00:00"},
        m2_literature={"confirmed_at": "2026-06-03T00:00:00",
                       "research_gaps": ["g1", "g2"]},
        m4_analysis={"confirmed_at": "2026-06-03T00:00:00"},
    )
    monkeypatch.setattr(router_agent, "_pick_module_via_llm", lambda _s: "M2")
    m2_stub = MagicMock()
    monkeypatch.setitem(router_agent._AGENT_BY_KEY, "M2", m2_stub)
    # Stub read_slice so the test doesn't make a real Gemini call.
    monkeypatch.setattr(router_agent, "read_slice",
                        lambda target, msg, cs, **kw: f"[read {target}]")

    picked, result, intent = router_agent.route_turn(
        _state(cs=cs, focus="M4", message="remind me what gap 2 was"),
    )
    assert picked == "M2"
    assert intent == "read"
    assert "[read M2]" in result.assistant_message
    # CRITICAL: the module step MUST NOT have been called for a read.
    m2_stub.step.assert_not_called()


def test_route_turn_cross_module_edit_is_mutate(monkeypatch):
    # Brief §4 worked example: focus=M4, user says "add a gap about remote
    # work" → router picks M2, intent=mutate. Module step IS called.
    cs = ContextStore(
        m2_literature={"confirmed_at": "2026-06-03T00:00:00",
                       "research_gaps": ["g1"]},
        m4_analysis={"confirmed_at": "2026-06-03T00:00:00"},
    )
    monkeypatch.setattr(router_agent, "_pick_module_via_llm", lambda _s: "M2")
    m2_stub = MagicMock()
    m2_stub.step.return_value = ModuleStepResult(
        assistant_message="added gap", context_patch={
            "confirmed_at": "2026-06-03T01:00:00",
            "research_gaps": ["g1", "remote work"],
        }, transition=True,
    )
    monkeypatch.setitem(router_agent._AGENT_BY_KEY, "M2", m2_stub)

    _, _, intent = router_agent.route_turn(
        _state(cs=cs, focus="M4",
               message="add a gap about remote work"),
    )
    assert intent == "mutate"
    m2_stub.step.assert_called_once()


def test_graph_v2_read_does_not_propagate_or_shift_focus(monkeypatch):
    # End-to-end: a read MUST leave M3/M4 done (no needs_review propagation)
    # AND must NOT shift focus. This is the brief §1.5 read contract.
    cs = ContextStore(
        m2_literature={"confirmed_at": "2026-06-03T00:00:00",
                       "research_gaps": ["g1"]},
        m3_design={"confirmed_at": "2026-06-03T00:00:00"},
        m4_analysis={"confirmed_at": "2026-06-03T00:00:00"},
    )
    monkeypatch.setattr(graph_v2, "route_turn", lambda state: (
        "M2",
        ModuleStepResult(
            assistant_message="Gap 1 is g1",
            # context_patch == existing slice → no change.
            context_patch=cs.m2_literature,
            transition=True,
        ),
        "read",
    ))

    patch = graph_v2.router_agent_node({
        "project_id": None, "thread_id": None,
        "messages": [HumanMessage(content="what was gap 1?")],
        "current_module": "M4", "context_store": cs, "focus": "M4",
        "mode": "interactive",
    })

    # Focus stays put.
    assert patch["focus"] == "M4", (
        "read intent must NOT shift focus (brief §1.5 'focus stays put')"
    )
    # No propagation — M3 was done, must still be done (not needs_review).
    assert patch["status"].M3 == "done"
    assert "_needs_review" not in (patch["context_store"].m3_design or {})


def test_router_agent_module_unused(monkeypatch):
    # Tighten import: ensure the new wiring doesn't accidentally orphan the
    # read_handler module (a common silent breakage when wiring is wrong).
    # Asserts the module exposes the public surface the router uses.
    assert hasattr(read_handler, "read_slice")
    assert hasattr(read_handler, "classify_intent_heuristic")
    assert read_handler.Intent.__class__.__name__ == "_LiteralGenericAlias" or \
        str(read_handler.Intent).startswith("typing.Literal")

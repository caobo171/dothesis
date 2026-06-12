"""Brief §1.5 propagation tests for the v2 router-agent graph node.

The router_agent_node in graph_v2.py owns the per-turn state patch. PR #2
makes it write `focus`, recompute `status`, and propagate `_needs_review`
to downstream done modules on a cross-module mutate. These tests pin that
behavior without touching the real Gemini router (route_turn is stubbed).
"""
from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage

from orchestrator import graph_v2
from orchestrator.agents.base import ModuleStepResult
from orchestrator.state import ContextStore


def _state(*, cs: ContextStore, focus=None, messages=None):
    """Minimal OrchestratorState for the node — just what router_agent_node reads."""
    return {
        "project_id": None,
        "thread_id": None,
        "messages": messages or [HumanMessage(content="hi")],
        "current_module": "M1",
        "context_store": cs,
        "focus": focus,
        "mode": "interactive",
    }


def _stub_route_turn(monkeypatch, picked: str, patch: dict, *,
                     transition=True, intent: str = "mutate"):
    """Replace route_turn so the test controls (picked module, context_patch, intent).

    The real route_turn calls the Gemini router + the picked module's step();
    we want neither. The patch IS the module's slice write — it lands on the
    new ContextStore unchanged. `intent` controls which §1.5 branch fires in
    router_agent_node (mutate = propagate; continue/read = don't).
    """
    result = ModuleStepResult(
        assistant_message="ok", context_patch=patch,
        transition=transition, needs_user_reply=not transition,
    )
    monkeypatch.setattr(graph_v2, "route_turn",
                        lambda state: (picked, result, intent))
    return result


def test_cross_module_mutate_propagates_needs_review_downstream(monkeypatch):
    # Focus is M4 (user was working on analysis). Router picks M2 — that's
    # a cross-module mutate per brief §1.5. M2's mutate must flag M3 + M4
    # (both done) as needs_review. M5 is empty → stays locked, no flag.
    cs = ContextStore(
        m2_literature={"confirmed_at": "2026-06-03T00:00:00", "research_gaps": ["old"]},
        m3_design={"confirmed_at": "2026-06-03T00:00:00", "paradigm": "quantitative"},
        m4_analysis={"confirmed_at": "2026-06-03T00:00:00", "data_type_detected": "SPSS"},
    )
    _stub_route_turn(monkeypatch, picked="M2", patch={
        "confirmed_at": "2026-06-03T01:00:00",
        "research_gaps": ["new gap added"],
    })

    patch = graph_v2.router_agent_node(_state(cs=cs, focus="M4"))
    new_cs = patch["context_store"]

    # The mutated module itself is unchanged (no self-flag) — user just
    # edited it; surfacing "needs_review" on the thing they edited would
    # loop on every confirm.
    assert "_needs_review" not in new_cs.m2_literature

    # Downstream DONE modules flagged.
    assert new_cs.m3_design.get("_needs_review") is True
    assert new_cs.m4_analysis.get("_needs_review") is True

    # status map reflects the propagation.
    assert patch["status"].M2 == "done"
    assert patch["status"].M3 == "needs_review"
    assert patch["status"].M4 == "needs_review"
    assert patch["status"].M5 == "locked"


def test_same_module_continue_does_not_propagate(monkeypatch):
    # Focus is M2 and router picks M2 → "continue", NOT a mutate per §1.5.
    # M3 was done; it must stay done (no needs_review). The propagation
    # rule explicitly excludes same-module work — otherwise every M2
    # clarification turn would noise downstream modules into review.
    cs = ContextStore(
        m2_literature={"confirmed_at": "2026-06-03T00:00:00"},
        m3_design={"confirmed_at": "2026-06-03T00:00:00"},
    )
    _stub_route_turn(monkeypatch, picked="M2", intent="continue", patch={
        "confirmed_at": "2026-06-03T01:00:00",
        "research_gaps": ["additional gap"],
    })

    patch = graph_v2.router_agent_node(_state(cs=cs, focus="M2"))
    assert patch["status"].M3 == "done", (
        "same-module continue must NOT flag downstream needs_review"
    )
    assert "_needs_review" not in (patch["context_store"].m3_design or {})


def test_mutate_shifts_focus_to_target(monkeypatch):
    # Brief §1.5 — mutate shifts focus to the mutated module. Continue
    # leaves focus alone.
    cs = ContextStore(
        m1_topic={"confirmed_at": "2026-06-03T00:00:00"},
        m4_analysis={"confirmed_at": "2026-06-03T00:00:00"},
    )
    _stub_route_turn(monkeypatch, picked="M1", patch={
        "confirmed_at": "2026-06-03T01:00:00",
        "research_title": "edited title",
    })

    patch = graph_v2.router_agent_node(_state(cs=cs, focus="M4"))
    assert patch["focus"] == "M1", "mutate must shift focus to the target"


def test_continue_preserves_focus(monkeypatch):
    cs = ContextStore(m2_literature={"research_gaps": ["g1"]})
    _stub_route_turn(monkeypatch, picked="M2", intent="continue",
                     patch={"research_gaps": ["g1", "g2"]},
                     transition=False)

    patch = graph_v2.router_agent_node(_state(cs=cs, focus="M2"))
    assert patch["focus"] == "M2", "same-module continue must preserve focus"


def test_cold_start_seeds_focus_to_picked(monkeypatch):
    # On the first turn focus is None — the cold-start short-circuit picks
    # M1, and we seed focus from it. No propagation possible (nothing was
    # done before the very first turn).
    _stub_route_turn(monkeypatch, picked="M1", intent="continue",
                     patch={"research_title": "First topic"})

    patch = graph_v2.router_agent_node(_state(cs=ContextStore(), focus=None))
    assert patch["focus"] == "M1"
    assert patch["status"].M1 == "in_progress"


def test_mutate_without_actual_slice_change_does_not_propagate(monkeypatch):
    # Edge case: route_turn picks M2, but the step paused for user input
    # without writing (clarification question). context_patch == old slice
    # → not a mutate per §1.5, no propagation. Without this guard, every
    # M2 clarification turn while focus=M4 would noise M3/M4 into review.
    cs = ContextStore(
        m2_literature={"_awaiting_field": "research_gaps", "confirmed_at": None},
        m3_design={"confirmed_at": "2026-06-03T00:00:00"},
    )
    _stub_route_turn(monkeypatch, picked="M2",
                     patch={"_awaiting_field": "research_gaps", "confirmed_at": None},
                     transition=False)

    patch = graph_v2.router_agent_node(_state(cs=cs, focus="M4"))
    assert patch["status"].M3 == "done", (
        "no slice change → not a mutate → no propagation"
    )

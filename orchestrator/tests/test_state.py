from datetime import datetime
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage

from orchestrator.state import (
    ContextStore, ModuleStatusMap, OrchestratorState,
    compute_status_map, get_module_slice, modules_after,
    next_unconfirmed_module, propagate_needs_review,
)


def test_context_store_default_empty():
    cs = ContextStore()
    for m in ("m1_topic", "m2_literature", "m3_design", "m4_analysis", "m5_writing"):
        assert getattr(cs, m) is None


def test_context_store_roundtrip_jsonb():
    cs = ContextStore(m1_topic={"research_title": "X"})
    blob = cs.model_dump()
    assert blob["m1_topic"] == {"research_title": "X"}
    cs2 = ContextStore.model_validate(blob)
    assert cs2.m1_topic == {"research_title": "X"}


def test_next_unconfirmed_walks_in_order():
    cs = ContextStore()
    assert next_unconfirmed_module(cs) == "M1"
    cs.m1_topic = {"confirmed_at": "2026-05-26T00:00:00"}
    assert next_unconfirmed_module(cs) == "M2"
    cs.m2_literature = {"confirmed_at": "2026-05-26T00:00:00"}
    cs.m3_design = {"confirmed_at": "2026-05-26T00:00:00"}
    cs.m4_analysis = {"confirmed_at": "2026-05-26T00:00:00"}
    assert next_unconfirmed_module(cs) == "M5"
    cs.m5_writing = {"confirmed_at": "2026-05-26T00:00:00"}
    assert next_unconfirmed_module(cs) == "DONE"


def test_get_module_slice_returns_only_relevant_field():
    cs = ContextStore(m1_topic={"a": 1}, m2_literature={"b": 2})
    assert get_module_slice(cs, "M1") == {"a": 1}
    assert get_module_slice(cs, "M2") == {"b": 2}
    assert get_module_slice(cs, "M3") == {}


# --- compute_status_map (brief §1.4 — workflow status map) -------------------
# These tests pin the four-state semantics from the target-architecture design
# (docs/architecture/2026-06-03-researchflow-target-architecture.md §1). The
# map is PURE-DERIVED from ContextStore — no hidden state, no overrides.

def test_compute_status_map_empty_is_all_locked():
    # Untouched project → every module is locked. Brief §8.4 calls this a
    # SOFT lock (recommendation), so the router/handlers must still answer
    # for any module; locked is purely a UI/status hint.
    sm = compute_status_map(ContextStore())
    assert sm.model_dump() == {
        "M1": "locked", "M2": "locked", "M3": "locked",
        "M4": "locked", "M5": "locked",
    }


def test_compute_status_map_confirmed_at_marks_done():
    # confirmed_at is the authoritative approval signal in the live flow —
    # mirrors orchestrator.artifacts.readiness() which trusts confirmation
    # over the content-only DoD so a user-approved-but-imperfect slice
    # doesn't flap back to in_progress.
    cs = ContextStore(m1_topic={"confirmed_at": "2026-06-03T00:00:00"})
    sm = compute_status_map(cs)
    assert sm.M1 == "done"
    assert sm.M2 == "locked"  # downstream untouched → still locked


def test_compute_status_map_content_without_confirm_is_in_progress():
    # User has started M1 (title set) but hasn't confirmed yet — that's
    # in_progress, not done. The router uses this to decide whether a
    # "what was my topic" question should hit M1's read handler (any
    # content) or fall through to a generic answer (locked).
    cs = ContextStore(m1_topic={"research_title": "Gen Z TikTok marketing"})
    sm = compute_status_map(cs)
    assert sm.M1 == "in_progress"


def test_compute_status_map_meta_only_slice_stays_locked():
    # _awaiting_field / _source / _awaiting_confirm are ROUTING markers,
    # not module content. A slice carrying only meta keys must NOT promote
    # to in_progress — otherwise the status map flips the moment the
    # supervisor opens the module, defeating the locked → in_progress
    # transition signal the UI relies on.
    cs = ContextStore(m1_topic={"_awaiting_field": "research_title",
                                 "_source": "imported"})
    sm = compute_status_map(cs)
    assert sm.M1 == "locked"


def test_compute_status_map_needs_review_marker_overrides_done():
    # PR #2 (router rewrite) will set _needs_review on downstream slices
    # when an upstream mutate invalidates them. The marker must WIN over
    # confirmed_at — that's the whole point of the brief §1.5 propagation
    # rule: "this was done, but an upstream change means you should look
    # at it again before trusting it."
    cs = ContextStore(m1_topic={"confirmed_at": "2026-06-03T00:00:00",
                                 "_needs_review": True})
    sm = compute_status_map(cs)
    assert sm.M1 == "needs_review"


def test_compute_status_map_dod_pass_without_confirm_is_done():
    # An imported slice that contains every required field is "done" even
    # without confirmed_at — matches the entry-wizard contract (brief §9):
    # importing a fully-formed model marks the module done without forcing
    # the user back through the confirm step.
    cs = ContextStore(m1_topic={
        "research_title": "X", "field": "Sociology",
        "research_type": "quantitative", "target_population": "Gen Z",
        "scope": "EU", "objectives": ["o1"], "research_questions": ["rq1"],
    })
    sm = compute_status_map(cs)
    assert sm.M1 == "done"


def test_module_status_map_default_is_all_locked():
    # The default ModuleStatusMap (no kwargs) matches an untouched project,
    # so callers that lose the ContextStore (e.g. legacy code paths during
    # the dual-write window) still get a coherent status.
    sm = ModuleStatusMap()
    assert sm.M1 == sm.M2 == sm.M3 == sm.M4 == sm.M5 == "locked"


def test_context_store_module_summaries_default_empty():
    # The summaries dict ships in PR #1 so PR #4 (tiered memory) can write
    # to it without another migration. Default = no compaction has run.
    assert ContextStore().module_summaries == {}


# --- modules_after + propagate_needs_review (brief §1.5 — mutate ⇒ ⚠) --------
# A mutate to module M flags ALL strictly-downstream done modules as
# needs_review. This is the §1.5 propagation rule that makes "edit M2 while
# in M4" honest about its blast radius — M3, M4, M5 (if done) all surface
# as "this might be stale now."

def test_modules_after_returns_strict_downstream():
    # "After" is strict — the mutated module is NOT in its own downstream.
    # M2's downstream is M3..M5; M5 has no downstream.
    assert modules_after("M2") == ("M3", "M4", "M5")
    assert modules_after("M5") == ()
    assert modules_after("M1") == ("M2", "M3", "M4", "M5")


def test_propagate_needs_review_marks_done_downstream():
    # M2 gets edited; M3 was done → must surface needs_review. M4 is empty
    # (locked), so nothing to invalidate there.
    cs = ContextStore(
        m2_literature={"confirmed_at": "2026-06-03T00:00:00", "research_gaps": ["g1"]},
        m3_design={"confirmed_at": "2026-06-03T00:00:00", "paradigm": "quantitative"},
    )
    new_cs = propagate_needs_review(cs, mutated="M2")
    sm = compute_status_map(new_cs)
    assert sm.M2 == "done"             # the mutated module itself is unaffected
    assert sm.M3 == "needs_review"     # downstream done → flagged
    assert sm.M4 == "locked"           # empty, was never done → no flag


def test_propagate_needs_review_skips_non_done_downstream():
    # Brief §1.5: only flag DONE downstream. An in_progress or locked module
    # has nothing committed to invalidate, so we leave it alone — otherwise
    # the user sees a "⚠" on a step they haven't started, which is noise.
    cs = ContextStore(
        m2_literature={"confirmed_at": "2026-06-03T00:00:00"},
        m3_design={"paradigm": "quantitative"},   # content but not confirmed
    )
    new_cs = propagate_needs_review(cs, mutated="M2")
    sm = compute_status_map(new_cs)
    assert sm.M3 == "in_progress"       # NOT promoted to needs_review


def test_propagate_needs_review_is_pure_returns_new_store():
    # Pure function — must NOT mutate the input ContextStore. The router
    # writes the returned store back to state in one place; in-place mutation
    # would silently leak `_needs_review` markers through cached references.
    original_m3 = {"confirmed_at": "2026-06-03T00:00:00"}
    cs = ContextStore(
        m2_literature={"confirmed_at": "2026-06-03T00:00:00"},
        m3_design=original_m3,
    )
    new_cs = propagate_needs_review(cs, mutated="M2")
    # Input slice untouched.
    assert "_needs_review" not in original_m3
    assert "_needs_review" not in (cs.m3_design or {})
    # Output slice carries the marker.
    assert new_cs.m3_design.get("_needs_review") is True


def test_propagate_needs_review_noop_when_no_done_downstream():
    # M5 has no downstream — propagation is a no-op (but must still return
    # a valid ContextStore so callers can unconditionally chain it).
    cs = ContextStore(m5_writing={"confirmed_at": "2026-06-03T00:00:00"})
    new_cs = propagate_needs_review(cs, mutated="M5")
    assert new_cs.m5_writing == cs.m5_writing


def test_orchestrator_state_accepts_focus_and_status():
    # focus and status are TypedDict total=False additions — old callers
    # work unchanged; new callers (PR #2 router) populate them.
    from uuid import uuid4
    state: OrchestratorState = {
        "project_id": uuid4(),
        "thread_id": uuid4(),
        "messages": [],
        "context_store": ContextStore(),
        "focus": "M2",
        "status": ModuleStatusMap(M1="done", M2="in_progress"),
        "mode": "interactive",
    }
    assert state["focus"] == "M2"
    assert state["status"].M1 == "done"
    assert state["status"].M2 == "in_progress"


def test_orchestrator_state_construction():
    state: OrchestratorState = {
        "project_id": uuid4(),
        "thread_id": uuid4(),
        "messages": [HumanMessage(content="hi")],
        "current_module": "M1",
        "context_store": ContextStore(),
        "mode": "interactive",
        "user_intent": None,
        "pending_confirmations": [],
    }
    assert state["current_module"] == "M1"
    assert state["mode"] == "interactive"

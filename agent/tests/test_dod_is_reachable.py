"""Whatever a module is graded on, the agent must be allowed to write.

SLICE_OWNERSHIP decides what commit_slice accepts and what load() shows the
agent. The dod_* functions decide when a module is done. They were maintained
independently and drifted: M2 owned one of the five keys dod_literature grades,
M3 owned none of the nine dod_design grades, M4 owned two of the six. Those
modules could not be completed from chat at all — only commit_reconstructed,
which bypasses ownership, could fill them, so a module only ever went green by
import.

It is not a new failure. dod_analysis's docstring already spells it out:
"`data_type_detected` and `results` are not M4-owned (agent/state.py), so on the
imported path there is no way for them to ever arrive — the module sat
in_progress permanently while the agent asked the student to plan an analysis
they had already run". That was patched with an escape hatch for one path
instead of by making the two maps agree.

So this test is behavioural, not a second declaration to keep in sync: it builds
a slice that SATISFIES each DoD and commits it through the real tool. A key that
is graded but unowned raises SliceOwnershipError, naming itself.
"""
import pytest

from agent.state import ProjectStateStore, SliceOwnershipError
from orchestrator.artifacts import (
    dod_analysis, dod_design, dod_literature, dod_topic, dod_writing,
)

# A slice that each DoD reports done for. Written from the DoD, not from the
# ownership map — the point is to catch the two disagreeing.
SATISFYING = {
    "M1": (dod_topic, {
        "research_title": "T", "field": "Marketing", "research_type": "quantitative",
        "target_population": "TikTok shoppers", "scope": "HCMC",
        "objectives": ["O1"], "research_questions": ["RQ1"],
    }),
    "M2": (dod_literature, {
        "research_state_summary": "The field has…",
        "theoretical_framework": "Source credibility model",
        "literature_review_doc": "Chapter 2 draft…",
        "research_gaps": [{"description": "a gap"}],
        "citation_list": [{"author": "Ohanian", "year": 1990}],
    }),
    "M3": (dod_design, {
        "paradigm": "quantitative", "design": "cross-sectional survey",
        "tool": "SPSS", "sampling_strategy": "purposive", "target_sample_size": 303,
        "conceptual_model": {"nodes": [{"id": "ATT"}], "edges": []},
    }),
    "M4": (dod_analysis, {
        "data_type_detected": "Quantitative",
        "analysis_outline": {"sections": [{"name": "EFA"}]},
        "results": {"hypothesis_tests": [{"id": "H1"}]},
    }),
    "M5": (dod_writing, {
        "final_sections": [
            {"chapter_name": n, "title": n, "prose": "body"}
            for n in ("intro", "lit_review", "methodology", "results", "conclusion")
        ],
    }),
}


@pytest.mark.parametrize("module", sorted(SATISFYING))
def test_the_slice_really_does_satisfy_the_dod(module):
    """Guards the fixture itself: a slice that does not pass would make the
    commit test below prove nothing."""
    dod, slice_ = SATISFYING[module]
    result = dod(slice_)
    assert result.done, f"{module} fixture is not DoD-complete: {result.gaps}"


@pytest.mark.parametrize("module", sorted(SATISFYING))
def test_the_agent_can_commit_a_dod_complete_slice(module, tmp_path):
    """The actual invariant. SliceOwnershipError names the offending keys, so a
    failure here reads as "M3 does not own ['paradigm', 'design', …]"."""
    _dod, slice_ = SATISFYING[module]
    store = ProjectStateStore(str(tmp_path))
    try:
        store.commit_slice(module, slice_, reason="dod-complete work")
    except SliceOwnershipError as e:
        pytest.fail(f"{module} is graded on keys it may not write — {e}")


@pytest.mark.parametrize("module", sorted(SATISFYING))
def test_a_dod_complete_slice_survives_a_reload(module, tmp_path):
    """Owned is not enough — the keys have to come back, or the DoD grades a
    slice the store has already dropped."""
    _dod, slice_ = SATISFYING[module]
    ProjectStateStore(str(tmp_path)).commit_slice(module, slice_, reason="r")
    reread = ProjectStateStore(str(tmp_path)).load()["contextStore"]
    for key in slice_:
        assert key in reread, f"{module}.{key} did not survive the round trip"


@pytest.mark.parametrize("module", ["M2", "M3", "M4"])
def test_a_dod_complete_slice_earns_its_done(module, tmp_path):
    """And the two gates agree at the end of it: a module whose DoD is satisfied
    can be confirmed done. `confirm_done` runs _has_done_content, a different
    gate — this is where the two would part company again."""
    _dod, slice_ = SATISFYING[module]
    store = ProjectStateStore(str(tmp_path))
    store.commit_slice(module, slice_, reason="r", confirm_done=True)
    assert store.load()["status"][module] == "done"


def test_a_single_classification_does_not_earn_a_done(tmp_path):
    """The new keys must not make the gate weaker than it was: `paradigm` is one
    word, not a finished design chapter."""
    store = ProjectStateStore(str(tmp_path))
    with pytest.raises(ValueError, match="cannot mark"):
        store.commit_slice("M3", {"paradigm": "quantitative"},
                           reason="r", confirm_done=True)


# --- the two gates, when they still disagree ----------------------------------

def test_a_thin_done_says_what_is_still_missing(tmp_path):
    """confirm_done runs _has_done_content (any one earning key). The DoD is far
    stricter and is what the backfill, the roadmap and the export gate use. Both
    stay as they are — tightening the interactive gate would stall students, and
    loosening the DoD would let a hollow module reach the export — but the
    disagreement is now stated instead of surfacing later as a refusal.
    """
    import json

    from agent.tools.state_tools import make_state_tools

    store = ProjectStateStore(str(tmp_path))
    tools = {t.name: t for t in make_state_tools(store)}
    out = json.loads(tools["commit_slice"].func(
        module="M2", reason="found the gaps",
        writes={"research_gaps": [{"description": "a gap"}]},
        confirm_done=True))

    assert "error" not in out
    assert store.load()["status"]["M2"] == "done"
    gaps = " ".join(out["done_but_incomplete"])
    for still_missing in ("research_state_summary", "theoretical_framework",
                          "literature_review_doc", "citation_list"):
        assert still_missing in gaps


def test_a_dod_complete_done_says_nothing(tmp_path):
    import json

    from agent.tools.state_tools import make_state_tools

    _dod, slice_ = SATISFYING["M2"]
    store = ProjectStateStore(str(tmp_path))
    tools = {t.name: t for t in make_state_tools(store)}
    out = json.loads(tools["commit_slice"].func(
        module="M2", reason="r", writes=slice_, confirm_done=True))
    assert "done_but_incomplete" not in out

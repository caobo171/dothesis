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
    for still_missing in ("verified literature source",):
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


def test_committed_smartpls_results_earn_done_without_a_sign_off():
    """The product rule: finished results ARE done — no separate confirmation.

    A student who runs SmartPLS themselves and has the agent commit the output
    ends up with an analysis_outline AND populated result tables. The old escape
    required `not analysis_outline` as a proxy for "this came from an import",
    so this slice fell through to the strict gate and failed on `missing
    data_type_detected` + `results is empty` — the numbers being in
    `analysis_results`, which is where this path puts them. The roadmap showed
    M4 at 5/5 while its status read in_progress.
    """
    from orchestrator.artifacts import dod_analysis

    committed = {
        "analysis_outline": ["Mô hình đo lường", "Giá trị phân biệt"],
        "analysis_results": {
            "sample": {"n": 311},
            "measurement_model": [{"construct": "ATT", "items": [{"item": "ATT_1"}]}],
            "hypothesis_tests": [{"hypothesis": "H1", "beta": 0.269, "supported": True}],
        },
    }
    assert dod_analysis(committed).done is True


def test_an_analysis_slice_with_only_bookkeeping_is_not_done():
    """The escape keys off RESULT tables, not "the dict is non-empty" — a slice
    that has only picked up housekeeping must not earn a done."""
    from orchestrator.artifacts import dod_analysis

    bookkeeping = {
        "analysis_outline": ["Mô hình đo lường"],
        "analysis_results": {"source_figures": {"measurement_model": "/tmp/x.png"}},
    }
    d = dod_analysis(bookkeeping)
    assert d.done is False
    assert d.gaps


def test_a_conversationally_committed_design_is_read_where_it_is_stored():
    """M3 keeps the same five facts in two shapes.

    `M3Output` declares them flat; the conversational path commits a nested
    `methodology` dict. The gate read only the flat shape, so a project with
    every fact present reported "missing paradigm, missing design, missing tool,
    missing sampling_strategy" — none of them missing, all of them elsewhere.
    """
    from orchestrator.artifacts import dod_design

    nested = {
        "methodology": {
            "paradigm": "quantitative",
            "design": "cross-sectional survey",
            "software": "SmartPLS",          # what this path calls `tool`
            "sampling_strategy": "purposive sampling of adults in Vietnam",
        },
        "sample_plan": {"target_n": 300},
        "conceptual_model": {"nodes": [{"id": "ATT"}], "edges": []},
    }
    assert dod_design(nested).gaps == []

    # The flat shape keeps working, and still wins when both are present.
    flat = {**nested, "tool": "SPSS"}
    assert dod_design(flat).done is True


def test_a_design_that_names_none_of_the_five_still_reports_them():
    """The resolver must not turn "look in more places" into "never missing"."""
    from orchestrator.artifacts import dod_design

    d = dod_design({"methodology": {"analysis_plan": ["bootstrap"]}})
    assert d.done is False
    assert set(d.gaps) == {
        "missing paradigm", "missing design", "missing tool",
        "missing sampling_strategy", "missing target_sample_size",
    }


def test_a_realized_sample_closes_the_planning_field_but_not_the_warning():
    """Keep the requirement, satisfy it from what the study actually collected.

    target_sample_size is a PLAN. A study with 311 valid responses has answered
    "how many?" more strongly than any target could, so it must not sit
    in_progress on a planning field it has outgrown. What it has NOT answered is
    "why that many?" — and that stays preflight's question, not this gate's, so
    the student is told before the defense without being blocked before it.
    """
    from agent.preflight import preflight_check
    from agent.state import _dod_satisfied

    m3 = {
        "methodology": {"paradigm": "quantitative", "design": "cross-sectional survey",
                        "software": "SmartPLS", "sampling_strategy": "purposive"},
        "conceptual_model": {"nodes": [{"id": "ATT"}], "edges": []},
    }
    flat_store = {**m3, "analysis_results": {"sample": {"valid": 311, "collected": 332},
                                             "hypothesis_tests": [{"hypothesis": "H1"}]}}

    assert _dod_satisfied("M3", flat_store) is True
    # …and without any results, the planning field is still genuinely missing.
    assert _dod_satisfied("M3", dict(m3)) is False

    warnings = preflight_check({"m3_design": m3})
    assert any("Sample size not planned" in w for w in warnings), warnings


def test_a_fielded_instrument_backs_the_design_step():
    """A student who arrives with SmartPLS output has an instrument by
    definition — 42 indicators, each with a loading computed from 311 real
    responses. `instrument.items` holds the item WORDING, which they never
    typed in; the step is labelled "build the scale", which they demonstrably
    did. Leaving it unsatisfied asked them to design a questionnaire they had
    already fielded.
    """
    from agent.preflight import preflight_check
    from agent.roadmap import satisfied_substeps

    measured = {
        "instrument": {"items": []},
        "conceptual_model": {"nodes": [{"id": "ATT"}], "edges": []},
        "hypotheses": [{"id": "H1"}],
        "methodology": {"paradigm": "quantitative"},
        "analysis_results": {"measurement_model": [
            {"construct": "ATT", "items": [{"item": "ATT_1", "loading": 0.85}]},
        ]},
    }
    assert "design_instrument" in satisfied_substeps("M3", {"contextStore": measured})

    # The wording is still missing, and preflight is now the one place saying so.
    assert any("questionnaire instrument" in w
               for w in preflight_check({"m3_design": measured}))


def test_an_unmeasured_study_still_has_to_build_its_instrument():
    """The escape is evidence of MEASUREMENT, not a way around the step. A
    design-stage project with no data has nothing to stand in for the scale."""
    from agent.roadmap import satisfied_substeps

    design_stage = {
        "instrument": {"items": []},
        "conceptual_model": {"nodes": [{"id": "ATT"}], "edges": []},
        "analysis_results": {"measurement_model": []},
    }
    assert "design_instrument" not in satisfied_substeps("M3", {"contextStore": design_stage})
    # And a spec with no items is still not an instrument — the original guard.
    spec_only = {**design_stage,
                 "instrument": {"constructs": ["ATT"], "items_per_construct": 5}}
    assert "design_instrument" not in satisfied_substeps("M3", {"contextStore": spec_only})

"""Pure-derivation tests for the coaching roadmap. Position is computed from
persisted artifacts (never model-narrated), so these assert the snap-to-nearest
milestone behavior directly, with no store or LLM."""
from agent.roadmap import ROADMAP, derive_substep


def _state(cs=None, status=None, focus="M1"):
    return {"contextStore": cs or {}, "status": status or {m: "locked" for m in ROADMAP},
            "focus": focus}


def test_m1_untouched_is_first_substep():
    assert derive_substep("M1", _state()) == "frame_topic"


def test_m1_title_only_advances_to_questions():
    assert derive_substep("M1", _state({"research_title": "T"})) == "derive_questions"


def test_m1_complete_returns_none():
    s = _state({"research_title": "T", "research_questions": ["Q"]})
    assert derive_substep("M1", s) is None


def test_m2_sources_but_no_gaps_is_find_gaps():
    assert derive_substep("M2", _state({"literature_sources": [{"title": "x"}]})) == "find_gaps"


def test_derived_substep_is_always_in_spine_or_none():
    for m in ROADMAP:
        sub = derive_substep(m, _state())
        assert sub is None or sub in ROADMAP[m]

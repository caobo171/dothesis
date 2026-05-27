"""Tests for M5Agent._extract_context_slice + _collect_references."""
from orchestrator.agents.m5_writing import M5Agent
from orchestrator.state import ContextStore


def test_extract_context_slice_returns_full_shape():
    agent = M5Agent()
    cs = ContextStore(
        m1_topic={"research_title": "TL → EE", "field": "Management",
                   "research_type": "quantitative", "language": "en",
                   "objectives": ["O1"], "research_questions": ["RQ1"],
                   "target_population": "SME emp", "scope": "VN 2026"},
        m2_literature={"literature_review_doc": "lit text",
                        "research_gaps": [{"description": "g1"}]},
        m3_design={"paradigm": "quantitative", "design": "PLS-SEM",
                    "tool": "SmartPLS", "conceptual_model": {"constructs": ["TL"]},
                    "scale_items": [{"construct": "TL", "items": ["I1"]}],
                    "sampling_strategy": "random", "target_sample_size": 200},
        m4_analysis={"data_type_detected": "SmartPLS",
                      "results": {"Outer Loadings": {"step_name": "Outer Loadings"}},
                      "qual_codes": [], "qual_themes": []},
    )
    out = agent._extract_context_slice(cs)
    assert out["research_title"] == "TL → EE"
    assert out["paradigm"] == "quantitative"
    assert out["design"] == "PLS-SEM"
    assert out["tool"] == "SmartPLS"
    assert "Outer Loadings" in out["results"]
    assert out["language"] == "en"


def test_extract_context_slice_handles_none_slices():
    """Each upstream module's slice may be None on a freshly-created project."""
    agent = M5Agent()
    cs = ContextStore()
    out = agent._extract_context_slice(cs)
    assert out["research_title"] is None
    assert out["paradigm"] is None
    assert out["objectives"] == []
    assert out["research_gaps"] == []
    assert out["results"] == {}
    assert out["language"] == "en"  # default fallback


def test_collect_references_dedupes_across_gaps():
    agent = M5Agent()
    context = {
        "research_gaps": [
            {"description": "g1", "supporting_papers": [
                {"author": "Bass", "year": 1990, "title": "Leadership"},
                {"author": "Avolio", "year": 2009, "title": "Auth"},
            ]},
            {"description": "g2", "supporting_papers": [
                {"author": "Bass", "year": 1990, "title": "Leadership"},  # dup
                {"author": "Smith", "year": 2020, "title": "S"},
            ]},
        ],
    }
    refs = agent._collect_references(context)
    keys = {(r["author"], r["year"]) for r in refs}
    assert len(refs) == 3
    assert ("Bass", 1990) in keys
    assert ("Avolio", 2009) in keys
    assert ("Smith", 2020) in keys

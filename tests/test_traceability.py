"""Gap→hypothesis→discussion traceability (§3.2/§3.8a) — all soft/advisory."""
from agent.coherence import traceability_findings, validate_coherence


def test_hypothesis_without_gap_flagged():
    m2 = {"literature_sources": [{"title": "x"}], "research_gaps": [{"gap": "No study links transformational leadership to remote engagement"}]}
    m3 = {"hypotheses": ["H1: Transformational leadership affects remote engagement",
                         "H2: Weather patterns influence coffee prices"]}  # H2 unrelated
    f = traceability_findings(m2, m3, {})
    checks = [x for x in f if x["check"] == "traceability.hypothesis_gap"]
    assert len(checks) == 1
    assert all(x["severity"] == "soft" for x in f)


def test_no_gaps_recorded():
    f = traceability_findings({"literature_sources": [{"title": "x"}]}, {"hypotheses": ["H1: X affects Y"]}, {})
    assert any(x["check"] == "traceability.no_gaps" for x in f)


def test_grounded_hypothesis_clean():
    m2 = {"literature_sources": [{"title": "x"}], "research_gaps": [{"gap": "leadership engagement remote"}]}
    m3 = {"hypotheses": ["H1: leadership drives engagement in remote teams"]}
    assert not [x for x in traceability_findings(m2, m3, {}) if x["check"] == "traceability.hypothesis_gap"]


def test_discussion_without_citation_flagged():
    chapters = {"discussion": "H1 was supported, showing a strong effect on the outcome variable "
                              "which confirms our theoretical expectation clearly here.\n\n"
                              "H2 was supported and aligns with prior work (Smith, 2020)."}
    f = traceability_findings({"literature_sources": [{"title": "x"}]}, {}, chapters)
    uncited = [x for x in f if x["check"] == "traceability.discussion_uncited"]
    assert len(uncited) == 1  # only H1's paragraph lacks a citation


def test_all_soft_never_raise():
    assert traceability_findings(None, None, None) == []
    for x in traceability_findings({"research_gaps": ["g"]}, {"hypotheses": ["H1: x affects y"]},
                                   {"discussion": "H1 discussed."}):
        assert x["severity"] == "soft"


def test_rides_validate_coherence():
    nested = {"m2_literature": {"literature_sources": [{"title": "x"}], "research_gaps": []},
              "m3_design": {"hypotheses": ["H1: leadership affects engagement"]}}
    agg = validate_coherence(nested)
    assert any(f["check"] == "traceability.no_gaps" for f in agg["findings"])
    assert agg["hard"] == 0  # traceability never blocks

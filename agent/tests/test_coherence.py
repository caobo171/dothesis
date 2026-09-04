"""Coherence gate (roadmap #6): registry, prose extraction, checks, entry points."""
import json

import pytest

from agent.coherence import (
    build_registry, check_coherence, coverage_findings, extract_number_claims,
    normalize_hypothesis_id, segment_sentences, validate_coherence, validate_m5_sections,
)

HYPS = ["H1: LS has a positive effect on PI"]
CM = {"nodes": [{"id": "n1", "label": "LS"}, {"id": "n2", "label": "PI"}],
      "edges": [{"id": "H1", "source": "n1", "target": "n2", "effect_type": "positive",
                 "hypothesis": "LS positively affects PI"}]}
AR = {"hypothesis_tests": [{"id": "r-H1", "hypothesis": "H1", "path": "LS → PI",
                           "numbers": {"beta": 0.3391, "t": 7.01, "p": "<0.001", "f2": 0.18},
                           "decision": "supported"}],
      "structural_model": {"r2": {"PI": 0.56}}}


# --- id normalization -------------------------------------------------------

@pytest.mark.parametrize("x,expected", [
    ("H1", "H1"), ("h1", "H1"), ("r-H1", "H1"), ("H12", "H12"),
    ("H1: LS has a positive effect", "H1"), ("Giả thuyết H2", "H2"), ("Hypothesis 3", "H3"),
    ({"id": "H1"}, "H1"), ({"label": "H2"}, "H2"), ({"statement": "H3: x"}, "H3"),
    (None, None), ({}, None), ("the moderating role", None),
])
def test_normalize_id(x, expected):
    assert normalize_hypothesis_id(x) == expected


# --- prose extraction -------------------------------------------------------

def test_segment_keeps_decimals():
    s = segment_sentences("H1 was supported (β = 0.34, p < .001). H2 was not.")
    assert len(s) == 2


@pytest.mark.parametrize("text,metric,val", [
    ("β = .34", "beta", 0.34), ("beta = 0.34", "beta", 0.34), ("β = −0.34", "beta", -0.34),
    ("β = –0.34", "beta", -0.34), ("hệ số hồi quy = 0,34", "beta", 0.34),
    ("R² = 0.56", "r2", 0.56), ("t = 7.01", "t", 7.01), ("f² = 0.18", "f2", 0.18),
])
def test_number_extraction(text, metric, val):
    claims = extract_number_claims(text)
    assert any(c["metric"] == metric and abs(c["value"] - val) < 1e-9 for c in claims)


def test_p_threshold_and_noise():
    assert any(c["metric"] == "p" and c.get("threshold") for c in extract_number_claims("p < .001"))
    assert extract_number_claims("published in (2024), see (Nguyen, 2020)") == []


# --- coverage (CO1 delegation + CO2) ----------------------------------------

def test_coverage_normalized_matching_no_miss():
    # H1 covered by an r-H1-only entry → no coverage finding (shipped X2 missed this)
    ar = {"hypothesis_tests": [{"id": "r-H1", "numbers": {}}]}
    assert coverage_findings(["H1"], ar) == []


def test_coverage_miss_keeps_shipped_id():
    f = coverage_findings(["H1", "H2"], {"hypothesis_tests": [{"hypothesis": "H1"}]})
    assert any(x["check"] == "xtable.hypothesis_coverage" and "H2" in x["message"] for x in f)


def test_orphan_result_soft():
    f = coverage_findings(["H1"], {"hypothesis_tests": [{"hypothesis": "H1"}, {"hypothesis": "H9"}]})
    assert any(x["check"] == "coherence.orphan_result" and x["severity"] == "soft" for x in f)


# --- NU1 number mismatch (the hard core) ------------------------------------

def _reg(prose):
    return build_registry(HYPS, CM, AR, {"results": prose, "discussion": prose})


def test_number_match_within_tolerance():
    reg = _reg("H1 was supported (β = .34, p < .001).")  # .34 ≈ stored .3391
    hard = [f for f in check_coherence(reg) if f["severity"] == "hard"]
    assert hard == []


def test_number_mismatch_hard():
    reg = _reg("H1 was supported (β = .31, p < .001).")
    findings = check_coherence(reg)
    assert any(f["check"] == "coherence.number_mismatch" and f["severity"] == "hard" for f in findings)


def test_sign_mismatch_hard():
    reg = build_registry(HYPS, CM,
                         {"hypothesis_tests": [{"hypothesis": "H1", "numbers": {"beta": -0.34}, "decision": "supported"}]},
                         {"results": "Hypothesis H1 yielded a path coefficient of β = .34 in the model.",
                          "discussion": "x" * 30})
    assert any(f["check"] == "coherence.number_mismatch" for f in check_coherence(reg))


def test_p_threshold_agreement():
    reg = _reg("H1: p < .001.")  # stored p is <0.001 threshold → agrees
    assert not any(f["check"] == "coherence.number_mismatch" for f in check_coherence(reg))


# --- direction / decision (soft) --------------------------------------------

def test_direction_m3_m4_soft():
    ar = {"hypothesis_tests": [{"hypothesis": "H1", "numbers": {"beta": -0.30}, "decision": "supported"}]}
    reg = build_registry(HYPS, CM, ar, {"results": "x" * 30, "discussion": "y" * 30})
    f = check_coherence(reg)
    assert any(x["check"] == "coherence.direction_m3_m4" and x["severity"] == "soft" for x in f)


def test_decision_prose_soft():
    reg = _reg("H1 was not supported.")  # stored decision supported
    f = check_coherence(reg)
    assert any(x["check"] == "coherence.decision_prose" and x["severity"] == "soft" for x in f)


# --- severity + determinism contracts ---------------------------------------

def test_only_number_mismatch_is_hard():
    reg = build_registry(HYPS, CM,
                         {"hypothesis_tests": [{"hypothesis": "H1", "numbers": {"beta": -0.30}, "decision": "supported"}]},
                         {"results": "H1 (β = .31), a negative effect, was not supported.", "discussion": "z" * 30})
    hard = {f["check"] for f in check_coherence(reg) if f["severity"] == "hard"}
    assert hard <= {"coherence.number_mismatch"}


def test_entry_points_never_raise_and_deterministic():
    flat = {"hypotheses": HYPS, "conceptual_model": CM, "analysis_results": AR}
    a = validate_m5_sections({"results": "Hypothesis H1 produced a coefficient of β = .31 here.", "discussion": "d" * 30}, flat)
    assert a["hard"] >= 1 and not a["crashed"]
    b = validate_m5_sections({"results": "Hypothesis H1 produced a coefficient of β = .31 here.", "discussion": "d" * 30}, flat)
    assert json.dumps(a) == json.dumps(b)
    # garbage never raises
    assert validate_coherence({"m4_analysis": "not a dict"})["crashed"] is False
    assert validate_m5_sections(None, {})["hard"] == 0


# --- boundary hardening (gap 4): hand-typed table extraction -----------------

from agent.coherence import extract_table_claims


def _reg_with(results_prose):
    return build_registry(HYPS, CM, AR, {"results": results_prose, "discussion": "x" * 40})


def test_table_claim_mismatch_hard_blocks():
    prose = ("Results below.\n\n| H | Path | β | t | p |\n|---|---|---|---|---|\n"
             "| H1 | LS → PI | 0.45 | 7.01 | <0.001 |\n")
    findings = check_coherence(_reg_with(prose))
    assert any(f["check"] == "coherence.number_mismatch" and f["severity"] == "hard" for f in findings)


def test_table_claim_within_tolerance_passes():
    prose = ("| H | β | t | p |\n|---|---|---|---|\n| H1 | 0.34 | 7.01 | <0.001 |\n")
    assert not any(f["check"] == "coherence.number_mismatch" for f in check_coherence(_reg_with(prose)))


def test_rendered_table_still_exempt():
    # same mismatching table wrapped in renderer sentinels → stripped, no finding
    from orchestrator.tools.results_render import render_results_tables, weave
    blocks = render_results_tables({"hypothesis_tests": AR["hypothesis_tests"],
                                    "structural_model": AR["structural_model"]})
    tampered_prose = ("<!--dt-rendered:begin kind=structural_paths sha=deadbeef0000-->\n"
                      "| H | β | t | p |\n|---|---|---|---|\n| H1 | 0.99 | 7.01 | <0.001 |\n"
                      "<!--dt-rendered:end kind=structural_paths-->\n")
    agg = validate_m5_sections({"results": tampered_prose, "discussion": "H1 supported. " + "x" * 30},
                               {"analysis_results": AR, "hypotheses": HYPS, "conceptual_model": CM})
    assert not any(f["check"] == "coherence.number_mismatch" and f["severity"] == "hard"
                   for f in agg.get("findings", []))


def test_table_without_anchor_produces_no_claim():
    prose = "| Metric | β |\n|---|---|\n| Loading | 0.45 |\n"   # no H-id in any row
    assert extract_table_claims(prose) == []


def test_table_eu_commas_parse():
    prose = "| H | β |\n|---|---|\n| H1 | 0,45 |\n"
    claims = extract_table_claims(prose)
    assert claims and abs(claims[0]["value"] - 0.45) < 1e-9


def test_vietnamese_header_maps_to_beta():
    prose = "| GT | Hệ số | t | p |\n|---|---|---|---|\n| H1 | 0.45 | 7.0 | 0.01 |\n"
    metrics = {c["metric"] for c in extract_table_claims(prose)}
    assert "beta" in metrics


# --- gap 4: percent-rendered R² ---------------------------------------------

from agent.coherence import percent_variance_findings

_AR_R2 = {"structural_model": {"r2": {"PI": 0.31}}}


def test_percent_variance_mismatch_hard():
    ch = {"results": "The model explains 56% of the variance in PI, a strong result overall."}
    f = percent_variance_findings(ch, _AR_R2)
    assert any(x["check"] == "coherence.number_mismatch" and x["severity"] == "hard" for x in f)


def test_percent_variance_match_passes():
    ch = {"results": "The model explains 31% of the variance in PI."}
    assert percent_variance_findings(ch, _AR_R2) == []


def test_percent_ambiguous_construct_skipped():
    ar = {"structural_model": {"r2": {"PI": 0.31, "LS": 0.20}}}
    ch = {"results": "Together PI and LS account for 56% of the variance explained."}
    assert not any(x["severity"] == "hard" for x in percent_variance_findings(ch, ar))


def test_percent_vietnamese_phrasing():
    ch = {"results": "Mô hình giải thích 56% phương sai của PI trong nghiên cứu này."}
    assert any(x["severity"] == "hard" for x in percent_variance_findings(ch, _AR_R2))


def test_percent_no_r2_no_finding():
    assert percent_variance_findings({"results": "explains 56% of the variance in PI"}, {}) == []


# --- R² vs its complement ----------------------------------------------------

_R2_STATE = {"structural_model": {"r2": {"PB": 0.716}}}


def _pv(prose):
    from agent.coherence import percent_variance_findings
    return percent_variance_findings({"results": prose}, _R2_STATE)


def test_remaining_percent_is_read_as_the_complement_not_as_r2():
    """"The remaining 28.4%" states 1 - R², not R².

    Read as R² it contradicts a stored 0.716 by 43 points, so the check
    reported a HARD blocking error against a correct, conventional sentence —
    in the student's own imported results chapter. Stating the unexplained
    remainder is standard practice, so this was the common case.
    """
    assert _pv("Phần còn lại 28.4% biến thiên của PB do các yếu tố ngoài mô hình quyết định.") == []
    assert _pv("The remaining 28.4% of the variance in PB may be associated with other variables.") == []
    assert _pv("The 28.4% unexplained variance in PB indicates other factors matter.") == []


def test_a_correct_explained_percentage_still_passes():
    assert _pv("Ba biến giải thích được 71.6% biến thiên của PB.") == []
    assert _pv("The model explained 71.6% of the variance in PB.") == []


def test_a_genuinely_wrong_explained_percentage_still_fails():
    """The complement handling must not become a blanket suppression."""
    out = _pv("The model explained 28.4% of the variance in PB.")
    assert len(out) == 1 and out[0]["severity"] == "hard"


def test_a_genuinely_wrong_remainder_still_fails():
    """A remainder of 50% implies R² = 0.50, which contradicts 0.716."""
    out = _pv("Phần còn lại 50.0% biến thiên của PB chưa được giải thích.")
    assert len(out) == 1 and out[0]["severity"] == "hard"
    assert "UNexplained" in out[0]["message"]


def test_traceability_flags_an_uncited_hypothesis_in_the_conclusion_chapter():
    # The check used to read chapters["discussion"]. After the five-chapter
    # collapse that key is never written, so the check would fire on nothing.
    #
    # `literature_sources` is REQUIRED in the m2 fixture: traceability_findings
    # returns early without it (agent/coherence.py:606, "only meaningful once
    # the project has a literature base"). Verified: with it, the old
    # `discussion` key yields two findings and `conclusion` yields none — which
    # is exactly the red state this test must start from.
    from agent.coherence import traceability_findings
    m2 = {"literature_sources": [{"title": "Davis 1989"}]}
    chapters = {"conclusion": "H1 was supported by the data, plainly.\n\n"
                              "H2 was supported by the data, plainly."}
    out = traceability_findings(m2, {}, chapters)
    assert any(f["check"] == "traceability.discussion_uncited" for f in out)


def test_a_finding_quotes_the_offending_sentence():
    """Naming a chapter is not enough to act on.

    "A paragraph states that 28.4% ..." left the student searching a chapter of
    several thousand words with nothing to search FOR. The quote is what makes
    the report actionable.
    """
    out = _pv("The model explained 28.4% of the variance in PB, which is lower than expected.")
    assert len(out) == 1
    f = out[0]
    assert f["location"]["chapter"] == "results"
    assert "28.4%" in f["location"]["sentence"]
    assert "results chapter" in f["message"]
    assert "Sentence:" in f["message"]
    # the computed value is stated, not just the contradiction
    assert "0.716" in f["message"] and "71.6%" in f["message"]

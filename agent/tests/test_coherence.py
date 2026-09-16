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


def _p_registry(stored_p, prose):
    return build_registry(
        [{"id": "H1", "path": "ATT -> INT"}], {},
        {"hypothesis_tests": [{"hypothesis": "H1", "numbers": {"p": stored_p}}]},
        {"results": prose, "conclusion": "Kết luận tổng hợp."},
    )


def test_p_greater_than_relation_is_preserved_and_can_match_exact_source():
    findings = check_coherence(_p_registry(0.03, "ATT → INT has p > 0.001."))
    assert not any(f["check"] == "coherence.number_mismatch" for f in findings)


def test_p_strict_upper_bound_wrong_against_exact_source_is_hard():
    findings = check_coherence(_p_registry(0.03, "ATT → INT has p < 0.001."))
    assert any(f["check"] == "coherence.number_mismatch" and f["severity"] == "hard" for f in findings)


def test_p_narrower_claim_than_stored_upper_bound_is_inconclusive():
    findings = check_coherence(_p_registry("<0.05", "ATT → INT has p < 0.001."))
    assert not any(f["check"] == "coherence.number_mismatch" for f in findings)


def test_p_exact_claim_outside_stored_upper_bound_is_hard():
    findings = check_coherence(_p_registry("<0.001", "ATT → INT has p = 0.05."))
    assert any(f["check"] == "coherence.number_mismatch" and f["severity"] == "hard" for f in findings)


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


# --- CO3 undiscussed-hypothesis (chapters_present must be True) -------------
#
# check_coherence's chapters_present parameter defaults to False, and _co3
# short-circuits on `not chapters_present` before the mentioned_in/chapter-set
# intersection ever runs (agent/coherence.py _co3, first line). Every OTHER
# test in this file calls check_coherence with its default, so none of them
# reach this logic at all — coherence.undiscussed_hypothesis was previously
# untested in both directions. These two tests pass chapters_present=True
# explicitly so the intersection this task's fix touched is actually
# exercised, not skipped before it runs.

def test_undiscussed_hypothesis_not_flagged_when_only_in_conclusion():
    # H1 has an M4 result (from the shared AR fixture) and appears only in the
    # conclusion chapter, never in results — exactly the five-chapter shape
    # (discussion of findings now lives in 5.2, not a separate chapter). This
    # must NOT be flagged: the fixed _co3 set is {"results", "conclusion"}.
    chapters = {"results": "General results are reported without any hypothesis-specific detail.",
                "conclusion": "H1 was supported by the data and confirms prior findings in the field."}
    reg = build_registry(HYPS, CM, AR, chapters)
    findings = check_coherence(reg, HYPS, AR, True)
    assert not any(f["check"] == "coherence.undiscussed_hypothesis" for f in findings)


def test_undiscussed_hypothesis_still_flagged_when_mentioned_nowhere():
    # H1 has an M4 result but is named in NEITHER results nor conclusion —
    # the check must still fire. Without this half, the test above would pass
    # even if _co3 were disabled outright (e.g. an empty intersection set).
    chapters = {"results": "General results are reported without referencing any hypothesis labels.",
                "conclusion": "General conclusions are drawn without naming any specific hypothesis."}
    reg = build_registry(HYPS, CM, AR, chapters)
    findings = check_coherence(reg, HYPS, AR, True)
    assert any(f["check"] == "coherence.undiscussed_hypothesis" for f in findings)


def test_explicit_registered_path_counts_as_discussion_without_h_label():
    """Generated results prose commonly uses ATT → INT rather than H1."""
    hyps = ["H1: ATT positively affects INT"]
    cm = {"nodes": [{"id": "att", "label": "ATT"}, {"id": "int", "label": "INT"}],
          "edges": [{"id": "H1", "source": "att", "target": "int"}]}
    ar = {"hypothesis_tests": [{"hypothesis": "H1", "path": "ATT → INT", "numbers": {}}]}
    reg = build_registry(hyps, cm, ar, {
        "results": "The ATT → INT path was examined in the structural model.",
        "conclusion": "The conclusion summarizes the model.",
    })
    assert not any(f["check"] == "coherence.undiscussed_hypothesis"
                   for f in check_coherence(reg, hyps, ar, True))


def test_reverse_or_interaction_path_does_not_cover_main_effect():
    """Path aliases must retain direction and cannot consume an MGA interaction."""
    hyps = ["H1: ATT positively affects INT"]
    cm = {"nodes": [{"id": "att", "label": "ATT"}, {"id": "int", "label": "INT"}],
          "edges": [{"id": "H1", "source": "att", "target": "int"}]}
    ar = {"hypothesis_tests": [{"hypothesis": "H1", "path": "ATT → INT", "numbers": {}}]}
    reg = build_registry(hyps, cm, ar, {
        "results": "The MGA interaction ATT × EXP → INT differs between groups. INT → ATT is also reported.",
        "conclusion": "The conclusion summarizes the model.",
    })
    assert any(f["check"] == "coherence.undiscussed_hypothesis"
               for f in check_coherence(reg, hyps, ar, True))


def test_registered_interaction_path_requires_both_operands():
    hyps = ["H9: ATT × EXP affects INT"]
    cm = {"nodes": [{"id": "interaction", "label": "ATT × EXP"}, {"id": "int", "label": "INT"}],
          "edges": [{"id": "H9", "source": "interaction", "target": "int"}]}
    ar = {"hypothesis_tests": [{"hypothesis": "H9", "path": "ATT × EXP → INT", "numbers": {}}]}
    reg = build_registry(hyps, cm, ar, {
        "results": "The ATT × EXP → INT interaction was significant.",
        "conclusion": "The conclusion summarizes the model.",
    })
    assert not any(f["check"] == "coherence.undiscussed_hypothesis"
                   for f in check_coherence(reg, hyps, ar, True))


def test_structured_hypothesis_path_covers_without_conceptual_model_edge():
    """Live M3 records can be dict paths before graph normalization runs."""
    hyps = [{"id": "H1", "path": "ATT -> INT", "direction": "dương"}]
    ar = {"hypothesis_tests": [{"hypothesis": "H1", "path": "ATT -> INT", "numbers": {}}]}
    reg = build_registry(hyps, {}, ar, {
        "results": "Kết quả của đường dẫn ATT → INT được trình bày trong mô hình.",
        "conclusion": "Kết luận tổng hợp các kết quả.",
    })
    assert not any(f["check"] == "coherence.undiscussed_hypothesis"
                   for f in check_coherence(reg, hyps, ar, True))


def test_interaction_tail_cannot_cover_its_second_operand_main_effect():
    hyps = [{"id": "H1", "path": "INT -> DEC"}]
    ar = {"hypothesis_tests": [{"hypothesis": "H1", "path": "INT -> DEC", "numbers": {}}]}
    reg = build_registry(hyps, {}, ar, {
        "results": "MGA reports the moderation INC × INT → DEC for one group.",
        "conclusion": "The conclusion summarizes the model.",
    })
    assert any(f["check"] == "coherence.undiscussed_hypothesis"
               for f in check_coherence(reg, hyps, ar, True))


def test_ascii_x_interaction_tail_cannot_cover_main_effect():
    hyps = [{"id": "H1", "path": "INT -> DEC"}]
    ar = {"hypothesis_tests": [{"hypothesis": "H1", "path": "INT -> DEC", "numbers": {}}]}
    reg = build_registry(hyps, {}, ar, {
        "results": "MGA reports INC x INT → DEC in one group.",
        "conclusion": "The conclusion summarizes the model.",
    })
    assert any(f["check"] == "coherence.undiscussed_hypothesis"
               for f in check_coherence(reg, hyps, ar, True))


def test_graph_display_labels_do_not_overwrite_structured_code_path_alias():
    hyps = [{"id": "H1", "path": "ATT -> INT"}]
    cm = {"nodes": [{"id": "ATT", "label": "Thái độ"}, {"id": "INT", "label": "Ý định"}],
          "edges": [{"id": "H1", "source": "ATT", "target": "INT"}]}
    ar = {"hypothesis_tests": [{"hypothesis": "H1", "path": "ATT -> INT", "numbers": {}}]}
    reg = build_registry(hyps, cm, ar, {
        "results": "Đường dẫn ATT → INT có ý nghĩa trong mô hình.",
        "conclusion": "The conclusion summarizes the model.",
    })
    assert not any(f["check"] == "coherence.undiscussed_hypothesis"
                   for f in check_coherence(reg, hyps, ar, True))


def test_unique_path_without_h_anchor_hard_checks_comma_decimal():
    reg = build_registry(
        [{"id": "H1", "path": "ATT -> INT"}], {},
        {"hypothesis_tests": [{"hypothesis": "H1", "numbers": {"beta": 0.31}, "decision": "supported"}]},
        {"results": "Đường dẫn ATT → INT có β = 0,45.", "conclusion": "Kết luận tổng hợp."},
    )
    findings = check_coherence(reg)
    mismatch = next(f for f in findings if f["check"] == "coherence.number_mismatch")
    assert mismatch["severity"] == "hard"
    assert mismatch["observed"] == {"metric": "beta", "sentence": "Đường dẫn ATT → INT có β = 0,45.", "value": 0.45}
    assert mismatch["expected"] == 0.31


def test_multiple_paths_do_not_assign_one_beta_to_a_main_effect():
    hyps = [{"id": "H1", "path": "ATT -> INT"}, {"id": "H2", "path": "EXP -> INT"}]
    ar = {"hypothesis_tests": [
        {"hypothesis": "H1", "numbers": {"beta": 0.31}},
        {"hypothesis": "H2", "numbers": {"beta": 0.22}},
    ]}
    reg = build_registry(hyps, {}, ar, {
        "results": "ATT → INT and EXP → INT have β = 0.99.", "conclusion": "Kết luận tổng hợp.",
    })
    findings = check_coherence(reg)
    assert not any(f["check"] == "coherence.number_mismatch" for f in findings)
    assert any(f["check"] == "coherence.ambiguous_path_attribution" for f in findings)


def test_mga_heading_suppresses_h_anchored_numeric_claim_until_next_heading():
    reg = build_registry(HYPS, CM, AR, {
        "results": "# MGA results\nH1 has β = 0.99 for group A.\n# Pooled results\nH1 has β = 0.34.",
        "conclusion": "Kết luận tổng hợp.",
    })
    findings = check_coherence(reg)
    assert not any(f["check"] == "coherence.number_mismatch" for f in findings)
    assert not any(f["check"] == "coherence.ambiguous_path_attribution" for f in findings)


def test_group_coefficient_difference_sentence_is_not_a_pooled_beta():
    reg = build_registry(HYPS, CM, AR, {
        "results": "For LS → PI, chênh lệch hệ số giữa các nhóm là β = -0,004.",
        "conclusion": "Kết luận tổng hợp.",
    })
    findings = check_coherence(reg)
    assert not any(f["check"] == "coherence.number_mismatch" for f in findings)
    assert not any(f["check"] == "coherence.ambiguous_path_attribution" for f in findings)


def test_h_anchor_conflicting_with_path_is_soft_and_not_misattributed():
    hyps = [{"id": "H1", "path": "ATT -> INT"}, {"id": "H2", "path": "EXP -> INT"}]
    ar = {"hypothesis_tests": [
        {"hypothesis": "H1", "numbers": {"beta": 0.31}},
        {"hypothesis": "H2", "numbers": {"beta": 0.22}},
    ]}
    reg = build_registry(hyps, {}, ar, {
        "results": "H1, path EXP → INT, has β = 0.99.", "conclusion": "Kết luận tổng hợp.",
    })
    findings = check_coherence(reg)
    assert not any(f["check"] == "coherence.number_mismatch" for f in findings)
    assert any("hypothesis path conflict" in f["message"] for f in findings)


def test_unique_path_in_same_paragraph_attributes_preceding_statistics():
    hyps = [{"id": "H1", "path": "ATT -> INT"}]
    ar = {"hypothesis_tests": [{"hypothesis": "H1", "numbers": {"beta": 0.257, "t": 7.49, "p": 0.0}}]}
    matching = ("Kết quả cho thấy ATT có tác động dương đến INT với β = 0,257, t = 7,490 và p = 0,000. "
                "Do đó, giả thuyết ATT → INT được ủng hộ.")
    reg = build_registry(hyps, {}, ar, {"results": matching, "conclusion": "Kết luận tổng hợp."})
    assert not any(f["check"] == "coherence.number_mismatch" for f in check_coherence(reg))

    tampered = matching.replace("β = 0,257", "β = 0,999", 1)
    reg = build_registry(hyps, {}, ar, {"results": tampered, "conclusion": "Kết luận tổng hợp."})
    assert any(f["check"] == "coherence.number_mismatch" and f["severity"] == "hard"
               for f in check_coherence(reg))


def test_unique_path_in_same_paragraph_attributes_direction_word():
    hyps = [{"id": "H1", "path": "ATT -> INT"}]
    ar = {"hypothesis_tests": [{"hypothesis": "H1", "numbers": {"beta": -0.257}}]}
    prose = "ATT có tác động tích cực đến INT với β = -0,257. Giả thuyết ATT → INT được trình bày."
    reg = build_registry(hyps, {}, ar, {"results": prose, "conclusion": "Kết luận tổng hợp."})
    assert any(f["check"] == "coherence.direction_prose" for f in check_coherence(reg))


def test_paragraph_does_not_borrow_managerial_recommendation_as_direction():
    hyps = [{"id": "H7", "path": "INT -> DEC"}]
    ar = {"hypothesis_tests": [{"hypothesis": "H7", "numbers": {"beta": 0.606}}]}
    prose = ("Kết quả cho thấy β = 0,606. Giả thuyết INT → DEC được ủng hộ. "
             "Vì vậy, doanh nghiệp cần giảm các rào cản đối với khách hàng.")
    reg = build_registry(hyps, {}, ar, {"results": prose, "conclusion": "Kết luận tổng hợp."})
    assert not any(f["check"] == "coherence.direction_prose" for f in check_coherence(reg))


def test_paragraph_with_competing_paths_does_not_associate_detached_statistics():
    hyps = [{"id": "H1", "path": "ATT -> INT"}, {"id": "H2", "path": "EXP -> INT"}]
    ar = {"hypothesis_tests": [
        {"hypothesis": "H1", "numbers": {"beta": 0.257}},
        {"hypothesis": "H2", "numbers": {"beta": 0.269}},
    ]}
    prose = "Kết quả cho thấy β = 0,999. Các đường dẫn ATT → INT và EXP → INT được ủng hộ."
    reg = build_registry(hyps, {}, ar, {"results": prose, "conclusion": "Kết luận tổng hợp."})
    assert not any(f["check"] == "coherence.number_mismatch" for f in check_coherence(reg))


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


def test_a_legacy_discussion_slice_reaches_the_traceability_and_coherence_checks():
    """`_resolve_chapters` passed dict keys through verbatim, so a legacy
    project whose closing chapter is stored under `discussion` produced
    chapters["conclusion"] is None: `present` was False, _co3 short-circuited,
    and traceability.discussion_uncited could never fire for the exact projects
    the aliasing work exists to rescue."""
    from agent.coherence import _resolve_chapters, traceability_findings

    slice_ = {"results": "H1 shows a strong path.",
              "discussion": "H1 was supported by the data, plainly.\n\n"
                            "H2 was supported by the data, plainly."}
    chapters = _resolve_chapters(slice_)
    assert "discussion" not in chapters
    assert chapters["conclusion"].startswith("H1 was supported")

    m2 = {"literature_sources": [{"title": "Davis 1989"}]}
    out = traceability_findings(m2, {}, chapters)
    assert any(f["check"] == "traceability.discussion_uncited" for f in out)
    # The finding id and its chapter label are stable identifiers for persisted
    # feedback — the alias must not rename them.
    assert all(f["location"]["chapter"] == "discussion"
               for f in out if f["check"] == "traceability.discussion_uncited")


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

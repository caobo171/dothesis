"""Phase 4: dothesis claim adapters (agent/stats_validation.py)."""
import copy

import pytest

pytest.importorskip("thesis_stats")

from agent.stats_validation import (
    claims_from_analysis_results, claims_from_run_stats,
    validate_analysis_results, validate_run_stats,
)


# --- The M4 skill's own sample block (SKILL.md) -----------------------------

GOOD_BLOCK = {
    "descriptives": {"n": 234, "by_item": [{"item": "LS1", "mean": 3.8, "sd": 0.9}]},
    "measurement_model": [
        {"construct": "LS",
         "items": [{"item": "LS1", "loading": 0.81}, {"item": "LS2", "loading": 0.78},
                   {"item": "LS3", "loading": 0.80}],
         "cronbach_alpha": 0.86, "composite_reliability": 0.90, "ave": 0.63},
        {"construct": "PI",
         "items": [{"item": "PI1", "loading": 0.80}, {"item": "PI2", "loading": 0.76},
                   {"item": "PI3", "loading": 0.74}],
         "cronbach_alpha": 0.84, "composite_reliability": 0.88, "ave": 0.58},
    ],
    "discriminant_validity": {"method": "HTMT", "matrix": [["LS", "PI"], [1.0, 0.42], [0.42, 1.0]]},
    "hypothesis_tests": [
        {"id": "r-H1", "hypothesis": "H1", "path": "LS → PI", "test": "PLS path",
         "numbers": {"beta": 0.34, "t": 7.01, "p": "<0.001", "f2": 0.18},
         "decision": "supported", "assumption_checks": {"vif": 1.02}},
    ],
    "structural_model": {"r2": {"PI": 0.56}, "q2": {"PI": 0.31}, "tool": "SmartPLS"},
}


def _hard(agg):
    return {f["check"] for f in agg["findings"] if f["severity"] == "hard"}


def test_good_block_validates_clean():
    agg = validate_analysis_results(GOOD_BLOCK)
    assert agg["hard"] == 0, _hard(agg)


def test_ave_loadings_mismatch_hard():
    b = copy.deepcopy(GOOD_BLOCK)
    b["measurement_model"][0]["ave"] = 0.85
    assert "consistency.ave_loadings" in _hard(validate_analysis_results(b))


def test_impossible_t_p_hard():
    b = copy.deepcopy(GOOD_BLOCK)
    b["hypothesis_tests"][0]["numbers"]["p"] = 0.48  # with t=7.01
    assert "consistency.t_p" in _hard(validate_analysis_results(b))


def test_family_mix_hard():
    b = copy.deepcopy(GOOD_BLOCK)
    b["structural_model"]["cfi"] = 0.95  # inject CB-SEM index into a PLS block
    assert "xtable.family_mix" in _hard(validate_analysis_results(b))


def test_orchestrator_results_dict_shape():
    block = {"results": {"step1": {"data_type": "loadings",
                                   "table": [{"item": "X1", "loading": 1.4}]}}}
    assert "bounds.loading" in _hard(validate_analysis_results(block))


def test_free_text_yields_soft_unstructured_no_crash():
    agg = validate_analysis_results("all hypotheses were supported")
    assert agg["hard"] == 0
    assert any(f["check"] == "structure.unstructured" for f in agg["findings"])


def test_none_and_list_do_not_crash():
    assert validate_analysis_results(None)["hard"] == 0
    assert validate_analysis_results([1, 2, 3])["hard"] == 0
    assert claims_from_analysis_results(None) == []


def test_x2_hypothesis_coverage_soft():
    agg = validate_analysis_results(GOOD_BLOCK, m3_hypotheses=[{"id": "H1"}, {"id": "H3"}])
    assert any(f["check"] == "xtable.hypothesis_coverage" for f in agg["findings"])
    assert agg["hard"] == 0


# --- run_stats summaries ----------------------------------------------------

def test_pls_summary_ci_containment_hard():
    summary = {
        "paths": {"A -> B": {"beta": 0.55, "ci95": [0.10, 0.30]}},
        "reliability": {"B": {"r_squared": 0.30, "ave": 0.60, "cronbach_alpha": 0.80, "cr_rho": 0.85}},
        "outer_loadings": {"B1": 0.80},
        "bootstrap_samples": 500,
    }
    agg = validate_run_stats("pls_sem", summary)
    assert "consistency.ci_contains" in _hard(agg)


def test_run_stats_bounds_impossible_r2():
    agg = validate_run_stats("regression", {"y": "Y", "n": 100, "r2": 1.4, "coefficients": {}})
    assert "bounds.r2" in _hard(agg)


def test_validate_run_stats_never_raises_on_garbage():
    assert validate_run_stats("pls_sem", None)["crashed"] is False  # non-dict → [] claims
    assert validate_run_stats("pls_sem", {"paths": "nonsense"})["hard"] == 0


def test_unknown_op_yields_no_claims():
    assert claims_from_run_stats("mystery", {"foo": 1}) == []


# --- deferred fast-follows: data_screening block coverage --------------------

def test_data_screening_block_clean():
    block = dict(GOOD_BLOCK)
    block["data_screening"] = {"missing": {"per_variable": {"LS1": {"missing_pct": 2.5}},
                                           "mcar": {"p": 0.34}},
                               "outliers": {"mahalanobis": {"max_d2": 30.1}}}
    assert validate_analysis_results(block)["hard"] == 0


def test_data_screening_block_impossible_missing_pct_hard():
    block = dict(GOOD_BLOCK)
    block["data_screening"] = {"missing": {"per_variable": {"LS1": {"missing_pct": 180}}}}
    assert "bounds.missing_pct" in _hard(validate_analysis_results(block))

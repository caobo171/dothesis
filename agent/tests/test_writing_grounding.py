from agent.writing_grounding import grounding_findings


def _context(**analysis):
    return {
        "analysis_results": analysis,
        "results": {"discriminant_validity": {"htmt": 0.42}},  # stale legacy result
        "constructs": [
            {"id": "ATT", "label": "Thái độ đối với du lịch nội địa"},
            {"id": "EXP", "label": "Chuyên môn người ảnh hưởng"},
        ],
    }


def test_explicit_diagnostic_pass_without_canonical_metric_is_soft_and_actionable():
    findings = grounding_findings({"results": "All HTMT values passed the threshold."}, _context(hypothesis_tests=[]))
    assert [(f["check"], f["severity"]) for f in findings] == [
        ("coherence.unsupported_diagnostic_claim", "soft"),
    ]


def test_theoretical_thresholds_negation_and_reported_metrics_are_not_false_positive():
    assert grounding_findings({"results": "The HTMT threshold is below 0.85. HTMT was not reported."}, _context(hypothesis_tests=[])) == []
    assert grounding_findings({"results": "All HTMT values passed the threshold."},
                              _context(discriminant_validity={"htmt": 0.42})) == []


def test_general_english_and_vietnamese_quality_criteria_are_not_reported_pass_claims():
    context = _context(hypothesis_tests=[])
    assert grounding_findings({"results": "Outer loadings above 0.70 are considered acceptable."}, context) == []
    assert grounding_findings({"results": "Độ tin cậy được đánh giá bằng Cronbach alpha; giá trị trên 0.7 được chấp nhận."}, context) == []


def test_canonical_analysis_results_beats_a_stale_legacy_results_field():
    findings = grounding_findings({"results": "All HTMT values passed the threshold."},
                                  _context(hypothesis_tests=[]))
    assert any(f["check"] == "coherence.unsupported_diagnostic_claim" for f in findings)


def test_a_fornell_larcker_matrix_is_not_mistaken_for_htmt_evidence():
    findings = grounding_findings(
        {"results": "All HTMT values passed the threshold."},
        _context(discriminant_validity={"method": "Fornell-Larcker", "matrix": [[1.0, 0.3], [0.3, 1.0]]}),
    )
    assert any(f["check"] == "coherence.unsupported_diagnostic_claim" for f in findings)


def test_only_explicit_known_construct_alias_conflicts_are_reported():
    findings = grounding_findings({"results": "ATT = Chuyên môn người ảnh hưởng."}, _context())
    assert any(f["check"] == "grounding.construct_alias_conflict" and f["severity"] == "soft"
               for f in findings)
    assert grounding_findings({"results": "ATT affects travel intention."}, _context()) == []

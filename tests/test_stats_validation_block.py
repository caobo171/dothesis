"""The M4 commit gate must not wave a results block through as "nothing to check".

A list-shaped `analysis_results` used to yield zero claims and zero warnings, so
a full SmartPLS run committed with `analysis_provenance.numbers.total = 0` and
the student was never told the numbers had gone unverified.
"""
from agent.stats_validation import claims_from_analysis_results, validate_analysis_results
from tests.fixtures.renderer_blocks import AGENT_LIST_BLOCK, FREE_TEXT_BLOCK, PLS_BLOCK


def test_list_shape_now_yields_claims():
    """No claims meant no findings, which read as a clean bill of health. The
    numbers in the list shape have to actually be checked."""
    claims = claims_from_analysis_results(AGENT_LIST_BLOCK)
    metrics = {c["metric"] for c in claims}
    assert {"alpha", "cr", "ave", "beta", "t", "r2"} <= metrics, metrics

    out = validate_analysis_results(AGENT_LIST_BLOCK)
    assert not out["hard"]
    assert not any(f["check"] == "structure.unstructured" for f in out["findings_soft"])


def test_documented_shape_still_validates():
    out = validate_analysis_results(PLS_BLOCK)
    assert not out["hard"]
    assert not any(f["check"] == "structure.unstructured" for f in out["findings_soft"])


def test_free_text_warns():
    out = validate_analysis_results(FREE_TEXT_BLOCK)
    assert any(f["check"] == "structure.unstructured" for f in out["findings_soft"])


def test_bare_list_warns_too():
    """The shape that slipped through: not a str, so the old check never fired."""
    out = validate_analysis_results([1, 2, 3])
    assert any(f["check"] == "structure.unstructured" for f in out["findings_soft"])


def test_empty_block_does_not_warn():
    """Nothing committed yet is not the same as something unreadable."""
    out = validate_analysis_results({})
    assert not any(f["check"] == "structure.unstructured" for f in out["findings_soft"])

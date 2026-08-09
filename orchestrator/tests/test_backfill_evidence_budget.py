"""Evidence budgeting + the unevidenced-methodology guard for the backfill.

Regression cover for a real failure: importing a 36k-char SPSS thesis produced
an M3 saying "PLS-SEM using SmartPLS". The prompt head-sliced the whole evidence
JSON at 6000 chars, so the model saw the first 16% — everything up to Chapter
4's descriptives — and never reached the methodology statement or the hypothesis
results table. With the contradicting facts cut away, it reported the analysis
those constructs usually imply rather than the one that was run.

No LLM: the budgeting and the guard are both pure functions.
"""
import json

from unittest.mock import MagicMock

import orchestrator.backfill as B
from orchestrator.state import ContextStore


def _thesis(marker: str, n: int = 36000) -> str:
    """A long document with `marker` buried ~68% in, where a results table sits."""
    filler = "Nội dung chương phân tích dữ liệu. "
    body = (filler * (n // len(filler) + 1))[:n]
    at = int(n * 0.68)
    return body[:at] + marker + body[at:]


# --- budgeting ---------------------------------------------------------------

def test_long_document_keeps_its_tail_not_just_its_head():
    """The old head-slice hid everything past ~16%, including the results."""
    doc = _thesis("BẢNG 4.17 H1 beta=0.371 H2 beta=0.551 H3 beta=0.468")
    fitted = B._fit_evidence({"m4_analysis": {"analysis_results": doc}})
    text = json.dumps(fitted, ensure_ascii=False)
    assert "BẢNG 4.17" in text
    assert "beta=0.551" in text


def test_a_huge_slice_cannot_starve_the_small_ones():
    """Water-filling, not a whole-payload slice.

    Under the old code a long M4 blob consumed the entire budget and M1/M3 fell
    off the end of the prompt even though they were tiny.
    """
    fitted = B._fit_evidence({
        "m1_topic": {"research_title": "KOL credibility and purchase behaviour"},
        "m3_design": {"methodology": "Multiple linear regression, SPSS, n=303"},
        "m4_analysis": {"analysis_results": _thesis("MARKER", 200000)},
    })
    text = json.dumps(fitted, ensure_ascii=False)
    assert "KOL credibility and purchase behaviour" in text
    assert "Multiple linear regression, SPSS, n=303" in text


def test_short_evidence_is_passed_through_untouched():
    ev = {"m1_topic": {"research_title": "T"}, "m3_design": {"methodology": "survey"}}
    assert B._fit_evidence(ev) == ev


def test_elision_is_marked_so_the_model_knows_it_is_partial():
    fitted = B._fit_evidence({"m4_analysis": {"analysis_results": _thesis("X", 200000)}})
    assert "characters omitted" in fitted["m4_analysis"]["analysis_results"]


def test_budget_is_respected():
    fitted = B._fit_evidence(
        {"m4_analysis": {"analysis_results": _thesis("X", 500000)},
         "m5_writing": {"final_sections": _thesis("Y", 500000)}},
        budget=20000)
    assert len(json.dumps(fitted, ensure_ascii=False)) <= 20000 * 1.1


# --- unevidenced methodology -------------------------------------------------

def test_methodology_naming_an_unevidenced_tool_is_dropped():
    """M5 writes the methodology chapter from this field, so a guessed package
    becomes a sentence describing an analysis the student never ran."""
    out = B._drop_unevidenced_method(
        {"methodology": "PLS-SEM using SmartPLS", "sample_plan": "n=303"},
        "results processed with spss, multiple linear regression, n=303")
    assert "methodology" not in out
    assert out["sample_plan"] == "n=303"   # other fields survive


def test_methodology_naming_an_evidenced_tool_is_kept():
    out = B._drop_unevidenced_method(
        {"methodology": "Multiple linear regression in SPSS"},
        "nguồn: kết quả xử lý bằng phần mềm SPSS")
    assert out["methodology"] == "Multiple linear regression in SPSS"


def test_methodology_without_any_tool_name_is_kept():
    """Only software/technique claims are gated — inferring 'quantitative
    survey design' from a questionnaire is legitimate."""
    out = B._drop_unevidenced_method({"methodology": "Quantitative survey design"}, "")
    assert out["methodology"] == "Quantitative survey design"


def test_guard_runs_inside_reconstruct_artifact():
    """End-to-end through the real entry point, with the LLM faked."""
    llm = MagicMock()
    llm.invoke.return_value.content = json.dumps({
        "methodology": "PLS-SEM estimated in SmartPLS 4",
        "hypotheses": ["H1: ATT → PB"],
        "_rationale": "inferred from the constructs",
    })
    cs = ContextStore(m4_analysis={"analysis_results":
                                   "Hồi quy tuyến tính đa biến bằng SPSS, n=303."})
    got = B.reconstruct_artifact("design", cs, llm=llm)
    assert "methodology" not in got
    assert got.get("hypotheses") == ["H1: ATT → PB"]

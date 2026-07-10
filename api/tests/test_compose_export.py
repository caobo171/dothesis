"""F1 gate unification + shared compose back-half. Pure functions over a
context_store dict — no network, no export subprocess (run_export/compose_chapter
are stubbed where used)."""
from orchestrator.tools.m5_writing import assess_export_readiness

_FULL = ["intro", "lit_review", "methodology", "results", "discussion", "conclusion"]


def test_gate_all_chapters_reports_everything_missing():
    assert assess_export_readiness({}, _FULL)  # empty store -> many missing


def test_gate_scopes_to_requested_chapters():
    # A store with only M4 results, composing ONLY results+discussion:
    store = {"m4_analysis": {"analysis_results": "AVE=0.62 HTMT ok R2=.41"}}
    missing = assess_export_readiness(store, ["results", "discussion"])
    # methodology not requested -> not reported; M4 results present -> not reported.
    assert not any("methodology" in m.lower() for m in missing)
    assert not any("analysis results" in m.lower() for m in missing)


def test_gate_none_chapters_is_backcompat_full_check():
    assert assess_export_readiness({}) == assess_export_readiness({}, None)


# --- Task 2: shared prose sanitation lives in the engine now ----------------
from orchestrator.tools.m5_writing import sanitize_prose


def test_sanitize_demotes_heading_hypothesis():
    # "### H1: full sentence." -> "**H1:** full sentence." (no oversized heading, no TOC).
    out = sanitize_prose("### H1: Trust positively affects intention to use the system.")
    assert out.startswith("**H1:**")
    assert not out.lstrip().startswith("#")


def test_sanitize_drops_placeholder_table():
    md = "**Bảng 4.1**\n\n| A | B |\n|---|---|\n| … | … |\n\n*Nguồn: tác giả*\n\nReal prose."
    out = sanitize_prose(md)
    assert "|" not in out          # the dotted shell table is gone
    assert "Real prose." in out    # surrounding prose kept

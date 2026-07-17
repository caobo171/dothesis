"""Phase 5: export-time ensure_rendered safety net."""
from orchestrator.tools.results_render import ensure_rendered, rendered_kinds, render_results_tables
from tests.fixtures.renderer_blocks import PLS_BLOCK, SCREENING_BLOCK


def _cs(ar=PLS_BLOCK):
    return {"m4_analysis": {"analysis_results": ar}, "m3_design": {}}


def test_weaves_missing_tables_into_results():
    sections = [{"title": "Results", "prose": "Our findings follow."}]
    out = ensure_rendered(sections, _cs())
    assert "dt-rendered:begin kind=measurement_model" in out[0]["prose"]
    assert "0.34" in out[0]["prose"]


def test_idempotent_when_already_rendered():
    blocks = render_results_tables(PLS_BLOCK)
    from orchestrator.tools.results_render import weave
    woven = weave("Findings.", blocks)
    sections = [{"title": "Results", "prose": woven}]
    out = ensure_rendered(sections, _cs())
    # same kinds, not doubled
    assert out[0]["prose"].count("kind=measurement_model sha=") == 1


def test_non_chapter_untouched():
    sections = [{"title": "Introduction", "prose": "Background."}]
    out = ensure_rendered(sections, _cs())
    assert out[0]["prose"] == "Background."


def test_methodology_gets_cleaning():
    sections = [{"title": "Methodology", "prose": "We collected data."}]
    out = ensure_rendered(sections, _cs(SCREENING_BLOCK))
    assert SCREENING_BLOCK["data_screening"]["narrative"] in out[0]["prose"]


def test_no_context_ar_no_change():
    sections = [{"title": "Results", "prose": "Findings."}]
    out = ensure_rendered(sections, {"m4_analysis": {}})
    assert out[0]["prose"] == "Findings."


def test_fail_open_garbage():
    assert ensure_rendered("notalist", {}) == "notalist"
    ensure_rendered([{"title": "Results"}], None)  # no raise

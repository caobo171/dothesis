"""render_verified_sections chat tool (roadmap M5 renderer, Phase 6.1)."""
import json

from agent.tools.writing import make_writing_tools
from orchestrator.tools.results_render import render_results_tables
from tests.fixtures.renderer_blocks import PLS_BLOCK, SCREENING_BLOCK


class _Store:
    def __init__(self, cs):
        self._cs = cs

    def load_full_context_store(self):
        return self._cs


def _tool(store):
    return {t.name: t for t in make_writing_tools(store)}["render_verified_sections"]


def test_results_tables_matches_pure_renderer():
    cs = {"m4_analysis": {"analysis_results": PLS_BLOCK}, "m1_topic": {"language": "en"}}
    out = json.loads(_tool(_Store(cs)).func("results_tables"))
    expected = "\n\n".join(b["markdown"] for b in render_results_tables(PLS_BLOCK, "en"))
    assert out["ok"] is True and out["markdown"] == expected
    assert "measurement_model" in out["kinds"]


def test_data_cleaning():
    cs = {"m4_analysis": {"analysis_results": SCREENING_BLOCK}}
    out = json.loads(_tool(_Store(cs)).func("data_cleaning"))
    assert out["ok"] is True and SCREENING_BLOCK["data_screening"]["narrative"] in out["markdown"]


def test_empty_store_no_data():
    out = json.loads(_tool(_Store({})).func("results_tables"))
    assert out["ok"] is False and out["reason"] == "no_data"


def test_store_raises_no_exception():
    class _Bad:
        def load_full_context_store(self):
            raise RuntimeError("boom")
    out = json.loads(_tool(_Bad()).func("results_tables"))
    assert out["ok"] is False


def test_tool_registered():
    tools = {t.name for t in make_writing_tools(_Store({}))}
    assert "render_verified_sections" in tools

"""Tests for intake helpers (importing a student's existing work)."""
from unittest.mock import MagicMock

from orchestrator.intake import assess_work, merge_import
from orchestrator.state import ContextStore


def _fake_llm(content: str) -> MagicMock:
    llm = MagicMock()
    llm.invoke.return_value.content = content
    return llm


def test_assess_work_extracts_known_slices():
    llm = _fake_llm(
        '{"m1_topic": {"research_title": "TikTok & Gen Z"}, '
        '"m3_design": {"paradigm": "quantitative"}}'
    )
    out = assess_work("I'm studying TikTok with a survey.", llm=llm)
    assert out["m1_topic"]["research_title"] == "TikTok & Gen Z"
    assert out["m3_design"]["paradigm"] == "quantitative"


def test_assess_work_drops_unknown_keys():
    llm = _fake_llm('{"bogus": {"x": 1}, "m1_topic": {"research_title": "Y"}}')
    out = assess_work("...", llm=llm)
    assert "bogus" not in out
    assert out["m1_topic"]["research_title"] == "Y"


def test_assess_work_empty_text_returns_empty():
    assert assess_work("", llm=_fake_llm("{}")) == {}


def test_assess_work_malformed_json_returns_empty():
    assert assess_work("some text", llm=_fake_llm("not json at all")) == {}


def test_merge_import_seeds_slice_and_tags_source():
    out = merge_import(ContextStore(), {"m1_topic": {"research_title": "X"}})
    assert out.m1_topic["research_title"] == "X"
    # Imported slices are tagged so later steps know they weren't agent-generated.
    assert out.m1_topic["_source"] == "imported"


def test_merge_import_preserves_untouched_slices():
    cs = ContextStore(m1_topic={"research_title": "Old", "scope": "National"})
    out = merge_import(cs, {"m3_design": {"paradigm": "quantitative"}})
    assert out.m1_topic == {"research_title": "Old", "scope": "National"}
    assert out.m3_design["paradigm"] == "quantitative"
    assert out.m3_design["_source"] == "imported"


def test_merge_import_merges_into_existing_slice():
    cs = ContextStore(m1_topic={"research_title": "Old"})
    out = merge_import(cs, {"m1_topic": {"scope": "National"}})
    assert out.m1_topic["research_title"] == "Old"   # kept
    assert out.m1_topic["scope"] == "National"        # added


def test_merge_import_ignores_unknown_keys():
    out = merge_import(ContextStore(), {"bogus": {"x": 1},
                                        "m1_topic": {"research_title": "Y"}})
    assert out.m1_topic["research_title"] == "Y"
    assert not hasattr(out, "bogus")

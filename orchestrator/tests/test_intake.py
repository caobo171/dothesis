"""Tests for intake helpers (importing a student's existing work)."""
from orchestrator.intake import merge_import
from orchestrator.state import ContextStore


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

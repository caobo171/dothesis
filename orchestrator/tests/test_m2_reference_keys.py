"""M2 stores one concept under two names. Every reader must agree about it.

A real project reached this state: `citation_list` held 6 sources,
`literature_sources` did not exist, the roadmap showed M2 `done`, and asking for
the thesis answered "không thể xuất bản DOCX/PDF hoàn chỉnh vì dự án đang thiếu
nguồn tài liệu M2". Same slice, two keys, opposite verdicts.

How it gets there is not an edge case, it is the default path:

  * `M2Output` (orchestrator/schemas/m2.py) — the schema the backfill's LLM
    reconstruction fills — declares `citation_list` and has NO
    `literature_sources` field, so an inferred M2 can only fill the one;
  * `literature_sources` is written by the grounded scout alone, and the scout
    runs on a 120s budget it routinely loses (orchestrator/backfill.py);
  * `dod_literature` counts `citation_list`, so M2 goes green anyway.

The fix is on the reader side, not by mirroring the keys: `literature_sources`
means "a real search verified these" and unverified recall must not be laundered
into it (the late grounding is deliberately ungated so it can overwrite recall).
"""
from orchestrator.tools.m5_writing import (
    _references_section_body, assess_export_readiness, m2_references,
)


_INFERRED_M2 = {"citation_list": [
    {"author": "Ohanian", "year": 1990, "used_for": "Source credibility model."},
    {"author": "Wang và Scheinbaum", "year": 2018, "used_for": "Endorser credibility."},
]}
_GROUNDED_M2 = {"literature_sources": [
    {"title": "Construction of a scale", "authors": ["Ohanian"], "year": 1990,
     "doi": "10.1080/00913367.1990.10673191", "verified": True}]}


def _cs(m2):
    return {"m1_topic": {"research_title": "T", "research_questions": ["RQ1"]},
            "m2_literature": m2,
            "m3_design": {"methodology": {"paradigm": "quant"}},
            "m4_analysis": {"analysis_results": {"hypothesis_tests": [{"id": "H1"}]}}}


def test_an_inferred_m2_is_not_reported_as_having_no_references():
    """The reported bug, at the gate that reported it."""
    assert m2_references(_INFERRED_M2)
    assert assess_export_readiness(_cs(_INFERRED_M2)) == []


def test_a_grounded_m2_still_works():
    assert assess_export_readiness(_cs(_GROUNDED_M2)) == []


def test_verified_sources_win_when_both_keys_are_filled():
    """The grounded search overwrites recall; the reader must not undo that by
    preferring the stale side."""
    both = {**_GROUNDED_M2, **_INFERRED_M2}
    assert m2_references(both) == _GROUNDED_M2["literature_sources"]


def test_a_genuinely_empty_m2_is_still_blocked():
    """The gate has to keep working — this must not become "always ready"."""
    missing = assess_export_readiness(_cs({}))
    assert any("M2" in m for m in missing)
    assert m2_references({}) == [] and m2_references(None) == []


def test_a_titleless_citation_renders_as_a_reference_not_as_punctuation():
    """citation_list records are author+year+why, with no title. The one-line
    entry builder rendered that as "Ohanian (1990). ." — now that the export
    legitimately falls back to these, the empty title clause has to go."""
    body = _references_section_body(_INFERRED_M2["citation_list"])
    assert "Ohanian (1990)." in body
    assert ". ." not in body

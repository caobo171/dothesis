"""Inline-citation → pandoc [@key] rewrite (drives clickable links in DOCX/PDF).

Regression: the LLM frequently writes "(Hilman 2024; Nocker 2024)" without the
comma the original regex required, so citations stayed plain text and never
became clickable links in the export.
"""
from orchestrator.tools.m5_writing import (
    _assign_citation_keys,
    _convert_inline_citations,
)

_REFS = [
    {"authors": ["Hilman"], "year": 2024, "title": "A"},
    {"authors": ["Nocker"], "year": 2024, "title": "B"},
]


def _ly():
    _csl, ly_to_key = _assign_citation_keys(_REFS)
    return ly_to_key


def test_no_comma_multi_citation_is_linkified():
    ly = _ly()
    out = _convert_inline_citations("... quan tâm (Hilman 2024; Nocker 2024).", ly)
    assert "[@hilman2024; @nocker2024]" in out
    assert "(Hilman 2024" not in out


def test_comma_form_still_works():
    ly = _ly()
    assert "[@hilman2024]" in _convert_inline_citations("text (Hilman, 2024).", ly)


def test_non_citation_parenthetical_untouched():
    ly = _ly()
    assert _convert_inline_citations("see (Figure 1) here", ly) == "see (Figure 1) here"


def test_unknown_reference_left_plain():
    ly = _ly()
    # Smith isn't in the pool — leave it exactly as written, don't mangle.
    assert _convert_inline_citations("x (Smith 2099) y", ly) == "x (Smith 2099) y"

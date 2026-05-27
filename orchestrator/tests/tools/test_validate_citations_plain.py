"""SP6.5: tests for validate_citations_plain — pure unit (no DB required)."""
from orchestrator.tools.m5_writing import validate_citations_plain


def test_validate_citations_plain_callable_exists():
    """SP6.5: autosave PATCH calls validate_citations_plain (no decorator)."""
    result = validate_citations_plain(
        prose="See (Smith, 2024) and (Unknown, 2023).",
        reference_pool=[{"author": "Smith", "year": "2024"}],
    )
    assert result["citations_used"] == ["(Smith, 2024)"]
    assert result["uncited_warnings"] == ["(Unknown, 2023)"]


def test_validate_citations_plain_dedupes_in_order():
    """Deduplicates citations and preserves first occurrence order."""
    result = validate_citations_plain(
        prose="(A, 2020). Later (B, 2021). Earlier (A, 2020) again.",
        reference_pool=[{"author": "A", "year": "2020"}, {"author": "B", "year": "2021"}],
    )
    assert result["citations_used"] == ["(A, 2020)", "(B, 2021)"]
    assert result["uncited_warnings"] == []


def test_validate_citations_plain_supports_nd_year():
    """Broader regex than the chapter-compose validator: accepts 'n.d.' years
    for in-progress drafts where the year isn't yet known."""
    result = validate_citations_plain(
        prose="See (Smith, n.d.) in the draft.",
        reference_pool=[{"author": "Smith", "year": "n.d."}],
    )
    assert result["citations_used"] == ["(Smith, n.d.)"]
    assert result["uncited_warnings"] == []

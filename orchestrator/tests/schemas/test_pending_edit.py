from datetime import datetime, timezone
from orchestrator.schemas.m5_editor import PendingEdit


def test_pending_edit_roundtrip():
    pe = PendingEdit(
        id="abc-123",
        chapter_name="intro",
        from_offset=10, to_offset=25,
        old_text="recent studies",
        new_text="A growing body of work",
        source="paraphrase",
        pending_at=datetime(2026, 5, 27, tzinfo=timezone.utc),
    )
    dumped = pe.model_dump()
    restored = PendingEdit.model_validate(dumped)
    assert restored == pe


def test_pending_edit_rejects_unknown_source():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        PendingEdit(
            id="x", chapter_name="intro",
            from_offset=0, to_offset=1,
            old_text="a", new_text="b",
            source="grammar_fix",  # not allowed
            pending_at=datetime.now(timezone.utc),
        )


def test_pending_edit_offsets_must_be_nonnegative():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        PendingEdit(
            id="x", chapter_name="intro",
            from_offset=-1, to_offset=1,
            old_text="", new_text="b",
            source="paraphrase",
            pending_at=datetime.now(timezone.utc),
        )


def test_pending_edit_degenerate_range_for_cite():
    """Cite is insertion-only — from == to, old_text == ''."""
    pe = PendingEdit(
        id="cite-1", chapter_name="intro",
        from_offset=50, to_offset=50, old_text="", new_text=" (Smith, 2024)",
        source="cite", pending_at=datetime.now(timezone.utc),
        metadata={"reference_id": "ref-abc"},
    )
    assert pe.from_offset == pe.to_offset
    assert pe.old_text == ""

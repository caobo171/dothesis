"""Guards the five-chapter thesis structure: every canonical chapter key in
`M5_CHAPTER_ORDER` must resolve to a prompt file on disk (compose_chapter
loads `orchestrator/prompts/m5/<chapter_name>.md` by name, so a missing file
raises at compose time, not at import time), no orphaned prompt files are left
behind to drift out of sync, and the `conclusion` prompt — now the sole
Chapter 5 composer — carries the full 5.1-5.7 structure including the
`[[DT:limitations]]` token, with no leftover reference to a Chapter 6.
"""
from pathlib import Path

from orchestrator.tools.m5_writing import M5_CHAPTER_ORDER


def test_every_canonical_chapter_has_a_prompt_and_no_orphans():
    # compose_chapter loads orchestrator/prompts/m5/<chapter_name>.md by name,
    # so a canonical chapter with no prompt file raises at compose time, and a
    # prompt file with no chapter is dead weight that will drift.
    d = Path(__file__).resolve().parents[1] / "prompts" / "m5"
    on_disk = {p.stem for p in d.glob("*.md")}
    assert set(M5_CHAPTER_ORDER) <= on_disk
    assert "discussion" not in on_disk


def test_conclusion_prompt_carries_the_full_chapter_five_structure():
    text = (Path(__file__).resolve().parents[1]
            / "prompts" / "m5" / "conclusion.md").read_text(encoding="utf-8")
    for needle in ("5.1", "5.2", "5.3", "5.4", "5.5", "5.6", "5.7"):
        assert needle in text, f"conclusion prompt lost section {needle}"
    # The limitations token must survive verbatim on its own line — it renders
    # the REAL flagged weaknesses from state. Losing it silently stops
    # limitation disclosure at export.
    assert "[[DT:limitations]]" in text
    assert "Chapter 6" not in text and "6.1" not in text

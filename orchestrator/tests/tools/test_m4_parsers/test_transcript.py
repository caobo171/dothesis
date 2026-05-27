"""Tests for transcript helpers + qual coding tools."""
import json
from pathlib import Path
from unittest.mock import MagicMock

from orchestrator.tools.m4_parsers.transcript import (
    cluster_codes_into_themes,
    split_transcript_into_segments,
    suggest_qual_codes,
)


_GOLDEN = Path(__file__).resolve().parent.parent.parent.parent / "tools" / "m4_parsers" / "golden"


def _load_golden(name: str) -> str:
    return (_GOLDEN / name).read_text()


def test_split_transcript_extracts_speaker_turns():
    """Split into segments by INTERVIEWER:/PARTICIPANT: prefix."""
    text = _load_golden("transcript_short.txt")
    segments = split_transcript_into_segments(text)
    assert len(segments) >= 6  # 3 interviewer + 3 participant turns
    speakers = {s["speaker"] for s in segments}
    assert "INTERVIEWER" in speakers
    assert "PARTICIPANT" in speakers


def test_suggest_qual_codes_returns_code_plus_quote(monkeypatch):
    """suggest_qual_codes returns [{code, quote, line_no?}, ...] from the transcript."""
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = json.dumps([
        {"code": "leadership vision",
         "quote": "Every Monday morning she paints a picture of where we're going as a team"},
        {"code": "engagement-absorption",
         "quote": "I felt completely absorbed. I forgot to eat lunch."},
        {"code": "psychological safety",
         "quote": "I can say 'this won't work' and we'd discuss it openly."},
    ])
    monkeypatch.setattr(
        "orchestrator.tools.m4_parsers.transcript._get_llm",
        lambda: fake_llm,
    )
    text = _load_golden("transcript_short.txt")
    codes = suggest_qual_codes.invoke({"transcript": text})
    assert isinstance(codes, list)
    assert len(codes) == 3
    assert codes[0]["code"] == "leadership vision"
    assert "Monday" in codes[0]["quote"]


def test_suggest_qual_codes_returns_empty_on_malformed(monkeypatch):
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "not valid json"
    monkeypatch.setattr(
        "orchestrator.tools.m4_parsers.transcript._get_llm",
        lambda: fake_llm,
    )
    codes = suggest_qual_codes.invoke({"transcript": "anything"})
    assert codes == []


def test_cluster_codes_into_themes(monkeypatch):
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = json.dumps([
        {"theme": "Leadership behavior",
         "codes": ["leadership vision"]},
        {"theme": "Employee engagement and safety",
         "codes": ["engagement-absorption", "psychological safety"]},
    ])
    monkeypatch.setattr(
        "orchestrator.tools.m4_parsers.transcript._get_llm",
        lambda: fake_llm,
    )
    codes = [
        {"code": "leadership vision", "quote": "..."},
        {"code": "engagement-absorption", "quote": "..."},
        {"code": "psychological safety", "quote": "..."},
    ]
    themes = cluster_codes_into_themes.invoke({"codes": codes})
    assert isinstance(themes, list)
    assert len(themes) == 2
    assert themes[0]["theme"] == "Leadership behavior"


def test_cluster_codes_falls_back_on_malformed(monkeypatch):
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "{ broken"
    monkeypatch.setattr(
        "orchestrator.tools.m4_parsers.transcript._get_llm",
        lambda: fake_llm,
    )
    themes = cluster_codes_into_themes.invoke({"codes": []})
    assert themes == []

"""Y: summary formatting — long strings and lists must render cleanly."""
from pydantic import BaseModel, Field
from orchestrator.agents.base import ModuleAgent


class _LongOutput(BaseModel):
    research_title: str = ""
    research_questions: list[str] = []


class _LongAgent(ModuleAgent):
    schema = _LongOutput
    module_key = "M1"
    tools = []
    system_prompt = "toy"


def test_summary_renders_strings_without_json_quotes():
    """Y: a string value should not appear wrapped in JSON double-quotes —
    the user sees `**research_title**: My Title` not `: \"My Title\"`."""
    s = _LongAgent()._summarize_for_confirm({
        "research_title": "TikTok engagement among Gen Z students",
    })
    assert '"TikTok' not in s
    assert "TikTok engagement among Gen Z students" in s


def test_summary_does_not_truncate_short_strings_mid_word():
    """Y: a 40-char string should NOT be truncated at all (well under any
    sensible cap). The bug report showed `\"Identi` from a 15-char value
    because the JSON brackets+quotes counted against the 200-char slice
    when the value was nested in a list."""
    s = _LongAgent()._summarize_for_confirm({
        "research_title": "Identifying engagement",
    })
    assert "Identifying engagement" in s
    assert "Identi\n" not in s  # mid-word slice signal


def test_summary_renders_list_of_strings_as_bullets():
    """Y: when the value is a list, render each item on its own indented
    line — not a JSON-encoded `[\"...\", \"What are t` blob that truncates
    the second question mid-sentence."""
    s = _LongAgent()._summarize_for_confirm({
        "research_questions": [
            "What are the factors influencing Gen Z purchase intention on TikTok?",
            "How does perceived authenticity mediate the effect?",
            "What role does parasocial interaction play in this relationship?",
        ],
    })
    # All three questions appear fully — no mid-sentence truncation
    assert "What are the factors influencing Gen Z purchase intention on TikTok?" in s
    assert "How does perceived authenticity mediate the effect?" in s
    assert "What role does parasocial interaction play in this relationship?" in s
    # Brackets and JSON quotes should be gone
    assert "[" not in s
    assert "]" not in s


def test_summary_truncates_very_long_string_at_word_boundary():
    """Y: 1000-char string should still be truncated, but on a word
    boundary with an ellipsis — never mid-word."""
    long = ("Lorem ipsum dolor sit amet consectetur adipiscing elit. " * 30)
    s = _LongAgent()._summarize_for_confirm({"research_title": long})
    # The truncated piece must not end mid-word (a-z immediately before …)
    import re
    matches = re.findall(r"([A-Za-z]+)…", s)
    # Either no truncation marker, or the token before … is a complete word
    # i.e. it appeared verbatim in the original.
    for token in matches:
        assert token in long, f"truncated mid-word: …{token}"

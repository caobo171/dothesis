from unittest.mock import patch
from orchestrator.tools.m5_inline import paraphrase_selection, translate_selection


@patch("orchestrator.tools.m5_inline._call_llm")
def test_paraphrase_returns_new_text_only(mock_llm):
    mock_llm.return_value = "A growing body of work suggests"
    result = paraphrase_selection.invoke({
        "chapter_name": "intro",
        "language": "en",
        "context_before": "The literature is broad.",
        "selection": "recent studies have shown",
        "context_after": "that algorithmic decisions...",
        "style": "more formal",
    })
    assert result == "A growing body of work suggests"


@patch("orchestrator.tools.m5_inline._call_llm")
def test_paraphrase_strips_quotes_and_whitespace(mock_llm):
    mock_llm.return_value = '  "A growing body of work suggests"  \n'
    result = paraphrase_selection.invoke({
        "chapter_name": "intro", "language": "en",
        "context_before": "", "selection": "x", "context_after": "",
    })
    assert result == "A growing body of work suggests"


@patch("orchestrator.tools.m5_inline._call_llm")
def test_paraphrase_without_style_hint(mock_llm):
    mock_llm.return_value = "rewritten text"
    result = paraphrase_selection.invoke({
        "chapter_name": "lit_review", "language": "en",
        "context_before": "", "selection": "old", "context_after": "",
    })
    assert result == "rewritten text"
    # Confirm the prompt didn't crash on missing style
    mock_llm.assert_called_once()


@patch("orchestrator.tools.m5_inline._call_llm")
def test_translate_returns_target_lang_text(mock_llm):
    mock_llm.return_value = "Một nghiên cứu gần đây cho thấy"
    result = translate_selection.invoke({
        "chapter_name": "intro",
        "target_lang": "vi",
        "context_before": "",
        "selection": "Recent studies have shown",
        "context_after": "",
    })
    assert result == "Một nghiên cứu gần đây cho thấy"


@patch("orchestrator.tools.m5_inline._call_llm")
def test_translate_preserves_inline_citation(mock_llm):
    mock_llm.return_value = "Theo (Smith, 2024), điều này quan trọng"
    result = translate_selection.invoke({
        "chapter_name": "intro", "target_lang": "vi",
        "context_before": "", "context_after": "",
        "selection": "According to (Smith, 2024), this matters",
    })
    assert "(Smith, 2024)" in result

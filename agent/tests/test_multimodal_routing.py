"""Capability routing (headless convergence spec §2). The routing-table test is
the test that would have caught defect 1: env-sniffing detect_provider ignored
DOTHESIS_MODEL_ROUTE and emitted Gemini media blocks into OpenAI-compat
endpoints, breaking EVERY attachment on route=ofox."""
import pytest

from agent.model_factory import ModelSpec
from agent import multimodal
from agent.multimodal import Attachment, build_user_message, detect_provider


@pytest.mark.parametrize("route,model,anthropic_key,expected", [
    ("native", "gemini-3.5-flash", None, "gemini"),
    ("native", "claude-sonnet-4-6", "sk-x", "anthropic"),
    ("ofox", "qwen/qwen-plus", None, "openai"),      # defect 1's exact case
    ("ofox", "google/gemini-2.5-flash", None, "openai"),
    ("openrouter", "meta-llama/llama-3", None, "openai"),
])
def test_provider_derives_from_spec(monkeypatch, route, model, anthropic_key, expected):
    if anthropic_key:
        monkeypatch.setenv("ANTHROPIC_API_KEY", anthropic_key)
    else:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert detect_provider(ModelSpec(route=route, model=model)) == expected


def _png(name="chart.png"):
    return Attachment(filename=name, bytes=b"\x89PNG fakebytes", mime_type="image/png")


def _pdf(name="doc.pdf"):
    return Attachment(filename=name, bytes=b"%PDF-1.4 fake", mime_type="application/pdf")


def test_text_only_brain_transcribes_image(monkeypatch):
    # qwen-plus can't see: the image must arrive as TEXT (vision sidecar
    # transcription), never as a media/image block the endpoint rejects.
    monkeypatch.setattr(multimodal, "_transcribe_via_vision",
                        lambda att: f"[transcribed {att.filename}]")
    msg = build_user_message("look", [_png()], "openai", supports_vision=False)
    assert isinstance(msg.content, str)
    assert "[transcribed chart.png]" in msg.content


def test_text_only_brain_extracts_pdf_text(monkeypatch):
    monkeypatch.setattr("agent.pdf_extract.extract_pdf_text",
                        lambda b: ("Cronbach alpha table " * 20, 3))
    msg = build_user_message("read", [_pdf()], "openai", supports_vision=False)
    assert isinstance(msg.content, str)
    assert "Cronbach alpha table" in msg.content


def test_scanned_pdf_falls_back_to_vision(monkeypatch):
    # Risk 3: extract_pdf_text has no OCR — a scan yields near-empty text.
    # Proceeding with a hollow message is the silent failure; the fallback
    # transcribes via the vision sidecar instead.
    monkeypatch.setattr("agent.pdf_extract.extract_pdf_text", lambda b: ("", 0))
    monkeypatch.setattr(multimodal, "_transcribe_via_vision",
                        lambda att: "[vision transcription of scan]")
    msg = build_user_message("read", [_pdf("scan.pdf")], "openai", supports_vision=False)
    assert "[vision transcription of scan]" in msg.content


def test_vision_capable_openai_keeps_image_blocks():
    msg = build_user_message("look", [_png()], "openai", supports_vision=True)
    kinds = [b.get("type") for b in msg.content]
    assert "image_url" in kinds


def test_openai_non_image_never_raises(monkeypatch):
    # The NotImplementedError landmine (multimodal.py:200-209) is gone: a CSV
    # on the openai provider becomes text, whatever the vision capability.
    csv = Attachment(filename="data.csv", bytes=b"a,b\n1,2", mime_type="text/csv")
    msg = build_user_message("data", [csv], "openai", supports_vision=True)
    flat = msg.content if isinstance(msg.content, str) else str(msg.content)
    assert "a,b" in flat


def test_anthropic_pdf_document_block():
    msg = build_user_message("read", [_pdf()], "anthropic")
    kinds = [b.get("type") for b in msg.content]
    assert "document" in kinds  # no NotImplementedError anymore


def test_gemini_path_unchanged():
    msg = build_user_message("look", [_png()], "gemini")
    kinds = [b.get("type") for b in msg.content]
    assert "media" in kinds

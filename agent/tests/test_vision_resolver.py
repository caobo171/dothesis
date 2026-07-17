"""Provider-agnostic vision: resolver matrix + MIME sniff (pure, no network)."""
import dataclasses

import pytest

from agent.model_factory import ModelSpec
from agent.multimodal import (
    Attachment, VisionResolution, _sniff_image_mime, resolve_vision,
)


@pytest.mark.parametrize("route,model,supports,anthropic,expected", [
    ("native", "gemini-3.5-flash", True, None, ("gemini", True)),
    ("native", "claude-sonnet-4-6", True, "sk-x", ("anthropic", False)),
    ("ofox", "bailian/qwen-plus", False, None, ("gemini", True)),
    ("ofox", "google/gemini-2.5-flash", True, None, ("openai", False)),
    ("openrouter", "anthropic/claude-sonnet-4-6", True, None, ("openai", False)),
    ("openrouter", "meta-llama/llama-3", False, None, ("gemini", True)),
])
def test_resolve_matrix(route, model, supports, anthropic, expected, monkeypatch):
    monkeypatch.delenv("DOTHESIS_VISION_FORCE_SIDECAR", raising=False)
    if anthropic:
        monkeypatch.setenv("ANTHROPIC_API_KEY", anthropic)
    else:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    res = resolve_vision(ModelSpec(route=route, model=model, supports_vision=supports))
    assert (res.provider, res.use_sidecar) == expected


def test_force_sidecar_env_overrides(monkeypatch):
    monkeypatch.setenv("DOTHESIS_VISION_FORCE_SIDECAR", "1")
    res = resolve_vision(ModelSpec(route="ofox", model="google/gemini-2.5-flash", supports_vision=True))
    assert (res.provider, res.use_sidecar) == ("gemini", True)


def test_resolve_from_env_default(monkeypatch):
    monkeypatch.setenv("DOTHESIS_MODEL_ROUTE", "ofox")
    monkeypatch.setenv("DOTHESIS_AGENT_MODEL", "bailian/qwen-plus")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DOTHESIS_VISION_FORCE_SIDECAR", raising=False)
    res = resolve_vision()
    assert (res.provider, res.use_sidecar) == ("gemini", True)


def test_resolution_is_frozen():
    res = VisionResolution("gemini", True)
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.provider = "openai"


# --- MIME sniff -------------------------------------------------------------

@pytest.mark.parametrize("data,expected", [
    (b"\x89PNG\r\n\x1a\n....", "image/png"),
    (b"\xff\xd8\xff\xe0....", "image/jpeg"),
    (b"GIF89a....", "image/gif"),
    (b"RIFF____WEBPXXXX", "image/webp"),
    (b"BM....", "image/bmp"),
    (b"not an image", None),
])
def test_sniff(data, expected):
    assert _sniff_image_mime(data) == expected


def test_from_path_sniffs_extensionless(tmp_path):
    p = tmp_path / "paste"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    assert Attachment.from_path(p).mime_type == "image/png"


def test_from_path_suffix_wins_over_sniff(tmp_path):
    p = tmp_path / "chart.png"
    p.write_bytes(b"arbitrary")
    assert Attachment.from_path(p).mime_type == "image/png"


def test_from_path_non_image_extensionless(tmp_path):
    p = tmp_path / "notes"
    p.write_bytes(b"just some text bytes")
    assert Attachment.from_path(p).mime_type == "application/octet-stream"

"""Provider-agnostic vision through parse_output_table: block shape per route,
fail-soft, list-content flatten. No network — the model is a fake."""
import json
from types import SimpleNamespace

import pytest

import agent.model_factory as mf
import agent.tools.output_parse as op


class FakeModel:
    def __init__(self, content):
        self._content = content
        self.seen = None

    def invoke(self, msgs):
        self.seen = msgs
        return SimpleNamespace(content=self._content)


def _png(tmp_path):
    p = tmp_path / "shot"  # extension-less → exercises the sniff too
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
    return str(p)


def _block_types(fake):
    # HumanMessage.content is the list of blocks (text + image).
    content = fake.seen[0].content
    return [b.get("type") for b in content if isinstance(b, dict)]


def _install(monkeypatch, content='{"table_kind":"loadings","rows":[{"item":"X1","value":0.74}]}'):
    fake = FakeModel(content)
    captured = {}

    def factory(spec=None, *, use_sidecar):
        captured["use_sidecar"] = use_sidecar
        return fake

    monkeypatch.setattr(mf, "make_vision_capable_model", factory)
    return fake, captured


def test_native_gemini_media_block_no_regression(tmp_path, monkeypatch):
    monkeypatch.delenv("DOTHESIS_MODEL_ROUTE", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DOTHESIS_VISION_FORCE_SIDECAR", raising=False)
    fake, captured = _install(monkeypatch)
    out = json.loads(op.parse_output_table.func(_png(tmp_path)))
    assert "media" in _block_types(fake) and captured["use_sidecar"] is True
    assert out["table_kind"] == "loadings"


def test_native_claude_image_block(tmp_path, monkeypatch):
    monkeypatch.setenv("DOTHESIS_MODEL_ROUTE", "native")
    monkeypatch.setenv("DOTHESIS_AGENT_MODEL", "claude-sonnet-4-6")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake, captured = _install(monkeypatch)
    op.parse_output_table.func(_png(tmp_path))
    assert "image" in _block_types(fake) and captured["use_sidecar"] is False


def test_ofox_default_media_block(tmp_path, monkeypatch):
    monkeypatch.setenv("DOTHESIS_MODEL_ROUTE", "ofox")
    monkeypatch.setenv("DOTHESIS_AGENT_MODEL", "bailian/qwen-plus")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    fake, captured = _install(monkeypatch)
    op.parse_output_table.func(_png(tmp_path))
    assert "media" in _block_types(fake) and captured["use_sidecar"] is True


def test_ofox_vision_capable_image_url_block(tmp_path, monkeypatch):
    monkeypatch.setenv("DOTHESIS_MODEL_ROUTE", "ofox")
    monkeypatch.setenv("DOTHESIS_AGENT_MODEL", "google/gemini-2.5-flash")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    fake, captured = _install(monkeypatch)
    op.parse_output_table.func(_png(tmp_path))
    assert "image_url" in _block_types(fake) and captured["use_sidecar"] is False


def test_fail_soft_on_model_error(tmp_path, monkeypatch):
    def boom(spec=None, *, use_sidecar):
        raise RuntimeError("no key")

    monkeypatch.setattr(mf, "make_vision_capable_model", boom)
    out = json.loads(op.parse_output_table.func(_png(tmp_path)))
    assert "error" in out and "hint" in out


def test_list_content_flatten(tmp_path, monkeypatch):
    monkeypatch.delenv("DOTHESIS_MODEL_ROUTE", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _install(monkeypatch, content=[{"text": '{"table_kind":"htmt",'},
                                   {"text": '"rows":[{"item":"A","value":0.5}]}'}])
    out = json.loads(op.parse_output_table.func(_png(tmp_path)))
    assert out["table_kind"] == "htmt"

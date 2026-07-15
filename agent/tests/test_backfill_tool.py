"""Tests for the in-thread backfill tool + its runtime widget shaping."""
import json

from agent.runtime import _parse_reconstructed
from agent.tools.backfill_tool import make_backfill_tool


class _DbStore:
    """Stand-in for DbProjectStateStore exposing load_full_context_store."""
    def __init__(self, slices):
        self._slices = slices

    def load_full_context_store(self):
        return self._slices


class _FileStore:
    """CLI file store — no load_full_context_store (the tool must degrade)."""


def test_backfill_tool_degrades_without_db_store():
    tool = make_backfill_tool(_FileStore())
    out = json.loads(tool.invoke({}))
    assert out == {"ok": False, "reconstructed": []}


def test_backfill_tool_empty_when_no_evidence():
    # DB store present but every slice empty → reconstruct_upstream returns [].
    tool = make_backfill_tool(_DbStore({"m1_topic": {}, "m4_analysis": {}}))
    out = json.loads(tool.invoke({}))
    assert out["ok"] is True and out["reconstructed"] == []


def test_parse_reconstructed_shapes_widget():
    content = json.dumps({"ok": True, "reconstructed": [
        {"module": "M3", "candidate": {"paradigm": "quant"}, "rationale": "r",
         "ready_to_confirm": False, "review": ["missing tool"]}]})
    hint = _parse_reconstructed(content)
    assert hint == {"widget_type": "reconstructed_modules", "items": [
        {"module": "M3", "candidate": {"paradigm": "quant"}, "rationale": "r",
         "ready_to_confirm": False, "review": ["missing tool"]}]}


def test_parse_reconstructed_none_when_empty_or_malformed():
    assert _parse_reconstructed(json.dumps({"ok": True, "reconstructed": []})) is None
    assert _parse_reconstructed("not json") is None
    assert _parse_reconstructed(json.dumps([1, 2])) is None

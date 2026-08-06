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


def test_backfill_tool_saves_each_reconstruction(monkeypatch):
    """The tool commits as it goes — the widget shows what landed, it doesn't
    gate it. This is what makes the headless/partner surfaces work: they run
    this tool with no card for anyone to click."""
    import orchestrator.backfill as bf
    monkeypatch.setattr(bf, "reconstruct_upstream", lambda cs, targets=None, language=None: [
        {"module": "M3", "candidate": {"conceptual_model": {"c": ["A"]}},
         "rationale": "", "ready_to_confirm": True, "review": []},
        {"module": "M1", "candidate": {"research_title": "T"},
         "rationale": "", "ready_to_confirm": True, "review": []},
    ])
    committed = []

    class _Store(_DbStore):
        def commit_reconstructed(self, module, slice_, **kw):
            committed.append((module, slice_))
            return {"module": module, "status": "done", "focus": "M4"}

    out = json.loads(make_backfill_tool(_Store({"m4_analysis": {"analysis_results": "x"}})).invoke({}))
    # Committed in MODULES order, not the order the reconstructor happened to
    # return — an M1 commit after M3 would flag the M3 it just wrote.
    assert [m for m, _ in committed] == ["M1", "M3"]
    assert [s["module"] for s in out["saved"]] == ["M1", "M3"]


def test_backfill_tool_reports_the_rest_when_one_commit_fails(monkeypatch):
    import orchestrator.backfill as bf
    monkeypatch.setattr(bf, "reconstruct_upstream", lambda cs, targets=None, language=None: [
        {"module": "M1", "candidate": {"research_title": "T"},
         "rationale": "", "ready_to_confirm": True, "review": []},
        {"module": "M3", "candidate": {"conceptual_model": {"c": ["A"]}},
         "rationale": "", "ready_to_confirm": True, "review": []},
    ])

    class _Store(_DbStore):
        def commit_reconstructed(self, module, slice_, **kw):
            if module == "M1":
                raise RuntimeError("boom")
            return {"module": module, "status": "done", "focus": "M4"}

    out = json.loads(make_backfill_tool(_Store({"m4_analysis": {"analysis_results": "x"}})).invoke({}))
    assert out["ok"] is True
    assert [s["module"] for s in out["saved"]] == ["M3"]
    assert len(out["reconstructed"]) == 2      # still reported to the student


def test_parse_reconstructed_shapes_widget():
    content = json.dumps({"ok": True, "reconstructed": [
        {"module": "M3", "candidate": {"paradigm": "quant"}, "rationale": "r",
         "ready_to_confirm": False, "review": ["missing tool"]}],
        "saved": [{"module": "M3", "status": "done", "focus": "M4"}]})
    hint = _parse_reconstructed(content)
    assert hint == {"widget_type": "reconstructed_modules", "items": [
        {"module": "M3", "candidate": {"paradigm": "quant"}, "rationale": "r",
         "ready_to_confirm": False, "review": ["missing tool"]}],
        "saved": [{"module": "M3", "status": "done", "focus": "M4"}]}


def test_parse_reconstructed_none_when_empty_or_malformed():
    assert _parse_reconstructed(json.dumps({"ok": True, "reconstructed": []})) is None
    assert _parse_reconstructed("not json") is None
    assert _parse_reconstructed(json.dumps([1, 2])) is None

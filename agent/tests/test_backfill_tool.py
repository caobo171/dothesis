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


def _capture_language(monkeypatch):
    """Record the `language` reconstruct_upstream is called with."""
    import orchestrator.backfill as bf
    seen = {}

    def fake(cs, targets=None, language=None, **kw):
        seen["language"] = language
        return []

    monkeypatch.setattr(bf, "reconstruct_upstream", fake)
    return seen


def test_an_explicit_language_reaches_the_reconstructor(monkeypatch):
    """The student asked for the thesis in English; the agent passes that on.

    This was hardcoded to "vi", so a student who uploaded a Vietnamese draft and
    asked for it in English got every reconstructed field back in Vietnamese —
    the same defect detect_language() already documents for the humanize path.
    """
    seen = _capture_language(monkeypatch)
    store = _DbStore({"m4_analysis": {"analysis_results": "Chapter 4 results."}})
    make_backfill_tool(store).invoke({"language": "en"})
    assert seen["language"] == "en"


def test_language_defaults_to_the_language_of_the_students_own_work(monkeypatch):
    """No explicit request → read it off the evidence, never assume."""
    seen = _capture_language(monkeypatch)
    english = ("The survey instrument was distributed to employees of hotels "
               "across the region and 218 valid responses were retained for "
               "analysis using partial least squares structural equation "
               "modelling throughout this chapter.")
    make_backfill_tool(_DbStore({"m4_analysis": {"analysis_results": english}})).invoke({})
    assert seen["language"] == "en"

    seen2 = _capture_language(monkeypatch)
    vietnamese = ("Nghiên cứu sử dụng phương pháp chọn mẫu thuận tiện với 303 "
                  "đáp viên hợp lệ tại Thành phố Hồ Chí Minh, dữ liệu được xử "
                  "lý bằng phần mềm SPSS.")
    make_backfill_tool(_DbStore({"m4_analysis": {"analysis_results": vietnamese}})).invoke({})
    assert seen2["language"] == "vi"


def test_language_falls_back_to_vietnamese_when_there_is_nothing_to_read(monkeypatch):
    seen = _capture_language(monkeypatch)
    make_backfill_tool(_DbStore({"m4_analysis": {"analysis_results": "x"}})).invoke({})
    assert seen["language"] == "vi"


def _thesis_blob() -> str:
    return ("CHƯƠNG 4: KẾT QUẢ NGHIÊN CỨU\n"
            + ("Kết quả phân tích cho thấy mô hình phù hợp. " * 60)
            + "\nCHƯƠNG 5: KẾT LUẬN VÀ KHUYẾN NGHỊ\n"
            + ("Nghiên cứu đóng góp vào lý thuyết hiện có. " * 60))


def test_a_finished_thesis_has_its_last_chapter_moved_to_m5(monkeypatch):
    """Chapters 4 and 5 arrive in one blob under m4_analysis, so M5 stayed null
    and locked while the student's own conclusions sat in the wrong module."""
    _capture_language(monkeypatch)
    committed = {}

    class _Store(_DbStore):
        def commit_slice(self, module, writes, reason, **kw):
            committed[module] = writes
            return {"module": module, "status": "done"}

    store = _Store({"m4_analysis": {"analysis_results": _thesis_blob()},
                    "m5_writing": None})
    make_backfill_tool(store).invoke({})

    # A LIST of section dicts — chapters_from_final_sections iterates and skips
    # non-dicts, so a bare string would be dropped silently at export.
    sections = committed["M5"]["final_sections"]
    assert isinstance(sections, list) and len(sections) == 1
    assert sections[0]["chapter_name"] == "conclusion"
    assert "CHƯƠNG 5" in sections[0]["prose"]
    assert "CHƯƠNG 5" not in committed["M4"]["analysis_results"]
    assert "CHƯƠNG 4" in committed["M4"]["analysis_results"]


def test_an_unsplittable_document_is_left_exactly_as_it_arrived(monkeypatch):
    """No confident boundary → touch nothing. Misfiling a discussion chapter is
    worse than leaving the blob whole."""
    _capture_language(monkeypatch)
    committed = {}

    class _Store(_DbStore):
        def commit_slice(self, module, writes, reason, **kw):
            committed[module] = writes
            return {"module": module, "status": "done"}

    only_ch4 = "CHƯƠNG 4: KẾT QUẢ\n" + ("Kết quả phân tích. " * 200)
    make_backfill_tool(_Store({"m4_analysis": {"analysis_results": only_ch4}})).invoke({})
    assert committed == {}


def test_an_already_populated_m5_is_never_overwritten(monkeypatch):
    """The student's real M5 work outranks anything we could carve out."""
    _capture_language(monkeypatch)
    committed = {}

    class _Store(_DbStore):
        def commit_slice(self, module, writes, reason, **kw):
            committed[module] = writes
            return {"module": module, "status": "done"}

    store = _Store({"m4_analysis": {"analysis_results": _thesis_blob()},
                    "m5_writing": {"final_sections": [
                        {"chapter_name": "conclusion", "prose": "Tôi đã tự viết."}]}})
    make_backfill_tool(store).invoke({})
    assert committed == {}


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

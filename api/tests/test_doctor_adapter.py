"""Repairs apply once; a repair that changes nothing is not retried.

The loop guard is the load-bearing part. M4 on the thread that motivated the
doctor fails its DoD with `results is empty`; if nothing supplies numbers, no
amount of re-running fixes it, and a doctor that runs every turn would bill the
student every turn for the same failed attempt.
"""
from app.doctor_adapter import apply_findings
from orchestrator.doctor import Finding


class _Store:
    def __init__(self, log=None):
        self.log = dict(log or {})
        self.commits = []

    def load_doctor_log(self):
        return dict(self.log)

    def save_doctor_log(self, log):
        self.log = dict(log)

    def commit_slice(self, module, writes, reason, **kw):
        self.commits.append((module, writes, reason, kw))
        return {"ok": True}


def test_a_deterministic_finding_is_committed_and_reported():
    store = _Store()
    res = apply_findings(store, [Finding(
        code="RESULTS_NOT_IN_STATE",
        detail="Đã đọc 102 dòng kết quả từ _Result.docx và lưu vào Chương 4.",
        repair="deterministic",
        payload={"results": {"outer_loadings": [{"label": "ATT_1", "values": [0.854]}]},
                 "filename": "_Result.docx", "module": "M4"},
    )])
    assert store.commits, "results must be committed to M4"
    module, writes, _reason, _kw = store.commits[0]
    assert module == "M4"
    assert writes["results"]["outer_loadings"][0]["label"] == "ATT_1"
    assert any("102 dòng" in line for line in res.repaired)


def test_false_done_is_a_status_correction_not_a_content_write():
    store = _Store()
    apply_findings(store, [Finding(
        code="FALSE_DONE", detail="M4 thiếu kết quả.", repair="deterministic",
        payload={"module": "M4", "gaps": ["results is empty"]})])
    module, writes, _reason, kw = store.commits[0]
    assert module == "M4"
    assert writes == {}, "the module keeps everything it has"
    assert kw["status_overrides"] == {"M4": "in_progress"}


def test_a_repair_that_changed_nothing_is_marked_exhausted():
    store = _Store()
    apply_findings(store, [Finding(
        code="FALSE_DONE", detail="M4 thiếu kết quả.", repair="deterministic",
        payload={"module": "M4", "gaps": ["results is empty"]})],
        gaps_after={"M4": ["results is empty"]})
    assert store.log["FALSE_DONE"]["exhausted"] is True


def test_a_repair_that_closed_its_gaps_is_not_exhausted():
    store = _Store()
    apply_findings(store, [Finding(
        code="FALSE_DONE", detail="M4 thiếu kết quả.", repair="deterministic",
        payload={"module": "M4", "gaps": ["results is empty"]})],
        gaps_after={"M4": []})
    assert store.log["FALSE_DONE"]["exhausted"] is False


def test_an_exhausted_finding_is_not_retried_and_asks_the_student():
    store = _Store({"FALSE_DONE": {"exhausted": True,
                                   "gaps_before": ["results is empty"]}})
    res = apply_findings(store, [Finding(
        code="FALSE_DONE", detail="M4 còn thiếu: results is empty.",
        repair="deterministic",
        payload={"module": "M4", "gaps": ["results is empty"]})])
    assert not store.commits, "an exhausted repair must not run again"
    assert res.directive and "results is empty" in res.directive
    assert "đừng viết lời từ chối vào trong chương" in res.directive


def test_new_evidence_clears_exhaustion():
    store = _Store({"FALSE_DONE": {"exhausted": True,
                                   "gaps_before": ["results is empty"]}})
    apply_findings(store, [Finding(
        code="FALSE_DONE", detail="M4 thiếu kết quả.", repair="deterministic",
        payload={"module": "M4", "gaps": ["results is empty"]})],
        new_evidence=True)
    assert store.commits, "new evidence must re-open an exhausted repair"


def test_directive_findings_are_never_committed():
    store = _Store()
    res = apply_findings(store, [Finding(
        code="BACKFILL_AVAILABLE", detail="Có thể dựng lại: M2, M3.",
        repair="directive", payload={"modules": ["M2", "M3"]})])
    assert not store.commits
    assert "backfill_upstream_modules" in res.directive
    assert "M2, M3" in res.directive
    # The directive has to out-argue the `[PROJECT STATE]` line above it.
    assert "locked" in res.directive


def test_a_refusal_chapter_directive_forbids_writing_the_refusal_into_the_chapter():
    store = _Store()
    res = apply_findings(store, [Finding(
        code="REFUSAL_CHAPTER", detail="Chương `methodology` không có nội dung thật.",
        repair="directive", payload={"chapter": "methodology"})])
    assert "never write the refusal into the chapter itself" in res.directive


def test_one_failing_repair_does_not_stop_the_others():
    class _Flaky(_Store):
        def commit_slice(self, module, writes, reason, **kw):
            if module == "M4" and writes == {}:
                raise RuntimeError("db hiccup")
            return super().commit_slice(module, writes, reason, **kw)

    store = _Flaky()
    res = apply_findings(store, [
        Finding(code="FALSE_DONE", detail="boom", repair="deterministic",
                payload={"module": "M4", "gaps": ["x"]}),
        Finding(code="RESULTS_NOT_IN_STATE", detail="ok", repair="deterministic",
                payload={"results": {"t": []}, "filename": "f.docx", "module": "M4"}),
    ])
    assert res.repaired == ["ok"]


def test_an_unreadable_ledger_does_not_stop_the_repair():
    class _Broken(_Store):
        def load_doctor_log(self):
            raise RuntimeError("db down")

    store = _Broken()
    res = apply_findings(store, [Finding(
        code="RESULTS_NOT_IN_STATE", detail="ok", repair="deterministic",
        payload={"results": {"t": []}, "filename": "f.docx", "module": "M4"})])
    assert res.repaired == ["ok"]


# --- reparse: the one repair that costs a model call ------------------------

_REPARSE = Finding(
    code="RESULTS_NOT_RENDERABLE", detail="đọc lại kết quả", repair="reparse",
    payload={"module": "M4", "filename": "_Result.docx", "text": "| ATT_1 | 0.854 |"},
)
_RENDERABLE = {
    "measurement_model": [{"construct": "ATT", "cronbach_alpha": 0.878,
                           "composite_reliability": 0.894, "ave": 0.65}],
    "structural_model": {"r2": {"INT": 0.527}, "tool": "SmartPLS"},
    "hypothesis_tests": [{"id": "H1", "path": "ATT → INT",
                          "numbers": {"beta": 0.257}, "decision": "supported"}],
}


def test_a_renderable_re_extraction_is_committed(monkeypatch):
    import app.import_work as iw
    monkeypatch.setattr(iw, "_infer_analysis_results", lambda text, lang: _RENDERABLE)
    store = _Store()
    res = apply_findings(store, [_REPARSE])
    module, writes, _reason, _kw = store.commits[0]
    assert module == "M4"
    assert writes["results"]["measurement_model"][0]["construct"] == "ATT"
    assert res.repaired and "dựng lại bảng" in res.repaired[0]


def test_an_extraction_that_still_will_not_render_is_not_committed(monkeypatch):
    """Committing an unreadable block would overwrite the student's numbers with
    a different set of unreadable ones, and Chapter 4 would still have 0 tables."""
    import app.import_work as iw
    monkeypatch.setattr(iw, "_infer_analysis_results",
                        lambda text, lang: {"ATT_to_INT": {"beta": 0.2}})
    store = _Store()
    res = apply_findings(store, [_REPARSE])
    assert not store.commits
    assert res.repaired == []


def test_an_empty_extraction_is_not_committed(monkeypatch):
    import app.import_work as iw
    monkeypatch.setattr(iw, "_infer_analysis_results", lambda text, lang: {})
    store = _Store()
    apply_findings(store, [_REPARSE])
    assert not store.commits


def test_a_failed_reparse_does_not_stop_other_repairs(monkeypatch):
    import app.import_work as iw
    monkeypatch.setattr(iw, "_infer_analysis_results",
                        lambda text, lang: (_ for _ in ()).throw(RuntimeError("no key")))
    store = _Store()
    res = apply_findings(store, [_REPARSE, Finding(
        code="RESULTS_NOT_IN_STATE", detail="ok", repair="deterministic",
        payload={"results": {"t": []}, "filename": "f.docx", "module": "M4"})])
    assert res.repaired == ["ok"]


# --- recompose: the doctor rewrites, instead of asking -----------------------

_RECOMPOSE = Finding(
    code="CHAPTERS_NEED_RECOMPOSE", detail="Đang viết lại: methodology.",
    repair="recompose",
    payload={"chapters": ["methodology"], "stub": ["methodology"],
             "uncited": [], "tableless": []},
)


class _CsStore(_Store):
    """A store whose full context has one good chapter and one stub."""

    def load_full_context_store(self):
        return {"m5_writing": {"final_sections": [
            {"chapter_name": "intro", "title": "C1", "prose": "Giới thiệu. " * 400},
            {"chapter_name": "methodology", "title": "C3",
             "prose": "Chưa thể biên soạn Chương 3 theo các yêu cầu đã nêu."},
        ]}}


def test_a_rewritten_chapter_replaces_the_stub_and_keeps_the_others(monkeypatch):
    import orchestrator.tools.m5_writing as M
    monkeypatch.setattr(M, "compose_all_sections", lambda cs, chapters=None, **kw: [
        {"chapter_name": "methodology", "title": "C3", "prose": "Chương 3 thật. " * 300}])
    store = _CsStore()
    apply_findings(store, [_RECOMPOSE])

    module, writes, _reason, _kw = store.commits[0]
    assert module == "M5"
    assert "Chương 3 thật." in writes["chapters"]["methodology"]["prose"]


def test_chapters_stay_in_canonical_order(monkeypatch):
    import orchestrator.tools.m5_writing as M
    monkeypatch.setattr(M, "compose_all_sections", lambda cs, chapters=None, **kw: [
        {"chapter_name": "methodology", "title": "C3", "prose": "Chương 3 thật. " * 300}])
    store = _CsStore()
    apply_findings(store, [_RECOMPOSE])
    names = list(store.commits[0][1]["chapters"])
    assert names == ["methodology"]


def test_a_compose_that_returns_another_stub_is_not_committed(monkeypatch):
    """A failed compose must not replace a bad chapter with an empty one."""
    import orchestrator.tools.m5_writing as M
    monkeypatch.setattr(M, "compose_all_sections", lambda cs, chapters=None, **kw: [
        {"chapter_name": "methodology", "prose": "Chưa thể biên soạn Chương 3."}])
    store = _CsStore()
    res = apply_findings(store, [_RECOMPOSE])
    assert not store.commits
    assert res.repaired == []


def test_a_compose_returning_nothing_is_not_committed(monkeypatch):
    import orchestrator.tools.m5_writing as M
    monkeypatch.setattr(M, "compose_all_sections", lambda cs, chapters=None, **kw: [])
    store = _CsStore()
    apply_findings(store, [_RECOMPOSE])
    assert not store.commits


def test_the_same_recompose_asked_twice_is_not_paid_for_twice(monkeypatch):
    """A rewrite that did not fix the chapter must not run again next turn.

    Recomposing four chapters is the most expensive thing the doctor does. If
    the result still fails its check, the identical finding arrives next turn —
    and without this it would be rewritten again, every turn, forever.
    """
    import orchestrator.tools.m5_writing as M
    monkeypatch.setattr(M, "compose_all_sections", lambda cs, chapters=None, **kw: [
        {"chapter_name": "methodology", "title": "C3", "prose": "Chương 3 thật. " * 300}])
    store = _CsStore()
    apply_findings(store, [_RECOMPOSE])
    assert len(store.commits) == 1

    res = apply_findings(store, [_RECOMPOSE])           # same finding again
    assert len(store.commits) == 1, "the recompose was paid for twice"
    assert store.log["CHAPTERS_NEED_RECOMPOSE"]["exhausted"] is True
    assert res.directive and "Đang viết lại" in res.directive


def test_a_recompose_of_DIFFERENT_chapters_still_runs(monkeypatch):
    import orchestrator.tools.m5_writing as M
    # Composes whatever it is asked for, so the second call is a real second
    # repair rather than a stub that happens to return the wrong chapter.
    monkeypatch.setattr(M, "compose_all_sections", lambda cs, chapters=None, **kw: [
        {"chapter_name": c, "title": c, "prose": f"Nội dung {c}. " * 300}
        for c in (chapters or [])])
    store = _CsStore()
    apply_findings(store, [_RECOMPOSE])
    other = Finding(code="CHAPTERS_NEED_RECOMPOSE", detail="Đang viết lại: intro.",
                    repair="recompose",
                    payload={"chapters": ["intro"], "stub": ["intro"],
                             "uncited": [], "tableless": []})
    apply_findings(store, [other])
    assert len(store.commits) == 2, "a different set of chapters must still be fixed"


class _M4Store(_Store):
    """A store whose M4 results can change during the doctor pass."""

    def __init__(self, results, **kw):
        super().__init__(**kw)
        self.results = results

    def load_full_context_store(self):
        return {"m4_analysis": {"results": self.results}}

    def commit_slice(self, module, writes, reason, **kw):
        if "results" in writes:
            self.results = writes["results"]
        return super().commit_slice(module, writes, reason, **kw)


def _figures_finding(stale):
    return Finding(
        code="FIGURES_NOT_LINKED", detail="Đã gắn 4 ảnh.", repair="deterministic",
        payload={"module": "M4", "filename": "_Result.docx",
                 "results": {**stale, "source_figures": {"structural_paths": "a.png"}},
                 "figures": {"structural_paths": "a.png"}})


def test_linking_figures_does_not_restore_the_pre_repair_snapshot(monkeypatch):
    import app.doctor_adapter as D
    monkeypatch.setattr(D, "_with_resolved_figures", lambda store, results: results)
    # diagnose() saw the unrenderable block; a re-extract replaced it before
    # this repair ran. The figures must land on the repaired block.
    store = _M4Store({"measurement_model": [{"construct": "ATT"}]})
    apply_findings(store, [_figures_finding({"```markdown": [{"label": "x"}]})])

    assert "```markdown" not in store.results
    assert store.results["measurement_model"] == [{"construct": "ATT"}]
    assert store.results["source_figures"] == {"structural_paths": "a.png"}


def test_figures_already_linked_by_the_reparse_are_a_no_op():
    store = _M4Store({"measurement_model": [], "source_figures": {"x": "b.png"}})
    res = apply_findings(store, [_figures_finding({})])
    assert not store.commits
    assert res.repaired == []


def test_unrenderable_results_never_ask_the_student_for_another_file():
    finding = Finding(code="RESULTS_NOT_RENDERABLE", detail="Kết quả đã lưu nhưng…",
                      repair="reparse",
                      payload={"module": "M4", "filename": "_Result.docx", "text": "t"})
    store = _Store(log={"RESULTS_NOT_RENDERABLE": {"exhausted": True}})
    res = apply_findings(store, [finding])

    assert "nói thẳng với sinh viên cần gửi gì" not in (res.directive or "")
    assert "uploads/_Result.docx.txt" in res.directive
    assert "never ask them to resend" in res.directive

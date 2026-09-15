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
    assert res.repaired == ["đọc lại kết quả"]


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

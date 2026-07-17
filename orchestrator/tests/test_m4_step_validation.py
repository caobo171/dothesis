"""Phase 7: self-validation on the orchestrator step-parse path."""
import pytest

pytest.importorskip("thesis_stats")

from orchestrator.schemas.m4 import M4Output, StepResult
from orchestrator.tools import m4_analysis
from orchestrator.tools.m4_analysis import _validate_step_table, run_analysis_step


def test_validate_step_table_clean_passes():
    result = {"step_name": "measurement", "table": [{"item": "X1", "loading": 0.81}]}
    v = _validate_step_table(result, "SmartPLS")
    assert v["hard"] == 0


def test_validate_step_table_catches_impossible_t_p():
    result = {"step_name": "structural",
              "table": [{"path": "LS -> PI", "beta": 0.34, "t": 7.01, "p": 0.48}]}
    v = _validate_step_table(result, "SmartPLS")
    assert any(f["check"] == "consistency.t_p" for f in v["findings"])


def test_validate_step_table_empty_is_none():
    assert _validate_step_table({"step_name": "s", "table": []}, "SmartPLS") is None


def test_run_analysis_step_attaches_validation(monkeypatch):
    monkeypatch.setattr(m4_analysis, "dispatch_parse", lambda dt, txt, sn: {
        "step_name": sn, "table": [{"path": "LS -> PI", "t": 7.01, "p": 0.48}],
        "thresholds_met": None, "interpretation": "", "raw_paste_excerpt": "", "parser": "regex"})
    out = run_analysis_step.func("structural", {"paste": "x", "data_type": "SmartPLS"})
    assert out["validation"]["hard"] >= 1


def test_run_analysis_step_fail_open_without_engine(monkeypatch):
    import builtins
    real = builtins.__import__

    def fake(name, *a, **k):
        if name == "thesis_stats" or name.startswith("thesis_stats"):
            raise ModuleNotFoundError(name="thesis_stats")
        return real(name, *a, **k)

    monkeypatch.setattr(m4_analysis, "dispatch_parse", lambda dt, txt, sn: {
        "step_name": sn, "table": [{"item": "X1", "loading": 0.8}], "parser": "regex"})
    monkeypatch.setattr(builtins, "__import__", fake)
    out = run_analysis_step.func("m", {"paste": "x", "data_type": "SmartPLS"})
    assert out["validation"] is None  # fail-open, table still returned
    assert out["table"]


def test_stepresult_validation_field_and_backward_compat():
    # New field accepted.
    sr = StepResult(step_name="s", table=[], validation={"passed": True, "hard": 0, "soft": 0, "findings": []})
    assert sr.validation["passed"] is True
    # Old persisted dict (no validation key) still validates.
    old = {"step_name": "s", "table": [{"item": "X1", "loading": 0.8}], "parser": "regex"}
    M4Output(data_type_detected="SmartPLS", analysis_outline={"sections": []},
             results={"s": old})

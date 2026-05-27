import pytest
from unittest.mock import MagicMock

from orchestrator.tools.m4_analysis import (
    detect_data_type, generate_analysis_outline, interpret_result,
    run_analysis_step,
)


def test_detect_data_type_spss_by_extension(tmp_path):
    f = tmp_path / "data.sav"; f.write_bytes(b"\x00")
    out = detect_data_type.invoke({"file_path": str(f)})
    assert out == "SPSS"


def test_detect_data_type_smartpls_by_html_signature(tmp_path):
    f = tmp_path / "report.html"
    f.write_text("<html><body>SmartPLS 4 PLS Algorithm Results — Outer Loadings</body></html>")
    out = detect_data_type.invoke({"file_path": str(f)})
    assert out == "SmartPLS"


def test_detect_data_type_qualitative_text(tmp_path):
    f = tmp_path / "transcript.txt"
    f.write_text("Interviewer: tell me about your experience.\nParticipant: ...")
    out = detect_data_type.invoke({"file_path": str(f)})
    assert out == "Qualitative"


def test_detect_data_type_unknown(tmp_path):
    f = tmp_path / "binary.bin"; f.write_bytes(b"\xff" * 100)
    out = detect_data_type.invoke({"file_path": str(f)})
    assert out == "Unknown"


def test_generate_analysis_outline_spss():
    out = generate_analysis_outline.invoke({
        "data_type": "SPSS", "methodology": {"design": "Regression"},
    })
    assert "sections" in out
    assert any("descriptive" in s.lower() for s in out["sections"])


def test_generate_analysis_outline_smartpls():
    out = generate_analysis_outline.invoke({
        "data_type": "SmartPLS", "methodology": {"design": "PLS-SEM"},
    })
    assert any("htmt" in s.lower() or "loadings" in s.lower() for s in out["sections"])



def test_interpret_result_in_vietnamese(monkeypatch):
    fake = MagicMock(); fake.invoke.return_value.content = "Diễn giải kết quả..."
    monkeypatch.setattr("orchestrator.tools.m4_analysis._get_llm", lambda: fake)
    out = interpret_result.invoke({"result": {"alpha": 0.84}, "language": "vi"})
    assert isinstance(out, str) and len(out) > 0


def test_run_analysis_step_dispatches_to_spss_parser(monkeypatch):
    """run_analysis_step calls dispatch_parse with the data_type from `data`."""
    from orchestrator.tools.m4_analysis import run_analysis_step

    captured = {}
    def fake_dispatch(data_type, text, step_name):
        captured["data_type"] = data_type
        captured["step_name"] = step_name
        return {"step_name": step_name, "table": [], "interpretation": "ok",
                "parser": "regex"}
    monkeypatch.setattr(
        "orchestrator.tools.m4_analysis.dispatch_parse", fake_dispatch
    )
    result = run_analysis_step.invoke({
        "step_name": "Regression Analysis",
        "data": {"paste": "raw spss text", "data_type": "SPSS"},
    })
    assert captured["data_type"] == "SPSS"
    assert captured["step_name"] == "Regression Analysis"
    assert result["parser"] == "regex"


def test_run_analysis_step_returns_stub_on_dispatch_none(monkeypatch):
    """When dispatch returns None, run_analysis_step returns a stub StepResult."""
    from orchestrator.tools.m4_analysis import run_analysis_step

    monkeypatch.setattr(
        "orchestrator.tools.m4_analysis.dispatch_parse",
        lambda dt, t, s: None,
    )
    result = run_analysis_step.invoke({
        "step_name": "Unparseable Step",
        "data": {"paste": "garbage", "data_type": "SPSS"},
    })
    assert result["parser"] == "stub"
    assert "unable" in result["interpretation"].lower()


def test_run_extra_analysis_returns_step_result(monkeypatch):
    """run_extra_analysis routes to extract_step_data + returns the result dict."""
    from orchestrator.tools.m4_analysis import run_extra_analysis

    fake_extract = MagicMock()
    fake_extract.invoke.return_value = {
        "step_name": "mediation H3", "table": [], "interpretation": "Mediation tested.",
        "parser": "llm_fallback",
    }
    monkeypatch.setattr(
        "orchestrator.tools.m4_analysis.extract_step_data", fake_extract
    )
    result = run_extra_analysis.invoke({
        "step_description": "mediation test on H3",
        "data_paste": "some output",
    })
    assert result["step_name"]
    assert result["interpretation"] == "Mediation tested."

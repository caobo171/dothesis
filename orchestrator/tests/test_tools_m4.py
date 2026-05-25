import pytest

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


def test_run_analysis_step_returns_stub():
    out = run_analysis_step.invoke({
        "step_name": "Cronbach's Alpha", "data": {"alpha": 0.84},
    })
    assert out["step"] == "Cronbach's Alpha"
    assert "summary" in out


def test_interpret_result_in_vietnamese(monkeypatch):
    from unittest.mock import MagicMock
    fake = MagicMock(); fake.invoke.return_value.content = "Diễn giải kết quả..."
    monkeypatch.setattr("orchestrator.tools.m4_analysis._get_llm", lambda: fake)
    out = interpret_result.invoke({"result": {"alpha": 0.84}, "language": "vi"})
    assert isinstance(out, str) and len(out) > 0

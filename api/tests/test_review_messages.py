from quality.review_messages import present_coherence_finding
from quality.rubric import _judge_prompt, judge_dimension


def test_numerical_finding_keeps_evidence_and_explains_in_vietnamese():
    finding = present_coherence_finding({
        "check": "coherence.number_mismatch", "severity": "hard",
        "message": "Internal English diagnostic", "location": {"hypothesis": "H1", "chapter": "results"},
        "observed": {"metric": "beta", "value": 0.8, "sentence": "ATT → INT: β = 0.8."}, "expected": 0.257,
    })
    assert "chưa khớp" in finding["issue"]
    assert "0.8" in finding["issue"] and "0.257" in finding["issue"]
    assert finding["evidence"]["sentence"] == "ATT → INT: β = 0.8."
    assert finding["severity"] == "hard"
    assert "Không sửa kết quả phân tích" in finding["fix"]


def test_unknown_attribution_is_not_presented_as_a_wrong_number():
    finding = present_coherence_finding({
        "check": "coherence.ambiguous_path_attribution", "severity": "soft",
        "message": "ambiguous", "location": {"chapter": "discussion"},
    })
    assert finding["chapter"] == "conclusion"
    assert "không phải kết luận số liệu sai" in finding["fix"]


def test_english_project_preserves_original_diagnostic():
    out = present_coherence_finding({"check": "coherence.number_mismatch", "message": "Wrong beta", "severity": "hard"}, "en")
    assert out["issue"] == "Wrong beta"


def test_writing_judge_sees_results_conclusion_and_canonical_definitions():
    context = {
        "m1_topic": {"language": "vi"},
        "m3_design": {"hypotheses": [{"id": "H2", "path": "EXP -> INT"}],
                      "constructs": [{"id": "EXP", "label": "Chuyên môn người ảnh hưởng"}]},
        "m4_analysis": {"analysis_results": {"hypothesis_tests": [{"hypothesis": "H2", "numbers": {"beta": 0.269}}]}},
        "m5_writing": {"chapters": {
            "intro": {"prose": "Introduction. " * 2000},
            "results": {"prose": "Giới thiệu chương.\n\n" + "Background. " * 1500 + "\n\nEXP → INT: β = 0.269."},
            "conclusion": {"prose": "Trải nghiệm (EXP) có ảnh hưởng tích cực."},
        }},
    }
    prompt = _judge_prompt("writing", context)
    assert "EXP → INT: β = 0.269." in prompt
    assert "Trải nghiệm (EXP)" in prompt
    assert "Chuyên môn người ảnh hưởng" in prompt
    assert "Vietnamese" in prompt and "soft advisory" in prompt


def test_semantic_judge_cannot_create_hard_findings_or_invent_quotes(monkeypatch):
    import orchestrator.tools.m5_writing as writing
    class Response:
        content = '''{"score": 0.5, "findings": [
          {"issue":"wrong label", "fix":"use definition", "severity":"hard", "evidence":{"sentence":"EXP means experience."}},
          {"issue":"invented", "fix":"fix", "evidence":{"sentence":"A quote that is not in the thesis"}}
        ]}'''
    monkeypatch.setattr(writing, "_get_llm", lambda: type("LLM", (), {"invoke": lambda self, p: Response()})())
    context = {"m5_writing": {"chapters": {"conclusion": {"prose": "EXP means experience."}}}}
    result = judge_dimension("writing", 1, "prompt", context)
    assert len(result["findings"]) == 1
    assert result["findings"][0]["severity"] == "soft"

"""F6 Mock Committee — committee questions from THIS thesis's weak points.

The plan wrote `generate_committee_questions` as a @tool taking a model-supplied
`context_store`; the F0 correction (models can't be trusted to pass real state)
makes the TOOL close over the project store, with the weakpoint logic in a pure
`committee_questions(context_store, rubric_result)` we unit-test directly. So the
plan's `generate_committee_questions.func(context_store=cs)` calls are rewritten
to exercise the pure core, plus a store-bound tool-wiring test.
"""
import json

from agent.tools.defense import committee_questions, make_defense_tools


def test_small_n_and_rejected_hypothesis_targeted():
    # Nested (full) context-store shape — what store.load_full_context_store()
    # returns and what the heuristic reads (m3_design / m4_analysis).
    cs = {"m3_design": {"methodology": "PLS-SEM", "sample_plan": {"target_n": 90},
                        "hypotheses": ["H1"]},
          "m4_analysis": {"analysis_results": "H1 not supported (p=0.21)"}}
    qs = committee_questions(cs)
    joined = " ".join(q["question"].lower() for q in qs)
    assert "sample" in joined and ("reject" in joined or "not support" in joined)


def test_always_returns_questions_even_on_empty_state():
    qs = committee_questions({})
    assert len(qs) >= 4  # the four staples


def test_rubric_findings_become_questions():
    # Each F3 rubric finding (dimensions[].findings[]) becomes a targeted
    # question so the drill hits the examiner's likely quality attack points.
    rr = {"dimensions": [{"name": "citations", "findings": [
        {"issue": "Citation (Ghost, 2099) has no matching reference.", "chapter": "intro"}]}]}
    qs = committee_questions({}, rubric_result=rr)
    assert any("ghost" in q["question"].lower() or "reference" in q["question"].lower()
               for q in qs)


def test_generate_committee_questions_tool_reads_store(monkeypatch):
    # F0 correction: the TOOL closes over the store and reads state itself (no
    # model-supplied context_store). Stub the rubric's LLM judge so no test hits
    # a live model (score_thesis fires judge dims); the tool's rubric pass is
    # best-effort anyway.
    import orchestrator.tools.m5_writing as _m5

    class _Resp:
        content = '{"score": 0.7, "findings": []}'

    monkeypatch.setattr(_m5, "_get_llm",
                        lambda: type("L", (), {"invoke": lambda self, p: _Resp()})())

    class _Store:
        def load_full_context_store(self):
            return {"m3_design": {"methodology": "PLS-SEM", "sample_plan": {"target_n": 80}},
                    "m4_analysis": {"analysis_results": "H1 rejected"}}

        def get_institution_profile(self):
            return {}

        def get_advisor_feedback(self):
            return []

    tools = {t.name: t for t in make_defense_tools(_Store())}
    assert "generate_committee_questions" in tools
    env = json.loads(tools["generate_committee_questions"].func())
    # New contract: full envelope, not a bare list.
    assert set(env) >= {"questions", "readiness", "meta"}
    assert env["questions"] and env["meta"]["rubric_available"] is True
    assert env["readiness"]["verdict"] in ("not_ready", "ready_with_disclosures", "ready")


def test_tool_falls_back_when_rubric_raises(monkeypatch):
    # score_thesis raising → tool still returns an envelope, rubric_available False.
    import quality.rubric as _rub
    monkeypatch.setattr(_rub, "score_thesis", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))

    class _Store:
        def load_full_context_store(self):
            return {"m3_design": {"sample_plan": {"target_n": 80}}}

        def get_institution_profile(self):
            return {}

        def get_advisor_feedback(self):
            return []

    tools = {t.name: t for t in make_defense_tools(_Store())}
    env = json.loads(tools["generate_committee_questions"].func())
    assert env["meta"]["rubric_available"] is False
    assert env["questions"]  # staples + state questions still present

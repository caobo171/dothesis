"""Eval harness for prerequisite reconstruction (Phase 3 backfill go/no-go).

Measures whether `reconstruct_artifact` can infer a SKIPPED `design` (M3) from a
student's existing `analysis` (M4) + `topic` (M1) well enough to be worth wiring
behind a confirm gate. For each realistic "enter at analysis" fixture it reports:

  - DoD validity: does the reconstructed design pass dod_design (content complete)?
  - Plausibility: an independent LLM judge rates 0-10 how consistent the inferred
    design is with the evidence (independent of the generator — SagaLLM principle).

Run:  set -a && source .env && set +a && api/.venv/bin/python -m orchestrator.evals.backfill_eval

This is a measurement tool, not a unit test (it makes real LLM calls).
"""
from __future__ import annotations

import json
import os

from orchestrator.artifacts import dod_design
from orchestrator.backfill import reconstruct_artifact
from orchestrator.state import ContextStore


# --- Realistic fixtures: rich downstream analysis + topic, NO design ---------
FIXTURES = [
    {
        "name": "Quant · PLS-SEM (SmartPLS)",
        "cs": ContextStore(
            m1_topic={
                "research_title": "The effect of TikTok engagement on Gen Z purchase intention",
                "research_type": "quantitative",
                "research_questions": ["Does TikTok engagement increase purchase intention?"],
            },
            m4_analysis={
                "data_type_detected": "SmartPLS",
                "results": {
                    "measurement_model": {"step_name": "reliability & validity",
                        "interpretation": "CR 0.87-0.92, AVE 0.61-0.74 for constructs "
                        "Engagement, Trust, Purchase Intention; N = 237."},
                    "structural_model": {"step_name": "path coefficients",
                        "interpretation": "Engagement -> Purchase Intention beta=0.42 (p<.001); "
                        "Trust -> Purchase Intention beta=0.31 (p<.01); R^2 = 0.38."},
                },
            },
        ),
    },
    {
        "name": "Quant · Multiple Regression (SPSS)",
        "cs": ContextStore(
            m1_topic={
                "research_title": "Predictors of academic burnout among university students",
                "research_type": "quantitative",
                "research_questions": ["Which factors predict academic burnout?"],
            },
            m4_analysis={
                "data_type_detected": "SPSS",
                "results": {
                    "descriptives": {"step_name": "sample", "interpretation": "N = 312 students."},
                    "regression": {"step_name": "multiple regression",
                        "interpretation": "Workload (beta=0.45, p<.001) and poor sleep "
                        "(beta=0.29, p<.01) predicted burnout; adjusted R^2 = 0.41."},
                },
            },
        ),
    },
    {
        "name": "Qual · Thematic Analysis",
        "cs": ContextStore(
            m1_topic={
                "research_title": "Lived experiences of first-generation university students",
                "research_type": "qualitative",
                "research_questions": ["How do first-gen students experience belonging?"],
            },
            m4_analysis={
                "data_type_detected": "Qualitative",
                "qual_themes": [{"theme": "Navigating unfamiliar systems"},
                                {"theme": "Family expectations vs. independence"},
                                {"theme": "Finding belonging"}],
                "qual_codes": [{"code": "imposter feelings"}, {"code": "financial strain"}],
                "results": {"coding": {"step_name": "thematic analysis",
                    "interpretation": "15 semi-structured interviews; 3 themes from 22 codes."}},
            },
        ),
    },
]


def _judge_llm():
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.5-flash"),
        temperature=0.0,
        timeout=int(os.getenv("ORCHESTRATOR_LLM_TIMEOUT", "20")),
    )


def _plausibility(evidence: dict, candidate: dict) -> tuple[int, str]:
    """Independent judge: is the inferred design consistent with the evidence?"""
    prompt = (
        "An AI inferred a research DESIGN from a student's existing analysis + topic, "
        "because they skipped documenting it. Rate how PLAUSIBLE and CONSISTENT the "
        "inferred design is with the evidence (0 = contradicts/implausible, "
        "10 = exactly what would have produced this analysis).\n\n"
        f"Evidence:\n{json.dumps(evidence, default=str, ensure_ascii=False)}\n\n"
        f"Inferred design:\n{json.dumps(candidate, default=str, ensure_ascii=False)}\n\n"
        'Respond ONLY as JSON: {"score": <0-10 int>, "reason": "<one sentence>"}.'
    )
    raw = _judge_llm().invoke(prompt).content.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    data = json.loads(raw)
    return int(data["score"]), data.get("reason", "")


def main() -> None:
    print("=" * 72)
    print("BACKFILL RECONSTRUCTION EVAL — infer skipped 'design' from analysis")
    print("=" * 72)
    dod_passes, scores = 0, []
    for fx in FIXTURES:
        cand = reconstruct_artifact("design", fx["cs"])
        dod = dod_design(cand)
        evidence = {k: getattr(fx["cs"], k) for k in ("m1_topic", "m4_analysis")
                    if getattr(fx["cs"], k)}
        try:
            score, reason = _plausibility(evidence, cand)
        except Exception as e:  # noqa: BLE001
            score, reason = -1, f"judge failed: {e}"
        dod_passes += 1 if dod.done else 0
        scores.append(score)
        print(f"\n[{fx['name']}]")
        print(f"  inferred: paradigm={cand.get('paradigm')!r} design={cand.get('design')!r} "
              f"tool={cand.get('tool')!r} N={cand.get('target_sample_size')!r}")
        print(f"  DoD: {'PASS' if dod.done else 'FAIL — ' + '; '.join(dod.gaps)}")
        print(f"  plausibility (independent judge): {score}/10 — {reason}")

    valid = [s for s in scores if s >= 0]
    avg = sum(valid) / len(valid) if valid else 0
    print("\n" + "=" * 72)
    print(f"VERDICT: DoD pass {dod_passes}/{len(FIXTURES)} · "
          f"avg plausibility {avg:.1f}/10")
    verdict = ("GO — wire behind a DoD + confirm gate"
               if dod_passes == len(FIXTURES) and avg >= 7
               else "NO-GO / revisit — reconstruction quality insufficient")
    print(f"  -> {verdict}")
    print("=" * 72)


if __name__ == "__main__":
    main()

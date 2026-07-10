"""Model shootout: run DoThesis's probe suite (and, optionally, compose fixtures scored by the
F3 rubric) across candidate models via one OpenAI-compatible client, and rank them by quality x
reliability x Vietnamese x true cost. All network is behind _complete so tests stub it.

No production model is auto-switched: this emits a ranked report + a CI gate that inform a human
who sets DOTHESIS_AGENT_MODEL.
"""
from __future__ import annotations
import logging
import os
import time

from quality.model_prices import cost
from quality.probes import score_probe

logger = logging.getLogger(__name__)


def _complete(model: str, prompt: str, system: str | None = None) -> tuple[str, dict]:
    """One network chokepoint — OpenRouter (OpenAI-compatible). Tests stub this.

    langchain_openai is imported lazily so the package imports (and the stubbed
    tests run) without the eval-only network dep installed."""
    from langchain_openai import ChatOpenAI  # noqa: PLC0415 — eval-only, lazy
    llm = ChatOpenAI(model=model, base_url="https://openrouter.ai/api/v1",
                     api_key=os.environ.get("OPENROUTER_API_KEY", ""))
    msgs = ([("system", system)] if system else []) + [("human", prompt)]
    resp = llm.invoke(msgs)
    usage = getattr(resp, "usage_metadata", {}) or {}
    return (resp.content or "",
            {"in": usage.get("input_tokens", 0), "out": usage.get("output_tokens", 0)})


def evaluate_models(models: list[str], probes: list[dict],
                    compose_fixtures: list[dict] | None = None) -> list[dict]:
    """Run the probe suite across each model; one row per model with per-dimension
    reliability + true cost. A single probe/model failure is isolated (counted in
    `errors`), never aborting the run."""
    rows: list[dict] = []
    for model in models:
        marker = instr = vi = 0
        marker_n = instr_n = vi_n = 0
        tin = tout = errors = 0
        t0 = time.time()
        for probe in probes:
            kind = probe["expect"]["kind"]
            try:
                text, usage = _complete(model, probe["prompt"], probe.get("system"))
                tin += usage.get("in", 0)
                tout += usage.get("out", 0)
                ok = score_probe(text, probe["expect"])
            except Exception:
                logger.exception("model_eval: %s failed on %s", model, probe.get("id"))
                errors += 1
                ok = False
            if kind == "marker":
                marker_n += 1
                marker += int(ok)
            elif kind == "language":
                vi_n += 1
                vi += int(ok)
            else:
                instr_n += 1
                instr += int(ok)
        latency = int((time.time() - t0) * 1000)
        row = {
            "model": model,
            "marker_reliability": round(marker / marker_n, 3) if marker_n else None,
            "instruction_reliability": round(instr / instr_n, 3) if instr_n else None,
            "vietnamese": round(vi / vi_n, 3) if vi_n else None,
            "tokens": {"in": tin, "out": tout},
            "cost_per_task": cost(model, tin, tout),
            "latency_ms": latency, "errors": errors,
        }
        # Compose-quality (F3 rubric) is folded in only when fixtures are supplied
        # AND F3 has landed — evaluate_compose_quality is a separate task (F9 Task 4).
        if compose_fixtures:
            row["quality"] = evaluate_compose_quality(model, compose_fixtures)
        rows.append(row)
    return rows


def evaluate_compose_quality(model: str, fixtures: list[dict]) -> float | None:
    """Run the model on compose fixtures and score the output with the F3 rubric.

    Deferred wiring: the F3 rubric (quality.rubric.score_thesis) lands in F3. Until
    then this returns None if the rubric isn't importable, so evaluate_models stays
    usable on probes alone (F9 probe tier)."""
    try:
        from quality.rubric import score_thesis  # noqa: PLC0415 — F3 dependency
    except Exception:
        return None
    scores = []
    for fx in fixtures:
        try:
            prose, _ = _complete(model, fx["compose_prompt"])
            cs = dict(fx.get("context_store") or {})
            cs.setdefault("m5_writing", {})["final_sections"] = [{"title": "Draft", "prose": prose}]
            scores.append(score_thesis(cs)["overall"])
        except Exception:
            logger.exception("model_eval: compose failed for %s", model)
    return round(sum(scores) / len(scores), 3) if scores else None


def recommend(rows: list[dict], marker_floor: float = 0.9) -> str | None:
    """Best quality-per-dollar model that clears the marker-reliability floor. None
    if nothing clears the floor (don't recommend an unreliable model however cheap)."""
    eligible = [r for r in rows if (r.get("marker_reliability") or 0) >= marker_floor]
    if not eligible:
        return None

    def value(r):
        c = r.get("cost_per_task") or 1e-9  # guard divide-by-zero
        return (r.get("quality") or 0) / c
    return max(eligible, key=value)["model"]


def render_report(rows: list[dict]) -> str:
    """Ranked markdown table for the docs/CI log."""
    head = "| model | quality | marker | instr | vi | $/task | errors |\n|---|---|---|---|---|---|---|"
    body = "\n".join(
        f"| {r['model']} | {r.get('quality')} | {r.get('marker_reliability')} | "
        f"{r.get('instruction_reliability')} | {r.get('vietnamese')} | {r.get('cost_per_task')} | "
        f"{r.get('errors')} |" for r in rows)
    return head + "\n" + body


def run_model_gate(candidate_row: dict, incumbent_row: dict, floors: dict) -> int:
    """Exit code for a CI swap gate: 1 (fail) if the candidate is below any floor,
    else 0. incumbent_row is accepted for future relative-regression checks."""
    for k, floor in floors.items():
        if (candidate_row.get(k) or 0) < floor:
            return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    import sys
    from quality.probes import load_probes
    models = (sys.argv[1].split(",") if len(sys.argv) > 1 else [])
    probes = load_probes("quality/fixtures/model_probes")
    rows = evaluate_models(models, probes)
    print(render_report(rows))
    print("\nRecommended:", recommend(rows))

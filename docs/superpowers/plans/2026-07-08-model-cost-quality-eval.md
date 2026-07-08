# Model Cost/Quality Evaluation Implementation Plan (F9)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One command that ranks candidate central-brain models on rubric quality, marker/instruction reliability, Vietnamese quality, and true cost per task — so the model swap is data-backed, and repeatable as prices change.

**Architecture:** A dated price table + a behavioral probe suite (markers/instruction/language) + a compose-quality tie-in via F3's `score_thesis`, run through a unified OpenAI-compatible (OpenRouter) client so all models are one string apart. Emits a ranked report + a CI gate.

**Tech Stack:** Python, `langchain_openai` (OpenAI-compatible client → OpenRouter), F3 `quality/rubric.py`, pytest via `./run.sh`. No network in tests (client is stubbed).

## Global Constraints

- **No auto-switch of production model** — the report informs a human who sets `DOTHESIS_AGENT_MODEL`.
- **No live API in tests** — the model client is isolated behind one function tests stub.
- **True cost, not sticker** — always cost = tokens × price table; a "thinking" model's output tokens count.
- **Depends on F3** (`score_thesis`) for the quality dimension.
- **Price table is dated + hand-maintained** — comment the source/date on each entry.
- **Comment the decision behind each change.**

---

### Task 1: Price table + `cost()`

**Files:**
- Create: `quality/model_prices.py`
- Test: `api/tests/test_model_prices.py`

**Interfaces:**
- Produces: `MODEL_PRICES: dict[str, dict]` and `cost(model: str, in_tokens: int, out_tokens: int) -> float | None`.

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_model_prices.py
from quality.model_prices import cost, MODEL_PRICES


def test_cost_math():
    # 1M in + 1M out at ($0.33, $1.95) = 2.28
    assert abs(cost("qwen3.6-plus", 1_000_000, 1_000_000) - 2.28) < 1e-6


def test_unknown_model_is_none():
    assert cost("does-not-exist", 100, 100) is None


def test_candidates_present():
    for m in ("gemini-3.5-flash", "qwen3.6-plus", "gpt-5.4-mini"):
        assert m in MODEL_PRICES
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd api && ./run.sh pytest tests/test_model_prices.py -q` → FAIL (no module).

- [ ] **Step 3: Implement the table + cost**

```python
# quality/model_prices.py
"""Dated $/1M-token price table for candidate central-brain models + a cost helper.
Hand-maintained — update the numbers and `updated` when prices move (they do, monthly).
Sources: July-2026 pricing research (OpenRouter / provider pages)."""
from __future__ import annotations

# in/out = USD per 1,000,000 tokens.
MODEL_PRICES: dict[str, dict] = {
    "gemini-3.5-flash": {"in": 1.50, "out": 9.00, "provider": "google",
                         "note": "current default; output tripled in 2026", "updated": "2026-07-08"},
    "gemini-2.5-flash": {"in": 0.30, "out": 2.50, "provider": "google",
                         "note": "cheaper but weaker instruction-following", "updated": "2026-07-08"},
    "gpt-5.4-mini": {"in": 0.40, "out": 1.75, "provider": "openai",
                     "note": "safe western drop-in", "updated": "2026-07-08"},
    "qwen3.6-plus": {"in": 0.325, "out": 1.95, "provider": "openrouter",
                     "note": "SEA-HELM Vietnamese leader; 1M ctx", "updated": "2026-07-08"},
    "deepseek-v4-flash": {"in": 0.09, "out": 0.18, "provider": "openrouter",
                          "note": "cheapest; reliability/VN unproven", "updated": "2026-07-08"},
    "glm-5.2": {"in": 1.40, "out": 4.40, "provider": "openrouter",
                "note": "over-thinks; output tokens balloon", "updated": "2026-07-08"},
    "claude-haiku-4-5": {"in": 1.00, "out": 5.00, "provider": "anthropic",
                         "note": "strong agentic, mid-price", "updated": "2026-07-08"},
}


def cost(model: str, in_tokens: int, out_tokens: int) -> float | None:
    p = MODEL_PRICES.get(model)
    if not p:
        return None
    return round(in_tokens / 1_000_000 * p["in"] + out_tokens / 1_000_000 * p["out"], 6)
```

- [ ] **Step 4: Run to verify it passes** → PASS.

- [ ] **Step 5: Commit**

```bash
git add quality/model_prices.py api/tests/test_model_prices.py
git commit -m "feat(model-eval): dated price table + cost()

Hand-maintained $/1M table for candidate central-brain models; cost() computes
true per-task cost from token counts.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Behavioral probe suite + `score_probe`

**Files:**
- Create: `quality/probes.py`, `quality/fixtures/model_probes/` (JSON probes)
- Test: `api/tests/test_probes.py`

**Interfaces:**
- Produces: `score_probe(completion: str, expect: dict) -> bool` handling kinds `marker`, `regex`, `json`, `language`. `load_probes(dir) -> list[dict]`.

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_probes.py
from quality.probes import score_probe


def test_marker_probe_pass_and_fail():
    assert score_probe("Pick one:\n[OPTIONS] a | b | c", {"kind": "marker", "value": "OPTIONS"})
    assert not score_probe("Pick one: a, b, c", {"kind": "marker", "value": "OPTIONS"})


def test_json_probe():
    assert score_probe('{"x": 1}', {"kind": "json", "value": None})
    assert not score_probe("not json", {"kind": "json", "value": None})


def test_language_probe_vietnamese():
    vi = "Đây là một câu trả lời bằng tiếng Việt về phương pháp nghiên cứu."
    assert score_probe(vi, {"kind": "language", "value": "vi"})
    assert not score_probe("This is English.", {"kind": "language", "value": "vi"})
```

- [ ] **Step 2: Run to verify it fails** → FAIL.

- [ ] **Step 3: Implement `score_probe` + seed probes**

```python
# quality/probes.py
"""Behavioral probes for DoThesis's model requirements — markers, instruction-following,
language. Deterministic scoring where possible; the runner adds a judge for fluency."""
from __future__ import annotations
import json
import re
from pathlib import Path

# A few high-signal Vietnamese function words for a cheap language check (no heavy dep).
_VI_HINTS = ("của", "và", "nghiên", "được", "trong", "này", "các", "là", "phương", "cứu")


def score_probe(completion: str, expect: dict) -> bool:
    kind = expect.get("kind")
    val = expect.get("value")
    text = completion or ""
    if kind == "marker":
        return f"[{val}]" in text or f"{{{{{ '' }}}}}" and (f"[{val}]" in text)
    if kind == "regex":
        return re.search(val, text) is not None
    if kind == "json":
        s, e = text.find("{"), text.rfind("}")
        if s == -1 or e == -1:
            return False
        try:
            json.loads(text[s:e + 1]); return True
        except Exception:
            return False
    if kind == "language" and val == "vi":
        low = text.lower()
        return sum(1 for h in _VI_HINTS if h in low) >= 2
    return False


def load_probes(directory: str) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(directory).glob("*.json"))]
```

> **Fix the marker branch** during implementation to a clean `return f"[{val}]" in text` — the
> snippet above shows the intent; the `{{cite}}` marker is checked via a `regex` probe
> (`\{\{\s*cite:`), not the marker kind.

Seed `quality/fixtures/model_probes/`: `options.json` (prompt that should yield `[OPTIONS]`),
`cite.json` (regex `\{\{\s*cite:` after a factual claim), `json_only.json`, `vi_answer.json`
(VN prompt, `language: vi`), `terse.json` (regex for ≤2 sentences).

- [ ] **Step 4: Run to verify it passes** → PASS.

- [ ] **Step 5: Commit**

```bash
git add quality/probes.py quality/fixtures/model_probes api/tests/test_probes.py
git commit -m "feat(model-eval): behavioral probe suite + score_probe

Deterministic checks for the marker/instruction/language contract DoThesis
depends on — the fast, decisive signal a per-token price ignores.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Multi-model runner (stubbed client in tests)

**Files:**
- Create: `quality/model_eval.py`
- Test: `api/tests/test_model_eval.py`

**Interfaces:**
- Produces:
  - `run_model(model, probes) -> dict` — `{completions, usage:{in,out}, latency_ms, errors}` via `_complete(model, prompt, system)`.
  - `evaluate_models(models, probes) -> list[dict]` — per-model row `{model, marker_reliability, instruction_reliability, vietnamese, tokens, cost_per_task, errors}`.
  - `_complete(model, prompt, system=None) -> tuple[str, dict]` — the ONE network chokepoint (OpenRouter `ChatOpenAI`); tests stub it.

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_model_eval.py
import quality.model_eval as me


def test_evaluate_ranks_and_costs(monkeypatch):
    probes = [{"id": "opt", "prompt": "pick", "expect": {"kind": "marker", "value": "OPTIONS"}},
              {"id": "vi", "prompt": "trả lời", "expect": {"kind": "language", "value": "vi"}}]

    def fake_complete(model, prompt, system=None):
        if model == "good":
            return ("[OPTIONS] a | b\nĐây là nghiên cứu của tôi và các bạn", {"in": 100, "out": 50})
        return ("no markers, english only", {"in": 100, "out": 50})
    monkeypatch.setattr(me, "_complete", fake_complete)
    monkeypatch.setattr(me, "cost", lambda m, i, o: 0.001 if m == "good" else 0.002)

    rows = me.evaluate_models(["good", "bad"], probes)
    by = {r["model"]: r for r in rows}
    assert by["good"]["marker_reliability"] == 1.0
    assert by["bad"]["marker_reliability"] == 0.0
    assert by["good"]["vietnamese"] >= 0.5


def test_model_failure_is_isolated(monkeypatch):
    def boom(model, prompt, system=None): raise RuntimeError("provider down")
    monkeypatch.setattr(me, "_complete", boom)
    rows = me.evaluate_models(["x"], [{"id": "a", "prompt": "p", "expect": {"kind": "marker", "value": "OPTIONS"}}])
    assert rows[0]["errors"] >= 1 and rows[0]["marker_reliability"] == 0.0
```

- [ ] **Step 2: Run to verify it fails** → FAIL.

- [ ] **Step 3: Implement the runner**

```python
# quality/model_eval.py
"""Model shootout: run DoThesis's probe suite (and, optionally, compose fixtures scored by the
F3 rubric) across candidate models via one OpenAI-compatible client, and rank them by quality x
reliability x Vietnamese x true cost. All network is behind _complete so tests stub it."""
from __future__ import annotations
import logging
import os
import time

from quality.model_prices import cost
from quality.probes import score_probe

logger = logging.getLogger(__name__)


def _complete(model: str, prompt: str, system: str | None = None) -> tuple[str, dict]:
    """One network chokepoint — OpenRouter (OpenAI-compatible). Tests stub this."""
    from langchain_openai import ChatOpenAI  # noqa: PLC0415
    llm = ChatOpenAI(model=model, base_url="https://openrouter.ai/api/v1",
                     api_key=os.environ.get("OPENROUTER_API_KEY", ""))
    msgs = ([("system", system)] if system else []) + [("human", prompt)]
    resp = llm.invoke(msgs)
    usage = getattr(resp, "usage_metadata", {}) or {}
    return (resp.content or "",
            {"in": usage.get("input_tokens", 0), "out": usage.get("output_tokens", 0)})


def evaluate_models(models: list[str], probes: list[dict]) -> list[dict]:
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
                tin += usage.get("in", 0); tout += usage.get("out", 0)
                ok = score_probe(text, probe["expect"])
            except Exception:
                logger.exception("model_eval: %s failed on %s", model, probe.get("id"))
                errors += 1; ok = False
            if kind == "marker":
                marker_n += 1; marker += int(ok)
            elif kind == "language":
                vi_n += 1; vi += int(ok)
            else:
                instr_n += 1; instr += int(ok)
        latency = int((time.time() - t0) * 1000)
        rows.append({
            "model": model,
            "marker_reliability": round(marker / marker_n, 3) if marker_n else None,
            "instruction_reliability": round(instr / instr_n, 3) if instr_n else None,
            "vietnamese": round(vi / vi_n, 3) if vi_n else None,
            "tokens": {"in": tin, "out": tout},
            "cost_per_task": cost(model, tin, tout),
            "latency_ms": latency, "errors": errors,
        })
    return rows
```

- [ ] **Step 4: Run to verify it passes** → PASS.

- [ ] **Step 5: Commit**

```bash
git add quality/model_eval.py api/tests/test_model_eval.py
git commit -m "feat(model-eval): multi-model probe runner

Runs the probe suite across models through one OpenAI-compatible client;
per-model marker/instruction/VN reliability + true cost. Failures isolated.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Compose-quality tie-in (F3 rubric)

**Files:**
- Modify: `quality/model_eval.py` (add `evaluate_compose_quality`)
- Create: `quality/fixtures/model_compose/` (a couple of `{context_store, compose_prompt}` fixtures, incl. a Vietnamese one)
- Test: `api/tests/test_model_eval.py`

**Interfaces:**
- Produces: `evaluate_compose_quality(model, fixtures) -> float` — average F3 `score_thesis["overall"]` over model-composed output. Folded into each row as `quality`.

- [ ] **Step 1: Write the failing test**

```python
# add to api/tests/test_model_eval.py
def test_compose_quality_uses_rubric(monkeypatch):
    monkeypatch.setattr(me, "_complete", lambda m, p, system=None: ("composed prose", {"in": 10, "out": 10}))
    import quality.rubric as rub
    monkeypatch.setattr(rub, "score_thesis", lambda cs, **k: {"overall": 0.77})
    q = me.evaluate_compose_quality("good", [{"context_store": {"m1_topic": {}}, "compose_prompt": "write intro"}])
    assert q == 0.77
```

- [ ] **Step 2: Run to verify it fails** → FAIL.

- [ ] **Step 3: Implement**

```python
# add to quality/model_eval.py
def evaluate_compose_quality(model: str, fixtures: list[dict]) -> float | None:
    """Run the model on compose fixtures and score the output with the F3 rubric."""
    from quality.rubric import score_thesis  # noqa: PLC0415
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
```

Fold `quality = evaluate_compose_quality(model, compose_fixtures)` into each `evaluate_models`
row when compose fixtures are supplied (make it an optional arg `compose_fixtures=None`).

- [ ] **Step 4: Run to verify it passes** → PASS.

- [ ] **Step 5: Commit**

```bash
git add quality/model_eval.py quality/fixtures/model_compose api/tests/test_model_eval.py
git commit -m "feat(model-eval): compose-quality via the F3 rubric

Deep signal beyond probes — score each model's composed output (incl. a
Vietnamese fixture) with the same rubric students are graded by.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Ranked report, recommendation, CI gate, doc

**Files:**
- Modify: `quality/model_eval.py` (add `render_report`, `recommend`, `run_model_gate`, `__main__`)
- Create: `docs/observability/model-eval.md`
- Test: `api/tests/test_model_eval.py`

**Interfaces:**
- Produces:
  - `recommend(rows, marker_floor=0.9) -> str` — best quality-per-dollar row clearing the floor.
  - `render_report(rows) -> str` — a ranked markdown table.
  - `run_model_gate(candidate_row, incumbent_row, floors) -> int` — 0/1 exit code.

- [ ] **Step 1: Write the failing test**

```python
# add to api/tests/test_model_eval.py
def test_recommend_picks_best_value_above_floor():
    rows = [
        {"model": "cheapbad", "marker_reliability": 0.4, "quality": 0.8, "cost_per_task": 0.001},
        {"model": "good", "marker_reliability": 0.95, "quality": 0.82, "cost_per_task": 0.003},
        {"model": "expensive", "marker_reliability": 0.96, "quality": 0.83, "cost_per_task": 0.02},
    ]
    assert me.recommend(rows, marker_floor=0.9) == "good"


def test_gate_fails_on_reliability_regression():
    cand = {"model": "c", "marker_reliability": 0.7, "quality": 0.8}
    inc = {"model": "i", "marker_reliability": 0.95, "quality": 0.8}
    assert me.run_model_gate(cand, inc, {"marker_reliability": 0.9}) == 1
```

- [ ] **Step 2: Run to verify it fails** → FAIL.

- [ ] **Step 3: Implement report/recommend/gate + CLI**

```python
# add to quality/model_eval.py
def recommend(rows: list[dict], marker_floor: float = 0.9) -> str | None:
    eligible = [r for r in rows if (r.get("marker_reliability") or 0) >= marker_floor]
    if not eligible:
        return None
    # best quality per dollar: quality / cost (guard divide-by-zero).
    def value(r):
        c = r.get("cost_per_task") or 1e-9
        return (r.get("quality") or 0) / c
    return max(eligible, key=value)["model"]


def render_report(rows: list[dict]) -> str:
    head = "| model | quality | marker | instr | vi | $/task | errors |\n|---|---|---|---|---|---|---|"
    body = "\n".join(
        f"| {r['model']} | {r.get('quality')} | {r.get('marker_reliability')} | "
        f"{r.get('instruction_reliability')} | {r.get('vietnamese')} | {r.get('cost_per_task')} | "
        f"{r.get('errors')} |" for r in rows)
    return head + "\n" + body


def run_model_gate(candidate_row: dict, incumbent_row: dict, floors: dict) -> int:
    for k, floor in floors.items():
        if (candidate_row.get(k) or 0) < floor:
            return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    import sys
    from quality.probes import load_probes
    models = (sys.argv[1].split(",") if len(sys.argv) > 1 else list())
    probes = load_probes("quality/fixtures/model_probes")
    rows = evaluate_models(models, probes)
    print(render_report(rows))
    print("\nRecommended:", recommend(rows))
```

`docs/observability/model-eval.md`: how to run (`OPENROUTER_API_KEY=… python -m quality.model_eval
qwen3.6-plus,gpt-5.4-mini,gemini-3.5-flash`), how to read the table, how to update
`model_prices.py`, and the reliability floors the gate enforces.

- [ ] **Step 4: Run to verify it passes** → PASS.

- [ ] **Step 5: Commit**

```bash
git add quality/model_eval.py docs/observability/model-eval.md api/tests/test_model_eval.py
git commit -m "feat(model-eval): ranked report + recommendation + CI gate

One command ranks candidates by quality-per-dollar above a reliability floor and
gates a swap that regresses markers/quality. Cost-vs-quality, decided by data.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] `cd api && ./run.sh pytest tests/test_model_prices.py tests/test_probes.py tests/test_model_eval.py -q` → all PASS.
- [ ] No network in tests: grep the tests for `_complete` stubs; confirm none hit OpenRouter.
- [ ] Dry run (with a key): `OPENROUTER_API_KEY=… ./run.sh python -m quality.model_eval qwen3.6-plus,gpt-5.4-mini,gemini-3.5-flash` prints a ranked table + recommendation.

## Notes

- **Depends on F3** (`quality/rubric.score_thesis`) for the compose-quality dimension. The probe
  suite alone (Tasks 1–3, 5) is useful even before F3 lands.
- **Fix the `score_probe` marker branch** to a clean `f"[{val}]" in text`; the `{{cite}}` check is
  a `regex` probe, not a `marker` probe (noted in Task 2).
- **Keep `model_prices.py` current** — it's the one file that decays; date every edit.
- Uses OpenRouter so all providers (Google/OpenAI/Qwen/DeepSeek/GLM/Anthropic) run through one
  client; production can still call each provider's native SDK once a winner is chosen.

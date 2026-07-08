# Model Cost/Quality Evaluation ("Model Shootout") Design (F9)

**Date:** 2026-07-08
**Status:** Design — approved, pending spec review
**Motivation:** Choosing DoThesis's central brain on per-token price alone is wrong — the
model must reliably emit UI markers, follow skills, write good Vietnamese, and be cheap *per
completed thesis*, not per token. Prices move monthly (Gemini 3.5 Flash tripled), so this must
be a repeatable command, not a one-off. Reuses F3's rubric scorer.

## Problem

The team is on `gemini-3.5-flash` ($1.50/$9.00 per 1M) and suspects cheaper, better-fitting
models exist (Qwen3.6 Plus, GPT-5.4 mini, DeepSeek, GLM). But swapping the central brain risks
breaking the marker/skill contract the whole system depends on, and per-token price hides the
real cost (a "thinking" model with a low sticker can cost more per turn). There's no way to
measure quality × reliability × Vietnamese × true cost across candidates.

## Goals

- **One command** ranks candidate models on four axes: **rubric quality** (reuse F3), **marker/
  instruction reliability**, **Vietnamese quality**, and **true cost per representative task**.
- **A maintained price table** ($/1M in/out per model, dated) so cost math tracks the market.
- **A provider-agnostic runner** (OpenAI-compatible / OpenRouter) so all models run through one
  client and A/B is a one-string change.
- **A ranked report + recommendation**, and an optional **CI gate** ("don't ship a cheaper model
  that regresses quality/reliability below a bar").

## Non-goals

- Does NOT auto-switch the production model — a human reads the report and sets
  `DOTHESIS_AGENT_MODEL`.
- Not a full end-to-end thesis per model (too slow/costly) — a representative probe + compose
  suite.
- Not a general LLM leaderboard — it measures *DoThesis's* specific requirements.

## Design

### Price table

`quality/model_prices.py` — `MODEL_PRICES: dict[str, {in, out, provider, note, updated}]`,
hand-maintained with dates. `cost(model, in_tokens, out_tokens) -> float`.

### Probe suite (the fast, decisive signal)

`quality/fixtures/model_probes/*.json` — behavioral single-turn probes with a checkable
expectation:
- **Marker probes:** a turn that should emit `[OPTIONS] a | b | c`, one that should emit
  `[PAPERS]{…}`, one that should emit an inline `{{cite: … | … | …}}` after a factual claim.
- **Instruction probes:** "answer in ≤2 sentences", "return only JSON", "mirror the user's
  language" — checkable deterministically.
- **Vietnamese probes:** a VN prompt that must be answered in fluent VN (language-detect + a
  short judge for fluency).

Each probe = `{id, prompt, system?, expect: {kind: "marker"|"regex"|"json"|"language"|"judge", value}}`.
`score_probe(completion, expect) -> bool`.

### Compose-quality tie-in (the deep signal)

For a small set of `context_store` fixtures, run the model on the compose task and score the
output with **F3 `score_thesis`** (reuses the whole rubric, including Vietnamese writing
dimension). This catches quality regressions the probes can't.

### Runner

`quality/model_eval.py`:
- For each model in the candidate list: run the probe suite + compose fixtures through a unified
  `ChatOpenAI(base_url=OpenRouter, model=…)` client, capture completion + token usage + latency.
- Compute per model: `quality` (avg rubric overall), `marker_reliability` (% marker probes
  passed), `instruction_reliability`, `vietnamese` (VN probe pass + VN compose writing score),
  `tokens`, `latency_p50`, and `cost_per_task` (from the price table).
- Emit a ranked markdown/CSV table + a one-line recommendation (best quality-per-dollar that
  clears the reliability floor).

### CI gate (optional)

`run_model_gate(candidate, incumbent, floors) -> exit_code` — fail if a proposed cheaper model
drops marker-reliability or quality below configured floors vs the incumbent. Wire into the same
CI as F3's harness so a model swap is data-gated.

## Data flow

```
model_eval --models qwen3.6-plus,gpt-5.4-mini,gemini-3.5-flash
  for each model:
    probes  → marker/instruction/language pass %
    compose fixtures → F3 score_thesis → quality
    usage → cost_per_task (price table)
  → ranked table (quality × reliability × VN × $) + recommendation
```

## Error handling

- A model/provider failure on a probe ⇒ that probe scored 0 for that model + a noted error;
  the run continues (one bad model never aborts the shootout).
- Missing price ⇒ cost shown as "n/a", model still ranked on quality/reliability.
- All live-API calls isolated behind a client function so tests stub it (no network in CI).

## Testing

- **Cost math:** `cost("x", 1000, 500)` against a known price ⇒ exact float.
- **Probe scorer:** a completion containing `[OPTIONS]` ⇒ marker probe passes; missing ⇒ fails;
  JSON/regex/language kinds each covered.
- **Runner:** with a stubbed client returning canned completions for 2 fake models ⇒ a ranked
  table with the expected winner; a client that raises for one model ⇒ that model scored 0, run
  completes.
- **CI gate:** candidate below the marker floor ⇒ non-zero exit.
- No network in tests; api tests via `./run.sh`.

## Migration / rollout

1. `model_prices.py` + `cost()` (+ dated entries for the candidates from the July-2026 research).
2. Probe suite + `score_probe` (marker/instruction/language kinds).
3. `model_eval.py` runner over probes with a stubbed-in-tests OpenAI-compatible client.
4. Compose-quality tie-in (F3 `score_thesis`) + Vietnamese scoring.
5. Ranked report + recommendation + `run_model_gate` + a short `docs/observability/model-eval.md`.

## Dependencies

- **F3** (`quality/score_thesis`, `eval_harness` patterns) — the quality dimension + harness
  conventions.
- OpenRouter (or any OpenAI-compatible gateway) for uniform multi-model access; `langchain_openai`.
- Ties to **F5** — tag `quality_reviewed` events with the active model so prod quality-by-model
  trends corroborate the offline shootout.

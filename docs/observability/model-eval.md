# Model cost/quality evaluation (F9)

One command ranks candidate central-brain models on the behaviors DoThesis
actually depends on — markers, instruction-following, Vietnamese — and their
**true** per-task cost, so a model swap is data-backed and repeatable as prices
move.

## Run it

```bash
OPENROUTER_API_KEY=… ./run.sh python -m quality.model_eval \
  qwen3.6-plus,gpt-5.4-mini,gemini-3.5-flash
```

All candidates run through one OpenAI-compatible client (OpenRouter), so every
provider is one model string apart. Production can still call each provider's
native SDK once a winner is chosen.

## Read the table

`render_report` prints a ranked markdown table:

| column | meaning |
|---|---|
| quality | avg F3-rubric `overall` on compose fixtures (F9 Task 4 / needs F3; blank until then) |
| marker | fraction of `[OPTIONS]`/marker probes passed |
| instr | fraction of instruction probes passed (JSON-only, terseness, `{{cite}}`) |
| vi | fraction of Vietnamese-language probes passed |
| $/task | true cost = tokens × `model_prices.py` (a "thinking" model's output tokens count) |
| errors | isolated per-probe failures (a provider hiccup never aborts the run) |

`recommend(rows, marker_floor=0.9)` picks the best **quality-per-dollar** model
that clears the marker-reliability floor — an unreliable model is never
recommended, however cheap.

## Reliability floors / CI gate

`run_model_gate(candidate_row, incumbent_row, floors)` returns exit code `1`
(fail) when the candidate is below any floor, else `0`. Wire it into CI so a swap
that regresses markers/quality can't land silently. Suggested floor:
`{"marker_reliability": 0.9}`.

## Keep the price table current

`quality/model_prices.py` is the one file that decays — hand-maintained $/1M-token
numbers. **Update the numbers and the `updated` date on each edit** (prices move
monthly). `cost()` returns `None` for an unknown model so an unpriced candidate is
visible rather than silently free.

## Invariants

- **No auto-switch of the production model.** The report informs a human who sets
  `DOTHESIS_AGENT_MODEL`.
- **No live API in tests.** The single network chokepoint is `_complete`; every
  test stubs it. `langchain_openai` is imported lazily inside `_complete`, so the
  package imports and the tests run without the eval-only dep installed.

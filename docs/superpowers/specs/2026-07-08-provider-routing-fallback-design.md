# Provider Routing + OpenRouter Fallback Design (F10)

**Date:** 2026-07-08
**Status:** Design — approved, pending spec review
**Motivation:** Make the central brain switchable and resilient — one abstraction, OpenRouter as
the default+failover backend, native SDK as a pin-able primary when prompt-caching math favors
it. Pairs with F9 (which picks *which* model; F10 lets you *switch/fall back* safely).

## Problem

`agent/runtime.py:_default_model()` hard-branches `ChatAnthropic` vs `ChatGoogleGenerativeAI`.
Adding Qwen/GPT/DeepSeek/GLM means more branches, there's no automatic failover if a provider is
down/rate-limited (a single point of failure for a one-brain product), and switching models is a
code change. A unified gateway (OpenRouter) solves switching + failover, but naïvely adopting it
risks: losing prompt caching (DoThesis injects a large system prompt + skills EVERY turn),
inconsistent token accounting (the credit ledger debits per token), and routing student PII
through unwanted providers.

## Goals

- **A provider abstraction DoThesis owns:** `make_model(spec) -> BaseChatModel`, env-selected,
  supporting a **native route** (anthropic/google/…) and an **openrouter route** (OpenAI-compatible
  + fallback list). Replaces the `_default_model` branch.
- **Automatic failover** via OpenRouter's `models: [primary, …fallbacks]` — cascades on error,
  billed only for the successful run.
- **Preserve prompt caching** where it matters (native route, or verified OpenRouter cache
  routes) — never silently lose the big-system-prompt cache discount.
- **Consistent token accounting** across routes so the credit ledger stays correct, incl.
  streaming usage.
- **Data policy** enforced on the openrouter route (no-train/no-log provider filter) for a
  commercial VN product.

## Non-goals

- Not removing native SDKs — they stay as a pin-able primary (caching/latency escape hatch).
- Not building our own gateway — OpenRouter is the gateway.
- Not choosing the model — that's F9.

## Design

### Model factory

`agent/model_factory.py`:

```python
def make_model(spec: ModelSpec | None = None) -> BaseChatModel: ...
```

`ModelSpec` from env/settings: `route` (`native` | `openrouter`), `model`, `fallbacks: list[str]`,
`temperature`, `max_tokens`. Selection:
- **native:** anthropic → `ChatAnthropic`; google → `ChatGoogleGenerativeAI` (today's behavior,
  moved here). Enables provider-native prompt caching.
- **openrouter:** `ChatOpenAI(base_url="https://openrouter.ai/api/v1", model=<primary>)` with
  `extra_body={"models": [primary, *fallbacks], "provider": {"data_collection": "deny",
  "allow_fallbacks": True}}` and `stream_options={"include_usage": True}` so streamed usage is
  reported.

`agent/runtime.py:_default_model()` becomes a thin call to `make_model()`.

### Failover semantics

OpenRouter's `models` array cascades on provider error transparently; the response reports which
model actually served (`response.model`) — surfaced in usage/telemetry (F5) so a silent fallback
to a pricier model is visible.

### Prompt caching guardrail

- Native route: keep provider caching (Anthropic `cache_control` on the system/skill prefix;
  Gemini implicit/explicit caching) as today.
- OpenRouter route: only enable a model/route documented to preserve caching for our prefix; a
  config flag `cache_preserving: bool` marks whether the active route caches. F9's cost column
  measures *cached* cost per route so the choice is made on real numbers (F10 Task 4).

### Token accounting

A single `extract_usage(chunk_or_response) -> {in, out}` helper handles both native and
OpenAI-compatible shapes, used by `stream_turn`'s usage accumulation (`chat_v3` credit debit), so
the ledger is route-independent.

### Config

`settings.py` / env: `DOTHESIS_MODEL_ROUTE`, `DOTHESIS_AGENT_MODEL`, `DOTHESIS_MODEL_FALLBACKS`
(comma-sep), `OPENROUTER_API_KEY`, `DOTHESIS_OPENROUTER_DATA_POLICY`. Defaults keep today's
behavior (native google) until explicitly switched.

## Data flow

```
build_agent → make_model(spec from env)
   native: ChatAnthropic/ChatGoogleGenerativeAI (caching preserved)
   openrouter: ChatOpenAI→OpenRouter with [primary,…fallbacks] + data policy + usage
turn: stream → extract_usage (uniform) → credit debit (chat_v3) + emit served-model (F5)
```

## Error handling

- OpenRouter cascades on provider error; if ALL fallbacks fail, the turn surfaces the existing
  error event (no new failure mode).
- Missing `OPENROUTER_API_KEY` on the openrouter route ⇒ clear startup error (fail fast), not a
  mid-turn 401.
- `make_model` on an unknown route/model ⇒ raises at build time with a helpful message.

## Testing

- **Route selection:** env `native`+google ⇒ a Google chat model; `openrouter` ⇒ a ChatOpenAI
  with `base_url` = OpenRouter and `extra_body.models` = `[primary, *fallbacks]` (assert the
  constructed config; no network).
- **Data policy:** openrouter route sets `provider.data_collection = "deny"`.
- **Usage extraction:** `extract_usage` returns `{in,out}` for both an Anthropic-shaped and an
  OpenAI-shaped chunk.
- **Streaming usage flag:** openrouter route sets `stream_options.include_usage = True`.
- **Back-compat:** with no new env, `make_model()` returns the same model type as today.
- No network in tests; api tests via `./run.sh`.

## Migration / rollout

1. `agent/model_factory.py` (native route = current behavior) + point `_default_model` at it.
2. OpenRouter route + fallback list + data policy + streaming usage flag.
3. `extract_usage` unification wired into `stream_turn` / credit debit.
4. Extend F9 cost to record cached vs uncached cost per route; emit served-model to F5.
5. Settings/env + `docs/observability/model-eval.md` note on route selection.

## Dependencies

- **F9** — cost column gains cached-cost-per-route; F9's `_complete` can reuse the openrouter
  client config.
- **F5** — emit the actually-served model on fallback.
- Touch points: `agent/runtime.py` (`_default_model`, `stream_turn` usage), `chat_v3` credit debit,
  `settings.py`.

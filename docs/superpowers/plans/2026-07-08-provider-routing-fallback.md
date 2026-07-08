# Provider Routing + OpenRouter Fallback Implementation Plan (F10)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the central brain switchable + resilient — a `make_model()` factory with a native route (caching preserved) and an OpenRouter route (auto-fallback + data policy), consistent token accounting, and cached-cost measurement.

**Architecture:** A provider abstraction DoThesis owns; `_default_model()` becomes a thin call to it. OpenRouter route uses `ChatOpenAI` → OpenRouter with a `models` fallback array + `provider.data_collection=deny` + streaming usage. One `extract_usage` keeps the credit ledger route-independent.

**Tech Stack:** `langchain_openai` (OpenAI-compatible), `langchain_anthropic`, `langchain_google_genai`, pytest via `./run.sh` (no network in tests).

## Global Constraints

- **Back-compat default:** with no new env, `make_model()` returns today's model (native Google), unchanged.
- **No network in tests** — assert constructed client config, don't call providers.
- **Preserve prompt caching** on the native route; mark whether the OpenRouter route caches.
- **Credit ledger must stay correct** — usage extraction is route-independent.
- **Fail fast** on a misconfigured route (bad model / missing key) at build time, not mid-turn.
- **Comment the decision behind each change.**

---

### Task 1: `make_model` factory (native route) + refactor `_default_model`

**Files:**
- Create: `agent/model_factory.py`
- Modify: `agent/runtime.py` (`_default_model` → calls `make_model`)
- Test: `api/tests/test_model_factory.py`

**Interfaces:**
- Produces: `ModelSpec` (dataclass/dict: `route, model, fallbacks, temperature, max_tokens`), `spec_from_env() -> ModelSpec`, `make_model(spec: ModelSpec | None = None) -> BaseChatModel`.

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_model_factory.py
from agent.model_factory import make_model, spec_from_env


def test_native_google_by_default(monkeypatch):
    monkeypatch.delenv("DOTHESIS_MODEL_ROUTE", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    m = make_model(spec_from_env())
    assert m.__class__.__name__ == "ChatGoogleGenerativeAI"


def test_native_anthropic_when_key_present(monkeypatch):
    monkeypatch.setenv("DOTHESIS_MODEL_ROUTE", "native")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("DOTHESIS_AGENT_MODEL", "claude-haiku-4-5")
    m = make_model(spec_from_env())
    assert m.__class__.__name__ == "ChatAnthropic"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd api && ./run.sh pytest tests/test_model_factory.py -q` → FAIL (no module).

- [ ] **Step 3: Implement the factory (native route)**

```python
# agent/model_factory.py
"""Provider abstraction for the central brain. One factory, two routes: native (caching
preserved) and openrouter (auto-fallback + data policy). _default_model calls this so adding a
provider is config, not a code branch."""
from __future__ import annotations
import os
from dataclasses import dataclass, field


@dataclass
class ModelSpec:
    route: str = "native"          # "native" | "openrouter"
    model: str = "gemini-3.5-flash"
    fallbacks: list[str] = field(default_factory=list)
    temperature: float = 0.4
    max_tokens: int = 8000


def spec_from_env() -> ModelSpec:
    route = os.getenv("DOTHESIS_MODEL_ROUTE", "native")
    default_model = "gemini-3.5-flash"
    if route == "native" and os.getenv("ANTHROPIC_API_KEY"):
        default_model = "claude-sonnet-4-6"
    return ModelSpec(
        route=route,
        model=os.getenv("DOTHESIS_AGENT_MODEL", default_model),
        fallbacks=[m for m in os.getenv("DOTHESIS_MODEL_FALLBACKS", "").split(",") if m.strip()],
        temperature=float(os.getenv("DOTHESIS_MODEL_TEMPERATURE", "0.4")),
        max_tokens=int(os.getenv("DOTHESIS_MODEL_MAX_TOKENS", "8000")),
    )


def make_model(spec: ModelSpec | None = None):
    spec = spec or spec_from_env()
    if spec.route == "native":
        return _native(spec)
    if spec.route == "openrouter":
        return _openrouter(spec)   # Task 2
    raise ValueError(f"unknown model route: {spec.route!r}")


def _native(spec: ModelSpec):
    # Native SDKs keep provider prompt-caching for the big system prompt + skills.
    if os.getenv("ANTHROPIC_API_KEY") and "claude" in spec.model:
        from langchain_anthropic import ChatAnthropic  # noqa: PLC0415
        return ChatAnthropic(model=spec.model, max_tokens=spec.max_tokens, temperature=spec.temperature)
    from langchain_google_genai import ChatGoogleGenerativeAI  # noqa: PLC0415
    return ChatGoogleGenerativeAI(model=spec.model, temperature=spec.temperature)
```

Replace the body of `_default_model()` in `agent/runtime.py` with `return make_model()`.

> **Note for implementer:** keep the existing model-name defaults from `runtime.py:480-491` in
> `spec_from_env` so behavior is byte-for-byte today's when no new env is set.

- [ ] **Step 4: Run to verify it passes** → PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/model_factory.py agent/runtime.py api/tests/test_model_factory.py
git commit -m "feat(model): make_model factory (native route) replaces _default_model branch

One provider abstraction DoThesis owns; native route keeps provider prompt
caching. Behavior unchanged with no new env.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: OpenRouter route — fallback list + data policy + streaming usage

**Files:**
- Modify: `agent/model_factory.py` (`_openrouter`)
- Modify: `api/app/settings.py` (`openrouter_api_key`, `openrouter_data_policy`)
- Test: `api/tests/test_model_factory.py`

**Interfaces:**
- Produces: `_openrouter(spec) -> ChatOpenAI` configured with base_url, `models` fallback array, data policy, and streaming usage.

- [ ] **Step 1: Write the failing test**

```python
# add to api/tests/test_model_factory.py
from agent.model_factory import make_model, ModelSpec


def test_openrouter_route_config():
    spec = ModelSpec(route="openrouter", model="qwen3.6-plus",
                     fallbacks=["gpt-5.4-mini", "gemini-3.5-flash"])
    m = make_model(spec)
    assert m.__class__.__name__ == "ChatOpenAI"
    assert "openrouter.ai" in str(m.openai_api_base)
    body = (m.extra_body or {})
    assert body["models"] == ["qwen3.6-plus", "gpt-5.4-mini", "gemini-3.5-flash"]
    assert body["provider"]["data_collection"] == "deny"
    assert (m.model_kwargs.get("stream_options") or {}).get("include_usage") is True
```

> **Note for implementer:** the exact attribute names on `ChatOpenAI` (`openai_api_base`/`base_url`,
> `extra_body`, `model_kwargs`) depend on the installed `langchain_openai` version — adjust the
> asserts to what the constructor actually stores; the *config values* are the contract.

- [ ] **Step 2: Run to verify it fails** → FAIL.

- [ ] **Step 3: Implement `_openrouter` + settings**

Add to `settings.py`: `openrouter_api_key: str = ""`, `openrouter_data_policy: str = "deny"`.

```python
# add to agent/model_factory.py
def _openrouter(spec: ModelSpec):
    from langchain_openai import ChatOpenAI  # noqa: PLC0415
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        raise RuntimeError("openrouter route needs OPENROUTER_API_KEY (set it or use route=native)")
    models = [spec.model, *spec.fallbacks]
    return ChatOpenAI(
        model=spec.model,
        base_url="https://openrouter.ai/api/v1",
        api_key=key,
        temperature=spec.temperature,
        max_tokens=spec.max_tokens,
        # OpenRouter-specific: fallback cascade + no-train/no-log provider filter.
        extra_body={"models": models,
                    "provider": {"data_collection": os.getenv("DOTHESIS_OPENROUTER_DATA_POLICY", "deny"),
                                 "allow_fallbacks": True}},
        # OpenAI-compatible streaming reports usage only when asked.
        model_kwargs={"stream_options": {"include_usage": True}},
    )
```

- [ ] **Step 4: Run to verify it passes** → PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/model_factory.py api/app/settings.py api/tests/test_model_factory.py
git commit -m "feat(model): OpenRouter route with fallback cascade + data policy

models:[primary,...fallbacks] auto-failover, provider.data_collection=deny for
student PII, stream_options.include_usage so the credit ledger sees usage.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Route-independent token accounting

**Files:**
- Create: `agent/usage.py` (`extract_usage`)
- Modify: `agent/runtime.py` (`stream_turn` usage accumulation)
- Test: `api/tests/test_usage.py`

**Interfaces:**
- Produces: `extract_usage(obj) -> dict` — `{"in": int, "out": int}` from either an Anthropic-shaped or OpenAI-compatible usage payload/chunk.

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_usage.py
from agent.usage import extract_usage


def test_openai_shaped_usage():
    assert extract_usage({"usage": {"prompt_tokens": 100, "completion_tokens": 40}}) == {"in": 100, "out": 40}


def test_anthropic_langchain_usage_metadata():
    class Msg:
        usage_metadata = {"input_tokens": 12, "output_tokens": 7}
    assert extract_usage(Msg()) == {"in": 12, "out": 7}


def test_missing_usage_is_zero():
    assert extract_usage({}) == {"in": 0, "out": 0}
```

- [ ] **Step 2: Run to verify it fails** → FAIL.

- [ ] **Step 3: Implement `extract_usage` + wire it**

```python
# agent/usage.py
"""Route-independent token accounting. The credit ledger (chat_v3) debits per token, so usage
must be read the same way whether the model is native (usage_metadata) or OpenAI-compatible
(usage.prompt_tokens/completion_tokens)."""
from __future__ import annotations


def extract_usage(obj) -> dict:
    um = getattr(obj, "usage_metadata", None)
    if isinstance(um, dict) and um:
        return {"in": int(um.get("input_tokens", 0)), "out": int(um.get("output_tokens", 0))}
    usage = obj.get("usage") if isinstance(obj, dict) else getattr(obj, "usage", None)
    if isinstance(usage, dict):
        return {"in": int(usage.get("prompt_tokens", usage.get("input_tokens", 0))),
                "out": int(usage.get("completion_tokens", usage.get("output_tokens", 0)))}
    return {"in": 0, "out": 0}
```

In `agent/runtime.py` `stream_turn`, replace the ad-hoc usage read that builds the `usage` SSE
event with `extract_usage(...)` so native + openrouter both feed the same accumulation that
`chat_v3` debits.

> **Note for implementer:** read `stream_turn`'s current `usage` handling (search `"usage"` in
> `runtime.py`) and route it through `extract_usage`; keep the emitted event shape identical so
> `chat_v3`'s credit debit is unchanged.

- [ ] **Step 4: Run to verify it passes** → PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/usage.py agent/runtime.py api/tests/test_usage.py
git commit -m "feat(model): route-independent token accounting

extract_usage reads native (usage_metadata) and OpenAI-compatible (usage.*)
shapes identically so the credit ledger stays correct across routes.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Cached-cost in F9 + served-model telemetry + docs

**Files:**
- Modify: `quality/model_eval.py` (record cached vs uncached cost per route)
- Modify: `agent/runtime.py` or `chat_v3` (emit the actually-served model — F5 `quality_reviewed`/a `model_served` event)
- Modify: `docs/observability/model-eval.md` (route selection + caching note)
- Test: `api/tests/test_model_eval.py`

**Interfaces:**
- Produces: `model_eval` rows gain `cached_cost_per_task` (from a second run with the caching-preserving route, when applicable); a `model_served` signal on fallback.

- [ ] **Step 1: Write the failing test**

```python
# add to api/tests/test_model_eval.py
import quality.model_eval as me


def test_row_reports_cached_cost_when_available(monkeypatch):
    monkeypatch.setattr(me, "_complete", lambda m, p, system=None: ("[OPTIONS] a | b", {"in": 1000, "out": 100}))
    monkeypatch.setattr(me, "cost", lambda m, i, o: 0.01)
    # cached run reports fewer effective input tokens (prefix cached)
    rows = me.evaluate_models(["m"], [{"id": "o", "prompt": "p", "expect": {"kind": "marker", "value": "OPTIONS"}}],
                              cached_input_ratio=0.2)
    assert rows[0]["cached_cost_per_task"] is not None
    assert rows[0]["cached_cost_per_task"] <= rows[0]["cost_per_task"]
```

- [ ] **Step 2: Run to verify it fails** → FAIL.

- [ ] **Step 3: Implement cached-cost + served-model emit**

In `evaluate_models`, add an optional `cached_input_ratio: float | None = None`; when set, compute
`cached_cost_per_task = cost(model, int(tin * cached_input_ratio), tout)` alongside the full
`cost_per_task`, so the report shows both (the big-system-prompt prefix is the cacheable part).
Document that native/caching routes realize the cached number; non-caching OpenRouter routes do
not.

Emit the served model: in the turn path, when usage/response reports a `model` different from the
requested primary (a fallback fired), emit `analytics.emit("model_served", uid, {"requested":
primary, "served": served})` (F5) so silent fallbacks to a pricier model are visible.

Update `docs/observability/model-eval.md`: how to set `DOTHESIS_MODEL_ROUTE` /
`DOTHESIS_MODEL_FALLBACKS`, that native route preserves caching (use the `cached_cost_per_task`
column to compare true cost), and the data-policy default.

- [ ] **Step 4: Run to verify it passes** → PASS.

- [ ] **Step 5: Commit**

```bash
git add quality/model_eval.py agent/runtime.py docs/observability/model-eval.md api/tests/test_model_eval.py
git commit -m "feat(model): cached-cost column + served-model telemetry

F9 reports cached vs uncached cost per route (the big system-prompt prefix is
the cacheable part), and fallbacks emit model_served so a silent switch to a
pricier model is visible.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] `cd api && ./run.sh pytest tests/test_model_factory.py tests/test_usage.py tests/test_model_eval.py -q` → all PASS.
- [ ] Back-compat: with no new env, `make_model()` returns the same class as before (Task 1 test proves it).
- [ ] No network in tests (config-only assertions).
- [ ] Manual: `DOTHESIS_MODEL_ROUTE=openrouter DOTHESIS_AGENT_MODEL=qwen3.6-plus DOTHESIS_MODEL_FALLBACKS=gpt-5.4-mini,gemini-3.5-flash OPENROUTER_API_KEY=… ./run.sh python -c "from agent.model_factory import make_model; print(make_model())"` builds a ChatOpenAI with the fallback array.

## Notes

- **Caching is the reason native stays** — the OpenRouter route is default+failover, but keep the
  ability to pin the winner to its native SDK if `cached_cost_per_task` says caching wins.
- **Verify `ChatOpenAI` param names** for the installed `langchain_openai` (`extra_body` /
  `model_kwargs`) — the config values are the contract, not the attribute spelling.
- **F9 dependency:** Task 4 edits `quality/model_eval.py` (F9) — land F9 first, or do Task 4 when F9 lands.

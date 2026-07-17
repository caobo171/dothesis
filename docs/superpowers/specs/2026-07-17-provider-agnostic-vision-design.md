# Provider-Agnostic Vision — Design Spec

**Date:** 2026-07-17
**Roadmap initiative:** #4 (`docs/superpowers/specs/2026-07-17-dothesis-vertical-agent-roadmap.md:141-164`)
**Status:** Approved for implementation (implementation plan: `2026-07-17-provider-agnostic-vision-plan.md`)

## 1. Problem

The chat agent ingests SPSS/SmartPLS **result screenshots** through a vision
model (`parse_output_table` in `agent/tools/output_parse.py`). That path is
hardwired to Gemini regardless of which brain the deployment is configured to
run (`DOTHESIS_MODEL_ROUTE` / `DOTHESIS_AGENT_MODEL`, resolved by
`agent/model_factory.py:spec_from_env`, lines 51–99).

Concretely, `_vision_read` (`agent/tools/output_parse.py:116-129`):

- builds the message with a **hardcoded** `provider="gemini"`
  (`agent/tools/output_parse.py:128`), and
- routes it through `orchestrator.llm.get_vision_llm`
  (`agent/tools/output_parse.py:126,129`), which delegates to
  `make_vision_model` (`orchestrator/llm.py:126-143`) — **always** a
  `ChatGoogleGenerativeAI` client (`agent/model_factory.py:210-241`).

The consequence, per configuration:

| Configuration | What happens today |
| --- | --- |
| `route=native`, Gemini brain (default) | Works — sidecar `gemini-2.5-flash` via native Google (`model_factory.py:232,241`). |
| `route=native`, Claude brain (`ANTHROPIC_API_KEY` set) | Screenshot parse **silently depends on a second provider's key**: `make_vision_model` still builds a Gemini client (`model_factory.py:241`), which fails without `GOOGLE_API_KEY`/`GEMINI_API_KEY` — even though the Claude brain can see images natively. The exception escapes `parse_output_table` uncaught (`output_parse.py:137` has no try/except) and kills the turn. |
| `route=ofox`, vision-capable model (e.g. `google/gemini-2.5-flash`) | The brain can see, but the parse tool ignores it and detours through the Gemini-native sidecar endpoint (`model_factory.py:235-240`). Inconsistent with the chat-attachment path, which already sends `image_url` blocks to the brain (`agent/runtime.py:646-654`). |
| `route=openrouter` | Sidecar falls through to native Google (`model_factory.py:241`) → again requires a Google key that the deployment may not have. |

Note on history: the original "defect 1" (env-sniffing `detect_provider`
emitting Gemini `{"type":"media"}` blocks into ChatOpenAI) has **already been
fixed for the chat-attachment path**. `detect_provider` is now spec-derived
and route-aware (`agent/multimodal.py:312-330`), `build_user_message` has
per-provider builders for gemini/openai/anthropic
(`agent/multimodal.py:125-131`), and `agent/runtime.py:646-654` wires them
together capability-first. **What remains — and what this spec covers — is
the screenshot-parse path (`output_parse.py`) and its Gemini-only sidecar
dependency.** This is exactly the residue roadmap initiative #4 names.

## 2. Current state (grounded)

### 2.1 Already in place (reuse, do not duplicate)

| Capability | Where | Notes |
| --- | --- | --- |
| Route/model config (single source of truth) | `agent/model_factory.py:51-99` (`spec_from_env`) | Reads `DOTHESIS_MODEL_ROUTE` (line 70), `DOTHESIS_AGENT_MODEL` (line 90), `DOTHESIS_VISION_MODEL` (line 97), `ANTHROPIC_API_KEY` default flip (lines 74-75). |
| Vision capability flag | `agent/model_factory.py:46-48` (`model_supports_vision`), hints at line 43 (`"gemini"`, `"claude"`), derived into `ModelSpec.supports_vision` at line 98. Fail-closed. |
| Route → wire-format provider | `agent/multimodal.py:312-330` (`detect_provider(spec)`) | `ofox`/`openrouter` → `"openai"` (325-326); native + `ANTHROPIC_API_KEY` + `"claude" in model` → `"anthropic"` (328-329, mirroring `model_factory.py:122`); else `"gemini"`. |
| Per-provider image/content blocks | `agent/multimodal.py`: gemini `{"type":"media",...}` (146-150), openai `{"type":"image_url","image_url":{"url":"data:...;base64,..."}}` (279-281), anthropic `{"type":"image","source":{"type":"base64",...}}` (299-301) + `document` (302-304). Dispatch: `build_user_message` (94-131). |
| Attachment abstraction + mime guess | `agent/multimodal.py:65-91` (`Attachment`, `from_path` guesses mime from suffix at 88-90). |
| Gemini vision sidecar factory | `agent/model_factory.py:210-241` (`make_vision_model`) — sidecar model default `gemini-2.5-flash` (232), temp 0.2 (233), Ofox Gemini-native endpoint on `route=ofox` (235-240). |
| Configurable sidecar model | `DOTHESIS_VISION_MODEL` already exists (`model_factory.py:97`, `ModelSpec.vision_model` line 36). The roadmap's "explicit, configurable vision-model spec for the sidecar case" is **already shipped**. |
| Capability-first chat integration (the pattern to copy) | `agent/runtime.py:646-654` — `spec_from_env()` → `detect_provider(spec)` → `build_user_message(..., supports_vision=spec.supports_vision)`. |
| needs_confirmation / error contract | `agent/tools/output_parse.py:141-151` — no-JSON → `{"error", "hint"}` (141-143); malformed JSON → `{"needs_confirmation", "raw"}` (146-148); empty rows → `{"needs_confirmation", "parsed"}` (149-150). |

### 2.2 The three hardwired sites this design replaces/touches

1. **`agent/tools/output_parse.py:116-129` (`_vision_read`)** — hardcoded
   `provider="gemini"` (128) + `get_vision_llm` (126,129). This is the main
   surgery site.
2. **`agent/tools/output_parse.py:137`** — `_vision_read` is called with no
   try/except; any factory/invoke exception (missing key, network) crashes
   the tool instead of the fail-soft JSON that `parse_smartpls_export`
   already returns (`output_parse.py:99-103`).
3. **`agent/multimodal.py:217-240` (`_transcribe_via_vision`)** — hardcodes
   `_build_gemini_message` + `make_vision_model`. This one is **correct by
   design** (it exists only for brains that *cannot* see, and the sidecar is
   deliberately always Gemini — see the rationale at `model_factory.py:226-231`)
   and stays as-is, except that its list-content flattening (236-239) is
   extracted into a shared helper so `_vision_read` can reuse it.

## 3. Design

### 3.1 Overview

One new **pure resolver** decides, from the `ModelSpec`, (a) the wire-format
provider for the image block and (b) whether to use the brain or the Gemini
sidecar. One new **thin factory** turns that decision into a client.
`_vision_read` is rewired to use both. No behavior change on native Gemini
or on the default Ofox config — guaranteed by construction (see matrix).

```
parse_output_table(file)
  └─ _vision_read(file)                                # stays the single network boundary
       ├─ spec = spec_from_env()                       # model_factory (existing)
       ├─ res  = resolve_vision(spec)                  # NEW, pure — multimodal.py
       ├─ att  = Attachment.from_path(file)            # existing (+ mime sniff fallback)
       ├─ msg  = build_user_message(_VISION_PROMPT,
       │            [att], res.provider,
       │            supports_vision=True)              # existing dispatch, correct block per provider
       ├─ model = make_vision_capable_model(spec,
       │            use_sidecar=res.use_sidecar)       # NEW, thin — model_factory.py
       └─ return _flatten_content(model.invoke([msg]).content)
```

### 3.2 The resolver — `resolve_vision(spec) -> VisionResolution`

**Lives in `agent/multimodal.py`**, next to `detect_provider`.

Rationale for location: `multimodal.py` already owns the `Provider` literal
(line 55), `detect_provider` (312-330), and the block builders it must agree
with. `model_factory.py` owns route logic and client construction but not
wire formats; putting the provider decision there would either duplicate
`detect_provider` or create a module-load import cycle
(`model_factory → multimodal → model_factory`). `multimodal.py` already
lazily imports `model_factory` inside functions (line 322 precedent), so the
resolver reuses `spec_from_env`/`detect_provider` with zero duplication and
zero new cycle.

```python
@dataclass(frozen=True, slots=True)
class VisionResolution:
    provider: Provider    # which image-block wire format build_user_message emits
    use_sidecar: bool     # True → make_vision_model(spec); False → make_model(spec)

def resolve_vision(spec: ModelSpec | None = None) -> VisionResolution:
    spec = spec or spec_from_env()          # lazy import, same as detect_provider
    provider = detect_provider(spec)        # REUSE — never re-derive route→provider
    if provider == "gemini":
        # Native-Gemini brain: keep today's exact path (deterministic t=0.2
        # sidecar, gemini media blocks). No regression by construction.
        return VisionResolution("gemini", use_sidecar=True)
    if provider == "anthropic":
        # Claude sees natively — kills the hidden GOOGLE_API_KEY dependency.
        return VisionResolution("anthropic", use_sidecar=False)
    # provider == "openai" (ofox / openrouter, OpenAI-compat wire):
    if spec.supports_vision and os.getenv("DOTHESIS_VISION_FORCE_SIDECAR", "") != "1":
        # Vision-capable model behind the gateway: image_url data-URI blocks,
        # same as the chat-attachment path already does (runtime.py:646-654).
        return VisionResolution("openai", use_sidecar=False)
    # Text-only gateway model (e.g. bailian/qwen-plus): Gemini sidecar,
    # routed through Ofox's Gemini-native endpoint on route=ofox
    # (model_factory.py:235-240) — today's behavior, unchanged.
    return VisionResolution("gemini", use_sidecar=True)
```

Design decisions:

- **Reuses `detect_provider` and `spec.supports_vision`** — the route→provider
  mapping and the vision-capability heuristic each keep one source of truth
  (`multimodal.py:312-330`, `model_factory.py:43-48`). The resolver adds only
  the brain-vs-sidecar policy, which exists nowhere today.
- **Pure and env-free given a spec** — takes a `ModelSpec`, returns a frozen
  dataclass. Fully unit-testable with constructed specs; the env-derived
  variant is testable with monkeypatched env via `spec_from_env`, exactly like
  `agent/tests/test_multimodal_routing.py:12-24`.
- **`DOTHESIS_VISION_FORCE_SIDECAR=1` escape hatch** — the one genuinely
  unverified cell in the matrix is Ofox's OpenAI-compat endpoint accepting
  `image_url` blocks for `google/*` models (only the Gemini-*native* Ofox
  endpoint is marked "verified working", `model_factory.py:218-221`). If it
  misbehaves in production, ops flips one env var to restore today's sidecar
  detour without a deploy. Read inside the resolver so it is unit-testable.

### 3.3 Route → provider → block-format matrix (normative)

| `DOTHESIS_MODEL_ROUTE` | `DOTHESIS_AGENT_MODEL` (or default) | `supports_vision` (`model_factory.py:46-48`) | Resolved provider | Vision client (`use_sidecar`) | Image block emitted by `build_user_message` |
| --- | --- | --- | --- | --- | --- |
| `native` (default) | `gemini-3.5-flash` (default, `model_factory.py:73`) | yes | `gemini` | sidecar: `ChatGoogleGenerativeAI(gemini-2.5-flash, t=0.2)` (`model_factory.py:232-233,241`) | `{"type":"media","mime_type":m,"data":b64}` (`multimodal.py:146-150`) — **unchanged from today** |
| `native` + `ANTHROPIC_API_KEY` | `claude-sonnet-4-6` (default flip, `model_factory.py:74-75`) | yes | `anthropic` | brain: `ChatAnthropic` via `make_model` (`model_factory.py:122-125`) | `{"type":"image","source":{"type":"base64","media_type":m,"data":b64}}` (`multimodal.py:299-301`) — **new; fixes the dead path** |
| `ofox` | `bailian/qwen-plus` (default, `model_factory.py:89`) | no | `gemini` | sidecar via Ofox Gemini-native endpoint (`model_factory.py:235-240`) | `{"type":"media",...}` — **unchanged from today** |
| `ofox` | `google/gemini-2.5-flash` (or any id containing `gemini`/`claude`) | yes | `openai` | brain: `ChatOpenAI @ https://api.ofox.ai/v1` (`model_factory.py:198-207`) | `{"type":"image_url","image_url":{"url":"data:m;base64,..."}}` (`multimodal.py:279-281`) — **new; aligns with chat path** |
| `openrouter` | vision-capable id | yes | `openai` | brain: `ChatOpenAI @ openrouter.ai` (`model_factory.py:145-164`) | `image_url` data-URI — **new** |
| `openrouter` | text-only id | no | `gemini` | sidecar → native Google (`model_factory.py:241`; requires `GOOGLE_API_KEY`/`GEMINI_API_KEY`) | `{"type":"media",...}` — same as today, but now fails **soft** (§3.6) |

`ANTHROPIC_API_KEY` participates exactly as it does in `detect_provider`
(`multimodal.py:328-329`): it only produces `anthropic` on `route=native`
with a `claude` model id — never on gateway routes, where Claude models ride
the OpenAI-compat wire.

### 3.4 The client chooser — `make_vision_capable_model(spec, *, use_sidecar)`

**Lives in `agent/model_factory.py`** (all client construction stays in the
factory; `output_parse.py` never constructs clients).

```python
def make_vision_capable_model(spec: ModelSpec | None = None, *, use_sidecar: bool):
    spec = spec or spec_from_env()
    if use_sidecar:
        return make_vision_model(spec)   # deterministic t=0.2 transcription sidecar
    return make_model(spec)              # the configured brain itself
```

Deliberately trivial: it exists to (a) keep construction knowledge out of the
tool layer, and (b) give tests a single monkeypatch seam. It takes
`use_sidecar` as a plain bool rather than importing `VisionResolution`, so
`model_factory` gains **no** import on `multimodal` (no cycle, not even a
lazy one).

### 3.5 MIME detection

`Attachment.from_path` guesses from the filename suffix
(`multimodal.py:88-90`) and falls back to `application/octet-stream`. On the
`openai` and `anthropic` paths, a screenshot with a missing/wrong extension
(clipboard pastes are commonly named `image` or `paste.bin`) would then be
routed to `_textualize` → lossy binary decode (`multimodal.py:279,299`)
instead of an image block.

Decision: add a pure `_sniff_image_mime(data: bytes) -> str | None` helper in
`agent/multimodal.py` checking magic bytes for the formats screenshots
actually come in — PNG (`\x89PNG`), JPEG (`\xff\xd8\xff`), GIF
(`GIF87a`/`GIF89a`), WebP (`RIFF....WEBP`), BMP (`BM`) — and use it in
`from_path` **only when** the suffix guess fails (returns `None`) or yields
`application/octet-stream`. Suffix guess stays primary so no existing
behavior changes for well-named files. No new dependency (`python-magic`
rejected: heavyweight, libmagic system dep, for five constant prefixes).

### 3.6 Error handling

- **Fail-soft at the tool boundary.** Wrap the `_vision_read` call in
  `parse_output_table` (`output_parse.py:137`) in try/except and return
  `{"error": "vision parse failed: <e>", "hint": "paste the values or upload
  the SmartPLS HTML export"}` — the same contract `parse_smartpls_export`
  already honors (`output_parse.py:99-103`). This converts today's
  turn-killing crash (missing Google key on a Claude deployment) into the
  agent asking the student for values.
- **Contract preserved bit-for-bit.** The three existing returns —
  `error`/`hint` on no-JSON (`output_parse.py:141-143`),
  `needs_confirmation`/`raw` on malformed JSON (146-148),
  `needs_confirmation`/`parsed` on empty rows (149-150) — are untouched. The
  existing tests (`api/tests/test_output_parse.py:32-46`) must pass without
  modification.
- **Fail-fast at construction stays.** `make_model` route errors
  (`model_factory.py:114,141,195`) still raise inside `_vision_read`; the new
  try/except converts them to the fail-soft JSON at the tool boundary.
- **Content flattening.** Gemini 3.x can return list-of-parts content;
  `_transcribe_via_vision` already flattens it (`multimodal.py:236-239`) but
  `_vision_read` does `str(content)` (`output_parse.py:129`), which happens
  to survive `find("{")`/`rfind("}")` but embeds Python-repr noise. Extract
  the flatten loop into `_flatten_content(content) -> str` in
  `agent/multimodal.py`, used by both call sites.

### 3.7 Integration points

| Site | Change |
| --- | --- |
| `agent/tools/output_parse.py:116-129` (`_vision_read`) | Rewire per §3.1. Drops the `from orchestrator.llm import get_vision_llm` import (line 126) — removes the only `agent → orchestrator` dependency in the tools layer. `_vision_read` remains the single stubbed boundary for existing tests. |
| `agent/tools/output_parse.py:132-151` (`parse_output_table`) | Add fail-soft try/except around the `_vision_read` call (§3.6). Nothing else. |
| `agent/multimodal.py` | Add `VisionResolution`, `resolve_vision`, `_sniff_image_mime`, `_flatten_content`; `_transcribe_via_vision` switches to `_flatten_content` (pure extraction, no behavior change); `Attachment.from_path` gains the sniff fallback. |
| `agent/model_factory.py` | Add `make_vision_capable_model` (§3.4). No changes to `make_model` / `make_vision_model` / `spec_from_env`. |
| `orchestrator/llm.py:126-143` (`get_vision_llm`) | **Unchanged.** It keeps serving auto-mode/orchestrator callers with its dual-env route resolution (line 141). It simply loses its `output_parse` caller. |
| `agent/runtime.py:646-654` (chat attachments) | **Unchanged.** Already capability-first; the resolver intentionally converges the parse tool onto the same decisions. |

### 3.8 Testing strategy — zero network

Repo conventions to follow: no test may hit a model, the network, or disk
(`api/tests/test_output_parse.py:5-10`); construction-only assertions with
faked env keys (`api/tests/test_model_factory.py:1,9-24`); fake
`langchain_openai` module injection for the lazy import
(`api/tests/test_model_factory.py:69-87`); parametrized route matrices with
monkeypatched env (`agent/tests/test_multimodal_routing.py:12-24`).

1. **Resolver unit tests (pure, the bulk of coverage).** Parametrize the full
   §3.3 matrix: `ModelSpec(route, model, supports_vision)` in →
   `(provider, use_sidecar)` out. Plus: `DOTHESIS_VISION_FORCE_SIDECAR=1`
   forces the sidecar on a vision-capable ofox model; env-derived variant via
   monkeypatched `DOTHESIS_MODEL_ROUTE`/`DOTHESIS_AGENT_MODEL`/`ANTHROPIC_API_KEY`
   + `resolve_vision()` with no arg.
2. **Factory tests (construction-only).** `use_sidecar=True` →
   `ChatGoogleGenerativeAI` class-name assert (faked `GOOGLE_API_KEY`);
   `use_sidecar=False` on native-Claude → `ChatAnthropic`; `use_sidecar=False`
   on ofox → fake-`ChatOpenAI` capture of `base_url="https://api.ofox.ai/v1"`.
3. **Block-shape-through-the-tool tests.** Monkeypatch
   `agent.model_factory.make_vision_capable_model` (patched at source; the
   import inside `_vision_read` is lazy, so source-module patching works) to
   return a `FakeModel` whose `invoke` records the `HumanMessage` and returns
   canned JSON. Per monkeypatched route env, assert the recorded message's
   image block `type` is `media` / `image` / `image_url` respectively, and
   that the tool's output JSON is the canned parse. This tests the exact
   route→block wiring the initiative is about, with zero network.
4. **Regression tests.** Existing `api/tests/test_output_parse.py` and
   `agent/tests/test_multimodal_routing.py` pass **unmodified** (17 tests,
   verified green at spec time). `_vision_read` stays stubbable exactly as
   before.
5. **Fail-soft test.** Factory raises `RuntimeError` → `parse_output_table`
   returns JSON with `error` + `hint`, never an exception.
6. **MIME sniff tests.** Pure byte-prefix table tests; `from_path` fallback
   test with an extension-less filename (write via `tmp_path`).

No recorded fixtures needed: the roadmap's "provider-matrix tests with
recorded fixtures" is satisfied more cheaply by asserting the outgoing block
shapes (which we control) rather than replaying provider responses (which
`_vision_read` stubbing already covers).

### 3.9 Risks

1. **Ofox OpenAI-compat vision unverified (top risk).** Only Ofox's
   Gemini-*native* endpoint is verified for vision
   (`model_factory.py:218-221`). If `image_url` blocks fail on
   `https://api.ofox.ai/v1` for `google/*` ids, the new brain path on
   `ofox + vision-model` regresses vs. today's sidecar detour. Mitigations:
   (a) `DOTHESIS_VISION_FORCE_SIDECAR=1` env rollback, no deploy needed;
   (b) the *default* ofox config (`bailian/qwen-plus`) never enters this cell
   — it resolves to the sidecar, unchanged; (c) an integration-marked manual
   probe (plan Phase 6) verifies before anyone flips a production model to a
   vision-capable ofox id.
2. **`model_supports_vision` false positives/negatives** (substring hints,
   `model_factory.py:43`) mis-resolve brain-vs-sidecar on gateway routes.
   Fail-closed default (unknown → sidecar) makes the failure mode "needless
   sidecar hop", not a broken request. Known maintenance point, already
   documented at `model_factory.py:40-43`.
3. **Anthropic transcription quality/params differ from the t=0.2 Gemini
   sidecar** (ChatAnthropic is built without a temperature kwarg,
   `model_factory.py:122-125`). Accepted: the prompt (`output_parse.py:111-113`)
   is the anti-fabrication control, and the low-confidence contract catches
   weak parses. Not a correctness risk.

### 3.10 Out of scope

- The chat-attachment path (`agent/runtime.py:646-654`) — already
  provider-agnostic; untouched.
- Making the **sidecar itself** non-Gemini (e.g. an OpenRouter-hosted vision
  sidecar for `openrouter` + text-only brains without a Google key). The
  sidecar stays Gemini by design (`model_factory.py:226-231`); that
  configuration now fails soft with a clear hint instead of crashing.
- `_transcribe_via_vision` policy (`multimodal.py:217-240`) — correct as-is;
  only the flatten helper is extracted from it.
- Gemini File API / >20MB attachments (`multimodal.py:169-206`) — screenshots
  are orders of magnitude below the 20MB inline cap.
- `orchestrator/llm.get_vision_llm` and its auto-mode callers.
- Billing/credit accounting for vision calls; OCR; PDF ingestion paths.
- The provider-routing fallback cascade design
  (`2026-07-08-provider-routing-fallback-design.md`) — this initiative
  unblocks it but does not implement it.

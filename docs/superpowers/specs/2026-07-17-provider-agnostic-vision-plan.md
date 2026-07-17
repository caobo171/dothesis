# Provider-Agnostic Vision — Implementation Plan

**Design spec:** `docs/superpowers/specs/2026-07-17-provider-agnostic-vision-design.md` (read it first — the route→provider→block matrix in §3.3 is normative)
**Approach:** strict TDD. Every phase: write the failing test, watch it fail, implement, watch it pass. The pure resolver and block wiring land fully tested **before** the parse tool is touched.

## Ground rules

- **No test may hit the network, a real model, or (except `tmp_path`) the
  filesystem.** This is the existing suite's contract
  (`api/tests/test_output_parse.py:5-10`).
- **Do not modify** any existing test in `api/tests/test_output_parse.py`,
  `agent/tests/test_multimodal_routing.py`, or `api/tests/test_model_factory.py`.
  They are the regression net; all 17 relevant tests were verified green at
  planning time.
- **Test runner quirk:** the repo venv is `api/.venv` and on this machine the
  universal python binary launches x86_64 while the wheels are arm64. The
  working invocation is:
  `arch -arm64 api/.venv/bin/python -m pytest <paths> -q`
  Every "Verify" below writes `python -m pytest ...` — substitute the working
  interpreter. If plain `python -m pytest` works in your session, use that.
- All paths are repo-relative to the dothesis root.
- Follow existing conventions: class-name asserts + faked env keys for client
  construction (`api/tests/test_model_factory.py:9-24`), fake-module injection
  for lazy `langchain_openai` imports (`api/tests/test_model_factory.py:69-87`),
  parametrized route matrices (`agent/tests/test_multimodal_routing.py:12-24`).

---

## Phase 0 — Baseline

**Task 0.1 — Confirm the regression net is green before touching anything.**
- Files: none.
- Verify: `python -m pytest api/tests/test_output_parse.py agent/tests/test_multimodal_routing.py api/tests/test_model_factory.py -q`
- Done when: all pass (expect ≥17 from the first two files). If anything is
  red here, STOP and report — do not build on a broken baseline.

---

## Phase 1 — Pure resolver (`resolve_vision`) with the full route matrix

**Task 1.1 — Write the resolver tests (failing).**
- Files: create `agent/tests/test_vision_resolver.py`.
- Content: import `ModelSpec` from `agent.model_factory` and (not yet
  existing) `VisionResolution`, `resolve_vision` from `agent.multimodal`.
  Parametrized matrix straight from design §3.3:

  | route | model | supports_vision | ANTHROPIC_API_KEY | expected (provider, use_sidecar) |
  | --- | --- | --- | --- | --- |
  | native | gemini-3.5-flash | True | unset | ("gemini", True) |
  | native | claude-sonnet-4-6 | True | set | ("anthropic", False) |
  | ofox | bailian/qwen-plus | False | unset | ("gemini", True) |
  | ofox | google/gemini-2.5-flash | True | unset | ("openai", False) |
  | openrouter | anthropic/claude-sonnet-4-6 | True | unset | ("openai", False) |
  | openrouter | meta-llama/llama-3 | False | unset | ("gemini", True) |

  Build specs directly (`ModelSpec(route=..., model=..., supports_vision=...)`);
  monkeypatch `ANTHROPIC_API_KEY` per row (delenv when unset — `detect_provider`
  reads it, `agent/multimodal.py:328`). Plus three non-matrix tests:
  1. `DOTHESIS_VISION_FORCE_SIDECAR=1` (monkeypatched) flips the
     ofox+vision-capable row to `("gemini", True)`.
  2. Env-derived: monkeypatch `DOTHESIS_MODEL_ROUTE=ofox`,
     `DOTHESIS_AGENT_MODEL=bailian/qwen-plus`, delenv `ANTHROPIC_API_KEY`;
     `resolve_vision()` with no arg → `("gemini", True)`.
  3. `VisionResolution` is frozen (assigning to a field raises).
- Verify: `python -m pytest agent/tests/test_vision_resolver.py -q` → **fails
  with ImportError** (symbols don't exist yet).
- Done when: the failure is the expected ImportError, not a collection error.

**Task 1.2 — Implement `VisionResolution` + `resolve_vision`.**
- Files: `agent/multimodal.py`. Add a frozen slotted dataclass
  `VisionResolution(provider: Provider, use_sidecar: bool)` and
  `resolve_vision(spec: ModelSpec | None = None) -> VisionResolution` exactly
  per design §3.2 — it MUST call the existing `detect_provider(spec)`
  (`agent/multimodal.py:312-330`) rather than re-deriving route→provider, and
  MUST read `spec.supports_vision` rather than re-matching model ids. Lazy
  `spec_from_env` import inside the function (precedent: line 322). Place it
  directly below `detect_provider`.
- Verify: `python -m pytest agent/tests/test_vision_resolver.py agent/tests/test_multimodal_routing.py -q`
- Done when: all resolver tests pass AND the pre-existing routing tests still
  pass unmodified.

---

## Phase 2 — Client chooser (`make_vision_capable_model`)

**Task 2.1 — Write the factory tests (failing).**
- Files: append to `api/tests/test_model_factory.py` (new tests only; do not
  touch existing ones).
- Tests:
  1. `use_sidecar=True`, spec `ModelSpec(route="native")`, monkeypatch
     `GOOGLE_API_KEY=test` → returned object class name is
     `ChatGoogleGenerativeAI` and its model is the sidecar default
     `gemini-2.5-flash` — i.e. it delegated to `make_vision_model`
     (`agent/model_factory.py:232`), NOT the brain model.
  2. `use_sidecar=False`, spec `ModelSpec(route="native", model="claude-sonnet-4-6")`,
     monkeypatch `ANTHROPIC_API_KEY=sk-test` → class name `ChatAnthropic`
     (delegates to `make_model` → `_native`, `agent/model_factory.py:122-125`).
  3. `use_sidecar=False`, spec `ModelSpec(route="ofox", model="google/gemini-2.5-flash")`,
     monkeypatch `OFOX_API_KEY=test`, install the fake `langchain_openai`
     module (reuse/extract the `_install_fake_chatopenai` helper already in
     this file, lines 69-87) → captured `base_url == "https://api.ofox.ai/v1"`
     and `model == "google/gemini-2.5-flash"`.
- Verify: `python -m pytest api/tests/test_model_factory.py -q` → new tests
  fail with AttributeError/ImportError.
- Done when: expected failures only.

**Task 2.2 — Implement `make_vision_capable_model`.**
- Files: `agent/model_factory.py`. Per design §3.4: two-branch function,
  keyword-only `use_sidecar: bool`, `spec = spec or spec_from_env()`.
  **No import of `agent.multimodal`** (takes a bool precisely to avoid the
  cycle). Place it next to `make_vision_model`.
- Verify: `python -m pytest api/tests/test_model_factory.py -q`
- Done when: whole file green, including all pre-existing tests.

---

## Phase 3 — MIME sniff fallback

**Task 3.1 — Write sniff tests (failing).**
- Files: append to `agent/tests/test_vision_resolver.py` (or a small
  `test_mime_sniff.py` beside it — implementer's choice, keep it in
  `agent/tests/`).
- Tests:
  1. `_sniff_image_mime` byte-prefix table: `b"\x89PNG\r\n..."` → `image/png`;
     `b"\xff\xd8\xff\xe0..."` → `image/jpeg`; `b"GIF89a..."` → `image/gif`;
     `b"RIFF____WEBP"` → `image/webp`; `b"BM..."` → `image/bmp`;
     `b"not an image"` → `None`.
  2. `Attachment.from_path(tmp_path / "paste")` (no extension) on a file
     containing PNG magic bytes → `mime_type == "image/png"` (today it would
     be `application/octet-stream`, `agent/multimodal.py:88-90`).
  3. Regression guard: `Attachment.from_path(tmp_path / "chart.png")` with
     arbitrary bytes still yields `image/png` (suffix guess stays primary —
     sniff only runs when the guess is `None`/`application/octet-stream`).
  4. Non-image extension-less file (plain text bytes) → still
     `application/octet-stream`.
- Verify: `python -m pytest agent/tests/ -q -k "sniff or from_path"` → fails.

**Task 3.2 — Implement `_sniff_image_mime` + `from_path` fallback.**
- Files: `agent/multimodal.py`. Pure prefix-table function per design §3.5
  (WebP needs `data[:4] == b"RIFF" and data[8:12] == b"WEBP"`); wire into
  `Attachment.from_path` only in the `guess is None or guess ==
  "application/octet-stream"` case. No new dependencies.
- Verify: `python -m pytest agent/tests/ -q` (whole agent test dir — proves
  no routing regression).
- Done when: green.

---

## Phase 4 — Rewire `_vision_read` + fail-soft `parse_output_table`

This phase touches the parse tool — everything it depends on is now built
and tested.

**Task 4.1 — Write the block-shape-through-the-tool tests (failing).**
- Files: append to `api/tests/test_output_parse.py` (new tests only).
- Fixture: a `FakeModel` class whose `invoke(msgs)` records `msgs` on the
  instance and returns `SimpleNamespace(content='{"table_kind":"loadings","rows":[{"item":"X1","value":0.74}]}')`.
  Monkeypatch **`agent.model_factory.make_vision_capable_model`** (patch at
  source module — `_vision_read`'s import will be lazy/in-function, so
  source-patching is seen) to return the fake and capture the `use_sidecar`
  kwarg. Also monkeypatch `agent.multimodal.Attachment.from_path` (or write a
  real 1-file via `tmp_path`) so no workspace file is needed — a tiny real
  PNG-magic byte string via `tmp_path` is preferred (also exercises Phase 3).
- Tests (each monkeypatches route env, then calls
  `op.parse_output_table.func(file=...)` and inspects the recorded
  `HumanMessage.content` block types):
  1. `DOTHESIS_MODEL_ROUTE` unset (native default), `ANTHROPIC_API_KEY`
     unset → recorded blocks contain `{"type": "media", ...}` and
     `use_sidecar is True`. **This is the no-regression-on-native-Gemini
     guard.**
  2. `DOTHESIS_MODEL_ROUTE=native`, `ANTHROPIC_API_KEY=sk-test`,
     `DOTHESIS_AGENT_MODEL=claude-sonnet-4-6` → a block with
     `type == "image"` and `source.type == "base64"`; `use_sidecar is False`.
  3. `DOTHESIS_MODEL_ROUTE=ofox`, `DOTHESIS_AGENT_MODEL=bailian/qwen-plus` →
     `type == "media"`, `use_sidecar is True` (default-ofox unchanged).
  4. `DOTHESIS_MODEL_ROUTE=ofox`, `DOTHESIS_AGENT_MODEL=google/gemini-2.5-flash`
     → `type == "image_url"` with a `data:image/png;base64,` URL prefix;
     `use_sidecar is False`.
  5. In every case above, the tool's return parses to the canned
     `{"table_kind": "loadings", ...}` JSON.
  6. Fail-soft: monkeypatched factory raises `RuntimeError("no key")` →
     `parse_output_table` returns JSON containing `"error"` and `"hint"`,
     and does NOT raise.
  7. List-content flatten: FakeModel returns
     `content=[{"text": '{"table_kind":"htmt",'}, {"text": '"rows":[{"item":"A","value":0.5}]}'}]`
     (Gemini 3.x parts shape) → tool output parses cleanly with
     `table_kind == "htmt"`.
- Verify: `python -m pytest api/tests/test_output_parse.py -q` → new tests
  fail (old `_vision_read` never calls the factory); **existing tests still
  pass**.

**Task 4.2 — Implement: `_flatten_content`, rewired `_vision_read`, fail-soft wrap.**
- Files: `agent/multimodal.py`, `agent/tools/output_parse.py`.
- Steps, in order:
  1. `agent/multimodal.py`: extract the list-of-parts flatten from
     `_transcribe_via_vision` (`multimodal.py:236-239`) into module-level
     `_flatten_content(content) -> str`; `_transcribe_via_vision` calls it
     (pure refactor — `agent/tests/test_multimodal_routing.py` must stay
     green untouched).
  2. `agent/tools/output_parse.py`: rewrite `_vision_read` per design §3.1:
     lazy imports of `spec_from_env`, `make_vision_capable_model` (from
     `agent.model_factory`) and `Attachment`, `build_user_message`,
     `resolve_vision`, `_flatten_content` (from `agent.multimodal`);
     `res = resolve_vision(spec)`; `build_user_message(_VISION_PROMPT, [att],
     res.provider, supports_vision=True)`;
     `make_vision_capable_model(spec, use_sidecar=res.use_sidecar)`; return
     `_flatten_content(...invoke(...).content)`. **Delete** the
     `from orchestrator.llm import get_vision_llm` import (line 126). Update
     the docstring (it currently promises "provider='gemini'").
  3. `parse_output_table`: wrap the `_vision_read(file)` call
     (`output_parse.py:137`) in try/except returning
     `json.dumps({"error": f"vision parse failed: {e}", "hint": "paste the
     values or upload the SmartPLS HTML export"})`. The three downstream
     returns (lines 141-151) stay byte-identical.
- Verify: `python -m pytest api/tests/test_output_parse.py agent/tests/ -q`
- Done when: everything green; `grep -n "orchestrator" agent/tools/output_parse.py`
  returns nothing; `grep -n 'provider="gemini"' agent/tools/output_parse.py`
  returns nothing.

---

## Phase 5 — Full-suite verification + doc alignment

**Task 5.1 — Full regression sweep.**
- Verify: `python -m pytest api/tests/test_output_parse.py api/tests/test_model_factory.py api/tests/test_orchestrator_llm.py agent/tests/ -q`
  (test_orchestrator_llm.py is included because `get_vision_llm` lost a
  caller — its behavior must be unchanged).
- Done when: zero failures, zero existing tests modified
  (`git diff --stat api/tests/test_orchestrator_llm.py agent/tests/test_multimodal_routing.py` shows only additions to files this plan names, and the pre-existing test functions are untouched in the diff).

**Task 5.2 — Update module docstrings that state the old design.**
- Files: `agent/tools/output_parse.py` (header comment block at lines
  106-113 says "isolated behind _vision_read... goes through the REAL
  multimodal API + the Gemini LLM factory" — update to name the resolver and
  the per-provider dispatch); `agent/multimodal.py` module docstring gains
  one line for `resolve_vision`. No new .md files.
- Verify: `python -m pytest api/tests/test_output_parse.py -q` (docstrings
  only — this is a sanity re-run).
- Done when: no stale "always Gemini" claims remain in the two touched
  modules' comments about the *parse* path (the sidecar's "always Gemini"
  rationale in `model_factory.py:226-231` is still true and stays).

---

## Phase 6 — Optional, manual, NOT CI: Ofox OpenAI-compat vision probe

Addresses design risk #1 (the only unverified matrix cell). Do this only if
credentials are available; it must never run in the default pytest suite.

**Task 6.1 — Probe script.**
- Files: create `scripts/probe_ofox_vision.py` (pattern precedent:
  `scripts/probe_prompt_cache.py`, referenced at `agent/model_factory.py:178`).
  It sends a small generated PNG as an `image_url` data-URI block to
  `https://api.ofox.ai/v1` with `model=google/gemini-2.5-flash` and prints
  whether the reply describes the image. Requires `OFOX_API_KEY`; exits with
  a clear message when unset.
- Verify: manual run with a real key:
  `arch -arm64 api/.venv/bin/python scripts/probe_ofox_vision.py`
- Done when: outcome is recorded as a dated comment at the top of the script
  (verified working / broken). **If broken:** flip the resolver's ofox
  vision-capable branch default by documenting
  `DOTHESIS_VISION_FORCE_SIDECAR=1` in the deploy env — do NOT change the
  resolver code; the escape hatch exists for exactly this.

---

## Execution order & dependencies

```
Phase 0 (baseline)
  └─► Phase 1 (resolver — pure, no deps)
        └─► Phase 2 (factory chooser)      Phase 3 (mime sniff — independent, can run parallel to 2)
              └────────────┬───────────────────────┘
                           ▼
                    Phase 4 (rewire _vision_read)   ← the only phase touching the tool
                           ▼
                    Phase 5 (full sweep + docs)
                           ▼
                    Phase 6 (optional manual probe)
```

## Definition of done (whole initiative)

1. The §3.3 matrix in the design spec is enforced by passing unit tests, per
   route, with monkeypatched env and zero network.
2. `agent/tools/output_parse.py` contains no hardcoded `provider="gemini"`
   and no `orchestrator` import.
3. Native-Gemini default and default-Ofox (`bailian/qwen-plus`) behavior is
   bit-identical (same sidecar client, same `media` blocks) — proven by
   tests 4.1.1 and 4.1.3.
4. A native-Claude deployment (`ANTHROPIC_API_KEY`, no Google key) gets a
   working screenshot parse via anthropic `image` blocks, and any residual
   failure surfaces as `{"error", "hint"}` JSON, never an uncaught exception.
5. All pre-existing tests pass unmodified.

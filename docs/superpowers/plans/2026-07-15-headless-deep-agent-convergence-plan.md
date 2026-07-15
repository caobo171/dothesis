# Headless Deep-Agent Convergence (A+B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One brain for every surface — a headless runner (`agent/headless.py`) that drives the existing deep agent to completion without a human, and the partner API rebuilt as the first headless client.

**Architecture:** Sub-project A adds `run_headless(agent, store, profile)` — a loop over the existing `build_agent`/`stream_turn` spine that plays the student's part (auto-decides `[OPTIONS]`, records decisions, stall-detects, enforces budgets). Sub-project B replaces the partner report's straight-line pipeline with: create a system-owned project row → seed the store via `commit_slice` → run the headless agent in a Job subprocess → export through the shared renderer → presign from the shared exports rows. Model capability routing (`supports_vision`, spec-derived `detect_provider`) fixes the attachment-format defect and makes vision a runtime capability instead of a model property.

**Tech Stack:** Python 3.13, deepagents/LangGraph (`InMemorySaver` for headless conversations), FastAPI, SQLAlchemy + Alembic, `FakeChatModel` fixtures for all agent-loop tests.

**Design spec (source of truth, approved):** `docs/superpowers/specs/2026-07-15-headless-deep-agent-convergence-design.md`

## Global Constraints

- **All new HTTP endpoints are `@router.post(...)`** — read-only ops too. `GET /api/v1/health` is the only allowed GET (CLAUDE.md).
- **`agent/` must NEVER import `api.app.*` / `app.*`.** That is why `pdf_extract` moves to `agent/` with a shim left at the old path. `agent → orchestrator` is allowed (existing direction: `agent/tools/output_parse.py:126`).
- **Python tests run via `cd api && ./run.sh pytest …`** — never `.venv/bin/*` directly (venv is arm64, shell is x86_64). Agent-package tests run as `cd api && ./run.sh pytest ../agent/tests/... -q`.
- **Comments explain WHY (the decision/reasoning), not what** — match `agent/runtime.py` / `api/app/agent_state.py` style. Every code block below carries its rationale comments; keep them.
- **`DbProjectStateStore` only round-trips `SLICE_OWNERSHIP` keys** (`api/app/agent_state.py:105-146,164-219`). Any new context_store key must be added to `SLICE_OWNERSHIP` (or `COACHING_KEYS`) AND covered by a Db round-trip test, or it is dead in prod.
- **Budget tests assert the run STOPS (fails)** — never that it completes. Budget exhaustion is a failed run with partial state preserved, never a silent success (spec §1).
- **Headless invariant:** neither `stream_turn` nor `build_agent` may inspect `RunProfile` — mode differences are data held by the caller only.
- **TDD:** every task writes its failing test first, watches it fail, then implements.
- Frequent commits — one per task, on branch `spec/headless-deep-agent-convergence`, no pushes.

## Design resolutions (spec-vs-code gaps found during verification — resolved here, not re-litigated)

1. **`decisions` needs a `SLICE_OWNERSHIP` entry.** The spec says "no store changes", but `commit_slice` rejects unowned keys (`agent/state.py:198-202`). Resolution: add `"decisions"` to every module's ownership list — the exact mechanism the `field_it_*` keys already use (`agent/state.py:32-38`) so `DbProjectStateStore._save` persists it automatically. Cost: `_save` mirrors the one flat list into all five module columns (redundant but always identical copies).
2. **`record_decision` must neutralize `commit_slice` side effects.** A bare commit flips the module to `in_progress` and flags started downstream modules `needs_review`. Recording an audit row must not move the state machine, so `record_decision` passes `status_overrides` snapshotting every module's current status (`commit_slice` applies overrides after its own status writes, `agent/state.py:248-250`).
3. **`roadmap.next_action` has no "done" sentinel** — when everything is done it returns the export/defense CTA (`agent/roadmap.py:140-143`). Terminal condition is therefore `all(status[m] == "done")`, checked by the runner directly.
4. **`get_vision_llm` delegate is a lazy in-function import.** `orchestrator/llm.py:9-11` documents `orchestrator → agent` as the cycle to avoid; the spec still mandates a delegate. A module-level import would create the load-time cycle; an import inside the function body does not (both directions are already lazy).
5. **`_infer_topic` / `_infer_model` cannot simply be deleted:** `api/app/import_work.py:11` imports them. They move into `import_work.py` (their last consumer); partner stops using them because the headless agent (backfill tool + skills) replaces inference.
6. **Partner M1 seeding requires extending `SLICE_OWNERSHIP["M1"]`** with the topic-framing keys the composers read from the `m1_topic` column (`language`, `field`, `research_type`, `objectives`, `target_population`, `scope`, `user_context`) — otherwise `commit_slice` rejects them and they never reach prod rows.
7. **progress_token → Job mapping needs a column.** The spec deletes the in-memory `_PROGRESS` dict and says progress rides JobEvent/SSE, but never says how the partner's opaque token finds the Job. Resolution: nullable indexed `jobs.partner_token` + Alembic migration.
8. **Wall-clock enforcement** wraps each turn's event-drain in `asyncio.wait_for(remaining)` — a turn cannot overrun the budget by more than its own timeout, and the check also runs at every loop boundary.

## File structure

| Path | Change | Responsibility |
|---|---|---|
| `agent/model_factory.py` | modify | + `vision_model`/`supports_vision` on `ModelSpec`, `model_supports_vision()`, `make_vision_model()` — the ONE model-truth source |
| `orchestrator/llm.py` | modify | `get_vision_llm` becomes a thin lazy delegate to `make_vision_model` |
| `agent/pdf_extract.py` | create | `extract_pdf_text` implementation (moved from api) |
| `api/app/pdf_extract.py` | rewrite | re-export shim (old import paths untouched) |
| `agent/multimodal.py` | modify | `detect_provider(spec)`, capability-driven `build_user_message`, vision-transcription + scanned-PDF fallback; no `NotImplementedError` left |
| `agent/runtime.py` | modify | attachment path passes the spec into `build_user_message` (lines 637-643) |
| `agent/state.py` | modify | `SLICE_OWNERSHIP` gains `decisions` (all modules) + M1 topic-framing keys |
| `agent/headless.py` | create | `RunProfile`, `RunResult`, `pick_option`, `record_decision`, `run_headless` — the run spine |
| `agent/tools/diagram.py` | create | `render_model_diagram` tool (promoted from partner, `shutil.which` node discovery) |
| `agent/tools/research.py` | modify | wall-clock cap + Crossref fallback behind `research_scout` |
| `orchestrator/tools/compose_export.py` | modify | `merge_conclusion` argument on `compose_sections` |
| `api/app/models.py` | modify | `Job.partner_token` column |
| `api/migrations/versions/20260715_partner_token.py` | create | migration for the column |
| `api/app/partner_run.py` | create | partner-as-headless-client: system user, seeding, export step, `ReportError`, extraction/sniff (moved) |
| `api/app/headless_entry.py` | create | `python -m app.headless_entry` subprocess entrypoint (events.jsonl contract) |
| `api/app/job_runner.py` | modify | `spawn_headless_run` |
| `api/app/routers/partner_report.py` | rewrite | create/seed/spawn/await/presign; progress from Job |
| `api/app/import_work.py` | modify | absorbs `_infer_topic`/`_infer_model` |
| `api/app/partner_report_service.py` | delete | replaced by `partner_run.py` + shared engine paths |
| tests | create/modify | listed per task |

---

### Task 1: Vision capability in the model factory

**Files:**
- Modify: `agent/model_factory.py` (ModelSpec at :23-29, `spec_from_env` at :32-55; append `make_vision_model` after `_ofox`)
- Modify: `orchestrator/llm.py:92-114` (`get_vision_llm` body → delegate)
- Test: `api/tests/test_model_factory.py` (append), `api/tests/test_orchestrator_llm.py` (existing vision tests must keep passing)

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `ModelSpec` gains `vision_model: str = ""` and `supports_vision: bool = False` (dataclass fields, appended after `max_tokens`).
  - `model_supports_vision(model: str) -> bool` — fail-closed lookup.
  - `make_vision_model(spec: ModelSpec | None = None, temperature: float | None = None)` → `ChatGoogleGenerativeAI` (Ofox Gemini-native endpoint on `route=="ofox"`).
  - `orchestrator.llm.get_vision_llm(model=None, temperature=None)` — unchanged signature, delegates.

- [ ] **Step 1: Write the failing tests** — append to `api/tests/test_model_factory.py`:

```python
# --- A: vision capability fields (headless convergence spec §2) -------------
from agent.model_factory import make_vision_model, model_supports_vision


def test_supports_vision_lookup_fail_closed():
    # FAIL-CLOSED is the load-bearing property: an unknown id must read as
    # text-only, so the worst drift outcome is a needless transcription —
    # never Gemini media blocks shipped into an OpenAI-compat endpoint
    # (design-doc defect 1's failure shape).
    assert model_supports_vision("gemini-3.5-flash") is True
    assert model_supports_vision("google/gemini-2.5-flash") is True
    assert model_supports_vision("claude-sonnet-4-6") is True
    assert model_supports_vision("qwen/qwen-plus") is False
    assert model_supports_vision("qwen-plus") is False
    assert model_supports_vision("some-future-model") is False
    assert model_supports_vision("") is False


def test_spec_from_env_derives_vision_fields(monkeypatch):
    monkeypatch.setenv("DOTHESIS_MODEL_ROUTE", "ofox")
    monkeypatch.setenv("DOTHESIS_AGENT_MODEL", "qwen/qwen-plus")
    monkeypatch.delenv("DOTHESIS_VISION_MODEL", raising=False)
    spec = spec_from_env()
    assert spec.supports_vision is False
    assert spec.vision_model == ""  # "" = resolve at make_vision_model time


def test_make_vision_model_text_only_brain_defaults_to_gemini(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test")
    monkeypatch.delenv("OFOX_API_KEY", raising=False)
    spec = ModelSpec(route="native", model="qwen-plus", supports_vision=False)
    m = make_vision_model(spec)
    assert m.__class__.__name__ == "ChatGoogleGenerativeAI"
    assert "gemini-2.5-flash" in m.model


def test_make_vision_model_ofox_prefixes_and_points_at_gateway(monkeypatch):
    monkeypatch.setenv("OFOX_API_KEY", "ok-test")
    spec = ModelSpec(route="ofox", model="qwen/qwen-plus",
                     vision_model="gemini-2.5-flash", supports_vision=False)
    m = make_vision_model(spec)
    assert "google/gemini-2.5-flash" in m.model  # Ofox needs provider-prefixed ids
```

- [ ] **Step 2: Run the tests, verify they fail**

Run: `cd api && ./run.sh pytest tests/test_model_factory.py -q`
Expected: FAIL — `ImportError: cannot import name 'make_vision_model'`.

- [ ] **Step 3: Implement in `agent/model_factory.py`**

Extend `ModelSpec` (currently :23-29):

```python
@dataclass
class ModelSpec:
    route: str = "native"  # "native" | "openrouter" | "ofox"
    model: str = "gemini-3.5-flash"
    fallbacks: list[str] = field(default_factory=list)
    temperature: float = 0.4
    max_tokens: int = 8000
    # Vision routing (headless convergence spec §2). vision_model "" means
    # "resolve at make_vision_model time" — the brain itself when it can see,
    # else the Gemini sidecar. supports_vision is derived from `model` and
    # FAIL-CLOSED: unknown ids are assumed text-only, because the wrong default
    # ships Gemini media blocks into an OpenAI-compat endpoint and hard-fails,
    # while a needless transcription costs fractions of a cent.
    vision_model: str = ""
    supports_vision: bool = False
```

Add after the dataclass:

```python
# Substring lookup on the model id — the same technique opencode uses for
# prompt selection. A KNOWN MAINTENANCE POINT: new vision-capable families
# must be added here, and fail-closed keeps that drift cheap (spec Risk 4).
_VISION_MODEL_HINTS = ("gemini", "claude")


def model_supports_vision(model: str) -> bool:
    m = (model or "").lower()
    return any(h in m for h in _VISION_MODEL_HINTS)
```

In `spec_from_env` (:49-55), bind the chosen model to a local before constructing, and pass the new fields:

```python
    model = os.getenv("DOTHESIS_AGENT_MODEL", default_model)
    return ModelSpec(
        route=route,
        model=model,
        fallbacks=[m for m in os.getenv("DOTHESIS_MODEL_FALLBACKS", "").split(",") if m.strip()],
        temperature=float(os.getenv("DOTHESIS_MODEL_TEMPERATURE", "0.4")),
        max_tokens=int(os.getenv("DOTHESIS_MODEL_MAX_TOKENS", "8000")),
        vision_model=os.getenv("DOTHESIS_VISION_MODEL", ""),
        supports_vision=model_supports_vision(model),
    )
```

Append after `_ofox` (:154):

```python
def make_vision_model(spec: ModelSpec | None = None, temperature: float | None = None):
    """Vision-capable model for image / screenshot / scanned-PDF turns.

    Implementation moved here from orchestrator/llm.get_vision_llm so "what
    model am I on" has ONE source of truth (spec §2 — this takes the
    model-truth sources from three to one and clears the path for D).

    Always a Gemini client: the vision path builds Gemini-format content
    blocks, which the OpenAI-compat Ofox route can't consume. On route=ofox we
    point the Gemini client at Ofox's Gemini-NATIVE endpoint (verified
    working) with the Ofox key; else native Google. temperature defaults 0.2 —
    transcription wants determinism, not creativity.
    """
    from langchain_google_genai import ChatGoogleGenerativeAI  # noqa: PLC0415 — lazy, heavy dep

    spec = spec or spec_from_env()
    # "" = same as `model` when the brain can see; text-only brains get the
    # Gemini sidecar default (mirrors the old get_vision_llm default).
    m = spec.vision_model or (spec.model if spec.supports_vision else "gemini-2.5-flash")
    t = 0.2 if temperature is None else temperature
    ofox_key = os.getenv("OFOX_API_KEY")
    if spec.route == "ofox" and ofox_key:
        vm = m if "/" in m else f"google/{m}"  # Ofox needs provider-prefixed ids
        return ChatGoogleGenerativeAI(
            model=vm, google_api_key=ofox_key,
            client_options={"api_endpoint": "https://api.ofox.ai/gemini"},
            transport="rest", temperature=t)
    return ChatGoogleGenerativeAI(model=m, temperature=t)
```

- [ ] **Step 4: Replace the body of `orchestrator/llm.py:get_vision_llm` (:92-114) with the delegate** (keep the def line and signature exactly):

```python
def get_vision_llm(model: str | None = None, temperature: float | None = None):
    """Thin delegate — the implementation moved to agent.model_factory.
    make_vision_model (headless convergence spec §2: one model-truth source).
    Kept so agent/tools/output_parse.py and auto-mode call sites keep working.

    The import is LAZY (inside the function) on purpose: a module-level
    `import agent...` here is exactly the orchestrator -> agent import cycle
    this file's header warns against. Both directions being in-function keeps
    module load acyclic.

    Route resolution preserves this delegate's historical dual-env behavior
    (auto-mode sets ORCHESTRATOR_LLM_ROUTE, chat sets DOTHESIS_MODEL_ROUTE).
    """
    from agent.model_factory import ModelSpec, make_vision_model  # noqa: PLC0415 — cycle-avoiding lazy import

    route = (os.getenv("ORCHESTRATOR_LLM_ROUTE") or os.getenv("DOTHESIS_MODEL_ROUTE") or "native").lower()
    m = model or os.getenv("DOTHESIS_VISION_MODEL", "gemini-2.5-flash")
    return make_vision_model(ModelSpec(route=route, vision_model=m), temperature=temperature)
```

- [ ] **Step 5: Run the tests, verify they pass — including the untouched delegate tests**

Run: `cd api && ./run.sh pytest tests/test_model_factory.py tests/test_orchestrator_llm.py -q`
Expected: PASS (all — `test_get_vision_llm_native_default` and `test_get_vision_llm_ofox_points_at_ofox` prove the delegate is behavior-compatible).

- [ ] **Step 6: Commit**

```bash
git add agent/model_factory.py orchestrator/llm.py api/tests/test_model_factory.py
git commit -m "feat(model): vision capability fields + make_vision_model, one model-truth source"
```

---

### Task 2: Move `pdf_extract` into `agent/` (shim at the old path)

**Files:**
- Create: `agent/pdf_extract.py`
- Rewrite: `api/app/pdf_extract.py` (shim)
- Test: `agent/tests/test_pdf_extract.py`

**Interfaces:**
- Produces: `agent.pdf_extract.extract_pdf_text(pdf_bytes: bytes) -> tuple[str, int]` — identical contract to today's `api/app/pdf_extract.py:15`. Old import paths (`api/app/routers/uploads.py:25`, any `from .pdf_extract import extract_pdf_text`) keep working via the shim.

- [ ] **Step 1: Write the failing test** — `agent/tests/test_pdf_extract.py`:

```python
"""extract_pdf_text moved into agent/ (headless convergence spec §2): the
capability-driven multimodal path needs it, and agent/ importing api.app.*
is the banned agent->app direction. The shim keeps api import paths alive."""
from agent.pdf_extract import extract_pdf_text


def test_empty_bytes_returns_empty():
    assert extract_pdf_text(b"") == ("", 0)


def test_garbage_bytes_fail_soft():
    # Image-only scans / invalid PDFs must yield ("", 0), never raise — callers
    # treat empty as "no usable text" and fall back (spec Risk 3).
    assert extract_pdf_text(b"not a pdf at all") == ("", 0)


def test_api_shim_reexports_same_function():
    from app.pdf_extract import extract_pdf_text as shim
    assert shim is extract_pdf_text
```

- [ ] **Step 2: Run it, verify failure**

Run: `cd api && ./run.sh pytest ../agent/tests/test_pdf_extract.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent.pdf_extract'`.

- [ ] **Step 3: Create `agent/pdf_extract.py`** — move the ENTIRE current content of `api/app/pdf_extract.py` (all 38 lines, unchanged), updating only the module docstring's first paragraph:

```python
"""PDF text extraction — sync, no OCR.

Lives in agent/ (moved from api/app/pdf_extract.py) because the multimodal
capability path (agent/multimodal.py) extracts PDFs for text-only brains, and
agent/ importing api.app.* is the recurring layering defect this repo bans.
Used by the uploads router (via the api shim) to cache extracted text
alongside the binary in S3, and by M2 Phase 4 to verify page-reference claims.
"""
from __future__ import annotations

import io
import logging
from typing import Tuple

logger = logging.getLogger(__name__)


def extract_pdf_text(pdf_bytes: bytes) -> Tuple[str, int]:
    """Extract plain text and page count from a PDF byte string.

    Returns ('', 0) for empty input, invalid PDFs, or extraction failure
    (e.g., image-only scans). Callers should treat both empty results as
    "no usable text" and surface a warning rather than treating it as an
    error — image-only PDFs are valid input but yield no text.
    """
    if not pdf_bytes:
        return ("", 0)
    try:
        from pdfminer.high_level import extract_text
        from pdfminer.pdfpage import PDFPage
    except ImportError:
        logger.exception("pdfminer.six not installed")
        return ("", 0)

    try:
        text = extract_text(io.BytesIO(pdf_bytes))
        page_count = sum(1 for _ in PDFPage.get_pages(io.BytesIO(pdf_bytes)))
        return (text or "", page_count)
    except Exception as e:
        logger.warning("pdfminer extract failed: %s", e)
        return ("", 0)
```

Replace `api/app/pdf_extract.py` entirely with:

```python
"""Re-export shim — the implementation moved to agent/pdf_extract.py.

Moved because the capability-driven multimodal path (agent/multimodal.py)
needs extract_pdf_text, and agent/ importing api.app.* is the recurring
agent->app layering defect this repo bans (headless convergence spec §2).
The shim keeps routers/uploads.py and other api-layer imports untouched.
"""
from agent.pdf_extract import extract_pdf_text  # noqa: F401
```

- [ ] **Step 4: Run tests + the existing uploads/partner suites that import the shim path**

Run: `cd api && ./run.sh pytest ../agent/tests/test_pdf_extract.py tests/test_uploads.py tests/test_partner_report.py -q` (if `tests/test_uploads.py` doesn't exist, run `tests/ -q -k upload`)
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/pdf_extract.py api/app/pdf_extract.py agent/tests/test_pdf_extract.py
git commit -m "refactor: move pdf_extract to agent/ with api shim (agent->app ban)"
```

---

### Task 3: Capability-driven multimodal (`detect_provider(spec)` + `build_user_message`)

**Files:**
- Modify: `agent/multimodal.py` (`detect_provider` :225-234, `build_user_message` :80-100, `_build_openai_message` :180-209, `_build_anthropic_message` :214-222)
- Modify: `agent/runtime.py:637-643` (attachment path)
- Test: `agent/tests/test_multimodal_routing.py`

**Interfaces:**
- Consumes: `agent.model_factory.ModelSpec/spec_from_env/make_vision_model` (Task 1), `agent.pdf_extract.extract_pdf_text` (Task 2).
- Produces:
  - `detect_provider(spec: ModelSpec | None = None) -> Provider` — derives from `route`+`model`, never env-sniffs alone. **This is defect 1's fix.**
  - `build_user_message(text, attachments, provider, *, supports_vision: bool | None = None) -> HumanMessage`. `supports_vision=None` keeps legacy per-provider behavior so `agent/tools/output_parse.py:128` (`provider="gemini"` positional) is untouched.
  - `_transcribe_via_vision(att: Attachment) -> str` (module-private, the single stub point for tests).
  - Nothing raises `NotImplementedError` anymore.

- [ ] **Step 1: Write the failing tests** — `agent/tests/test_multimodal_routing.py`:

```python
"""Capability routing (headless convergence spec §2). The routing-table test is
the test that would have caught defect 1: env-sniffing detect_provider ignored
DOTHESIS_MODEL_ROUTE and emitted Gemini media blocks into OpenAI-compat
endpoints, breaking EVERY attachment on route=ofox."""
import pytest

from agent.model_factory import ModelSpec
from agent import multimodal
from agent.multimodal import Attachment, build_user_message, detect_provider


@pytest.mark.parametrize("route,model,anthropic_key,expected", [
    ("native", "gemini-3.5-flash", None, "gemini"),
    ("native", "claude-sonnet-4-6", "sk-x", "anthropic"),
    ("ofox", "qwen/qwen-plus", None, "openai"),      # defect 1's exact case
    ("ofox", "google/gemini-2.5-flash", None, "openai"),
    ("openrouter", "meta-llama/llama-3", None, "openai"),
])
def test_provider_derives_from_spec(monkeypatch, route, model, anthropic_key, expected):
    if anthropic_key:
        monkeypatch.setenv("ANTHROPIC_API_KEY", anthropic_key)
    else:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert detect_provider(ModelSpec(route=route, model=model)) == expected


def _png(name="chart.png"):
    return Attachment(filename=name, bytes=b"\x89PNG fakebytes", mime_type="image/png")


def _pdf(name="doc.pdf"):
    return Attachment(filename=name, bytes=b"%PDF-1.4 fake", mime_type="application/pdf")


def test_text_only_brain_transcribes_image(monkeypatch):
    # qwen-plus can't see: the image must arrive as TEXT (vision sidecar
    # transcription), never as a media/image block the endpoint rejects.
    monkeypatch.setattr(multimodal, "_transcribe_via_vision",
                        lambda att: f"[transcribed {att.filename}]")
    msg = build_user_message("look", [_png()], "openai", supports_vision=False)
    assert isinstance(msg.content, str)
    assert "[transcribed chart.png]" in msg.content


def test_text_only_brain_extracts_pdf_text(monkeypatch):
    monkeypatch.setattr("agent.pdf_extract.extract_pdf_text",
                        lambda b: ("Cronbach alpha table " * 20, 3))
    msg = build_user_message("read", [_pdf()], "openai", supports_vision=False)
    assert isinstance(msg.content, str)
    assert "Cronbach alpha table" in msg.content


def test_scanned_pdf_falls_back_to_vision(monkeypatch):
    # Risk 3: extract_pdf_text has no OCR — a scan yields near-empty text.
    # Proceeding with a hollow message is the silent failure; the fallback
    # transcribes via the vision sidecar instead.
    monkeypatch.setattr("agent.pdf_extract.extract_pdf_text", lambda b: ("", 0))
    monkeypatch.setattr(multimodal, "_transcribe_via_vision",
                        lambda att: "[vision transcription of scan]")
    msg = build_user_message("read", [_pdf("scan.pdf")], "openai", supports_vision=False)
    assert "[vision transcription of scan]" in msg.content


def test_vision_capable_openai_keeps_image_blocks():
    msg = build_user_message("look", [_png()], "openai", supports_vision=True)
    kinds = [b.get("type") for b in msg.content]
    assert "image_url" in kinds


def test_openai_non_image_never_raises(monkeypatch):
    # The NotImplementedError landmine (multimodal.py:200-209) is gone: a CSV
    # on the openai provider becomes text, whatever the vision capability.
    csv = Attachment(filename="data.csv", bytes=b"a,b\n1,2", mime_type="text/csv")
    msg = build_user_message("data", [csv], "openai", supports_vision=True)
    flat = msg.content if isinstance(msg.content, str) else str(msg.content)
    assert "a,b" in flat


def test_anthropic_pdf_document_block():
    msg = build_user_message("read", [_pdf()], "anthropic")
    kinds = [b.get("type") for b in msg.content]
    assert "document" in kinds  # no NotImplementedError anymore


def test_gemini_path_unchanged():
    msg = build_user_message("look", [_png()], "gemini")
    kinds = [b.get("type") for b in msg.content]
    assert "media" in kinds
```

- [ ] **Step 2: Run, verify failure**

Run: `cd api && ./run.sh pytest ../agent/tests/test_multimodal_routing.py -q`
Expected: FAIL — `detect_provider() takes 0 positional arguments but 1 was given`, `NotImplementedError`, etc.

- [ ] **Step 3: Implement in `agent/multimodal.py`**

Replace `detect_provider` (:225-234):

```python
def detect_provider(spec=None) -> Provider:
    """Provider of the ACTIVE brain, derived from the ModelSpec (route+model).

    The old body sniffed env (ANTHROPIC_API_KEY else "gemini") and ignored
    DOTHESIS_MODEL_ROUTE entirely — on route=ofox + qwen-plus it emitted
    Gemini-native {type:"media"} blocks into an OpenAI-compatible endpoint, a
    malformed request that broke EVERY attachment (design-doc defect 1).
    Deriving from the spec also collapses the third "what model am I on"
    source of truth into agent.model_factory.
    """
    from agent.model_factory import spec_from_env  # noqa: PLC0415 — lazy; keeps import-light callers cheap

    spec = spec or spec_from_env()
    if spec.route in ("ofox", "openrouter"):
        return "openai"  # OpenAI-compatible wire format on both gateways
    # native route mirrors model_factory._native's branch condition exactly.
    if os.getenv("ANTHROPIC_API_KEY") and "claude" in spec.model:
        return "anthropic"
    return "gemini"
```

Replace `build_user_message` (:80-100):

```python
def build_user_message(
    text: str,
    attachments: list[Attachment],
    provider: Provider,
    *,
    supports_vision: bool | None = None,
) -> HumanMessage:
    """Compose a HumanMessage carrying both prose and attached files —
    capability-driven, not provider-driven (spec §2).

    `supports_vision=None` keeps each provider's historical default (gemini/
    anthropic can see; openai fail-closed cannot) so the one existing
    positional caller (agent/tools/output_parse.py:128, provider="gemini")
    behaves identically. Callers that know the active ModelSpec pass
    spec.supports_vision explicitly (agent/runtime.py does).
    """
    if not attachments:
        return HumanMessage(content=text)

    if supports_vision is None:
        supports_vision = provider in ("gemini", "anthropic")

    if not supports_vision:
        # Text-only brain: EVERYTHING becomes text — images via the vision
        # sidecar, PDFs via extraction (vision fallback for scans). Vision is
        # a runtime capability, not a model property.
        return _build_text_only_message(text, attachments)
    if provider == "gemini":
        return _build_gemini_message(text, attachments)
    if provider == "openai":
        return _build_openai_message(text, attachments)
    if provider == "anthropic":
        return _build_anthropic_message(text, attachments)
    raise ValueError(f"unknown provider {provider!r}")
```

Add after `_upload_to_gemini_files`:

```python
# Below this many characters a "PDF extraction" is treated as a scan: pdfminer
# has no OCR, so an image-only PDF yields near-empty text and the agent would
# silently get nothing (spec Risk 3). The vision sidecar reads scans instead.
_MIN_PDF_TEXT_CHARS = 200


def _transcribe_via_vision(att: Attachment) -> str:
    """Turn an image / scanned-PDF attachment into text with the vision model.

    Isolated as the single function tests stub — same pattern as
    output_parse._vision_read — so the network/model boundary stays out of
    the test suite. Anti-fabrication: the prompt forbids invented values.
    """
    from agent.model_factory import make_vision_model  # noqa: PLC0415 — lazy, heavy dep

    prompt = (
        "Transcribe the full content of this file faithfully as plain "
        "text/Markdown. Render tables as Markdown tables. Do NOT invent or "
        "guess values; mark anything unreadable as [unreadable]."
    )
    # The vision model is always Gemini (see make_vision_model), so the
    # message uses the Gemini block shape regardless of the text brain.
    msg = _build_gemini_message(prompt, [att])
    out = make_vision_model().invoke([msg])
    content = getattr(out, "content", "")
    if isinstance(content, list):  # Gemini 3.x list-of-parts shape
        content = "".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in content
        )
    return str(content or "")


def _textualize(att: Attachment) -> tuple[str, str]:
    """(label, body) for one attachment as plain text — the text-only-brain
    path of the capability table (spec §2). Never raises: the worst input
    degrades to a lossy decode, not a dead turn."""
    name = (att.filename or "").lower()
    if att.mime_type.startswith("image/"):
        return ("image transcription", _transcribe_via_vision(att))
    if att.mime_type == "application/pdf" or name.endswith(".pdf"):
        from agent.pdf_extract import extract_pdf_text  # noqa: PLC0415 — agent-layer, lazy
        body, _pages = extract_pdf_text(att.bytes)
        if len((body or "").strip()) < _MIN_PDF_TEXT_CHARS:
            # Scanned PDF: extraction came back hollow → vision fallback
            # rather than proceeding with an empty message (Risk 3).
            return ("scanned-PDF transcription", _transcribe_via_vision(att))
        return ("PDF text", body)
    return ("file content", att.bytes.decode("utf-8", errors="replace"))


def _build_text_only_message(text: str, attachments: list[Attachment]) -> HumanMessage:
    parts = [text]
    for att in attachments:
        label, body = _textualize(att)
        parts.append(f"\n\n[ATTACHMENT {att.filename} — {label}]\n{body}")
    return HumanMessage(content="".join(parts))
```

Replace `_build_openai_message` (:180-209):

```python
def _build_openai_message(text: str, attachments: list[Attachment]) -> HumanMessage:
    """Vision-capable OpenAI-compatible brain: images ride as data-URI
    image_url blocks; everything else becomes text (OpenAI-compat chat has no
    first-class document type, and extraction is lossless enough for result
    tables). The old NotImplementedError landmine is gone — a failing raise
    on a normal upload is a worse outcome than a text fallback."""
    blocks: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for att in attachments:
        if att.mime_type.startswith("image/"):
            data_url = f"data:{att.mime_type};base64,{base64.b64encode(att.bytes).decode('ascii')}"
            blocks.append({"type": "image_url", "image_url": {"url": data_url}})
        else:
            label, body = _textualize(att)
            blocks.append({"type": "text",
                           "text": f"\n\n[ATTACHMENT {att.filename} — {label}]\n{body}"})
    return HumanMessage(content=blocks)
```

Replace `_build_anthropic_message` (:214-222):

```python
def _build_anthropic_message(text: str, attachments: list[Attachment]) -> HumanMessage:
    """Anthropic native blocks: images as `image`, PDFs as `document` (base64,
    ≤32MB inline per their docs — no File API hop needed), the rest as text.
    Implemented now (was a NotImplementedError stub) because the capability
    table says a vision-capable brain gets native blocks (spec §2)."""
    blocks: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for att in attachments:
        b64 = base64.b64encode(att.bytes).decode("ascii")
        if att.mime_type.startswith("image/"):
            blocks.append({"type": "image",
                           "source": {"type": "base64", "media_type": att.mime_type, "data": b64}})
        elif att.mime_type == "application/pdf":
            blocks.append({"type": "document",
                           "source": {"type": "base64", "media_type": "application/pdf", "data": b64}})
        else:
            label, body = _textualize(att)
            blocks.append({"type": "text",
                           "text": f"\n\n[ATTACHMENT {att.filename} — {label}]\n{body}"})
    return HumanMessage(content=blocks)
```

- [ ] **Step 4: Update the runtime call site** — `agent/runtime.py:637-643`, replace:

```python
    if attachments:
        # Lazy import — multimodal.py pulls in google-genai which is heavy
        # and only needed when the user attached something.
        from agent.multimodal import build_user_message, detect_provider
        msg = build_user_message(user_text, attachments, detect_provider())
        payload = {"messages": [msg]}
```

with:

```python
    if attachments:
        # Lazy import — multimodal.py pulls in google-genai which is heavy
        # and only needed when the user attached something.
        from agent.model_factory import spec_from_env
        from agent.multimodal import build_user_message, detect_provider
        # Capability-driven: provider AND vision support both derive from the
        # ONE model-truth source. The old env-sniffing detect_provider()
        # ignored DOTHESIS_MODEL_ROUTE and shipped Gemini media blocks into
        # OpenAI-compat endpoints (design-doc defect 1).
        spec = spec_from_env()
        msg = build_user_message(user_text, attachments, detect_provider(spec),
                                 supports_vision=spec.supports_vision)
        payload = {"messages": [msg]}
```

- [ ] **Step 5: Run tests + output_parse regression**

Run: `cd api && ./run.sh pytest ../agent/tests/test_multimodal_routing.py tests/test_output_parse.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add agent/multimodal.py agent/runtime.py agent/tests/test_multimodal_routing.py
git commit -m "feat(multimodal): capability-driven routing from ModelSpec — fixes ofox attachment defect"
```

---

### Task 4: Decision recording (`decisions` slice key + `record_decision` + Db round-trip)

**Files:**
- Modify: `agent/state.py` (SLICE_OWNERSHIP :24-40)
- Create: `agent/headless.py` (start with `record_decision` only; the runner arrives in Task 5)
- Test: `agent/tests/test_headless_decisions.py`, `api/tests/test_headless_db_roundtrip.py`

**Interfaces:**
- Produces:
  - `SLICE_OWNERSHIP[m]` contains `"decisions"` for every module `m`.
  - `agent.headless.record_decision(store, *, options: list[str], choice: str, rationale: str) -> dict` — appends `{ts, module, options, choice, rationale}` to the flat `decisions` list via `commit_slice`, with all module statuses snapshotted so recording never moves the state machine.

- [ ] **Step 1: Write the failing tests** — `agent/tests/test_headless_decisions.py`:

```python
"""Auto-decision audit trail (spec §4). Decisions ride INSIDE the owned slice,
written through commit_slice — a new top-level context_store key would
round-trip against this file store and VANISH in prod, because
DbProjectStateStore only persists SLICE_OWNERSHIP keys (the known CRITICAL
failure mode). The DB half of this proof lives in
api/tests/test_headless_db_roundtrip.py."""
from agent.headless import record_decision
from agent.state import MODULES, SLICE_OWNERSHIP, ProjectStateStore


def _store(tmp_path):
    store = ProjectStateStore(tmp_path)
    store.commit_slice("M1", {"research_title": "T"}, "seed")
    return store


def test_decisions_key_is_owned_by_every_module():
    for m in MODULES:
        assert "decisions" in SLICE_OWNERSHIP[m]


def test_record_appends_to_owned_slice(tmp_path):
    store = _store(tmp_path)
    rec = record_decision(store, options=["Có", "Không"], choice="Có",
                          rationale="auto: first option")
    st = store.load()
    assert st["contextStore"]["decisions"] == [rec]
    assert rec["module"] == "M1" and rec["choice"] == "Có" and rec["ts"]

    record_decision(store, options=["A", "B"], choice="A", rationale="auto")
    assert len(store.load()["contextStore"]["decisions"]) == 2


def test_record_never_moves_the_state_machine(tmp_path):
    # commit_slice's normal side effects (module -> in_progress, downstream
    # needs_review) belong to CONTENT commits. An audit append must be inert:
    # a done module stays done, nothing gets flagged, focus stays put.
    store = _store(tmp_path)
    store.commit_slice("M1", {"research_questions": ["RQ1"]}, "finish M1",
                       confirm_done=True)
    store.commit_slice("M2", {"literature_sources": [{"title": "P"}]}, "start M2")
    before = store.load()
    record_decision(store, options=["Next", "Stop"], choice="Next", rationale="auto")
    after = store.load()
    assert after["status"] == before["status"]      # M1 still done, M2 in_progress
    assert after["focus"] == before["focus"]
```

And `api/tests/test_headless_db_roundtrip.py` (uses the existing `project_id` fixture from `api/tests/conftest.py:27-38`):

```python
"""NON-NEGOTIABLE Db round-trip for headless auto-decisions (spec §4).

DbProjectStateStore.load()/_save() iterate SLICE_OWNERSHIP and nothing else —
this is the test class that catches "works on the file store, dead in prod"."""
from agent.headless import record_decision
from app.agent_state import DbProjectStateStore
from app.db import get_engine


def test_decisions_round_trip_through_db(project_id, tmp_path):
    store = DbProjectStateStore(get_engine(), project_id, tmp_path)
    store.commit_slice("M1", {"research_title": "T"}, "seed")
    rec = record_decision(store, options=["Có", "Không"], choice="Có",
                          rationale="auto: first option")
    # Fresh store = fresh DB read, no in-memory carryover.
    reloaded = DbProjectStateStore(get_engine(), project_id, tmp_path).load()
    assert reloaded["contextStore"]["decisions"][0]["choice"] == "Có"
    assert reloaded["contextStore"]["decisions"][0]["module"] == rec["module"]


def test_decision_recording_keeps_status_in_db(project_id, tmp_path):
    store = DbProjectStateStore(get_engine(), project_id, tmp_path)
    store.commit_slice("M1", {"research_title": "T", "research_questions": ["RQ"]},
                       "seed", confirm_done=True)
    record_decision(store, options=["A", "B"], choice="A", rationale="auto")
    reloaded = DbProjectStateStore(get_engine(), project_id, tmp_path).load()
    assert reloaded["status"]["M1"] == "done"   # audit append didn't regress it
```

- [ ] **Step 2: Run both, verify failure**

Run: `cd api && ./run.sh pytest ../agent/tests/test_headless_decisions.py tests/test_headless_db_roundtrip.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent.headless'` and the ownership assertion.

- [ ] **Step 3: Extend `SLICE_OWNERSHIP` in `agent/state.py`** — replace the dict (:24-40) with:

```python
SLICE_OWNERSHIP: dict[str, list[str]] = {
    "M1": ["research_title", "research_questions", "decisions"],
    "M2": ["literature_sources", "research_gaps", "decisions"],
    # sample_plan / cmb_plan / missing_data_plan added for the F8 methods
    # pre-flight: commit_slice must be able to WRITE them (they're M3 design
    # decisions), and preflight_check reads them to gate M3->M4 readiness.
    "M3": ["conceptual_model", "hypotheses", "methodology", "instrument",
           "sample_plan", "cmb_plan", "missing_data_plan", "decisions"],
    # field_it_* added for F7 results ingestion: fielded survey responses +
    # quality flags land in M4 (where F8's Output Sanity Layer reads). Making
    # them M4-owned is what lets DbProjectStateStore._save persist them into the
    # m4_analysis column automatically — the same mechanism as analysis_results,
    # so there is no Db-specific write path to forget (project_db_store_persistence_gap).
    "M4": ["analysis_outline", "analysis_results",
           "field_it_collection_id", "field_it_responses", "field_it_quality",
           "decisions"],
    "M5": ["final_sections", "decisions"],
}
# "decisions" (headless auto-decision audit trail, convergence spec §4) is
# owned by EVERY module: the runner records each choice under whichever module
# is in focus, and riding the slice map is what makes DbProjectStateStore
# persist it with no store-specific code — the same mechanism as field_it_*.
# The flat load() view holds ONE decisions list; _save mirrors it into every
# module column, so the five copies are redundant but always identical. That
# redundancy was accepted over a new top-level key, which would round-trip in
# file-store tests and silently VANISH in prod (the known CRITICAL gap).
```

- [ ] **Step 4: Create `agent/headless.py`** (record_decision only for now):

```python
"""Headless run spine (convergence spec §1/§4).

The runner plays the STUDENT's part against the same build_agent/stream_turn
brain chat uses. Mode differences are DATA held by this caller — neither
stream_turn nor build_agent ever inspects a profile, which is what preserves
the headless invariant: chat features cannot gate headless, because headless
runs the same code with a different caller.
"""
from __future__ import annotations

from datetime import datetime, timezone

from agent.state import MODULES, ProjectStateStore


def record_decision(
    store: ProjectStateStore,
    *,
    options: list[str],
    choice: str,
    rationale: str,
) -> dict:
    """Append one auto-decision to the audit trail, through commit_slice.

    Spec §4: decisions ride INSIDE the owned slice ("decisions" is in every
    module's SLICE_OWNERSHIP) so DbProjectStateStore persists them via the
    existing ownership machinery — a new top-level key would pass file-store
    tests and vanish in prod. Worse data modelling, considerably safer.

    status_overrides snapshots every module's CURRENT status because
    commit_slice's normal side effects (module -> in_progress, downstream
    needs_review propagation) belong to content commits; an audit append that
    regressed a `done` module or flagged reviews would corrupt the very run it
    is auditing. Overrides are applied after commit_slice's own status writes
    (agent/state.py), so the snapshot always wins.
    """
    state = store.load()
    module = state.get("focus") or "M1"
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "module": module,
        "options": list(options),
        "choice": choice,
        "rationale": rationale,
    }
    decisions = list(state["contextStore"].get("decisions") or []) + [record]
    store.commit_slice(
        module,
        {"decisions": decisions},
        reason=f"headless auto-decision: {choice[:80]}",
        status_overrides={m: state["status"].get(m, "locked") for m in MODULES},
    )
    return record
```

- [ ] **Step 5: Run the tests, verify they pass; run the state-store regression suites**

Run: `cd api && ./run.sh pytest ../agent/tests/test_headless_decisions.py ../agent/tests/test_state_store.py ../agent/tests/test_state_tools.py tests/test_headless_db_roundtrip.py tests/test_agent_state.py tests/test_agent_state_coaching.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add agent/state.py agent/headless.py agent/tests/test_headless_decisions.py api/tests/test_headless_db_roundtrip.py
git commit -m "feat(headless): decision audit trail in the owned slice + Db round-trip proof"
```

---

### Task 5: The run spine — `run_headless` with stall detection and budgets

**Files:**
- Modify: `agent/headless.py` (add `RunProfile`, `RunResult`, `pick_option`, `run_headless`)
- Test: `agent/tests/test_headless_runner.py`

**Interfaces:**
- Consumes: `agent.runtime.build_agent` (runtime.py:467), `agent.runtime.stream_turn(agent, thread_id, user_text, attachments=None, store=None)` (runtime.py:608), `record_decision` (Task 4), `agent.testing.fake_model.FakeChatModel.from_fixtures_dir` (fake_model.py:64), `langgraph.checkpoint.memory.InMemorySaver`.
- Produces:
  - `RunProfile(interactive: bool = False, max_turns: int = 40, wall_clock_s: int = 1800, max_stalls: int = 3, on_options: str = "auto")`
  - `RunResult(status, reason, turns, decisions, pending_options)` with `status ∈ {"done","failed","needs_input"}`, `reason ∈ {"roadmap_done","max_turns","wall_clock","max_stalls","awaiting_options"}`
  - `async run_headless(agent, store, profile, *, thread_id="headless", initial_prompt="continue", on_event=None, _clock=time.monotonic) -> RunResult`
  - `pick_option(options: list[str]) -> tuple[str, str]` (choice, rationale)

- [ ] **Step 1: Write the failing tests** — `agent/tests/test_headless_runner.py`:

```python
"""run_headless over the real deepagents brain with the scripted FakeChatModel:
loop, stall detection, budgets, options auto-decide (spec §1/§5). Only the
completion is fake — tools, store writes, and the [OPTIONS] parser are real.

Budget tests assert the run STOPS (fails). A budget bug only ever surfaces as
a test that asserts failure — asserting completion would pass right through it.
"""
import asyncio
import json

from agent.headless import RunProfile, run_headless
from agent.state import MODULES, ProjectStateStore


def _module_steps(module, writes):
    # One roadmap-module turn = 2 completions: the tool_calls step, then the
    # post-ToolMessage wrap-up (FakeChatModel steps index by AI-message count).
    return [
        {"response": f"Working on {module}.",
         "tool_calls": [{"name": "commit_slice",
                         "args": {"module": module, "writes": writes,
                                  "reason": "headless fixture", "confirm_done": True}}]},
        {"response": f"{module} committed."},
    ]


HAPPY = {"scenario": "headless-happy", "entry": "continue", "steps": [
    *_module_steps("M1", {"research_title": "T", "research_questions": ["RQ1"]}),
    *_module_steps("M2", {"literature_sources": [{"title": "P", "year": 2024}]}),
    *_module_steps("M3", {"conceptual_model": "CM", "hypotheses": ["H1"],
                          "methodology": "PLS-SEM"}),
    *_module_steps("M4", {"analysis_outline": "O", "analysis_results": "R"}),
    *_module_steps("M5", {"final_sections": [{"title": "Intro", "prose": "p"}]}),
]}


def _build(tmp_path, fixture):
    fx = tmp_path / "fixtures"
    fx.mkdir()
    (fx / "run.json").write_text(json.dumps(fixture), encoding="utf-8")
    from langgraph.checkpoint.memory import InMemorySaver
    from agent.runtime import build_agent
    from agent.testing.fake_model import FakeChatModel
    proj = tmp_path / "proj"
    store = ProjectStateStore(proj)
    agent = build_agent(proj, model=FakeChatModel.from_fixtures_dir(str(fx)),
                        checkpointer=InMemorySaver(), store=store)
    return agent, store


def test_happy_path_runs_to_done(tmp_path):
    agent, store = _build(tmp_path, HAPPY)
    result = asyncio.run(run_headless(agent, store, RunProfile(max_turns=10)))
    assert result.status == "done" and result.reason == "roadmap_done"
    st = store.load()
    assert all(st["status"][m] == "done" for m in MODULES)


def test_stall_fixture_fails_at_max_stalls(tmp_path):
    # A model that neither commits nor asks: store bytes never change, no
    # [OPTIONS] — deterministic stall regardless of WHY (missing marker,
    # off-script model, silent tool failure). The run must FAIL, loudly.
    stall = {"scenario": "stall", "entry": "continue", "steps": [
        {"response": "Hmm, let me think."},
        {"response": "Still thinking."},
        {"response": "Thinking harder."},
    ]}
    agent, store = _build(tmp_path, stall)
    result = asyncio.run(run_headless(agent, store,
                                      RunProfile(max_stalls=3, max_turns=10)))
    assert result.status == "failed" and result.reason == "max_stalls"
    assert result.turns == 3


def test_looping_fixture_fails_at_turn_cap(tmp_path):
    # Progress every turn, completion never: the turn budget is the only thing
    # standing between this and infinite spend.
    steps = []
    for i in range(6):
        steps += [
            {"response": "Revising.",
             "tool_calls": [{"name": "commit_slice",
                             "args": {"module": "M1",
                                      "writes": {"research_title": f"T{i}"},
                                      "reason": "loop fixture"}}]},
            {"response": "Revised."},
        ]
    agent, store = _build(tmp_path, {"scenario": "loop", "entry": "continue",
                                     "steps": steps})
    result = asyncio.run(run_headless(agent, store, RunProfile(max_turns=4)))
    assert result.status == "failed" and result.reason == "max_turns"
    assert result.turns == 4
    # partial state preserved — budget exhaustion is failure WITH the work kept
    assert store.load()["contextStore"]["research_title"] == "T3"


def test_wall_clock_fails_run(tmp_path):
    agent, store = _build(tmp_path, {"scenario": "slow", "entry": "continue",
                                     "steps": [{"response": "ok"},
                                               {"response": "ok again"}]})
    t = {"now": 0.0}

    def clock():  # each budget check advances fake time 400s
        t["now"] += 400.0
        return t["now"]

    result = asyncio.run(run_headless(agent, store,
                                      RunProfile(wall_clock_s=600), _clock=clock))
    assert result.status == "failed" and result.reason == "wall_clock"


OPTIONS_FIX = {"scenario": "opts", "entry": "continue", "steps": [
    {"response": "Chọn cách tiếp cận:\n\n[OPTIONS:paradigm] Định lượng | Định tính"},
    {"expect_user": "Định lượng",
     "response": "Committing the pick.",
     "tool_calls": [{"name": "commit_slice",
                     "args": {"module": "M1", "writes": {"research_title": "T"},
                              "reason": "picked"}}]},
    {"response": "Done for now."},
]}


def test_options_auto_decided_and_recorded(tmp_path):
    agent, store = _build(tmp_path, OPTIONS_FIX)
    result = asyncio.run(run_headless(agent, store,
                                      RunProfile(max_turns=3, max_stalls=1)))
    # The fixture never reaches all-done: the run must STOP as a failure,
    # never report success on a hollow project.
    assert result.status == "failed"
    assert result.decisions and result.decisions[0]["choice"] == "Định lượng"
    st = store.load()
    assert st["contextStore"]["decisions"][0]["choice"] == "Định lượng"
    assert st["contextStore"]["research_title"] == "T"  # the reply drove the agent


def test_on_options_ask_stops_and_surfaces(tmp_path):
    agent, store = _build(tmp_path, OPTIONS_FIX)
    result = asyncio.run(run_headless(agent, store,
                                      RunProfile(on_options="ask", max_turns=3)))
    assert result.status == "needs_input" and result.reason == "awaiting_options"
    assert result.pending_options == ["Định lượng", "Định tính"]
    assert not store.load()["contextStore"].get("decisions")  # nothing auto-recorded
```

- [ ] **Step 2: Run, verify failure**

Run: `cd api && ./run.sh pytest ../agent/tests/test_headless_runner.py -q`
Expected: FAIL — `ImportError: cannot import name 'RunProfile'`.

- [ ] **Step 3: Implement the runner in `agent/headless.py`** (append below `record_decision`; add `import asyncio`, `import time`, `from dataclasses import dataclass, field` to the imports):

```python
@dataclass
class RunProfile:
    """Mode differences as DATA (spec §1). Only the runner reads this —
    stream_turn/build_agent never see it, so a chat feature physically cannot
    gate a headless run."""
    interactive: bool = False
    max_turns: int = 40
    wall_clock_s: int = 1800
    max_stalls: int = 3
    on_options: str = "auto"  # "auto": decide + record | "ask": stop, surface options


@dataclass
class RunResult:
    status: str   # "done" | "failed" | "needs_input"
    reason: str   # "roadmap_done" | "max_turns" | "wall_clock" | "max_stalls" | "awaiting_options"
    turns: int = 0
    decisions: list = field(default_factory=list)
    pending_options: list | None = None


def pick_option(options: list[str]) -> tuple[str, str]:
    """Headless option policy: FIRST option.

    By the [OPTIONS] convention (runtime.SYSTEM_PROMPT) the first card is the
    confirm/advance choice, so first-pick is the fire-and-forget default.
    Deterministic (hence testable), and always auditable + overridable because
    every pick flows through record_decision.
    """
    return options[0], "auto: first option (headless default policy)"


def _options_from_events(events: list[dict]) -> list[str] | None:
    """[OPTIONS] surfaces as a card_grid tool_calls event — reuse the runtime's
    parser output instead of re-parsing prose here (one parser, one truth).
    papers_panel / export hints also ride tool_calls, hence the widget filter."""
    for ev in reversed(events):
        if ev.get("type") == "tool_calls":
            payload = ev.get("payload") or {}
            if payload.get("widget_type") == "card_grid":
                return [o["value"] for o in payload.get("options") or []]
    return None


def _all_done(state: dict) -> bool:
    # Terminal condition. roadmap.next_action never returns a "done" sentinel —
    # with everything done it returns the export/defense CTA — so the runner
    # reads the status map directly.
    status = state.get("status") or {}
    return all(status.get(m) == "done" for m in MODULES)


async def run_headless(
    agent,
    store: ProjectStateStore,
    profile: RunProfile,
    *,
    thread_id: str = "headless",
    initial_prompt: str = "continue",
    on_event=None,
    _clock=time.monotonic,
) -> RunResult:
    """Drive the deep agent to roadmap completion with no human present.

    ALL THREE budgets fail the run — exhaustion is a failed run with partial
    state preserved (everything commit_slice wrote stays), never a silent
    success. Stall detection is deterministic: store.load() before vs after
    the turn catches "nothing happened" regardless of cause (missing [OPTIONS]
    marker, off-script model, unresolvable blocker, silently failing tool).
    It bounds the damage of prose-asking; it does not make auto-decide an
    enforced boundary (spec Risk 1).

    _clock is injectable so wall-clock tests are deterministic instead of
    sleeping (a slow test IS a budget bug's favorite hiding place).
    """
    from agent.runtime import stream_turn  # noqa: PLC0415 — keeps headless import-light

    started = _clock()
    stalls = 0
    turns = 0
    decisions: list[dict] = []
    next_prompt = initial_prompt

    while True:
        before = store.load()
        if _all_done(before):
            return RunResult("done", "roadmap_done", turns, decisions)
        if turns >= profile.max_turns:
            return RunResult("failed", "max_turns", turns, decisions)
        remaining = profile.wall_clock_s - (_clock() - started)
        if remaining <= 0:
            return RunResult("failed", "wall_clock", turns, decisions)

        events: list[dict] = []

        async def _drain(prompt: str) -> None:
            async for ev in stream_turn(agent, thread_id, prompt, store=store):
                events.append(ev)
                if on_event is not None:
                    on_event(ev)

        try:
            # Hard wall-clock: a single runaway turn cannot overrun the budget
            # (bounded_invoke at orchestrator/agents/base.py is the precedent
            # for per-call wall-clock discipline).
            await asyncio.wait_for(_drain(next_prompt), timeout=max(remaining, 0.001))
        except asyncio.TimeoutError:
            return RunResult("failed", "wall_clock", turns + 1, decisions)
        turns += 1

        options = _options_from_events(events)
        after = store.load()
        # Progress = observable change OR an explicit question. Errors surface
        # as {"type":"error"} events with no state change → they land in the
        # stall path and get bounded, not retried forever.
        progressed = (after != before) or bool(options)
        if not progressed:
            stalls += 1
            if stalls >= profile.max_stalls:
                return RunResult("failed", "max_stalls", turns, decisions)
            next_prompt = "continue"
            continue
        stalls = 0

        if options:
            if profile.on_options == "ask":
                return RunResult("needs_input", "awaiting_options", turns,
                                 decisions, pending_options=options)
            choice, rationale = pick_option(options)
            decisions.append(record_decision(
                store, options=options, choice=choice, rationale=rationale))
            # The choice IS the next user turn — exactly what a student
            # clicking the card would have sent.
            next_prompt = choice
        else:
            next_prompt = "continue"
```

- [ ] **Step 4: Run the tests, verify they pass**

Run: `cd api && ./run.sh pytest ../agent/tests/test_headless_runner.py -q`
Expected: PASS (6 tests). If the happy path fails on FixtureError, check the fixture's `entry` matches after the `[PROJECT STATE]` header (matching is `re.search`, never anchored).

- [ ] **Step 5: Commit**

```bash
git add agent/headless.py agent/tests/test_headless_runner.py
git commit -m "feat(headless): run_headless spine — stall detection, budgets fail loudly, options auto-decide"
```

---

### Task 6: `render_model_diagram` tool (promoted from the partner service)

**Files:**
- Create: `agent/tools/diagram.py`
- Modify: `agent/runtime.py` (register the tool in `build_agent`'s tools list, after the `make_defense_tools` entry at :537)
- Test: `agent/tests/test_diagram_tool.py`

**Interfaces:**
- Produces: `render_model_diagram(constructs: list[dict], paths: list[dict]) -> str` (a `@tool`; JSON string result `{"ok": true, "image_markdown": "![...](data:image/png;base64,...)"}` or `{"error": ...}`), plus pure helper `_mermaid_source(constructs, paths) -> str | None`.

- [ ] **Step 1: Write the failing tests** — `agent/tests/test_diagram_tool.py`:

```python
"""render_model_diagram — promoted from partner_report_service._render_model_diagram
(spec §3): the hardcoded nvm node path (_NODE_BIN) whose failure was swallowed
meant every partner report silently shipped without its diagram. As an agent
tool all three surfaces get it, with node discovered via shutil.which."""
import json

from agent.tools.diagram import _mermaid_source, render_model_diagram


def test_mermaid_source_from_model():
    src = _mermaid_source(
        constructs=[{"id": "TR", "label": "Trust"}, {"id": "PI", "label": "Intention"}],
        paths=[{"from": "TR", "to": "PI"}],
    )
    assert src.startswith("flowchart LR")
    assert 'TR["Trust"]' in src and "TR --> PI" in src


def test_mermaid_source_rejects_dangling_paths():
    # A path to an undeclared construct is model noise, not a diagram edge.
    assert _mermaid_source(constructs=[{"id": "A", "label": "A"}],
                           paths=[{"from": "A", "to": "GHOST"}]) is None
    assert _mermaid_source(constructs=[], paths=[]) is None


def test_tool_fails_soft_without_mmdc(tmp_path, monkeypatch):
    # No mermaid CLI installed → a recovery-hint JSON, never a crashed turn.
    import agent.tools.diagram as mod
    monkeypatch.setattr(mod, "_MERMAID_DIR", tmp_path)  # empty dir: no mmdc
    out = json.loads(render_model_diagram.func(
        constructs=[{"id": "A", "label": "A"}, {"id": "B", "label": "B"}],
        paths=[{"from": "A", "to": "B"}]))
    assert out["error"] == "mmdc_unavailable"
```

- [ ] **Step 2: Run, verify failure**

Run: `cd api && ./run.sh pytest ../agent/tests/test_diagram_tool.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent.tools.diagram'`.

- [ ] **Step 3: Create `agent/tools/diagram.py`:**

```python
"""Research-model diagram tool — promoted from the partner service (spec §3).

Why a tool and not a pipeline step: partner's _render_model_diagram lived
behind a hardcoded nvm node path (partner_report_service._NODE_BIN) whose
failure was swallowed, so every partner report silently shipped without its
diagram. As a tool bound to the agent, ALL THREE surfaces get it — chat
students want a research-model figure in their methodology too — and node is
discovered via shutil.which instead of a user-specific path.

The agent supplies constructs/paths from the M3 slice it already committed —
small structured data it legitimately knows, not model-supplied file bytes
(the banned defect class is models inventing state/bytes, not models
describing their own conceptual model).
"""
from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_MERMAID_DIR = Path(__file__).resolve().parents[2] / "engine" / "tools" / "mermaid_cli"


def _mermaid_source(constructs: list[dict], paths: list[dict]) -> str | None:
    """Pure mermaid-text builder, split out so the diagram grammar is testable
    without node/mmdc. Dangling paths (to undeclared constructs) are dropped —
    rendering model noise as edges would fabricate relationships."""
    labels = {
        str(c["id"]): str(c.get("label") or c["id"])
        for c in (constructs or []) if isinstance(c, dict) and c.get("id")
    }
    edges = [
        (str(p.get("from")), str(p.get("to")))
        for p in (paths or [])
        if isinstance(p, dict) and str(p.get("from")) in labels and str(p.get("to")) in labels
    ]
    if not labels or not edges:
        return None
    lines = ["flowchart LR"]
    for cid, label in labels.items():
        lines.append(f'  {cid}["{label.replace(chr(34), chr(39))}"]')
    for a, b in edges:
        lines.append(f"  {a} --> {b}")
    return "\n".join(lines)


@tool
def render_model_diagram(constructs: list[dict], paths: list[dict]) -> str:
    """Render the study's conceptual/structural research model as a PNG figure.

    Pass the constructs and directed paths from the project's M3 design —
    constructs as [{"id": "TR", "label": "Trust"}, ...] (short ascii ids) and
    paths as [{"from": "TR", "to": "PI"}, ...]. On success returns
    {"ok": true, "image_markdown": "![Research model](data:image/png;base64,…)"}.
    Embed `image_markdown` (with your own caption line) into the methodology
    prose you commit, so the figure ships inside the exported document.
    """
    mmd = _mermaid_source(constructs, paths)
    if mmd is None:
        return json.dumps({"error": "empty_model",
                           "hint": "provide at least two constructs and one path "
                                   "between declared construct ids"})
    mmdc = _MERMAID_DIR / "node_modules" / ".bin" / "mmdc"
    cfg = _MERMAID_DIR / "puppeteer.json"
    if not mmdc.exists():
        # Fail soft with a stable code: a missing renderer must degrade the
        # figure, never the turn (the swallowed-failure lesson, made loud).
        logger.warning("render_model_diagram: mmdc not installed at %s", mmdc)
        return json.dumps({"error": "mmdc_unavailable",
                           "hint": "mermaid CLI is not installed on this host; "
                                   "describe the model in prose or a ```mermaid``` block instead"})
    try:
        d = Path(tempfile.mkdtemp(prefix="model_"))
        mmd_path, png_path = d / "model.mmd", d / "model.png"
        mmd_path.write_text(mmd, encoding="utf-8")
        env = dict(os.environ)
        # Node discovery via shutil.which replaces the hardcoded _NODE_BIN —
        # the exact prod bug this promotion exists to kill.
        node = shutil.which("node")
        extra = ([str(Path(node).parent)] if node else []) + ["/opt/homebrew/bin"]
        env["PATH"] = ":".join(extra + [env.get("PATH", "")])
        subprocess.run(
            [str(mmdc), "-i", str(mmd_path), "-o", str(png_path),
             "-c", str(cfg), "-b", "white", "-w", "1100"],
            check=True, capture_output=True, timeout=120, env=env,
            cwd=str(_MERMAID_DIR),
        )
        if not png_path.exists():
            return json.dumps({"error": "render_failed", "hint": "mmdc produced no PNG"})
        b64 = base64.b64encode(png_path.read_bytes()).decode("ascii")
        # data URI so the image embeds in BOTH the WeasyPrint PDF and the
        # pandoc DOCX with no external file alive at render time.
        return json.dumps({"ok": True,
                           "image_markdown": f"![Research model](data:image/png;base64,{b64})"})
    except Exception as e:
        logger.exception("render_model_diagram failed")
        return json.dumps({"error": "render_failed", "detail": str(e)})
```

- [ ] **Step 4: Register in `build_agent`** — in `agent/runtime.py`, add to the imports block (after the `make_defense_tools` import at :162):

```python
from agent.tools.diagram import render_model_diagram  # research-model figure, all surfaces
```

and append to the `tools` list (after `*make_defense_tools(store),` at :537):

```python
        # Research-model diagram (promoted from partner, spec §3): renders the
        # M3 constructs/paths to an embeddable PNG so exported documents carry
        # the figure — the swallowed partner diagram bug, turned into a feature.
        render_model_diagram,
```

- [ ] **Step 5: Run tests**

Run: `cd api && ./run.sh pytest ../agent/tests/test_diagram_tool.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add agent/tools/diagram.py agent/runtime.py agent/tests/test_diagram_tool.py
git commit -m "feat(tools): render_model_diagram promoted from partner — shutil.which node, fail-soft"
```

---

### Task 7: Budget + Crossref fallback behind `research_scout`

**Files:**
- Modify: `agent/tools/research.py` (`research_scout` :20-76)
- Test: `api/tests/test_research_budget.py`

**Interfaces:**
- Consumes: `orchestrator.tools.m2_literature.scout_citations` (existing call, now under a timeout), `httpx`.
- Produces: `research_scout` — same tool signature and same `{"sources": [...], "count": N}` result shape; a fallback result additionally carries `"note": "budgeted fallback (Crossref)"`. New module-private `_crossref_fallback(query: str, n: int) -> list[dict]`. Timeout via env `DOTHESIS_SCOUT_TIMEOUT_S` (default `120` — generous enough for the documented 30-90s chat scout; partner's old 45s cap was tuned for a per-report budget the run-level wall clock now owns).

- [ ] **Step 1: Write the failing tests** — `api/tests/test_research_budget.py`:

```python
"""_budgeted_scout's discipline (wall-clock cap + Crossref fallback) moved
behind research_scout (spec §3) — the same tool now protects all three
surfaces from a hung/rate-limited deep scout.

NOTE: scout_citations is a pydantic StructuredTool — `.func` is not a settable
field (same trap the compose_export tests document for compose_chapter), so we
swap the WHOLE object in the m2 namespace; research_scout resolves it by a
call-time `from ... import scout_citations`, which reads the patched binding."""
import json
from types import SimpleNamespace

import agent.tools.research as research


class _Resp:
    def json(self):
        return {"message": {"items": [{
            "title": ["Livestream commerce and purchase intention"],
            "author": [{"family": "Sun"}],
            "issued": {"date-parts": [[2019]]},
            "container-title": ["ECRA"],
            "DOI": "10.1/x", "URL": "https://doi.org/10.1/x",
        }]}}


def test_scout_failure_falls_back_to_crossref(monkeypatch):
    import orchestrator.tools.m2_literature as m2

    def boom(*a, **k):
        raise RuntimeError("rate limited")

    monkeypatch.setattr(m2, "scout_citations", SimpleNamespace(func=boom))
    monkeypatch.setattr(research.httpx, "get", lambda *a, **k: _Resp())
    out = json.loads(research.research_scout.func("livestream commerce"))
    assert out["count"] == 1
    assert out["sources"][0]["doi"] == "10.1/x"
    assert out["note"] == "budgeted fallback (Crossref)"


def test_scout_timeout_falls_back(monkeypatch):
    import time
    import orchestrator.tools.m2_literature as m2

    def hang(*a, **k):
        time.sleep(3)
        return []

    monkeypatch.setenv("DOTHESIS_SCOUT_TIMEOUT_S", "1")
    monkeypatch.setattr(m2, "scout_citations", SimpleNamespace(func=hang))
    monkeypatch.setattr(research.httpx, "get", lambda *a, **k: _Resp())
    out = json.loads(research.research_scout.func("anything"))
    assert out["note"] == "budgeted fallback (Crossref)"


def test_scout_success_is_unchanged(monkeypatch):
    import orchestrator.tools.m2_literature as m2
    monkeypatch.setattr(
        m2, "scout_citations",
        SimpleNamespace(func=lambda *a, **k: [{"title": "P", "doi": "10.2/y"}]))
    out = json.loads(research.research_scout.func("topic"))
    assert out["count"] == 1 and "note" not in out
```

- [ ] **Step 2: Run, verify failure**

Run: `cd api && ./run.sh pytest tests/test_research_budget.py -q`
Expected: FAIL — `AttributeError: module 'agent.tools.research' has no attribute 'httpx'` (and no `note` key).

- [ ] **Step 3: Implement in `agent/tools/research.py`.** Add to the module imports:

```python
import os

import httpx  # module-level so tests can monkeypatch research.httpx
```

Add before `research_scout`:

```python
# Wall-clock discipline promoted from partner's _budgeted_scout (spec §3): the
# deep scout can run minutes / rate-limit into a hang, and a hung tool is the
# stall mode headless cannot distinguish from thinking. Cap it, fall back to a
# direct Crossref query so a turn never hangs and never ships zero references.
# Default 120s (not partner's old 45s): chat's scout legitimately runs 30-90s,
# and the run-level wall clock now owns the per-report budget.
_SCOUT_FALLBACK_N = 8


def _crossref_fallback(query: str, n: int = _SCOUT_FALLBACK_N) -> list[dict]:
    """Direct Crossref query — real peer-reviewed sources + DOIs in ~2s.
    Ported from partner's _literature_search minus its LLM query-translation
    hop (that inline prompt is deleted with the partner pipeline); Crossref
    gets the raw topic, which is good enough for a degraded-mode fetch."""
    try:
        r = httpx.get(
            "https://api.crossref.org/works",
            params={
                "query.bibliographic": (query or "")[:200],
                "rows": n,
                "select": "title,author,issued,DOI,container-title,URL",
                "filter": "type:journal-article,has-abstract:true",
                "sort": "relevance",
            },
            timeout=20,
            headers={"User-Agent": "DoThesis/1.0 (mailto:cao.nv17@gmail.com)"},
        )
        items = r.json().get("message", {}).get("items", [])
    except Exception:
        logger.exception("crossref fallback failed (returning no sources)")
        return []
    refs: list[dict] = []
    for it in items:
        title = (it.get("title") or [""])[0].strip()
        if not title:
            continue
        parts = (it.get("issued", {}).get("date-parts") or [[None]])
        refs.append({
            "title": title,
            "authors": [str(a.get("family")).strip() for a in it.get("author", []) if a.get("family")],
            "year": parts[0][0] if parts and parts[0] else None,
            "venue": (it.get("container-title") or [None])[0],
            "doi": it.get("DOI"),
            "url": it.get("URL"),
            "verified": bool(it.get("DOI")),
        })
    return refs[:n]
```

Replace the try-block inside `research_scout` (:50-60) with:

```python
    import concurrent.futures as _fut

    timeout_s = int(os.getenv("DOTHESIS_SCOUT_TIMEOUT_S", "120"))
    citations = None
    # NOTE: do NOT use `with ThreadPoolExecutor(...)`. Its __exit__ calls
    # shutdown(wait=True), which BLOCKS until the (possibly runaway) scout
    # thread finishes — a result(timeout=...) that fires would still wait
    # minutes for the hung thread, defeating the cap entirely (the lesson
    # partner's _budgeted_scout learned on a Semantic Scholar 429 storm).
    ex = _fut.ThreadPoolExecutor(max_workers=1)
    try:
        from orchestrator.tools.m2_literature import scout_citations
        future = ex.submit(scout_citations.func, composed, min_n=min_sources)
        citations = future.result(timeout=timeout_s)
    except Exception:
        # TimeoutError, engine failure, rate limit — all degrade to Crossref.
        logger.exception("research_scout: deep scout failed/timed out; Crossref fallback")
    finally:
        ex.shutdown(wait=False, cancel_futures=True)

    if not citations:
        refs = _crossref_fallback(composed)
        return json.dumps({
            "sources": refs, "count": len(refs),
            # Honesty marker: the agent should tell the user this was the
            # light fallback, not the deep validated scout.
            "note": "budgeted fallback (Crossref)",
        }, ensure_ascii=False)
```

Keep the existing normalize-and-return block for the success path exactly as-is (:62-76).

- [ ] **Step 4: Run tests**

Run: `cd api && ./run.sh pytest tests/test_research_budget.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add agent/tools/research.py api/tests/test_research_budget.py
git commit -m "feat(research): wall-clock cap + Crossref fallback behind research_scout"
```

---

### Task 8: `merge_conclusion` argument on `compose_sections`

**Files:**
- Modify: `orchestrator/tools/compose_export.py` (`compose_sections` :33-40 signature + body head)
- Test: `api/tests/test_compose_export.py` (append)

**Interfaces:**
- Produces: `compose_sections(context_store, chapters, language, references=None, progress=None, title_overrides=None, merge_conclusion=False)` — with `merge_conclusion=True`, `conclusion` is dropped, `discussion` is kept/added and retitled "Chương 5 — Kết luận" / "Chapter 5 — Conclusion". Existing callers are unaffected (default False).

- [ ] **Step 1: Write the failing test** — append to `api/tests/test_compose_export.py`:

```python
# --- headless convergence: Discussion+Conclusion merge is an export argument -
def test_merge_conclusion_relabels_discussion(monkeypatch):
    seen = []

    class _FakeTool:
        def invoke(self, payload):
            seen.append(payload["chapter_name"])
            return {"prose": f"prose for {payload['chapter_name']}"}

    monkeypatch.setattr(ce, "compose_chapter", _FakeTool())
    sections = ce.compose_sections(
        {"m1_topic": {}, "m4_analysis": {}},
        ["intro", "results", "discussion", "conclusion"],
        "vi", merge_conclusion=True,
    )
    assert "conclusion" not in seen            # dropped, not composed twice
    assert seen[-1] == "discussion"
    assert sections[-1]["title"] == "Chương 5 — Kết luận"
```

- [ ] **Step 2: Run, verify failure**

Run: `cd api && ./run.sh pytest tests/test_compose_export.py -q`
Expected: FAIL — `TypeError: compose_sections() got an unexpected keyword argument 'merge_conclusion'`.

- [ ] **Step 3: Implement.** Change the signature (compose_export.py:33-40) to add `merge_conclusion: bool = False`, and insert at the top of the body (before the `m1 = ...` line):

```python
    if merge_conclusion and "conclusion" in set(chapters):
        # Presentation choice promoted from the partner pipeline (spec §3):
        # standard VN thesis structure has ONE concluding chapter ("Chương 5 —
        # Kết luận"), not Discussion + Conclusion. The discussion composer
        # already emits the full conclusion structure (summary → contributions
        # → limitations → future work), so drop `conclusion` and relabel
        # `discussion` — an export ARGUMENT, not a pipeline fork.
        chapters = [c for c in chapters if c != "conclusion"]
        if "discussion" not in chapters:
            chapters = [*chapters, "discussion"]
        combined = ("Chương 5 — Kết luận" if str(language).lower().startswith("vi")
                    else "Chapter 5 — Conclusion")
        title_overrides = {**(title_overrides or {}), "discussion": combined}
```

- [ ] **Step 4: Run the whole file (regressions included)**

Run: `cd api && ./run.sh pytest tests/test_compose_export.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/tools/compose_export.py api/tests/test_compose_export.py
git commit -m "feat(compose): merge_conclusion export argument (was a partner pipeline fork)"
```

---

### Task 9: `jobs.partner_token` column + migration

**Files:**
- Modify: `api/app/models.py` (Job class, after `langgraph_thread_id` at :106)
- Create: `api/migrations/versions/20260715_partner_token.py`
- Test: covered by Task 11's router tests; a minimal model test here.

**Interfaces:**
- Produces: `Job.partner_token: str | None` — the partner's opaque `progress_token`, indexed, so the progress endpoint can find the Job (replaces the in-memory `_PROGRESS` dict and its single-process constraint).

- [ ] **Step 1: Write the failing test** — `api/tests/test_job_partner_token.py`:

```python
"""jobs.partner_token maps the partner's opaque progress_token to the Job row —
the durable, multi-process replacement for the deleted in-memory _PROGRESS dict."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Job


def test_partner_token_round_trips():
    with Session(get_engine()) as s:
        j = Job(paper_id=None, project_id=uuid.uuid4(), mode="partner",
                status="queued", partner_token="tok-123")
        s.add(j)
        s.commit()
        got = s.scalar(select(Job).where(Job.partner_token == "tok-123"))
        assert got is not None and got.id == j.id
```

- [ ] **Step 2: Run, verify failure**

Run: `cd api && ./run.sh pytest tests/test_job_partner_token.py -q`
Expected: FAIL — `TypeError: 'partner_token' is an invalid keyword argument for Job`.

- [ ] **Step 3: Add the column to `Job`** (models.py, after `langgraph_thread_id` :106):

```python
    # Partner runs: the caller-supplied opaque progress_token, so the
    # /partner/report/progress poll can find this Job. Durable + multi-process,
    # unlike the in-memory _PROGRESS dict it replaces (convergence spec §3).
    partner_token: Mapped[str | None] = mapped_column(Text, index=True)
```

Create `api/migrations/versions/20260715_partner_token.py` (head verified: `20260715_paperupmime01`):

```python
"""jobs.partner_token — durable partner progress-token -> Job mapping.

The partner report path becomes an ordinary Job (headless convergence spec §3);
its progress poll needs token -> job resolution that survives restarts and
multiple API processes, which the old in-memory _PROGRESS dict did not.

Revision ID: 20260715_partnertok01
Revises: 20260715_paperupmime01
Create Date: 2026-07-15
"""
from alembic import op
import sqlalchemy as sa

revision = "20260715_partnertok01"
down_revision = "20260715_paperupmime01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("partner_token", sa.Text(), nullable=True))
    op.create_index("ix_jobs_partner_token", "jobs", ["partner_token"])


def downgrade() -> None:
    op.drop_index("ix_jobs_partner_token", table_name="jobs")
    op.drop_column("jobs", "partner_token")
```

- [ ] **Step 4: Run test (conftest uses `Base.metadata.create_all`, so the model change is enough for tests; the migration is for real deploys)**

Run: `cd api && ./run.sh pytest tests/test_job_partner_token.py tests/test_models.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/app/models.py api/migrations/versions/20260715_partner_token.py api/tests/test_job_partner_token.py
git commit -m "feat(db): jobs.partner_token for durable partner progress polling"
```

---

### Task 10: Partner-run module + headless subprocess entry + spawner

**Files:**
- Create: `api/app/partner_run.py`
- Create: `api/app/headless_entry.py`
- Modify: `api/app/job_runner.py` (append `spawn_headless_run` after `spawn_orchestrator_run` :380-440)
- Modify: `agent/state.py` (`SLICE_OWNERSHIP["M1"]` gains the topic-framing seed keys)
- Test: `api/tests/test_partner_run.py`

**Interfaces:**
- Consumes: `DbProjectStateStore` (api/app/agent_state.py:39), `_workspace_dir` (api/app/routers/chat_v3.py:102), `build_agent`/`run_headless`/`RunProfile` (Tasks 4-5), `compose_sections(merge_conclusion=...)` (Task 8), `run_export` (orchestrator/tools/m5_writing.py:1481), `M5_CHAPTER_ORDER` (:983), `JsonlAppender` (engine/job_io.py:10), `get_engine` (app/db.py:17).
- Produces (`api/app/partner_run.py`):
  - `ReportError(code, message)` (moved verbatim from `partner_report_service.py:74-80`)
  - `_extract_text(file_bytes, filename) -> tuple[str, int]` and `pdf_looks_like_analysis(text) -> bool` (moved verbatim from `partner_report_service.py:441-496`, plus the `_M4_DATA_SIGNALS` tuple; `_extract_text`'s final line now calls `extract_pdf_text` imported `from .pdf_extract import extract_pdf_text` — the Task 2 shim)
  - `ANALYSIS_CHAPTERS = ["intro", "results", "discussion", "conclusion"]`
  - `resolve_chapters(depth: str, chapters: list[str] | None) -> list[str]` (raises `ReportError` bad_depth/bad_chapters)
  - `ensure_partner_user(db: Session) -> User`
  - `seed_partner_store(store, *, analysis_text, m1=None, m2=None, m3=None, title=None, notes=None, language="en") -> None`
  - `run_partner_export(store, project_id, params: dict) -> dict` returning `{"sections": [...], "chapters": [...], "artifact_keys": {"pdf": key, "docx": key}}`
  - `_presign(s3, s3_key, *, expires_in=3600) -> str` (moved from `partner_report_service.py:100-106`)
- Produces (`api/app/headless_entry.py`): `python -m app.headless_entry --project-id U --job-id U --workdir P --params-json P`, `KICKOFF_PROMPT`, writes `events.jsonl` (`phase_progress`/`activity`/`job_done`/`error`).
- Produces (`api/app/job_runner.py`): `spawn_headless_run(db: Session, run: Job, params: dict) -> None`.

- [ ] **Step 1: Write the failing tests** — `api/tests/test_partner_run.py`:

```python
"""Partner-as-headless-client plumbing (spec §3): system user, store seeding
through commit_slice (the ONLY write path), and the post-run export step."""
import uuid

import pytest
from sqlalchemy.orm import Session

from app.agent_state import DbProjectStateStore
from app.db import get_engine
from app.models import Project
from app.partner_run import (
    ReportError,
    ensure_partner_user,
    resolve_chapters,
    run_partner_export,
    seed_partner_store,
)


def _partner_project(tmp_path):
    engine = get_engine()
    with Session(engine) as s:
        u = ensure_partner_user(s)
        p = Project(user_id=u.id, name="Partner report", language="vi")
        s.add(p)
        s.commit()
        pid = p.id
    return DbProjectStateStore(engine, pid, tmp_path), pid


def test_ensure_partner_user_is_idempotent():
    with Session(get_engine()) as s:
        a = ensure_partner_user(s)
        b = ensure_partner_user(s)
        assert a.id == b.id and a.credit == 0


def test_resolve_chapters():
    assert resolve_chapters("analysis_report", None) == ["intro", "results",
                                                         "discussion", "conclusion"]
    assert resolve_chapters("full_thesis", None)[0] == "intro"
    assert resolve_chapters("ignored", ["results", "bogus"]) == ["results"]
    with pytest.raises(ReportError):
        resolve_chapters("bad", None)
    with pytest.raises(ReportError):
        resolve_chapters("analysis_report", ["bogus_only"])


def test_seed_lands_in_owned_slices(tmp_path):
    store, pid = _partner_project(tmp_path)
    seed_partner_store(
        store,
        analysis_text="Cronbach alpha .87, AVE 0.62",
        m1={"research_title": "Given title", "objectives": "Aim",
            "not_a_real_key": "dropped"},
        m3={"conceptual_model": "TR -> PI"},
        notes="steer this way", language="vi",
    )
    st = DbProjectStateStore(get_engine(), pid, tmp_path).load()  # fresh DB read
    cs = st["contextStore"]
    assert cs["research_title"] == "Given title"
    assert cs["objectives"] == "Aim"          # M1 framing key now owned + persisted
    assert cs["language"] == "vi"
    assert cs["user_context"] == "steer this way"
    assert cs["conceptual_model"] == "TR -> PI"
    assert cs["analysis_results"].startswith("Cronbach")
    assert "not_a_real_key" not in cs          # unowned keys are dropped, not smuggled
    # Seeding must not trip needs_review anywhere (M1->M4 order = downstream
    # of every commit is still locked).
    assert "needs_review" not in st["status"].values()


def test_run_partner_export_composes_and_persists(tmp_path, monkeypatch):
    store, pid = _partner_project(tmp_path)
    seed_partner_store(store, analysis_text="AVE 0.62", language="en")

    import app.partner_run as pr
    monkeypatch.setattr(pr, "compose_sections",
                        lambda *a, **k: [{"title": "Chapter 5 — Conclusion",
                                          "prose": "p"}])
    monkeypatch.setattr(pr, "run_export",
                        lambda *a, **k: [{"kind": "docx", "s3_key": "k.docx"},
                                         {"kind": "pdf", "s3_key": "k.pdf"}])
    out = run_partner_export(store, pid, {"depth": "analysis_report",
                                          "language": "en"})
    assert out["artifact_keys"] == {"docx": "k.docx", "pdf": "k.pdf"}
    assert out["sections"] == ["Chapter 5 — Conclusion"]
    # artifacts persisted to the shared exports rows (what the presign reads)
    from app.models import Export
    with Session(get_engine()) as s:
        rows = s.query(Export).filter_by(project_id=pid).all()
        assert {r.s3_key for r in rows} == {"k.docx", "k.pdf"}
        assert all(r.scope == "partner" for r in rows)
```

- [ ] **Step 2: Run, verify failure**

Run: `cd api && ./run.sh pytest tests/test_partner_run.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.partner_run'`.

- [ ] **Step 3: Extend `SLICE_OWNERSHIP["M1"]`** in `agent/state.py` (the dict updated in Task 4):

```python
    # Topic-framing keys added for partner seeding + richer M1 commits: the
    # chapter composers read language/field/objectives/… from the m1_topic
    # column, and DbProjectStateStore only persists OWNED keys — without
    # ownership a partner-supplied framing would silently die before prod
    # (project_db_store_persistence_gap). Same mechanism as field_it_* in M4.
    "M1": ["research_title", "research_questions", "decisions",
           "language", "field", "research_type", "objectives",
           "target_population", "scope", "user_context"],
```

- [ ] **Step 4: Create `api/app/partner_run.py`:**

```python
"""Partner report = a headless client of the deep agent (convergence spec §3).

The old partner_report_service was a THIRD generation engine: inline prompts,
a private compose loop, zero tools/skills/state. This module replaces it with
the same brain every surface runs: create a system-owned project row, seed the
store through commit_slice (the ONLY write path), run the deep agent headless
in a Job subprocess, compose the requested report shape through the SHARED
compose/export path, and presign from the shared exports rows.

What partner gains the day this lands: all ~20 tools, all 8 skills, threshold
checks, questionnaire audit, rubric review, preflight — everything it lacked.
"""
from __future__ import annotations

import logging
import os
import re  # used by the moved pdf_looks_like_analysis

from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.state import SLICE_OWNERSHIP
# Module-level (not lazy) so tests can monkeypatch partner_run.compose_sections /
# partner_run.run_export; m5_writing defers its own heavy LLM deps internally.
from orchestrator.tools.compose_export import compose_sections
from orchestrator.tools.m5_writing import M5_CHAPTER_ORDER, run_export

from .models import User
from .pdf_extract import extract_pdf_text

logger = logging.getLogger(__name__)

# Subset composed for the lighter "analysis_report" depth (single copy now —
# the old _CHAPTER_ORDER clone is gone; the canonical order is M5_CHAPTER_ORDER).
ANALYSIS_CHAPTERS = ["intro", "results", "discussion", "conclusion"]

PARTNER_USER_EMAIL = "partner-system@dothesis.internal"


class ReportError(Exception):
    """Raised with a stable `code` the router maps to an HTTP response."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def resolve_chapters(depth: str, chapters: list[str] | None) -> list[str]:
    """Chapter selection precedence unchanged from the old service: explicit
    `chapters` subset wins over `depth`; unknown keys are ignored; an
    empty-after-filter list and an unknown depth are clean 422 codes."""
    if chapters:
        keys = [c for c in chapters if c in set(M5_CHAPTER_ORDER)]
        if not keys:
            raise ReportError("bad_chapters",
                              f"chapters must be a subset of {M5_CHAPTER_ORDER}")
        return keys
    if depth == "full_thesis":
        return list(M5_CHAPTER_ORDER)
    if depth == "analysis_report":
        return list(ANALYSIS_CHAPTERS)
    raise ReportError("bad_depth",
                      "depth must be one of ['analysis_report', 'full_thesis']")


def ensure_partner_user(db: Session) -> User:
    """Find-or-create the system user that owns partner projects.

    Partner runs have no end-user relationship (the partner owns billing), but
    Project.user_id is NOT NULL and the whole app authorizes through ownership
    — one well-known system row keeps every query intact, and its permanent
    0-credit balance makes job_runner._charge_auto_run a guaranteed no-op
    (charge = min(cost, credit or 0) = 0)."""
    u = db.scalar(select(User).where(User.email == PARTNER_USER_EMAIL))
    if u is None:
        u = User(email=PARTNER_USER_EMAIL, username="partner-system",
                 password_hash="!disabled", email_verified=True, credit=0)
        db.add(u)
        db.flush()
    return u


def seed_partner_store(
    store,
    *,
    analysis_text: str,
    m1: dict | None = None,
    m2: dict | None = None,
    m3: dict | None = None,
    title: str | None = None,
    notes: str | None = None,
    language: str = "en",
) -> None:
    """Seed the project store from the partner payload — through commit_slice
    only, filtered to OWNED keys (an unowned key would either raise or, worse,
    silently never reach prod rows). Caller-provided modules are used verbatim;
    missing ones stay empty for the agent to reconstruct (backfill tool).

    Seed order M1 -> M4 matters: commit_slice flags STARTED downstream modules
    needs_review, and seeding forward means every commit's downstream is still
    locked — no spurious review flags on a brand-new project."""
    m1 = dict(m1 or {})
    if (title or "").strip():
        # A caller-typed title always wins over anything inferred later.
        m1["research_title"] = title.strip()
    m1.setdefault("language", language)
    if (notes or "").strip():
        m1.setdefault("user_context", notes.strip())
    writes1 = {k: v for k, v in m1.items() if k in set(SLICE_OWNERSHIP["M1"])}
    if writes1:
        store.commit_slice("M1", writes1, "partner payload: topic framing seed")
    if m2:
        writes2 = {k: v for k, v in m2.items() if k in set(SLICE_OWNERSHIP["M2"])}
        if writes2:
            store.commit_slice("M2", writes2, "partner payload: literature seed")
    if m3:
        writes3 = {k: v for k, v in m3.items() if k in set(SLICE_OWNERSHIP["M3"])}
        if writes3:
            store.commit_slice("M3", writes3, "partner payload: design seed")
    store.commit_slice("M4", {"analysis_results": analysis_text},
                       "partner payload: uploaded analysis output")


def run_partner_export(store, project_id, params: dict) -> dict:
    """Compose the REQUESTED report shape from the finished run's store and
    export through the shared renderer.

    The run itself already produced a full-thesis export via the M5 done-hook
    (DbProjectStateStore._auto_export_m5) — that stays in the project's Exports
    as a bonus. This renders the partner's requested subset/merged shape:
    chapters/depth are presentation choices, not a pipeline fork (spec §3)."""
    chapters = resolve_chapters(params.get("depth") or "analysis_report",
                                params.get("chapters"))
    language = params.get("language") or "en"
    full_cs = store.load_full_context_store()
    references = (full_cs.get("m2_literature") or {}).get("literature_sources") or None
    sections = compose_sections(full_cs, chapters, language,
                                references=references, merge_conclusion=True)
    if not sections:
        raise ReportError("compose_failed", "the writing engine produced no sections")
    artifacts = run_export(sections, str(project_id),
                           references=references, language=language)
    store.persist_export_artifacts(artifacts, scope="partner")
    return {
        "sections": [s["title"] for s in sections],
        "chapters": chapters,
        "artifact_keys": {a.get("kind"): a.get("s3_key")
                          for a in artifacts if a.get("s3_key")},
    }


def _presign(s3, s3_key: str, *, expires_in: int = 3600) -> str:
    """Same raw-key presign convention as the exports router — M5 export
    uploads with Bucket=S3_BUCKET and NO settings prefix (see
    orchestrator/tools/m5_writing._upload_to_s3)."""
    bucket = os.environ.get("S3_BUCKET") or os.environ["AWS_S3_BUCKET"]
    return s3.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": s3_key},
        ExpiresIn=expires_in,
    )
```

Then append, moved **verbatim** from `api/app/partner_report_service.py`, the ingest helpers: the `_M4_DATA_SIGNALS` tuple (:471-481), `pdf_looks_like_analysis` (:484-496), and `_extract_text` (:441-465) — no edits beyond what already imports (`extract_pdf_text` is imported at the top of this file).

- [ ] **Step 5: Create `api/app/headless_entry.py`:**

```python
"""Headless-run subprocess entrypoint — the auto-mode pattern for the deep agent.

    python -m app.headless_entry --project-id <uuid> --job-id <uuid> \
        --workdir <path> --params-json <path>

Mirrors orchestrator/__main__.py: stream events to <workdir>/events.jsonl so
the API's existing job_runner._monitor tails them and updates Job rows — this
process NEVER writes Job rows itself (the API is the single Job writer).
Project state is written only through DbProjectStateStore.commit_slice by the
agent's own tools; a crash or budget failure keeps everything committed so far.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import traceback
from pathlib import Path
from uuid import UUID

logger = logging.getLogger("headless_entry")

# The runner's only prompt — a USER-turn instruction, not a new system prompt:
# the brain's behavior still comes from SYSTEM_PROMPT + skills (spec §1 "no new
# prompts" for the spine; the student's opening message is the one thing a
# headless run must say itself). The per-turn [NEXT] header steers direction.
KICKOFF_PROMPT = (
    "Generate the complete work for this project from its current state. "
    "Work through every module in roadmap order without waiting for me; "
    "reconstruct missing upstream modules from what already exists (backfill) "
    "instead of asking me for inputs."
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m app.headless_entry")
    p.add_argument("--project-id", required=True)
    p.add_argument("--job-id", required=True)
    p.add_argument("--workdir", required=True)
    p.add_argument("--params-json", required=True)
    return p.parse_args()


def _make_progress_hook(appender, store):
    """Per-turn progress beats over the events.jsonl → JobEvent → SSE pipe —
    the durable replacement for the deleted in-memory _PROGRESS dict. Module
    granularity: `done`/`total` count finished modules, `phase` is the focus."""
    from agent.state import MODULES

    def on_event(ev: dict) -> None:
        try:
            if ev.get("type") == "tool_start":
                appender.write({"type": "activity", "agent": "headless",
                                "text": f"tool: {ev.get('name')}"})
            elif ev.get("type") == "done":  # one per turn (stream_turn's last event)
                state = store.load()
                done_n = sum(1 for m in MODULES if state["status"].get(m) == "done")
                appender.write({"type": "phase_progress",
                                "phase": state.get("focus") or "M1",
                                "progress": done_n / len(MODULES),
                                "total": len(MODULES), "done": done_n})
        except Exception:  # noqa: BLE001 — progress beats must never kill the run
            pass

    return on_event


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = _parse_args()
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    # engine/ is not an installed package — same repo-root sys.path trick as
    # orchestrator/__main__.py (agent/app/orchestrator are editable-installed).
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from engine.job_io import JsonlAppender

    appender = JsonlAppender(workdir / "events.jsonl")
    try:
        params = json.loads(Path(args.params_json).read_text("utf-8"))
        project_id = UUID(args.project_id)

        from langgraph.checkpoint.memory import InMemorySaver

        from agent.headless import RunProfile, run_headless
        from agent.runtime import build_agent
        from app.agent_state import DbProjectStateStore
        from app.db import get_engine
        from app.routers.chat_v3 import _workspace_dir

        workspace = _workspace_dir(project_id)  # same dir chat would use — later chat handoff sees the files
        store = DbProjectStateStore(get_engine(), project_id, workspace)
        # InMemorySaver: the conversation only needs to outlive THIS run —
        # durable progress is whatever commit_slice wrote, and a failed run
        # "resumes" by re-running against that state, not by replaying chat.
        agent = build_agent(workspace, checkpointer=InMemorySaver(), store=store)
        profile = RunProfile(
            interactive=False,
            max_turns=int(params.get("max_turns") or 80),
            wall_clock_s=int(params.get("wall_clock_s") or 1800),
        )
        result = asyncio.run(run_headless(
            agent, store, profile,
            thread_id=f"headless:{args.job_id}",
            initial_prompt=KICKOFF_PROMPT,
            on_event=_make_progress_hook(appender, store),
        ))
        if result.status != "done":
            # Budget exhaustion / stalls = a FAILED run with partial state
            # preserved — never a silent success (spec §1). The store keeps
            # everything committed; the partner gets a clean error, not a
            # hollow report.
            appender.write({"type": "error",
                            "text": f"headless run failed: {result.reason} "
                                    f"after {result.turns} turns"})
            return 1

        from app.partner_run import run_partner_export
        out = run_partner_export(store, project_id, params)
        appender.write({"type": "job_done", **out})
        return 0
    except Exception:
        logger.exception("headless run crashed")
        appender.write({"type": "error", "text": "headless run crashed",
                        "traceback": traceback.format_exc()})
        return 1
    finally:
        appender.close()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Append `spawn_headless_run` to `api/app/job_runner.py`** (after `spawn_orchestrator_run`):

```python
def spawn_headless_run(db: Session, run: Job, params: dict) -> None:
    """Spawn `python -m app.headless_entry` — the deep-agent twin of
    spawn_orchestrator_run. Reuses the events.jsonl contract so the existing
    _monitor works unchanged, which is exactly what makes C (auto-mode
    migration) a swap later: point THIS spawner at auto briefs instead of
    `python -m orchestrator --auto-draft`."""
    settings = get_settings()
    workdir = settings.job_workdir_root / str(run.id)
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "params.json").write_text(json.dumps(params), encoding="utf-8")
    (workdir / "events.jsonl").touch()

    env = os.environ.copy()
    env["DATABASE_URL"] = os.environ.get("DATABASE_URL", "")
    env["AWS_REGION"] = settings.aws_region
    env["S3_BUCKET"] = settings.s3_bucket
    env["S3_PREFIX"] = settings.s3_prefix
    env["AWS_ACCESS_KEY"] = settings.aws_access_key
    env["AWS_SECRET_KEY"] = settings.aws_secret_key
    if settings.gemini_api_key:
        env["GEMINI_API_KEY"] = settings.gemini_api_key
        env["GOOGLE_API_KEY"] = settings.gemini_api_key
    if settings.openai_api_key:
        env["OPENAI_API_KEY"] = settings.openai_api_key
    if settings.anthropic_api_key:
        env["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

    cmd = [sys.executable, "-m", "app.headless_entry",
           "--project-id", str(run.project_id),
           "--job-id", str(run.id),
           "--workdir", str(workdir),
           "--params-json", str(workdir / "params.json")]
    proc = subprocess.Popen(
        cmd,
        # repo root: `app`/`agent`/`orchestrator` resolve via editable installs,
        # `engine` via python -m's cwd-on-sys.path (same as the orchestrator spawn).
        cwd=str(Path(__file__).resolve().parents[2]),
        env=env,
    )
    run.pid = proc.pid
    run.workdir = str(workdir)
    run.status = "running"
    run.started_at = datetime.now(timezone.utc)
    db.commit()

    start_monitor(run.id)
```

- [ ] **Step 7: Run the tests**

Run: `cd api && ./run.sh pytest tests/test_partner_run.py tests/test_agent_state.py -q`
Expected: PASS.

- [ ] **Step 8: Sanity-check the entrypoint parses** (no run — DB/model not needed to import):

Run: `cd api && ./run.sh python -c "import app.headless_entry, app.partner_run; print('imports ok')"`
Expected: `imports ok`.

- [ ] **Step 9: Commit**

```bash
git add api/app/partner_run.py api/app/headless_entry.py api/app/job_runner.py agent/state.py api/tests/test_partner_run.py
git commit -m "feat(partner): headless client plumbing — system user, seeding, subprocess entry, spawner"
```

---

### Task 11: Partner router rewrite + service deletion

**Files:**
- Rewrite: `api/app/routers/partner_report.py`
- Modify: `api/app/import_work.py` (absorb `_infer_topic`/`_infer_model`)
- Delete: `api/app/partner_report_service.py`
- Rewrite: `api/tests/test_partner_report.py`

**Interfaces:**
- Consumes: everything from Task 9/10, `job_runner.spawn_headless_run`, `s3_from_env` (api/app/routers/uploads.py:62), `db_session` (app/db.py:38), `JobEvent`, `Job`.
- Produces: `POST /partner/report` (multipart contract unchanged: `file`, `depth`, `chapters`, `progress_token`, `title`, `notes`, `language`, `m1`, `m2`, `m3`, header `X-Partner-Token`; response `PartnerReportOut` unchanged) and `POST /partner/report/progress` (reads the Job). Both POST — no GET.

- [ ] **Step 1: Rewrite the tests** — `api/tests/test_partner_report.py` (full replacement):

```python
"""Partner endpoint = create project -> seed -> spawn headless Job -> await ->
presign (spec §3). Heavy pieces (extraction, the subprocess itself, S3) are
monkeypatched; project/job/event rows are real (conftest Postgres)."""
from __future__ import annotations

import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import job_runner
from app.db import get_engine
from app.models import Job, JobEvent, Project
from app.routers import partner_report as router_mod

TOKEN = "test-partner-secret"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("PARTNER_API_TOKEN", TOKEN)
    monkeypatch.setenv("JOB_WORKDIR_ROOT", str(tmp_path))  # workspace mirror target
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    from app.settings import reset_settings
    reset_settings()
    app = FastAPI()
    app.include_router(router_mod.router, prefix="/api/v1")
    return TestClient(app)


def _post(client, *, token=TOKEN, depth="analysis_report", body=b"%PDF-1.4 fake",
          progress_token=None):
    headers = {"X-Partner-Token": token} if token is not None else {}
    data = {"depth": depth, "title": "My Study", "language": "en"}
    if progress_token:
        data["progress_token"] = progress_token
    return client.post(
        "/api/v1/partner/report",
        headers=headers,
        files={"file": ("analysis.pdf", io.BytesIO(body), "application/pdf")},
        data=data,
    )


def test_missing_token_is_401(client):
    assert _post(client, token=None).status_code == 401


def test_wrong_token_is_401(client):
    assert _post(client, token="nope").status_code == 401


def test_unextractable_file_is_422(client, monkeypatch):
    monkeypatch.setattr(router_mod.prun, "_extract_text", lambda b, f: ("", 0))
    r = _post(client)
    assert r.status_code == 422
    assert r.json()["detail"]["error"]["code"] == "no_extractable_text"


def test_non_analysis_pdf_is_422(client, monkeypatch):
    monkeypatch.setattr(router_mod.prun, "_extract_text",
                        lambda b, f: ("just an essay, no statistics", 2))
    r = _post(client)  # analysis_report includes "results" -> sniff applies
    assert r.status_code == 422
    assert r.json()["detail"]["error"]["code"] == "insufficient_m4_data"


def test_bad_depth_is_422(client, monkeypatch):
    monkeypatch.setattr(router_mod.prun, "_extract_text",
                        lambda b, f: ("cronbach 0.9 ave 0.6 " + "0.1 " * 10, 2))
    r = _post(client, depth="bogus")
    assert r.status_code == 422
    assert r.json()["detail"]["error"]["code"] == "bad_depth"


class _FakeS3:
    def generate_presigned_url(self, op, Params=None, ExpiresIn=None):
        return f"https://signed.example/{Params['Key']}"


def _fake_spawn(db: Session, run: Job, params: dict) -> None:
    # Stand-in for the subprocess: mark done + write the job_done event the
    # real headless_entry would emit.
    run.status = "done"
    run.workdir = "/tmp/x"
    db.add(JobEvent(job_id=run.id, type="job_done",
                    meta_json={"sections": ["Chapter 5 — Conclusion"],
                               "chapters": ["intro", "results", "discussion"],
                               "artifact_keys": {"pdf": "p/k.pdf",
                                                 "docx": "p/k.docx"}}))
    db.commit()


def test_happy_path_creates_project_job_and_presigns(client, monkeypatch):
    monkeypatch.setattr(router_mod.prun, "_extract_text",
                        lambda b, f: ("cronbach 0.9 ave 0.6 " + "0.1 " * 10, 3))
    monkeypatch.setattr(job_runner, "spawn_headless_run", _fake_spawn)
    monkeypatch.setattr(router_mod, "s3_from_env", lambda: _FakeS3())

    r = _post(client, progress_token="ptok-1")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pdf_url"].endswith("p/k.pdf")
    assert body["docx_url"].endswith("p/k.docx")
    assert body["pdf_key"] == "p/k.pdf"
    assert body["sections"] == ["Chapter 5 — Conclusion"]
    assert body["pages"] == 3
    assert body["powered_by"] == "DoThesis"

    with Session(get_engine()) as s:
        job = s.scalar(select(Job).where(Job.partner_token == "ptok-1"))
        assert job is not None and job.mode == "partner" and job.status == "done"
        proj = s.get(Project, job.project_id)
        assert proj is not None  # a REAL project row — chat handoff is possible
        # the store was seeded before spawn
        from app.agent_state import DbProjectStateStore
        st = DbProjectStateStore(get_engine(), proj.id, "/tmp/x").load()
        assert st["contextStore"]["analysis_results"].startswith("cronbach")


def test_failed_run_is_502(client, monkeypatch):
    monkeypatch.setattr(router_mod.prun, "_extract_text",
                        lambda b, f: ("cronbach 0.9 ave 0.6 " + "0.1 " * 10, 3))

    def failing_spawn(db, run, params):
        run.status = "failed"
        run.error_text = "headless run failed: max_stalls after 3 turns"
        db.commit()

    monkeypatch.setattr(job_runner, "spawn_headless_run", failing_spawn)
    r = _post(client)
    assert r.status_code == 502
    assert r.json()["detail"]["error"]["code"] == "report_failed"


def test_progress_reads_job(client, monkeypatch):
    monkeypatch.setattr(router_mod.prun, "_extract_text",
                        lambda b, f: ("cronbach 0.9 ave 0.6 " + "0.1 " * 10, 3))

    def running_then_done(db, run, params):
        run.status = "running"
        run.phase = "M3"
        run.progress = 0.4
        db.commit()

    monkeypatch.setattr(job_runner, "spawn_headless_run", running_then_done)
    monkeypatch.setattr(router_mod, "_wait_for_job",
                        _async_return("failed"))  # don't actually wait 35min
    _post(client, progress_token="ptok-2")

    r = client.post("/api/v1/partner/report/progress",
                    headers={"X-Partner-Token": TOKEN},
                    json={"progress_token": "ptok-2"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "processing" and body["phase"] == "M3"
    assert body["done"] == 2 and body["total"] == 5  # 0.4 * 5 modules

    r = client.post("/api/v1/partner/report/progress",
                    headers={"X-Partner-Token": TOKEN},
                    json={"progress_token": "unknown-token"})
    assert r.json()["status"] == "unknown"


def _async_return(value):
    async def _f(*a, **k):
        return value
    return _f
```

- [ ] **Step 2: Run, verify failure**

Run: `cd api && ./run.sh pytest tests/test_partner_report.py -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'prun'` etc.

- [ ] **Step 3: Rewrite `api/app/routers/partner_report.py`** (full replacement):

```python
"""Partner report endpoint — service-to-service ("Powered by DoThesis").

Rebuilt as a headless client of the deep agent (convergence spec §3): the
upload becomes a REAL project row + Job running `run_headless` in a subprocess,
then the shared compose/export path renders the requested report shape. The
multipart contract (shared X-Partner-Token secret, POST-only) is unchanged;
progress now reads the Job row instead of an in-memory dict, so it survives
restarts and multiple API processes.

Auth is a single shared secret (settings.partner_api_token). Empty secret ->
the endpoint 401s on every call, so it stays closed until explicitly enabled.
"""
from __future__ import annotations

import asyncio
import hmac
import logging
import os
import uuid

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import partner_run as prun
from .. import job_runner
from ..agent_state import DbProjectStateStore
from ..db import db_session
from ..models import Job, JobEvent, Project
from ..settings import get_settings
from .chat_v3 import _workspace_dir
from .uploads import s3_from_env

logger = logging.getLogger(__name__)

router = APIRouter(tags=["partner"])

# Analysis PDFs are typically small; cap defensively so a partner can't stream a
# giant file into the LLM path.
_MAX_BYTES = 25 * 1024 * 1024
_ALLOWED_MIME = {
    "application/pdf",
    "application/octet-stream",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
    "application/msword",
}


def _require_partner(x_partner_token: str | None) -> None:
    """Constant-time check of the shared partner secret. 401 on any mismatch."""
    expected = get_settings().partner_api_token
    if not expected or not x_partner_token or not hmac.compare_digest(x_partner_token, expected):
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "bad_partner_token", "message": "invalid partner token"}},
        )


class PartnerReportOut(BaseModel):
    pages: int
    depth: str
    chapters: list[str]
    sections: list[str]
    pdf_url: str | None
    docx_url: str | None
    pdf_key: str | None = None
    docx_key: str | None = None
    powered_by: str = "DoThesis"


async def _wait_for_job(engine, job_id: uuid.UUID, timeout_s: int) -> str:
    """Poll the Job row until terminal — the endpoint stays synchronous (the
    existing partner contract: one long call, progress polled alongside), but
    completion is now observed through the same DB rows the monitor writes,
    so it works across processes and restarts."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout_s
    while True:
        with Session(engine) as s:
            j = s.get(Job, job_id)
            status = j.status if j else "failed"
        if status in {"done", "failed", "canceled"}:
            return status
        if loop.time() > deadline:
            return "timeout"
        await asyncio.sleep(2.0)


def _job_done_meta(engine, job_id: uuid.UUID) -> dict:
    with Session(engine) as s:
        ev = s.scalars(
            select(JobEvent)
            .where(JobEvent.job_id == job_id, JobEvent.type == "job_done")
            .order_by(JobEvent.id.desc())
        ).first()
        return dict(ev.meta_json or {}) if ev else {}


@router.post("/partner/report", response_model=PartnerReportOut)
async def create_partner_report(
    file: UploadFile = File(...),
    depth: str = Form("analysis_report"),
    chapters: str | None = Form(None),
    progress_token: str | None = Form(None),
    title: str | None = Form(None),
    notes: str | None = Form(None),
    language: str = Form("en"),
    m1: str | None = Form(None),
    m2: str | None = Form(None),
    m3: str | None = Form(None),
    x_partner_token: str | None = Header(None, alias="X-Partner-Token"),
    db: Session = Depends(db_session),
):
    _require_partner(x_partner_token)

    if file.content_type and file.content_type not in _ALLOWED_MIME:
        raise HTTPException(
            415, detail={"error": {"code": "unsupported_media_type",
                                   "message": f"expected a PDF, got {file.content_type}"}})
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(422, detail={"error": {"code": "empty_file",
                                                   "message": "no file bytes"}})
    if len(pdf_bytes) > _MAX_BYTES:
        raise HTTPException(413, detail={"error": {"code": "file_too_large",
                                                   "message": f"max {_MAX_BYTES // (1024 * 1024)}MB"}})

    chapter_list = [c.strip() for c in chapters.split(",") if c.strip()] if chapters else None

    # Parse each optional module JSON up front so a malformed shape is a clean
    # 422 (never a silent drop / silent overwrite of a caller-provided module).
    import json

    def _parse(name, raw):
        if not raw:
            return None
        try:
            val = json.loads(raw)
        except json.JSONDecodeError:
            raise HTTPException(422, detail={"error": {"code": "bad_module_json",
                                                       "message": f"{name} must be valid JSON"}})
        if not isinstance(val, dict):
            raise HTTPException(422, detail={"error": {"code": "bad_module_json",
                                                       "message": f"{name} must be a JSON object"}})
        return val

    m1_d, m2_d, m3_d = _parse("m1", m1), _parse("m2", m2), _parse("m3", m3)

    # Everything below fails fast BEFORE any row is created — a 422 must not
    # leave orphan projects/jobs behind.
    try:
        chapter_keys = prun.resolve_chapters(depth, chapter_list)
    except prun.ReportError as e:
        raise HTTPException(422, detail={"error": {"code": e.code, "message": e.message}})

    text, pages = await run_in_threadpool(prun._extract_text, pdf_bytes, file.filename)
    if not text.strip():
        raise HTTPException(422, detail={"error": {"code": "no_extractable_text",
                                                   "message": "the file has no machine-readable text (image-only scan?)"}})
    if "results" in chapter_keys and not prun.pdf_looks_like_analysis(text):
        raise HTTPException(422, detail={"error": {"code": "insufficient_m4_data",
                                                   "message": "the uploaded file lacks the statistical analysis data "
                                                              "needed to write the Results (M4) chapter"}})

    # Real project row (system-owned) + workspace mirror + seeded store.
    sys_user = prun.ensure_partner_user(db)
    project = Project(user_id=sys_user.id,
                      name=(title or "Partner report").strip()[:200] or "Partner report",
                      language=language)
    db.add(project)
    db.commit()  # commit BEFORE seeding: the store opens its own connections

    workspace = _workspace_dir(project.id)
    (workspace / "uploads").mkdir(parents=True, exist_ok=True)
    # Mirror the raw upload so agent tools (read_file / parse_reference) can
    # open it — same uploads/ convention chat uses.
    (workspace / "uploads" / (file.filename or "analysis.pdf")).write_bytes(pdf_bytes)

    engine = db.bind
    store = DbProjectStateStore(engine, project.id, workspace)
    # Seeding is sync DB I/O — keep it off the event loop.
    await run_in_threadpool(
        prun.seed_partner_store, store,
        analysis_text=text, m1=m1_d, m2=m2_d, m3=m3_d,
        title=title, notes=notes, language=language,
    )

    run = Job(paper_id=None, project_id=project.id, mode="partner",
              status="queued", partner_token=progress_token,
              langgraph_thread_id=str(uuid.uuid4()))
    db.add(run)
    db.flush()
    params = {
        "depth": depth, "chapters": chapter_list, "language": language,
        "max_turns": int(os.getenv("PARTNER_MAX_TURNS", "80")),
        "wall_clock_s": int(os.getenv("PARTNER_WALL_CLOCK_S", "1800")),
    }
    job_runner.spawn_headless_run(db, run, params)

    status = await _wait_for_job(engine, run.id,
                                 timeout_s=int(os.getenv("PARTNER_REPORT_TIMEOUT_S", "2100")))
    if status != "done":
        raise HTTPException(502, detail={"error": {"code": "report_failed",
                                                   "message": f"headless run ended: {status}"}})

    meta = _job_done_meta(engine, run.id)
    keys = meta.get("artifact_keys") or {}
    s3 = s3_from_env()

    def _sign(key):
        return prun._presign(s3, key) if key else None

    # F5: partner surface export completed. Headless (no user id) — best-effort.
    from ..analytics import emit
    emit("export_completed", None,
         {"scope": ",".join(chapter_list) if chapter_list else depth, "surface": "partner"})

    return {
        "pages": pages,
        "depth": depth,
        "chapters": meta.get("chapters") or chapter_keys,
        "sections": meta.get("sections") or [],
        "pdf_url": _sign(keys.get("pdf")),
        "docx_url": _sign(keys.get("docx")),
        "pdf_key": keys.get("pdf"),
        "docx_key": keys.get("docx"),
    }


class ProgressIn(BaseModel):
    progress_token: str


class ProgressOut(BaseModel):
    status: str  # processing | done | error | unknown
    phase: str | None = None       # focus module (M1..M5)
    total: int | None = None
    done: int | None = None
    current: str | None = None


@router.post("/partner/report/progress", response_model=ProgressOut)
async def partner_report_progress(
    body: ProgressIn,
    x_partner_token: str | None = Header(None, alias="X-Partner-Token"),
    db: Session = Depends(db_session),
):
    """Poll live progress for an in-flight report — reads the Job the token
    maps to (module granularity now: total/done count finished modules)."""
    _require_partner(x_partner_token)
    j = db.scalars(
        select(Job).where(Job.partner_token == body.progress_token)
        .order_by(Job.started_at.desc().nulls_last())
    ).first()
    if j is None:
        return {"status": "unknown"}
    status = {"queued": "processing", "running": "processing",
              "done": "done"}.get(j.status, "error")
    return {"status": status, "phase": j.phase, "total": 5,
            "done": int(round((j.progress or 0.0) * 5)), "current": None}
```

- [ ] **Step 4: Absorb the inference helpers into `api/app/import_work.py`.** Copy `_infer_topic` (partner_report_service.py:139-192) and `_infer_model` (:330-388) **verbatim** into `import_work.py` as module-private functions (above their call sites at :58/:63), and replace the import at :11 with a comment:

```python
# _infer_topic/_infer_model moved in from the deleted partner_report_service —
# import-your-work is now their ONLY caller (partner inference is replaced by
# the headless agent's backfill tool, convergence spec §3).
```

- [ ] **Step 5: Delete `api/app/partner_report_service.py`**

```bash
git rm api/app/partner_report_service.py
```

- [ ] **Step 6: Run the partner + import suites**

Run: `cd api && ./run.sh pytest tests/test_partner_report.py tests/test_import_work.py tests/test_import_route.py -q`
Expected: PASS. If `test_import_work.py` monkeypatched the old service module, update those patch targets to `app.import_work._infer_topic` / `app.import_work._infer_model`.

- [ ] **Step 7: Commit**

```bash
git add -A api/app api/tests/test_partner_report.py
git commit -m "feat(partner): rebuild endpoint as headless client — project row + Job + shared export; delete third engine"
```

---

### Task 12: Partner E2E under mock + full-suite verification

**Files:**
- Create: `api/tests/test_partner_headless_e2e.py`

**Interfaces:**
- Consumes: everything above. `DOTHESIS_E2E_MOCK` is not needed — the fake model is injected directly into `build_agent` (the env guard at runtime.py:564-566 exists for the full-process Playwright E2E; in-process tests inject).

- [ ] **Step 1: Write the E2E test** — `api/tests/test_partner_headless_e2e.py`:

```python
"""Partner E2E under mock (spec §5): seed -> run_headless -> artifacts, with
the REAL DbProjectStateStore, real deepagents loop, real commit_slice tools —
only the completion (FakeChatModel) and the heavy renderer are fake. No API
spend, no flake."""
import asyncio
import json

import pytest
from sqlalchemy.orm import Session

from agent.headless import RunProfile, run_headless
from agent.state import MODULES
from app.agent_state import DbProjectStateStore
from app.db import get_engine
from app.models import Project
from app.partner_run import ensure_partner_user, seed_partner_store


def _module_steps(module, writes):
    return [
        {"response": f"Working on {module}.",
         "tool_calls": [{"name": "commit_slice",
                         "args": {"module": module, "writes": writes,
                                  "reason": "e2e fixture", "confirm_done": True}}]},
        {"response": f"{module} committed."},
    ]


FIXTURE = {"scenario": "partner-e2e", "entry": "continue", "steps": [
    # One decision beat before work starts — proves the audit trail end-to-end.
    {"response": "Xác nhận hướng phân tích?\n\n[OPTIONS] Tiếp tục | Dừng lại"},
    *_module_steps("M1", {"research_title": "T", "research_questions": ["RQ1"]}),
    *_module_steps("M2", {"literature_sources": [{"title": "P", "year": 2024}]}),
    *_module_steps("M3", {"conceptual_model": "CM", "hypotheses": ["H1"],
                          "methodology": "PLS-SEM"}),
    *_module_steps("M4", {"analysis_outline": "O"}),
    *_module_steps("M5", {"final_sections": [{"title": "Intro", "prose": "p"}]}),
]}


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    # The M5 done-hook shells out to the real renderer — stub it; the export
    # path has its own tests (run_partner_export / m5 export suites).
    monkeypatch.setattr(DbProjectStateStore, "_auto_export_m5", lambda self: None)
    engine = get_engine()
    with Session(engine) as s:
        u = ensure_partner_user(s)
        p = Project(user_id=u.id, name="Partner report", language="vi")
        s.add(p)
        s.commit()
        pid = p.id
    store = DbProjectStateStore(engine, pid, tmp_path / "ws")
    seed_partner_store(store, analysis_text="Cronbach alpha .87 AVE 0.62",
                       language="vi", notes="steer")
    return store, pid, tmp_path


def test_seed_run_artifacts(seeded):
    store, pid, tmp_path = seeded
    fx = tmp_path / "fixtures"
    fx.mkdir()
    (fx / "run.json").write_text(json.dumps(FIXTURE), encoding="utf-8")

    from langgraph.checkpoint.memory import InMemorySaver
    from agent.runtime import build_agent
    from agent.testing.fake_model import FakeChatModel

    agent = build_agent(tmp_path / "ws",
                        model=FakeChatModel.from_fixtures_dir(str(fx)),
                        checkpointer=InMemorySaver(), store=store)
    result = asyncio.run(run_headless(agent, store,
                                      RunProfile(max_turns=15),
                                      initial_prompt="continue"))
    assert result.status == "done", result
    # everything below is a FRESH DB read — prod truth, not runner memory
    reloaded = DbProjectStateStore(get_engine(), pid, tmp_path / "ws").load()
    assert all(reloaded["status"][m] == "done" for m in MODULES)
    assert reloaded["contextStore"]["decisions"][0]["choice"] == "Tiếp tục"
    assert reloaded["contextStore"]["research_title"] == "T"
    # the seeded analysis survived the whole run
    assert reloaded["contextStore"]["analysis_results"].startswith("Cronbach")
```

- [ ] **Step 2: Run it**

Run: `cd api && ./run.sh pytest tests/test_partner_headless_e2e.py -q`
Expected: PASS. (If the decision turn stalls: the `[OPTIONS]` step commits nothing, so `progressed` must come from the options event — that is precisely what the runner's `or bool(options)` covers.)

- [ ] **Step 3: Full verification sweep**

Run: `cd api && ./run.sh pytest -q`
Expected: PASS (whole api suite; testcontainers Postgres required).

Run: `cd api && ./run.sh pytest ../agent/tests -q`
Expected: PASS (whole agent suite).

- [ ] **Step 4: Commit**

```bash
git add api/tests/test_partner_headless_e2e.py
git commit -m "test(partner): E2E under mock — seed, headless run, Db-backed audit trail"
```

---

## Out of scope (per spec)

- **C** (auto-mode → deep agent swap; also: deleting `_sync_context_store_from_checkpoint`, job_runner.py:160 — spec §4 says delete only once auto-mode runs the deep agent).
- **D** (retiring `orchestrator/prompts/*`, the second model factory, `CHAPTER_ORDER` copies in `orchestrator/`, the dead `DOTHESIS_AGENT_V3` docs).
- **E** (billing/model mismatch, job_runner.py:373 vs orchestrator/llm.py:47 — ships independently, ahead of A+B).
- Quality equivalence claims — same brain proves consistency by construction, not quality (spec Non-goals).
- The qwen-plus cost premise — measure with the benchmark harness (`a070354`) before flipping any default model env.

## Execution notes

- The spec names `SessionPrompt.runLoop`, `session/llm.ts`, etc. — those are **opencode** references (prior art), not symbols in this repo.
- After Task 11, `grep -rn "partner_report_service" --include="*.py" .` must return only docs/spec hits; anything else is a missed caller.
- Real-model smoke (optional, costs tokens): `cd api && DOTHESIS_E2E_MOCK=0 ./run.sh python -m app.headless_entry --help` only checks arg parsing; a true live run needs a seeded project and is not part of this plan's gates.

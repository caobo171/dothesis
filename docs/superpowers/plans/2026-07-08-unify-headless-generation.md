# Unify Headless Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the duplicated compose/gate logic between the Partner API and the M5 engine, and give the Partner API an optional M1/M2/M3 input contract that generates missing modules (with real, time-bounded M2 research).

**Architecture:** `run_export` is already the single shared export path. The remaining duplication is partner's subset-compose clone (`_compose_chapters`), its prose sanitation, and its second M4 gate (`_has_sufficient_m4_data`). We (1) push sanitation into the engine's `compose_chapter` so every compose path shares it, (2) extend the one store-level gate `assess_export_readiness` with chapter-scoping, (3) add an engine `compose_and_export` for subset composition, and (4) split partner into a front half (`build_partner_context_store`, with optional inputs + budgeted M2 research) that feeds the shared back half.

**Tech Stack:** Python 3, FastAPI, LangChain tools (`.invoke`/`.func`), pytest. Engine code under `orchestrator/tools/`, API under `api/app/`.

## Global Constraints

- **POST-only endpoints.** New/changed routes stay `@router.post`; params in the body/form (project convention; `/health` is the only GET). Copied verbatim from CLAUDE.md.
- **No new gates on headless paths beyond what exists.** Auto-mode gets shared sanitation + the shared gate *function*, but no new *blocking* gate. Only the Partner front half enforces the gate (it already did).
- **Never overwrite caller-provided modules.** Partner generation only fills holes.
- **Best-effort research.** M2 research must never hang or hard-fail the report — always fall back to Crossref, then `[]`.
- **Run api tests via `./run.sh`** from `api/` (arm64 venv): `cd api && ./run.sh pytest <path> -q`. Engine tests: `cd orchestrator && ../api/run.sh ...` is not set up — engine-importing tests live under `api/tests` and run from `api/`.
- **Comment the decision behind each change** (project convention: explain *why*, not just *what*).

---

### Task 1: Chapter-scope the single M4 gate

Give `assess_export_readiness` an optional `chapters` argument so it only reports
missing data that the *requested* chapters actually need. This makes it usable as the
one gate for partial (partner "analysis_report") composes, replacing partner's
`_has_sufficient_m4_data` as the store-level gate.

**Files:**
- Modify: `orchestrator/tools/m5_writing.py:1103` (`assess_export_readiness`)
- Test: `api/tests/test_compose_export.py` (create)

**Interfaces:**
- Produces: `assess_export_readiness(context_store: dict, chapters: list[str] | None = None) -> list[str]` — empty list = ready. When `chapters` is given, only returns missing items whose owning chapter is in `chapters`.

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_compose_export.py
from orchestrator.tools.m5_writing import assess_export_readiness

_FULL = ["intro", "lit_review", "methodology", "results", "discussion", "conclusion"]


def test_gate_all_chapters_reports_everything_missing():
    assert assess_export_readiness({}, _FULL)  # empty store -> many missing


def test_gate_scopes_to_requested_chapters():
    # A store with only M4 analysis results, composing ONLY results+discussion:
    store = {"m4_analysis": {"analysis_results": "AVE=0.62 HTMT ok R2=.41"}}
    missing = assess_export_readiness(store, ["results", "discussion"])
    # M3 methodology is NOT requested (no methodology chapter) -> not reported.
    assert not any("methodology" in m.lower() for m in missing)
    # M4 results ARE present -> not reported either.
    assert not any("analysis results" in m.lower() for m in missing)


def test_gate_none_chapters_is_backcompat_full_check():
    # No chapters arg -> behaves exactly as before (checks all modules).
    assert assess_export_readiness({}) == assess_export_readiness({}, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && ./run.sh pytest tests/test_compose_export.py -q`
Expected: FAIL — `test_gate_scopes_to_requested_chapters` (methodology reported despite not being requested) and/or TypeError on the 2-arg call.

- [ ] **Step 3: Implement chapter scoping**

Replace the body of `assess_export_readiness` (`orchestrator/tools/m5_writing.py:1103`):

```python
# Which requested chapter makes each missing item relevant. Title/RQs and
# literature are needed by every academic chapter, so any requested chapter
# pulls them in; methodology + results are chapter-specific. This lets a
# partial compose (partner "analysis_report" = intro/results/discussion) gate
# only on what those chapters need — one gate for full AND subset composes.
def assess_export_readiness(context_store: dict, chapters: list[str] | None = None) -> list[str]:
    """Return human-readable missing-data items (empty = ready).

    When `chapters` is given, only report items whose owning chapter is in the
    requested set, so a subset compose isn't blocked by data a skipped chapter
    would have used.
    """
    m1 = context_store.get("m1_topic") or {}
    m2 = context_store.get("m2_literature") or {}
    m3 = context_store.get("m3_design") or {}
    m4 = context_store.get("m4_analysis") or {}

    ANY = None  # relevant to every chapter
    checks = [
        (ANY, not str(m1.get("research_title") or "").strip(), "M1 — research title"),
        (ANY, not (m1.get("research_questions") or []), "M1 — research questions"),
        (ANY, not (m2.get("literature_sources") or []),
         "M2 — literature sources (no references to cite)"),
        ("methodology", not (m3.get("methodology") or m3.get("conceptual_model")),
         "M3 — methodology / conceptual model"),
        ("results", not (m4.get("analysis_results") or m4.get("qual_themes") or m4.get("qual_codes")),
         "M4 — analysis results (the Results chapter has no data)"),
    ]
    req = set(chapters) if chapters is not None else None
    missing: list[str] = []
    for owner, is_missing, label in checks:
        if not is_missing:
            continue
        if req is None or owner is ANY or owner in req:
            missing.append(label)
    return missing
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd api && ./run.sh pytest tests/test_compose_export.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add orchestrator/tools/m5_writing.py api/tests/test_compose_export.py
git commit -m "feat(engine): chapter-scope assess_export_readiness

One gate for full AND subset composes — a partial compose isn't blocked by
data only a skipped chapter would use. Enables partner to drop its second
_has_sufficient_m4_data store-gate.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Move prose sanitation into the engine compose path

Partner sanitizes composed prose (`_sanitize_prose`, `_drop_placeholder_tables`,
`_reflow_inline_bullets`); the engine's own `compose_chapter` does not, so auto-mode and
the chat agent ship un-sanitized quirks. Move these helpers into the engine and apply them
inside `compose_chapter` so **every** compose path (auto-mode, agent, partner) shares one
sanitation pass.

**Files:**
- Modify: `orchestrator/tools/m5_writing.py` (add helpers; call in `compose_chapter` at 1602)
- Modify: `api/app/partner_report_service.py` (delete the three helpers; import from engine)
- Test: `api/tests/test_compose_export.py`

**Interfaces:**
- Produces: `sanitize_prose(prose: str) -> str` in `orchestrator/tools/m5_writing.py` (public; the merged pass — inline-bullet reflow + hypothesis demotion + placeholder-table drop).
- Consumes: `compose_chapter.invoke({...})` now returns `{"prose": <sanitized>}`.

- [ ] **Step 1: Write the failing test**

```python
# add to api/tests/test_compose_export.py
from orchestrator.tools.m5_writing import sanitize_prose


def test_sanitize_demotes_heading_hypothesis():
    # "### H1: full sentence." -> "**H1:** full sentence." (no oversized heading, no TOC).
    out = sanitize_prose("### H1: Trust positively affects intention to use the system.")
    assert out.startswith("**H1:**")
    assert not out.lstrip().startswith("#")


def test_sanitize_drops_placeholder_table():
    md = "**Bảng 4.1**\n\n| A | B |\n|---|---|\n| … | … |\n\n*Nguồn: tác giả*\n\nReal prose."
    out = sanitize_prose(md)
    assert "|" not in out          # the dotted shell table is gone
    assert "Real prose." in out    # surrounding prose kept
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && ./run.sh pytest tests/test_compose_export.py -q`
Expected: FAIL — `ImportError: cannot import name 'sanitize_prose'`.

- [ ] **Step 3: Move the helpers into the engine**

In `orchestrator/tools/m5_writing.py`, copy `_reflow_inline_bullets`, `_sanitize_prose`,
`_drop_placeholder_tables` and the module-level regexes they use (`_HEADING_RE`, `_HYP_RE`,
`_BOLD_HYP_RE`, `_STAR_BULLET_RE`, `_DASH_BULLET_RE`, `_PAREN_GROUP_RE`,
`_PLACEHOLDER_CELL_RE`) verbatim from `partner_report_service.py:104-259`. Expose the merged
pass under a public name:

```python
# Public: the single prose-normalization pass shared by every compose path.
# Moved here from partner_report_service so auto-mode + agent + partner all get
# the same cleanup (inline-bullet reflow, hypothesis-heading demotion, dropping
# placeholder "…" tables).
def sanitize_prose(prose: str) -> str:
    return _sanitize_prose(prose)
```

Then apply it inside `compose_chapter` (`orchestrator/tools/m5_writing.py:1602`) at the
point it currently returns `{"prose": prose}` — wrap that prose:

```python
        # Sanitize here so EVERY caller (auto-mode graph, chat agent, partner)
        # ships normalized prose from one place instead of each re-cleaning.
        prose = sanitize_prose(prose)
        return {"prose": prose, ...}   # keep the rest of the existing return dict
```

- [ ] **Step 4: Delete the partner copies and import from engine**

In `api/app/partner_report_service.py`: delete `_reflow_inline_bullets`, `_sanitize_prose`,
`_drop_placeholder_tables` and their now-unused regexes. Anywhere partner called
`_sanitize_prose(prose)` (in the compose loop), it will instead rely on `compose_chapter`
having already sanitized — but keep a defensive import for the fallback path:

```python
from orchestrator.tools.m5_writing import sanitize_prose  # noqa: E402 (top-level ok here)
```

- [ ] **Step 5: Run tests**

Run: `cd api && ./run.sh pytest tests/test_compose_export.py tests/test_partner_report.py -q`
Expected: PASS. Also run the engine's M5 suite for regressions:
Run: `cd api && ./run.sh pytest ../orchestrator/tests/test_agents_m5.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/tools/m5_writing.py api/app/partner_report_service.py api/tests/test_compose_export.py
git commit -m "refactor(engine): share prose sanitation across all compose paths

Move _sanitize_prose/_drop_placeholder_tables/_reflow_inline_bullets out of
partner into compose_chapter so auto-mode + agent + partner clean prose once,
in one place. Kills the partner-only clone.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Add the shared `compose_and_export` back half

Extract partner's subset-compose loop (`_compose_chapters`) into an engine function that
composes a requested chapter subset and exports it, so partner stops owning a clone of
`compose_all_sections`.

**Files:**
- Create: `orchestrator/tools/compose_export.py`
- Test: `api/tests/test_compose_export.py`

**Interfaces:**
- Consumes: `compose_chapter` (Task 2, sanitized), `run_export(sections, project_id, references, language)`, `_chapter_titles`, `_fallback_section` from `orchestrator/tools/m5_writing.py`.
- Produces:
  - `ProgressFn = Callable[[int, str, str, str], None]` (idx, key, title, phase="start"|"end").
  - `compose_sections(context_store, chapters, language, references=None, progress=None) -> list[dict]` — `[{title, prose}]` in canonical order.
  - `compose_and_export(context_store, project_id, *, chapters, language, references=None, progress=None) -> list[dict]` — artifacts from `run_export`.

- [ ] **Step 1: Write the failing test**

```python
# add to api/tests/test_compose_export.py
import orchestrator.tools.m5_writing as m5
from orchestrator.tools import compose_export as ce


def test_compose_sections_orders_canonically_and_calls_compose(monkeypatch):
    seen = []
    monkeypatch.setattr(m5.compose_chapter, "invoke",
                        lambda payload: (seen.append(payload["chapter_name"]),
                                         {"prose": f"prose for {payload['chapter_name']}"})[1])
    store = {"m1_topic": {"research_title": "T"}, "m4_analysis": {"analysis_results": "x"}}
    # Pass chapters OUT of order; expect canonical order in the output.
    out = ce.compose_sections(store, ["results", "intro"], "en")
    assert [s["title"] for s in out]  # titles resolved
    assert seen == ["intro", "results"]  # canonical order enforced


def test_compose_and_export_calls_run_export(monkeypatch):
    monkeypatch.setattr(ce, "compose_sections",
                        lambda *a, **k: [{"title": "Chapter 4 — Results", "prose": "p"}])
    called = {}
    monkeypatch.setattr(m5, "run_export",
                        lambda sections, pid, references=None, language="en":
                        called.update(pid=pid, n=len(sections)) or
                        [{"kind": "pdf", "s3_key": f"projects/{pid}/x.pdf", "size_bytes": 1}])
    arts = ce.compose_and_export({"m1_topic": {}}, "partner-abc",
                                 chapters=["results"], language="en")
    assert called == {"pid": "partner-abc", "n": 1}
    assert arts[0]["kind"] == "pdf"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && ./run.sh pytest tests/test_compose_export.py -q`
Expected: FAIL — `ModuleNotFoundError: orchestrator.tools.compose_export`.

- [ ] **Step 3: Implement the module**

```python
# orchestrator/tools/compose_export.py
"""Shared headless back half: compose a chapter SUBSET from a context_store and
export it. Extracted from partner_report_service._compose_chapters so the Partner
API stops owning a near-clone of compose_all_sections. Composition is sanitized in
compose_chapter (see m5_writing.sanitize_prose); this module only owns subset
selection, canonical ordering, and the run_export hand-off. It deliberately does
NOT gate — gating stays a caller decision (partner enforces, auto-mode does not),
so this never adds a blocking gate to a headless path.
"""
from __future__ import annotations

import logging
from typing import Callable

from .m5_writing import (
    M5_CHAPTER_ORDER,
    _chapter_titles,
    _fallback_section,
    compose_chapter,
    run_export,
)

logger = logging.getLogger(__name__)

# progress(idx, chapter_key, title, phase) — phase is "start" or "end".
ProgressFn = Callable[[int, str, str, str], None]


def compose_sections(
    context_store: dict,
    chapters: list[str],
    language: str,
    references: list[dict] | None = None,
    progress: ProgressFn | None = None,
    title_overrides: dict[str, str] | None = None,
) -> list[dict]:
    """Compose a requested subset of M5 chapters, in canonical order → [{title, prose}]."""
    m1 = context_store.get("m1_topic") or {}
    m3 = context_store.get("m3_design") or {}
    m4 = context_store.get("m4_analysis") or {}
    context_slice: dict = {**m1, **m3, **m4}
    context_slice.setdefault("results", m4.get("analysis_results"))

    ordered = [k for k in M5_CHAPTER_ORDER if k in set(chapters)]
    titles = {**_chapter_titles(language), **(title_overrides or {})}

    out: list[dict] = []
    for idx, name in enumerate(ordered):
        if progress:
            progress(idx, name, titles[name], "start")
        try:
            draft = compose_chapter.invoke({
                "chapter_name": name,
                "paradigm": "",
                "context_slice": context_slice,
                "references": references or [],
                "citation_style": "apa7",
                "language": language,
            })
            prose = (draft or {}).get("prose") or ""
        except Exception:
            logger.exception("compose_sections: compose_chapter failed for %s", name)
            prose = ""
        if not prose.strip():
            prose = _fallback_section(name, context_store)
        if prose.strip():
            out.append({"title": titles[name], "prose": prose})
        if progress:
            progress(idx, name, titles[name], "end")
    return out


def compose_and_export(
    context_store: dict,
    project_id: str,
    *,
    chapters: list[str],
    language: str,
    references: list[dict] | None = None,
    progress: ProgressFn | None = None,
    title_overrides: dict[str, str] | None = None,
) -> list[dict]:
    """Compose the chapter subset and export via the shared run_export path."""
    sections = compose_sections(
        context_store, chapters, language,
        references=references, progress=progress, title_overrides=title_overrides,
    )
    return run_export(sections, str(project_id), references=references or None, language=language)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd api && ./run.sh pytest tests/test_compose_export.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/tools/compose_export.py api/tests/test_compose_export.py
git commit -m "feat(engine): shared compose_and_export subset back half

Extract partner's _compose_chapters clone into the engine. Owns subset
selection + canonical ordering + run_export hand-off; deliberately does NOT
gate (caller's choice) so it never adds a blocking gate to a headless path.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Partner front half — optional M1/M2/M3 with generate-if-missing

Add `build_partner_context_store` that accepts optional caller-provided modules and
generates only the missing ones. This is the input-contract requirement.

**Files:**
- Modify: `api/app/partner_report_service.py` (add builder; rename gate helper)
- Test: `api/tests/test_partner_report.py`

**Interfaces:**
- Consumes: existing `_infer_topic`, `_infer_model`, `_literature_search`, `_budgeted_scout` (Task 5).
- Produces:
  - `pdf_looks_like_analysis(text: str) -> bool` (renamed from `_has_sufficient_m4_data`; ingest pre-check).
  - `build_partner_context_store(text, *, notes, language, m1=None, m2=None, m3=None) -> dict` — a nested `context_store`. Provided modules are used verbatim; missing ones generated.

- [ ] **Step 1: Write the failing test**

```python
# add to api/tests/test_partner_report.py
def test_build_context_store_uses_provided_m1_verbatim(monkeypatch):
    called = {"infer": False}
    monkeypatch.setattr(svc, "_infer_topic", lambda *a, **k: called.__setitem__("infer", True) or {})
    monkeypatch.setattr(svc, "_budgeted_scout", lambda *a, **k: [])
    provided_m1 = {"research_title": "Given Title", "research_questions": ["RQ1"]}
    store = svc.build_partner_context_store(
        "AVE=0.6 HTMT ok R2=.4", notes=None, language="en", m1=provided_m1)
    assert store["m1_topic"]["research_title"] == "Given Title"
    assert called["infer"] is False  # provided -> NOT inferred


def test_build_context_store_generates_missing_m2(monkeypatch):
    monkeypatch.setattr(svc, "_infer_topic", lambda *a, **k: {"research_title": "Inferred"})
    monkeypatch.setattr(svc, "_infer_model", lambda *a, **k: {})
    scout_hits = [{"title": "Real Paper", "doi": "10.1/x"}]
    monkeypatch.setattr(svc, "_budgeted_scout", lambda *a, **k: scout_hits)
    store = svc.build_partner_context_store("AVE=0.6", notes=None, language="en")  # no m2
    assert store["m2_literature"]["literature_sources"] == scout_hits
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && ./run.sh pytest tests/test_partner_report.py -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'build_partner_context_store'`.

- [ ] **Step 3: Implement the builder + rename the gate**

In `api/app/partner_report_service.py`, rename `_has_sufficient_m4_data` →
`pdf_looks_like_analysis` (keep the body; update its one caller in `generate_partner_report`
in Task 6). Add:

```python
def build_partner_context_store(
    text: str,
    *,
    notes: str | None,
    language: str,
    m1: dict | None = None,
    m2: dict | None = None,
    m3: dict | None = None,
) -> dict:
    """Assemble the nested context_store for a partner report.

    Input contract: M1/M2/M3 are OPTIONAL. Each one the caller provides is used
    VERBATIM; each missing one is generated (M1 via _infer_topic, M3 via
    _infer_model, M2 via real budgeted research). M4 is always the uploaded
    analysis text. Provided modules are never overwritten.
    """
    notes_clean = (notes or "").strip()

    # M1: provided or inferred (notes prepended so inference reflects user intent).
    if m1:
        m1_topic = dict(m1)
        m1_topic.setdefault("language", language)
    else:
        infer_text = (f"Mô tả bổ sung:\n{notes_clean}\n\n{text}" if notes_clean else text)
        inferred = _infer_topic(infer_text, language)
        m1_topic = {"research_title": str(inferred.get("research_title") or "").strip()
                    or "Báo cáo phân tích", "language": language}
        for key in ("field", "research_type", "objectives", "target_population", "scope"):
            val = inferred.get(key)
            if isinstance(val, str) and val.strip():
                m1_topic[key] = val.strip()
        rqs = inferred.get("research_questions")
        if isinstance(rqs, list) and rqs:
            m1_topic["research_questions"] = [str(q) for q in rqs if str(q).strip()]
    if notes_clean:
        m1_topic.setdefault("user_context", notes_clean)

    store: dict = {"m1_topic": m1_topic, "m4_analysis": {"analysis_results": text}}

    # M3: provided or inferred (used later for the methodology diagram).
    store["m3_design"] = dict(m3) if m3 else (_infer_model(text, language) or {})

    # M2: provided verbatim, else REAL budgeted research (never a bare token fetch).
    if m2:
        store["m2_literature"] = dict(m2)
    else:
        refs = _budgeted_scout(
            m1_topic.get("research_title", ""),
            m1_topic.get("research_questions") or [],
        )
        if refs:
            store["m2_literature"] = {"literature_sources": refs}

    return store
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd api && ./run.sh pytest tests/test_partner_report.py -q`
Expected: PASS (the two new tests; others still green — `_budgeted_scout` is stubbed).

- [ ] **Step 5: Commit**

```bash
git add api/app/partner_report_service.py api/tests/test_partner_report.py
git commit -m "feat(partner): optional M1/M2/M3 inputs with generate-if-missing

build_partner_context_store uses caller-provided modules verbatim and only
generates the holes; missing M2 runs real research. Rename the PDF ingest
check to pdf_looks_like_analysis (store-level gate is now the shared one).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Budgeted real M2 research with Crossref fallback

Missing M2 must run *real* research (the deep scout) but under a wall-clock budget, falling
back to the existing light Crossref search so it never hangs.

**Files:**
- Modify: `api/app/partner_report_service.py` (add `_budgeted_scout`)
- Test: `api/tests/test_partner_report.py`

**Interfaces:**
- Consumes: `scout_citations.func(topic, min_n)` from `orchestrator.tools.m2_literature`; existing `_literature_search`.
- Produces: `_budgeted_scout(topic: str, research_questions: list[str]) -> list[dict]`.

Budget constants (chosen here; tune later): `_M2_SCOUT_MIN = 8`, `_M2_SCOUT_TIMEOUT_S = 45`.

- [ ] **Step 1: Write the failing test**

```python
# add to api/tests/test_partner_report.py
def test_budgeted_scout_uses_real_scout_when_in_budget(monkeypatch):
    import orchestrator.tools.m2_literature as m2lit
    monkeypatch.setattr(m2lit.scout_citations, "func",
                        lambda topic, min_n=8: [{"title": "Scouted", "doi": "10.1/a"}])
    out = svc._budgeted_scout("topic", ["RQ1"])
    assert out and out[0]["title"] == "Scouted"


def test_budgeted_scout_falls_back_on_timeout(monkeypatch):
    import orchestrator.tools.m2_literature as m2lit

    def slow(topic, min_n=8):
        import time; time.sleep(5); return []
    monkeypatch.setattr(m2lit.scout_citations, "func", slow)
    monkeypatch.setattr(svc, "_M2_SCOUT_TIMEOUT_S", 0.2)  # force timeout fast
    monkeypatch.setattr(svc, "_literature_search",
                        lambda *a, **k: [{"title": "Crossref fallback"}])
    out = svc._budgeted_scout("topic", ["RQ1"])
    assert out == [{"title": "Crossref fallback"}]


def test_budgeted_scout_falls_back_on_error(monkeypatch):
    import orchestrator.tools.m2_literature as m2lit
    def boom(topic, min_n=8):
        raise RuntimeError("scout down")
    monkeypatch.setattr(m2lit.scout_citations, "func", boom)
    monkeypatch.setattr(svc, "_literature_search", lambda *a, **k: [])
    assert svc._budgeted_scout("topic", []) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && ./run.sh pytest tests/test_partner_report.py -k budgeted -q`
Expected: FAIL — no `_budgeted_scout`.

- [ ] **Step 3: Implement `_budgeted_scout`**

Add near `_literature_search` in `api/app/partner_report_service.py`:

```python
# Real M2 research for a partner report, under a wall-clock budget. The full
# scout can run minutes / rate-limit; we cap it and fall back to the light
# Crossref search so a report never hangs and never ships zero references.
_M2_SCOUT_MIN = 8
_M2_SCOUT_TIMEOUT_S = 45


def _budgeted_scout(topic: str, research_questions: list[str]) -> list[dict]:
    """Deep scout capped by time; Crossref fallback on timeout/error/empty."""
    import concurrent.futures as _fut

    composed = topic
    if research_questions:
        composed += "\nResearch questions:\n" + "\n".join(f"- {q}" for q in research_questions)

    try:
        from orchestrator.tools.m2_literature import scout_citations  # noqa: PLC0415
        with _fut.ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(scout_citations.func, composed, min_n=_M2_SCOUT_MIN)
            citations = future.result(timeout=_M2_SCOUT_TIMEOUT_S)
        sources = [
            {"title": c.get("title"), "authors": c.get("authors"), "year": c.get("year"),
             "venue": c.get("source") or c.get("venue"), "doi": c.get("doi"),
             "url": c.get("url")}
            for c in (citations or [])
        ]
        if sources:
            return sources
    except Exception:
        # TimeoutError, engine failure, rate limit — all fall through to Crossref.
        logger.exception("partner_report: budgeted scout failed; using Crossref fallback")

    return _literature_search(topic, research_questions)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd api && ./run.sh pytest tests/test_partner_report.py -k budgeted -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add api/app/partner_report_service.py api/tests/test_partner_report.py
git commit -m "feat(partner): budgeted real M2 research with Crossref fallback

Missing-M2 now runs the deep scout capped at 45s, falling back to the light
Crossref search on timeout/error/empty so a report never hangs or ships zero
references.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Rewire `generate_partner_report` onto the shared back half

Replace partner's inline compose loop + second M4 gate with:
`build_partner_context_store` → `assess_export_readiness(store, chapters)` gate →
`compose_and_export`. Delete `_compose_chapters`.

**Files:**
- Modify: `api/app/partner_report_service.py:613` (`generate_partner_report`); delete `_compose_chapters:262`
- Test: `api/tests/test_partner_report.py` (update `test_service_composes_and_presigns`)

**Interfaces:**
- Consumes: Tasks 1–5. `generate_partner_report(pdf_bytes, *, depth, chapters, progress_token, filename, title, notes, language, m1=None, m2=None, m3=None)`.

- [ ] **Step 1: Update the failing test to the new internals**

Replace `test_service_composes_and_presigns` monkeypatches (`api/tests/test_partner_report.py:114`)
so it stubs the new seams instead of the deleted ones:

```python
def test_service_composes_and_presigns(monkeypatch):
    monkeypatch.setattr(svc, "extract_pdf_text", lambda b: ("AVE=0.62, HTMT ok, R2=.41", 5))
    monkeypatch.setattr(svc, "pdf_looks_like_analysis", lambda text: True)
    monkeypatch.setattr(svc, "build_partner_context_store",
                        lambda text, **k: {"m1_topic": {"research_title": "T"},
                                           "m4_analysis": {"analysis_results": text}})
    # Gate passes (nothing missing) for the requested chapters.
    monkeypatch.setattr("orchestrator.tools.m5_writing.assess_export_readiness",
                        lambda store, chapters=None: [])
    # Stub the shared compose + export seams the service now calls by name.
    import orchestrator.tools.compose_export as ce
    monkeypatch.setattr(ce, "compose_sections",
                        lambda *a, **k: [{"title": "Chapter 4 — Results", "prose": "p"}])
    monkeypatch.setattr(svc, "_maybe_embed_model_diagram", lambda *a, **k: None)
    import orchestrator.tools.m5_writing as m5
    monkeypatch.setattr(m5, "run_export",
                        lambda sections, pid, references=None, language="en": [
                            {"kind": "pdf", "s3_key": f"projects/{pid}/report.pdf", "size_bytes": 10},
                            {"kind": "docx", "s3_key": f"projects/{pid}/report.docx", "size_bytes": 10},
                        ])

    class _FakeS3:
        def generate_presigned_url(self, op, Params, ExpiresIn):
            return f"https://s3.example/{Params['Key']}?sig=1"
    monkeypatch.setattr(svc, "_s3_from_env", lambda: _FakeS3())
    monkeypatch.setenv("S3_BUCKET", "bkt")

    out = svc.generate_partner_report(b"pdf", depth="analysis_report", title="T", language="en")
    assert out["pages"] == 5
    assert out["pdf_url"].endswith("report.pdf?sig=1")
```

Also add a gate-rejection test:

```python
def test_service_rejects_when_gate_reports_missing(monkeypatch):
    monkeypatch.setattr(svc, "extract_pdf_text", lambda b: ("AVE=0.62 HTMT R2=.41", 5))
    monkeypatch.setattr(svc, "pdf_looks_like_analysis", lambda text: True)
    monkeypatch.setattr(svc, "build_partner_context_store", lambda text, **k: {"m1_topic": {}})
    monkeypatch.setattr("orchestrator.tools.m5_writing.assess_export_readiness",
                        lambda store, chapters=None: ["M4 — analysis results"])
    with pytest.raises(ReportError) as ei:
        svc.generate_partner_report(b"pdf", depth="analysis_report", language="en")
    assert ei.value.code == "needs_data"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd api && ./run.sh pytest tests/test_partner_report.py -q`
Expected: FAIL — old internals still referenced / no `needs_data` path yet.

- [ ] **Step 3: Rewrite `generate_partner_report`**

Replace the body from the extract/gate/compose section
(`api/app/partner_report_service.py:660-789`) with the delegated flow. Keep the chapter-key
resolution (`chapters`/`depth`), the Discussion+Conclusion merge, and the progress/S3/presign
tail. New middle:

```python
        text, pages = _extract_text(pdf_bytes, filename)
        if not text.strip():
            raise ReportError("no_extractable_text",
                              "the file has no machine-readable text (image-only scan?)")

        # Ingest pre-check: cheap fail-fast before any LLM spend when the upload
        # isn't statistical output at all (only when a Results chapter is asked).
        if "results" in chapter_keys and not pdf_looks_like_analysis(text):
            raise ReportError("insufficient_m4_data",
                              "the uploaded file lacks the statistical analysis data "
                              "needed to write the Results (M4) chapter")

        context_store = build_partner_context_store(
            text, notes=notes, language=language, m1=m1, m2=m2, m3=m3)

        # The ONE store-level gate (shared with the rest of the app), scoped to
        # the requested chapters. Missing data -> needs_data (partner charges a
        # small validation fee instead of a full report).
        from orchestrator.tools.m5_writing import assess_export_readiness  # noqa: PLC0415
        missing = assess_export_readiness(context_store, chapter_keys)
        if missing:
            raise ReportError("needs_data", "missing required data: " + "; ".join(missing))

        references = (context_store.get("m2_literature") or {}).get("literature_sources") or None

        def _on_chapter(idx, key, title_, phase):
            _set_progress(progress_token, done=idx + (1 if phase == "end" else 0),
                          current=None if phase == "end" else title_)

        combined_title = "Chương 5 — Kết luận" if language.startswith("vi") else "Chapter 5 — Conclusion"
        _set_progress(progress_token, phase="compose")

        # Partner composes via the shared `compose_sections`, injects its
        # methodology diagram into the returned sections, THEN exports. We do NOT
        # use compose_and_export here (which composes+exports in one call) because
        # the diagram must be embedded between those two steps — compose_and_export
        # stays for callers that don't need the diagram (and for Spec-2 reuse).
        from orchestrator.tools.compose_export import compose_sections  # noqa: PLC0415
        from orchestrator.tools.m5_writing import run_export  # noqa: PLC0415
        project_id = f"partner-{uuid.uuid4().hex}"
        sections = compose_sections(
            context_store, chapter_keys, language,
            references=references, progress=_on_chapter,
            title_overrides={"discussion": combined_title},
        )
        if not sections:
            raise ReportError("compose_failed", "the writing engine produced no sections")
        _maybe_embed_model_diagram(sections, text, language, chapter_keys)
        _set_progress(progress_token, phase="export", current=None)
        artifacts = run_export(sections, project_id, references=references, language=language)
```

Extract the existing methodology-diagram block (`partner_report_service.py:753-771`) verbatim
into a helper so the compose→embed→export order is preserved:

```python
def _maybe_embed_model_diagram(sections: list[dict], text: str, language: str,
                               chapter_keys: list[str]) -> None:
    """Infer + render the M3 model diagram and embed it in the methodology section
    (in place). Best-effort — a diagram failure never breaks the report."""
    if "methodology" not in chapter_keys:
        return
    try:
        model = _infer_model(text, language)
        png = _render_model_diagram(model) if model else None
        if not png:
            return
        from orchestrator.tools.m5_writing import _chapter_titles  # noqa: PLC0415
        meth_title = _chapter_titles(language).get("methodology")
        caption = ("Hình 1. Mô hình nghiên cứu đề xuất"
                   if str(language).lower().startswith("vi")
                   else "Figure 1. Proposed research model")
        figure_md = f"\n\n![{caption}]({png})\n"
        for sec in sections:
            if sec.get("title") == meth_title:
                sec["prose"] = (sec.get("prose") or "") + figure_md
                break
    except Exception:
        logger.exception("partner_report: model diagram step failed (continuing)")
```

Then update the S3 presign tail to consume `artifacts` (unchanged logic). Add
`m1=None, m2=None, m3=None` params to the `generate_partner_report` signature. Delete
`_compose_chapters` and the now-unused `_references_section` append (the citeproc path in
`run_export` builds the bibliography; behavior stays identical to today's DOCX path).

- [ ] **Step 4: Run the full partner suite**

Run: `cd api && ./run.sh pytest tests/test_partner_report.py -q`
Expected: PASS (all, including the new gate-rejection test).

- [ ] **Step 5: Commit**

```bash
git add api/app/partner_report_service.py api/tests/test_partner_report.py
git commit -m "refactor(partner): route report through shared compose_sections + one gate

generate_partner_report now builds the context_store (optional M1/M2/M3),
gates once via assess_export_readiness(store, chapters), composes via the
shared engine path, and exports via run_export. Deletes the _compose_chapters
clone; keeps the methodology-diagram injection.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Accept optional M1/M2/M3 at the partner route

Expose the input contract over HTTP: the partner can POST `m1`/`m2`/`m3` as JSON strings.

**Files:**
- Modify: `api/app/routers/partner_report.py:61` (`create_partner_report`)
- Test: `api/tests/test_partner_report.py`

**Interfaces:**
- Consumes: `generate_partner_report(..., m1=..., m2=..., m3=...)` (Task 6).

- [ ] **Step 1: Write the failing test**

```python
# add to api/tests/test_partner_report.py
def test_router_passes_optional_modules_through(client, monkeypatch):
    captured = {}
    def fake(*a, **k):
        captured.update(k)
        return {"pages": 1, "depth": "analysis_report", "chapters": ["results"],
                "sections": ["R"], "pdf_url": "u", "docx_url": "u"}
    monkeypatch.setattr(router_mod, "generate_partner_report", fake)

    r = client.post(
        "/api/v1/partner/report",
        headers={"X-Partner-Token": TOKEN},
        files={"file": ("a.pdf", io.BytesIO(b"%PDF-1.4 x"), "application/pdf")},
        data={"depth": "analysis_report", "language": "en",
              "m1": '{"research_title": "Given"}'},
    )
    assert r.status_code == 200
    assert captured["m1"] == {"research_title": "Given"}
    assert captured["m2"] is None and captured["m3"] is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd api && ./run.sh pytest tests/test_partner_report.py -k optional_modules -q`
Expected: FAIL — router doesn't accept/parse `m1`.

- [ ] **Step 3: Add the form fields + JSON parsing**

In `create_partner_report` (`api/app/routers/partner_report.py:61`), add three optional
form fields and parse each (a bad JSON shape is a 422, never a silent drop):

```python
    m1: str | None = Form(None),
    m2: str | None = Form(None),
    m3: str | None = Form(None),
```

Before the `run_in_threadpool` call:

```python
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
```

Pass `m1=m1_d, m2=m2_d, m3=m3_d` into the `generate_partner_report` call.

- [ ] **Step 4: Run to verify it passes**

Run: `cd api && ./run.sh pytest tests/test_partner_report.py -q`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/partner_report.py api/tests/test_partner_report.py
git commit -m "feat(partner): accept optional m1/m2/m3 JSON at the report route

Exposes the input contract over HTTP — a partner can pass a real topic/sources/
model to skip generation. Bad JSON is a 422, never a silent overwrite.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] Run the full affected suites:
  `cd api && ./run.sh pytest tests/test_compose_export.py tests/test_partner_report.py tests/test_m5_editor_router.py -q`
  and `cd api && ./run.sh pytest ../orchestrator/tests/test_agents_m5.py -q`
  Expected: all PASS (auto-mode + agent export paths unaffected except shared sanitation).
- [ ] Grep for stragglers: `grep -rn "_compose_chapters\|_has_sufficient_m4_data" api/ orchestrator/` returns nothing but the renamed `pdf_looks_like_analysis`.

## Notes / spec deviations

- **Spec said "both auto-mode and partner call `compose_and_export`."** In reality `run_export`
  is already shared by every surface, and auto-mode composes *all* sections via
  `compose_all_sections` inside its graph agent. So this plan unifies what's actually
  duplicated — the subset-compose loop (partner only, → `compose_and_export`), the prose
  sanitation (now shared via `compose_chapter`), and the M4 gate (now the one
  `assess_export_readiness` for both). Auto-mode adopts the shared **sanitation** and the
  shared **gate function** but keeps its own all-chapters compose call; fully routing
  auto-mode through `compose_and_export` is low value and deferred (would touch the graph
  agent for no behavior gain).
- The single `assess_export_readiness(store, chapters)` gate is the completeness core
  **Spec 2 (coaching layer)** will read for per-module status.

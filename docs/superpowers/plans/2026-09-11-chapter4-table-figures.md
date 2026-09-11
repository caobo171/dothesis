# Chapter 4 Table Figures Implementation Plan

> **STATUS: executed 2026-09-11** on branch `fix/chapter4-table-figures`
> (6 commits). The checkboxes below are the plan as written, not a live
> tracker. Three things the plan did not anticipate, all found by rendering
> end-to-end rather than by the unit tests, and all fixed in the commits:
>
> 1. `export_docx` uses **Pandoc**; `export_docx_basic` (what Tasks 3/7 test)
>    is only the fallback. Comment stripping had to move to a whole-text pass
>    (`_strip_html_comments`) because the closing sentinel shares a paragraph
>    with the source line.
> 2. Pandoc demotes `![](img)` to an inline unless a blank line follows, and
>    both engines caption a non-empty alt *below*. Final form is
>    `**caption**\n\n![](path)` — caption above, empty alt.
> 3. `weave()` places blocks at the writer's tokens, so the fixed per-kind
>    numbers came out `4.1, 4.4, 4.3` on the real chapter. Numbering now
>    follows document order (an extra change beyond the tasks below).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chapter 4 ships the student's real SmartPLS table screenshots in the Word/PDF export, captioned and numbered, with the transcribed numbers still committed to state so the verification gates keep working.

**Architecture:** The OCR pass already transcribes every embedded image (`agent/docx_extract.py`). Three things are missing and one is broken. Broken: `analysis_results` committed as a list makes `results_render` return no blocks at all, so `weave()` deletes the `[[DT:kind]]` tokens and the chapter ships table-less. Missing: the extractor discards the image bytes after OCR; nothing carries an image path into `analysis_results`; and the export writer has no HTML-comment branch, so the renderer's sentinels would print as literal text in Word the moment weaving starts working.

**Tech Stack:** Python 3.13, python-docx, pytest. `api/run.sh` forces the arm64 interpreter — always run tests through it, never `api/.venv/bin/*` directly.

**Spec:** This document. Derived from the live defect on project `4c5f769a-7d96-4056-9a5d-a4e3654116ac` (thread `269e7585-6d7b-4700-8d46-d64746d2cec4`), diagnosed 2026-09-11.

## Global Constraints

- `orchestrator/tools/results_render.py` is **pure and stdlib-only**. It MUST NOT import `m5_writing`, boto3, langchain, pandas or numpy — `agent/coherence.py:386` and `quality/similarity.py:236` import it lazily and fail-open. `os.path` / `pathlib` are fine.
- Every public function in `results_render.py` is `try/except` → log + return empty/None/input-unchanged. Keep that property.
- A path that reaches the renderer must have been resolved and containment-checked by deterministic code first. **Never trust a model-supplied absolute path.**
- Run tests with `api/run.sh pytest …` from the repo root. Tests importing `engine.*` need `sys.path.insert(0, str(Path(__file__).parent.parent / "engine"))` — the convention in `tests/test_checkpoint_benchmarks.py:23`.
- Per `CLAUDE.md`: any new API endpoint is `@router.post`. This plan adds none.
- Comment the reasoning behind each change, matching the density of the surrounding code.

---

### Task 1: Normalize the agent's list-shaped `analysis_results`

The blocker. `render_results_tables` bails on any non-dict (`results_render.py:398`) and the live project persisted a list, so Chapter 4 got zero tables from a complete SmartPLS run.

**Files:**
- Modify: `orchestrator/tools/results_render.py` (add `normalize_analysis_results`; call it in `detect_family:194` and `render_results_tables:387`)
- Modify: `tests/fixtures/renderer_blocks.py` (add `AGENT_LIST_BLOCK`)
- Test: `tests/test_results_render.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `normalize_analysis_results(analysis_results: Any) -> dict` — returns `{}` for anything it cannot map. Tasks 2 and 6 both call it.

- [ ] **Step 1: Add the real-world fixture**

Append to `tests/fixtures/renderer_blocks.py`. These are the exact values persisted by the live project — trimmed to three constructs and two hypotheses, key spellings preserved verbatim (`CR`, `AVE`, `alpha`, `rho_A`).

```python
# The shape the CHAT agent actually commits: a list of {id, source, results}
# step blocks, not the dict every consumer reads. skills/dothesis-m4-analysis
# declares `analysis_results: AnalysisResult[]` (an array) while showing a dict
# payload, and the agent followed the declaration. Values copied from project
# 4c5f769a-7d96-4056-9a5d-a4e3654116ac.
AGENT_LIST_BLOCK = [
    {"id": "measurement_model", "source": "user-provided SmartPLS report",
     "results": {
         "r2": {"DEC": 0.575, "INT": 0.527},
         "f2": {"ATT_to_INT": 0.137, "INT_to_DEC": 0.858},
         "htmt_max": 0.661,
         "vif_range": "1.000-1.025",
         "outer_loadings": "All reported indicators > 0.7",
         "reliability_validity": [
             {"construct": "ATT", "alpha": 0.878, "rho_A": 0.894, "CR": 0.911, "AVE": 0.671},
             {"construct": "DEC", "alpha": 0.911, "rho_A": 0.912, "CR": 0.933, "AVE": 0.737},
             {"construct": "INT", "alpha": 0.905, "rho_A": 0.906, "CR": 0.930, "AVE": 0.725},
         ]}},
    {"id": "hypothesis_tests", "source": "user-provided SmartPLS bootstrapping report",
     "results": [
         {"hypothesis": "H2", "path": "ATT → INT", "beta": 0.257, "t": 7.49,
          "sd": 0.034, "p": "<0.001", "decision": "supported"},
         {"hypothesis": "H7", "path": "INT → DEC", "beta": 0.606, "t": 13.367,
          "sd": 0.045, "p": "<0.001", "decision": "supported"},
     ]},
]
```

- [ ] **Step 2: Write the failing test**

Append to `tests/test_results_render.py`. Add `AGENT_LIST_BLOCK` to the existing `from tests.fixtures.renderer_blocks import (...)` list at the top of the file.

```python
def test_agent_list_shape_normalizes_and_renders():
    """The list shape the chat agent commits must reach the same tables the
    documented dict shape does — same numbers, different container."""
    from orchestrator.tools.results_render import normalize_analysis_results

    norm = normalize_analysis_results(AGENT_LIST_BLOCK)
    assert [c["construct"] for c in norm["measurement_model"]] == ["ATT", "DEC", "INT"]
    assert norm["measurement_model"][0]["cronbach_alpha"] == 0.878
    assert norm["measurement_model"][0]["composite_reliability"] == 0.911
    assert norm["measurement_model"][0]["ave"] == 0.671
    assert norm["structural_model"]["r2"] == {"DEC": 0.575, "INT": 0.527}
    # Flat beta/t/p must move under `numbers` — where _structural_block reads them.
    h2 = next(h for h in norm["hypothesis_tests"] if h["id"] == "H2")
    assert h2["numbers"]["beta"] == 0.257
    assert h2["numbers"]["t"] == 7.49
    assert h2["numbers"]["f2"] == 0.137      # merged from the f2 map by path
    assert h2["decision"] == "supported"

    assert detect_family(AGENT_LIST_BLOCK) == "pls_sem"
    kinds = {b["kind"] for b in render_results_tables(AGENT_LIST_BLOCK, "vi")}
    assert kinds == {"measurement_model", "structural_paths", "r2_q2"}


def test_normalize_leaves_documented_shape_untouched():
    from orchestrator.tools.results_render import normalize_analysis_results
    assert normalize_analysis_results(PLS_BLOCK) is PLS_BLOCK


def test_normalize_rejects_what_it_cannot_map():
    from orchestrator.tools.results_render import normalize_analysis_results
    assert normalize_analysis_results(FREE_TEXT_BLOCK) == {}
    assert normalize_analysis_results(None) == {}
    assert normalize_analysis_results([1, 2, 3]) == {}
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
api/run.sh pytest tests/test_results_render.py -k "agent_list or normalize" -v
```

Expected: FAIL with `ImportError: cannot import name 'normalize_analysis_results'`.

- [ ] **Step 4: Implement the normalizer**

Insert into `orchestrator/tools/results_render.py` immediately above `def detect_family` (line 194).

```python
# --- shape normalization ----------------------------------------------------
#
# Two shapes reach this module and only one was ever read. The documented block
# (skills/dothesis-m4-analysis/SKILL.md:217) is a dict keyed by table name; the
# chat agent commits a LIST of {id, source, results} steps, because the same
# skill declares `analysis_results: AnalysisResult[]` at line 12 and says
# "append to analysis_results" at line 206. Every consumer here — and
# claims_from_analysis_results, and coverage_findings — tests `isinstance(dict)`
# and silently sees nothing, so one real thesis exported a Results chapter with
# a complete SmartPLS run behind it and not one table in it.
#
# Coerce rather than reject: the student is mid-flow and the numbers are right,
# only the container is wrong. What cannot be mapped returns {} and the caller
# falls back exactly as before.

_CONSTRUCT_ALIASES = ("construct", "matrix", "name", "variable")
_CON_FIELDS = {
    "cronbach_alpha": ("cronbach_alpha", "alpha", "cronbachs_alpha"),
    "composite_reliability": ("composite_reliability", "cr", "composite"),
    "ave": ("ave", "average_variance_extracted"),
    "rho_a": ("rho_a",),
}
_ARROW_RE = re.compile(r"\s*(?:->|→|_to_)\s*")


def _lower_keys(d: dict) -> dict:
    return {str(k).lower(): v for k, v in d.items()}


def _pick(low: dict, names: tuple) -> Any:
    for n in names:
        if low.get(n) is not None:
            return low[n]
    return None


def _norm_path_key(value: Any) -> str:
    """"EXP → INT", "EXP -> INT" and "EXP_to_INT" are one path. Used only to
    line the f² map up with the hypothesis rows it belongs to."""
    return "->".join(p.strip().upper() for p in _ARROW_RE.split(str(value or "")) if p.strip())


def _constructs_from(payload: Any) -> list:
    """The list of per-construct reliability rows inside a step payload.

    The agent parks it under whatever the SmartPLS tab was called
    (`reliability_validity`, `constructs`, `rows`), so find it by SHAPE: a
    non-empty list of dicts that name a construct and carry at least one
    reliability statistic.
    """
    candidates = [payload] if isinstance(payload, list) else (
        list(payload.values()) if isinstance(payload, dict) else [])
    for value in candidates:
        if not (isinstance(value, list) and value):
            continue
        rows = [r for r in value if isinstance(r, dict)]
        if not rows:
            continue
        low = _lower_keys(rows[0])
        has_name = any(a in low for a in _CONSTRUCT_ALIASES)
        has_stat = any(_pick(low, names) is not None for names in _CON_FIELDS.values())
        if has_name and has_stat:
            return rows
    return []


def _constructs_block(rows: list) -> list:
    out = []
    for row in rows:
        low = _lower_keys(row)
        con = {"construct": _pick(low, _CONSTRUCT_ALIASES), "items": []}
        for target, names in _CON_FIELDS.items():
            value = _pick(low, names)
            if value is not None:
                con[target] = value
        out.append(con)
    return out


def _hypotheses_block(rows: Any, f2_map: dict) -> list:
    """Flat {beta, t, p} rows → the {id, path, numbers:{…}, decision} shape
    `_structural_block` reads. f² arrives as its own SmartPLS tab keyed by path,
    so fold it into the row it describes instead of dropping a whole column."""
    out = []
    for row in (rows if isinstance(rows, list) else []):
        if not isinstance(row, dict):
            continue
        low = _lower_keys(row)
        numbers = dict(low.get("numbers") or {})
        for key in ("beta", "t", "p", "f2", "se", "z"):
            if low.get(key) is not None:
                numbers.setdefault(key, low[key])
        path = low.get("path")
        if numbers.get("f2") is None:
            f2 = f2_map.get(_norm_path_key(path))
            if f2 is not None:
                numbers["f2"] = f2
        out.append({"id": _pick(low, ("id", "hypothesis")), "path": path,
                    "numbers": numbers, "decision": low.get("decision")})
    return out


def normalize_analysis_results(analysis_results: Any) -> dict:
    """The documented dict block, whatever shape the results arrived in.

    Returns the input unchanged when it is already a dict, a mapped block when
    it is the agent's list-of-steps, and {} for anything else (free text, a bare
    list of numbers) so callers keep their existing no-data behaviour.
    """
    try:
        if isinstance(analysis_results, dict):
            return analysis_results
        if not isinstance(analysis_results, list):
            return {}
        # Generic pass: an entry's `id` IS the block name for every kind whose
        # payload already matches (hypothesis_tests, descriptives, …).
        by_id: Dict[str, Any] = {}
        for entry in analysis_results:
            if isinstance(entry, dict) and entry.get("id") and entry.get("results") is not None:
                by_id.setdefault(str(entry["id"]), entry["results"])
        if not by_id:
            return {}

        out: Dict[str, Any] = {}
        structural: Dict[str, Any] = {}
        f2_map: Dict[str, Any] = {}

        for kind, payload in by_id.items():
            if isinstance(payload, dict):
                # R²/Q²/f² ride inside whichever step reported them.
                for key in ("r2", "q2"):
                    if isinstance(payload.get(key), dict):
                        structural.setdefault(key, payload[key])
                if isinstance(payload.get("f2"), dict):
                    f2_map.update({_norm_path_key(k): v for k, v in payload["f2"].items()})
                if isinstance(payload.get("tool"), str):
                    structural.setdefault("tool", payload["tool"])

        for kind, payload in by_id.items():
            if kind == "hypothesis_tests":
                continue                       # needs f2_map; done after this loop
            rows = _constructs_from(payload)
            if rows:
                out.setdefault("measurement_model", _constructs_block(rows))
            elif isinstance(payload, dict) and isinstance(payload.get("matrix"), list):
                out.setdefault("discriminant_validity", payload)

        if "hypothesis_tests" in by_id:
            tests = _hypotheses_block(by_id["hypothesis_tests"], f2_map)
            if tests:
                out["hypothesis_tests"] = tests
        if structural:
            out["structural_model"] = structural
        return out
    except Exception:
        logger.debug("normalize_analysis_results failed", exc_info=True)
        return {}
```

- [ ] **Step 5: Route both entry points through it**

In `detect_family` (line 194), replace:

```python
        ar = analysis_results
        if not isinstance(ar, dict):
            return None
```

with:

```python
        ar = normalize_analysis_results(analysis_results)
        if not ar:
            return None
```

In `render_results_tables` (line 397), replace:

```python
        ar = analysis_results
        if not isinstance(ar, dict):
            return []
```

with:

```python
        ar = normalize_analysis_results(analysis_results)
        if not ar:
            return []
```

Leave `fam = detect_family(ar)` on the line below as it is — it is now normalizing an already-normalized dict, which is the identity branch.

- [ ] **Step 6: Run the full renderer suite**

```bash
api/run.sh pytest tests/test_results_render.py tests/test_render_tool.py \
  tests/test_ensure_rendered.py tests/test_render_checker_integration.py \
  orchestrator/tests/test_results_render_family.py -v
```

Expected: PASS, including the pre-existing `test_results_render.py:123`
`assert render_results_tables(LEGACY_STEP_BLOCK) == []` — `LEGACY_STEP_BLOCK` is
a *dict* (`{"results": {"step1": …}}`), so it takes the identity branch, carries
no construct rows and no hypothesis list, and still renders nothing.

- [ ] **Step 7: Commit**

```bash
git add orchestrator/tools/results_render.py tests/fixtures/renderer_blocks.py tests/test_results_render.py
git commit -m "Render Chapter 4 tables when the agent commits results as a list"
```

---

### Task 2: Say so when the results block carries no readable table

Right now a list slips through every gate silently: `claims_from_analysis_results` returns `[]` for a non-dict, so the commit records `"numbers": {"total": 0}` on a full chapter of statistics and nobody is told.

**Files:**
- Modify: `agent/stats_validation.py:217` (`claims_from_analysis_results`), `:344` (`validate_analysis_results`)
- Test: `tests/test_stats_validation_block.py` (create if absent — check first with `ls tests/ | grep stats`)

**Interfaces:**
- Consumes: `normalize_analysis_results` from Task 1.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Write the failing test**

```python
from agent.stats_validation import validate_analysis_results
from tests.fixtures.renderer_blocks import AGENT_LIST_BLOCK, FREE_TEXT_BLOCK


def test_list_shape_now_yields_claims():
    """The agent's list shape must be verified, not waved through as 'nothing
    to check' — that is how a chapter of statistics committed with total=0."""
    out = validate_analysis_results(AGENT_LIST_BLOCK)
    assert not out["hard"]
    assert out["findings"] is not None


def test_unmappable_block_warns_instead_of_passing_silently():
    out = validate_analysis_results(FREE_TEXT_BLOCK)
    assert any(f["check"] == "structure.unstructured" for f in out["findings_soft"])


def test_bare_list_warns_too():
    out = validate_analysis_results([1, 2, 3])
    assert any(f["check"] == "structure.unstructured" for f in out["findings_soft"])
```

- [ ] **Step 2: Run it to verify it fails**

```bash
api/run.sh pytest tests/test_stats_validation_block.py -v
```

Expected: `test_bare_list_warns_too` FAILS — the soft finding is currently gated on `isinstance(block, str)`.

- [ ] **Step 3: Normalize before extracting claims**

In `claims_from_analysis_results` (line 217-219), replace:

```python
    if not isinstance(block, dict):
        return []
```

with:

```python
    # The agent's list-of-steps shape carries the same numbers in a different
    # container; reading it as "no claims" is how a full SmartPLS run committed
    # with analysis_provenance numbers.total = 0 and nothing verified.
    if not isinstance(block, dict):
        from orchestrator.tools.results_render import (  # noqa: PLC0415 — pure, stdlib-only
            normalize_analysis_results)
        block = normalize_analysis_results(block)
    if not block:
        return []
```

- [ ] **Step 4: Widen the unstructured warning**

In `validate_analysis_results` (line 350), replace:

```python
        if isinstance(block, str) and block.strip():
```

with:

```python
        # Was `isinstance(block, str)` only, so a LIST — the shape the chat
        # agent actually commits — passed with no claims and no warning.
        # Anything that does not normalize into a readable block warns.
        from orchestrator.tools.results_render import (  # noqa: PLC0415
            normalize_analysis_results)
        if block and not normalize_analysis_results(block):
```

and change that finding's `message` to:

```python
                "message": "Results are not stored as a readable results block, so the "
                           "numbers cannot be verified and Chapter 4 will have no tables.",
```

- [ ] **Step 5: Run the tests**

```bash
api/run.sh pytest tests/test_stats_validation_block.py tests/test_results_render.py -v
api/run.sh pytest tests/ -k "stats_validation or commit_slice" -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add agent/stats_validation.py tests/test_stats_validation_block.py
git commit -m "Warn when analysis results carry no readable table instead of committing silently"
```

---

### Task 3: Stop the renderer's sentinels printing into Word

Verified by running `export_docx_basic` on a woven block: the Word file contains a paragraph reading `<!--dt-rendered:begin kind=measurement_model sha=e3e425c7f9aa--> Bảng 4.1 — …`. It has never been seen because nothing has successfully woven a block into a shipped export yet. Task 1 makes weaving work, so this must land with it.

**Files:**
- Modify: `engine/utils/export_professional.py` (markdown walk at `:925`)
- Test: `tests/test_export_rendered_blocks.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing.

- [ ] **Step 1: Write the failing test**

```python
"""Renderer sentinels are internal markup and must never reach the document."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "engine"))
pytest.importorskip("docx")

from docx import Document  # noqa: E402
from engine.utils.export_professional import export_docx_basic  # noqa: E402

_MD = """# Chương 4

<!--dt-rendered:begin kind=measurement_model sha=e3e425c7f9aa-->
**Bảng 4.1 — Mô hình đo lường**

| Khái niệm | CR |
|---|---|
| ATT | 0.911 |
<!--dt-rendered:end kind=measurement_model-->
"""


def test_sentinels_do_not_reach_the_docx(tmp_path):
    md, out = tmp_path / "c4.md", tmp_path / "c4.docx"
    md.write_text(_MD, encoding="utf-8")
    assert export_docx_basic(md, out)

    doc = Document(str(out))
    body = "\n".join(p.text for p in doc.paragraphs)
    assert "dt-rendered" not in body
    assert "<!--" not in body
    # The caption survives as its own paragraph, and the table still renders.
    assert any("Bảng 4.1" in p.text for p in doc.paragraphs)
    assert len(doc.tables) == 1
```

- [ ] **Step 2: Run it to verify it fails**

```bash
api/run.sh pytest tests/test_export_rendered_blocks.py -v
```

Expected: FAIL on `assert "dt-rendered" not in body`.

- [ ] **Step 3: Drop comment lines in the markdown walk**

In `export_professional.py`, immediately after the blank-line branch (lines 929-931) and **before** the `if "$" in line:` branch, insert:

```python
            # HTML comments are internal markup, never document content. The
            # results renderer brackets every verified table in
            # `<!--dt-rendered:begin …-->` sentinels so the coherence and
            # similarity checkers can tell a computed table from a typed one;
            # without this branch those sentinels print into Word as body text,
            # and the one on the caption's line swallows the caption with it.
            if line.strip().startswith("<!--"):
                i += 1
                continue
```

- [ ] **Step 4: Run the test**

```bash
api/run.sh pytest tests/test_export_rendered_blocks.py -v
```

Expected: PASS.

- [ ] **Step 5: Check the PDF path is unaffected**

```bash
api/run.sh pytest tests/ -k "export" -v
```

Expected: PASS. Pandoc (the PDF engine) already treats `<!--…-->` as a raw HTML comment and drops it for non-HTML output, so only the python-docx writer needed the branch.

- [ ] **Step 6: Commit**

```bash
git add engine/utils/export_professional.py tests/test_export_rendered_blocks.py
git commit -m "Keep renderer sentinels out of the exported Word document"
```

---

### Task 4: Keep the transcribed image bytes

`_image_payload` hands bytes to the vision model and drops them (`docx_extract.py:101-120`). To put the real screenshot in the export, the bytes have to survive extraction.

**Files:**
- Modify: `agent/docx_extract.py:144` (`extract_docx_text`)
- Test: `agent/tests/test_docx_extract.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `extract_docx_text(data, *, transcribe_images=True, image_sink: list | None = None)`. When `image_sink` is a list, each successfully transcribed image appends
  `{"figure": int, "name": str, "bytes": bytes, "mime": str}` where `figure` is the `[Hình N]` number in the returned text. Task 5 consumes this.

- [ ] **Step 1: Write the failing test**

Append to `agent/tests/test_docx_extract.py`. Reuse the module's existing `_four_image_docx()` helper (referenced at `:210`) and its vision monkeypatching — read how `test_docx_extract.py:200-240` fakes `_vision_block` and follow the same approach.

```python
def test_image_sink_collects_bytes_for_transcribed_images(monkeypatch):
    """The export needs the original screenshot, not just its transcription."""
    monkeypatch.setattr("agent.docx_extract._vision_block",
                        lambda payload: "| A | B |\n|---|---|\n| 1 | 2 |")
    sink = []
    out = extract_docx_text(_four_image_docx(), image_sink=sink)

    assert len(sink) == 4
    assert [entry["figure"] for entry in sink] == [1, 2, 3, 4]
    assert all(entry["bytes"] for entry in sink)
    assert all(entry["mime"].startswith("image/") for entry in sink)
    # The figure number in the sink is the one printed in the text.
    assert "[Hình 1]" in out and "[Hình 4]" in out


def test_image_sink_skips_images_that_yielded_nothing(monkeypatch):
    """An image transcribed as NONE gets no [Hình n] slot, so it must not claim
    a sink entry either — the numbers have to line up."""
    monkeypatch.setattr("agent.docx_extract._vision_block", lambda payload: None)
    sink = []
    extract_docx_text(_four_image_docx(), image_sink=sink)
    assert sink == []


def test_image_sink_is_optional():
    extract_docx_text(_four_image_docx(), transcribe_images=False)  # no raise
```

- [ ] **Step 2: Run to verify it fails**

```bash
api/run.sh pytest agent/tests/test_docx_extract.py -k image_sink -v
```

Expected: FAIL with `TypeError: extract_docx_text() got an unexpected keyword argument 'image_sink'`.

- [ ] **Step 3: Implement**

Change the signature at `docx_extract.py:144`:

```python
def extract_docx_text(data: bytes, *, transcribe_images: bool = True,
                      image_sink: list | None = None) -> str:
```

Add to the docstring, after the `transcribe_images=False` paragraph:

```
    `image_sink`, when given a list, also receives the BYTES of every image that
    transcribed to something — `{"figure", "name", "bytes", "mime"}`, with
    `figure` matching the `[Hình n]` label in the returned text. The export
    embeds the student's original SmartPLS screenshot rather than a rebuilt
    table: a screenshot is visibly from the software, and a supervisor reads
    that as evidence in a way a retyped table is not.
```

Then extend the numbering loop at lines 232-233. Replace:

```python
        for n, slot_i in enumerate(sorted(filled), start=1):
            parts[slot_i] = f"[Hình {n}]\n{filled[slot_i]}"
```

with:

```python
        # `slots` is in document order and `filled` is keyed by slot index, so
        # sorting the surviving keys numbers the figures by page — the same
        # ordering the label promises — and lets the sink reuse that number.
        payload_by_slot = {slot_i: payload for slot_i, payload in slots}
        for n, slot_i in enumerate(sorted(filled), start=1):
            parts[slot_i] = f"[Hình {n}]\n{filled[slot_i]}"
            if image_sink is not None:
                name, blob, mime = payload_by_slot[slot_i]
                image_sink.append({"figure": n, "name": name, "bytes": blob, "mime": mime})
```

- [ ] **Step 4: Run the tests**

```bash
api/run.sh pytest agent/tests/test_docx_extract.py -v
```

Expected: PASS, all pre-existing tests included.

- [ ] **Step 5: Commit**

```bash
git add agent/docx_extract.py agent/tests/test_docx_extract.py
git commit -m "Keep the bytes of every transcribed docx image for the export"
```

---

### Task 5: Write the screenshots into the workspace beside the OCR sidecar

The agent reads `uploads/<name>.docx.txt` to see the transcriptions. Put the images next to it and name them in that text, so the agent can point a results block at one without any new plumbing.

**Files:**
- Modify: `api/app/routers/uploads.py:60` (`_extract_docx_text`), `:119` (`_extract_upload_text`), `:361-372` (workspace mirror)
- Test: `api/tests/test_uploads_router.py`

**Interfaces:**
- Consumes: `image_sink` from Task 4.
- Produces: images at `<workspace>/uploads/<safe_name>.img/hinh-NN.<ext>`, and a `(ảnh gốc: uploads/<safe_name>.img/hinh-NN.png)` marker on each `[Hình N]` line of the sidecar. Task 6 resolves those relative paths.

- [ ] **Step 1: Write the failing test**

Follow the existing `_docx_with_table_between_chapters()` pattern at `api/tests/test_uploads_router.py:324`.

```python
def test_docx_extraction_returns_images_for_the_workspace(monkeypatch):
    """The sidecar names the file each [Hình n] came from, so the agent can
    point a results block at the original screenshot."""
    monkeypatch.setattr("agent.docx_extract._vision_block",
                        lambda payload: "| A |\n|---|\n| 1 |")
    from app.routers.uploads import _extract_docx_text

    text, _pages, images = _extract_docx_text(_docx_with_one_image())
    assert len(images) == 1
    assert images[0]["figure"] == 1
    assert "[Hình 1] (ảnh gốc: " in text
    assert ".img/hinh-01." in text
```

Add a `_docx_with_one_image()` helper to that test module, built the same way `agent/tests/test_docx_extract.py` builds its image fixtures — import and reuse that helper if it is public, rather than duplicating the PNG bytes.

- [ ] **Step 2: Run to verify it fails**

```bash
api/run.sh pytest api/tests/test_uploads_router.py -k images_for_the_workspace -v
```

Expected: FAIL — `_extract_docx_text` returns a 2-tuple.

- [ ] **Step 3: Widen the extraction tuple**

`_extract_docx_text` at `:60` becomes:

```python
def _extract_docx_text(body: bytes, *, stem: str = "") -> tuple[str, int, list]:
```

Its body (replacing lines 84-85):

```python
    from agent.docx_extract import extract_docx_text  # noqa: PLC0415
    images: list = []
    text = extract_docx_text(body, image_sink=images)
    # Name the file each figure came from, inline in the sidecar the agent
    # reads. Without this the agent knows a table was transcribed but not which
    # screenshot backs it, and the export can only rebuild the table in
    # markdown — which reads as retyped rather than as SmartPLS output.
    for entry in images:
        entry["relpath"] = f"uploads/{stem}.img/{_figure_filename(entry)}"
        text = text.replace(
            f"[Hình {entry['figure']}]",
            f"[Hình {entry['figure']}] (ảnh gốc: {entry['relpath']})", 1)
    return text, 0, images
```

Add above it:

```python
_MIME_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif",
             "image/bmp": "bmp", "image/tiff": "tif", "image/webp": "webp"}


def _figure_filename(entry: dict) -> str:
    """`hinh-04.png` — zero-padded so a directory listing sorts by page."""
    ext = _MIME_EXT.get(str(entry.get("mime") or "").lower(), "png")
    return f"hinh-{int(entry['figure']):02d}.{ext}"
```

- [ ] **Step 4: Thread it through the caller**

`_extract_upload_text` at `:119` returns `tuple[str, int, list]`. Every `return` in it gains an empty list except the docx branch:

```python
    if mime == "application/pdf" or fname.endswith(".pdf"):
        text, pages = extract_pdf_text(body, ocr_if_hollow=True)
        return (text, pages, [])
    if mime == _DOCX_MIME or fname.endswith(".docx"):
        return _extract_docx_text(body, stem=(filename or "untitled").replace("/", "_"))
    if is_dataset(fname):
        return (profile_dataset(body, filename or "dataset"), 0, [])
    try:
        return (body.decode("utf-8", errors="ignore"), 1, [])
    except Exception:  # noqa: BLE001
        return ("", 0, [])
```

Update the unpack at `:335-336`:

```python
        text, page_count, images = await run_in_threadpool(
            _extract_upload_text, body, mime, fname, file.filename or "")
```

and give the reuse branch above it (`:330-331`) `images = []` so the variable is always bound.

Then in the workspace mirror (`:361-372`), after the `.txt` write at `:370`:

```python
        # The screenshots the OCR pass transcribed, beside the sidecar that
        # names them. The export embeds these originals in Chapter 4.
        if images:
            img_dir = workspace / "uploads" / f"{safe_name}.img"
            img_dir.mkdir(parents=True, exist_ok=True)
            for entry in images:
                (img_dir / _figure_filename(entry)).write_bytes(entry["bytes"])
```

- [ ] **Step 5: Fix the other call site**

`api/app/routers/tools.py:584` unpacks two values from `_extract_docx_text`. Update it:

```python
        text, page_count, _images = _extract_docx_text(body)
```

Check for any other unpack with `grep -rn "_extract_docx_text" api/` and fix each.

- [ ] **Step 6: Run the tests**

```bash
api/run.sh pytest api/tests/test_uploads_router.py -v
api/run.sh pytest api/tests/ -k "tools_router or upload" -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add api/app/routers/uploads.py api/app/routers/tools.py api/tests/test_uploads_router.py
git commit -m "Save transcribed docx screenshots into the project workspace"
```

---

### Task 6: Render the original screenshot instead of a rebuilt table

**Files:**
- Modify: `orchestrator/tools/results_render.py` (`_wrap:137` and the six block builders `:242-384`)
- Modify: `agent/tools/state_tools.py` (M4 commit, near the provenance block at `:380`)
- Test: `tests/test_results_render.py`, `tests/test_commit_figures.py` (create)

**Interfaces:**
- Consumes: the `uploads/<name>.img/hinh-NN.png` relpaths from Task 5; `normalize_analysis_results` from Task 1.
- Produces: `analysis_results["source_figures"]` — `{<block kind>: <absolute path>}`, resolved and containment-checked at commit. The renderer emits `![<caption>](<abs path>)` for any kind present there.

- [ ] **Step 1: Write the failing renderer test**

```python
def test_source_figure_replaces_the_rebuilt_table(tmp_path):
    """A real SmartPLS screenshot is evidence in a way a rebuilt table is not,
    so when one exists it IS the table."""
    png = tmp_path / "hinh-04.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")
    block = {**PLS_BLOCK, "source_figures": {"measurement_model": str(png)}}

    blocks = {b["kind"]: b for b in render_results_tables(block, "vi")}
    md = blocks["measurement_model"]["markdown"]
    assert f"]({png})" in md
    assert "Bảng 4.1" in md
    assert "\n|" not in md                    # the pipe table is gone
    assert "dt-rendered:begin kind=measurement_model" in md   # still verified state
    # Kinds without a screenshot keep rendering as tables.
    assert "\n|" in blocks["structural_paths"]["markdown"]


def test_missing_figure_falls_back_to_the_table(tmp_path):
    block = {**PLS_BLOCK, "source_figures": {"measurement_model": str(tmp_path / "gone.png")}}
    md = {b["kind"]: b for b in render_results_tables(block, "vi")}["measurement_model"]["markdown"]
    assert "\n|" in md
```

- [ ] **Step 2: Run to verify it fails**

```bash
api/run.sh pytest tests/test_results_render.py -k source_figure -v
```

Expected: FAIL — `source_figures` is ignored, so the markdown still holds a pipe table.

- [ ] **Step 3: Implement the image body in the renderer**

Add above `_wrap` (line 137):

```python
def _figure_body(ar: dict, kind: str, caption: str) -> str | None:
    """The student's own screenshot of this table as a markdown image line, or
    None when there isn't one on disk.

    Why the image wins over the table we can render: the screenshot is visibly
    SmartPLS output. A supervisor reads that as evidence; a rebuilt table reads
    as numbers someone typed. The transcription still lives in state, so the
    coherence gate keeps checking the prose against it either way.

    The path is checked for existence here, and was resolved + contained under
    the project workspace by commit_slice — this module never trusts a path far
    enough to build one.
    """
    try:
        import os  # noqa: PLC0415 — stdlib, keeps this module import-light
        figures = ar.get("source_figures")
        path = figures.get(kind) if isinstance(figures, dict) else None
        if not (isinstance(path, str) and path and os.path.isfile(path)):
            return None
        return f"**{caption}**\n\n![{caption}]({path})"
    except Exception:
        logger.debug("_figure_body failed for %s", kind, exc_info=True)
        return None
```

Then in each of the six builders, replace the `body = f"**{caption}**\n\n" + _table…` line with a figure-first version. `_measurement_block` (line 276-277) becomes:

```python
    body = _figure_body(ar, "measurement_model", caption) or (
        f"**{caption}**\n\n" + _table_pruned(
            [H["construct"], H["item"], loading_hdr, H["alpha"], H["cr"], H["ave"]], rows))
```

Apply the same `_figure_body(ar, "<kind>", caption) or (…)` wrapping in `_discriminant_block` (`:298`, kind `discriminant_validity`), `_model_fit_block` (`:312`, `model_fit`), `_structural_block` (`:346`, `structural_paths`), `_r2q2_block` (`:367`, `r2_q2`) and `_descriptives_block` (`:383`, `descriptives`).

`_discriminant_block` builds its title separately — there, use
`_figure_body(ar, "discriminant_validity", title.strip("*")) or (title + "\n\n" + _table(…))`.

Note `_measurement_block`'s caption switches between `measurement_model` and `scale_reliability`; key `source_figures` off the fixed kind `"measurement_model"` there, matching the `_wrap` kind that the sentinel and `weave()` already use.

- [ ] **Step 4: Write the failing commit test**

Create `tests/test_commit_figures.py`:

```python
"""source_figures must be resolved by code and contained in the workspace —
a model-supplied absolute path is not something to hand a file reader."""
from agent.tools.state_tools import _resolve_source_figures


def test_relative_path_resolves_under_the_workspace(tmp_path):
    (tmp_path / "uploads" / "r.docx.img").mkdir(parents=True)
    png = tmp_path / "uploads" / "r.docx.img" / "hinh-04.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")

    out = _resolve_source_figures(
        {"measurement_model": "uploads/r.docx.img/hinh-04.png"}, str(tmp_path))
    assert out == {"measurement_model": str(png)}


def test_escaping_path_is_dropped(tmp_path):
    assert _resolve_source_figures(
        {"measurement_model": "../../../etc/passwd"}, str(tmp_path)) == {}


def test_absolute_path_outside_the_workspace_is_dropped(tmp_path):
    assert _resolve_source_figures(
        {"measurement_model": "/etc/hosts"}, str(tmp_path)) == {}


def test_missing_file_is_dropped(tmp_path):
    assert _resolve_source_figures(
        {"measurement_model": "uploads/nope.png"}, str(tmp_path)) == {}


def test_no_project_dir_drops_everything(tmp_path):
    assert _resolve_source_figures({"measurement_model": "uploads/x.png"}, None) == {}
```

- [ ] **Step 5: Run to verify it fails**

```bash
api/run.sh pytest tests/test_commit_figures.py -v
```

Expected: FAIL with `ImportError: cannot import name '_resolve_source_figures'`.

- [ ] **Step 6: Implement the resolver**

Add to `agent/tools/state_tools.py`, at module level near the other helpers:

```python
def _resolve_source_figures(figures: Any, project_dir: Any) -> dict:
    """Workspace-relative figure paths → absolute paths that exist, dropping
    anything that escapes the workspace.

    The model names a file it saw in the sidecar; deterministic code decides
    whether that name points at a real file inside this project. A path is the
    one piece of state a model supplies that a later step opens, so it is
    resolved and contained here rather than trusted downstream.
    """
    import os  # noqa: PLC0415

    if not (isinstance(figures, dict) and project_dir):
        return {}
    root = os.path.realpath(str(project_dir))
    out = {}
    for kind, rel in figures.items():
        if not isinstance(rel, str) or not rel:
            continue
        full = os.path.realpath(os.path.join(root, rel))
        if not (full == root or full.startswith(root + os.sep)):
            logger.warning("commit_slice: source_figures[%s] escapes the workspace", kind)
            continue
        if os.path.isfile(full):
            out[str(kind)] = full
    return out
```

Then wire it into the M4 commit. Insert immediately **before** the provenance block at `:380` (`if module == "M4" and "analysis_results" in writes:`), so the stored block already carries resolved paths:

```python
        # Resolve the screenshot paths the agent named in the results block.
        # Before provenance so what gets attributed is what gets stored.
        if module == "M4" and isinstance(writes.get("analysis_results"), dict) \
                and writes["analysis_results"].get("source_figures"):
            _ar = writes["analysis_results"]
            _figs = _resolve_source_figures(_ar["source_figures"],
                                            getattr(store, "project_dir", None))
            writes = {**writes, "analysis_results": {**_ar, "source_figures": _figs}}
```

- [ ] **Step 7: Run everything**

```bash
api/run.sh pytest tests/test_commit_figures.py tests/test_results_render.py \
  tests/test_render_tool.py tests/test_ensure_rendered.py -v
api/run.sh pytest tests/ -k "commit_slice or state_tools" -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add orchestrator/tools/results_render.py agent/tools/state_tools.py \
        tests/test_results_render.py tests/test_commit_figures.py
git commit -m "Put the student's SmartPLS screenshot in Chapter 4 instead of a rebuilt table"
```

---

### Task 7: Caption a table image above it, not below

`_add_docx_image` always puts the caption under the picture in italic 10pt — figure styling. A table caption belongs above the table.

**Files:**
- Modify: `engine/utils/export_professional.py:650` (`_add_docx_image`)
- Test: `tests/test_export_rendered_blocks.py` (from Task 3)

**Interfaces:**
- Consumes: the `![Bảng 4.1 — …](path)` lines Task 6 emits.
- Produces: nothing.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_export_rendered_blocks.py`:

```python
def _png(path):
    """Smallest valid 1x1 PNG — python-docx must be able to measure it."""
    import base64
    path.write_bytes(base64.b64decode(
        b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="))
    return path


def test_table_image_caption_sits_above_the_picture(tmp_path):
    img = _png(tmp_path / "hinh-04.png")
    md, out = tmp_path / "c4.md", tmp_path / "c4.docx"
    md.write_text(f"# Chương 4\n\n![Bảng 4.1 — Mô hình đo lường]({img})\n", encoding="utf-8")
    assert export_docx_basic(md, out)

    doc = Document(str(out))
    texts = [p.text for p in doc.paragraphs]
    cap = next(i for i, t in enumerate(texts) if "Bảng 4.1" in t)
    pic = next(i for i, p in enumerate(doc.paragraphs) if p.runs
               and any("graphic" in r._r.xml for r in p.runs))
    assert cap < pic, "a table caption goes above the table"


def test_figure_image_caption_stays_below(tmp_path):
    img = _png(tmp_path / "model.png")
    md, out = tmp_path / "c3.md", tmp_path / "c3.docx"
    md.write_text(f"# Chương 3\n\n![Hình 3.1. Mô hình nghiên cứu]({img})\n", encoding="utf-8")
    assert export_docx_basic(md, out)

    doc = Document(str(out))
    texts = [p.text for p in doc.paragraphs]
    cap = next(i for i, t in enumerate(texts) if "Hình 3.1" in t)
    pic = next(i for i, p in enumerate(doc.paragraphs) if p.runs
               and any("graphic" in r._r.xml for r in p.runs))
    assert pic < cap, "a figure caption goes below the figure"
```

- [ ] **Step 2: Run to verify it fails**

```bash
api/run.sh pytest tests/test_export_rendered_blocks.py -k caption -v
```

Expected: `test_table_image_caption_sits_above_the_picture` FAILS (caption index > picture index).

- [ ] **Step 3: Implement**

Rewrite `_add_docx_image` (`:650-667`):

```python
_TABLE_CAPTION_RE = _re.compile(r"^\s*(?:Bảng|Bang|Table|Tabelle)\b", _re.IGNORECASE)


def _add_docx_image(doc, path: str, caption: str) -> bool:
    """Place a picture on its own centred paragraph with its caption.

    A figure is captioned below it and a table above it — the convention every
    Vietnamese thesis template follows, and a supervisor's first-page check. The
    caption text says which it is, because the results renderer writes "Bảng
    4.1 — …" for a table screenshot and "Hình 3.1. …" for a diagram.
    """
    from pathlib import Path as _P
    from docx.shared import Inches as _Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH as _AL
    p = _P(path)
    if not p.exists():
        return False

    def _caption_para():
        cap = doc.add_paragraph()
        cap.alignment = _AL.CENTER
        r = cap.add_run(caption)
        r.italic = True
        r.font.size = _docx_pt(10)

    is_table = bool(caption and _TABLE_CAPTION_RE.match(caption))
    if caption and is_table:
        _caption_para()
    para = doc.add_paragraph()
    para.alignment = _AL.CENTER
    para.add_run().add_picture(str(p), width=_Inches(6.0))
    if caption and not is_table:
        _caption_para()
    return True
```

- [ ] **Step 4: Run the tests**

```bash
api/run.sh pytest tests/test_export_rendered_blocks.py -v
api/run.sh pytest tests/ -k "export or figure" -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/utils/export_professional.py tests/test_export_rendered_blocks.py
git commit -m "Caption a table screenshot above it and a figure below it"
```

---

### Task 8: Fix the M4 skill contract that produced the wrong shape

The agent wrote a list because the skill told it to. `skills/dothesis-m4-analysis/SKILL.md:12` declares `analysis_results: AnalysisResult[]` and `:206` says "append to `analysis_results`", while `:217` shows the dict every consumer reads. Task 1 makes both work; the skill should still stop asking for the one that loses data, and should start asking for the screenshots.

**Files:**
- Modify: `skills/dothesis-m4-analysis/SKILL.md:12`, `:206-207`, `:217-240`
- Test: none (documentation). Verified by the Task 1 and Task 6 tests.

**Interfaces:**
- Consumes: `source_figures` from Task 6.
- Produces: nothing.

- [ ] **Step 1: Fix the type declaration at line 12**

Replace:

```
- `analysis_results: AnalysisResult[]` — actual numbers + per-test interpretation
```

with:

```
- `analysis_results: AnalysisResultBlock` — ONE dict keyed by table
  (`measurement_model`, `hypothesis_tests`, `discriminant_validity`,
  `structural_model`, `descriptives`), not a list of steps. M5 renders Chapter
  4 from these keys; a list of `{id, results}` step entries used to render
  nothing at all.
```

- [ ] **Step 2: Fix the per-step instruction at lines 206-207**

Replace:

```
Per step: call `run_stats`, capture the returned numbers verbatim, append to
`analysis_results`.
```

with:

```
Per step: call `run_stats`, capture the returned numbers verbatim, and MERGE
them into the `analysis_results` dict under the table key they belong to. Merge,
never append — `analysis_results` is one block, not a log of steps.
```

- [ ] **Step 3: Document `source_figures` after the JSON example at line 240**

Add:

```markdown
**When the numbers came from a screenshot, name the screenshot.** An uploaded
.docx of SmartPLS output is transcribed image by image, and the sidecar
(`uploads/<name>.docx.txt`) labels each one:

    [Hình 4] (ảnh gốc: uploads/_Result.docx.img/hinh-04.png)

Put those paths on `source_figures`, keyed by the table each image shows:

```json
"source_figures": {
  "measurement_model": "uploads/_Result.docx.img/hinh-04.png",
  "discriminant_validity": "uploads/_Result.docx.img/hinh-05.png",
  "structural_paths": "uploads/_Result.docx.img/hinh-09.png"
}
```

Chapter 4 then carries the student's own SmartPLS screenshot instead of a table
rebuilt from the transcription — which is what a supervisor recognizes as
output. Paths are workspace-relative; `commit_slice` resolves them and drops any
that don't exist. The kinds are `descriptives`, `measurement_model`,
`discriminant_validity`, `model_fit`, `structural_paths`, `r2_q2`.

**Store the transcribed rows too, always — a screenshot does not replace them.**
The coherence gate compares your prose against these numbers, so a block with
only an image is a chapter nobody can check.
```

- [ ] **Step 4: Strengthen the completeness rule at line 250**

After the existing bullet `A reliability/validity value (α, CR, AVE, loading) is required for **every** construct…`, add:

```
- **Never summarize a table you were given.** A transcribed SmartPLS table comes
  back with every row; writing `"outer_loadings": "all > 0.7, range 0.766-0.863"`
  throws away 41 rows that were already read for you, and Table 4.1 then cannot
  be rendered at all. Copy the rows.
```

- [ ] **Step 5: Verify the skill still loads**

```bash
api/run.sh pytest tests/ -k "skill" -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add skills/dothesis-m4-analysis/SKILL.md
git commit -m "Stop the M4 skill asking for the results shape that renders nothing"
```

---

## Verification

After Task 8, confirm the whole path end to end against the live project rather than fixtures:

```bash
api/run.sh pytest tests/ agent/tests/ api/tests/ orchestrator/tests/ -q
```

Then re-render the real block and confirm it produces the tables the shipped
docx is missing:

```bash
api/run.sh python - <<'PY'
import json
from sqlalchemy import create_engine, text
from orchestrator.tools.results_render import render_results_tables

P = '/Users/caonguyenvan/project/dothesis/'
url = [l.split('=', 1)[1].strip() for l in open(P + '.env')
       if l.startswith('DATABASE_URL=')][0]
with create_engine(url).connect() as c:
    m4 = c.execute(text("select m4_analysis from context_store "
                        "where project_id::text=:p"),
                   {"p": "4c5f769a-7d96-4056-9a5d-a4e3654116ac"}).scalar()
if isinstance(m4, str):
    m4 = json.loads(m4)
blocks = render_results_tables(m4["analysis_results"], "vi")
print("kinds:", [b["kind"] for b in blocks])
print(blocks[0]["markdown"][:400] if blocks else "STILL EMPTY")
PY
```

Expected: `kinds: ['measurement_model', 'structural_paths', 'r2_q2']` — three
tables from a block that renders none today.

## Known gaps this plan does not close

- **Per-item outer loadings for this project.** The transcription holds 41
  loading rows, but the committed block summarized them into a sentence, so
  Table 4.1 renders construct-level α/CR/AVE only. Recovering the rows means
  re-reading `uploads/_Result.docx.txt` in a fresh M4 pass — a data repair for
  one project, not a code change.
- **`rho_A` has no column.** `_HEADERS` (`results_render.py:34`) has no `rho_a`
  entry, so the normalizer stores it and `_measurement_block` drops it. Standard
  in a SmartPLS reliability table; add the column in a follow-up.
- **TRUST_1–5 came back blank and one image's headers read `[unreadable]`.**
  Vision transcription is lossy on some crops. The screenshot path Task 6 adds
  is the mitigation — the image is right even where its transcription isn't.

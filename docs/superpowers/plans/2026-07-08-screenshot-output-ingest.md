# Screenshot / Image Output Ingest Implementation Plan (F13)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Turn a SmartPLS/SPSS/AMOS results table (screenshot OR HTML/xlsx export) into structured rows the F8 Output Sanity Layer can classify.

**Architecture:** Two tools that take a **workspace file path** (like `run_stats` — a model can't supply bytes): a deterministic export parser (preferred) and a vision parser using the real `agent/multimodal.build_user_message` + `Attachment.from_path` + Gemini `_get_llm()`. Both emit `{table_kind, rows}` → F8's `check_thresholds`.

**Tech Stack:** Python, `agent/multimodal` (`build_user_message`, `Attachment.from_path`), `pandas`(+`lxml`)/`openpyxl`, F8 `check_thresholds`, pytest via `./run.sh` (no real vision API in tests).

## Global Constraints

- **Tools take file paths, never bytes/base64 args** the model fills. Resolve within the project workspace like `run_stats` (`agent/tools/stats.py:131`).
- **Never fabricate a value** — unreadable cells `null` + flagged.
- **Real multimodal API only** — `build_user_message(text, attachments, provider)` + `Attachment.from_path`; provider `"google"` to match `_get_llm()` (Gemini). NO `model_message_for` (doesn't exist).
- No real vision/API in tests (stub `_vision_read`). Comment the decision behind each change.

---

### Task 1: `parse_smartpls_export(file)` — deterministic (ships first)

**Files:**
- Create: `agent/tools/output_parse.py`
- Test: `api/tests/test_output_parse.py`

**Interfaces:**
- Produces: `parse_smartpls_export(file: str) -> str` (json `{table_kind, rows}`), `infer_table_kind(headers) -> str`, and `_load_bytes(file) -> bytes` (workspace resolver; tests stub it).

- [ ] **Step 1: Write the failing test (call `.func`, stub the loader)**

```python
# api/tests/test_output_parse.py
import json
import agent.tools.output_parse as op
from agent.tools.output_parse import infer_table_kind


def test_infer_table_kind():
    assert infer_table_kind(["Construct", "HTMT"]) == "htmt"
    assert infer_table_kind(["Item", "Outer loading"]) == "loadings"


def test_parse_html_htmt(monkeypatch):
    html = ("<table><tr><th>pair</th><th>HTMT</th></tr>"
            "<tr><td>BI-ATT</td><td>0.91</td></tr></table>").encode()
    monkeypatch.setattr(op, "_load_bytes", lambda f: html)
    out = json.loads(op.parse_smartpls_export.func(file="report.html"))
    assert out["table_kind"] == "htmt" and out["rows"][0]["value"] == 0.91
```

- [ ] **Step 2: Run to verify it fails** → `cd api && ./run.sh pytest tests/test_output_parse.py -q` → FAIL.

- [ ] **Step 3: Implement**

```python
# agent/tools/output_parse.py
"""Parse SmartPLS/SPSS result tables into {table_kind, rows} for the F8 sanity layer. Tools take a
workspace FILE PATH (a model can't supply bytes). Transcribes values; never computes them."""
from __future__ import annotations
import io
import json
from pathlib import Path

from langchain_core.tools import tool

_KIND_HINTS = {
    "htmt": ("htmt", "heterotrait"), "loadings": ("outer loading", "factor loading", "loading"),
    "fornell_larcker": ("fornell", "larcker"), "vif": ("vif",),
    "path_coeffs": ("path coefficient", "original sample", "t statistic"),
    "fit_indices": ("cfi", "rmsea", "tli", "srmr"), "ave": ("ave", "average variance"),
    "cr": ("composite reliability",),
}


def infer_table_kind(headers: list[str]) -> str:
    joined = " ".join(str(h).lower() for h in headers)
    for kind, hints in _KIND_HINTS.items():
        if any(h in joined for h in hints):
            return kind
    return "unknown"


def _load_bytes(file: str) -> bytes:
    """Resolve `file` in the project workspace (uploads dir), like run_stats. Isolated for tests."""
    from agent.tools.stats import _resolve_upload_path  # noqa: PLC0415 — reuse run_stats' resolver
    return Path(_resolve_upload_path(file)).read_bytes()


def _num(x):
    try:
        return float(str(x).replace(",", "."))
    except (ValueError, TypeError):
        return None


def _rows(headers: list[str], data: list[list]) -> list[dict]:
    out = []
    for r in data:
        label = str(r[0]) if r else "?"
        nums = [_num(c) for c in r[1:]]
        present = [n for n in nums if n is not None]
        if len(present) <= 1:                       # row-oriented table
            out.append({"item": label, "value": present[0] if present else None})
        else:                                        # matrix row — keep all values
            out.append({"item": label, "values": nums})
    return out


@tool
def parse_smartpls_export(file: str) -> str:
    """Parse a SmartPLS/SPSS HTML or .xlsx results export (a file in the workspace) into
    {table_kind, rows}. Preferred over a screenshot when the student has the file."""
    name = (file or "").lower()
    try:
        content = _load_bytes(file)
        if name.endswith((".xlsx", ".xls")):
            import openpyxl  # noqa: PLC0415
            ws = openpyxl.load_workbook(io.BytesIO(content), data_only=True).active
            grid = [[c.value for c in row] for row in ws.iter_rows()]
        else:
            import pandas as pd  # noqa: PLC0415 — needs lxml
            df = pd.read_html(io.BytesIO(content))[0]
            grid = [list(df.columns)] + df.values.tolist()
        headers = [str(h) for h in grid[0]]
        return json.dumps({"table_kind": infer_table_kind(headers), "rows": _rows(headers, grid[1:])},
                          ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"couldn't parse export: {e}",
                           "hint": "paste the values or upload a screenshot"}, ensure_ascii=False)
```

> **Note:** add `lxml` to `api/pyproject.toml`; confirm `_resolve_upload_path` is the real helper
> `run_stats` uses to locate an uploaded file (adapt the name to what `agent/tools/stats.py` exposes).

- [ ] **Step 4: Run to verify it passes** → PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/tools/output_parse.py api/tests/test_output_parse.py api/pyproject.toml
git commit -m "feat(m4): parse SmartPLS HTML/xlsx export (workspace path) -> {table_kind, rows}

Deterministic path from a real export to the F8 sanity layer; matrix rows kept.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `parse_output_table(file)` — vision (real multimodal API, stubbed in tests)

**Files:**
- Modify: `agent/tools/output_parse.py`
- Test: `api/tests/test_output_parse.py`

**Interfaces:**
- Produces: `parse_output_table(file: str) -> str`; vision behind `_vision_read(file) -> str` (stubbed in tests).

- [ ] **Step 1: Write the failing test**

```python
# add to api/tests/test_output_parse.py
def test_vision_ok(monkeypatch):
    monkeypatch.setattr(op, "_vision_read",
                        lambda f: '{"table_kind":"loadings","rows":[{"item":"X1","value":0.74}]}')
    out = json.loads(op.parse_output_table.func(file="shot.png"))
    assert out["table_kind"] == "loadings" and out["rows"][0]["value"] == 0.74


def test_vision_junk(monkeypatch):
    monkeypatch.setattr(op, "_vision_read", lambda f: "the image is blurry")
    out = json.loads(op.parse_output_table.func(file="shot.png"))
    assert out.get("error") or out.get("needs_confirmation")
```

- [ ] **Step 2: Run to verify it fails** → FAIL.

- [ ] **Step 3: Implement (real `build_user_message` + `Attachment.from_path` + Gemini)**

```python
# add to agent/tools/output_parse.py
_VISION_PROMPT = ("Transcribe ONLY the visible results table into STRICT JSON "
                  '{"table_kind": "...", "rows": [{"item": "", "value": <number or null>}]}. '
                  "Do NOT invent numbers; mark unreadable cells null. No prose.")


def _vision_read(file: str) -> str:
    """Read a results-table image via Gemini. Isolated so tests stub it."""
    from agent.multimodal import Attachment, build_user_message  # noqa: PLC0415 (real API)
    from orchestrator.tools.m5_writing import _get_llm  # noqa: PLC0415 (Gemini)
    att = Attachment.from_path(_resolve_path(file))
    msg = build_user_message(_VISION_PROMPT, [att], provider="google")  # provider matches _get_llm
    return str(getattr(_get_llm().invoke([msg]), "content", ""))


def _resolve_path(file: str) -> str:
    from agent.tools.stats import _resolve_upload_path  # noqa: PLC0415
    return _resolve_upload_path(file)


@tool
def parse_output_table(file: str) -> str:
    """Parse a SCREENSHOT (a workspace image file) of a SmartPLS/SPSS/AMOS results table into
    {table_kind, rows}. Prefer parse_smartpls_export if the student has the file. Never invents
    numbers; low-confidence parses ask the student to confirm."""
    raw = _vision_read(file)
    s, e = raw.find("{"), raw.rfind("}")
    if s == -1 or e == -1:
        return json.dumps({"error": "couldn't read a table in that image",
                           "hint": "paste the values or upload the SmartPLS HTML export"})
    try:
        data = json.loads(raw[s:e + 1])
    except Exception:
        return json.dumps({"needs_confirmation": True, "raw": raw[:300]})
    if not data.get("rows"):
        return json.dumps({"needs_confirmation": True, "parsed": data})
    return json.dumps(data, ensure_ascii=False)
```

> **Note:** verify `build_user_message`'s exact signature/`provider` values in `agent/multimodal.py`
> (`Provider` type at ~line 218); the contract is prompt + image attachment → a Gemini `HumanMessage`.

- [ ] **Step 4: Run to verify it passes** → PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/tools/output_parse.py api/tests/test_output_parse.py
git commit -m "feat(m4): vision parse of results screenshots (real multimodal API)

Workspace image -> Gemini via build_user_message/Attachment.from_path -> rows;
unreadable cells asked, never guessed.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Wire to F8 + M4 skill (end-to-end)

**Files:**
- Modify: `agent/runtime.py` (register both tools in the `build_agent` tool list), `skills/dothesis-m4-analysis/SKILL.md`
- Test: `api/tests/test_output_parse.py`

- [ ] **Step 1: Write the failing end-to-end test** (needs F8's `check_thresholds`)

```python
# add to api/tests/test_output_parse.py
def test_export_feeds_check_thresholds(monkeypatch):
    from agent.tools.stats import check_thresholds     # F8
    html = "<table><tr><th>pair</th><th>HTMT</th></tr><tr><td>BI-ATT</td><td>0.91</td></tr></table>".encode()
    monkeypatch.setattr(op, "_load_bytes", lambda f: html)
    parsed = json.loads(op.parse_smartpls_export.func(file="r.html"))
    flags = json.loads(check_thresholds.func(table_kind=parsed["table_kind"], rows=parsed["rows"]))
    assert any("discriminant" in f["issue"].lower() for f in flags["findings"])
```

- [ ] **Step 2: Run to verify it fails** (until F8 lands) → FAIL/ERROR.

- [ ] **Step 3: Register + wire**

Add `parse_smartpls_export` and `parse_output_table` to the tool list in `agent/runtime.py`'s
`build_agent` (the `tools = [...]` block at `runtime.py:448`). In
`skills/dothesis-m4-analysis/SKILL.md`: "When the student attaches an image or export of results,
call `parse_output_table` / `parse_smartpls_export` → `check_thresholds` → narrate with the
output-interpretation + two-register content. Low-confidence parse → show it back to confirm first."

- [ ] **Step 4: Run to verify it passes** → PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/runtime.py skills/dothesis-m4-analysis/SKILL.md api/tests/test_output_parse.py
git commit -m "feat(m4): wire output parsers to the F8 sanity layer

Screenshot/export -> parsed rows -> check_thresholds -> grounded narration.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] `cd api && ./run.sh pytest tests/test_output_parse.py -q` → PASS (incl. F8 end-to-end).
- [ ] No real vision API in tests (`_vision_read`/`_load_bytes` stubbed); no bytes/positional tool calls (all `.func(file=…)`).
- [ ] Layering clean: `grep -rn "^from app" agent/tools/output_parse.py` → nothing.

## Notes

- **Depends on F8** (`check_thresholds` + output-interpretation content) — build F8 first or land
  Task 3 when F8 lands.
- Deterministic export parse (Task 1) is the reliable default; vision (Task 2) is the convenience
  path with confirm-on-low-confidence.

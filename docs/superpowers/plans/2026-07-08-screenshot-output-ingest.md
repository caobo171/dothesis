# Screenshot / Image Output Ingest Implementation Plan (F13)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Turn a screenshot (or SmartPLS HTML/Excel export) of a results table into structured rows the F8 Output Sanity Layer can classify — so the flagship correctness feature survives real student input.

**Architecture:** A deterministic export parser (preferred) + a vision parser (multimodal model, already wired) both produce `{table_kind, rows}`; the M4 skill feeds them to `check_thresholds` (F8) and narrates from the grounded result. Low-confidence cells are confirmed, never guessed.

**Tech Stack:** Python, `agent/multimodal` (Gemini/Claude vision), `pandas`/`openpyxl`, F8 `check_thresholds`, pytest via `./run.sh` (vision + no real API in tests).

## Global Constraints

- **Never fabricate a value** — unreadable cells are `null` + flagged.
- **Deterministic export parse preferred** over vision when the student has the file.
- **No real vision/API in tests** — the model call is stubbed.
- **Comment the decision behind each change.**

---

### Task 1: `parse_smartpls_export` (deterministic — ships first)

**Files:**
- Create: `agent/tools/output_parse.py`
- Test: `api/tests/test_output_parse.py`

**Interfaces:**
- Produces: `parse_smartpls_export(content: bytes, filename: str) -> str` (json `{table_kind, rows}`), and a shared `infer_table_kind(headers: list[str]) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_output_parse.py
import json
from agent.tools.output_parse import parse_smartpls_export, infer_table_kind


def test_infer_table_kind():
    assert infer_table_kind(["Construct", "HTMT"]) == "htmt"
    assert infer_table_kind(["Item", "Outer loading"]) == "loadings"


def test_parse_html_htmt_table():
    html = ("<table><tr><th>pair</th><th>HTMT</th></tr>"
            "<tr><td>BI-ATT</td><td>0.91</td></tr></table>")
    out = json.loads(parse_smartpls_export(html.encode(), "report.html"))
    assert out["table_kind"] == "htmt"
    assert out["rows"][0]["value"] == 0.91
```

- [ ] **Step 2: Run to verify it fails** → FAIL.

- [ ] **Step 3: Implement**

```python
# agent/tools/output_parse.py
"""Parse SmartPLS/SPSS result tables into {table_kind, rows} for the F8 sanity layer. Deterministic
export parse (HTML/xlsx) + a vision fallback (Task 2). Transcribes values; never computes them."""
from __future__ import annotations
import json
from langchain_core.tools import tool

_KIND_HINTS = {
    "htmt": ("htmt", "heterotrait"), "loadings": ("outer loading", "factor loading", "loading"),
    "fornell_larcker": ("fornell", "larcker"), "vif": ("vif",),
    "path_coeffs": ("path coefficient", "original sample", "t statistic"),
    "fit_indices": ("cfi", "rmsea", "tli", "srmr"), "ave": ("ave", "average variance"),
    "cr": ("composite reliability",),
}


def infer_table_kind(headers: list[str]) -> str:
    joined = " ".join(h.lower() for h in headers)
    for kind, hints in _KIND_HINTS.items():
        if any(h in joined for h in hints):
            return kind
    return "unknown"


def _rows_from_matrix(headers: list[str], data: list[list]) -> list[dict]:
    val_col = next((i for i, h in enumerate(headers) if i > 0), 1)
    out = []
    for r in data:
        try:
            out.append({"item": str(r[0]), "value": float(str(r[val_col]).replace(",", "."))})
        except (ValueError, IndexError):
            out.append({"item": str(r[0]) if r else "?", "value": None})
    return out


@tool
def parse_smartpls_export(content: bytes, filename: str) -> str:
    """Parse a SmartPLS/SPSS HTML or .xlsx results export into {table_kind, rows}. Preferred over a
    screenshot when the student has the file."""
    name = (filename or "").lower()
    try:
        if name.endswith((".xlsx", ".xls")):
            import openpyxl, io  # noqa: PLC0415
            ws = openpyxl.load_workbook(io.BytesIO(content), data_only=True).active
            rows = [[c.value for c in row] for row in ws.iter_rows()]
        else:  # html
            import pandas as pd, io  # noqa: PLC0415
            df = pd.read_html(io.BytesIO(content))[0]
            rows = [list(df.columns)] + df.values.tolist()
        headers = [str(h) for h in rows[0]]
        return json.dumps({"table_kind": infer_table_kind(headers),
                           "rows": _rows_from_matrix(headers, rows[1:])}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"couldn't parse export: {e}",
                           "hint": "paste the values or upload a screenshot"}, ensure_ascii=False)
```

- [ ] **Step 4: Run to verify it passes** → PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/tools/output_parse.py api/tests/test_output_parse.py
git commit -m "feat(m4): parse SmartPLS HTML/xlsx export into {table_kind, rows}

Deterministic path from a real export to the F8 sanity layer — no retyping.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `parse_output_table` (vision, stubbed in tests)

**Files:**
- Modify: `agent/tools/output_parse.py`
- Test: `api/tests/test_output_parse.py`

**Interfaces:**
- Produces: `parse_output_table(image_ref: str) -> str` — vision → `{table_kind, rows}` or `{error|needs_confirmation}`. The vision call is behind `_vision_read(image_ref) -> str` (stubbed in tests).

- [ ] **Step 1: Write the failing test**

```python
# add to api/tests/test_output_parse.py
import agent.tools.output_parse as op


def test_vision_parse_ok(monkeypatch):
    monkeypatch.setattr(op, "_vision_read",
                        lambda ref: '{"table_kind":"loadings","rows":[{"item":"X1","value":0.74}]}')
    out = json.loads(op.parse_output_table.func(image_ref="att://1"))
    assert out["table_kind"] == "loadings" and out["rows"][0]["value"] == 0.74


def test_vision_parse_junk_is_error(monkeypatch):
    monkeypatch.setattr(op, "_vision_read", lambda ref: "the image is blurry")
    out = json.loads(op.parse_output_table.func(image_ref="att://1"))
    assert out.get("error") or out.get("needs_confirmation")
```

- [ ] **Step 2: Run to verify it fails** → FAIL.

- [ ] **Step 3: Implement**

```python
# add to agent/tools/output_parse.py
_VISION_PROMPT = ("Transcribe ONLY the visible results table into STRICT JSON "
                  '{"table_kind": "...", "rows": [{"item": "", "value": <number or null>}]}. '
                  "Do NOT invent numbers; mark unreadable cells null. No prose.")


def _vision_read(image_ref: str) -> str:
    """Read a results-table image via the multimodal model. image_ref is an attachment the runtime
    already resolved to model-visible bytes. Isolated so tests stub it."""
    from agent.multimodal import model_message_for  # noqa: PLC0415 — match the real helper
    from orchestrator.tools.m5_writing import _get_llm  # noqa: PLC0415
    msg = model_message_for(_VISION_PROMPT, image_ref)   # provider-aware image message
    resp = _get_llm().invoke([msg])
    return str(getattr(resp, "content", resp))


@tool
def parse_output_table(image_ref: str) -> str:
    """Parse a SCREENSHOT of a SmartPLS/SPSS/AMOS results table into {table_kind, rows} for the
    threshold checker. Prefer parse_smartpls_export if the student has the file. Never invents
    numbers; low-confidence parses ask the student to confirm."""
    raw = _vision_read(image_ref)
    s, e = raw.find("{"), raw.rfind("}")
    if s == -1 or e == -1:
        return json.dumps({"error": "couldn't read a table in that image",
                           "hint": "paste the values or upload the SmartPLS HTML export"})
    try:
        data = json.loads(raw[s:e + 1])
    except Exception:
        return json.dumps({"error": "unclear table", "needs_confirmation": True})
    if not data.get("rows"):
        return json.dumps({"needs_confirmation": True, "parsed": data})
    return json.dumps(data, ensure_ascii=False)
```

> **Note for implementer:** match `agent/multimodal.py`'s real helper name/signature for building a
> provider-aware image message; the contract is "prompt + image → text", tests stub `_vision_read`.

- [ ] **Step 4: Run to verify it passes** → PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/tools/output_parse.py api/tests/test_output_parse.py
git commit -m "feat(m4): vision parse of results-table screenshots

Screenshot -> {table_kind, rows}; unreadable cells asked, never guessed.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Wire to F8 + M4 skill (end-to-end)

**Files:**
- Modify: `agent/runtime.py` (register both parse tools), `skills/dothesis-m4-analysis/SKILL.md`
- Test: `api/tests/test_output_parse.py`

- [ ] **Step 1: Write the failing end-to-end test**

```python
# add to api/tests/test_output_parse.py
def test_export_feeds_check_thresholds():
    from agent.tools.stats import check_thresholds   # F8
    html = "<table><tr><th>pair</th><th>HTMT</th></tr><tr><td>BI-ATT</td><td>0.91</td></tr></table>"
    parsed = json.loads(parse_smartpls_export(html.encode(), "r.html"))
    flags = json.loads(check_thresholds.func(table_kind=parsed["table_kind"], rows=parsed["rows"]))
    assert any("discriminant" in f["issue"].lower() for f in flags["findings"])
```

- [ ] **Step 2: Run to verify it fails** (until F8's `check_thresholds` + these parsers coexist) → FAIL/ERROR.

- [ ] **Step 3: Register + wire**

Register `parse_smartpls_export` and `parse_output_table` in `agent/runtime.py`'s tool list. In
`skills/dothesis-m4-analysis/SKILL.md`: "When the student attaches an image or export of results,
call `parse_output_table` / `parse_smartpls_export` → `check_thresholds` → narrate with
output-interpretation + two-register content. If the parse is low-confidence, show it back to
confirm before interpreting."

- [ ] **Step 4: Run to verify it passes** → PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/runtime.py skills/dothesis-m4-analysis/SKILL.md api/tests/test_output_parse.py
git commit -m "feat(m4): wire output parsers to the F8 sanity layer

Screenshot/export -> parsed rows -> check_thresholds -> grounded narration.
Closes the input gap that would have killed the correctness feature.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] `cd api && ./run.sh pytest tests/test_output_parse.py -q` → PASS (incl. the F8 end-to-end).
- [ ] No real vision API in tests (`_vision_read` stubbed).

## Notes

- **Depends on F8** (`check_thresholds` + output-interpretation content) — build F8 first or land
  Task 3 when F8 lands.
- Deterministic export parse (Task 1) is the reliable default; vision (Task 2) is the convenience
  path with confirm-on-low-confidence.

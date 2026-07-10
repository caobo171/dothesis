"""Parse SmartPLS/SPSS result tables into {table_kind, rows} for the F8 sanity layer.

Design decisions:
- Tools take a workspace FILE PATH, never bytes/base64 the model fills in. A model
  cannot hand over raw file content, and letting it try invites fabrication. This
  mirrors `run_stats` / `_load_df` (agent/tools/stats.py), which does `Path(file)`
  directly — there is no separate workspace resolver to reuse.
- We TRANSCRIBE the values the student's software already produced; we never compute
  a statistic here. Downstream, F8's `check_thresholds` only *compares* these numbers.
- Unreadable cells become `null`, never a guessed number.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

from langchain_core.tools import tool

# Header-substring hints, most-specific first. The first kind whose hint appears in
# the joined header row wins. Ordering matters: "loading" would also match a header
# that merely mentions loadings inside another table, so we keep the discriminant/
# HTMT hints ahead of it.
_KIND_HINTS = {
    "htmt": ("htmt", "heterotrait"),
    "loadings": ("outer loading", "factor loading", "loading"),
    "fornell_larcker": ("fornell", "larcker"),
    "vif": ("vif",),
    "path_coeffs": ("path coefficient", "original sample", "t statistic"),
    "fit_indices": ("cfi", "rmsea", "tli", "srmr"),
    "ave": ("ave", "average variance"),
    "cr": ("composite reliability",),
}


def infer_table_kind(headers: list[str]) -> str:
    """Classify a results table by its header row so F8 knows which threshold set
    applies. Returns "unknown" when nothing matches (caller then asks the student)."""
    joined = " ".join(str(h).lower() for h in headers)
    for kind, hints in _KIND_HINTS.items():
        if any(h in joined for h in hints):
            return kind
    return "unknown"


def _load_bytes(file: str) -> bytes:
    """Read the file. `file` is a path the runtime passes (same convention as
    run_stats/_load_df, which does `Path(file)` directly — there is NO separate
    workspace resolver). Isolated as its own function so tests stub it and never
    touch disk."""
    return Path(file).read_bytes()


def _num(x):
    """Best-effort numeric parse. Accepts the comma decimal separator common in
    EU-locale SmartPLS exports. Anything non-numeric (a label, a blank, a dash)
    becomes None rather than a fabricated 0."""
    try:
        return float(str(x).replace(",", "."))
    except (ValueError, TypeError):
        return None


def _rows(headers: list[str], data: list[list]) -> list[dict]:
    """Shape a parsed grid into rows. A row-oriented table (one value per label,
    e.g. loadings/AVE/HTMT-as-pairs) yields {"item", "value"}; a matrix row (many
    numbers, e.g. a full HTMT/Fornell-Larcker matrix) keeps every value so nothing
    is silently dropped."""
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
            import openpyxl  # noqa: PLC0415 — heavy, xlsx-only
            ws = openpyxl.load_workbook(io.BytesIO(content), data_only=True).active
            grid = [[c.value for c in row] for row in ws.iter_rows()]
        else:
            import pandas as pd  # noqa: PLC0415 — needs lxml for read_html
            df = pd.read_html(io.BytesIO(content))[0]
            grid = [list(df.columns)] + df.values.tolist()
        headers = [str(h) for h in grid[0]]
        return json.dumps({"table_kind": infer_table_kind(headers), "rows": _rows(headers, grid[1:])},
                          ensure_ascii=False)
    except Exception as e:
        # Fail soft: hand the agent a recovery hint instead of raising, so it can
        # ask the student for the values rather than crashing the turn.
        return json.dumps({"error": f"couldn't parse export: {e}",
                           "hint": "paste the values or upload a screenshot"}, ensure_ascii=False)

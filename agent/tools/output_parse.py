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


# --- Vision path (screenshot) --------------------------------------------
# Convenience path for when the student only has a screenshot. It goes through the
# REAL multimodal API (agent.multimodal): resolve_vision(spec) picks the per-provider
# image block-format + client for the ACTIVE model (Gemini sidecar / Claude brain /
# OpenAI-compatible vision model), so it is NOT hardwired to Gemini. Isolated behind
# _vision_read() — the single function tests stub — to keep the network/model boundary
# out of the test suite; parse_output_table wraps it fail-soft.
_VISION_PROMPT = ("Transcribe ONLY the visible results table into STRICT JSON "
                  '{"table_kind": "...", "rows": [{"item": "", "value": <number or null>}]}. '
                  "Do NOT invent numbers; mark unreadable cells null. No prose.")


def _vision_read(file: str) -> str:
    """Read a results-table image, provider-agnostically. `file` is the workspace path.

    resolve_vision(spec) picks the image block-format + client for the ACTIVE model
    (native Gemini sidecar, native Claude brain, or an OpenAI-compatible vision model
    on Ofox/OpenRouter) — so screenshot parsing no longer silently depends on a Google
    key when the brain is Claude. Isolated so tests stub it and never call a model."""
    from agent.model_factory import make_vision_capable_model, spec_from_env  # noqa: PLC0415
    from agent.multimodal import (  # noqa: PLC0415 (real API)
        Attachment, _flatten_content, build_user_message, resolve_vision,
    )
    spec = spec_from_env()
    res = resolve_vision(spec)
    att = Attachment.from_path(file)                       # `file` is already the path
    msg = build_user_message(_VISION_PROMPT, [att], res.provider, supports_vision=True)
    model = make_vision_capable_model(spec, use_sidecar=res.use_sidecar)
    return _flatten_content(getattr(model.invoke([msg]), "content", ""))


@tool
def parse_output_table(file: str) -> str:
    """Parse a SCREENSHOT (a workspace image file) of a SmartPLS/SPSS/AMOS results table into
    {table_kind, rows}. Prefer parse_smartpls_export if the student has the file. Never invents
    numbers; low-confidence parses ask the student to confirm."""
    try:
        raw = _vision_read(file)
    except Exception as e:
        # Fail-soft: a vision/model/key error must never crash the turn — hand the
        # student a clear fallback instead of an exception.
        return json.dumps({"error": f"vision parse failed: {e}",
                           "hint": "paste the values or upload the SmartPLS HTML export"})
    # Extract the JSON object the model was asked to emit. If there is none, the
    # model didn't find a table — surface that, don't fabricate a parse.
    s, e = raw.find("{"), raw.rfind("}")
    if s == -1 or e == -1:
        return json.dumps({"error": "couldn't read a table in that image",
                           "hint": "paste the values or upload the SmartPLS HTML export"})
    try:
        data = json.loads(raw[s:e + 1])
    except Exception:
        # Malformed JSON = low confidence: hand it back for confirmation, don't guess.
        return json.dumps({"needs_confirmation": True, "raw": raw[:300]})
    if not data.get("rows"):
        return json.dumps({"needs_confirmation": True, "parsed": data})
    return json.dumps(data, ensure_ascii=False)

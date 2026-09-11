"""Read a survey dataset into a short text profile.

The agent twin of docx_extract: one place that knows how to turn a data file
into something a text-only brain can read.

The point is NOT to turn the data into text. A 283-row SPSS export is ~12,000
numbers; pasting them into a prompt costs a fortune and buys nothing, because
the model cannot run Cronbach's alpha by reading. What the brain actually needs
is enough to (a) recognise the columns as the student's constructs and (b) call
the stats tools on the real file — `agent/tools/stats.py` already loads .sav via
pyreadstat and .xlsx/.xls/.csv via pandas from the workspace, where the uploads
route mirrors every attachment as `uploads/<filename>`.

So the profile is shape, columns, and a few rows: what a variable view would
show you. It always names the workspace path, because a brain that knows the
columns but not the path describes the dataset instead of analysing it.

Never raises. An unreadable dataset degrades to a one-line note saying so — the
upload still succeeded, the file is still on disk, and the stats tools can still
be pointed at it.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Enough columns to recognise every construct in a normal thesis instrument
# (8-12 constructs x 4-6 items, plus demographics) without turning the profile
# into the thing it exists to avoid.
_MAX_COLS = 120
_SAMPLE_ROWS = 3

DATA_EXTS = (".csv", ".xlsx", ".xls", ".sav")


def is_dataset(filename: str) -> bool:
    return (filename or "").lower().endswith(DATA_EXTS)


def _load(body: bytes, filename: str):
    """bytes -> DataFrame. Kept in step with stats.py::_load_df on purpose:
    the profile must describe the same frame the tools will later compute on."""
    import pandas as pd

    suffix = Path(filename or "").suffix.lower()
    if suffix == ".sav":
        # pyreadstat only reads paths, not buffers.
        import tempfile

        import pyreadstat

        with tempfile.NamedTemporaryFile(suffix=".sav") as tmp:
            tmp.write(body)
            tmp.flush()
            df, _meta = pyreadstat.read_sav(tmp.name)
        return df
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(io.BytesIO(body))
    return pd.read_csv(io.BytesIO(body))


def profile_dataset(body: bytes, filename: str) -> str:
    """A compact, readable description of the dataset. Best-effort → a note."""
    name = filename or "dataset"
    try:
        df = _load(body, name)
    except Exception as e:  # noqa: BLE001 — a bad dataset must not kill the turn
        logger.warning("data_profile: could not read %s: %s", name, e)
        return (f"{name}: could not be read as a dataset ({type(e).__name__}). "
                f"The file is in the workspace at uploads/{name} — try the stats "
                f"tools on it directly.")

    rows, cols = int(df.shape[0]), int(df.shape[1])
    lines = [
        f"{name} — {rows} rows x {cols} columns.",
        f"Workspace path: uploads/{name} "
        f"(pass this to the stats tools; do not compute from this profile).",
        "",
        "Columns:",
    ]

    shown = list(df.columns)[:_MAX_COLS]
    for c in shown:
        col = df[c]
        example = "" if col.dropna().empty else str(col.dropna().iloc[0])[:40]
        lines.append(
            f"  - {c} ({col.dtype}, {int(col.notna().sum())}/{rows} valid)"
            + (f" e.g. {example}" if example else "")
        )
    if cols > len(shown):
        lines.append(f"  … and {cols - len(shown)} more columns")

    if rows:
        lines += ["", f"First {min(_SAMPLE_ROWS, rows)} rows:"]
        head = df.head(_SAMPLE_ROWS)
        lines.append("  " + " | ".join(str(c) for c in shown))
        for _, r in head.iterrows():
            lines.append("  " + " | ".join(str(r[c])[:20] for c in shown))

    return "\n".join(lines)

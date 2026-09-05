"""SP5: per-format paste-text parsers for M4 outline steps.

Each format module exports `parse_<format>(text, step_name) -> dict | None`.
On regex match: returns a StepResult-shaped dict with `parser="regex"`.
On no match: returns None, triggering LLM fallback in `dispatch_parse`.
"""
from __future__ import annotations

import re

# Lazy imports inside dispatch_parse / format_step_as_markdown so the package
# doesn't crash on import if a parser module has a transient error in dev.


_MD_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def _md_cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def flatten_markdown_tables(text: str) -> str:
    """Rewrite Markdown tables as the whitespace columns the regex parsers read.

    The parsers were written for a SmartPLS/SPSS paste — `AA_1  0.842` — and
    match a header of bare words followed by rows they split on whitespace. A
    results grid now often arrives as a Markdown table instead (that is what the
    vision transcription of a pasted screenshot produces), so every row began
    with `|`, the header regex never matched, and a document full of statistics
    parsed to nothing.

    Empty cells are load-bearing and must survive the rewrite: the parsers map a
    value to a construct BY ITS COLUMN INDEX, so `| APE_1 | | 0.784 |` has to
    keep a placeholder in the first column or 0.784 is credited to the wrong
    construct. Blank cells therefore become `-`, which is non-numeric (the
    parsers skip it) but still occupies its position. The header's own leading
    corner cell is dropped, because the parsers index the header from the first
    column AFTER the row label.
    """
    if "|" not in text:
        return text
    out: list[str] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        is_row = line.strip().startswith("|") and line.count("|") >= 2
        header_next = i + 1 < len(lines) and _MD_SEPARATOR.match(lines[i + 1] or "")
        if is_row and header_next:
            header = _md_cells(line)
            while header and not header[0]:
                header.pop(0)          # drop the empty corner cell
            out.append(" ".join(h for h in header if h))
            i += 2                      # skip the |---| separator
            while i < len(lines) and lines[i].strip().startswith("|"):
                if _MD_SEPARATOR.match(lines[i]):
                    i += 1
                    continue
                cells = [c if c else "-" for c in _md_cells(lines[i])]
                out.append(" ".join(cells))
                i += 1
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


def dispatch_parse(data_type: str, text: str, step_name: str) -> dict | None:
    """Regex-first, LLM-fallback. Returns a StepResult dict or None.

    Returning None means both regex and LLM fallback failed — caller should
    produce a stub StepResult so the outline walk continues without crashing.
    """
    # Markdown grids are normalised once, here, so every format parser below
    # sees the shape it was written for.
    text = flatten_markdown_tables(text)
    from .spss import parse_spss
    from .smartpls import parse_smartpls
    from .lavaan import parse_lavaan
    from .llm_fallback import extract_step_data

    parsers = {
        "SPSS": parse_spss,
        "SmartPLS": parse_smartpls,
        "CB-SEM": parse_lavaan,
    }
    parser = parsers.get(data_type)
    if parser is not None:
        result = parser(text, step_name)
        if result is not None:
            return result
    # Fallback path
    return extract_step_data.invoke({
        "text": text,
        "step_name": step_name,
        "data_type": data_type,
    })


def format_step_as_markdown(step_result: dict) -> str:
    """Build the markdown body for a per-step AIMessage."""
    name = step_result.get("step_name", "Step")
    rows = step_result.get("table") or []
    interp = step_result.get("interpretation", "")
    md = f"**{name}**\n\n"
    if rows:
        cols = list(rows[0].keys())
        md += "| " + " | ".join(cols) + " |\n"
        md += "| " + " | ".join("---" for _ in cols) + " |\n"
        for r in rows:
            md += "| " + " | ".join(str(r.get(c, "")) for c in cols) + " |\n"
        md += "\n"
    if interp:
        md += interp
    return md

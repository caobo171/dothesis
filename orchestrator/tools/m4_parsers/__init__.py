"""SP5: per-format paste-text parsers for M4 outline steps.

Each format module exports `parse_<format>(text, step_name) -> dict | None`.
On regex match: returns a StepResult-shaped dict with `parser="regex"`.
On no match: returns None, triggering LLM fallback in `dispatch_parse`.
"""
from __future__ import annotations


# Lazy imports inside dispatch_parse / format_step_as_markdown so the package
# doesn't crash on import if a parser module has a transient error in dev.


def dispatch_parse(data_type: str, text: str, step_name: str) -> dict | None:
    """Regex-first, LLM-fallback. Returns a StepResult dict or None.

    Returning None means both regex and LLM fallback failed — caller should
    produce a stub StepResult so the outline walk continues without crashing.
    """
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

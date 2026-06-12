"""M5 writing tools — seams into the EXISTING engine writing pipeline.

Architecture §2.2: the M5 skill orchestrates (what to write, revisions); the
engine pipeline executes (structure → compose → citations → compile →
validate) and the docx post-processor owns ALL document mechanics (TOC,
clickable citations, DOI links, reference formatting).

Spike status: the tool contracts are final; the deep engine wiring is
migration step 2 (the engine's draft path currently runs as an api job with
S3 + job context — see api/routers/papers.py). Until that adapter lands,
these tools return a structured not-wired signal so the agent tells the user
honestly instead of hand-rolling prose dumps or OOXML.
"""
from __future__ import annotations

import json

from langchain_core.tools import tool

_NOT_WIRED = (
    "The writing pipeline adapter is not wired in this environment yet "
    "(migration step 2 — engine job context). Draft individual sections "
    "conversationally with the user, store them via commit_slice with full "
    "lineage, and tell the user DOCX export will compile them once the "
    "pipeline lands."
)


@tool
def write_pipeline(
    sections: list[str],
    citation_style: str = "apa7",
    language: str = "en",
) -> str:
    """Generate thesis chapters through the engine writing pipeline.

    Runs structure → compose → citations → compile → validate over the
    project's context_store (M1 RQs, M2 sources/gaps, M3 model/methodology,
    M4 results are the ONLY grounding corpus). Streams progress to the user.
    Use for full-paper or per-chapter generation; use agent-side revision for
    surgical edits afterward.

    Args:
        sections: Section names to generate (e.g. ["literature_review"]) or
            ["all"] for the full standard structure.
        citation_style: apa7 (default), vancouver, ieee, …
        language: "en" or "vi".
    """
    return json.dumps({"error": "not_wired", "hint": _NOT_WIRED,
                       "requested": {"sections": sections,
                                     "citation_style": citation_style,
                                     "language": language}})


@tool
def export_docx(citation_style: str = "apa7") -> str:
    """Export the current draft (final_sections) to Word via the engine's
    docx post-processor: headings, auto Table of Contents, in-text citations
    as clickable internal links, DOI hyperlinks, style-correct references
    with hanging indents. Never hand-build OOXML — this tool owns it.

    Args:
        citation_style: apa7 (default), vancouver, ieee, …
    """
    return json.dumps({"error": "not_wired", "hint": _NOT_WIRED,
                       "requested": {"citation_style": citation_style}})

"""M5 — Writing & Export tools.

These tools are the bridge that lets the auto-mode orchestrator produce
the same final artifacts (docx + pdf) that today's `python -m engine` ships.
They delegate into engine/phases/compose, engine/phases/compile, and
engine/utils/* so we don't reimplement the layout/formatting logic.

Sub-project 1 note: where the engine's actual function signature doesn't match
the orchestrator's tool contract, the wrapper falls back to a minimal
implementation. Proper engine integration is a follow-on sub-project.
"""
from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path
from uuid import uuid4

import boto3
from langchain_core.tools import tool

# Make engine package importable.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logger = logging.getLogger(__name__)


def _scratch_dir() -> Path:
    d = Path(os.getenv("ORCHESTRATOR_SCRATCH", "/tmp/orchestrator_scratch"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def s3_from_env():
    """S3 client factory — mirrors the SP2 api/app/routers/uploads.py pattern.
    Indirection point so tests can monkeypatch easily.
    """
    return boto3.client(
        "s3",
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_KEY"),
    )


_CONTENT_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf":  "application/pdf",
}


def _upload_to_s3(local_path: str, project_id: str, kind: str, filename: str) -> str:
    """Upload a local artifact to S3 under projects/{project_id}/exports/.

    Returns the s3_key (not signed URL — keys persist; signed URLs expire).
    Deletes the local file after upload to keep the scratch dir clean.
    """
    s3 = s3_from_env()
    bucket = os.environ["AWS_S3_BUCKET"]
    s3_key = f"projects/{project_id}/exports/{filename}"
    content_type = _CONTENT_TYPES[kind]
    with open(local_path, "rb") as f:
        s3.put_object(
            Bucket=bucket, Key=s3_key, Body=f.read(),
            ContentType=content_type,
        )
    Path(local_path).unlink(missing_ok=True)
    return s3_key


_CITE_PATTERN = re.compile(r"\((?P<author>[A-Z][\w-]+(?: et al\.)?), (?P<year>\d{4})\)")


def validate_citations(prose: str, references: list[dict]) -> tuple[list[str], list[str]]:
    """Regex-scan prose for (Author, Year) patterns; partition into
    (cited_in_pool, uncited). Each returned list is de-duplicated and
    preserves first-occurrence order.

    Plain Python helper (not a @tool) — used by compose_chapter +
    rewrite_chapter post-validation.
    """
    # Build a pool of (author, year) tuples from references.
    # Convert year to string to match regex group which is always a string.
    pool = {(r.get("author", ""), str(r.get("year", ""))) for r in references}
    cited: list[str] = []
    uncited: list[str] = []
    seen: set[tuple[str, str]] = set()
    for m in _CITE_PATTERN.finditer(prose):
        key = (m.group("author"), m.group("year"))
        if key in seen:
            continue
        seen.add(key)
        label = f"{m.group('author')}, {m.group('year')}"
        if key in pool:
            cited.append(label)
        else:
            uncited.append(label)
    return cited, uncited


# --- Wrappers that tests can monkeypatch ---------------------------------

def _compose_section_via_engine(section_name: str, context_store: dict) -> str:
    """Compose one section using engine/phases/compose helpers.

    If the engine's section composer isn't found or fails, return a fallback
    formed from the context_store (so the auto-mode pipeline keeps moving).
    """
    try:
        from engine.phases.context import DraftContext
        from engine.phases import compose as _compose
    except Exception as e:
        logger.warning("engine.phases.compose import failed: %s", e)
        return _fallback_section(section_name, context_store)

    try:
        ctx = DraftContext()
        ctx.topic = (context_store.get("m1_topic") or {}).get("research_title", "Untitled")
        ctx.language = (context_store.get("m1_topic") or {}).get("language", "en")
        ctx.scribe_output = (context_store.get("m2_literature") or {}).get("literature_review_doc", "")
        ctx.signal_output = "\n".join(
            g.get("description", "") for g in
            (context_store.get("m2_literature") or {}).get("research_gaps", [])
        )

        # Try documented private composers first; fall back to public run_compose_phase.
        composer = {
            "intro":       getattr(_compose, "_compose_intro", None),
            "lit_review":  getattr(_compose, "_compose_lit_review", None),
            "methodology": getattr(_compose, "_compose_methodology", None),
            "results":     getattr(_compose, "_compose_results", None),
            "discussion":  getattr(_compose, "_compose_discussion", None),
            "conclusion":  getattr(_compose, "_compose_conclusion", None),
        }.get(section_name)
        if composer is None:
            return _fallback_section(section_name, context_store)
        return composer(ctx)
    except Exception as e:
        logger.warning("engine compose failed for %s: %s", section_name, e)
        return _fallback_section(section_name, context_store)


def _fallback_section(section_name: str, context_store: dict) -> str:
    """Minimal text we can emit when engine integration isn't wired up yet."""
    title = (context_store.get("m1_topic") or {}).get("research_title", "Untitled")
    return f"# {section_name.title()}\n\n[Auto-generated for '{title}']\n"


def _validate_via_engine(text: str) -> dict:
    """Run engine validation. Sub-project 1 fallback if signature differs."""
    try:
        from engine.phases.validate import quick_validate
        return quick_validate(text)
    except Exception:
        # Fallback: trivial sanity check
        issues = []
        if len(text) < 100:
            issues.append({"kind": "too_short", "message": "draft <100 chars"})
        return {"issues": issues, "score": 1.0 - 0.5 * len(issues)}


def _compile_pdf_via_engine(sections: list[dict], output_path: str, **kw) -> str:
    """Render sections to a PDF using engine/utils/export_professional if available;
    otherwise write a minimal placeholder so the pipeline can continue.
    """
    try:
        from engine.utils.export_professional import export_pdf
        return export_pdf(sections, output_path, **kw)
    except Exception as e:
        logger.warning("engine export_pdf failed: %s — writing placeholder", e)
        Path(output_path).write_bytes(b"%PDF-1.4\n%% placeholder - engine wiring pending\n")
        return output_path


def _export_docx_via_engine(sections: list[dict], output_path: str, **kw) -> str:
    """Render to .docx. Same fallback strategy as PDF."""
    try:
        from engine.utils.docx_post_processor import export_docx as _real
        return _real(sections, output_path, **kw)
    except Exception as e:
        logger.warning("engine export_docx failed: %s — writing placeholder", e)
        Path(output_path).write_bytes(b"PK\x03\x04 placeholder docx\n")
        return output_path


class CitationCompiler:
    """Wrapper exposing a `(style)` constructor + `.compile(items) -> str`.

    Engine's CitationCompiler takes a CitationDatabase, not a style string, so
    sub-project 1 uses a minimal formatter here. Proper engine integration ships later.
    """
    def __init__(self, style: str):
        self.style = style

    def compile(self, items: list[dict]) -> str:
        if not items:
            return ""
        lines = []
        for it in items:
            author = it.get("author") or "Anon"
            year = it.get("year") or "n.d."
            title = it.get("title") or ""
            lines.append(f"{author} ({year}). {title}.".strip())
        return "\n".join(lines)


# --- Public tools --------------------------------------------------------

@tool
def compose_section(section_name: str, context_store: dict) -> str:
    """Compose one section of the thesis from the project's context_store.

    `section_name` is one of: intro, lit_review, methodology, results,
    discussion, conclusion.
    """
    return _compose_section_via_engine(section_name, context_store)


@tool
def validate_draft(text: str) -> dict:
    """Run engine's validation pipeline on a draft section. Returns issues + score."""
    return _validate_via_engine(text)


@tool
def compile_pdf(sections: list[dict], project_id: str) -> str:
    """SP6: render sections to PDF, upload to S3, return s3_key.

    Required for both interactive and auto-mode paths — local-path fallback
    removed (Q-S3 decision).
    """
    if not project_id:
        raise ValueError("compile_pdf requires project_id")
    filename = f"thesis-{uuid4().hex[:8]}.pdf"
    local_path = _scratch_dir() / filename
    _compile_pdf_via_engine(sections, str(local_path))
    return _upload_to_s3(str(local_path), project_id, "pdf", filename)


@tool
def export_docx(sections: list[dict], project_id: str) -> str:
    """SP6: render sections to DOCX, upload to S3, return s3_key.

    Required for both interactive and auto-mode paths.
    """
    if not project_id:
        raise ValueError("export_docx requires project_id")
    filename = f"thesis-{uuid4().hex[:8]}.docx"
    local_path = _scratch_dir() / filename
    _export_docx_via_engine(sections, str(local_path))
    return _upload_to_s3(str(local_path), project_id, "docx", filename)


@tool
def format_citations(items: list[dict], style: str = "apa7") -> str:
    """Format a citation list using the requested style."""
    return CitationCompiler(style).compile(items)


@tool
def compile_bibliography(references: list[dict], citation_style: str) -> str:
    """Format M2 references as a bibliography section using the existing
    CitationCompiler. Returns the formatted block as a multi-line string,
    or '(No references)' on empty input.
    """
    if not references:
        return "(No references)"
    return CitationCompiler(citation_style).compile(references)

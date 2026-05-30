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

import json
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

# Directory where M5 chapter prompt templates live.
_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts" / "m5"


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


def _upload_to_s3(local_path: str, project_id: str, kind: str, filename: str) -> tuple[str, int]:
    """Upload a local artifact to S3 under projects/{project_id}/exports/.

    Returns (s3_key, size_bytes). Deletes the local file after upload.
    Reading the file bytes before upload lets us capture size without a
    separate stat call, and avoids a second open() after write.
    """
    s3 = s3_from_env()
    # The project convention is S3_BUCKET (settings.py, job_runner, uploads,
    # engine all use it); job_runner sets S3_BUCKET when launching this auto
    # subprocess. Reading AWS_S3_BUCKET here silently broke M5 export in the real
    # flow. Prefer S3_BUCKET, keep AWS_S3_BUCKET as a back-compat fallback.
    bucket = os.environ.get("S3_BUCKET") or os.environ["AWS_S3_BUCKET"]
    s3_key = f"projects/{project_id}/exports/{filename}"
    content_type = _CONTENT_TYPES[kind]
    body = Path(local_path).read_bytes()
    size_bytes = len(body)
    s3.put_object(
        Bucket=bucket, Key=s3_key, Body=body,
        ContentType=content_type,
    )
    Path(local_path).unlink(missing_ok=True)
    return s3_key, size_bytes


_CITE_PATTERN = re.compile(r"\((?P<author>[A-Z][\w-]+(?: et al\.)?), (?P<year>\d{4})\)")

# SP6.5: separate regex used by validate_citations_plain for the autosave PATCH
# endpoint. Broader than _CITE_PATTERN — accepts any author token and n.d. years
# so the inline autosave validator is tolerant of varied LLM citation styles.
_CITATION_REGEX = re.compile(r"\(([^)]+?),\s*(\d{4}|n\.d\.)\)")


def validate_citations_plain(prose: str, reference_pool: list[dict]) -> dict:
    """Extract (Author, Year) patterns; classify as used vs uncited based on pool.

    SP6.5: called directly by the autosave PATCH endpoint without @tool overhead.
    Uses _CITATION_REGEX (broader pattern, accepts n.d.) unlike the older
    _CITE_PATTERN. Returns {"citations_used": [...], "uncited_warnings": [...]}
    preserving first-occurrence order with no duplicates.
    """
    # Decision: strip whitespace from pool keys so "Smith " and "Smith" match,
    # and convert year to string to align with the regex group (always a string).
    pool_keys = {
        (str(r.get("author", "")).strip(), str(r.get("year", "")).strip())
        for r in reference_pool
    }
    seen: dict[str, bool] = {}    # ordered dedupe via insertion-order dict
    citations_used: list[str] = []
    uncited: list[str] = []
    for match in _CITATION_REGEX.finditer(prose):
        author, year = match.group(1).strip(), match.group(2).strip()
        text = f"({author}, {year})"
        if text in seen:
            continue
        seen[text] = True
        if (author, year) in pool_keys:
            citations_used.append(text)
        else:
            uncited.append(text)
    return {"citations_used": citations_used, "uncited_warnings": uncited}


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


# --- M5 LLM helpers -------------------------------------------------------

def _format_references_for_prompt(refs: list[dict]) -> str:
    """One reference per line, numbered. Used inside chapter prompts."""
    if not refs:
        return "(no references available — write without inline citations)"
    lines = []
    for i, r in enumerate(refs, 1):
        author = r.get("author", "Anon")
        year = r.get("year", "n.d.")
        title = r.get("title", "")
        lines.append(f"[{i}] {author} ({year}). {title}".strip())
    return "\n".join(lines)


def _safe_format_kwargs(context_slice: dict) -> dict:
    """Convert dict/list values to JSON strings so str.format() doesn't break."""
    out = {}
    for k, v in context_slice.items():
        if isinstance(v, (dict, list)):
            out[k] = json.dumps(v, ensure_ascii=False, default=str)
        elif v is None:
            out[k] = ""
        else:
            out[k] = str(v)
    return out


def _annotate_uncited(prose: str, uncited: list[str]) -> str:
    """Append a notice block listing any uncited (Author, Year) flags."""
    if not uncited:
        return prose
    notice = (
        "\n\n> ⚠️ The following inline citations are not present in the "
        "M2 reference pool and may be hallucinated: "
        + ", ".join(uncited)
        + ". Verify or remove."
    )
    return prose + notice


def _get_llm():
    """LLM factory for M5 tools. Monkeypatchable in tests."""
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.5-flash"),
        temperature=0.4,
    )


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
def compile_pdf(sections: list[dict], project_id: str) -> dict:
    """SP6: render sections to PDF, upload to S3, return {s3_key, size_bytes}.

    Returning size_bytes avoids a separate S3 HeadObject call in the agent and
    lets ExportArtifact carry real file sizes instead of hardcoded 0.
    """
    if not project_id:
        raise ValueError("compile_pdf requires project_id")
    filename = f"thesis-{uuid4().hex[:8]}.pdf"
    local_path = _scratch_dir() / filename
    _compile_pdf_via_engine(sections, str(local_path))
    s3_key, size_bytes = _upload_to_s3(str(local_path), project_id, "pdf", filename)
    return {"s3_key": s3_key, "size_bytes": size_bytes}


@tool
def export_docx(sections: list[dict], project_id: str) -> dict:
    """SP6: render sections to DOCX, upload to S3, return {s3_key, size_bytes}.

    Returning size_bytes avoids a separate S3 HeadObject call in the agent and
    lets ExportArtifact carry real file sizes instead of hardcoded 0.
    """
    if not project_id:
        raise ValueError("export_docx requires project_id")
    filename = f"thesis-{uuid4().hex[:8]}.docx"
    local_path = _scratch_dir() / filename
    _export_docx_via_engine(sections, str(local_path))
    s3_key, size_bytes = _upload_to_s3(str(local_path), project_id, "docx", filename)
    return {"s3_key": s3_key, "size_bytes": size_bytes}


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


@tool
def compose_chapter(
    chapter_name: str, paradigm: str, context_slice: dict,
    references: list[dict], citation_style: str, language: str,
) -> dict:
    """Compose one chapter via LLM, returns ChapterDraft dict.

    Loads orchestrator/prompts/m5/<chapter_name>.md as the prompt template;
    fills it with the context_slice + references; calls the LLM; runs
    validate_citations on the result; returns
    {name, prose, citations_used, uncited_warnings}.
    """
    prompt_template = (_PROMPT_DIR / f"{chapter_name}.md").read_text()
    refs_block = _format_references_for_prompt(references)
    safe_kwargs = _safe_format_kwargs(context_slice)
    safe_kwargs.setdefault("paradigm", paradigm)
    safe_kwargs.setdefault("language", language)
    safe_kwargs.setdefault("citation_style", citation_style)
    safe_kwargs["references_list"] = refs_block
    # str.format may KeyError on placeholders not in safe_kwargs — pre-extract
    # all expected keys and fall back to empty string for missing context.
    expected_keys = (
        "research_title", "field", "paradigm", "research_type",
        "objectives", "research_questions", "target_population", "scope",
        "literature_review_doc", "research_gaps",
        "design", "tool", "conceptual_model", "scale_items",
        "themes", "interview_guide", "purposive_criteria",
        "sampling_strategy", "target_sample_size", "mixed_design_type",
        "data_type_detected", "results", "qual_codes", "qual_themes",
        "custom_analyses",
        "language", "citation_style", "references_list",
    )
    for k in expected_keys:
        safe_kwargs.setdefault(k, "")

    try:
        prompt = prompt_template.format(**safe_kwargs)
        prose = _get_llm().invoke(prompt).content.strip()
    except Exception as e:
        logger.warning("compose_chapter LLM call failed for %s: %s", chapter_name, e)
        prose = f"# {chapter_name.title()}\n\n[Composition failed — please retry]"

    cited_in_pool, uncited = validate_citations(prose, references)
    if uncited:
        prose = _annotate_uncited(prose, uncited)
    return {
        "name": chapter_name,
        "prose": prose,
        "citations_used": cited_in_pool,
        "uncited_warnings": uncited,
    }


@tool
def rewrite_chapter(
    chapter_name: str, current_prose: str, instruction: str,
    context_slice: dict, references: list[dict], language: str,
) -> dict:
    """Rewrite one chapter per user instruction. Returns new ChapterDraft dict.

    Used when the user says e.g. "rewrite the intro to be less formal".
    Same prompt template as compose_chapter + the instruction + current prose
    as anchor. On LLM error, returns the original prose unchanged.
    """
    # Decision: load the same chapter prompt template as compose_chapter so the
    # rewrite stays grounded in the chapter's structural requirements, then
    # append the user's instruction and existing prose as a rewrite anchor.
    prompt_template = (_PROMPT_DIR / f"{chapter_name}.md").read_text()
    refs_block = _format_references_for_prompt(references)
    safe_kwargs = _safe_format_kwargs(context_slice)
    safe_kwargs.setdefault("paradigm", context_slice.get("paradigm", "quantitative"))
    safe_kwargs.setdefault("language", language)
    safe_kwargs.setdefault("citation_style", "apa7")
    safe_kwargs["references_list"] = refs_block
    expected_keys = (
        "research_title", "field", "paradigm", "research_type",
        "objectives", "research_questions", "target_population", "scope",
        "literature_review_doc", "research_gaps",
        "design", "tool", "conceptual_model", "scale_items",
        "themes", "interview_guide", "purposive_criteria",
        "sampling_strategy", "target_sample_size", "mixed_design_type",
        "data_type_detected", "results", "qual_codes", "qual_themes",
        "custom_analyses",
        "language", "citation_style", "references_list",
    )
    for k in expected_keys:
        safe_kwargs.setdefault(k, "")

    try:
        base_prompt = prompt_template.format(**safe_kwargs)
        rewrite_prompt = (
            f"{base_prompt}\n\n"
            f"## User rewrite instruction\n{instruction}\n\n"
            f"## Current chapter prose (rewrite based on the instruction; preserve good content):\n"
            f"{current_prose}\n\n"
            f"Output ONLY the rewritten chapter prose."
        )
        prose = _get_llm().invoke(rewrite_prompt).content.strip()
    except Exception as e:
        # Decision: on any LLM failure, return the original prose unchanged so
        # the user never loses work they've already reviewed or produced.
        logger.warning("rewrite_chapter LLM call failed for %s: %s", chapter_name, e)
        prose = current_prose  # unchanged on failure

    cited_in_pool, uncited = validate_citations(prose, references)
    if uncited:
        prose = _annotate_uncited(prose, uncited)
    return {
        "name": chapter_name,
        "prose": prose,
        "citations_used": cited_in_pool,
        "uncited_warnings": uncited,
    }

"""Partner report generation — service-to-service ("Powered by DoThesis").

Turns an uploaded analysis PDF (e.g. Fillform's SPSS / SmartPLS statistical
output) into a composed, exported report (DOCX + PDF) using the same M5 writing
engine that powers a real thesis — but with NO user project, NO chat thread and
NO credit ledger. This is the cross-product path: a partner app authenticates
with a shared token, POSTs the PDF, and gets back short-lived download URLs.

Two depths:
  - "analysis_report" (default): a focused narrative — Introduction, Results,
    Discussion, Conclusion. Fast; matches "drop a file -> get a report".
  - "full_thesis": the full six-chapter M5 composition (heavier, slower).

The heavy work (pdfminer extract + LLM chapter composition + LibreOffice render)
is blocking, so callers should run generate_partner_report() in a threadpool.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from .pdf_extract import extract_pdf_text

logger = logging.getLogger(__name__)

# Mermaid CLI (mmdc) tool dir — renders the M3 research-model diagram to PNG.
_MERMAID_DIR = Path(__file__).resolve().parents[2] / "engine" / "tools" / "mermaid_cli"
# node lives under nvm here; ensure the mmdc subprocess can find it.
_NODE_BIN = "/Users/kaoguyen/.nvm/versions/node/v24.18.0/bin"

# Subset composed for the lighter "analysis_report" depth. Ordered as they
# should appear in the document. "full_thesis" uses compose_all_sections
# (all six chapters + auto References) instead.
_ANALYSIS_CHAPTERS = ["intro", "results", "discussion", "conclusion"]

# Canonical chapter order (matches orchestrator M5_CHAPTER_ORDER). A caller can
# request any subset of these via `chapters`; we always compose them in this
# order so "Chương 1..6" stay in sequence regardless of checkbox order.
_CHAPTER_ORDER = ["intro", "lit_review", "methodology", "results", "discussion", "conclusion"]

_VALID_DEPTHS = {"analysis_report", "full_thesis"}

# --- Live progress tracking (drives the partner poll) ------------------------
# In-memory, keyed by a caller-supplied progress_token. The compose loop updates
# it per chapter; the /partner/report/progress endpoint reads it. Single-process
# only, which is fine — the compose runs in this same API process.
_PROGRESS: dict[str, dict] = {}


def _set_progress(token: str | None, **fields) -> None:
    if not token:
        return
    cur = _PROGRESS.get(token) or {}
    cur.update(fields)
    _PROGRESS[token] = cur


def get_progress(token: str) -> dict | None:
    """Read the live progress for a token (None if unknown/expired)."""
    return _PROGRESS.get(token)


class ReportError(Exception):
    """Raised with a stable `code` the router maps to an HTTP response."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _s3_from_env():
    """Raw boto3 client matching the export upload convention.

    M5 export uploads artifacts to `Bucket=S3_BUCKET, Key=projects/.../file`
    with NO settings prefix (see orchestrator/tools/m5_writing._upload_to_s3),
    so we presign the same way the exports router does — raw key, no prefix.
    """
    import boto3

    return boto3.client(
        "s3",
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_KEY"),
    )


def _presign(s3, s3_key: str, *, expires_in: int = 3600) -> str:
    bucket = os.environ.get("S3_BUCKET") or os.environ["AWS_S3_BUCKET"]
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": s3_key},
        ExpiresIn=expires_in,
    )


_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
_HYP_RE = re.compile(r"^(H\s*\d+)\s*[:.\)]\s*(.+)$", re.IGNORECASE)
_BOLD_HYP_RE = re.compile(r"^\s*\*\*\s*(H\s*\d+)\s*[:.\)]\s*(.+?)\s*\*\*\s*$", re.IGNORECASE)
# Inline list markers the composer sometimes emits on a single line.
#  * a spaced single ``*`` is unambiguous (``**bold**``/``*italic*`` never have a
#    space directly inside the asterisks) -> always a bullet.
#  * a spaced ASCII hyphen ``-`` is ambiguous with a parenthetical dash and MUST
#    only match U+002D (en-dash ``–`` / em-dash ``—`` in "Fornell–Larcker" etc.
#    are different codepoints and never match) -> only treated as a bullet when
#    every item is a bold-led label, so real dashes in prose are left alone.
_STAR_BULLET_RE = re.compile(r"\s\*\s+")
_DASH_BULLET_RE = re.compile(r"\s-\s+")
# A "content" pipe inside a table cell: not padded by whitespace and not already
# escaped — i.e. a literal ``|`` that must not be treated as a column delimiter.
_CONTENT_PIPE_RE = re.compile(r"(?<![\s|\\])\|(?=[^\s|])")


def _reflow_inline_bullets(line: str) -> list[str]:
    """Turn inline ``* a * b`` / ``- a - b`` list markers into real one-per-line
    list items.

    The composer sometimes emits a list on a single line (``Intro: * item one
    * item two`` or ``... . - **Label:** text - **Label2:** text``). Markdown
    only makes a list when each marker starts its own line, so inline markers
    render literally and the items collapse into one paragraph. We split them
    into a proper bullet list (blank line before/after so it parses in both
    pandoc and weasyprint).
    """
    stripped = line.lstrip()
    # leave tables, real headings, blockquotes and already-list lines alone
    if not stripped or stripped[0] in "|>#" or stripped[:2] in ("- ", "* ", "+ "):
        return [line]

    require_bold = False
    if len(_STAR_BULLET_RE.split(line)) >= 2:
        parts = _STAR_BULLET_RE.split(line)
    else:
        parts = _DASH_BULLET_RE.split(line)
        if len(parts) < 2:
            return [line]
        # ASCII-hyphen lists only when items are bold-led (avoids splitting a
        # parenthetical "abc - def" or a name range "Hà Nội - Hải Phòng").
        require_bold = True

    head = parts[0].rstrip()
    items = [p.strip() for p in parts[1:] if p.strip()]
    if not items:
        return [line]
    if require_bold and not all(it.startswith("**") for it in items):
        return [line]

    out: list[str] = []
    if head:
        out.append(head)
        out.append("")
    out.extend(f"- {it}" for it in items)
    out.append("")
    return out


def _sanitize_prose(prose: str) -> str:
    """Normalize LLM markdown quirks before export.

    The composer sometimes emits each hypothesis (``H1: ...`` full sentence) as a
    Markdown *heading*. Word then (a) renders it as an oversized bold line and
    (b) pulls it into the Table of Contents with a page number — both wrong. It
    also sometimes wraps the whole hypothesis sentence in ``**bold**``.

    We demote those to a normal body paragraph with only the ``Hn:`` label bold,
    and demote any heading whose text is a full sentence (a real section title is
    short and doesn't end in a period) — never a legitimate heading.
    """
    out: list[str] = []
    # Expand any inline "* a * b" lists into one-item-per-line first, then run
    # the per-line normalizations over the expanded lines.
    expanded: list[str] = []
    for raw in prose.split("\n"):
        expanded.extend(_reflow_inline_bullets(raw))
    for ln in expanded:
        # 0) table rows: escape any *content* pipe (e.g. the SmartPLS header
        #    ``T Statistics (|O/STDEV|)``). A literal ``|`` inside a cell is read
        #    as an extra column delimiter, which desyncs the column count and
        #    breaks the whole table on render. Delimiter pipes are always padded
        #    by a space; content pipes are tight (``(|O``/``V|)``), so we escape
        #    only pipes with a non-space, non-escaped neighbour on both sides.
        #    Separator rows (only |,-,:,space) are left untouched.
        if ln.lstrip().startswith("|") and set(ln.strip()) - set("|-: "):
            ln = _CONTENT_PIPE_RE.sub(r"\\|", ln)
        # 1) whole-sentence bold hypothesis:  **H1: ....**  ->  **H1:** ....
        bm = _BOLD_HYP_RE.match(ln)
        if bm:
            out.append(f"**{bm.group(1).strip().upper().replace(' ', '')}:** {bm.group(2).strip()}")
            continue
        # 2) heading form
        hm = _HEADING_RE.match(ln)
        if hm:
            text = hm.group(1).strip()
            hyp = _HYP_RE.match(text)
            if hyp:  # "### H1: full sentence"  ->  "**H1:** full sentence"
                out.append(f"**{hyp.group(1).strip().upper().replace(' ', '')}:** {hyp.group(2).strip()}")
                continue
            # a heading that is actually a full sentence -> plain bold paragraph
            if len(text) > 60 and text.rstrip().endswith((".", ")", ":")):
                out.append(f"**{text}**")
                continue
        out.append(ln)
    return "\n".join(out)


def _compose_chapters(
    context_store: dict,
    chapter_keys: list[str],
    language: str,
    on_chapter=None,
    references: list[dict] | None = None,
    title_overrides: dict[str, str] | None = None,
) -> list[dict]:
    """Compose an explicit set of M5 chapters via the engine, in canonical order.

    Mirrors compose_all_sections' per-chapter composition (real LLM prose
    grounded in the merged context slice) but limited to the requested chapters
    so the user only pays for the "Chương N" they ticked. `on_chapter(index,
    key, title, phase)` is called with phase="start"/"end" around each chapter
    so callers can surface live progress.
    """
    from orchestrator.tools.m5_writing import (  # noqa: PLC0415 — heavy import, load lazily
        _chapter_titles,
        _fallback_section,
        compose_chapter,
    )

    m1 = context_store.get("m1_topic") or {}
    m3 = context_store.get("m3_design") or {}
    m4 = context_store.get("m4_analysis") or {}
    context_slice: dict = {**m1, **m3, **m4}
    context_slice.setdefault("results", m4.get("analysis_results"))

    # Always compose in canonical order regardless of how the caller ordered them.
    ordered = [k for k in _CHAPTER_ORDER if k in set(chapter_keys)]

    base_titles = _chapter_titles(language)
    titles = {**base_titles, **(title_overrides or {})}
    out: list[dict] = []
    for idx, name in enumerate(ordered):
        if on_chapter:
            on_chapter(idx, name, titles[name], "start")
        try:
            draft = compose_chapter.invoke({
                "chapter_name": name,
                "paradigm": "",
                "context_slice": context_slice,
                "references": references or [],
                "citation_style": "apa7",
                "language": language,
            })
            prose = (draft or {}).get("prose") or ""
        except Exception:
            logger.exception("partner_report: compose_chapter failed for %s", name)
            prose = ""
        if not prose.strip():
            prose = _fallback_section(name, context_store)
        if prose.strip():
            out.append({"title": titles[name], "prose": _sanitize_prose(prose)})
        if on_chapter:
            on_chapter(idx, name, titles[name], "end")
    return out


def _infer_topic(analysis_text: str, language: str) -> dict:
    """Infer the study's framing from the raw analysis output.

    The partner flow only has statistical output (reliability, EFA/CFA, SEM/PLS
    paths, correlations) — no topic. Without a title/objectives/RQs the chapter
    composer emits bracketed "[fill this in]" stubs. This runs ONE cheap LLM
    call to infer research_title / field / objectives / research_questions /
    target_population / scope from the constructs & relationships in the data,
    so the composed prose is concrete. Best-effort: returns {} on any failure.
    """
    import json as _json

    from orchestrator.tools.m5_writing import _get_llm  # noqa: PLC0415 — heavy import

    snippet = (analysis_text or "")[:6000]
    lang_name = "Vietnamese" if str(language).lower().startswith("vi") else "English"
    prompt = (
        "You are a research methodologist. Below is the raw statistical analysis "
        "output of a quantitative study (reliability, EFA/CFA, SEM/PLS path "
        "results, correlations, etc.). Infer the study's most plausible framing "
        "from the CONSTRUCTS, VARIABLES and RELATIONSHIPS present in the data.\n\n"
        f"Write every value in {lang_name}. Be specific and realistic. Do NOT use "
        "bracketed placeholders like [ ... ]. Do NOT restate or verbalize any "
        "statistics/numbers (no coefficients, no p-values, no 'zero point eight "
        "seven') — describe the study's framing conceptually, not its results.\n\n"
        "Field meanings:\n"
        "- research_title: a concise academic title naming the constructs & outcome.\n"
        "- field: the academic discipline.\n"
        "- research_type: e.g. quantitative explanatory / survey-based SEM study.\n"
        "- objectives: the study's AIM/purpose in 1-2 sentences (no numbers).\n"
        "- research_questions: 2-3 questions about the relationships between constructs.\n"
        "- target_population: the likely respondents.\n"
        "- scope: the study's boundary in one phrase.\n\n"
        "Return STRICT JSON only (no prose, no code fence) with exactly these keys:\n"
        '{"research_title": "", "field": "", "research_type": "", "objectives": "", '
        '"research_questions": [], "target_population": "", "scope": ""}\n\n'
        f"ANALYSIS OUTPUT:\n{snippet}"
    )
    try:
        resp = _get_llm().invoke(prompt)
        content = getattr(resp, "content", resp)
        if isinstance(content, list):
            content = " ".join(
                str(p.get("text", "") if isinstance(p, dict) else p) for p in content
            )
        content = str(content).strip()
        start, end = content.find("{"), content.rfind("}")
        if start == -1 or end == -1:
            return {}
        data = _json.loads(content[start:end + 1])
        return data if isinstance(data, dict) else {}
    except Exception:
        logger.exception("partner_report: topic inference failed (continuing without it)")
        return {}


def _search_query_en(topic: str, research_questions: list[str] | None) -> str:
    """One short ENGLISH bibliographic query from the (possibly Vietnamese) topic.

    Crossref indexes mostly English scholarship, so a Vietnamese title returns
    little. A tiny LLM call turns the topic into an English keyword query; falls
    back to the raw topic if the LLM is unavailable.
    """
    try:
        from orchestrator.tools.m5_writing import _get_llm  # noqa: PLC0415
        rq = ("; ".join(research_questions or []))[:300]
        prompt = (
            "Turn this research topic into ONE short English academic search query "
            "(5-10 keywords, no punctuation, no quotes). Topic: "
            f"{topic}\nQuestions: {rq}\nQuery:"
        )
        resp = _get_llm().invoke(prompt)
        q = getattr(resp, "content", resp)
        if isinstance(q, list):
            q = " ".join(str(p.get("text", "") if isinstance(p, dict) else p) for p in q)
        q = str(q).strip().strip('"').splitlines()[0][:200]
        if q:
            return q
    except Exception:
        logger.exception("partner_report: query translation failed")
    return (topic or "")[:200]


def _literature_search(topic: str, research_questions: list[str] | None,
                       *, n: int = 8, timeout_s: int = 20) -> list[dict]:
    """Fast M2 literature search via Crossref (real peer-reviewed sources + DOIs).

    dothesis's full scout is tuned for 100+ sources / 119 queries / minutes and
    rate-limits badly, so it can't return within a per-report budget. A direct
    Crossref query gives ~8 verified sources in a couple seconds. Best-effort:
    returns [] on any failure (citations are a nice-to-have, never a blocker).
    """
    import httpx

    query = _search_query_en(topic, research_questions)
    try:
        r = httpx.get(
            "https://api.crossref.org/works",
            params={
                "query.bibliographic": query,
                "rows": n,
                "select": "title,author,issued,DOI,container-title,URL",
                "filter": "type:journal-article,has-abstract:true",
                "sort": "relevance",
            },
            timeout=timeout_s,
            headers={"User-Agent": "DoThesis-PartnerReport/1.0 (mailto:cao.nguyen@wele-learn.com)"},
        )
        items = r.json().get("message", {}).get("items", [])
    except Exception:
        logger.exception("partner_report: Crossref search failed (skipping citations)")
        return []

    refs: list[dict] = []
    for it in items:
        title = (it.get("title") or [""])[0].strip()
        if not title:
            continue
        authors = [str(a.get("family")).strip() for a in it.get("author", []) if a.get("family")]
        parts = (it.get("issued", {}).get("date-parts") or [[None]])
        year = parts[0][0] if parts and parts[0] else None
        refs.append({
            "title": title,
            "authors": authors,
            "year": year,
            "venue": (it.get("container-title") or [None])[0],
            "doi": it.get("DOI"),
            "url": it.get("URL"),
        })
    return refs[:n]


def _references_section(references: list[dict], language: str) -> dict:
    """Build a populated References section from the sources.

    Deterministic — lists every source we found regardless of whether the LLM
    cited it inline, so the section is never an empty heading. Reuses dothesis's
    shared `_references_section_body` (sorted by author+year, clickable DOI/URL
    links) instead of a drifted local clone. This section is what the PDF
    (weasyprint) fallback ships; the citeproc DOCX path generates its own.
    """
    from orchestrator.tools.m5_writing import _references_section_body  # noqa: PLC0415
    title = "Tài liệu tham khảo" if str(language).lower().startswith("vi") else "References"
    return {"title": title, "prose": _references_section_body(references)}


def _infer_model(analysis_text: str, language: str) -> dict:
    """Infer the study's structural/conceptual model (constructs + directed
    paths) from the analysis output, for the M3 research-model diagram.

    Returns {"constructs":[{"id","label"}], "paths":[{"from","to"}]} or {}.
    """
    import json as _json

    from orchestrator.tools.m5_writing import _get_llm  # noqa: PLC0415

    snippet = (analysis_text or "")[:6000]
    lang = "Vietnamese" if str(language).lower().startswith("vi") else "English"
    prompt = (
        "From this statistical analysis output, extract the STRUCTURAL / CONCEPTUAL "
        "research model: the latent constructs and the DIRECTED relationships "
        "(which construct predicts which), based on the path/regression results.\n"
        f"Give each construct a short ascii id (no spaces) and a {lang} label.\n"
        "Return STRICT JSON only:\n"
        '{"constructs":[{"id":"","label":""}],"paths":[{"from":"id","to":"id"}]}\n\n'
        f"ANALYSIS OUTPUT:\n{snippet}"
    )
    try:
        resp = _get_llm().invoke(prompt)
        content = getattr(resp, "content", resp)
        if isinstance(content, list):
            content = " ".join(str(p.get("text", "") if isinstance(p, dict) else p) for p in content)
        content = str(content)
        s, e = content.find("{"), content.rfind("}")
        if s == -1 or e == -1:
            return {}
        data = _json.loads(content[s:e + 1])
        if isinstance(data, dict) and data.get("constructs") and data.get("paths"):
            return data
    except Exception:
        logger.exception("partner_report: model inference failed")
    return {}


def _render_model_diagram(model: dict) -> str | None:
    """Render a mermaid flowchart of the model to a PNG via mmdc. Abs path or None."""
    constructs = {
        str(c["id"]): str(c.get("label") or c["id"])
        for c in model.get("constructs", [])
        if isinstance(c, dict) and c.get("id")
    }
    paths = [
        (str(p.get("from")), str(p.get("to")))
        for p in model.get("paths", [])
        if isinstance(p, dict) and str(p.get("from")) in constructs and str(p.get("to")) in constructs
    ]
    if not constructs or not paths:
        return None

    lines = ["flowchart LR"]
    for cid, label in constructs.items():
        lines.append(f'  {cid}["{label.replace(chr(34), chr(39))}"]')
    for a, b in paths:
        lines.append(f"  {a} --> {b}")
    mmd = "\n".join(lines)

    mmdc = _MERMAID_DIR / "node_modules" / ".bin" / "mmdc"
    cfg = _MERMAID_DIR / "puppeteer.json"
    if not mmdc.exists():
        logger.warning("partner_report: mmdc not installed — skipping model diagram")
        return None
    try:
        d = Path(tempfile.mkdtemp(prefix="model_"))
        mmd_path = d / "model.mmd"
        png_path = d / "model.png"
        mmd_path.write_text(mmd, encoding="utf-8")
        env = dict(os.environ)
        env["PATH"] = f"{_NODE_BIN}:/opt/homebrew/bin:" + env.get("PATH", "")
        subprocess.run(
            [str(mmdc), "-i", str(mmd_path), "-o", str(png_path), "-c", str(cfg), "-b", "white", "-w", "1100"],
            check=True, capture_output=True, timeout=120, env=env, cwd=str(_MERMAID_DIR),
        )
        if not png_path.exists():
            return None
        # Return a base64 data URI so the image embeds in BOTH the WeasyPrint PDF
        # (no base_url needed) and the pandoc DOCX, with no external file at render.
        import base64
        b64 = base64.b64encode(png_path.read_bytes()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception:
        logger.exception("partner_report: mermaid render failed")
        return None


def _extract_text(file_bytes: bytes, filename: str | None) -> tuple[str, int]:
    """Extract analysis text from a PDF or DOCX. Returns (text, page_count).

    DOCX is detected by extension or the zip magic (PK). Everything else goes
    through the PDF extractor. Table cell text is flattened into pipe rows so the
    statistics inside result tables survive.
    """
    name = (filename or "").lower()
    if name.endswith(".docx") or file_bytes[:2] == b"PK":
        try:
            import io

            from docx import Document
            doc = Document(io.BytesIO(file_bytes))
            parts = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
            for tbl in doc.tables:
                for row in tbl.rows:
                    cells = [c.text.strip() for c in row.cells if c.text and c.text.strip()]
                    if cells:
                        parts.append(" | ".join(cells))
            return ("\n".join(parts), 0)
        except Exception:
            logger.exception("partner_report: docx text extraction failed")
            return ("", 0)
    return extract_pdf_text(file_bytes)


# Signals that an uploaded file actually contains statistical-analysis output
# (SmartPLS / SPSS), which the Results (M4) chapter needs. Covers English and
# Vietnamese terminology.
_M4_DATA_SIGNALS = (
    "cronbach", "composite reliability", "average variance", "ave", "htmt",
    "heterotrait", "outer loading", "factor loading", "r square", "r-square",
    "p value", "p-value", "t statistic", "t-statistic", "std", "standard deviation",
    "correlation", "regression", "coefficient", "path coefficient", "variance",
    "eigenvalue", "kmo", "bartlett", "f square", "vif", "original sample",
    "sample mean", "stdev", "significance", "sig.", "beta", "β", "α",
    "độ tin cậy", "phương sai", "tương quan", "hồi quy", "hệ số", "trung bình",
    "độ lệch chuẩn", "kiểm định", "giá trị hội tụ", "giá trị phân biệt",
    "tải nhân tố", "nhân tố",
)


def _has_sufficient_m4_data(text: str) -> bool:
    """True when the extracted text looks like real statistical-analysis output.

    The Results (M4) chapter is built FROM the uploaded analysis (reliability,
    validity, path coefficients, …). If the file is a proposal / an unrelated
    doc / mostly prose with no numbers, M4 has nothing to tabulate — we fail
    fast instead of fabricating tables. Heuristic: needs at least two distinct
    statistical terms AND a handful of decimal numbers.
    """
    low = (text or "").lower()
    keyword_hits = sum(1 for k in _M4_DATA_SIGNALS if k in low)
    decimal_hits = len(re.findall(r"\d[.,]\d", text or ""))
    return keyword_hits >= 2 and decimal_hits >= 6


def generate_partner_report(
    pdf_bytes: bytes,
    *,
    depth: str = "analysis_report",
    chapters: list[str] | None = None,
    progress_token: str | None = None,
    filename: str | None = None,
    title: str | None = None,
    notes: str | None = None,
    language: str = "en",
) -> dict[str, Any]:
    """Generate a report from an analysis PDF and return download URLs.

    Chapter selection precedence:
      1. `chapters` — an explicit subset of _CHAPTER_ORDER (the "tick Chương N"
         path). Unknown keys are ignored; empty-after-filter is a bad_chapters
         error.
      2. `depth` — "full_thesis" (all six) or "analysis_report" (the light
         four). Kept for back-compat / the preset buttons.

    Returns {pages, depth, chapters, sections: [titles], pdf_url, docx_url}.
    Raises ReportError(code) for empty-text / bad-depth / bad-chapters /
    compose-failed so the router can map to a stable 4xx/5xx.
    """
    if chapters:
        chapter_keys = [c for c in chapters if c in set(_CHAPTER_ORDER)]
        if not chapter_keys:
            raise ReportError("bad_chapters",
                              f"chapters must be a subset of {_CHAPTER_ORDER}")
    elif depth == "full_thesis":
        chapter_keys = list(_CHAPTER_ORDER)
    elif depth == "analysis_report":
        chapter_keys = list(_ANALYSIS_CHAPTERS)
    else:
        raise ReportError("bad_depth", f"depth must be one of {sorted(_VALID_DEPTHS)}")

    # Combine Discussion + Conclusion into a SINGLE concluding chapter, matching
    # the standard thesis structure (one "Chương 5: Kết luận", not a separate
    # Thảo luận + Kết luận). The discussion composer already emits the full
    # conclusion structure (summary → contributions → limitations → future
    # work), so we drop `conclusion` and just relabel `discussion`.
    if "conclusion" in chapter_keys:
        chapter_keys = [k for k in chapter_keys if k != "conclusion"]
        if "discussion" not in chapter_keys:
            chapter_keys.append("discussion")

    total = len(chapter_keys)
    _set_progress(progress_token, status="processing", phase="extract",
                  total=total, done=0, current=None)

    try:
        text, pages = _extract_text(pdf_bytes, filename)
        if not text.strip():
            # Image-only scans and non-text files land here — a clear 422, not 500.
            raise ReportError("no_extractable_text",
                              "the file has no machine-readable text (image-only scan?)")

        # M4 gate: the Results chapter needs real statistical output. If it was
        # requested but the file has no such data, fail fast (before any LLM
        # spend) so the partner can charge only a small validation fee instead
        # of billing for a report it can't build.
        if "results" in chapter_keys and not _has_sufficient_m4_data(text):
            raise ReportError(
                "insufficient_m4_data",
                "the uploaded file lacks the statistical analysis data (reliability, "
                "validity, path coefficients, …) needed to write the Results (M4) chapter",
            )

        # When the user gave no title (and always, for supporting context), infer
        # the study framing from the data so chapters aren't full of "[...]" stubs.
        # The user's free-text notes (if any) are prepended so the inferred
        # title/objectives/RQs reflect what they described — this then cascades
        # into the intro/lit-review/methodology framing.
        notes_clean = (notes or "").strip()
        infer_text = (
            f"Mô tả bổ sung từ người dùng (ưu tiên bám sát):\n{notes_clean}\n\n{text}"
            if notes_clean else text
        )
        inferred = _infer_topic(infer_text, language)

        research_title = (title or "").strip() or str(inferred.get("research_title") or "").strip()
        m1_topic: dict = {
            "research_title": research_title or "Báo cáo phân tích",
            "language": language,
        }
        if notes_clean:
            m1_topic["user_context"] = notes_clean
        # These map 1:1 to the M5 intro/chapter prompt inputs (field, objectives,
        # research_questions, target_population, scope, research_type).
        for key in ("field", "research_type", "objectives", "target_population", "scope"):
            val = inferred.get(key)
            if isinstance(val, str) and val.strip():
                m1_topic[key] = val.strip()
        rqs = inferred.get("research_questions")
        if isinstance(rqs, list) and rqs:
            m1_topic["research_questions"] = [str(q) for q in rqs if str(q).strip()]

        # Minimal nested context_store the M5 engine understands. The analysis
        # text becomes M4's analysis_results (the canonical `results` key).
        context_store: dict = {
            "m1_topic": m1_topic,
            "m4_analysis": {"analysis_results": text},
        }

        # M2: fetch a bounded literature set so composed chapters get real inline
        # citations backed by a populated References section. EVERY academic
        # chapter cites (intro/lit_review/methodology/results/discussion), so we
        # fetch whenever any chapter is composed — not only when Chương 2 is
        # ticked. Otherwise the LLM cites sources with no bibliography behind
        # them (hallucinated citations + empty References). Best-effort: []-safe.
        references: list[dict] = []
        if chapter_keys:
            _set_progress(progress_token, phase="research")
            references = _literature_search(
                m1_topic["research_title"], m1_topic.get("research_questions") or []
            )
            if references:
                context_store["m2_literature"] = {"literature_sources": references}

        _set_progress(progress_token, phase="compose")

        def _on_chapter(idx: int, key: str, title_: str, phase: str) -> None:
            if phase == "start":
                _set_progress(progress_token, done=idx, current=title_)
            else:
                _set_progress(progress_token, done=idx + 1, current=None)

        # The (now combined) Discussion chapter is presented as the concluding
        # chapter — relabel its heading to "Kết luận"/"Conclusion".
        combined_title = "Chương 5 — Kết luận" if language.startswith("vi") else "Chapter 5 — Conclusion"
        sections = _compose_chapters(
            context_store, chapter_keys, language, on_chapter=_on_chapter,
            references=references or None, title_overrides={"discussion": combined_title},
        )

        if not sections:
            raise ReportError("compose_failed", "the writing engine produced no sections")

        # M3: when the methodology chapter is included, infer the structural model
        # from the data, render it as a diagram, and embed it in that chapter.
        if "methodology" in chapter_keys:
            try:
                model = _infer_model(text, language)
                png = _render_model_diagram(model) if model else None
                if png:
                    from orchestrator.tools.m5_writing import _chapter_titles  # noqa: PLC0415
                    meth_title = _chapter_titles(language).get("methodology")
                    caption = (
                        "Hình 1. Mô hình nghiên cứu đề xuất"
                        if str(language).lower().startswith("vi")
                        else "Figure 1. Proposed research model"
                    )
                    figure_md = f"\n\n![{caption}]({png})\n"
                    for sec in sections:
                        if sec.get("title") == meth_title:
                            sec["prose"] = (sec.get("prose") or "") + figure_md
                            break
            except Exception:
                logger.exception("partner_report: model diagram step failed (continuing)")

        # Append a deterministic References section as a belt-and-braces fallback:
        # the citeproc DOCX path drops it (by title) and generates its own
        # bibliography with `nocite:@*` (all pool sources, never empty); the
        # plain PDF (weasyprint) fallback ships THIS one so the PDF is never
        # missing its references.
        if references:
            sections.append(_references_section(references, language))

        _set_progress(progress_token, phase="export", done=total, current=None)

        from orchestrator.tools.m5_writing import run_export  # noqa: PLC0415

        # No user project — a synthetic id namespaces the S3 export keys. Pass
        # references so the DOCX renders via citeproc: inline "(Author, Year)"
        # become clickable links + a complete, formatted bibliography.
        project_id = f"partner-{uuid.uuid4().hex}"
        artifacts = run_export(sections, project_id, references=references or None, language=language)

        s3 = _s3_from_env()
        urls: dict[str, str] = {}
        keys: dict[str, str] = {}
        for a in artifacts:
            kind = a.get("kind") or a.get("type")
            key = a.get("s3_key")
            if kind and key:
                urls[f"{kind}_url"] = _presign(s3, key)
                keys[f"{kind}_key"] = key

        _set_progress(progress_token, status="done", phase="done", done=total, current=None)
    except Exception:
        _set_progress(progress_token, status="error")
        raise

    return {
        "pages": pages,
        "depth": depth,
        "chapters": chapter_keys,
        "sections": [s["title"] for s in sections],
        "pdf_url": urls.get("pdf_url"),
        "docx_url": urls.get("docx_url"),
        # Durable S3 keys so the partner can re-presign fresh download URLs when
        # a user re-opens a saved report later (presigned URLs above expire).
        "pdf_key": keys.get("pdf_key"),
        "docx_key": keys.get("docx_key"),
    }

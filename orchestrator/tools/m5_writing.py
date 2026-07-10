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

from orchestrator.message_utils import text_of  # flatten Gemini 3.x list content

import boto3
from langchain_core.tools import tool

# Make engine package importable.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
# AND put engine/ itself on the path. The engine modules use repo-internal
# imports like `from utils.logging_config import get_logger` (engine/ as the
# root), so importing them as `engine.utils.*` from the api process fails at
# THAT line unless engine/ is also a sys.path root. This was the cause of M5
# exports landing as 24-byte placeholders (0 KB): _export_docx_via_engine's
# `from engine.utils.export_professional import …` raised ModuleNotFoundError
# on the internal `from utils.…`, the except branch wrote the placeholder.
_ENGINE = _ROOT / "engine"
if str(_ENGINE) not in sys.path:
    sys.path.insert(0, str(_ENGINE))

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


def _ref_author_label(ref: dict) -> str:
    """Derive the inline-citation author label from a reference record.

    M2 sources carry `authors` as a LIST (e.g. ["Nguyen", "Tran"] or ["NIH"]);
    earlier code read a singular `author` key that doesn't exist, so EVERY
    reference collapsed to "Anon" — which is exactly what the LLM then cited
    ("(Anon, 2011)"). This reads the real list: first author's surname, plus
    "et al." when there are co-authors. Falls back to a singular `author` field
    or "Anon" only when nothing usable is present.
    """
    authors = ref.get("authors")
    if isinstance(authors, list) and authors:
        first = str(authors[0]).strip()
        surname = first.split()[-1] if first else ""
        if surname:
            return f"{surname} et al." if len(authors) > 1 else surname
    single = str(ref.get("author") or "").strip()
    return single or "Anon"


def _ref_citation_key(ref: dict) -> tuple[str, str]:
    """(author_label, year_str) used as the canonical pool key for a reference,
    shared by the prompt formatter and the citation validators so they agree."""
    return (_ref_author_label(ref), str(ref.get("year", "")).strip())

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
    pool_keys = {_ref_citation_key(r) for r in reference_pool}
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
    # Build a pool of (author_label, year) tuples from references via the
    # shared key helper — reads the `authors` LIST, not a non-existent
    # `author` field (the bug that made every reference "Anon").
    pool = {_ref_citation_key(r) for r in references}
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


def _sections_to_markdown(sections: list[dict]) -> str:
    """Flatten [{title, prose}] into a single markdown document.

    The engine renderers (engine/utils/export_professional) consume a
    markdown *file*, not a Python list — so this is the missing adapter
    that lets the orchestrator's section list reach the real Pandoc-backed
    export. `prose` is assumed to already be markdown (chapter composers
    emit markdown); we only prepend an H1 per section title.
    """
    parts: list[str] = []
    for sec in sections:
        # Accept both section conventions: compose_all_sections emits
        # {title, prose}; the M5 agent's _build_sections_for_export historically
        # emitted {name, text}. Reading only title/prose silently dropped every
        # chapter's heading AND body for the agent path → a styles-only (blank)
        # docx/pdf. Normalize both here so neither producer can lose content.
        title = (sec.get("title") or "").strip()
        if not title and sec.get("name"):
            title = M5_CHAPTER_TITLES.get(
                sec["name"], str(sec["name"]).replace("_", " ").title())
        prose = (sec.get("prose") or sec.get("body")
                 or sec.get("text") or sec.get("content") or "").strip()
        # Defensive last line: strip internal placeholder/QA text so it can
        # never reach the rendered document, even on a forced export, then
        # normalize inline-bullet runs into proper markdown lists.
        prose = _normalize_prose_markdown(
            _mermaid_to_prose(_split_run_on_hypotheses(_scrub_internal_markers(prose)))
        )
        # Defense-in-depth against the duplicate chapter heading: the prompt
        # tells the LLM not to emit the chapter title, but Gemini sometimes
        # leads with its own "# Chương N: …" / "## <chapter title>" anyway, and
        # we prepend `# {title}` below — yielding the heading twice. Strip a
        # leading chapter-level heading (but never a numbered sub-section like
        # "## 4.1 …", which is real content).
        if title:
            prose = _strip_leading_chapter_heading(prose, title)
            parts.append(f"# {title}")
        if prose:
            parts.append(prose)
    md = "\n\n".join(parts) + "\n"
    # Normalize long dashes to a plain hyphen across the whole output (chapter
    # titles + prose): the LLM peppers prose with em-dashes and our headings use
    # them, which reads as machine-generated. Runs AFTER list-reflow (which must
    # distinguish en-dashes from ASCII hyphens), so it can't disturb that.
    md = md.replace("—", "-").replace("–", "-")
    return md


def _strip_leading_chapter_heading(prose: str, title: str | None = None) -> str:
    """Drop a leading chapter-title line the LLM emitted despite the prompt.

    We prepend `# {title}` to every section, so a chapter that opens with its
    own title renders the title twice (the "Chương N appears twice" bug). Remove
    the first non-blank line ONLY when it is a chapter title in one of these
    shapes, and never a numbered sub-section (`4.1`, `2.3.1`) which is content:
      (a) an ATX heading `#`..`######` (any level) that isn't a sub-section;
      (b) a NON-heading line the LLM wrote as plain/bold text, e.g.
          `CHƯƠNG 4: KẾT QUẢ NGHIÊN CỨU` or `**Chapter 4 - Results**` — this is
          what pandoc rendered as a stray `Normal` paragraph under the H1;
      (c) a line whose marker-stripped text equals the prepended `title`.
    """
    if not prose:
        return prose
    lines = prose.split("\n")
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines):
        return prose
    line = lines[i]
    rest = lambda: "\n".join(lines[i + 1:]).strip()

    # (a) ATX heading (widened to any level) that is not a numbered sub-section.
    m = re.match(r"^\s*#{1,6}\s+(.+?)\s*$", line)
    if m and not re.match(r"^\d+(\.\d+)+\b", m.group(1).strip()):
        return rest()

    # marker-stripped text: drop leading `#`s and surrounding `**` bold markers.
    bare = re.sub(r"^\s*#*\s*", "", line.strip())
    bare = re.sub(r"^\*\*\s*|\s*\*\*$", "", bare).strip()
    # (b) a title-shaped chapter line (bounded length so real sentences that
    #     merely start "Chương 4: trình bày…" — long — are never stripped).
    if re.match(r"(?i)^(CHƯƠNG|CHAPTER)\s+\d+\s*[:.\-–—]\s*.{0,80}$", bare) \
            and not re.match(r"^\d+(\.\d+)+\b", bare):
        return rest()
    # (c) exact match against the prepended title (any marker form).
    if title and bare and bare.casefold() == title.strip().casefold():
        return rest()
    return prose


def _scrub_internal_markers(prose: str) -> str:
    """Remove engine-internal placeholder/QA text that must never appear in a
    final thesis (composition stubs, the old uncited-citation warning block)."""
    if not prose:
        return prose
    # Drop the legacy "⚠️ … may be hallucinated …" blockquote if any survived.
    prose = re.sub(r"\n?>\s*⚠️[^\n]*\n?", "", prose)
    # Drop bracketed composition placeholders like "[Composition failed …]"
    # and "[Auto-generated for '…']".
    prose = re.sub(r"\[(?:Composition failed|Auto-generated for)[^\]]*\]", "", prose)
    return prose.strip()


def _split_run_on_hypotheses(prose: str) -> str:
    """Break a paragraph that lists H1/H2/H3… inline into ONE paragraph per H.

    The M5 discussion composer sometimes emits every hypothesis as a
    continuous run: "Cụ thể: - H1: KOL … (β=…). - H2: HATH … (β=…). - H3: …"
    That reads as a wall of prose because the separators aren't at line start
    (so `_normalize_prose_markdown` doesn't fire). Insert a real paragraph
    break before each `Hn:` marker so each hypothesis stands as its own block.

    Handles: `- H1:`, `– H1:`, `- **H1:**`, `**H1:**`, with the leading dash
    optional; the leading intro `Cụ thể: -` stays with its sentence.
    """
    if not prose or "H1" not in prose:
        return prose
    # Match a hypothesis marker that isn't already at line start. Uses a
    # positive lookahead so the marker text is preserved.
    # Group: whitespace/dash before "H<n>:" (or "**H<n>:**") in-line.
    pattern = re.compile(
        r"(?<!\n)[ \t]*[-–—]?[ \t]*(\*\*)?H\d{1,2}:",
    )

    def _sub(m: "re.Match[str]") -> str:
        marker = m.group(0).lstrip(" \t-–—")
        # Preserve the ** if present.
        return "\n\n" + marker.lstrip()

    out = pattern.sub(_sub, prose)
    # First H may end up as "\n\nH1:" at the very start; strip leading blanks.
    return out.lstrip("\n")


def _render_mermaid_png(mmd_source: str, out_path: Path) -> bool:
    """Render mermaid source to a PNG via the local @mermaid-js/mermaid-cli.

    Puppeteer's own Chrome-for-Testing binary is used (the OS Chrome install
    fails to connect over the puppeteer WS socket on macOS). Returns True on a
    real PNG, False when the CLI is missing / times out — the caller falls back
    to a text list so the document still ships.
    """
    import os as _os
    import subprocess as _subprocess
    import shutil as _shutil

    engine_root = Path(__file__).resolve().parents[2] / "engine"
    mmdc_dir = engine_root / "tools" / "mermaid_cli"
    mmdc = mmdc_dir / "node_modules" / ".bin" / "mmdc"
    if not mmdc.exists():
        return False
    # Locate puppeteer's own Chrome. It gets installed under ~/.cache/puppeteer
    # (or the value of PUPPETEER_CACHE_DIR). Pick the highest-versioned dir.
    chrome_bin: Path | None = None
    cache_dir = Path(_os.environ.get("PUPPETEER_CACHE_DIR",
                                     Path.home() / ".cache" / "puppeteer"))
    chrome_root = cache_dir / "chrome"
    if chrome_root.exists():
        versions = sorted(chrome_root.iterdir(), key=lambda p: p.name, reverse=True)
        for v in versions:
            # macOS layout: <v>/chrome-mac-arm64/Google Chrome for Testing.app/…
            for candidate in v.rglob("Google Chrome for Testing"):
                if candidate.is_file():
                    chrome_bin = candidate
                    break
            if chrome_bin:
                break
            # Linux layout: <v>/chrome-linux64/chrome
            for candidate in v.rglob("chrome"):
                if candidate.is_file():
                    chrome_bin = candidate
                    break
            if chrome_bin:
                break

    mmd_path = out_path.with_suffix(".mmd")
    mmd_path.write_text(mmd_source, encoding="utf-8")
    puppeteer_cfg = mmdc_dir / "puppeteer.json"
    if not puppeteer_cfg.exists():
        puppeteer_cfg.write_text(
            '{ "args": ["--no-sandbox", "--disable-setuid-sandbox"] }',
            encoding="utf-8",
        )

    env = _os.environ.copy()
    if chrome_bin:
        env["PUPPETEER_EXECUTABLE_PATH"] = str(chrome_bin)
    cmd = [str(mmdc), "-p", str(puppeteer_cfg), "-i", str(mmd_path),
           "-o", str(out_path), "-w", "1100", "-b", "white"]
    try:
        result = _subprocess.run(cmd, env=env, capture_output=True, timeout=45)
    except (_subprocess.TimeoutExpired, OSError) as e:
        logger.warning("mermaid render failed: %s", e)
        return False
    finally:
        try:
            mmd_path.unlink(missing_ok=True)
        except Exception:
            pass
    if result.returncode != 0:
        logger.warning("mmdc exit=%s stderr=%s",
                       result.returncode, result.stderr[:200].decode(errors="ignore"))
        return False
    return out_path.exists() and out_path.stat().st_size > 200


def _mermaid_to_prose(prose: str) -> str:
    """DOCX/PDF can't render Mermaid syntax directly. Replace ```mermaid``` (or
    a bare `flowchart LR …`) with a rendered PNG image + a text-list caption
    (relationships) so the document has BOTH the visual and the source of truth.

    On render failure (mmdc missing / puppeteer timeout) the diagram falls back
    to just the text list — the doc still ships, just without the picture.
    """
    low = prose.lower()
    if "flowchart" not in low and "graph " not in low and "mermaid" not in low:
        return prose
    labels = dict(re.findall(r"([A-Za-z0-9_]+)\[([^\]]+)\]", prose))
    edges: list[tuple[str, str, str]] = []
    for em in re.finditer(
        r"([A-Za-z0-9_]+)(?:\[[^\]]*\])?\s*-\.?-?->\s*(?:\|([^|]*)\|)?\s*([A-Za-z0-9_]+)(?:\[[^\]]*\])?",
        prose,
    ):
        s = (labels.get(em.group(1), em.group(1)) or "").strip()
        t = (labels.get(em.group(3), em.group(3)) or "").strip()
        edges.append((s, t, (em.group(2) or "").strip()))
    if not edges:
        return prose  # not a parseable diagram — don't risk mangling real prose

    # Reconstruct a clean mermaid source from what we parsed (drops any prose
    # accidentally interleaved with the diagram lines) — this is what we hand
    # to mmdc. Nodes use their long labels; edges keep the pipe-labeled arrow
    # so the hypothesis id ("H1: +") shows on the arrow.
    # Regex with THREE groups: src_id, edge_label (optional), tgt_id.
    edge_re = re.compile(
        r"([A-Za-z0-9_]+)(?:\[[^\]]*\])?\s*-\.?-?->\s*(?:\|([^|]*)\|)?\s*([A-Za-z0-9_]+)"
    )
    parsed_edges = [(m.group(1), (m.group(2) or "").strip(), m.group(3))
                    for m in edge_re.finditer(prose)]
    mmd_lines = ["flowchart LR"]
    seen_nodes: set[str] = set()
    for src_id, _e, tgt_id in parsed_edges:
        for nid in (src_id, tgt_id):
            if nid in seen_nodes:
                continue
            seen_nodes.add(nid)
            lbl = labels.get(nid, nid).replace('"', "'")
            mmd_lines.append(f'    {nid}["{lbl}"]')
    for s_id, e_lbl, t_id in parsed_edges:
        if e_lbl:
            mmd_lines.append(f'    {s_id} -->|{e_lbl}| {t_id}')
        else:
            mmd_lines.append(f'    {s_id} --> {t_id}')
    mmd_source = "\n".join(mmd_lines)

    # Drop mermaid syntax lines from the surrounding prose.
    keep: list[str] = []
    for line in prose.split("\n"):
        st = line.strip().strip("`").strip()
        if re.match(r"^(flowchart|graph)\s+\w+", st, re.I):
            continue
        if st.lower() == "mermaid":
            continue
        if "-->" in st or "-.->" in st:
            continue
        if re.match(r"^[A-Za-z0-9_]+\[[^\]]*\]$", st):
            continue
        keep.append(line)

    # Try to render to PNG (in the same scratch dir the md file lives in, so
    # pandoc's relative-image resolution finds it via absolute path).
    img_line = ""
    try:
        png_path = _scratch_dir() / f"conceptmodel-{uuid4().hex[:8]}.png"
        if _render_mermaid_png(mmd_source, png_path):
            # Pandoc: `![caption](abs/path/img.png)`. Absolute path is fine.
            img_line = f'\n![Mô hình nghiên cứu]({png_path})\n'
    except Exception:
        logger.exception("mermaid render step failed")

    rel = ["", "**Mối quan hệ giả thuyết trong mô hình:**", ""]
    rel += [f"- {s} → {t}" + (f" ({e})" if e else "") for s, t, e in edges]
    return "\n".join(keep).rstrip() + img_line + "\n" + "\n".join(rel) + "\n"


def _normalize_prose_markdown(prose: str) -> str:
    """Fix the most common LLM markdown mistake: bullet items mushed onto one
    line ("Goals: * a * b * c"), which pandoc renders as literal asterisks in a
    paragraph instead of a real list. Splits such runs into a proper
    newline-separated markdown list with a blank line before it.

    Conservative: only triggers when a line has 2+ inline markers
    (a near-certain inlined list), so it won't disturb `*emphasis*`/`**bold**`
    (no surrounding spaces) or a single stray asterisk. The marker set covers
    `*`, `-`, the en-dash `–`, the em-dash `—`, and the bullet `•` — LLMs emit
    any of these for an inlined list (e.g. hypotheses "… – H1: … – H2: …"), and
    only the hyphen was caught before, leaving en-dash lists run together.
    """
    if not prose:
        return prose

    out_lines: list[str] = []
    for line in prose.split("\n"):
        # A real list line already starts with a marker — leave it alone.
        if re.match(r"^\s*([*\-+–—•]|\d+\.)\s+", line):
            out_lines.append(line)
            continue
        # `*` / `•` are unambiguous inline-list markers. `-`/`–`/`—` double as
        # PARENTHETICAL dashes ("text — aside — more"), so only treat them as a
        # list when the items are bold-led labels — otherwise a dash-parenthetical
        # sentence gets wrongly chopped into bullets.
        star = re.findall(r"\s[*•]\s+\S", line)
        dash = re.findall(r"\s[-–—]\s+\S", line)
        parts = None
        require_bold = False
        if len(star) >= 2:
            parts = re.split(r"\s+[*•]\s+", line)
        elif len(dash) >= 2:
            parts = re.split(r"\s+[-–—]\s+", line)
            require_bold = True
        if parts is not None:
            head = parts[0].strip()
            items = [p.strip() for p in parts[1:] if p.strip()]
            if len(items) >= 2 and (not require_bold or all(it.startswith("**") for it in items)):
                if head:
                    out_lines.append(head)
                    out_lines.append("")
                out_lines.extend(f"- {it}" for it in items)
                continue
        out_lines.append(line)
    return "\n".join(out_lines)


# YAML block that makes pandoc citeproc emit EVERY bibliography entry, even ones
# not matched by an inline `[@key]`. Uses the literal-block form (the documented
# way — `-M nocite=@*` on the CLI is a plain MetaString citeproc won't parse).
_NOCITE_FRONTMATTER = "---\nnocite: |\n  @*\n---"


def _write_markdown_tmp(sections: list[dict], frontmatter: str | None = None) -> Path:
    md = _sections_to_markdown(sections)
    if frontmatter:
        md = frontmatter.rstrip("\n") + "\n\n" + md
    md_path = _scratch_dir() / f"draft-{uuid4().hex[:8]}.md"
    md_path.write_text(md, encoding="utf-8")
    return md_path


def _compile_pdf_via_engine(sections: list[dict], output_path: str, **kw) -> str:
    """Render sections to a PDF via engine/utils/export_professional.export_pdf.

    The engine fn takes (md_file, output_pdf) and has its own multi-engine
    fallback (libreoffice → pandoc → weasyprint); if none are available it
    returns False and we drop a minimal placeholder so the pipeline still
    produces a downloadable artifact instead of raising.
    """
    try:
        from engine.utils.export_professional import export_pdf
        md_path = _write_markdown_tmp(sections)
        ok = export_pdf(md_path, Path(output_path), **kw)
        if ok and Path(output_path).exists():
            return output_path
        logger.warning("engine export_pdf returned falsy — writing placeholder")
    except Exception as e:
        logger.warning("engine export_pdf failed: %s — writing placeholder", e)
    Path(output_path).write_bytes(b"%PDF-1.4\n%% placeholder - engine renderer unavailable\n")
    return output_path


def _export_docx_via_engine(sections: list[dict], output_path: str,
                            frontmatter: str | None = None,
                            populate_toc: bool = False, **kw) -> str:
    """Render to .docx via engine/utils/export_professional.export_docx.

    Same (md_file, output) contract + internal Pandoc fallback as the PDF
    path. NOTE: the earlier import target (docx_post_processor) had no
    export_docx — that's why every prior export produced a placeholder.

    `frontmatter` is prepended to the markdown (used for the `nocite: @*` block).
    `populate_toc` fills the pandoc-inserted (otherwise empty) Word TOC field
    with static entries so the DOCX opens with a visible table of contents.
    """
    try:
        from engine.utils.export_professional import export_docx as _real
        md_path = _write_markdown_tmp(sections, frontmatter=frontmatter)
        ok = _real(md_path, Path(output_path), **kw)
        if ok and Path(output_path).exists():
            if populate_toc:
                try:
                    _populate_docx_toc(output_path)
                except Exception as e:  # noqa: BLE001 — TOC is best-effort
                    logger.warning("populate TOC failed: %s", e)
            return output_path
        logger.warning("engine export_docx returned falsy — writing placeholder")
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
    """One reference per line, with the EXACT inline-citation form to use.

    Shows the LLM the precise `(Author, Year)` string it must reproduce so it
    cites real sources instead of inventing "(Anon, 2011)". The author label
    comes from `_ref_author_label` (reads the `authors` list), so it matches
    what `validate_citations` will accept.
    """
    if not refs:
        return "(no references available — write WITHOUT inline citations)"
    lines = [
        "Cite ONLY from this list, using the exact (Author, Year) form shown. "
        "Do NOT invent citations. If no source fits a claim, state it without a citation."
    ]
    for i, r in enumerate(refs, 1):
        label = _ref_author_label(r)
        year = r.get("year", "n.d.")
        title = r.get("title", "")
        venue = r.get("venue", "")
        cite = f"({label}, {year})"
        lines.append(f"[{i}] {cite} — {title}{(' · ' + venue) if venue else ''}".strip())
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


# Matches ONLY `{valid_python_identifier}` — leaves `{N+1}`, `{"json": 1}`, and
# any other stray braces in a prompt template untouched.
_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _fill_template(template: str, kwargs: dict) -> str:
    """Substitute `{key}` placeholders without str.format()'s brittleness.

    str.format() parses EVERY brace in the template, so a literal `{N+1}` or a
    JSON example like `{"x": 1}` in a prompt file raises KeyError/ValueError and
    aborts the whole chapter (the "[Composition failed — please retry]" bug —
    only results.md had a stray `4.{N+1}`). This fills known identifier
    placeholders and leaves any other brace content exactly as written.
    """
    def _repl(m: "re.Match") -> str:
        key = m.group(1)
        return str(kwargs[key]) if key in kwargs else m.group(0)

    return _PLACEHOLDER_RE.sub(_repl, template)


# A "citation-shaped" parenthetical: `(<author text with a letter>, <YYYY>)`.
# Broader than _CITE_PATTERN so it catches every form a Vietnamese-language LLM
# emits — `(Hair & Ringle, 2019)`, `(Nguyễn và cộng sự, 2021)`, `(Đặng, 2019)`,
# `(Smith, 2020; Jones, 2021)` — while NOT matching non-citations that lack a
# real year: `(xem Bảng 4.1)`, `(β = 0.302, p = 0.000)`, `(N = 188)`.
# Exclude ';' so a multi-citation like "(TUNÇ, 2022; Wu, 2025)" is left intact
# (not greedily matched and stripped when only the LAST pair fails to validate).
_CITE_SHAPED = re.compile(r"\(\s*([^()';]*?[^\W\d_][^()';]*?),\s*((?:19|20)\d{2}[a-z]?)\s*\)")


def _cite_surname_year(author_text: str, year: str) -> tuple[str, str]:
    """First alphabetic surname token (Unicode-aware) + 4-digit year, for
    tolerant matching against the reference pool. Handles `&` / `và cộng sự`
    joined authors and diacritic names (Đặng, Nguyễn)."""
    toks = re.findall(r"[^\W\d_]+", author_text, flags=re.UNICODE)
    surname = toks[0].casefold() if toks else ""
    y = re.match(r"(\d{4})", year)
    return surname, (y.group(1) if y else year)


def _pool_surname_years(references: list[dict]) -> set[tuple[str, str]]:
    """Pool keyed by (first-author surname, 4-digit year) for tolerant lookup."""
    out: set[tuple[str, str]] = set()
    for r in references:
        toks = re.findall(r"[^\W\d_]+", _ref_author_label(r), flags=re.UNICODE)
        surname = toks[0].casefold() if toks else ""
        year = str(r.get("year", "")).strip()
        ym = re.match(r"(\d{4})", year)
        if surname and ym:
            out.add((surname, ym.group(1)))
    return out


def _strip_uncited_citations(prose: str, references: list[dict]) -> str:
    """Remove inline citations not backed by the reference pool, so a
    hallucinated "(Anon, 2011)" never reaches the rendered document.

    When the pool is EMPTY (e.g. Crossref returned nothing), every
    citation-shaped parenthetical is stripped — there is nothing to back any of
    them. When the pool is non-empty, a citation is kept only when its
    (surname, year) matches a pool entry (tolerant of `&`/`và cộng sự` joins and
    diacritics). We delete the parenthetical plus one leading space; real,
    pool-backed citations are untouched.
    """
    pool = _pool_surname_years(references)

    def _repl(m: "re.Match") -> str:
        surname, year = _cite_surname_year(m.group(1), m.group(2))
        return m.group(0) if (pool and (surname, year) in pool) else ""

    # Consume an optional leading space so "research (Anon, 2011)." → "research."
    cleaned = re.sub(r"\s?" + _CITE_SHAPED.pattern, _repl, prose)
    # Collapse any double spaces / space-before-punctuation the removal created.
    cleaned = re.sub(r"  +", " ", cleaned)
    cleaned = re.sub(r"\s+([.,;:])", r"\1", cleaned)
    return cleaned


# Appended to every chapter prompt. The composed prose is rendered to DOCX/PDF
# via pandoc, which needs well-formed markdown — the LLM otherwise mushes list
# items onto one line and emits broken tables.
# Appended to every chapter prompt so the academic-style + table-interpretation
# rules apply uniformly across all 6 chapters from one place, rather than being
# duplicated (and drifting) across each prompts/m5/<chapter>.md file.
_MARKDOWN_FORMAT_RULES = """

---
OUTPUT FORMATTING (strict — the text is rendered to a Word document via Markdown):
- Write academic prose in full paragraphs. Separate paragraphs with a blank line.
- For any list, put EACH item on its OWN line starting with "- ", and leave a
  blank line BEFORE the list. NEVER put multiple bullet items on one line.
- Prefer prose over tables for NARRATIVE content. Do NOT wrap ordinary
  discussion in tables.
- BUT statistical / measurement results ARE tabular data and MUST be presented
  as Markdown tables, not buried in prose: reliability & validity (Cronbach's
  alpha, composite reliability, AVE, item loadings), correlation/HTMT matrices,
  descriptives, and path/regression coefficients. Put each row on its own line
  with correct "| col | col |" pipes and a "| --- | --- |" separator row, then
  interpret the table in prose AFTER it.
- ONLY build a table when the ACTUAL numbers are present in the provided
  analysis. NEVER output a table containing placeholder cells ("…", "...",
  "TBD", "N/A", blanks) or invented numbers. If the specific values for a table
  (e.g. the full HTMT matrix) are NOT in the data, describe that finding in
  prose only — do not emit a table shell of placeholders.
- Use "## Heading" on its own line for sub-sections.
- Do not output the chapter title as an H1 — it is added automatically.
- Never write meta-commentary about the writing process, missing inputs, or
  assumptions you made to fill gaps (e.g. "the author assumed", "due to limited
  information", "giả định", "thiếu thông tin"). Write as a finished scholarly
  document — if a fact is not in the inputs, omit it, do not narrate its absence.

ACADEMIC STYLE (applies to every chapter):
- Impersonal voice only — never "I", "we", "the author thinks". Attribute claims
  to evidence: "the results indicate...", "the analysis shows...".
- No unsupported certainties — replace "certainly / will definitely / proves"
  with calibrated phrasing ("the results suggest", "the findings indicate").
- No absolutes about the sample — "all students" becomes "most respondents in
  the sample".
- No emotive or colloquial words ("sadly", "amazing", "a lot of") — stay neutral
  and precise.
- Split any sentence over ~40 words into shorter, single-idea sentences.
- Vary vocabulary — don't repeat the same verb (rotate study/examine/analyse/
  assess; affect/influence/shape; show/indicate/demonstrate).
- Expand each abbreviation on first use, then use the short form.

CITATIONS (strict — invalid citations are removed automatically):
- Cite ONLY sources from the provided reference list. NEVER invent an author or
  a source that is not on that list.
- Always cite in PARENTHETICAL form at the END of the sentence/clause:
  "… mối quan hệ này (Author, Year)." Use the EXACT (Author, Year) string shown
  in the list.
- NEVER write a citation as the sentence subject / narrative form
  ("Author (Year) đã chỉ ra…", "Author (Year) showed…"). Rephrase so the
  citation sits in parentheses at the end.
- If no provided source supports a claim, state the claim without a citation —
  do not attribute it to an invented source.

GOLDEN RULE FOR TABLES: every statistical table MUST be followed by an
interpreting paragraph. Pattern: [overview sentence] -> [caption] -> [table] ->
[source] -> [detailed interpretation of the key values] -> [closing comment].
Never leave a table standing alone with no prose.

TABLE CAPTION & SOURCE (match a standard thesis exactly):
- Immediately BEFORE each statistical table, put a bold caption on its OWN line.
  Vietnamese: `**Bảng <chương>.<số>: <tên bảng>**` (e.g. `**Bảng 4.1: Thống kê
  mô tả mẫu**`). English: `**Table <số>: <name>**`.
- Immediately AFTER each table, put an italic source line on its OWN line.
  Vietnamese: `*Nguồn: Kết quả phân tích từ SmartPLS/SPSS, tác giả tổng hợp.*`
  English: `*Source: Author's analysis.*`.
- Number tables sequentially per chapter (Bảng 4.1, 4.2, 4.3 …).
"""


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


# --- Per-module "M5-mini" composer (for single/multi-module exports) ---------
# A real LLM write-up of ONE module's slice as academic prose — used by the
# Export-to-Word actions (scope=M1..M4). Distinct from `_compose_section_via_
# engine`, which targets the auto-mode full-thesis pipeline and falls back to
# placeholder stubs when the engine's private composers aren't available.
_MODULE_COMPOSE_SKIP = {"confirmed_at", "needs_review", "module_status", "focus"}
_MODULE_COMPOSE_GUIDE = {
    "M1": "Write the **Introduction & Research Focus** section: 2-3 short paragraphs "
          "establishing the background and problem, then state the research title and "
          "present the research questions in prose (you may list the RQs).",
    "M2": "Write the **Literature Review** section: synthesize the provided sources into "
          "flowing paragraphs (what is known, debates, and the research gaps). Use inline "
          "citations in (Author, Year) form. CITE ONLY the sources provided below — never "
          "invent a source. Do NOT include a reference list (it is appended automatically).",
    "M3": "Write the **Research Design & Methodology** section in prose: the conceptual "
          "model and variables, the hypotheses, the methodology (paradigm, design, "
          "sampling, planned analysis), and a short description of the instrument. Cite "
          "(Author, Year) where a construct/scale comes from a source.",
    "M4": "Write the **Data Analysis** section: describe the analysis plan and report only "
          "results that are present in the data below. Never invent statistics.",
}


def compose_module_prose(module: str, slice_: dict, title: str = "Untitled thesis") -> str:
    """Compose ONE module's slice as a standalone academic write-up (markdown body,
    heading stripped — the caller supplies the section title). Real LLM compose;
    returns "" on unknown module or failure so the caller can flag needs_data."""
    guide = _MODULE_COMPOSE_GUIDE.get((module or "").upper())
    if not guide:
        return ""
    payload = {
        k: v for k, v in (slice_ or {}).items()
        if k not in _MODULE_COMPOSE_SKIP and not str(k).startswith("_")
    }
    prompt = (
        "You are writing one section of a Master's thesis for a student to submit "
        "to their professor. Formal academic register, concise (about 300-600 "
        "words). Markdown only: '## ' for the section heading, '### ' for "
        "sub-headings, '- ' for bullets; no tables.\n\n"
        f"## Thesis: {title}\n## Section: {module}\n\n"
        f"Instructions: {guide}\n\n"
        f"Module data (JSON):\n{json.dumps(payload, ensure_ascii=False, default=str)[:9000]}\n\n"
        "Write the section now (markdown):"
    )
    try:
        msg = _get_llm().invoke(prompt)
        c = getattr(msg, "content", "")
        text = (
            "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in c)
            if isinstance(c, list) else str(c)
        )
        return _strip_leading_chapter_heading(text.strip())
    except Exception:
        logger.exception("compose_module_prose failed for %s", module)
        return ""


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
    _export_docx_via_engine(sections, str(local_path), populate_toc=True)
    s3_key, size_bytes = _upload_to_s3(str(local_path), project_id, "docx", filename)
    return {"s3_key": s3_key, "size_bytes": size_bytes}


# Canonical 6-chapter order + display titles, shared by every caller that
# turns an m5_writing slice into exporter sections (the auto-export hook in
# api/app/agent_state.py, the /m5/export route, and the agent's export tool).
# One source of truth so the three paths can't drift.
M5_CHAPTER_ORDER = ["intro", "lit_review", "methodology", "results", "discussion", "conclusion"]
M5_CHAPTER_TITLES = {
    "intro":       "Chapter 1 — Introduction",
    "lit_review":  "Chapter 2 — Literature Review",
    "methodology": "Chapter 3 — Methodology",
    "results":     "Chapter 4 — Results",
    "discussion":  "Chapter 5 — Discussion",
    "conclusion":  "Chapter 6 — Conclusion",
}
# Vietnamese chapter titles — the document language must be consistent, so the
# headings match the (Vietnamese) chapter prose instead of staying English.
M5_CHAPTER_TITLES_VI = {
    "intro":       "Chương 1 — Giới thiệu",
    "lit_review":  "Chương 2 — Tổng quan tài liệu",
    "methodology": "Chương 3 — Phương pháp nghiên cứu",
    "results":     "Chương 4 — Kết quả",
    "discussion":  "Chương 5 — Thảo luận",
    "conclusion":  "Chương 6 — Kết luận",
}
_REFERENCES_TITLE = {"vi": "Tài liệu tham khảo", "en": "References"}


def _chapter_titles(language: str) -> dict:
    """Chapter-title map matching the prose language (vi → Vietnamese)."""
    return M5_CHAPTER_TITLES_VI if str(language).lower().startswith("vi") else M5_CHAPTER_TITLES


def _references_title(language: str) -> str:
    return _REFERENCES_TITLE["vi"] if str(language).lower().startswith("vi") else _REFERENCES_TITLE["en"]


def chapters_from_final_sections(final_sections: list[dict]) -> dict:
    """Map the conversational `final_sections` list onto the editor's canonical
    chapter dict: ``{intro: {name, prose}, lit_review: {...}, …}``.

    The editor (OutlineRail) only knows the six canonical chapter names, but the
    conversational / export path stores M5 as a flat `final_sections` list. We
    resolve each section's canonical name from its explicit `chapter_name`
    (compose path) first, then fall back to a title reverse-lookup across the EN
    and VI title maps (agent path, which carries only `title`). Sections that map
    to no canonical chapter — e.g. References — are dropped: they aren't editable
    chapters. Returns {} when nothing maps, so callers can fall through.
    """
    # Index BOTH language maps by their titles. (A dict merge would collapse
    # them — they share the canonical-name keys, so the second map's titles
    # would win and the first language's titles would be lost.)
    title_to_name: dict[str, str] = {}
    for mapping in (M5_CHAPTER_TITLES, M5_CHAPTER_TITLES_VI):
        for name, title in mapping.items():
            title_to_name[title.strip().lower()] = name
    out: dict = {}
    for sec in final_sections or []:
        if not isinstance(sec, dict):
            continue
        name = sec.get("chapter_name")
        if name not in M5_CHAPTER_ORDER:
            title = (sec.get("title") or sec.get("name") or "").strip().lower()
            name = title_to_name.get(title)
        if name not in M5_CHAPTER_ORDER:
            continue
        prose = (sec.get("prose") or sec.get("body") or sec.get("content") or "").strip()
        if not prose:
            continue
        out[name] = {"name": name, "prose": prose}
    return out


def sections_from_m5_slice(m5_slice: dict) -> list[dict]:
    """Build exporter sections [{title, prose}] from an m5_writing slice.

    Tolerates both shapes the writers produce:
    - `chapters: {intro: {prose: "…"}, …}` — the canonical auto-mode shape.
    - `final_sections: [{title, body|prose}, …]` — the conversational agent
      shape (the M5 skill's DocumentSection list).
    Returns [] when neither carries usable prose, so callers can short-circuit
    instead of exporting an empty document.
    """
    chapters = (m5_slice or {}).get("chapters") or {}
    if chapters:
        out = []
        for name in M5_CHAPTER_ORDER:
            ch = chapters.get(name)
            if not ch:
                continue
            prose = (ch.get("prose") or ch.get("body") or "").strip() if isinstance(ch, dict) else str(ch)
            if prose:
                out.append({"title": M5_CHAPTER_TITLES[name], "prose": prose})
        if out:
            return out
    final_sections = (m5_slice or {}).get("final_sections") or []
    out = []
    for sec in final_sections:
        if not isinstance(sec, dict):
            continue
        title = (sec.get("title") or sec.get("name") or "").strip()
        prose = (sec.get("prose") or sec.get("body") or sec.get("content") or "").strip()
        if prose:
            out.append({"title": title or "Section", "prose": prose})
    return out


# Markers that signal a chapter could NOT be properly composed. These must
# never reach the exported document (the "[Composition failed]" / "[Auto-
# generated for …]" weirdness the user saw). When detected we treat the
# chapter as missing and ask the user to fill the gap instead of shipping it.
_STUB_MARKERS = ("[Composition failed", "[Auto-generated for", "[Composition failed — please retry]")


def _is_stub_prose(prose: str) -> bool:
    """True when prose is a placeholder/failure stub, not real chapter content."""
    if not prose or not prose.strip():
        return True
    if any(marker in prose for marker in _STUB_MARKERS):
        return True
    # A real chapter is at least a few sentences; anything tiny is a stub.
    return len(prose.strip()) < 120


# Minimal data each chapter needs to be writable. Used to decide whether to
# ask the user to fill gaps BEFORE spending ~1 min composing — and to tell
# them exactly what's missing in plain language.
def assess_export_readiness(context_store: dict, chapters: list[str] | None = None) -> list[str]:
    """Return human-readable missing-data items (empty = ready).

    When `chapters` is given, only report items whose owning chapter is in the
    requested set, so a subset compose (partner "analysis_report" = intro/
    results/discussion) isn't blocked by data a skipped chapter would have used.
    Title/RQs and literature are needed by every academic chapter (owner ANY);
    methodology + results are chapter-specific. This is the ONE gate for full
    AND subset composes — it replaces partner's second _has_sufficient_m4_data
    store-gate.
    """
    m1 = context_store.get("m1_topic") or {}
    m2 = context_store.get("m2_literature") or {}
    m3 = context_store.get("m3_design") or {}
    m4 = context_store.get("m4_analysis") or {}

    ANY = None  # relevant to every chapter
    checks = [
        (ANY, not str(m1.get("research_title") or "").strip(), "M1 — research title"),
        (ANY, not (m1.get("research_questions") or []), "M1 — research questions"),
        (ANY, not (m2.get("literature_sources") or []),
         "M2 — literature sources (no references to cite)"),
        ("methodology", not (m3.get("methodology") or m3.get("conceptual_model")),
         "M3 — methodology / conceptual model"),
        ("results", not (m4.get("analysis_results") or m4.get("qual_themes") or m4.get("qual_codes")),
         "M4 — analysis results (the Results chapter has no data)"),
    ]
    req = set(chapters) if chapters is not None else None
    missing: list[str] = []
    for owner, is_missing, label in checks:
        if not is_missing:
            continue
        if req is None or owner is ANY or owner in req:
            missing.append(label)
    return missing


def _references_section_body(references: list[dict]) -> str:
    """Build the References list body (no heading) as markdown.

    Each entry ends with a markdown link to the source's DOI or URL — pandoc
    renders `[text](url)` as a real clickable hyperlink in the DOCX/PDF, which
    is what makes the bibliography clickable. Sorted by author then year.
    """
    if not references:
        return ""

    def _key(r: dict) -> tuple:
        return (_ref_author_label(r).lower(), str(r.get("year", "")))

    entries: list[str] = []
    for r in sorted(references, key=_key):
        label = _ref_author_label(r)
        year = r.get("year", "n.d.")
        title = (r.get("title") or "").strip()
        venue = (r.get("venue") or "").strip()
        doi = (r.get("doi") or "").strip()
        url = (r.get("url") or "").strip()
        link = f"https://doi.org/{doi}" if doi else url

        entry = f"{label} ({year}). {title}.".rstrip(".") + "."
        if venue:
            entry += f" *{venue}*."
        if link:
            entry += f" [{link}]({link})"
        entries.append(entry)
    # Blank line between entries so pandoc treats each as its own paragraph.
    return "\n\n".join(entries)


def compose_all_sections(context_store: dict) -> list[dict]:
    """Compose all 6 chapters from a nested context_store → [{title, prose}].

    `context_store` is the nested module shape ({m1_topic, m2_literature,
    m3_design, m4_analysis}). Each chapter is written by `compose_chapter`
    (real LLM composition against the orchestrator/prompts/m5/<name>.md
    templates), grounded in the project state. On a per-chapter LLM failure
    we drop in a minimal fallback so one bad chapter can't abort the whole
    export — but the happy path is full prose, not stubs.

    Used by the export tool to generate a draft on demand when the user asks
    for the file but nothing was written yet.
    """
    m1 = context_store.get("m1_topic") or {}
    m2 = context_store.get("m2_literature") or {}
    m3 = context_store.get("m3_design") or {}
    m4 = context_store.get("m4_analysis") or {}

    methodology = m3.get("methodology") if isinstance(m3.get("methodology"), dict) else {}
    paradigm = (methodology or {}).get("paradigm", "") or ""
    references = m2.get("literature_sources") or []
    language = m1.get("language") or "vi"
    citation_style = "apa7"

    # Merge every module's keys into one flat slice for the prompt templates.
    # compose_chapter JSON-encodes nested values and fills missing keys with
    # "", so an over-broad merge is safe; we just make sure the canonical
    # `results` key points at M4's analysis output.
    context_slice: dict = {**m1, **m2, **m3, **m4}
    context_slice.setdefault("results", m4.get("analysis_results"))

    titles = _chapter_titles(language)
    out: list[dict] = []
    for name in M5_CHAPTER_ORDER:
        try:
            draft = compose_chapter.invoke({
                "chapter_name": name,
                "paradigm": paradigm,
                "context_slice": context_slice,
                "references": references,
                "citation_style": citation_style,
                "language": language,
            })
            prose = (draft or {}).get("prose") or ""
        except Exception:
            logger.exception("compose_all_sections: compose_chapter failed for %s", name)
            prose = ""
        if not prose.strip():
            prose = _fallback_section(name, context_store)
        out.append({"title": titles[name], "prose": prose})

    # Append a References section built from the M2 sources, with clickable
    # DOI/URL links. Without this the document has inline "(Author, Year)"
    # citations but no bibliography to back them.
    refs_body = _references_section_body(references)
    if refs_body:
        out.append({"title": _references_title(language), "prose": refs_body})
    return out


def _assign_citation_keys(references: list[dict]) -> tuple[list[dict], dict]:
    """Build (CSL-JSON items, {(author_label, year): citekey}) from references.

    Citekeys are surname+year (deduped with a/b/c suffixes), the form pandoc
    citeproc uses. The label→key map lets us rewrite the LLM's "(Author, Year)"
    inline citations into pandoc `[@key]` syntax that becomes clickable.
    """
    csl_items: list[dict] = []
    ly_to_key: dict[tuple, str] = {}
    used: set[str] = set()
    for r in references:
        label = _ref_author_label(r)
        surname = re.sub(r"[^a-z0-9]", "", label.replace(" et al.", "").lower()) or "ref"
        year = str(r.get("year", "")).strip()
        base = f"{surname}{year or 'nd'}"
        key, suffix = base, ord("a")
        while key in used:
            key = f"{base}{chr(suffix)}"
            suffix += 1
        used.add(key)
        ly_to_key.setdefault((label, year), key)

        authors = r.get("authors") or []
        csl_authors = [{"family": str(a)} for a in authors] if authors else [{"family": label}]
        item: dict = {
            "id": key,
            "type": "article-journal",
            "title": r.get("title") or "Untitled",
            "author": csl_authors,
        }
        if year.isdigit():
            item["issued"] = {"date-parts": [[int(year)]]}
        if r.get("venue"):
            item["container-title"] = r["venue"]
        if r.get("doi"):
            item["DOI"] = r["doi"]
        if r.get("url"):
            item["URL"] = r["url"]
        csl_items.append(item)
    return csl_items, ly_to_key


def _convert_inline_citations(prose: str, ly_to_key: dict) -> str:
    """Rewrite "(Author, Year; Author2, Year2)" → pandoc "[@key1; @key2]".

    Accepts both "Author, Year" and "Author Year" (the LLM frequently drops the
    comma — "(Hilman 2024; Nocker 2024)" — and without this the citation stayed
    plain text and never became a clickable link in the DOCX/PDF).

    Only rewrites a parenthetical when EVERY part maps to a known reference;
    otherwise the parenthetical is left exactly as written (so "(see Figure 1)"
    or an unknown citation is never mangled).
    """
    if not prose or not ly_to_key:
        return prose

    def _repl(m: "re.Match") -> str:
        parts = [p.strip() for p in m.group(1).split(";")]
        keys: list[str] = []
        for p in parts:
            # Author/year separator may be a comma+space OR just a space; an
            # optional trailing letter handles disambiguated years like "2024a".
            cm = re.match(r"^(.*?)[,\s]\s*(\d{4})[a-z]?$", p)
            if not cm:
                return m.group(0)
            key = ly_to_key.get((cm.group(1).strip(), cm.group(2)))
            if not key:
                return m.group(0)
            keys.append(f"@{key}")
        return "[" + "; ".join(keys) + "]"

    return re.sub(r"\(([^()]*\d{4}[^()]*)\)", _repl, prose)


def _populate_docx_toc(docx_path: str) -> None:
    """Replace the DOCX's auto-updating Word TOC field with STATIC entries.

    Pandoc inserts a `TOC \\o "1-3" \\h \\z \\u` field code that Word (and only
    Word) fills in on "Update Field". LibreOffice's headless PDF converter
    doesn't run field codes → the PDF shows only the "Table of Contents" title
    with nothing under it. So walk the doc, collect every Heading 1/2/3, and
    write those in place of the empty field placeholder. Best-effort — silent
    return on failure leaves the (still-working, TOC-less) PDF path intact.
    """
    try:
        from docx import Document
        from docx.oxml.ns import qn
    except Exception:
        return
    try:
        doc = Document(docx_path)
    except Exception:
        logger.warning("populate-toc: could not open docx", exc_info=True)
        return

    # Collect Heading 1..3 entries in document order.
    entries: list[tuple[int, str]] = []
    for p in doc.paragraphs:
        style = (p.style.name if p.style else "") or ""
        text = p.text.strip()
        if not text:
            continue
        if style == "Heading 1":
            entries.append((1, text))
        elif style == "Heading 2":
            entries.append((2, text))
        elif style == "Heading 3":
            entries.append((3, text))
    if not entries:
        return

    # Pandoc wraps the whole TOC in a `w:sdt` (structured document tag) block:
    #   <w:sdt><w:sdtPr><w:docPartObj><w:docPartGallery val="Table of Contents"/>
    # …</w:sdtPr><w:sdtContent>…w:p with TOC field…</w:sdtContent></w:sdt>
    # Find that sdt so we can gut its content and refill with static entries
    # (while keeping the "Table of Contents" title paragraph LibreOffice already
    # renders correctly).
    body = doc.element.body
    from docx.oxml import OxmlElement

    def _find_toc_sdt():
        for sdt in body.iter(qn("w:sdt")):
            for gallery in sdt.iter(qn("w:docPartGallery")):
                if gallery.get(qn("w:val")) == "Table of Contents":
                    return sdt
        return None

    toc_sdt = _find_toc_sdt()
    if toc_sdt is not None:
        # Inside sdtContent, keep the FIRST paragraph (the "Table of Contents"
        # title, styled TOCHeading) and drop everything else (the field-code
        # placeholders + any pandoc hint paragraphs).
        content = toc_sdt.find(qn("w:sdtContent"))
        if content is None:
            return
        children = list(content)
        # First para = title. Remove all children EXCEPT that first paragraph.
        title_el = children[0] if children else None
        for child in children[1:]:
            content.remove(child)
    else:
        # Fallback: no sdt wrapper — look for a bare TOC field paragraph.
        target = None
        for p_el in body.iterfind(qn("w:p")):
            instr = p_el.find(f".//{qn('w:instrText')}")
            if instr is not None and instr.text and "TOC " in instr.text:
                target = p_el
                break
        if target is None:
            return
        target.getparent().remove(target)
        content = None
        title_el = None

    def _mk_para(level: int, text: str):
        p = OxmlElement("w:p")
        pPr = OxmlElement("w:pPr")
        # A tiny left indent per level so H2/H3 read hierarchical.
        if level > 1:
            ind = OxmlElement("w:ind")
            ind.set(qn("w:left"), str(360 * (level - 1)))  # 360 dxa ≈ 0.25"
            pPr.append(ind)
        p.append(pPr)
        r = OxmlElement("w:r"); rPr = OxmlElement("w:rPr")
        if level == 1:
            b = OxmlElement("w:b"); rPr.append(b)
        r.append(rPr)
        t = OxmlElement("w:t"); t.text = text; t.set(qn("xml:space"), "preserve")
        r.append(t); p.append(r)
        return p

    if content is not None:
        # Append fresh entries inside w:sdtContent (below the title paragraph
        # that survived the pruning above).
        for level, text in entries:
            content.append(_mk_para(level, text))
    else:
        # Insert at the same body index the deleted TOC field paragraph held.
        # (This branch runs only when there's no w:sdt wrapper.)
        for level, text in entries:
            body.append(_mk_para(level, text))

    try:
        doc.save(docx_path)
    except Exception:
        logger.warning("populate-toc: could not save docx", exc_info=True)


def _docx_to_pdf(docx_path: str, pdf_path: str) -> bool:
    """Convert a DOCX to PDF via LibreOffice headless so the PDF inherits the
    citeproc-rendered clickable citations from the DOCX (rather than
    re-rendering from markdown, which LibreOffice can't citeproc).

    Populates the pandoc-inserted TOC field with static entries first —
    LibreOffice's field engine doesn't run Word's TOC codes, so without this
    the PDF's TOC is empty.
    """
    import shutil
    import subprocess

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return False
    # Fill the TOC in place so both the DOCX and the resulting PDF have entries.
    _populate_docx_toc(docx_path)
    outdir = str(Path(pdf_path).parent)
    subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", outdir, docx_path],
        capture_output=True, timeout=180, check=True,
    )
    produced = Path(outdir) / (Path(docx_path).stem + ".pdf")
    if produced.exists() and str(produced) != pdf_path:
        produced.replace(pdf_path)
    return Path(pdf_path).exists()


def _artifact_dict(kind: str, pid: str, s3_key: str, size_bytes: int) -> dict:
    return {
        "kind": kind,
        "s3_key": s3_key,
        "size_bytes": size_bytes,
        "download_url": f"/api/v1/projects/{pid}/exports/{s3_key.split('/')[-1]}",
        "uri": "",
    }


def run_export(sections: list[dict], project_id: str,
               references: list[dict] | None = None,
               language: str = "en") -> list[dict]:
    """Render docx + pdf, upload to S3, return ContextPanel-ready artifacts.

    The single export entrypoint shared by the auto-export hook, the
    /m5/export route, and the agent's export_docx tool.

    When `references` is provided, renders via the citeproc path so inline
    "(Author, Year)" citations become clickable links to the auto-generated
    References section. `language` keeps the generated References heading
    consistent with the (possibly Vietnamese) document. Falls back to the plain
    render on any citeproc failure so export never breaks.
    """
    pid = str(project_id)
    if references:
        try:
            return _run_export_citeproc(sections, pid, references, language)
        except Exception:
            logger.exception("citeproc export failed — falling back to plain render")

    docx_res = export_docx.invoke({"sections": sections, "project_id": pid})
    pdf_res = compile_pdf.invoke({"sections": sections, "project_id": pid})
    return [
        _artifact_dict("docx", pid, docx_res["s3_key"], docx_res["size_bytes"]),
        _artifact_dict("pdf", pid, pdf_res["s3_key"], pdf_res["size_bytes"]),
    ]


# All language variants of the References heading — used to strip a manually
# built bibliography before citeproc generates its own.
_ALL_REFERENCE_TITLES = {t.lower() for t in _REFERENCES_TITLE.values()}


# Standard Word hyperlink blue. Applied inline so links look like hyperlinks
# even if the reference template's "Hyperlink" character style is missing/plain.
_HYPERLINK_COLOR = "0563C1"


def _style_link_runs(docx_path: str) -> None:
    """Give every <w:hyperlink> run a blue color + single underline.

    pandoc's `link-citations` wraps in-text "(Author, Year)" citations in real
    hyperlinks to the bibliography, but whether they LOOK like links depends on
    the reference doc's Hyperlink style. We set the color/underline inline so the
    look is guaranteed (citations, the bibliography's DOI/URL links, the TOC).
    No-ops silently if python-docx isn't available or the file isn't a real docx.
    """
    try:
        from docx import Document
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
    except Exception:  # noqa: BLE001
        return
    try:
        doc = Document(docx_path)
    except Exception:  # noqa: BLE001 — placeholder / non-docx; skip
        return

    changed = False
    for hl in doc.element.body.iter(qn("w:hyperlink")):
        for run in hl.findall(qn("w:r")):
            rpr = run.find(qn("w:rPr"))
            if rpr is None:
                rpr = OxmlElement("w:rPr")
                run.insert(0, rpr)
            if rpr.find(qn("w:color")) is None:
                c = OxmlElement("w:color")
                c.set(qn("w:val"), _HYPERLINK_COLOR)
                rpr.append(c)
            if rpr.find(qn("w:u")) is None:
                u = OxmlElement("w:u")
                u.set(qn("w:val"), "single")
                rpr.append(u)
            changed = True
    if changed:
        doc.save(docx_path)


def _run_export_citeproc(sections: list[dict], pid: str, references: list[dict],
                         language: str = "en") -> list[dict]:
    """Render DOCX with pandoc citeproc (clickable citations + auto bibliography),
    then convert that DOCX to PDF via LibreOffice so both formats match."""
    csl_items, ly_to_key = _assign_citation_keys(references)

    # Drop any manually-built References section (any language) — citeproc
    # generates its own — and rewrite inline citations to [@key] in each chapter.
    body: list[dict] = []
    for s in sections:
        if (s.get("title") or "").strip().lower() in _ALL_REFERENCE_TITLES:
            continue
        body.append({
            "title": s.get("title", ""),
            "prose": _convert_inline_citations(s.get("prose", ""), ly_to_key),
        })
    # Trailing heading (in the doc's language) tells pandoc where to place the
    # generated bibliography.
    body.append({"title": _references_title(language), "prose": ""})

    bib_path = _scratch_dir() / f"refs-{uuid4().hex[:8]}.json"
    bib_path.write_text(json.dumps(csl_items, ensure_ascii=False), encoding="utf-8")

    docx_name = f"thesis-{uuid4().hex[:8]}.docx"
    docx_local = _scratch_dir() / docx_name
    # nocite:@* → citeproc prints the FULL bibliography (never an empty heading,
    # regardless of which inline [@key]s matched). populate_toc → filled TOC.
    # toc-title makes the TOC heading match the document language.
    toc_title = "Mục lục" if str(language).lower().startswith("vi") else "Contents"
    frontmatter = f'---\nnocite: |\n  @*\ntoc-title: "{toc_title}"\n---'
    _export_docx_via_engine(body, str(docx_local), bibliography=bib_path,
                            frontmatter=frontmatter, populate_toc=True)
    # Force the hyperlink look (blue + underline) on every link run, so in-text
    # citation links read as hyperlinks regardless of the reference template's
    # Hyperlink style. Done before PDF conversion so the PDF inherits it.
    _style_link_runs(str(docx_local))

    pdf_name = f"thesis-{uuid4().hex[:8]}.pdf"
    pdf_local = _scratch_dir() / pdf_name
    pdf_ok = _docx_to_pdf(str(docx_local), str(pdf_local))

    docx_key, docx_size = _upload_to_s3(str(docx_local), pid, "docx", docx_name)
    out = [_artifact_dict("docx", pid, docx_key, docx_size)]
    if pdf_ok:
        pdf_key, pdf_size = _upload_to_s3(str(pdf_local), pid, "pdf", pdf_name)
        out.append(_artifact_dict("pdf", pid, pdf_key, pdf_size))
    else:
        # No LibreOffice → weasyprint can't resolve `[@key]`. Render the ORIGINAL
        # sections (plain "(Author, Year)" text + the deterministic References
        # section) so the PDF never ships raw `[@key]` markers or an empty
        # bibliography — instead of the citeproc-rewritten `body`.
        pdf_res = compile_pdf.invoke({"sections": sections, "project_id": pid})
        out.append(_artifact_dict("pdf", pid, pdf_res["s3_key"], pdf_res["size_bytes"]))
    bib_path.unlink(missing_ok=True)
    return out


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
    prompt_template = (_PROMPT_DIR / f"{chapter_name}.md").read_text(encoding="utf-8")
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
        prompt = _fill_template(prompt_template, safe_kwargs) + _MARKDOWN_FORMAT_RULES
        prose = text_of(_get_llm().invoke(prompt)).strip()
    except Exception as e:
        logger.warning("compose_chapter LLM call failed for %s: %s", chapter_name, e)
        prose = f"# {chapter_name.title()}\n\n[Composition failed — please retry]"

    # Strip any citation the LLM invented that isn't in the reference pool, so
    # hallucinated "(Anon, 2011)" never reaches the rendered document. The
    # warning stays as RETURNED metadata (uncited_warnings) for QA/logging — it
    # must NOT be appended into the prose, which gets rendered verbatim.
    cited_in_pool, uncited = validate_citations(prose, references)
    # ALWAYS run the pool-based stripper (not only when the narrow validator
    # flagged something): it removes every parenthetical citation not backed by
    # the reference pool — the authoritative cleaner for hallucinated cites.
    prose = _strip_uncited_citations(prose, references)
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
    prompt_template = (_PROMPT_DIR / f"{chapter_name}.md").read_text(encoding="utf-8")
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
        base_prompt = _fill_template(prompt_template, safe_kwargs)
        rewrite_prompt = (
            f"{base_prompt}\n\n"
            f"## User rewrite instruction\n{instruction}\n\n"
            f"## Current chapter prose (rewrite based on the instruction; preserve good content):\n"
            f"{current_prose}\n\n"
            f"Output ONLY the rewritten chapter prose."
        )
        prose = text_of(_get_llm().invoke(rewrite_prompt)).strip()
    except Exception as e:
        # Decision: on any LLM failure, return the original prose unchanged so
        # the user never loses work they've already reviewed or produced.
        logger.warning("rewrite_chapter LLM call failed for %s: %s", chapter_name, e)
        prose = current_prose  # unchanged on failure

    # Strip any citation the LLM invented that isn't in the reference pool, so
    # hallucinated "(Anon, 2011)" never reaches the rendered document. The
    # warning stays as RETURNED metadata (uncited_warnings) for QA/logging — it
    # must NOT be appended into the prose, which gets rendered verbatim.
    cited_in_pool, uncited = validate_citations(prose, references)
    # ALWAYS run the pool-based stripper (not only when the narrow validator
    # flagged something): it removes every parenthetical citation not backed by
    # the reference pool — the authoritative cleaner for hallucinated cites.
    prose = _strip_uncited_citations(prose, references)
    return {
        "name": chapter_name,
        "prose": prose,
        "citations_used": cited_in_pool,
        "uncited_warnings": uncited,
    }

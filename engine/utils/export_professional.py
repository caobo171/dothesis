#!/usr/bin/env python3
"""
ABOUTME: Production-grade academic document export utility with strategy pattern
ABOUTME: Supports multiple PDF engines (LibreOffice, Pandoc, WeasyPrint) with auto-fallback
"""

import sys
import argparse
from pathlib import Path
from typing import Optional, Literal

# Use centralized logging system
from utils.logging_config import get_logger
logger = get_logger(__name__)

# Add project root to path for subprocess/different CWD execution
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from utils.pdf_engines import (
    PDFGenerationOptions,
    PDFEngineFactory,
    get_available_engines,
    get_recommended_engine
)


def extract_metadata_from_yaml(md_file: Path) -> dict:
    """
    Extract metadata from YAML frontmatter in markdown file.

    Normalizes German/Spanish/French field names to English.

    Args:
        md_file: Path to markdown file with YAML frontmatter

    Returns:
        dict: Normalized metadata (title, author, date, institution, department, degree)
    """
    import yaml

    try:
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Extract YAML frontmatter
        if not content.strip().startswith('---'):
            return {}

        parts = content.split('---', 2)
        if len(parts) < 3:
            return {}

        yaml_content = parts[1]
        metadata = yaml.safe_load(yaml_content) or {}

        # Normalize localized field names to English
        field_map = {
            # German
            'titel': 'title',
            'untertitel': 'subtitle',
            'autor': 'author',
            'datum': 'date',
            # Spanish
            'título': 'title',
            'subtítulo': 'subtitle',
            'autor': 'author',
            'fecha': 'date',
            # French
            'titre': 'title',
            'sous-titre': 'subtitle',
            'auteur': 'author',
            'date': 'date',
            # English (pass-through)
            'title': 'title',
            'subtitle': 'subtitle',
            'author': 'author',
            'date': 'date',
            'institution': 'institution',
            'department': 'department',
            'degree': 'degree',
            'advisor': 'advisor',
            'student_id': 'student_id',
            'project_type': 'project_type',
            'system_credit': 'system_credit',
            'generated_by': 'system_credit',  # Map generated_by to system_credit
        }

        normalized = {}
        for key, value in metadata.items():
            normalized_key = field_map.get(key.lower(), key.lower())
            normalized[normalized_key] = value

        return normalized

    except Exception as e:
        logger.warning(f"Could not extract YAML metadata: {e}")
        return {}


def export_pdf(
    md_file: Path,
    output_pdf: Path,
    engine: Literal['auto', 'libreoffice', 'pandoc', 'weasyprint'] = 'auto',
    options: Optional[PDFGenerationOptions] = None
) -> bool:
    """
    Export markdown to PDF using specified engine.

    Uses strategy pattern with automatic fallback to other engines on failure.
    This follows SOLID principles and provides production-grade error handling.

    Args:
        md_file: Path to input markdown file
        output_pdf: Path for output PDF file
        engine: PDF engine to use ('auto' for automatic selection)
        options: PDF generation options (uses academic defaults if None)

    Returns:
        bool: True if PDF generation succeeded, False otherwise

    Examples:
        >>> export_pdf(Path('draft.md'), Path('draft.pdf'))
        >>> export_pdf(Path('draft.md'), Path('draft.pdf'), engine='libreoffice')
        >>> options = PDFGenerationOptions(line_spacing=1.5)
        >>> export_pdf(Path('draft.md'), Path('draft.pdf'), options=options)
    """
    md_file = Path(md_file)
    output_pdf = Path(output_pdf)

    # Extract metadata from YAML frontmatter
    metadata = extract_metadata_from_yaml(md_file)

    # Create options with metadata if not provided
    if options is None:
        options = PDFGenerationOptions(
            title=metadata.get('title'),
            subtitle=metadata.get('subtitle'),
            author=metadata.get('author'),
            date=metadata.get('date'),
            institution=metadata.get('institution'),
            department=metadata.get('department'),
            course=metadata.get('degree'),  # Map degree to course field
            instructor=metadata.get('advisor'),  # Map advisor to instructor field
            student_id=metadata.get('student_id'),
            project_type=metadata.get('project_type'),
            system_credit=metadata.get('system_credit')
        )

    logger.info("="*70)
    logger.info(f"Generating PDF: {output_pdf.name}")
    logger.info(f"Input: {md_file}")
    logger.info(f"Engine: {engine}")
    logger.info("="*70)

    # Use factory to generate with automatic fallback
    result = PDFEngineFactory.generate_with_fallback(
        md_file=md_file,
        output_pdf=output_pdf,
        options=options,
        preferred_engine=engine if engine != 'auto' else None
    )

    # Display result
    if result.success:
        logger.info(f"PDF created successfully: {result.output_path}")
        logger.info(f"Engine used: {result.engine_name}")

        if result.warnings:
            logger.warning("Warnings during PDF generation:")
            for warning in result.warnings:
                logger.warning(f"  - {warning}")

        return True
    else:
        logger.error("PDF generation failed")
        logger.error(f"Error: {result.error_message}")
        return False


def _normalize_yaml_for_pandoc(md_content: str) -> str:
    """
    Normalize YAML frontmatter field names to English for Pandoc compatibility.

    Pandoc only recognizes English field names (title, subtitle, author, date)
    for creating styled paragraphs in DOCX/PDF output. This function translates
    localized field names back to English while preserving the field values.

    Supported translations:
    - German: titel→title, untertitel→subtitle, autor→author, datum→date
    - Spanish: título→title, subtítulo→subtitle, autor→author, fecha→date
    - French: titre→title, sous-titre→subtitle, auteur→author, date→date

    Args:
        md_content: Markdown content with YAML frontmatter

    Returns:
        Markdown content with normalized YAML field names
    """
    import re

    # Translation map: localized → English
    field_translations = {
        # German
        'titel:': 'title:',
        'untertitel:': 'subtitle:',
        'autor:': 'author:',
        'datum:': 'date:',
        'wortzahl:': 'word_count:',
        'seitenzahl:': 'page_count:',
        'sprache:': 'language:',
        'thema:': 'topic:',
        'schlagwörter:': 'keywords:',
        'qualitäts_bewertung:': 'quality_score:',
        'system_ersteller:': 'system_creator:',
        'zitate_verifiziert:': 'citations_verified:',
        'visuelle_elemente:': 'visual_elements:',
        'generierungs_methode:': 'generation_method:',
        'beschreibung_showcase:': 'showcase_description:',
        'system_fähigkeiten:': 'system_capabilities:',
        'aufruf_zur_aktion:': 'call_to_action:',
        'lizenz:': 'license:',

        # Spanish
        'título:': 'title:',
        'subtítulo:': 'subtitle:',
        'fecha:': 'date:',
        'recuento_de_palabras:': 'word_count:',
        'idioma:': 'language:',

        # French
        'titre:': 'title:',
        'sous-titre:': 'subtitle:',
        'auteur:': 'author:',
        'nombre_de_mots:': 'word_count:',
        'langue:': 'language:',
    }

    # Only process if YAML frontmatter exists
    if not md_content.strip().startswith('---'):
        return md_content

    # Extract YAML frontmatter
    parts = md_content.split('---', 2)
    if len(parts) < 3:
        return md_content

    yaml_content = parts[1]
    rest_content = parts[2]

    # Translate field names (case-insensitive)
    for localized, english in field_translations.items():
        yaml_content = re.sub(
            f'^{re.escape(localized)}',
            english,
            yaml_content,
            flags=re.MULTILINE | re.IGNORECASE
        )

    # Reconstruct markdown
    return f'---{yaml_content}---{rest_content}'


def _is_table_separator(line: str) -> bool:
    """A markdown table separator looks like `|---|---|` (with optional :---, ---:, :--:)."""
    s = line.strip()
    if not s.startswith("|") or not s.endswith("|"):
        return False
    cells = [c.strip() for c in s.strip("|").split("|")]
    if not cells:
        return False
    for cell in cells:
        if not cell:
            return False
        # Allow leading/trailing colons for alignment
        if not all(ch in "-:" for ch in cell):
            return False
        if "-" not in cell:
            return False
    return True


def _split_table_row(line: str) -> list[str]:
    """Split `| a | b | c |` into ['a', 'b', 'c'], stripping whitespace."""
    inner = line.strip().strip("|")
    return [cell.strip() for cell in inner.split("|")]


def _add_docx_table(doc, rows: list[list[str]]) -> None:
    """Insert a python-docx Table from a list of rows (header first)."""
    if not rows:
        return
    n_cols = max(len(r) for r in rows)
    table = doc.add_table(rows=len(rows), cols=n_cols)
    table.style = "Light Grid Accent 1"
    for r_idx, row in enumerate(rows):
        for c_idx in range(n_cols):
            cell = table.rows[r_idx].cells[c_idx]
            cell_text = row[c_idx] if c_idx < len(row) else ""
            # Clear the default paragraph then add a properly-formatted one.
            cell.text = ""
            para = cell.paragraphs[0]
            _emit_inline_runs(para, cell_text, base_bold=(r_idx == 0))


# Inline markdown patterns. Order matters — longer / more specific patterns first.
# Each tuple is (pattern, kind) where kind tells _emit_inline_runs how to style the captured text.
import re as _re

_INLINE_PATTERNS = [
    # Bold-italic ***x*** or ___x___
    (_re.compile(r"\*\*\*(.+?)\*\*\*"), "bold_italic"),
    (_re.compile(r"___(.+?)___"),       "bold_italic"),
    # Bold **x** or __x__
    (_re.compile(r"\*\*(.+?)\*\*"),     "bold"),
    (_re.compile(r"__(.+?)__"),         "bold"),
    # Inline code `x`
    (_re.compile(r"`([^`]+?)`"),        "code"),
    # Link [text](url) — kind tracks the URL via the regex itself
    (_re.compile(r"\[([^\]]+?)\]\(([^)]+?)\)"), "link"),
    # Italic *x* or _x_  (after bold so ** isn't matched as italic-italic)
    (_re.compile(r"(?<![*\w])\*([^*\n]+?)\*(?!\*)"), "italic"),
    (_re.compile(r"(?<![_\w])_([^_\n]+?)_(?!_)"),   "italic"),
]


def _emit_inline_runs(para, text: str, *, base_bold: bool = False) -> None:
    """Walk a single line of markdown text and append python-docx Runs with formatting."""
    if not text:
        return
    # Strip stray heading markers that shouldn't appear inside a paragraph
    cursor = 0
    # Find all non-overlapping spans across all patterns and process in order.
    spans = []
    for pattern, kind in _INLINE_PATTERNS:
        for m in pattern.finditer(text):
            spans.append((m.start(), m.end(), kind, m))
    # Sort by start; resolve overlaps by preferring the earlier start, then the wider span.
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    chosen = []
    last_end = -1
    for s in spans:
        if s[0] >= last_end:
            chosen.append(s)
            last_end = s[1]
    for start, end, kind, m in chosen:
        if start > cursor:
            _add_plain_run(para, text[cursor:start], base_bold=base_bold)
        if kind == "link":
            label, url = m.group(1), m.group(2)
            run = para.add_run(label)
            run.font.color.rgb = _docx_color("#1c2eff")
            run.underline = True
            if base_bold:
                run.bold = True
        elif kind == "code":
            run = para.add_run(m.group(1))
            run.font.name = "Consolas"
            run.font.size = _docx_pt(10)
            if base_bold:
                run.bold = True
        elif kind == "bold_italic":
            run = para.add_run(m.group(1))
            run.bold = True
            run.italic = True
        elif kind == "bold":
            run = para.add_run(m.group(1))
            run.bold = True
        elif kind == "italic":
            run = para.add_run(m.group(1))
            run.italic = True
            if base_bold:
                run.bold = True
        cursor = end
    if cursor < len(text):
        _add_plain_run(para, text[cursor:], base_bold=base_bold)


def _add_plain_run(para, text: str, *, base_bold: bool = False) -> None:
    if not text:
        return
    run = para.add_run(text)
    if base_bold:
        run.bold = True


def _docx_color(hex_str: str):
    from docx.shared import RGBColor
    hex_str = hex_str.lstrip("#")
    return RGBColor(int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16))


def _docx_pt(n):
    from docx.shared import Pt
    return Pt(n)


def _extract_toc_entries(lines: list[str]) -> list[tuple[int, str]]:
    """Scan the (frontmatter-stripped) markdown for headings.

    Skips headings inside fenced code blocks. Returns a list of (level, text)
    where level is 1..3 — deeper headings rarely belong in a TOC.
    """
    entries: list[tuple[int, str]] = []
    in_fence = False
    for raw in lines:
        line = raw.rstrip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _re.match(r"^(#{1,3})\s+(.*)$", line)
        if not m:
            continue
        level = len(m.group(1))
        text = _strip_inline_markers(m.group(2).strip())
        if not text:
            continue
        entries.append((level, text))
    return entries


def _strip_inline_markers(text: str) -> str:
    """Strip the markers used by the inline parser so TOC lines stay clean."""
    out = text
    out = _re.sub(r"\*\*\*(.+?)\*\*\*", r"\1", out)
    out = _re.sub(r"___(.+?)___", r"\1", out)
    out = _re.sub(r"\*\*(.+?)\*\*", r"\1", out)
    out = _re.sub(r"__(.+?)__", r"\1", out)
    out = _re.sub(r"`([^`]+?)`", r"\1", out)
    out = _re.sub(r"\[([^\]]+?)\]\(([^)]+?)\)", r"\1", out)
    out = _re.sub(r"(?<!\w)\*([^*\n]+?)\*(?!\*)", r"\1", out)
    out = _re.sub(r"(?<!\w)_([^_\n]+?)_(?!_)", r"\1", out)
    return out.strip()


def _render_static_toc(doc, entries: list[tuple[int, str]], *, body_font: str) -> None:
    """Render a plain-text TOC listing. Indents by heading level."""
    from docx.shared import Pt, Inches

    title = doc.add_heading("Table of Contents", level=1)
    try:
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    except Exception:
        pass

    n_h1 = 0
    n_h2 = 0
    n_h3 = 0
    for level, text in entries:
        if level == 1:
            n_h1 += 1
            n_h2 = 0
            n_h3 = 0
            number = f"{n_h1}"
        elif level == 2:
            n_h2 += 1
            n_h3 = 0
            number = f"{n_h1}.{n_h2}"
        else:
            n_h3 += 1
            number = f"{n_h1}.{n_h2}.{n_h3}"

        para = doc.add_paragraph()
        para.paragraph_format.left_indent = Inches(0.0 if level == 1 else 0.25 * (level - 1))
        para.paragraph_format.space_after = Pt(4)
        # Number column
        num_run = para.add_run(f"{number}  ")
        num_run.bold = (level == 1)
        num_run.font.name = body_font
        num_run.font.size = Pt(12 if level == 1 else 11)
        # Title
        text_run = para.add_run(text)
        text_run.bold = (level == 1)
        text_run.font.name = body_font
        text_run.font.size = Pt(12 if level == 1 else 11)


def _insert_word_toc_field(doc) -> None:
    """Insert a Word TOC field that auto-populates with page numbers.

    Users see the static list above; if they right-click → Update Field
    Word will replace this with a real linked TOC with page numbers.
    """
    try:
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
    except Exception:
        return

    para = doc.add_paragraph()
    para.paragraph_format.space_before = _docx_pt(8)
    run = para.add_run()
    # Hint label
    hint = doc.add_paragraph()
    hint_run = hint.add_run(
        "(For page numbers, right-click the TOC below and choose Update Field in Microsoft Word.)"
    )
    hint_run.italic = True
    hint_run.font.size = _docx_pt(10)

    fld_para = doc.add_paragraph()
    fld_run = fld_para.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = 'TOC \\o "1-3" \\h \\z \\u'
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    placeholder = OxmlElement("w:t")
    placeholder.text = "[Right-click → Update Field to populate]"
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    fld_run._r.append(fld_begin)
    fld_run._r.append(instr)
    fld_run._r.append(fld_sep)
    fld_run._r.append(placeholder)
    fld_run._r.append(fld_end)


def _strip_yaml_frontmatter(md: str) -> str:
    """Drop a leading `---\\n...\\n---\\n` block if present."""
    if not md.startswith("---"):
        return md
    parts = md.split("\n", 1)
    if len(parts) < 2:
        return md
    end = md.find("\n---", 3)
    if end < 0:
        return md
    after = md[end + 4:]
    return after.lstrip("\n")


def export_docx_basic(md_file: Path, output_docx: Path) -> bool:
    """
    Export markdown to DOCX format using basic python-docx parsing.

    Note: This is a legacy/fallback function with limited formatting support.
    Does NOT support tables, complex formatting, or citations.

    For production use, prefer export_docx() which uses Pandoc with full
    markdown support and proper table formatting.

    Args:
        md_file: Path to input markdown file
        output_docx: Path for output DOCX file

    Returns:
        bool: True if DOCX generation succeeded, False otherwise
    """
    md_file = Path(md_file)
    output_docx = Path(output_docx)

    try:
        from docx import Document
        from docx.shared import Pt, Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH
    except ImportError:
        logger.error("python-docx not installed")
        logger.error("Run: pip install python-docx")
        return False

    try:
        # Read markdown
        with open(md_file, 'r', encoding='utf-8') as f:
            md_content = f.read()

        # Drop the YAML frontmatter outright — basic exporter doesn't render a
        # cover page from it, so leaving it in produces a wall of key:value lines.
        md_content = _strip_yaml_frontmatter(md_content)
        lines = md_content.splitlines()

        # Create document with 1" margins
        doc = Document()
        for section in doc.sections:
            section.top_margin = Inches(1.0)
            section.bottom_margin = Inches(1.0)
            section.left_margin = Inches(1.0)
            section.right_margin = Inches(1.0)

        # Centered italic footer (manual page numbering hint)
        footer_para = doc.sections[0].footer.paragraphs[0]
        footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = footer_para.add_run("[Add page numbers via Insert > Page Number in Word]")
        run.font.name = 'Times New Roman'
        run.font.size = Pt(10)
        run.font.italic = True

        BODY_FONT = "Times New Roman"
        BODY_SIZE = Pt(12)

        # --- Build Table of Contents from headings before walking the body ---
        toc_entries = _extract_toc_entries(lines)
        if toc_entries:
            _render_static_toc(doc, toc_entries, body_font=BODY_FONT)
            # Word's auto-updating TOC field. Hidden behind the static list so users
            # who Update Field get the real page numbers; everyone else sees the
            # static one we just wrote.
            _insert_word_toc_field(doc)
            doc.add_page_break()

        def style_body(para):
            para.paragraph_format.line_spacing = 1.5
            para.paragraph_format.space_after = Pt(6)
            for r in para.runs:
                if not r.font.name:
                    r.font.name = BODY_FONT
                if not r.font.size:
                    r.font.size = BODY_SIZE

        i = 0
        while i < len(lines):
            line = lines[i].rstrip()

            # Blank
            if not line.strip():
                i += 1
                continue

            # Fenced code block ```lang ... ```
            if line.startswith("```"):
                lang = line[3:].strip()
                code_buf = []
                i += 1
                while i < len(lines) and not lines[i].rstrip().startswith("```"):
                    code_buf.append(lines[i].rstrip("\n"))
                    i += 1
                if i < len(lines):
                    i += 1  # skip closing ```
                para = doc.add_paragraph()
                run = para.add_run("\n".join(code_buf))
                run.font.name = "Consolas"
                run.font.size = Pt(10)
                # Light gray shade via paragraph; python-docx doesn't easily set bg, so we just
                # indent and use the monospace font.
                para.paragraph_format.left_indent = Inches(0.25)
                para.paragraph_format.space_after = Pt(8)
                continue

            # Pipe table: header + separator + body
            if line.startswith("|") and i + 1 < len(lines) and _is_table_separator(lines[i + 1]):
                table_rows = [_split_table_row(line)]
                i += 2
                while i < len(lines) and lines[i].rstrip().startswith("|"):
                    table_rows.append(_split_table_row(lines[i]))
                    i += 1
                _add_docx_table(doc, table_rows)
                continue

            # ATX headings #, ##, ###, ####, ##### (centered for top level only)
            if line.startswith("#"):
                m = _re.match(r"^(#{1,6})\s+(.*)$", line)
                if m:
                    level = len(m.group(1))
                    heading_text = m.group(2).strip()
                    para = doc.add_heading(level=min(level, 4))
                    _emit_inline_runs(para, heading_text)
                    if level == 1:
                        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    i += 1
                    continue

            # Horizontal rule (--- on its own line, not a table separator)
            if line.strip() in {"---", "***", "___"}:
                para = doc.add_paragraph()
                run = para.add_run("_" * 60)
                run.font.size = Pt(12)
                i += 1
                continue

            # Blockquote (one or more consecutive > lines)
            if line.startswith(">"):
                quote_lines = []
                while i < len(lines) and lines[i].lstrip().startswith(">"):
                    quote_lines.append(_re.sub(r"^>\s?", "", lines[i].rstrip()))
                    i += 1
                joined = " ".join(quote_lines).strip()
                para = doc.add_paragraph()
                para.paragraph_format.left_indent = Inches(0.4)
                para.paragraph_format.right_indent = Inches(0.4)
                _emit_inline_runs(para, joined)
                for r in para.runs:
                    r.italic = True
                    if not r.font.name:
                        r.font.name = BODY_FONT
                    if not r.font.size:
                        r.font.size = BODY_SIZE
                continue

            # Unordered list (- or * item)
            if _re.match(r"^[\-\*\+]\s+", line):
                while i < len(lines) and _re.match(r"^[\-\*\+]\s+", lines[i].rstrip()):
                    item_text = _re.sub(r"^[\-\*\+]\s+", "", lines[i].rstrip())
                    para = doc.add_paragraph(style="List Bullet")
                    _emit_inline_runs(para, item_text)
                    style_body(para)
                    i += 1
                continue

            # Ordered list (1. item, 2. item, ...)
            if _re.match(r"^\d+\.\s+", line):
                while i < len(lines) and _re.match(r"^\d+\.\s+", lines[i].rstrip()):
                    item_text = _re.sub(r"^\d+\.\s+", "", lines[i].rstrip())
                    para = doc.add_paragraph(style="List Number")
                    _emit_inline_runs(para, item_text)
                    style_body(para)
                    i += 1
                continue

            # Regular paragraph — collapse soft-wrapped lines until blank or block break
            para_buf = [line]
            i += 1
            while i < len(lines):
                nxt = lines[i].rstrip()
                if not nxt.strip():
                    break
                if nxt.startswith(("#", ">", "|", "```")):
                    break
                if _re.match(r"^[\-\*\+]\s+", nxt) or _re.match(r"^\d+\.\s+", nxt):
                    break
                if nxt in {"---", "***", "___"}:
                    break
                para_buf.append(nxt)
                i += 1
            paragraph_text = " ".join(para_buf)
            para = doc.add_paragraph()
            _emit_inline_runs(para, paragraph_text)
            style_body(para)

        doc.save(output_docx)
        logger.info(f"DOCX created successfully: {output_docx}")
        return True

    except Exception as e:
        logger.error(f"DOCX generation failed: {str(e)}", exc_info=True)
        return False


def export_docx(
    md_file: Path,
    output_docx: Path,
    options: Optional[PDFGenerationOptions] = None
) -> bool:
    """
    Export markdown to DOCX with full formatting support (tables, citations, styles).

    Uses Pandoc with custom reference document for professional formatting that matches
    PDF output quality. Automatically falls back to basic export if Pandoc unavailable.

    Features:
    - ✅ Tables rendered as Word tables (not pipe text)
    - ✅ Proper heading styles (APA 7th edition compatible)
    - ✅ Citations and footnotes
    - ✅ Table of contents
    - ✅ Custom fonts and spacing from reference document

    Args:
        md_file: Path to input markdown file
        output_docx: Path for output DOCX file
        options: PDF generation options (uses academic defaults if None)

    Returns:
        bool: True if DOCX generation succeeded, False otherwise

    Examples:
        >>> export_docx(Path('draft.md'), Path('draft.docx'))
        >>> options = PDFGenerationOptions(enable_toc=True, toc_depth=3)
        >>> export_docx(Path('draft.md'), Path('draft.docx'), options)
    """
    md_file = Path(md_file)
    output_docx = Path(output_docx)

    import subprocess
    import shutil

    # Extract metadata from YAML frontmatter
    metadata = extract_metadata_from_yaml(md_file)

    # Create options with metadata if not provided
    if options is None:
        options = PDFGenerationOptions(
            title=metadata.get('title'),
            subtitle=metadata.get('subtitle'),
            author=metadata.get('author'),
            date=metadata.get('date'),
            institution=metadata.get('institution'),
            department=metadata.get('department'),
            faculty=metadata.get('faculty'),
            course=metadata.get('degree'),  # Map degree to course field
            instructor=metadata.get('advisor'),  # Map advisor to instructor field
            second_examiner=metadata.get('second_examiner'),
            student_id=metadata.get('student_id'),
            project_type=metadata.get('project_type'),
            system_credit=metadata.get('system_credit'),
            location=metadata.get('location')
        )

    # Try Pandoc method first (best quality)
    if not shutil.which('pandoc'):
        logger.warning("Pandoc not found - falling back to basic DOCX export")
        logger.warning("Tables and advanced formatting will be limited")
        logger.info("Install Pandoc for better results: sudo apt install pandoc")
        return export_docx_basic(md_file, output_docx)

    try:
        # Read and normalize YAML field names for Pandoc compatibility
        # (Pandoc only recognizes English field names like 'title', 'author', 'date')
        with open(md_file, 'r', encoding='utf-8') as f:
            md_content = f.read()

        md_content = _normalize_yaml_for_pandoc(md_content)

        # Write normalized content to temporary file for Pandoc
        import tempfile
        temp_md = None
        try:
            temp_fd, temp_path = tempfile.mkstemp(suffix='.md', text=True)
            temp_md = Path(temp_path)
            with open(temp_md, 'w', encoding='utf-8') as f:
                f.write(md_content)
        finally:
            if temp_fd:
                import os
                os.close(temp_fd)

        # Locate reference document
        reference_doc = Path(__file__).parent.parent / "examples" / "custom-reference.docx"

        if not reference_doc.exists():
            logger.warning(f"Reference document not found: {reference_doc}")
            logger.warning("Continuing without reference document (may lose some formatting)")
            reference_doc = None

        # Build pandoc command (use normalized temp file)
        cmd = [
            'pandoc',
            str(temp_md),  # Use normalized markdown instead of original
            '-o', str(output_docx),
            '--from', 'markdown',
            '--to', 'docx',
        ]

        # Add reference document for styling
        if reference_doc:
            cmd.extend(['--reference-doc', str(reference_doc)])

        # Add table of contents (Pandoc generates a proper Word TOC field)
        if options.enable_toc:
            cmd.append('--toc')
            cmd.extend(['--toc-depth', str(options.toc_depth)])

        # Add metadata if provided
        if options.title:
            cmd.extend(['--metadata', f'title={options.title}'])
        if options.author:
            cmd.extend(['--metadata', f'author={options.author}'])

        logger.info("="*70)
        logger.info(f"Generating DOCX with Pandoc: {output_docx.name}")
        logger.info(f"Input: {md_file}")
        if reference_doc:
            logger.info(f"Reference doc: {reference_doc.name}")
        logger.info("="*70)

        # Run pandoc
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode != 0:
            logger.error(f"Pandoc failed with return code {result.returncode}")
            if result.stderr:
                logger.error(f"Error: {result.stderr}")
            return False

        logger.info(f"DOCX created successfully: {output_docx}")
        logger.info("Tables, formatting, and styling preserved from markdown")

        # Post-process DOCX to add academic structure (title page + TOC + page breaks)
        # Fixes Pandoc's inline title block by inserting professional page breaks
        from utils.docx_post_processor import insert_academic_structure

        # Build options dict from PDFGenerationOptions for cover page enhancement
        post_options = {}
        if options:
            if options.institution:
                post_options['institution'] = options.institution
            if hasattr(options, 'faculty') and options.faculty:
                post_options['faculty'] = options.faculty
            if options.department:
                post_options['department'] = options.department
            if options.course:
                post_options['course'] = options.course
            if options.instructor:
                post_options['instructor'] = options.instructor
            if hasattr(options, 'second_examiner') and options.second_examiner:
                post_options['second_examiner'] = options.second_examiner
            if options.student_id:
                post_options['student_id'] = options.student_id
            if hasattr(options, 'project_type') and options.project_type:
                post_options['project_type'] = options.project_type
            if hasattr(options, 'system_credit') and options.system_credit:
                post_options['system_credit'] = options.system_credit
            if hasattr(options, 'location') and options.location:
                post_options['location'] = options.location

        if not insert_academic_structure(output_docx, verbose=True, options=post_options if post_options else None):
            logger.warning("Post-processing failed - DOCX created but may lack page structure")
            logger.warning("DOCX will have inline title block instead of standalone pages")
            return True  # Still return True since basic DOCX was created

        return True

    except subprocess.TimeoutExpired:
        logger.error("DOCX generation timed out (>60s)")
        return False
    except Exception as e:
        logger.error(f"DOCX generation failed: {str(e)}")
        return False
    finally:
        # Clean up temporary markdown file
        if temp_md and temp_md.exists():
            temp_md.unlink()


def show_available_engines() -> None:
    """Display available PDF engines and their status."""
    logger.info("="*70)
    logger.info("Available PDF Engines")
    logger.info("="*70)

    engines = get_available_engines()
    if not engines:
        logger.warning("No PDF engines available")
        logger.info("Install at least one of:")
        logger.info("  - LibreOffice: sudo apt install libreoffice-writer libreoffice-core-nogui")
        logger.info("  - Pandoc: sudo apt install pandoc texlive-latex-base texlive-latex-recommended")
        logger.info("  - WeasyPrint: pip install weasyprint")
        return

    recommended = get_recommended_engine()

    for engine in engines:
        marker = "[Recommended]" if engine == recommended else ""
        logger.info(f"  {engine} {marker}")

    if recommended:
        logger.info(f"Recommended: {recommended}")


def main():
    """CLI entry point."""
    # Logging is automatically configured by utils.logging_config on import

    parser = argparse.ArgumentParser(
        description='Export markdown to professional academic PDF/DOCX',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Auto-select best engine
  python export_professional.py draft.md --pdf draft.pdf

  # Use specific engine
  python export_professional.py draft.md --pdf draft.pdf --engine libreoffice

  # Generate both PDF and DOCX
  python export_professional.py draft.md --pdf draft.pdf --docx draft.docx

  # List available engines
  python export_professional.py --list-engines

Engine Options:
  auto         - Automatically select best available engine (recommended)
  libreoffice  - Use LibreOffice (best quality, requires installation)
  pandoc       - Use Pandoc/LaTeX (highest quality, academic standard)
  weasyprint   - Use WeasyPrint (fallback, known font rendering issues)
        '''
    )
    parser.add_argument('input', nargs='?', help='Input markdown file')
    parser.add_argument('--pdf', help='Output PDF file')
    parser.add_argument('--docx', help='Output DOCX file')
    parser.add_argument(
        '--engine',
        choices=['auto', 'libreoffice', 'pandoc', 'weasyprint'],
        default='auto',
        help='PDF engine to use (default: auto)'
    )
    parser.add_argument(
        '--list-engines',
        action='store_true',
        help='List available PDF engines and exit'
    )

    args = parser.parse_args()

    # List engines mode
    if args.list_engines:
        show_available_engines()
        sys.exit(0)

    # Validate arguments
    if not args.input:
        parser.error("Input file required (or use --list-engines)")

    input_file = Path(args.input)

    if not input_file.exists():
        logger.error(f"Input file not found: {input_file}")
        sys.exit(1)

    if not args.pdf and not args.docx:
        parser.error("Specify --pdf and/or --docx output file")

    # Generate outputs
    success = True

    if args.pdf:
        pdf_success = export_pdf(input_file, Path(args.pdf), engine=args.engine)
        success = success and pdf_success

    if args.docx:
        docx_success = export_docx(input_file, Path(args.docx))
        success = success and docx_success

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

"""Humanize a .docx IN PLACE, so the student gets their document back.

Why this exists rather than reusing the text extractor: `_extract_docx_text`
(api/app/routers/uploads.py) was built to feed the AGENT, where layout costs
nothing — it takes `p.text`, so heading levels and character formatting are
gone, and it appends every table at the END as pipe-joined rows, detached from
the caption that introduced it. That is fine for classification and useless as
the input to a rewrite you intend to hand to a supervisor.

So this walks the document object instead and writes the rewrite back into the
same paragraphs. Paragraph styles, heading levels, numbering, tables and the
overall structure survive because they are never touched.

Two things are skipped BY DESIGN, not by omission:

  tables   — they are data. The frozen-token rule already forbids changing a
             number, so re-voicing a results table is pure risk. python-docx's
             `doc.paragraphs` excludes table-cell paragraphs, so this falls out
             of the walk for free.
  headings — structural labels, not prose. Re-voicing "4.3.3 Thang đo Chuyên
             môn" produces a heading that no longer matches the table of
             contents.

Known loss, stated plainly: replacing a paragraph's text rebuilds its runs, so
a **bold** phrase mid-sentence does not survive. The first run is kept (which
preserves the paragraph's style and that run's character formatting) and the
rest are blanked.
"""
from __future__ import annotations

import io
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

# A paragraph shorter than this is a caption, a label, a figure note or a
# stray fragment — "Bảng 4.7: Chi tiết độ tin cậy thang đo" has nothing to
# re-voice, and rewriting it risks breaking a cross-reference.
_MIN_WORDS = 12

# Characters per batch. Consecutive body paragraphs are rewritten together:
# one call per ~2 pages instead of one per paragraph turns a 60-page thesis
# from ~300 calls into ~20, and gives the rewrite enough context to vary
# sentence rhythm ACROSS paragraphs rather than inside each one in isolation.
_BATCH_CHARS = 3000

_HEADING_STYLES = ("heading", "title", "subtitle", "toc", "caption")


def _is_heading(p: Any) -> bool:
    try:
        name = (p.style.name or "").strip().lower()
    except Exception:  # noqa: BLE001 — a malformed style must not sink the walk
        return False
    return any(name.startswith(h) for h in _HEADING_STYLES)


def _eligible(p: Any) -> bool:
    text = (p.text or "").strip()
    if not text or _is_heading(p):
        return False
    return len(text.split()) >= _MIN_WORDS


def _batches(indexed: list[tuple[int, str]]) -> list[list[int]]:
    """Group consecutive eligible paragraphs into rewrite passages.

    Breaks on a gap in the index (an intervening heading or table), so a batch
    never spans a section boundary — which would ask the model to keep one
    voice across two different topics.
    """
    out: list[list[int]] = []
    cur: list[int] = []
    size = 0
    prev_idx: int | None = None
    for idx, text in indexed:
        gap = prev_idx is not None and idx != prev_idx + 1
        if cur and (gap or size + len(text) > _BATCH_CHARS):
            out.append(cur)
            cur, size = [], 0
        cur.append(idx)
        size += len(text)
        prev_idx = idx
    if cur:
        out.append(cur)
    return out


def _open(body: bytes):
    from docx import Document  # noqa: PLC0415 — heavy, and only needed here
    return Document(io.BytesIO(body))


def scan_docx(body: bytes) -> dict:
    """What a rewrite would touch, without touching it. No LLM, no charge.

    Exists so the student sees the size of the job before paying for it: a
    thesis is hundreds of paragraphs, and "upload and hope" is the wrong way to
    spend someone's credits.
    """
    try:
        doc = _open(body)
    except Exception:  # noqa: BLE001
        logger.exception("humanize_docx: could not open document")
        return {"ok": False, "error": "unreadable"}

    paragraphs = doc.paragraphs
    eligible = [(i, (p.text or "").strip()) for i, p in enumerate(paragraphs) if _eligible(p)]
    headings = sum(1 for p in paragraphs if _is_heading(p) and (p.text or "").strip())
    short = sum(
        1 for p in paragraphs
        if (p.text or "").strip() and not _is_heading(p) and len((p.text or "").split()) < _MIN_WORDS
    )
    return {
        "ok": True,
        "body_paragraphs": len(eligible),
        "headings": headings,
        "short_or_captions": short,
        "tables": len(doc.tables),
        "passages": len(_batches(eligible)),
        "chars": sum(len(t) for _, t in eligible),
    }


def _set_paragraph_text(p: Any, text: str) -> None:
    """Replace a paragraph's text, keeping its style and first run's format."""
    if p.runs:
        p.runs[0].text = text
        for r in p.runs[1:]:
            r.text = ""
    else:
        p.add_run(text)


def humanize_docx(
    body: bytes,
    *,
    language: str = "vi",
    user_anchor: str | None = None,
    humanize_fn: Callable[..., dict] | None = None,
) -> tuple[bytes | None, dict]:
    """Rewrite every eligible body paragraph and return the rebuilt .docx.

    `humanize_fn` defaults to humanize_prose and is injectable so tests can
    drive the walk without a model.

    Returns (docx_bytes, report). A batch whose rewrite fails verification — or
    whose paragraph count comes back different from what was sent — keeps its
    ORIGINAL paragraphs. That second check is load-bearing: the batch is
    reassembled positionally, so a model that merges two paragraphs would
    otherwise shift every later paragraph's text into the wrong slot and
    silently scramble the document.
    """
    if humanize_fn is None:
        from .humanize import humanize_prose  # noqa: PLC0415
        humanize_fn = humanize_prose

    try:
        doc = _open(body)
    except Exception:  # noqa: BLE001
        logger.exception("humanize_docx: could not open document")
        return None, {"ok": False, "error": "unreadable"}

    paragraphs = doc.paragraphs
    eligible = [(i, (p.text or "").strip()) for i, p in enumerate(paragraphs) if _eligible(p)]
    if not eligible:
        return None, {"ok": False, "error": "no_prose",
                      "detail": "No body paragraphs long enough to rewrite — the "
                                "document looks like headings, tables or captions."}

    by_idx = dict(eligible)
    usage: list[dict] = []
    rewritten = skipped = 0
    failures: list[dict] = []

    for batch in _batches(eligible):
        source = [by_idx[i] for i in batch]
        joined = "\n\n".join(source)
        r = humanize_fn(joined, language=language, user_anchor=user_anchor)
        usage.extend(r.get("usage") or [])

        if not r.get("ok"):
            skipped += len(batch)
            failures.append({"paragraphs": len(batch), "error": r.get("error")})
            continue

        parts = [s.strip() for s in (r.get("text") or "").split("\n\n") if s.strip()]
        if len(parts) != len(batch):
            # Structural mismatch — keep the originals rather than reassemble
            # the document out of alignment.
            skipped += len(batch)
            failures.append({"paragraphs": len(batch), "error": "paragraph_count_changed"})
            continue

        for idx, new_text in zip(batch, parts):
            _set_paragraph_text(paragraphs[idx], new_text)
        rewritten += len(batch)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.getvalue(), {
        "ok": rewritten > 0,
        "rewritten": rewritten,
        "skipped": skipped,
        "failures": failures,
        "usage": usage,
    }

"""Read a .docx into plain text, IN DOCUMENT ORDER.

The agent twin of pdf_extract: one place that knows how to turn a Word file
into something a text-only brain can read.

Two properties matter, and both were learned the hard way:

  - Tables must come out AT ALL. A quantitative thesis keeps its results in
    them — Cronbach's alpha, EFA loadings, KMO, path coefficients. Text
    without the tables is a results chapter with no results.
  - Tables must come out WHERE THEY WERE WRITTEN. python-docx exposes
    `doc.paragraphs` and `doc.tables` as two flat lists with no interleaving,
    so the obvious implementation emits every paragraph and then every table,
    which moves a thesis's tables into one block at the very end. Downstream
    that broke the import's chapter split (every table landed on the final
    chapter's side, leaving the analysis module with none) and left the writer
    unable to tell which table belonged to which section.

  - Third, learned the same way: a results table is very often not a table at
    all. Students paste the SmartPLS/SPSS output straight in as a SCREENSHOT,
    so the numbers live in an image and this walk saw nothing. One real upload
    carried eleven result screenshots and extracted as a page of prose holding
    exactly one number; the writer then produced a Results chapter that cited
    tables it had never been given. Images are transcribed with the vision
    model and emitted in place, for the same document-order reason as tables.

  - Fourth: "we transcribe images" was not the same claim as "we read every
    image", and the gap between them lost numbers quietly. An image is skipped
    when it sits inside a table cell (a screenshot centred in a 1x1 table is an
    ordinary Word habit and `cell.text` cannot see it), when it is small on
    disk but large on the page (a cropped four-row table compresses under the
    byte floor), or when it falls past the per-document cap. Only the cap is a
    real decision, and it now says so in the output instead of dropping the
    tail in silence.

So walk the body XML instead of the convenience lists.
"""
from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)

# Namespaces needed to find an image reference inside a paragraph.
_NS_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_NS_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

# Bound the vision spend on one document: a deck of screenshots must not turn a
# single upload into an unbounded run of model calls. Small images are skipped
# outright — logos, bullets and signature scribbles carry no statistics.
_MAX_IMAGES = 25
# How many transcriptions may be in flight at once. Each call is essentially
# pure network wait (a model round-trip on a ~25 KB PNG), so serializing them
# spent an upload's entire latency budget on an idle socket: 12 screenshots
# measured 29s serial against a real _Result.docx. Six rather than "all of
# them" because _MAX_IMAGES allows 25, and 25 simultaneous vision calls is a
# rate-limit incident, not a speedup.
_OCR_CONCURRENCY = 6
_MIN_IMAGE_BYTES = 3000
# ...but bytes alone got this wrong in the direction that loses data. A tightly
# cropped four-row reliability table is mostly white, compresses to well under
# 2 KB, and is still 600px of readable numbers. So an image is only a logo when
# it is small BOTH on disk and on the page.
_MIN_IMAGE_PX = 200

_IMAGE_PROMPT = (
    "This image comes from a thesis (often SmartPLS/SPSS output). "
    "If it shows a TABLE, transcribe it verbatim as a Markdown table — keep every "
    "row label, column header and number EXACTLY as shown. "
    "If it is a path/model diagram, describe the constructs and the arrows between "
    "them, including any numbers on the paths. "
    "If it carries no data, reply with the single word NONE. "
    "Never invent, round or guess a number; mark unreadable cells [unreadable]."
)


def _image_rids(element) -> list[str]:
    """Relationship ids of every image embedded anywhere under one element.

    Takes any block element, not just a paragraph: a screenshot centred by
    dropping it into a 1x1 table is an ordinary Word habit, and a table cell is
    where this has to look to find it.
    """
    return [
        rid
        for blip in element.iter(f"{_NS_A}blip")
        if (rid := blip.get(f"{_NS_R}embed"))
    ]


def _longest_side_px(part) -> int:
    """Longest side of an image part in pixels, or 0 when it will not say."""
    try:
        image = part.image
        return max(int(image.px_width or 0), int(image.px_height or 0))
    except Exception:
        return 0


def _image_payload(doc, rid: str, ordinal: int) -> tuple[str, bytes, str] | None:
    """The bytes of one embedded image as (name, data, mime), or None to skip it.

    Split from the model call below and kept ON THE WALK THREAD deliberately:
    everything here reaches into python-docx and its shared lxml tree
    (`related_parts`, `.blob`, `.image`), which is not something to touch from
    six threads at once. The pool downstream receives plain bytes and never
    sees the document at all.
    """
    try:
        part = doc.part.related_parts[rid]
        data = part.blob
    except Exception:
        return None
    if not data:
        return None
    if len(data) < _MIN_IMAGE_BYTES and _longest_side_px(part) < _MIN_IMAGE_PX:
        return None
    name = str(getattr(part, "partname", f"image{ordinal}")).rsplit("/", 1)[-1]
    return (name, data, getattr(part, "content_type", None) or "image/png")


def _vision_block(payload: tuple[str, bytes, str]) -> str | None:
    """Vision-transcribe one image's bytes, or None when it carries no data.

    Runs in the thread pool. Never raises: a missing key, an unreachable model
    or an odd part degrades to the text-only extraction this module did before,
    and one bad image must not take the other eleven down with it.
    """
    name, data, mime = payload
    try:
        from agent.multimodal import Attachment, _transcribe_via_vision  # noqa: PLC0415 — heavy/lazy

        att = Attachment(filename=name, bytes=data, mime_type=mime)
        text = (_transcribe_via_vision(att, prompt=_IMAGE_PROMPT) or "").strip()
    except Exception:
        logger.exception("docx image transcription failed (%s)", name)
        return None
    if not text or text.upper().startswith("NONE"):
        return None
    return text


def extract_docx_text(data: bytes, *, transcribe_images: bool = True,
                      image_sink: list | None = None) -> str:
    """Paragraphs, table rows and embedded images as text, in document order.

    Table rows are flattened to `a | b | c` so the numbers inside them survive
    as text, and pasted result screenshots are transcribed where they appear.
    Best-effort: returns "" rather than raising, because the callers are an
    upload path and a chat turn, and neither should die on one odd file.

    `transcribe_images=False` skips the vision pass for callers that only need
    the prose and cannot afford the latency.

    `image_sink`, when given a list, also receives the BYTES of every image that
    transcribed to something — `{"figure", "name", "bytes", "mime"}`, with
    `figure` matching the `[Hình n]` label in the returned text. Chapter 4
    embeds the student's original SmartPLS screenshot rather than a table
    rebuilt from the transcription: the screenshot is visibly output from the
    software, and a supervisor reads that as evidence in a way retyped numbers
    are not. An image that transcribed to nothing gets no label and no entry, so
    the two stay in step.
    """
    try:
        from docx import Document  # noqa: PLC0415 — heavy, and only needed here
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        doc = Document(io.BytesIO(data))
        parts: list[str] = []
        over_cap = 0
        # One rid is one image, however many places reference it. `row.cells`
        # repeats a merged cell, so without this a merged screenshot is
        # transcribed twice: two vision calls, and the same table printed twice
        # into text a model then reads as two findings.
        seen_rids: set[str] = set()
        # (index into `parts`, payload) per image awaiting transcription. The
        # placeholder claims the image's SLOT during the walk, before any model
        # call happens, so the concurrent pass below can finish in whatever
        # order it likes and the text still reads in document order — the
        # property this whole module exists to protect.
        slots: list[tuple[int, tuple[str, bytes, str]]] = []

        def take_images(element) -> None:
            nonlocal over_cap
            if not transcribe_images:
                return
            for rid in _image_rids(element):
                if rid in seen_rids:
                    continue
                seen_rids.add(rid)
                # The cap now counts images ATTEMPTED, not images that came back
                # with text. It used to be the latter, which meant a document of
                # blank screenshots could keep spending model calls forever
                # without the counter moving. Budget should be spent by asking,
                # since asking is what costs.
                if len(slots) >= _MAX_IMAGES:
                    over_cap += 1
                    continue
                payload = _image_payload(doc, rid, len(slots) + 1)
                if payload is None:
                    continue
                slots.append((len(parts), payload))
                parts.append("")     # placeholder; filled in after the walk

        for child in doc.element.body.iterchildren():
            tag = child.tag.split("}")[-1]
            if tag == "p":
                text = Paragraph(child, doc).text
                if text and text.strip():
                    parts.append(text)
                take_images(child)
            elif tag == "tbl":
                for row in Table(child, doc).rows:
                    cells = [c.text.strip() for c in row.cells
                             if c.text and c.text.strip()]
                    if cells:
                        parts.append(" | ".join(cells))
                    # `cell.text` cannot see a pasted screenshot, and a results
                    # table inside a bordered cell is exactly where one lives.
                    for cell in row.cells:
                        take_images(cell._tc)
        # The walk is done and every image has a reserved slot; now pay for the
        # model calls, all at once instead of one after another. `pool.map`
        # rather than `as_completed` because it yields results in SUBMIT order,
        # which lines the zip up with `slots` without any sorting — the
        # ordering guarantee falls out of the API instead of being re-derived.
        filled: dict[int, str] = {}
        if slots:
            from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415 — only needed here

            with ThreadPoolExecutor(max_workers=min(_OCR_CONCURRENCY, len(slots))) as pool:
                for (slot_i, _payload), text in zip(
                        slots, pool.map(_vision_block, [p for _, p in slots])):
                    if text:
                        filled[slot_i] = text

        # Number the survivors in DOCUMENT order. The figure number is a label
        # the writer cites, so it has to follow the page, not the order twelve
        # threads happened to finish in.
        # `slots` is in document order and `filled` is keyed by slot index, so
        # sorting the surviving keys numbers the figures by page — the ordering
        # the label promises — and lets the sink reuse that same number.
        payload_by_slot = {slot_i: payload for slot_i, payload in slots}
        for n, slot_i in enumerate(sorted(filled), start=1):
            parts[slot_i] = f"[Hình {n}]\n{filled[slot_i]}"
            if image_sink is not None:
                name, blob, mime = payload_by_slot[slot_i]
                image_sink.append({"figure": n, "name": name, "bytes": blob, "mime": mime})
        # Drop the slots whose image yielded nothing. Only placeholders are ever
        # empty here — the walk appends text solely when it is non-blank.
        parts = [p for p in parts if p]
        images_done = len(filled)

        # Say what was left out. The cap is right — it bounds the spend on one
        # upload — but dropping the excess silently is not: a results chapter
        # with thirty screenshots came back looking complete and missing its
        # last five tables, and nothing downstream could tell.
        if over_cap:
            parts.append(
                f"[docx: {over_cap} more image(s) not read: over the "
                f"{_MAX_IMAGES}-image limit for one document]")
            logger.warning("docx extraction: %d image(s) over the %d-image cap",
                           over_cap, _MAX_IMAGES)
        if images_done:
            logger.info("docx extraction: transcribed %d embedded image(s)", images_done)
        return "\n".join(parts)
    except Exception:
        logger.exception("docx text extraction failed")
        return ""

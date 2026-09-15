"""Reconcile what a project HAS against what its state SAYS. No I/O, no model.

Diagnosis is a pure function so it can run on every turn for free and be tested
with literals. The adapter (api/app/doctor_adapter.py) does all the gathering
and all the repairing; this module only decides what is wrong.

Why this exists. Measured on the dev database, 2026-09-15:

  - 12 of 21 uploads had never ridden a turn. All 21 extracted successfully —
    the text sat on disk and no turn ever carried it.
  - Project 500319a8 held 102 rows of real SmartPLS coefficients in
    `uploads/_Result.docx.txt` from 06:07 UTC, while `m4_analysis.results` was
    `{}` and the module was marked done at 05:33.

Nothing noticed either. The project looked healthy while being empty, and every
later turn started blind. Both cases reach the student as the same sentence:
"tài liệu đã upload lên, chỉ là chưa được đọc".

The checks are deliberately heuristic rather than inferential. The numbers were
already turned into text when the file was uploaded, so paying a model to read
them a second time buys nothing — and a diagnosis that costs a model call is
one nobody can afford to run every turn.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class UploadRecord:
    upload_id: str
    filename: str
    sidecar_text: str | None
    ever_attached: bool


@dataclass(frozen=True)
class DoctorInput:
    # PER-MODULE slices, as load_full_context_store() returns them:
    # {"m1_topic": {...}, "m4_analysis": {...}}. Not flattened — every slice
    # carries its own `confirmed_at`, so a flat dict could not say WHICH module
    # is falsely marked done, and `reconstructable_modules` wants this shape.
    context_store: dict
    uploads: list[UploadRecord]
    chapter_prose: dict[str, str]


@dataclass(frozen=True)
class Finding:
    code: str
    detail: str
    repair: str  # "deterministic" | "directive" | "ask_student"
    payload: dict = field(default_factory=dict)


# Module id -> its slice key. Mirrors orchestrator.state._MODULE_TO_FIELD; kept
# local so this module has no import-time dependency on the state package.
_MODULE_FIELD = {
    "M1": "m1_topic",
    "M2": "m2_literature",
    "M3": "m3_design",
    "M4": "m4_analysis",
}

# A coefficient is a decimal with at least two places: 0.854, 12.30. Integers
# are excluded — an item count and a sample size are not results.
_COEF_RE = re.compile(r"-?\d+\.\d{2,}")

# Heading -> canonical table. First hit wins, so the specific patterns (HTMT,
# VIF) come before the broad reliability keywords that would also match them.
#
# The keyword sets come from the seven headings in the real file, typos
# included ("BOOSTRAPPING"). Student result exports are hand-assembled Word
# documents; matching only the correct spelling means matching the tidy half.
_TABLE_KEYWORDS = (
    ("discriminant_validity", ("htmt", "heterotrait", "fornell", "larcker",
                               "giá trị phân biệt")),
    ("collinearity", ("vif", "đa cộng tuyến", "collinearity")),
    ("explained_variance", ("r²", "r2", "r square", "q²", "q2", "f²", "f2",
                            "f square")),
    ("path_coefficients", ("bootstrap", "boostrap", "path", "đường dẫn",
                           "hệ số tác động", "structural", "giả thuyết")),
    ("reliability", ("cronbach", "composite reliability", " cr ", "ave",
                     "độ tin cậy")),
    ("outer_loadings", ("outer loading", "hệ số tải", "factor loading",
                        "loading")),
)

# `[Hình 2] (ảnh gốc: …)` — the .docx extractor writes an image caption between
# the heading and the table it introduces, so the line nearest a table is
# almost never its heading.
_CAPTION_RE = re.compile(r"^\[\s*(hình|hinh|figure|fig)\b", re.IGNORECASE)


def _match_table(heading: str) -> str | None:
    """Canonical table name for a heading, or None when nothing matches."""
    h = f" {heading.strip().lower()} "
    for name, keywords in _TABLE_KEYWORDS:
        if any(k in h for k in keywords):
            return name
    return None


def _canonical_table(heading: str) -> str:
    # An unmatched heading keeps its own text rather than being guessed at or
    # dropped. A mis-keyed table puts HTMT numbers under reliability, which is
    # worse than an oddly-named key nobody reads.
    return _match_table(heading) or (heading.strip()[:80] or "untitled")


# A heading is terse. The notes that sit between a heading and its table are
# sentences, and they mention the same vocabulary — "Outer Loading > 0.7 → Đạt
# yêu cầu về ĐỘ TIN CẬY của thang đo" matches `reliability` while introducing
# the outer-loadings table. Length is what separates the two reliably.
_HEADING_MAX_CHARS = 60


def _pick_heading(lines: list[str], previous: str = "") -> str:
    """The best heading for the table about to start.

    The real file reads:

        OUTER LOADINGS                      <- the heading
        Outer Loading > 0.7, → Đạt yêu cầu  <- a note, mentions "độ tin cậy"
        [Hình 2] (ảnh gốc: …hinh-02.png)    <- the caption
        | Matrix | ATT | DEC | …            <- the table

    Three things had to be true at once, and each was found by running this
    against that document:

    - captions are skipped, or all ten tables key to `[Hình N]`;
    - among lines that name a table, the SHORTEST wins, or the note above
      files outer loadings under reliability;
    - a table with no heading of its own continues the previous one, which is
      what a second page of the same table is.
    """
    candidates = [ln.strip() for ln in lines
                  if ln.strip() and not _CAPTION_RE.match(ln.strip())]
    named = [ln for ln in candidates
             if _match_table(ln) and len(ln) <= _HEADING_MAX_CHARS]
    if named:
        return min(named, key=len)
    if candidates:
        # Nothing recognisable: keep the nearest line as the key rather than
        # guessing a canonical name for it.
        return candidates[-1]
    return previous


def _parse_row(line: str) -> dict | None:
    """`| ATT_1 | 0.854 | | |` -> {"label": "ATT_1", "values": [0.854]}."""
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    values = [float(m) for c in cells for m in _COEF_RE.findall(c)]
    if not values:
        return None
    label = next((c for c in cells if c and not _COEF_RE.fullmatch(c)), "")
    return {"label": label, "values": values}


def parse_results_tables(sidecar_text: str) -> dict[str, list[dict]]:
    """Extracted sidecar text -> ONE dict keyed by table. `{}` when unsure.

    Deterministic on purpose. The hard part is not reading a number, it is
    knowing which table it belongs to: the real file spreads 102 rows over
    outer loadings, CR/AVE, HTMT, VIF and R², separated only by the heading
    above each block.

    Returns a dict keyed by table, never a list — the list shape silently
    shipped a Chapter 4 with no tables and verified zero numbers once already.
    """
    if not (sidecar_text or "").strip():
        return {}
    out: dict[str, list[dict]] = {}
    block: list[dict] = []
    heading = ""
    # Prose seen since the last table closed. Capped because a heading sits
    # near its table; anything further back belongs to another section.
    pending: list[str] = []
    # Tracked separately from `block` on purpose. A markdown table opens with a
    # header row and a `| :--- |` separator, neither of which carries a
    # coefficient — so "block is still empty" does NOT mean "no table has
    # started", and using it to decide re-recomputed the heading from an
    # already-emptied buffer, filing all 102 rows under `untitled`.
    in_table = False

    def _flush() -> None:
        if not block:
            return
        rows = out.setdefault(_canonical_table(heading), [])
        # Exact duplicates are dropped WITHIN a table. A wide matrix is exported
        # as several overlapping screenshots, and the overlap column repeats a
        # row verbatim: the real file yields INSP_1 twice, which counted as six
        # INSP items against a five-item scale and reads as a mismatch between
        # the questionnaire and the results. Identical label AND identical
        # values is the same measurement printed twice, never two findings.
        seen = {(r["label"], tuple(r["values"])) for r in rows}
        for row in block:
            key = (row["label"], tuple(row["values"]))
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)

    for line in sidecar_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            if not in_table:
                heading = _pick_heading(pending, previous=heading)
                pending = []
                in_table = True
            row = _parse_row(stripped)
            if row:
                block.append(row)
            continue
        if stripped:
            # Prose closes the open table; the line then becomes a heading
            # candidate for whatever table comes next.
            if in_table:
                _flush()
                block = []
                in_table = False
            pending.append(stripped)
            del pending[:-6]
    _flush()
    return out


# Canonical table name -> the `kind` results_render._figure_body looks up in
# `results.source_figures`. Two of our tables belong to one figure kind
# (measurement model covers loadings and reliability); collinearity has no
# figure slot and is simply not mapped.
_TABLE_TO_FIGURE_KIND = {
    "outer_loadings": "measurement_model",
    "reliability": "measurement_model",
    "discriminant_validity": "discriminant_validity",
    "explained_variance": "r2_q2",
    "path_coefficients": "structural_paths",
}

# `[Hình 2] (ảnh gốc: uploads/_Result.docx.img/hinh-02.png)` — the caption the
# .docx extractor writes above each table it pulled an image for. The path is
# already workspace-relative, which is the form commit_slice resolves.
_FIGURE_PATH_RE = re.compile(
    r"^\[\s*(?:hình|hinh|figure|fig)[^\]]*\]\s*\([^:]*:\s*([^)]+\.(?:png|jpg|jpeg))\s*\)",
    re.IGNORECASE)


def parse_source_figures(sidecar_text: str) -> dict[str, str]:
    """kind -> the student's own screenshot of that table.

    `results_render._figure_body` prefers this image over any table we could
    render, on purpose: a SmartPLS screenshot is visibly output from the
    software, and a supervisor reads that as evidence in a way retyped numbers
    are not. The whole mechanism already existed — nothing was populating it.

    The mapping is in the document. The extractor writes the image caption
    directly above the table it belongs to, so the same walk that finds a
    table's heading finds its figure. First figure per kind wins: a wide matrix
    split across two screenshots should be represented by its first page, not
    silently replaced by its continuation.
    """
    if not (sidecar_text or "").strip():
        return {}
    out: dict[str, str] = {}
    pending: list[str] = []
    figure = ""
    heading = ""
    in_table = False
    for line in sidecar_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("|"):
            if not in_table:
                in_table = True
                heading = _pick_heading(pending, previous=heading)
                kind = _TABLE_TO_FIGURE_KIND.get(_canonical_table(heading))
                if kind and figure and kind not in out:
                    out[kind] = figure
                pending, figure = [], ""
            continue
        in_table = False
        m = _FIGURE_PATH_RE.match(stripped)
        if m:
            figure = m.group(1).strip()
            continue          # a caption is not a heading
        pending.append(stripped)
        del pending[:-6]
    return out


def _unread_uploads(inp: DoctorInput) -> list[Finding]:
    """Files whose text was extracted and which no turn ever carried."""
    out = []
    for u in inp.uploads:
        if u.ever_attached or not (u.sidecar_text or "").strip():
            continue
        out.append(Finding(
            code="UNREAD_UPLOAD",
            detail=f"{u.filename} đã tải lên nhưng chưa từng được đọc.",
            repair="deterministic",
            payload={"upload_id": u.upload_id, "filename": u.filename},
        ))
    return out


def _results_not_in_state(inp: DoctorInput) -> list[Finding]:
    """Numbers on disk that never reached `m4_analysis.results`.

    The highest-value check and the cheapest one. Chapter 4 does not need raw
    data — an uploaded SmartPLS/SPSS export IS the analysis — so a project
    holding a parseable results table while `results` is empty is repairable
    with no model call at all.
    """
    if ((inp.context_store or {}).get("m4_analysis") or {}).get("results"):
        return []
    for u in inp.uploads:
        tables = parse_results_tables(u.sidecar_text or "")
        if not tables:
            continue
        n = sum(len(rows) for rows in tables.values())
        return [Finding(
            code="RESULTS_NOT_IN_STATE",
            detail=f"Đã đọc {n} dòng kết quả từ {u.filename} và lưu vào Chương 4.",
            repair="deterministic",
            payload={"results": tables, "filename": u.filename, "module": "M4"},
        )]
    return []


def _results_not_renderable(inp: DoctorInput) -> list[Finding]:
    """Results are stored, and no table will ever render from them.

    Chapter 4 is judged on its tables, and the machinery to build them is wired
    and working — `compose_chapter` → `_weave_verified_blocks` →
    `render_results_tables`. It bails on the first line, because
    `detect_family()` only recognises a canonical block:
    `measurement_model` (list), `discriminant_validity` (dict),
    `structural_model.r2`, `hypothesis_tests` (list), `fit`.

    A real project stored its results keyed by PATH instead —
    `{"ATT_to_INT": …, "EXP_to_INT": …, "gender_MGA": …}` — so `detect_family`
    returned None and the exported thesis carried 85,704 characters and ZERO
    tables. The numbers were all present; nothing could read them.

    This is the one check whose repair needs a model, so it is the only one
    marked `reparse`. The doctor stays pure: it decides that the stored shape is
    unrenderable and that a source document exists to re-extract from, and hands
    both to the adapter. Gated on brokenness, so it fires once on a project in
    this state rather than every turn.
    """
    from orchestrator.tools.results_render import (  # noqa: PLC0415
        detect_family, normalize_analysis_results)

    m4 = (inp.context_store or {}).get("m4_analysis") or {}
    stored = m4.get("results") or m4.get("analysis_results")
    if not stored:
        return []  # nothing stored at all is _results_not_in_state's problem
    try:
        if detect_family(normalize_analysis_results(stored)):
            return []  # already renderable — leave it alone
    except Exception:  # noqa: BLE001
        return []
    # Re-extract from the document, not from the mangled block: the source text
    # still has the column headers that say which number is CR and which is AVE.
    source = next((u for u in inp.uploads
                   if u.sidecar_text and parse_results_tables(u.sidecar_text)), None)
    if source is None:
        return []
    return [Finding(
        code="RESULTS_NOT_RENDERABLE",
        detail=f"Kết quả đã lưu nhưng không dựng được bảng cho Chương 4 — "
               f"đọc lại từ {source.filename}.",
        repair="reparse",
        payload={"module": "M4", "filename": source.filename,
                 "text": source.sidecar_text},
    )]


def _figures_not_linked(inp: DoctorInput) -> list[Finding]:
    """Renderable results, screenshots on disk, and nothing connecting them.

    `results_render._figure_body` prefers the student's own screenshot over any
    table we can build, and falls back silently when `source_figures` is absent
    — so an export renders retyped tables while twelve extracted images sit
    unreferenced in `uploads/<file>.img/`.

    Separate from RESULTS_NOT_RENDERABLE because that one is gated on the block
    being unreadable. A project whose results were already fixed would never
    revisit them, and its figures would stay unlinked forever.

    Deterministic and cheap: the caption above each table names its image.
    """
    cs = inp.context_store or {}
    m4 = cs.get("m4_analysis") or {}
    ar = m4.get("results") or m4.get("analysis_results")
    if not isinstance(ar, dict) or ar.get("source_figures"):
        return []
    for u in inp.uploads:
        figures = parse_source_figures(u.sidecar_text or "")
        if not figures:
            continue
        return [Finding(
            code="FIGURES_NOT_LINKED",
            detail=f"Đã gắn {len(figures)} ảnh kết quả gốc từ {u.filename} "
                   f"vào chương kết quả.",
            repair="deterministic",
            payload={"module": "M4", "results": {**ar, "source_figures": figures},
                     "filename": u.filename},
        )]
    return []


def _instrument_not_parsed(inp: DoctorInput) -> list[Finding]:
    """A questionnaire sitting as one blob instead of a measurement table.

    An uploaded questionnaire lands in `m3_design.instrument` as
    `{"raw": "<27 KB>"}`. Every downstream reader wants `items`: the panel can
    otherwise only print a word count, and the export cannot build "Bảng 3.1 —
    Thang đo các khái niệm nghiên cứu", the construct/code/item table a
    Vietnamese thesis is required to carry.

    Deterministic: the text was extracted at upload time, and a model asked to
    "extract the items" paraphrases them. These are the student's own survey
    questions — they come out verbatim or they are not the instrument that was
    fielded. Construct codes are taken from the outer-loadings labels already in
    `m4_analysis.results`, which is what their SmartPLS model actually used.
    """
    from orchestrator.instrument_parse import parse_instrument_items  # noqa: PLC0415

    cs = inp.context_store or {}
    m3 = cs.get("m3_design") or {}
    instrument = m3.get("instrument")
    if not isinstance(instrument, dict) or instrument.get("items"):
        return []
    raw = instrument.get("raw")
    if not isinstance(raw, str) or not raw.strip():
        return []

    results = (cs.get("m4_analysis") or {}).get("results") or {}
    loadings = results.get("outer_loadings") or []
    codes = sorted({str(r.get("label", "")).split("_")[0]
                    for r in loadings if isinstance(r, dict) and "_" in str(r.get("label", ""))})

    items = parse_instrument_items(raw, codes=codes)
    if not items:
        return []
    constructs = len({i["construct"] for i in items})
    return [Finding(
        code="INSTRUMENT_NOT_PARSED",
        detail=f"Đã tách bảng hỏi thành {len(items)} biến quan sát "
               f"thuộc {constructs} thang đo.",
        repair="deterministic",
        # The whole existing instrument rides along so the commit MERGES rather
        # than replaces — `raw` is the student's uploaded document and must
        # survive; `items` is only our structured reading of it.
        payload={"module": "M3", "items": items, "instrument": dict(instrument)},
    )]


# DoD gaps are internal strings — "missing target_sample_size", "results is
# empty". They are the right key for the loop guard and the wrong thing to show
# a student: the prompt forbids exposing schema names such as
# `target_sample_size` as student-facing prose, and one reached a real reply as
# "M3 đang được đánh dấu xong nhưng còn thiếu: missing target_sample_size."
_GAP_VI = {
    "missing target_sample_size": "cỡ mẫu mục tiêu",
    "missing paradigm": "hướng tiếp cận nghiên cứu",
    "missing design": "thiết kế nghiên cứu",
    "missing tool": "phần mềm phân tích",
    "missing sampling_strategy": "cách chọn mẫu",
    "missing analysis_outline": "dàn ý phân tích",
    "missing data_type_detected": "loại dữ liệu",
    "results is empty": "kết quả phân tích",
    "missing research_gaps": "khoảng trống nghiên cứu",
    "missing verified literature source": "nguồn tài liệu đã kiểm chứng",
}


def _humanize_gaps(gaps: list[str]) -> str:
    """Plain-language names for what a module is missing, deduped and ordered.

    An unmapped gap is dropped rather than printed raw — a student cannot act
    on `missing cmb_plan`, and the agent explains the specifics in prose.
    """
    named = list(dict.fromkeys(_GAP_VI[g] for g in gaps if g in _GAP_VI))
    return ", ".join(named)


def _false_done(inp: DoctorInput) -> list[Finding]:
    """A module wearing `confirmed_at` while its own DoD says it is not done.

    Read per-slice, not flat: `confirmed_at` exists on every module, so a
    flattened store would report whichever one happened to land last.
    """
    from orchestrator.state import dod_for_module  # noqa: PLC0415

    cs = inp.context_store or {}
    out = []
    for module, field_name in _MODULE_FIELD.items():
        slice_ = cs.get(field_name) or {}
        if not isinstance(slice_, dict) or not slice_.get("confirmed_at"):
            continue
        dod = dod_for_module(module)
        if dod is None:
            continue
        result = dod(slice_)
        if not result.done:
            human = _humanize_gaps(list(result.gaps))
            out.append(Finding(
                code="FALSE_DONE",
                detail=(f"{module} chưa hoàn tất — còn thiếu {human}."
                        if human else f"{module} chưa hoàn tất."),
                # The RAW gaps stay in the payload: they are what the loop guard
                # compares before and after a repair, and they must not be
                # lossy the way the student-facing sentence is.
                repair="deterministic",
                payload={"module": module, "gaps": list(result.gaps)},
            ))
    return out


def _refusal_chapter_names(inp: DoctorInput) -> list[str]:
    """Chapters that are a placeholder or a refusal rather than content."""
    from orchestrator.tools.m5_writing import _is_stub_prose  # noqa: PLC0415

    return [name for name, prose in (inp.chapter_prose or {}).items()
            if _is_stub_prose(prose or "")]


# A citation in finished prose: "(Nguyen, 2024)", "(Akram và Majeed 2026)", or
# the chat pill before it is converted. Deliberately loose — the question is
# "did this chapter cite ANYTHING", not "is every citation well-formed".
_CITATION_RE = re.compile(r"\([^()]{0,120}?(?:19|20)\d{2}[a-z]?[^()]{0,40}?\)|\{\{cite:")
# Below this a "chapter" is a stub or a placeholder, and having no citations in
# it says nothing.
_CITABLE_CHAPTER_CHARS = 2000
# Chapters that argue from literature. Results and conclusion cite far less and
# a thin count there is not evidence of anything broken.
_MUST_CITE = ("intro", "lit_review", "methodology")


def _uncited_chapter_names(inp: DoctorInput) -> list[str]:
    """Finished prose that cites nothing, on a project that HAS sources.

    This is the "uncited bibliography" failure, and it is invisible until an
    examiner opens the document. On the project that motivated it: M2 held five
    verified sources with DOIs, the exported docx rendered all five under "Tài
    liệu tham khảo", and the body carried ZERO citations across 84,684
    characters — a reference list no sentence pointed at.

    The cause is ordering, not the composer. Chapter 2 was written while
    `m2_literature` was still null, so `{references_list}` in the compose prompt
    was empty and there was nothing to cite. The sources arrived later, via
    backfill. And `agent/tools/writing.py` REUSES any chapter that already has
    non-stub prose, so that chapter can never gain citations no matter how many
    times the student asks — only a forced recompose rewrites it.

    Hence a directive rather than a repair: recomposing a chapter costs a model
    call and replaces work the student may have edited, so the agent does it,
    having told them why.
    """
    m2 = (inp.context_store or {}).get("m2_literature") or {}
    sources = m2.get("literature_sources") or m2.get("citation_list") or []
    if not sources:
        return []  # nothing to cite WITH — that is a backfill problem, not this
    stale = [
        name for name, prose in (inp.chapter_prose or {}).items()
        if name in _MUST_CITE
        and len(prose or "") >= _CITABLE_CHAPTER_CHARS
        and not _CITATION_RE.search(prose or "")
    ]
    return stale


def _results_chapter_lacks_tables(inp: DoctorInput) -> list[str]:
    """The results chapter has no tables, on a project whose results DO render.

    Only once `detect_family` recognises the stored block — before that the
    chapter cannot have tables and saying so is noise.
    """
    from orchestrator.tools.results_render import (  # noqa: PLC0415
        detect_family, normalize_analysis_results, render_results_tables)

    m4 = (inp.context_store or {}).get("m4_analysis") or {}
    ar = m4.get("results") or m4.get("analysis_results")
    if not ar:
        return []
    try:
        if not detect_family(normalize_analysis_results(ar)):
            return []
        if not render_results_tables(ar, "vi"):
            return []
    except Exception:  # noqa: BLE001
        return []
    prose = (inp.chapter_prose or {}).get("results") or ""
    if not prose.strip():
        return []
    has_table = bool(re.search(r"(?m)^\|.*\|\s*$", prose)) or "dt-rendered:begin" in prose
    return [] if has_table else ["results"]


def _chapters_need_recompose(inp: DoctorInput) -> list[Finding]:
    """Chapters that are broken in a way only rewriting them fixes.

    One finding rather than three directives, because the repair is the same
    action and the student should be told once.

    This is `repair="recompose"` — the doctor DOES it — after asking failed
    repeatedly. The directive version told the agent to recompose with force;
    it called export_docx with a narrow scope instead and reported five
    chapters rewritten. When the honesty guard started catching that, the
    student was told to say "viết lại toàn bộ các chương, ghi đè bản cũ", said
    exactly that, and still nothing was rewritten — 323 credits for a turn that
    changed nothing. `agent/tools/writing.py` reuses any chapter with non-stub
    prose unless force=True, and nothing passes force=True.
    """
    stub = _refusal_chapter_names(inp)
    uncited = _uncited_chapter_names(inp)
    tableless = _results_chapter_lacks_tables(inp)
    chapters = [c for c in dict.fromkeys(stub + uncited + tableless)]
    if not chapters:
        return []
    why = []
    if stub:
        why.append(f"{', '.join(stub)} chưa có nội dung thật")
    if uncited:
        why.append(f"{', '.join(uncited)} chưa trích dẫn nguồn nào")
    if tableless:
        why.append("chương kết quả chưa chèn bảng")
    return [Finding(
        code="CHAPTERS_NEED_RECOMPOSE",
        detail=f"Đang viết lại: {', '.join(chapters)} ({'; '.join(why)}).",
        repair="recompose",
        payload={"chapters": chapters, "stub": stub,
                 "uncited": uncited, "tableless": tableless},
    )]


def _backfill_available(inp: DoctorInput) -> list[Finding]:
    """Modules that have evidence to infer from and are not COMPLETE."""
    from orchestrator.backfill import reconstructable_modules  # noqa: PLC0415
    from orchestrator.state import ContextStore  # noqa: PLC0415

    cs = inp.context_store or {}
    try:
        store = ContextStore(**{f: cs[f] for f in _MODULE_FIELD.values()
                                if isinstance(cs.get(f), dict)})
        modules = reconstructable_modules(store)
    except Exception:  # noqa: BLE001 — diagnosis must never fail a turn
        return []
    if not modules:
        return []
    return [Finding(
        code="BACKFILL_AVAILABLE",
        detail=f"Có thể dựng lại từ dữ liệu sẵn có: {', '.join(modules)}.",
        repair="directive",
        payload={"modules": modules},
    )]


def diagnose(inp: DoctorInput) -> list[Finding]:
    """Every problem this project has that the doctor knows how to name.

    Ordered by repair value: the deterministic results commit first, because a
    later check's verdict (FALSE_DONE on M4) can be made obsolete by it.
    """
    return (_results_not_in_state(inp)
            + _results_not_renderable(inp)
            + _figures_not_linked(inp)
            + _instrument_not_parsed(inp)
            + _unread_uploads(inp)
            + _false_done(inp)
            + _chapters_need_recompose(inp)
            + _backfill_available(inp))

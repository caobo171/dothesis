"""Gather the doctor's input, apply its repairs, render its directive.

The only half that touches I/O. `orchestrator/doctor.py` decides what is wrong;
this decides what to do about it, and keeps the ledger that stops a repair from
running forever.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from orchestrator.doctor import DoctorInput, Finding, UploadRecord, diagnose

logger = logging.getLogger(__name__)


@dataclass
class DoctorResult:
    """What the turn should do with this pass."""
    repaired: list[str] = field(default_factory=list)   # student-facing lines
    directive: str | None = None                        # injected into the turn


def apply_findings(store, findings: list[Finding], *,
                   gaps_after: dict[str, list[str]] | None = None,
                   new_evidence: bool = False) -> DoctorResult:
    """Run every repair still worth running, and record what happened.

    A repair that runs, changes nothing, and runs again next turn bills
    forever. M4 on the thread that motivated this is the live example: its DoD
    gap is `results is empty`, and if nothing supplies numbers no amount of
    re-running fixes it. So each repair records the gaps before and after; when
    they match, that code is exhausted and converts to something the student is
    TOLD rather than something attempted again.

    New evidence clears exhaustion — the same "new context" signal the backfill
    directive keys on. A student who uploads their results has changed the
    facts, and every previous verdict was reached without them.
    """
    res = DoctorResult()
    try:
        log = store.load_doctor_log()
    except Exception:  # noqa: BLE001 — the doctor must never fail a turn
        logger.exception("doctor: log unreadable")
        log = {}
    if new_evidence:
        log = {}

    asks: list[str] = []
    directives: list[str] = []

    for f in findings:
        entry = log.get(f.code) or {}
        if entry.get("exhausted"):
            asks.append(f.detail)
            continue
        # The same repair, asked for again with the same inputs, already ran and
        # did not fix it. Without this the expensive repairs bill every turn
        # forever: a recompose of four chapters that comes back still uncited
        # presents an identical finding next turn, and would be run again.
        # Cheap deterministic repairs are exempt — re-moving data that is
        # already where it belongs costs nothing and is idempotent.
        if f.repair in ("reparse", "recompose") and entry.get("signature") == _signature(f):
            asks.append(f.detail)
            log[f.code] = {**entry, "exhausted": True}
            continue
        if f.repair == "directive":
            directives.append(_render_directive(f))
            continue
        if f.repair not in ("deterministic", "reparse", "recompose"):
            asks.append(f.detail)
            continue
        try:
            if f.repair == "reparse":
                _reparse(store, f)
            elif f.repair == "recompose":
                _recompose(store, f)
            else:
                _commit(store, f)
        except Exception:  # noqa: BLE001 — one failed repair must not stop the rest
            logger.exception("doctor: repair %s failed", f.code)
            continue
        res.repaired.append(f.detail)
        before = list(f.payload.get("gaps") or [])
        after = list((gaps_after or {}).get(f.payload.get("module") or "", before)) \
            if gaps_after is not None else []
        log[f.code] = {"gaps_before": before, "gaps_after": after,
                       "signature": _signature(f),
                       "exhausted": bool(before) and before == after}

    try:
        store.save_doctor_log(log)
    except Exception:  # noqa: BLE001
        logger.exception("doctor: log unwritable")

    if asks:
        directives.append(
            "[DOCTOR] Những việc sau không tự sửa được — nói thẳng với sinh viên "
            "cần gửi gì, đừng viết lời từ chối vào trong chương: " + " ".join(asks))
    res.directive = "\n".join(directives) or None
    return res


def _signature(f: Finding) -> str:
    """What this repair was asked to fix, as a stable string.

    Chapter names for a recompose, the source filename for a re-extract. Two
    findings with the same signature describe the same broken thing, so the
    second one arriving means the first repair did not work.
    """
    parts = f.payload.get("chapters") or [f.payload.get("filename") or ""]
    return f"{f.code}:{','.join(sorted(str(p) for p in parts))}"


def _with_resolved_figures(store, results: dict) -> dict:
    """Turn workspace-relative figure paths into ones the exporter can open.

    `results_render.localize` does a bare `os.path.isfile`, so a relative path
    is resolved against the SERVER's working directory and silently fails —
    the figure block returns None and the export quietly falls back to a
    rendered table. That is why four correct screenshot paths still produced
    "NO IMAGE".

    `commit_slice` already does this resolution, including containment against
    the project workspace and preferring the durable S3 copy, but only when the
    write names `analysis_results`. The doctor writes the same block under
    `results`, the other M4-owned key, so it never fired. Reusing the same
    helper rather than repeating it: this is the one piece of state that a
    later step OPENS, and its containment check should have exactly one
    implementation.
    """
    figures = (results or {}).get("source_figures")
    if not isinstance(figures, dict) or not figures:
        return results
    try:
        from agent.tools.state_tools import _resolve_source_figures  # noqa: PLC0415
        resolved = _resolve_source_figures(figures, getattr(store, "project_dir", None))
    except Exception:  # noqa: BLE001 — a missing figure degrades to the table
        logger.exception("doctor: figure resolution failed")
        return results
    if not resolved:
        # Every path dropped: storing an empty map would look like "checked,
        # none found" to the next run and stop it retrying.
        return {k: v for k, v in results.items() if k != "source_figures"}
    return {**results, "source_figures": resolved}


def _commit(store, f: Finding) -> None:
    """Apply one deterministic repair. Only moves evidence the student already
    supplied into the state that is supposed to describe it — never writes
    prose, never invents a number."""
    module = f.payload.get("module")
    if f.code in ("RESULTS_NOT_IN_STATE", "FIGURES_NOT_LINKED"):
        store.commit_slice(module or "M4",
                           {"results": _with_resolved_figures(store, f.payload["results"])},
                           reason=f"doctor: kết quả đọc từ {f.payload['filename']}")
        return
    if f.code == "INSTRUMENT_NOT_PARSED":
        # Merged, not replaced: `raw` is the student's uploaded document and
        # stays the source of truth. `items` is the structured reading of it
        # that the panel and the Bảng 3.1 exporter need.
        store.commit_slice(
            module or "M3",
            {"instrument": {**(f.payload.get("instrument") or {}),
                            "items": f.payload["items"]}},
            reason="doctor: tách bảng hỏi đã tải lên thành bảng thang đo")
        return
    if f.code == "FALSE_DONE":
        # A status correction, not a content write: the module keeps everything
        # it has and simply stops claiming to be finished.
        store.commit_slice(module, {}, reason="doctor: chưa đủ điều kiện hoàn thành",
                           status_overrides={module: "in_progress"})
        return
    # UNREAD_UPLOAD has nothing to commit — run_doctor's caller attaches the
    # file to the turn, which is what "reading" it means.


def _reparse(store, f: Finding) -> None:
    """Re-extract a renderable results block from the source document.

    The ONE repair that costs a model call, and the only reason it is allowed:
    the stored block cannot be salvaged by rearranging it. Whether a number is
    Cronbach's Alpha or CR lives in the column header of the original table, and
    the header is gone by the time the results are a dict keyed by path.

    `_infer_analysis_results` is reused rather than reimplemented. It was
    written for exactly this ("storing the paste as a raw string made every
    downstream reader blind to it… render_results_tables bail[s] on a
    non-dict"), it emits the canonical schema detect_family wants, and its
    prompt already forbids computing, rounding or inventing a value. A second
    mapper producing the same schema would drift from it — which is precisely
    how two hypothesis renderers ended up disagreeing.

    Nothing is committed unless the result is actually renderable. A re-extract
    that produces another unreadable block is a no-op, and the loop guard then
    marks the finding exhausted instead of paying for it again next turn.
    """
    from orchestrator.tools.results_render import (  # noqa: PLC0415
        detect_family, normalize_analysis_results)

    from .import_work import _infer_analysis_results  # noqa: PLC0415

    block = _infer_analysis_results(f.payload["text"], "vi")
    if not isinstance(block, dict) or not block:
        raise RuntimeError("re-extraction produced nothing")
    if not detect_family(normalize_analysis_results(block)):
        raise RuntimeError("re-extraction still not renderable")

    # The student's own screenshots, which results_render prefers over any
    # table we can build — "a SmartPLS screenshot is visibly output from the
    # software, and a supervisor reads that as evidence in a way a table of
    # retyped numbers is not". That whole mechanism already existed and was
    # simply never populated, so every export fell through to rendered tables
    # and the twelve extracted images were referenced by nothing.
    #
    # Deterministic: the extractor writes each image's caption directly above
    # the table it belongs to, so the mapping is read out of the document
    # rather than inferred.
    from orchestrator.doctor import parse_source_figures  # noqa: PLC0415
    figures = parse_source_figures(f.payload["text"])
    if figures:
        block = {**block, "source_figures": figures}
    store.commit_slice(
        f.payload.get("module") or "M4", {"results": block},
        reason=f"doctor: đọc lại kết quả từ {f.payload['filename']} để dựng bảng Chương 4")


def _recompose(store, f: Finding) -> None:
    """Rewrite the broken chapters, instead of asking the agent to.

    Asking failed four times. The directive said to recompose with force; the
    agent called export_docx with a narrow scope and reported five chapters
    rewritten. Once the honesty guard caught that, the student was told the
    exact phrasing to force a rewrite, typed it, and still nothing changed —
    323 credits for a turn that moved zero characters. `agent/tools/writing.py`
    reuses any chapter with non-stub prose unless force=True, and no caller
    passes force=True, so "recompose" was never reachable from chat at all.

    compose_all_sections takes the NESTED store and composes exactly the
    chapters named, so this bypasses the reuse guard by never consulting it —
    the chapters handed over are the ones the doctor already proved are broken.
    _weave_verified_blocks runs inside compose_chapter, so Chapter 4 gets its
    tables from the same pass.

    Only chapters that came back with real content are committed: a compose
    that fails must not replace a bad chapter with an empty one.
    """
    from orchestrator.tools.m5_writing import (  # noqa: PLC0415
        _is_stub_prose, compose_all_sections)

    chapters = list(f.payload.get("chapters") or [])
    if not chapters:
        return
    cs = store.load_full_context_store() or {}
    composed = compose_all_sections(cs, chapters=chapters, force_recompose=True) or []

    kept = [s for s in composed
            if (s.get("chapter_name") or "") in chapters
            and not _is_stub_prose(s.get("prose") or "")]
    if not kept:
        raise RuntimeError("recompose produced nothing usable")

    # Commit into `chapters`, the resolver's canonical home. Writing the same
    # prose only to final_sections looks successful but is immediately hidden
    # by the unchanged chapters copy, so the next export and the honesty
    # fingerprint both see zero change.
    existing = dict((cs.get("m5_writing") or {}).get("chapters") or {})
    for s in kept:
        name = s.get("chapter_name") or ""
        previous = existing.get(name) if isinstance(existing.get(name), dict) else {}
        existing[name] = {**previous, **s, "name": name}
    store.commit_slice("M5", {"chapters": existing},
                       reason="doctor: viết lại các chương chưa đạt")


def _render_directive(f: Finding) -> str:
    if f.code == "BACKFILL_AVAILABLE":
        mods = ", ".join(f.payload["modules"])
        return (
            f"[BACKFILL AVAILABLE] These modules are incomplete and CAN be "
            f"reconstructed right now from evidence already in this project: "
            f"{mods}.\n"
            f"A `locked` status on the [PROJECT STATE] line above does NOT mean "
            f"these are off limits — it means nobody has filled them yet, and "
            f"that is what this tool is for.\n"
            f"Call `backfill_upstream_modules` THIS TURN before you write, "
            f"recompose or export any chapter. Do not narrow it to the module "
            f"the student happens to be asking about.\n"
            f"Afterwards tell them in one line what was filled in."
        )
    if f.code == "CHAPTERS_WITHOUT_CITATIONS":
        chapters = ", ".join(f.payload["chapters"])
        return (
            f"[UNCITED CHAPTERS] {chapters} contain no citations at all, while "
            f"this project has {f.payload['source_count']} verified sources. "
            f"They were written before the sources existed.\n"
            f"Recompose those chapters with force=True this turn — WITHOUT "
            f"force they are reused verbatim (agent/tools/writing.py) and can "
            f"never gain citations, no matter how many times the student asks. "
            f"Re-exporting alone does not fix this.\n"
            f"Then export again, and tell the student which chapters you "
            f"rewrote and why."
        )
    if f.code == "REFUSAL_CHAPTER":
        return (
            f"[EMPTY CHAPTER] {f.detail} Recompose it this turn. If it still "
            f"cannot be written, say which chapter and what is missing — never "
            f"write the refusal into the chapter itself."
        )
    return f"[DOCTOR] {f.detail}"


def gather(db, project_id, store, workspace) -> DoctorInput:
    """Assemble the doctor's input from Postgres and the workspace mirror."""
    from pathlib import Path  # noqa: PLC0415

    from sqlalchemy import select  # noqa: PLC0415

    from .models import Message, PaperUpload, Thread  # noqa: PLC0415

    attached: set[str] = set()
    for (tcj,) in db.execute(
        select(Message.tool_calls_json)
        .join(Thread, Thread.id == Message.thread_id)
        .where(Thread.project_id == project_id)
    ).all():
        for chip in ((tcj or {}).get("attachments") or []):
            if chip.get("upload_id"):
                attached.add(str(chip["upload_id"]))

    ws = Path(workspace)
    uploads: list[UploadRecord] = []
    for row in db.execute(
        select(PaperUpload).where(PaperUpload.project_id == project_id)
    ).scalars().all():
        # The upload route caches extracted text in a sidecar next to the
        # bytes. That extraction is already paid for — re-running vision over
        # a screenshot docx would charge the student twice to learn the same
        # numbers.
        sidecar = ws / "uploads" / f"{row.filename}.txt"
        text = None
        try:
            if sidecar.exists():
                text = sidecar.read_text(encoding="utf-8") or None
        except Exception:  # noqa: BLE001 — an unreadable sidecar is not an error
            logger.warning("doctor: unreadable sidecar %s", sidecar)
        uploads.append(UploadRecord(
            upload_id=str(row.id), filename=row.filename,
            sidecar_text=text, ever_attached=str(row.id) in attached))

    try:
        cs = store.load_full_context_store() or {}
    except Exception:  # noqa: BLE001
        logger.exception("doctor: context store unreadable")
        cs = {}

    from orchestrator.tools.m5_writing import chapter_prose  # noqa: PLC0415
    prose = chapter_prose(cs.get("m5_writing") or {})

    # Per-module slices pass through unflattened — the shape the checks want.
    return DoctorInput(context_store=cs, uploads=uploads, chapter_prose=prose)


def run_doctor(db, project_id, store, workspace, *,
               new_evidence: bool = False) -> DoctorResult:
    """One diagnosis + repair pass. Never raises.

    A doctor that breaks turns is worse than no doctor: the student loses the
    answer they actually asked for, for the sake of a repair they did not.
    """
    try:
        findings = diagnose(gather(db, project_id, store, workspace))
    except Exception:  # noqa: BLE001
        logger.exception("doctor: diagnosis failed")
        return DoctorResult()
    if not findings:
        return DoctorResult()
    try:
        return apply_findings(store, findings, new_evidence=new_evidence)
    except Exception:  # noqa: BLE001
        logger.exception("doctor: repair pass failed")
        return DoctorResult()

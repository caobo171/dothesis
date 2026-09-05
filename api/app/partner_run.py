"""Partner report = a headless client of the deep agent (convergence spec §3).

The old partner_report_service was a THIRD generation engine: inline prompts,
a private compose loop, zero tools/skills/state. This module replaces it with
the same brain every surface runs: create a system-owned project row, seed the
store through commit_slice (the ONLY write path), run the deep agent headless
in a Job subprocess, compose the requested report shape through the SHARED
compose/export path, and presign from the shared exports rows.

What partner gains the day this lands: all ~20 tools, all 8 skills, threshold
checks, questionnaire audit, rubric review, preflight — everything it lacked.
"""
from __future__ import annotations

import logging
import os
import re  # used by the moved pdf_looks_like_analysis
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.state import SLICE_OWNERSHIP
# Module-level (not lazy) so tests can monkeypatch partner_run.compose_sections /
# partner_run.run_export; m5_writing defers its own heavy LLM deps internally.
from orchestrator.tools.compose_export import compose_sections
from orchestrator.tools.m5_writing import (
    M5_CHAPTER_ORDER,
    assess_export_readiness,
    run_export,
)

from .models import User
from .pdf_extract import extract_pdf_text

logger = logging.getLogger(__name__)

# Subset composed for the lighter "analysis_report" depth (single copy now —
# the old _CHAPTER_ORDER clone is gone; the canonical order is M5_CHAPTER_ORDER).
# The chapters an analysis-only order buys. `discussion` is gone with the
# five-chapter collapse — the discussion of findings is written inside
# Chapter 5 (Kết luận và Kiến nghị), not as a chapter of its own.
ANALYSIS_CHAPTERS = ["intro", "results", "conclusion"]

PARTNER_USER_EMAIL = "partner-system@dothesis.internal"


class ReportError(Exception):
    """Raised with a stable `code` the router maps to an HTTP response."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def mint_partner_token() -> str:
    """Mint the progress-polling token SERVER-SIDE.

    Task 9 made `jobs.partner_token` UNIQUE, but the token was still whatever
    the CALLER put in the `progress_token` form field — and partner auth is one
    globally shared secret, so there is no partner identity to scope tokens by.
    Two callers holding that same secret and picking the same string (a fixed
    "job-1", a colliding client-side uuid, a retry replaying an old value) would
    now collide at INSERT and 500. Minting here removes the caller from the
    equation entirely: uniqueness is guaranteed by the generator, not hoped for.

    It doubles as the capability to READ that run's progress, so it must also be
    unguessable — token_urlsafe(32) is 256 bits of CSPRNG, not a uuid4 (which
    leaks version/variant bits and is routinely treated as non-secret).
    """
    return secrets.token_urlsafe(32)


def resolve_chapters(depth: str, chapters: list[str] | None) -> list[str]:
    """Chapter selection precedence unchanged from the old service: explicit
    `chapters` subset wins over `depth`; unknown keys are ignored; an
    empty-after-filter list and an unknown depth are clean 422 codes."""
    if chapters:
        keys = [c for c in chapters if c in set(M5_CHAPTER_ORDER)]
        if not keys:
            raise ReportError("bad_chapters",
                              f"chapters must be a subset of {M5_CHAPTER_ORDER}")
        return keys
    if depth == "full_thesis":
        return list(M5_CHAPTER_ORDER)
    if depth == "analysis_report":
        return list(ANALYSIS_CHAPTERS)
    raise ReportError("bad_depth",
                      "depth must be one of ['analysis_report', 'full_thesis']")


def required_modules_for(chapters: list[str]) -> frozenset[str]:
    """The modules a headless run must finish to serve THIS chapter request.

    Fed to RunProfile.required_modules so a partner asking for 4 chapters isn't
    forced to drive a full M1-M5 run — a seeded project's M2 is usually empty
    (payloads rarely carry literature), and demanding a literature review before
    an analysis_report meant the partner got a hard error because work they never
    requested stalled.

    The chapter -> owning-module map is REUSED from the agent's advisor-feedback
    router (`agent.tools.state_tools`) rather than restated here: two maps of the
    same fact drift, and the disagreement would be invisible until a run ended in
    the wrong place. M1 owns no chapter, so it is never in the required set — its
    intake framing is a partner-supplied INPUT (seed_partner_store writes it), not
    work the run has to produce, and the M1 data the chapters actually need is
    already gated by m5_writing.assess_export_readiness at compose time.
    """
    from agent.tools.state_tools import chapter_to_module  # noqa: PLC0415
    return frozenset(chapter_to_module(c) for c in chapters)


def ensure_partner_user(db: Session) -> User:
    """Find-or-create the system user that owns partner projects.

    Partner runs have no end-user relationship (the partner owns billing), but
    Project.user_id is NOT NULL and the whole app authorizes through ownership
    — one well-known system row keeps every query intact, and its permanent
    0-credit balance makes job_runner._charge_auto_thesis_run a guaranteed no-op
    (charge = min(cost, credit or 0) = 0).

    password_hash is a bcrypt-shaped impossibility, not a hash of anything: no
    password can verify against it, so the row cannot be logged into even though
    it is a normal `users` row to every other query.
    """
    u = db.scalar(select(User).where(User.email == PARTNER_USER_EMAIL))
    if u is None:
        u = User(email=PARTNER_USER_EMAIL, username="partner-system",
                 password_hash="!disabled", email_verified=True, credit=0)
        db.add(u)
        db.flush()
    return u


def seed_partner_store(
    store,
    *,
    analysis_text: str,
    m1: dict | None = None,
    m2: dict | None = None,
    m3: dict | None = None,
    title: str | None = None,
    notes: str | None = None,
    language: str = "en",
) -> None:
    """Seed the project store from the partner payload — through commit_slice
    only, filtered to OWNED keys (an unowned key would either raise or, worse,
    silently never reach prod rows). Caller-provided modules are used verbatim;
    missing ones stay empty for the agent to reconstruct (backfill tool).

    Seed order M1 -> M4 matters: commit_slice flags STARTED downstream modules
    needs_review, and seeding forward means every commit's downstream is still
    locked — no spurious review flags on a brand-new project."""
    m1 = dict(m1 or {})
    if (title or "").strip():
        # A caller-typed title always wins over anything inferred later.
        m1["research_title"] = title.strip()
    m1.setdefault("language", language)
    if (notes or "").strip():
        m1.setdefault("user_context", notes.strip())
    _commit_owned(store, "M1", m1, "partner payload: topic framing seed")
    if m2:
        _commit_owned(store, "M2", m2, "partner payload: literature seed")
    if m3:
        _commit_owned(store, "M3", m3, "partner payload: design seed")
    store.commit_slice("M4", {"analysis_results": analysis_text},
                       "partner payload: uploaded analysis output")


def _commit_owned(store, module: str, payload: dict, reason: str) -> None:
    """Commit a payload's OWNED keys and log the rest.

    The filter is not optional — commit_slice enforces ownership, and a key the
    module doesn't own would either raise or land somewhere DbProjectStateStore
    never persists (project_db_store_persistence_gap). But dropping silently is
    how a partner sending `research_gaps` under m1 (it is M2-owned) gets a report
    that ignores the gaps they paid to supply, with nothing anywhere saying why.
    One WARNING per module names the caller, the module and the keys, so the
    answer is in the logs the first time it is asked. Deliberately not a 422: the
    envelope is theirs to get wrong, but a stray key has never been fatal here and
    making it so now would break callers over a field they were free to send.
    """
    owned = set(SLICE_OWNERSHIP[module])
    writes = {k: v for k, v in payload.items() if k in owned}
    dropped = sorted(set(payload) - owned)
    if dropped:
        logger.warning("partner_report: dropping %s key(s) not owned by %s: %s",
                       len(dropped), module, ", ".join(dropped))
    if writes:
        store.commit_slice(module, writes, reason)


def run_partner_export(store, project_id, params: dict) -> dict:
    """Compose the REQUESTED report shape from the finished run's store and
    export through the shared renderer.

    The run itself already produced a full-thesis export via the M5 done-hook
    (DbProjectStateStore._auto_export_m5) — that stays in the project's Exports
    as a bonus. This renders the partner's requested subset/merged shape:
    chapters/depth are presentation choices, not a pipeline fork (spec §3)."""
    chapters = resolve_chapters(params.get("depth") or "analysis_report",
                                params.get("chapters"))
    language = params.get("language") or "en"
    full_cs = store.load_full_context_store()

    # THE readiness gate — restored from the deleted service, which returned a
    # `needs_data` error instead of composing. Without it compose_sections falls
    # through to _fallback_section for every chapter it cannot write, so a
    # payload that used to be refused for a validation fee instead buys a FULL
    # agent run and gets a fallback-padded report at full price. Billing for a
    # hollow report is worse than failing, so this fails.
    #
    # EXPORT-time, not submit-time, and deliberately so. The point of the
    # migration is that the agent BACKFILLS what the payload lacks (it has all
    # ~20 tools now), so gating the raw payload would refuse work the new engine
    # can genuinely do — a regression in the opposite direction. The old engine
    # gated here too: after its research phase had had its chance, never on the
    # inbound payload. The cheap pre-run refusals that don't depend on the run
    # (unreadable file, no analysis data for a Results chapter) still fire in the
    # router before a single row is created, so the fail-fast property survives
    # for the cases where it is actually decidable up front.
    #
    # ONE gate, reused: assess_export_readiness is the same function chat exports
    # through (agent/tools/writing.py). Its `chapters` scoping is already
    # required_modules-aware by construction — a chapter-specific check is owned
    # by exactly the module required_modules_for derives from that chapter — so
    # there is no second gate and no second chapter->module map to drift.
    missing = assess_export_readiness(full_cs, chapters)
    if missing:
        raise ReportError("needs_data", "missing required data: " + "; ".join(missing))

    references = (full_cs.get("m2_literature") or {}).get("literature_sources") or None
    sections = compose_sections(full_cs, chapters, language, references=references)
    if not sections:
        raise ReportError("compose_failed", "the writing engine produced no sections")
    report_title = (full_cs.get("m1_topic") or {}).get("research_title") or None
    artifacts = run_export(sections, str(project_id),
                           references=references, language=language,
                           title=report_title)
    store.persist_export_artifacts(artifacts, scope="partner")
    # Committee-readiness gate summary (roadmap #12) rides the partner export as
    # an advisory field — deterministic + offline. A certificate failure must
    # NEVER fail a paid export, so it's fully fail-open.
    gate = None
    try:
        from quality.certificate import build_certificate, gate_summary  # noqa: PLC0415
        gate = gate_summary(build_certificate(full_cs, project_id=str(project_id)))
    except Exception:
        logger.exception("run_partner_export: gate summary failed (advisory)")
    return {
        "sections": [s["title"] for s in sections],
        # No merge to reconcile anymore — `conclusion` is the real, canonical
        # final chapter (five-chapter collapse), so `chapters` is already what
        # got composed. The old comment here explained a POST-merge/PRE-merge
        # split; that split doesn't exist once there's nothing to merge.
        "chapters": chapters,
        "artifact_keys": {a.get("kind"): a.get("s3_key")
                          for a in artifacts if a.get("s3_key")},
        "gate_summary": gate,
    }


def _presign(s3, s3_key: str, *, expires_in: int = 3600) -> str:
    """Same raw-key presign convention as the exports router — M5 export
    uploads with Bucket=S3_BUCKET and NO settings prefix (see
    orchestrator/tools/m5_writing._upload_to_s3)."""
    bucket = os.environ.get("S3_BUCKET") or os.environ["AWS_S3_BUCKET"]
    return s3.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": s3_key},
        ExpiresIn=expires_in,
    )


# --- Ingest helpers (moved verbatim from partner_report_service) --------------


# Ingest reads DOCX through agent.docx_extract — the SAME walk the uploads
# router and the chat attachment path use. That sharing is deliberate: the two
# implementations had already drifted once (uploads read tables, chat did not),
# and a second copy here would have drifted again the moment either learned
# something new — as this one just did, by learning to read pasted screenshots.


def _extract_text(file_bytes: bytes, filename: str | None) -> tuple[str, int]:
    """Extract analysis text from a PDF or DOCX. Returns (text, page_count).

    DOCX is detected by extension or the zip magic (PK). Everything else goes
    through the PDF extractor. Table cell text is flattened into pipe rows so the
    statistics inside result tables survive, and embedded images (pasted
    SmartPLS/SPSS screenshots) are vision-transcribed so their numbers survive too.
    """
    name = (filename or "").lower()
    if name.endswith(".docx") or file_bytes[:2] == b"PK":
        from agent.docx_extract import extract_docx_text  # noqa: PLC0415 — heavy/lazy

        return (extract_docx_text(file_bytes), 0)
    # Partner ingest: the whole report is written from this file, so a scanned
    # or screenshot-built PDF has to be transcribed rather than dropped.
    return extract_pdf_text(file_bytes, ocr_if_hollow=True)


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


def pdf_looks_like_analysis(text: str) -> bool:
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

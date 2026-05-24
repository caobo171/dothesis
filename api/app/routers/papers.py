import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..credit_ledger import InsufficientCredit, debit
from ..db import db_session
from ..deps import current_user
from ..job_runner import spawn_job
from ..models import CreditTransaction, Job, Paper, User
from ..pricing import paper_cost, resolve_model
from ..quotas import QuotaError, check_can_start_job
from ..s3 import get_s3_from_settings
from ..settings import get_settings

router = APIRouter(prefix="/papers", tags=["papers"])

ALLOWED_LEVELS = {"research", "bachelor", "master", "phd"}
ALLOWED_STYLES = {"apa", "mla", "chicago", "ieee", "harvard"}
ALLOWED_TIERS = {"standard", "premium"}


class Sources(BaseModel):
    crossref: bool = True
    openalex: bool = True
    semanticscholar: bool = True
    arxiv: bool = True
    jstor: bool = False
    googleScholar: bool = False


class PaperCreate(BaseModel):
    topic: str = Field(min_length=4, max_length=500)
    research_question: str | None = Field(default=None, max_length=2000)
    academic_level: str
    language: str = Field(min_length=2, max_length=16)
    model_tier: str = Field(default="standard")
    citation_style: str
    sources: Sources = Sources()
    tone: str | None = None


class PaperOut(BaseModel):
    id: str
    title: str
    level: str
    status: str
    progress: float
    updated_at: str
    discipline: str | None = None


class CreateResp(BaseModel):
    paper_id: str
    job_id: str


def _level_to_label(level: str) -> str:
    return {
        "research": "Research paper",
        "bachelor": "Bachelor's thesis",
        "master": "Master's thesis",
        "phd": "PhD dissertation",
    }.get(level, level)


def _paper_to_out(p: Paper, latest: Job | None) -> PaperOut:
    return PaperOut(
        id=str(p.id),
        title=p.topic,
        level=_level_to_label(p.academic_level),
        status=p.status,
        progress=latest.progress if latest else 0.0,
        updated_at=p.updated_at.isoformat() if p.updated_at else "",
    )


@router.get("", response_model=list[PaperOut])
def list_papers(user: User = Depends(current_user), db: Session = Depends(db_session)):
    rows = db.scalars(select(Paper).where(Paper.user_id == user.id).order_by(desc(Paper.updated_at))).all()
    out = []
    for p in rows:
        latest = None
        if p.latest_job_id:
            latest = db.get(Job, p.latest_job_id)
        out.append(_paper_to_out(p, latest))
    return out


@router.post("", response_model=CreateResp, status_code=201)
async def create_paper(body: PaperCreate, user: User = Depends(current_user), db: Session = Depends(db_session)):
    if body.academic_level not in ALLOWED_LEVELS:
        raise HTTPException(422, detail={"error": {"code": "bad_level", "message": "invalid academic_level"}})
    if body.citation_style not in ALLOWED_STYLES:
        raise HTTPException(422, detail={"error": {"code": "bad_style", "message": "invalid citation_style"}})
    if body.model_tier not in ALLOWED_TIERS:
        raise HTTPException(422, detail={"error": {"code": "bad_tier", "message": "invalid model_tier"}})

    try:
        check_can_start_job(db, user.id)
    except QuotaError as e:
        status = 409 if e.code == "already_running" else 429
        raise HTTPException(status, detail={"error": {"code": e.code, "message": e.message}})

    cost = paper_cost(body.academic_level, body.model_tier)
    try:
        debit(db, user, delta=cost, reason="paper_run", ref_type="paper", ref_id=None)
    except InsufficientCredit as e:
        raise HTTPException(
            402,
            detail={"error": {"code": "insufficient_credit", "required": e.required, "balance": e.balance}},
        )

    paper = Paper(
        user_id=user.id,
        topic=body.topic,
        research_question=body.research_question,
        academic_level=body.academic_level,
        language=body.language,
        citation_style=body.citation_style,
        tone=body.tone,
        model=resolve_model(body.model_tier),
        model_tier=body.model_tier,
        sources_json=body.sources.model_dump(),
        status="running",
    )
    db.add(paper)
    db.flush()

    # Backfill paper_id into the ledger row we just wrote
    last_tx = db.scalars(
        select(CreditTransaction)
        .where(CreditTransaction.user_id == user.id, CreditTransaction.ref_id.is_(None))
        .order_by(CreditTransaction.id.desc()).limit(1)
    ).one()
    last_tx.ref_id = paper.id
    db.flush()

    job = Job(paper_id=paper.id, status="queued")
    db.add(job)
    db.flush()

    paper.latest_job_id = job.id
    db.commit()

    brief = {
        "topic": body.topic,
        "research_question": body.research_question,
        "academic_level": body.academic_level,
        "language": body.language,
        "citation_style": body.citation_style,
        "model": resolve_model(body.model_tier),
        "tone": body.tone,
        "sources": body.sources.model_dump(),
    }
    try:
        spawn_job(db, job, brief)
    except Exception as e:
        # Don't leave the user permanently quota-blocked if subprocess launch fails.
        job.status = "failed"
        job.error_text = f"failed to launch engine: {e}"
        paper.status = "failed"
        db.commit()
        raise HTTPException(500, detail={"error": {"code": "spawn_failed", "message": str(e)}})

    return CreateResp(paper_id=str(paper.id), job_id=str(job.id))


@router.get("/{paper_id}")
def get_paper(paper_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(db_session)):
    p = db.get(Paper, paper_id)
    if not p or p.user_id != user.id:
        raise HTTPException(404, detail={"error": {"code": "not_found", "message": "paper not found"}})
    latest = db.get(Job, p.latest_job_id) if p.latest_job_id else None
    latest_out = None
    if latest:
        latest_out = {
            "id": str(latest.id),
            "status": latest.status,
            "phase": latest.phase,
            "progress": latest.progress,
            "completed_phase": latest.completed_phase,
            "has_checkpoint": latest.checkpoint_json is not None,
        }
    return {"paper": _paper_to_out(p, latest).model_dump(), "latest_job": latest_out}


@router.post("/{paper_id}/resume", status_code=202)
async def resume_paper(paper_id: uuid.UUID,
                       user: User = Depends(current_user),
                       db: Session = Depends(db_session)):
    """Spawn a new job that picks up from the latest job's checkpoint."""
    import shutil
    from pathlib import Path

    p = db.get(Paper, paper_id)
    if not p or p.user_id != user.id:
        raise HTTPException(404, detail={"error": {"code": "not_found", "message": "paper not found"}})
    if not p.latest_job_id:
        raise HTTPException(409, detail={"error": {"code": "no_job", "message": "no prior job to resume"}})
    last_job = db.get(Job, p.latest_job_id)
    if not last_job:
        raise HTTPException(409, detail={"error": {"code": "no_job", "message": "prior job missing"}})
    if last_job.status not in {"failed", "canceled"}:
        raise HTTPException(409, detail={"error": {"code": "not_resumable",
                                                    "message": f"job is {last_job.status}; cannot resume"}})
    if not last_job.checkpoint_json:
        raise HTTPException(409, detail={"error": {"code": "no_checkpoint",
                                                    "message": "no checkpoint was saved for this job"}})

    # Quota: same rules as fresh submit.
    try:
        check_can_start_job(db, user.id)
    except QuotaError as e:
        status_code = 409 if e.code == "already_running" else 429
        raise HTTPException(status_code, detail={"error": {"code": e.code, "message": e.message}})

    # New job row, same paper.
    new_job = Job(paper_id=p.id, status="queued")
    db.add(new_job)
    db.flush()
    p.latest_job_id = new_job.id
    p.status = "running"
    db.commit()

    # Write the checkpoint into the new workdir; copy bibliography if the old workdir still has it.
    settings = get_settings()
    new_workdir = settings.job_workdir_root / str(new_job.id)
    new_workdir.mkdir(parents=True, exist_ok=True)
    new_checkpoint = new_workdir / "checkpoint.json"
    new_checkpoint.write_text(json.dumps(last_job.checkpoint_json), encoding="utf-8")
    if last_job.workdir:
        old_workdir = Path(last_job.workdir)
        for fname in ("bibliography.json",):
            src = old_workdir / fname
            if src.exists():
                shutil.copy(src, new_workdir / fname)

    # Reconstruct the brief from the checkpoint's preserved user inputs.
    cp = last_job.checkpoint_json
    brief = {
        "topic": cp.get("topic") or p.topic,
        "research_question": p.research_question,
        "academic_level": cp.get("academic_level") or p.academic_level,
        "language": cp.get("language") or p.language,
        "citation_style": cp.get("citation_style") or p.citation_style,
        "model": p.model,
        "tone": p.tone,
        "sources": p.sources_json or {},
    }

    try:
        spawn_job(db, new_job, brief, resume_from=str(new_checkpoint))
    except Exception as e:
        new_job.status = "failed"
        new_job.error_text = f"failed to launch engine: {e}"
        p.status = "failed"
        db.commit()
        raise HTTPException(500, detail={"error": {"code": "spawn_failed", "message": str(e)}})

    return {"paper_id": str(p.id), "job_id": str(new_job.id),
            "resumed_from_phase": last_job.completed_phase}


def _job_key_root(paper: Paper, job_id: uuid.UUID) -> str:
    return f"users/{paper.user_id}/papers/{paper.id}/jobs/{job_id}"


def _require_done_paper(db: Session, user: User, paper_id: uuid.UUID) -> tuple[Paper, uuid.UUID]:
    p = db.get(Paper, paper_id)
    if not p or p.user_id != user.id:
        raise HTTPException(404, detail={"error": {"code": "not_found", "message": "paper not found"}})
    if not p.latest_job_id:
        raise HTTPException(404, detail={"error": {"code": "no_job", "message": "no job for paper"}})
    job = db.get(Job, p.latest_job_id)
    if not job or job.status != "done":
        raise HTTPException(409, detail={"error": {"code": "not_ready", "message": "draft not finished"}})
    return p, job.id


# Intermediate engine artifacts that live in exports/ but are NOT the final draft.
# When falling back to a prefix listing, skip these so the API doesn't surface
# the abstract or the pre-abstract intermediate as if it were the full paper.
_EXPORT_INTERMEDIATES = {
    "16_abstract_generated.md",
    "intermediate_draft.md",
}


def _list_exports(s3, key_root: str) -> list[dict]:
    prefix = s3._full_key(f"{key_root}/exports/")
    resp = s3._client.list_objects_v2(Bucket=s3.bucket, Prefix=prefix)
    return resp.get("Contents", []) or []


def _fetch_export_bytes(s3, key_root: str, canonical_relpath: str, ext: str) -> bytes | None:
    """Try the canonical key first; if missing, fall back to listing the exports/ prefix.

    Older engine runs wrote {slug}.{ext} instead of draft.{ext}. The fallback prefers
    the largest matching file and skips known intermediate artifacts (the abstract
    fragment, pre-citation intermediate), so we always return the actual final draft.
    """
    try:
        full = s3._full_key(f"{key_root}/{canonical_relpath}")
        return s3._client.get_object(Bucket=s3.bucket, Key=full)["Body"].read()
    except s3._client.exceptions.NoSuchKey:
        pass
    suffix = "." + ext.lower()
    candidates = []
    for item in _list_exports(s3, key_root):
        key = item["Key"]
        name = key.rsplit("/", 1)[-1].lower()
        if not name.endswith(suffix):
            continue
        if name in _EXPORT_INTERMEDIATES:
            continue
        candidates.append((item.get("Size", 0), key))
    if not candidates:
        return None
    # Largest wins — the final draft is always longer than any intermediate fragment.
    candidates.sort(reverse=True)
    pick = candidates[0][1]
    return s3._client.get_object(Bucket=s3.bucket, Key=pick)["Body"].read()


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Extract a leading YAML frontmatter block. Returns (meta, body).

    Frontmatter is a `---\n...\n---\n` block at the very top of the file. We
    parse it line-by-line as `key: "value"` pairs (which is what the engine
    emits) rather than pulling in PyYAML for one field-per-line block.
    """
    if not text.startswith("---"):
        return {}, text
    lines = text.split("\n")
    if len(lines) < 2:
        return {}, text
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}, text
    meta: dict = {}
    for raw_line in lines[1:end_idx]:
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, _, val = line.partition(":")
        val = val.strip()
        if val.startswith('"') and val.endswith('"'):
            val = val[1:-1]
        meta[key.strip()] = val
    body = "\n".join(lines[end_idx + 1:]).lstrip("\n")
    return meta, body


@router.get("/{paper_id}/draft")
def get_draft(paper_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(db_session)):
    p, job_id = _require_done_paper(db, user, paper_id)
    settings = get_settings()
    s3 = get_s3_from_settings(settings)
    raw = _fetch_export_bytes(s3, _job_key_root(p, job_id), "exports/draft.md", "md")
    if raw is None:
        raise HTTPException(
            404,
            detail={"error": {"code": "draft_missing", "message": "Markdown draft not found in storage — the engine may have crashed before upload. Try re-running the paper."}},
        )
    full_text = raw.decode("utf-8")
    meta, body = _split_frontmatter(full_text)
    chapters = _chapters_from_markdown(body)
    return {
        "meta": meta,
        "markdown": body,
        "html": _md_to_html(body),
        "word_count": sum(len(c.get("title", "").split()) for c in chapters) + len(body.split()),
        "chapters": chapters,
    }


def _chapters_from_markdown(md: str) -> list[dict]:
    out: list[dict] = []
    n = 0
    for line in md.splitlines():
        if line.startswith("## ") and not line.startswith("### "):
            n += 1
            title = line[3:].strip()
            out.append({"num": str(n), "title": title, "words": 0})
    return out


def _md_to_html(md: str) -> str:
    try:
        import markdown
        return markdown.markdown(md, extensions=["fenced_code", "tables"])
    except ImportError:
        return "<pre>" + md.replace("<", "&lt;") + "</pre>"


@router.get("/{paper_id}/citations")
def get_citations(paper_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(db_session)):
    p, job_id = _require_done_paper(db, user, paper_id)
    s3 = get_s3_from_settings(get_settings())
    key = s3._full_key(f"{_job_key_root(p, job_id)}/research/bibliography.json")
    try:
        body = s3._client.get_object(Bucket=s3.bucket, Key=key)["Body"].read().decode("utf-8")
    except s3._client.exceptions.NoSuchKey:
        raise HTTPException(
            404,
            detail={"error": {"code": "bibliography_missing", "message": "Bibliography not found in storage — the engine may have crashed before upload."}},
        )
    raw = json.loads(body) if body else []
    out = []
    for e in raw:
        if isinstance(e, str):
            # Engine wrote a list of formatted citation strings — surface them as title-only entries.
            out.append({
                "key": "", "title": e, "authors": "", "year": None,
                "doi": None, "source": "CrossRef", "venue": None, "verified": True,
            })
            continue
        if not isinstance(e, dict):
            continue
        authors = e.get("authors", "")
        if isinstance(authors, list):
            authors = ", ".join(str(a) for a in authors)
        out.append({
            "key": e.get("key") or e.get("id") or "",
            "title": e.get("title", ""),
            "authors": authors,
            "year": e.get("year"),
            "doi": e.get("doi"),
            "source": e.get("source", "CrossRef"),
            "venue": e.get("venue") or e.get("journal"),
            "verified": bool(e.get("verified", True)),
        })
    return out


EXPORT_FORMATS = {
    "pdf": ("exports/draft.pdf", "application/pdf"),
    "docx": ("exports/draft.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "tex": ("exports/draft.tex", "application/x-tex"),
    "md": ("exports/draft.md", "text/markdown"),
    "zip": ("exports/bundle.zip", "application/zip"),
}


@router.get("/{paper_id}/exports")
def list_exports(paper_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(db_session)):
    p, job_id = _require_done_paper(db, user, paper_id)
    s3 = get_s3_from_settings(get_settings())
    key_root = _job_key_root(p, job_id)
    # For each format, prefer the canonical path. If it isn't there (older runs)
    # fall back to picking the largest non-intermediate file with that extension.
    out = []
    listing = _list_exports(s3, key_root)
    for fmt, (rel, _ct) in EXPORT_FORMATS.items():
        canonical_meta = s3.head_object(f"{key_root}/{rel}")
        if canonical_meta:
            out.append({"format": fmt, "size": canonical_meta["ContentLength"],
                         "generated_at": canonical_meta["LastModified"].isoformat()})
            continue
        # Fallback: find a slug-named alternative
        suffix = "." + fmt.lower()
        cands = []
        for item in listing:
            name = item["Key"].rsplit("/", 1)[-1].lower()
            if not name.endswith(suffix) or name in _EXPORT_INTERMEDIATES:
                continue
            cands.append((item.get("Size", 0), item))
        if cands:
            cands.sort(reverse=True)
            item = cands[0][1]
            out.append({"format": fmt, "size": item["Size"],
                         "generated_at": item["LastModified"].isoformat()})
    return out


@router.get("/{paper_id}/exports/{fmt}")
def download_export(paper_id: uuid.UUID, fmt: str,
                     user: User = Depends(current_user), db: Session = Depends(db_session)):
    if fmt not in EXPORT_FORMATS:
        raise HTTPException(404, detail={"error": {"code": "unknown_format", "message": fmt}})
    p, job_id = _require_done_paper(db, user, paper_id)
    s3 = get_s3_from_settings(get_settings())
    rel, _ct = EXPORT_FORMATS[fmt]
    key_root = _job_key_root(p, job_id)

    # Prefer the canonical path. If absent (older runs), find the slug-named alternative.
    canonical_full = s3._full_key(f"{key_root}/{rel}")
    target_key = None
    if s3.head_object(f"{key_root}/{rel}"):
        target_key = canonical_full
    else:
        suffix = "." + fmt.lower()
        cands = []
        for item in _list_exports(s3, key_root):
            name = item["Key"].rsplit("/", 1)[-1].lower()
            if name.endswith(suffix) and name not in _EXPORT_INTERMEDIATES:
                cands.append((item.get("Size", 0), item["Key"]))
        if cands:
            cands.sort(reverse=True)
            target_key = cands[0][1]

    if not target_key:
        raise HTTPException(
            404,
            detail={"error": {"code": "export_missing", "message": f"No {fmt} export found for this paper."}},
        )

    # presigned_get expects a relative key (it prefixes); pass the raw key by going through the client.
    url = s3._client.generate_presigned_url(
        "get_object",
        Params={"Bucket": s3.bucket, "Key": target_key},
        ExpiresIn=300,
    )
    return RedirectResponse(url, status_code=302)

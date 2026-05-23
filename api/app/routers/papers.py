import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..db import db_session
from ..deps import current_user
from ..job_runner import spawn_job
from ..models import Job, Paper, User
from ..quotas import QuotaError, check_can_start_job
from ..s3 import get_s3_from_settings
from ..settings import get_settings

router = APIRouter(prefix="/papers", tags=["papers"])

ALLOWED_LEVELS = {"research", "bachelor", "master", "phd"}
ALLOWED_STYLES = {"apa", "mla", "chicago", "ieee", "harvard"}
ALLOWED_MODELS = {"gemini-flash", "claude-sonnet", "claude-opus", "gpt-5"}


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
    model: str
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
    if body.model not in ALLOWED_MODELS:
        raise HTTPException(422, detail={"error": {"code": "bad_model", "message": "invalid model"}})

    try:
        check_can_start_job(db, user.id)
    except QuotaError as e:
        status = 409 if e.code == "already_running" else 429
        raise HTTPException(status, detail={"error": {"code": e.code, "message": e.message}})

    paper = Paper(
        user_id=user.id,
        topic=body.topic,
        research_question=body.research_question,
        academic_level=body.academic_level,
        language=body.language,
        citation_style=body.citation_style,
        tone=body.tone,
        model=body.model,
        sources_json=body.sources.model_dump(),
        status="running",
    )
    db.add(paper)
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
        "model": body.model,
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
    return {"paper": _paper_to_out(p, latest).model_dump(),
            "latest_job": {"id": str(latest.id), "status": latest.status, "phase": latest.phase, "progress": latest.progress} if latest else None}


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


@router.get("/{paper_id}/draft")
def get_draft(paper_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(db_session)):
    p, job_id = _require_done_paper(db, user, paper_id)
    settings = get_settings()
    s3 = get_s3_from_settings(settings)
    md_key = f"{_job_key_root(p, job_id)}/exports/draft.md"
    body = s3._client.get_object(Bucket=s3.bucket, Key=s3._full_key(md_key))["Body"].read().decode("utf-8")
    chapters = _chapters_from_markdown(body)
    return {
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
    key = f"{_job_key_root(p, job_id)}/research/bibliography.json"
    body = s3._client.get_object(Bucket=s3.bucket, Key=s3._full_key(key))["Body"].read().decode("utf-8")
    raw = json.loads(body) if body else []
    return [
        {
            "key": e.get("key") or e.get("id") or "",
            "title": e.get("title", ""),
            "authors": ", ".join(e.get("authors", [])) if isinstance(e.get("authors"), list) else e.get("authors", ""),
            "year": e.get("year"),
            "doi": e.get("doi"),
            "source": e.get("source", "CrossRef"),
            "venue": e.get("venue") or e.get("journal"),
            "verified": bool(e.get("verified", True)),
        }
        for e in raw
    ]


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
    out = []
    for fmt, (rel, _ct) in EXPORT_FORMATS.items():
        meta = s3.head_object(f"{_job_key_root(p, job_id)}/{rel}")
        if meta:
            out.append({"format": fmt, "size": meta["ContentLength"],
                         "generated_at": meta["LastModified"].isoformat()})
    return out


@router.get("/{paper_id}/exports/{fmt}")
def download_export(paper_id: uuid.UUID, fmt: str,
                     user: User = Depends(current_user), db: Session = Depends(db_session)):
    if fmt not in EXPORT_FORMATS:
        raise HTTPException(404, detail={"error": {"code": "unknown_format", "message": fmt}})
    p, job_id = _require_done_paper(db, user, paper_id)
    s3 = get_s3_from_settings(get_settings())
    rel, _ct = EXPORT_FORMATS[fmt]
    url = s3.presigned_get(f"{_job_key_root(p, job_id)}/{rel}", expires_in=300)
    return RedirectResponse(url, status_code=302)

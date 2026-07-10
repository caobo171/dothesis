"""Field-It: hand a vetted instrument off to the team's own survey rails.

Vets nothing here — the Questionnaire Doctor already ran in M3. This route takes
the instrument + sampling plan and creates a collection on fillform (VN) or
survify (intl), returning a share link. The commercial flywheel
(project_sibling_products memory): DoThesis funnels survey traffic to the user's
own products.

Best-effort (Global Constraint): a provider failure returns the existing Google
Form Apps Script so the student is never stuck without a way to field. POST-only
(project convention); authed + ownership-checked (F0 Part B — writing a survey
against a project and, for /results, into M4 must never be an anonymous write).
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..deps import current_user, db_session
from ..models import Project, User
from ..settings import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["field-it"])


# --- auth / store seams (stubbed in tests, mirror roadmap.py) ---------------

def _authorize(db: Session, user: User, project_id: str) -> Project:
    """403 unless the caller owns the project. Kept thin so tests can stub it."""
    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(404, detail={"error": {"code": "not_found", "message": "no such project"}})
    p = db.get(Project, pid)
    if p is None or p.user_id != user.id:
        raise HTTPException(403, detail={"error": {"code": "forbidden", "message": "not your project"}})
    return p


def _store_for(project_id: str):
    """Return the project's DbProjectStateStore. Isolated so tests can stub it.
    Mirrors roadmap.py / chat_v3's construction."""
    from ..agent_state import DbProjectStateStore
    from ..db import get_engine
    from .chat_v3 import _workspace_dir
    pid = uuid.UUID(project_id)
    return DbProjectStateStore(get_engine(), pid, _workspace_dir(pid))


# --- provider selection + handoff ------------------------------------------

class FieldItIn(BaseModel):
    instrument: dict
    sampling_plan: dict = {}
    language: str = "en"


def _provider_for(language: str) -> str:
    """Default provider by language/region: Vietnamese → fillform, else survify."""
    return "fillform" if str(language).lower().startswith("vi") else "survify"


def _provider_create_survey(provider: str, payload: dict) -> dict:
    """Call the provider REST API to create a collection.

    Isolated so tests stub it and so the real fillform/survify wiring
    (settings.fillform_api_* / settings.survify_api_*) is a single edit. Until
    the provider contract is live this raises, and the route's fallback returns
    the Google Form script — that's the intended ship state.
    """
    settings = get_settings()
    base = settings.fillform_api_base if provider == "fillform" else settings.survify_api_base
    if not base:
        raise RuntimeError(f"{provider} API base not configured")
    # Real REST call goes here (httpx POST base + token). Deliberately not wired
    # until the provider contract lands; the fallback path ships in the meantime.
    raise NotImplementedError(f"{provider} REST handoff not wired yet")


@router.post("/projects/{project_id}/field-it")
async def create_field_it(project_id: str, body: FieldItIn,
                          user: User = Depends(current_user),
                          db: Session = Depends(db_session)):
    _authorize(db, user, project_id)
    provider = _provider_for(body.language)
    items = body.instrument.get("items", [])
    # Every fielded survey opens with a consent/data-privacy notice (F0 #5).
    from agent.tools.instrument import build_consent_notice  # noqa: PLC0415
    consent = build_consent_notice(body.language)
    payload = {"project_id": project_id, "items": items,
               "target_n": body.sampling_plan.get("target_n"), "consent": consent}
    try:
        res = _provider_create_survey(provider, payload)
        return {"provider": provider, "collection_id": res["collection_id"],
                "survey_url": res["survey_url"]}
    except Exception:
        logger.exception("field-it: provider handoff failed; returning Google Form fallback")
        from agent.tools.forms import make_google_form_script  # noqa: PLC0415
        # make_google_form_script expects questions as list[dict] (F0 #3), not
        # list[str]; default each to a paragraph item. Consent rides in the form
        # description so the fallback is ethics-complete too.
        script = make_google_form_script.func(
            title="Thesis Survey",
            questions=[{"text": i.get("text", ""), "type": "paragraph"} for i in items],
            description=consent)
        return {"provider": "google_form_fallback", "fallback_google_script": script}

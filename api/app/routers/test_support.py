"""E2E-only test-support endpoints (POST-only, per CLAUDE.md).

SECURITY: create_app mounts this router ONLY when
settings.test_support_enabled (env DOTHESIS_TEST_SUPPORT=1) is set, and every
endpoint re-checks the flag at request time (defense in depth against an
accidental mount). No production configuration sets the flag.

Three seams, each standing in for something a browser test cannot do:
- verify-email: real signup returns {ok,email} and requires the emailed
  verify link (auth.py:signup); this replaces "clicking the link" so signup
  and login themselves stay fully real in tests.
- seed-project: builds a project the way chat.create_project does, then
  writes module slices through DbProjectStateStore.commit_slice — the REAL
  guarded write path (ownership, done-gate, needs_review propagation) — so
  seeded state is indistinguishable from agent-committed state.
- set-credit: pins a balance (e.g. 0 for the 402 journey). Sets the column
  directly and deliberately NOT via credit_ledger: the ledger records real
  financial events and synthetic entries would pollute admin reporting.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.state import MODULES, SliceOwnershipError

from ..agent_state import DbProjectStateStore
from ..credit_ledger import credit as ledger_credit
from ..db import db_session
from ..deps import current_user
from ..jwt_auth import AuthedBody
from ..models import ContextStore, Project, Thread, User
from ..settings import get_settings

router = APIRouter(prefix="/test", tags=["test-support"])


def _require_test_support():
    # Second gate alongside the conditional mount in create_app(). get_settings() is a
    # process-lifetime singleton (reset once, at boot), so this does NOT catch an env var
    # flipped on an already-running server — it guards a DIFFERENT scenario: a future code
    # change that imports/mounts this router unconditionally from somewhere else. Belt +
    # suspenders, not a live runtime toggle.
    if not get_settings().test_support_enabled:
        raise HTTPException(404)


class VerifyEmailBody(BaseModel):
    email: EmailStr


@router.post("/verify-email")
def verify_email(body: VerifyEmailBody,
                 db: Session = Depends(db_session),
                 _=Depends(_require_test_support)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user:
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    if not user.email_verified:
        user.email_verified = True
        # Mirror auth.verify's effect so a seeded user behaves like a real one
        # (the signup bonus is what funds their chat turns).
        settings = get_settings()
        ledger_credit(db, user, delta=settings.signup_bonus_credits,
                      reason="signup_bonus", ref_type="user", ref_id=user.id)
    user.last_login = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


class SeedProjectBody(AuthedBody):
    name: str = "E2E seeded thesis"
    # {"M1": {<writes>}, …} — keys must be the module's OWNED keys
    # (agent/state.py SLICE_OWNERSHIP); anything else 422s via commit_slice.
    slices: dict[str, dict] = {}
    # Modules to mark done (confirm_done=True on their commit).
    done: list[str] = []


@router.post("/seed-project")
def seed_project(body: SeedProjectBody,
                 user: User = Depends(current_user),
                 db: Session = Depends(db_session),
                 _=Depends(_require_test_support)):
    # Same rows chat.create_project writes (project + "Main" thread +
    # context_store shell) so the chat UI finds everything it expects.
    p = Project(user_id=user.id, name=body.name, field=None, language="en",
                citation_style="apa", current_module="M1", status="draft")
    db.add(p)
    db.flush()
    t = Thread(project_id=p.id, name="Main", langgraph_thread_id=str(uuid.uuid4()))
    db.add(t)
    db.add(ContextStore(project_id=p.id))
    db.commit()
    db.refresh(p)
    db.refresh(t)

    # Single source of truth for workspace locations — same helper chat_v3
    # uses when it builds the agent for this project.
    from .chat_v3 import _workspace_dir

    store = DbProjectStateStore(db.get_bind(), p.id, _workspace_dir(p.id))
    done = set(body.done)
    # Canonical M1->M5 order matches how a real user commits modules in sequence.
    # NOTE: this order does NOT exercise DOWNSTREAM needs_review propagation — every
    # downstream module is still `locked` (the one state the propagation check skips) at the
    # moment its upstream neighbor commits. Triggering it requires re-committing an
    # ALREADY-done upstream module after a downstream one is also done — see plan Note 14
    # for that follow-up scenario. This ordering is correct for seeding a clean fixture; it
    # is not, by itself, a needs_review test.
    for module in [m for m in MODULES if m in body.slices]:
        try:
            store.commit_slice(module, body.slices[module], "e2e seed",
                               confirm_done=module in done)
        except (SliceOwnershipError, ValueError) as e:
            raise HTTPException(422, detail={"error": {"code": "bad_slice",
                                                       "message": str(e)}})
    return {"project_id": str(p.id), "thread_id": str(t.id)}


class SetCreditBody(AuthedBody):
    credit: int


@router.post("/set-credit")
def set_credit(body: SetCreditBody,
               user: User = Depends(current_user),
               db: Session = Depends(db_session),
               _=Depends(_require_test_support)):
    user.credit = body.credit
    db.commit()
    return {"ok": True, "credit": user.credit}

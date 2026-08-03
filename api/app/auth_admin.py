import logging
import uuid

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from .admin_config import is_super_admin
from .deps import current_user
from .models import Project, User

log = logging.getLogger(__name__)


def require_admin(user: User = Depends(current_user)) -> User:
    if not is_super_admin(user):
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "forbidden", "message": "admin only"}},
        )
    return user


def readable_project(db: Session, user: User, project_id: uuid.UUID) -> Project:
    """The project, if `user` may READ it: the owner, or a super admin.

    Routers keep their own `_owned_project` for anything that WRITES. The split
    is deliberate and the asymmetry is the point: a super admin needs to open a
    student's thread to debug a bad run, but must not be able to post a message
    into it — that would spend the student's credits, append to their history
    and mutate the graph checkpoint under them. Debugging is a read.

    Same 404 (not 403) as the owner path for a project that doesn't exist or
    isn't readable, so this never becomes an oracle for "does this id exist".

    Admin access to someone else's work is logged. It is a real privacy event —
    thesis drafts are the most private thing in the product — and "who looked at
    what" should be answerable from the journal rather than from memory.
    """
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404,
                            detail={"error": {"code": "not_found", "message": "project not found"}})
    if p.user_id == user.id:
        return p
    if is_super_admin(user):
        log.info("admin_read project_id=%s owner_id=%s admin=%s",
                 project_id, p.user_id, user.email)
        return p
    raise HTTPException(status_code=404,
                        detail={"error": {"code": "not_found", "message": "project not found"}})

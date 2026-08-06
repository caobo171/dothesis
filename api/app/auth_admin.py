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


def _run_404() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"error": {"code": "not_found", "message": "tool run not found"}})


def readable_run(db: Session, user: User, run_id: int):
    """The tool run, if `user` may READ it: the owner, or a super admin.

    Same shape and same reasoning as `readable_project` above — a tool run now
    holds the student's actual document, so "who looked at what" has to be
    answerable from the journal, and a run the caller may not read is a 404
    rather than a 403 so the route never becomes an existence oracle.

    Reading a run is how a bad one gets diagnosed: the 2026-08-05 translation
    bug needed both files, and without this the only way to get them is to ask
    the student.
    """
    from .models import ToolRun  # noqa: PLC0415

    run = db.get(ToolRun, run_id)
    if not run:
        raise _run_404()
    if run.user_id == user.id:
        return run
    if is_super_admin(user):
        log.info("admin_read tool_run=%s owner_id=%s admin=%s",
                 run_id, run.user_id, user.email)
        return run
    raise _run_404()


def owned_run(db: Session, user: User, run_id: int):
    """The tool run, if `user` OWNS it. For anything that writes.

    Re-running spends the owner's credits and appends to their history, so it
    takes this gate and not `readable_run` — the same split `_owned_project`
    keeps for every write on a project an admin may read.
    """
    from .models import ToolRun  # noqa: PLC0415

    run = db.get(ToolRun, run_id)
    if not run or run.user_id != user.id:
        raise _run_404()
    return run

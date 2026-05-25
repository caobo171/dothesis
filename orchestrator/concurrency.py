"""First-confirm-wins commit for the project-shared context_store.

Concurrent threads within the same project may both reach the end of the same
module. We use a row-level lock on context_store(project_id) so the second
committer can detect "field X already filled" and raise a structured conflict
that the agent can surface to the user.
"""
from __future__ import annotations

import json
import logging
from typing import Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

ModuleKey = Literal["M1", "M2", "M3", "M4", "M5"]

# Maps module identifiers to their corresponding context_store column names.
# This is an explicit fixed dict — column names never come from user input,
# which ensures the raw-SQL f-string interpolation below is safe (no injection).
_MODULE_COLUMN = {
    "M1": "m1_topic",
    "M2": "m2_literature",
    "M3": "m3_design",
    "M4": "m4_analysis",
    "M5": "m5_writing",
}


class ContextCommitConflict(RuntimeError):
    """Raised when a thread tries to confirm a module already confirmed elsewhere."""

    def __init__(self, module: ModuleKey, project_id: UUID,
                 existing_thread_name: str, existing_confirmed_at: str):
        super().__init__(
            f"{module} was already confirmed in thread '{existing_thread_name}' "
            f"at {existing_confirmed_at}"
        )
        self.module = module
        self.project_id = project_id
        self.existing_thread_name = existing_thread_name
        self.existing_confirmed_at = existing_confirmed_at


def commit_module_output(
    db: Session,
    *,
    project_id: UUID,
    module: ModuleKey,
    output: dict,
    thread_name: str,
) -> None:
    """Commit `output` to context_store.<module_column> with first-confirm-wins.

    Caller still owns the transaction (must `db.commit()` after).

    Behavior:
      - SELECT … FOR UPDATE on the context_store row for this project.
      - If the module column is already non-null AND has a confirmed_at value,
        raise ContextCommitConflict with the existing thread's name.
      - Otherwise, write the new JSONB.

    Security note: `column` is derived exclusively from `_MODULE_COLUMN`, a fixed
    compile-time dict mapping known module keys to known column names.  It is never
    derived from user-supplied input, so the f-string interpolation into raw SQL is
    safe against injection.
    """
    column = _MODULE_COLUMN[module]

    # Acquire a row-level lock so two concurrent callers serialise here.
    existing = db.execute(
        text(f"SELECT {column} FROM context_store WHERE project_id = :pid FOR UPDATE"),
        {"pid": project_id},
    ).scalar()

    if existing and existing.get("confirmed_at"):
        # Decision: first writer wins — surface the conflict to the caller so the
        # agent can inform the user rather than silently discarding their output.
        # Prefer reading the thread name directly from the stored blob (set on
        # write below) before falling back to a messages-table lookup.
        existing_thread = (
            existing.get("_confirmed_by_thread")
            or _find_confirming_thread(db, project_id, module)
            or "another thread"
        )
        raise ContextCommitConflict(
            module=module,
            project_id=project_id,
            existing_thread_name=existing_thread,
            existing_confirmed_at=existing["confirmed_at"],
        )

    # Embed provenance in the blob so conflicts can always name the source thread,
    # even when the threads table has no matching row yet (e.g. early in project
    # setup).  Keys prefixed with `_` are internal metadata, not domain fields.
    enriched_output = {**output, "_confirmed_by_thread": thread_name}

    db.execute(
        text(
            f"UPDATE context_store SET {column} = CAST(:val AS JSONB), "
            f"updated_at = NOW() WHERE project_id = :pid"
        ),
        {"val": json.dumps(enriched_output, default=str), "pid": project_id},
    )

    # Also record provenance in messages for projects that have a threads row.
    # INSERT is a no-op (LIMIT 1 returns nothing) when the thread row doesn't
    # exist yet — this keeps the helper self-contained without hard-coupling to
    # thread creation order.
    db.execute(
        text(
            "INSERT INTO messages (thread_id, role, content, module_tag) "
            "SELECT t.id, 'system', :marker, :module "
            "FROM threads t WHERE t.project_id = :pid AND t.name = :tname "
            "LIMIT 1"
        ),
        {"marker": f"[confirmed {module}]", "module": module,
         "pid": project_id, "tname": thread_name},
    )
    logger.info("context_store.%s committed for project %s by thread %s",
                column, project_id, thread_name)


def _find_confirming_thread(db: Session, project_id: UUID, module: ModuleKey) -> str | None:
    """Look up the thread that emitted the `[confirmed M*]` system message."""
    row = db.execute(
        text(
            "SELECT t.name FROM messages m JOIN threads t ON t.id = m.thread_id "
            "WHERE t.project_id = :pid AND m.module_tag = :module "
            "AND m.content = :marker ORDER BY m.id DESC LIMIT 1"
        ),
        {"pid": project_id, "module": module, "marker": f"[confirmed {module}]"},
    ).scalar()
    return row

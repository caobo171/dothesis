"""Brief §1.3 — resume from our own tables, not a checkpoint framework.

The brief is explicit: "Resume = load durable state. The DB is the
checkpoint." LangGraph's PostgresSaver is what we built first; PR #6
adds the alternative — reconstruct OrchestratorState per turn from
`projects` + `context_store` + `messages`, then run the graph with
`MemorySaver` (in-process, throwaway).

PR #6 is FLAG-GATED. With `RESUME_VIA_DB=true` set, the API process
uses this loader instead of LangGraph's checkpoint persistence. Default
off so production traffic stays on the current path until soak passes.

What gets loaded:
  - context_store        — from context_store table (PR #1)
  - focus + status       — from projects.focus / module_status (PR #1)
  - messages             — full transcript from messages table
  - target_artifact      — from threads.target_artifact
  - mode                 — interactive (this loader is interactive-only;
                           auto-mode subprocess keeps its own state)

What gets persisted on each turn (single transaction):
  - context_store        — slice writes from the picked module
  - projects.focus       — post-turn focus from router_agent_node
  - projects.module_status  — recomputed status map
  - messages             — assistant reply(ies)
  - version_history      — snapshot row when intent == 'mutate'
                           (closes brief §2 gap as a side effect)
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from orchestrator.state import (
    ContextStore, ModuleKey, ModuleStatusMap, OrchestratorState,
    compute_status_map,
)

logger = logging.getLogger(__name__)


def resume_via_db_enabled() -> bool:
    """Brief §1.3 / §6 flag.

    Off → today's path (LangGraph PostgresSaver in orchestrator/graph.py).
    On  → load_state / persist_turn (this module) replace the checkpoint.

    Defaulting OFF keeps the rollout safe: we ship the loader, exercise
    it via tests, then flip in production once soaked. The chat router
    branches on this flag at the resume site.
    """
    return os.getenv("RESUME_VIA_DB", "false").lower() == "true"


@dataclass
class LoadedState:
    """What load_state returns. Same fields the graph would have read
    from a checkpoint — minus the per-node intermediate state, which
    LangGraph reconstructs anyway when we re-enter the graph."""
    context_store: ContextStore
    messages: list[BaseMessage]
    focus: ModuleKey | None
    status: ModuleStatusMap
    target_artifact: str | None


def load_state(
    project_id: uuid.UUID,
    thread_id: uuid.UUID,
    *,
    db: Any,
) -> LoadedState:
    """Reconstruct OrchestratorState from our own tables (brief §1.3).

    Pure read — no writes, no side effects. The caller wires the result
    into a graph_input dict for the next turn.

    Failure mode: a missing project or thread raises (the chat router's
    HTTPException 404 path catches and returns to the user). Empty
    transcript / no context_store rows are valid (cold start) and
    return defaults.
    """
    # Imports inside the function to keep this module importable without
    # the api package (e.g. eval scripts that exercise the loader logic
    # against a stub session).
    from app.models import (
        ContextStore as DbContextStore, Message, Project, Thread,
    )

    p = db.get(Project, project_id)
    if p is None:
        raise LookupError(f"project {project_id} not found")
    t = db.get(Thread, thread_id)
    if t is None or t.project_id != project_id:
        raise LookupError(f"thread {thread_id} not found on project {project_id}")

    db_cs = db.get(DbContextStore, project_id)
    cs = ContextStore(
        m1_topic=(db_cs.m1_topic if db_cs else None),
        m2_literature=(db_cs.m2_literature if db_cs else None),
        m3_design=(db_cs.m3_design if db_cs else None),
        m4_analysis=(db_cs.m4_analysis if db_cs else None),
        m5_writing=(db_cs.m5_writing if db_cs else None),
    )

    # Load the full transcript. Per brief §5 / PR #4: FULL MODE first.
    # When phase 2 (tiered memory) lands, the assembler trims this list
    # — but the load_state contract is "everything the thread has". This
    # is also what makes resume preserve perfect recall: the next turn
    # gets the same transcript the previous turn saw.
    rows = (
        db.query(Message)
        .filter(Message.thread_id == thread_id)
        .order_by(Message.id)
        .all()
    )
    messages: list[BaseMessage] = []
    for row in rows:
        if row.role == "user":
            messages.append(HumanMessage(content=row.content))
        else:
            ai = AIMessage(content=row.content)
            if row.tool_calls_json:
                ai.additional_kwargs["tool_calls_json"] = row.tool_calls_json
            messages.append(ai)

    focus: ModuleKey | None = p.focus or p.current_module  # dual-write fallback
    # Persisted status (PR #1) is the cache; derive fresh from cs to be
    # defensive against drift between context_store writes and the
    # projects.module_status column.
    status = compute_status_map(cs)

    return LoadedState(
        context_store=cs,
        messages=messages,
        focus=focus,
        status=status,
        target_artifact=t.target_artifact,
    )


def build_graph_input(loaded: LoadedState, *, project_id: uuid.UUID,
                      thread_id: uuid.UUID, user_message: str,
                      widget_payload: dict | None = None) -> dict:
    """Translate LoadedState into the graph_input dict for graph.astream.

    Same shape the chat router builds today on the first-turn seed path
    — the difference is we build it on EVERY turn (no checkpoint owns
    persistent state between turns).
    """
    return {
        "messages": loaded.messages + [HumanMessage(content=user_message)],
        "mode": "interactive",
        "thread_id": str(thread_id),
        "pending_widget_payload": widget_payload,
        "context_store": loaded.context_store,
        "project_id": project_id,
        "focus": loaded.focus,
        "status": loaded.status,
        "target_artifact": loaded.target_artifact,
    }


def persist_turn(
    project_id: uuid.UUID,
    thread_id: uuid.UUID,
    *,
    db: Any,
    final_state: dict,
    user_message: str,
    assistant_message: str,
    module_tag: str | None,
    tool_calls_json: dict | None,
    intent: str = "continue",
) -> None:
    """Write everything from one turn back to our tables in ONE transaction.

    Replaces the chat router's separate context_store-sync block. Brief
    §2 version_history is written here too (only on intent='mutate' to
    avoid one row per clarification turn — the version is the SNAPSHOT
    of a decision, not the turn).

    The caller has already inserted the user message before invoking the
    graph (chat router's existing contract); this function does NOT
    re-insert it. It DOES insert the assistant reply.
    """
    from app.models import (
        ContextStore as DbContextStore, Message, Project,
    )

    cs_after = final_state.get("context_store")
    if cs_after is not None:
        db.query(DbContextStore).filter_by(project_id=project_id).update({
            "m1_topic":      cs_after.m1_topic,
            "m2_literature": cs_after.m2_literature,
            "m3_design":     cs_after.m3_design,
            "m4_analysis":   cs_after.m4_analysis,
            "m5_writing":    cs_after.m5_writing,
        })

    proj_patch: dict = {}
    if final_state.get("focus"):
        proj_patch["focus"] = final_state["focus"]
    if final_state.get("status") is not None:
        proj_patch["module_status"] = final_state["status"].model_dump()
    if proj_patch:
        db.query(Project).filter_by(id=project_id).update(proj_patch)

    db.add(Message(
        thread_id=thread_id, role="assistant",
        content=assistant_message,
        module_tag=module_tag, tool_calls_json=tool_calls_json,
    ))

    # Brief §2 — version_history. Append-only snapshot of (slice, before,
    # after) per mutate. Only on intent=='mutate' to avoid noise from
    # clarification turns. The before/after is the ENTIRE slice value
    # (small, JSONB-friendly) — diffs computed on read.
    if intent == "mutate" and cs_after is not None:
        _record_version(db, project_id, cs_after, module_tag)

    db.commit()


def _record_version(db: Any, project_id: uuid.UUID,
                    cs_after: ContextStore, module_tag: str | None) -> None:
    """Insert one row into version_history. Best-effort: if the table
    doesn't exist yet (migration pending) we log and move on rather
    than break the turn."""
    try:
        from app.models import VersionHistory  # noqa: F401
    except ImportError:
        logger.debug("version_history table not yet migrated; skipping snapshot")
        return

    slice_field = {
        "M1": "m1_topic", "M2": "m2_literature", "M3": "m3_design",
        "M4": "m4_analysis", "M5": "m5_writing",
    }.get(module_tag or "", None)
    if slice_field is None:
        return  # unknown module — no snapshot meaningful

    from app.models import VersionHistory
    db.add(VersionHistory(
        project_id=project_id,
        slice_field=slice_field,
        slice_after=getattr(cs_after, slice_field) or {},
    ))

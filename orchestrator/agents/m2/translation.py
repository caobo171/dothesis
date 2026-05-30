"""Translation between outer OrchestratorState and M2SubGraphState."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import PaperUpload
from orchestrator.agents.m2.state import M2SubGraphState, fresh_state


def _seed_from_outer(outer_state: dict, db: Session) -> M2SubGraphState:
    """Build a fresh M2SubGraphState from the outer state + DB-resolved paper_uris.

    Reads m1_topic for research metadata and m2_literature for any partial work
    already persisted, so the sub-graph can resume mid-session rather than restart.
    """
    cs = outer_state["context_store"]
    m1 = cs.m1_topic or {}
    m2 = cs.m2_literature or {}

    project_id = outer_state.get("project_id")
    paper_uris: list[str] = []
    if project_id is not None:
        rows = db.query(PaperUpload).filter_by(project_id=project_id).all()
        paper_uris = [r.s3_uri for r in rows]

    sub = fresh_state(
        project_id=project_id,
        thread_id=outer_state.get("thread_id"),
        research_title=m1.get("research_title", "Untitled"),
        research_type=m1.get("research_type", "quantitative"),
        language=m1.get("language", "en"),
        paper_uris=paper_uris,
        mode=outer_state.get("mode", "interactive"),
    )

    # Restore any partial work already confirmed/saved in context_store.m2_literature
    if m2.get("research_state_summary"):
        sub["research_state_draft"] = m2["research_state_summary"]
    if m2.get("research_gaps"):
        sub["candidate_gaps"] = m2["research_gaps"]
        sub["selected_gap_ids"] = [str(i) for i in range(len(m2["research_gaps"]))]
    if m2.get("citation_list"):
        sub["citation_list"] = m2["citation_list"]

    # Restore the FULL working sub-state persisted by the previous interactive
    # turn (phase pointer + per-phase scratch). Applied last so it wins over the
    # coarse business-field restores above. Without this the wrapper rebuilt a
    # fresh sub-state every turn — current_phase reset to "familiarize" — so M2
    # could never advance past phase 1 (the phase-amnesia half of the
    # "stuck after confirming M1" bug). See _flatten_to_m2_output for the writer.
    phase_state = m2.get("_phase_state")
    if phase_state:
        sub.update(phase_state)
    return sub


def _flatten_to_m2_output(sub_state: M2SubGraphState) -> dict[str, Any]:
    """Pack the sub-graph's final state into a M2Output-shape dict.

    Only emits 'confirmed_at' when current_phase == 'DONE', so partial saves
    don't falsely mark the module as complete in the outer context store.
    """
    research_type = sub_state.get("research_type", "quantitative")
    research_gaps = sub_state.get("candidate_gaps") or []
    if sub_state.get("selected_gap_ids"):
        try:
            sel = set(int(i) for i in sub_state["selected_gap_ids"])
            research_gaps = [g for i, g in enumerate(research_gaps) if i in sel]
        except (ValueError, TypeError):
            pass

    out: dict[str, Any] = {
        "research_state_summary": sub_state.get("research_state_draft") or "",
        "research_gaps": research_gaps,
        "theoretical_framework": sub_state.get("theoretical_framework", ""),
        "hypotheses": [] if research_type == "qualitative"
                       else sub_state.get("hypotheses", []),
        "propositions": [] if research_type == "quantitative"
                         else sub_state.get("propositions", []),
        "literature_review_doc": sub_state.get("ch2_draft") or "",
        "citation_list": sub_state.get("citation_list", []),
    }
    if sub_state.get("current_phase") == "DONE":
        out["confirmed_at"] = datetime.now(timezone.utc).isoformat()
    else:
        # Mid-M2: persist the full working sub-state (minus the inputs that
        # _seed_from_outer re-derives each turn, and minus `messages` which hold
        # non-JSON-serialisable BaseMessage objects) so the next turn resumes
        # exactly where this one paused. Underscore-prefixed key → ignored by the
        # base agent's summary/printing helpers and never mistaken for a real
        # M2Output business field.
        out["_phase_state"] = {
            k: v for k, v in sub_state.items() if k not in _SEEDED_INPUT_KEYS
        }
    return out


# Inputs that _seed_from_outer rebuilds from outer state on every M2 entry, so
# they must NOT be frozen into the persisted _phase_state (research_title etc.
# could legitimately change; messages aren't JSON-serialisable).
_SEEDED_INPUT_KEYS = frozenset({
    "project_id", "thread_id", "research_title", "research_type",
    "language", "paper_uris", "messages", "mode",
})

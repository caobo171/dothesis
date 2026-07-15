"""Headless run spine (convergence spec §1/§4).

The runner plays the STUDENT's part against the same build_agent/stream_turn
brain chat uses. Mode differences are DATA held by this caller — neither
stream_turn nor build_agent ever inspects a profile, which is what preserves
the headless invariant: chat features cannot gate headless, because headless
runs the same code with a different caller.
"""
from __future__ import annotations

from datetime import datetime, timezone

from agent.state import MODULES, ProjectStateStore


def record_decision(
    store: ProjectStateStore,
    *,
    options: list[str],
    choice: str,
    rationale: str,
) -> dict:
    """Append one auto-decision to the audit trail, through commit_slice.

    Spec §4: decisions ride INSIDE the owned slice ("decisions" is in every
    module's SLICE_OWNERSHIP) so DbProjectStateStore persists them via the
    existing ownership machinery — a new top-level key would pass file-store
    tests and vanish in prod. Worse data modelling, considerably safer.

    status_overrides snapshots every module's CURRENT status because
    commit_slice's normal side effects (module -> in_progress, downstream
    needs_review propagation) belong to content commits; an audit append that
    regressed a `done` module or flagged reviews would corrupt the very run it
    is auditing. Overrides are applied after commit_slice's own status writes
    (agent/state.py), so the snapshot always wins.
    """
    state = store.load()
    module = state.get("focus") or "M1"
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "module": module,
        "options": list(options),
        "choice": choice,
        "rationale": rationale,
    }
    decisions = list(state["contextStore"].get("decisions") or []) + [record]
    store.commit_slice(
        module,
        {"decisions": decisions},
        reason=f"headless auto-decision: {choice[:80]}",
        status_overrides={m: state["status"].get(m, "locked") for m in MODULES},
    )
    return record

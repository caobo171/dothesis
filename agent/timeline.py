"""Backwards thesis timeline + progress. Pure + null-safe (no I/O, no LLM) so it's
deterministic and safe to import from both the runtime and the API.

Buffers reflect reality — data collection is measured in weeks, not days, and is
sized from the target sample n (shared with F7's sampling plan). The plan is
laid out forward (M1 -> defense) but anchored to the defense date, so an
infeasible (too-late) start is flagged rather than refused (Global Constraint:
advisory, never blocking).

F0 correction: no dead `_PHASE_WEEKS` constant — the phase weeks live inline in
`build_timeline`'s `forward` list, the single source of truth.
"""
from __future__ import annotations

from datetime import date, timedelta

# Roadmap phase order (F2 modules + the two non-module phases: data collection
# between M3 and M4, defense prep after M5). Used by timeline_status to compare
# the student's real focus against the planned position.
_ORDER = ["M1", "M2", "M3", "collect", "M4", "M5", "defense"]


def _collection_weeks(target_n: int) -> int:
    """Weeks of fielding for `target_n` responses. ~50 quality responses/week via
    a typical survey push; floored at 3, capped at 6 (students underestimate)."""
    return max(3, min(6, -(-int(target_n or 150) // 50)))


def build_timeline(defense_date: date, method: str, target_n: int, today: date) -> dict:
    """Plan M1 -> defense backwards from `defense_date`.

    Returns {milestones:[{module,label,start,end,weeks}], data_collection_weeks,
    total_weeks, feasible}. `feasible` is False when the required start is already
    in the past (advisory flag, never a refusal)."""
    coll = _collection_weeks(target_n)
    # Forward order: M1 -> M2 -> M3 -> collect -> M4 -> M5 -> defense. Buffers are
    # deliberately generous. (method is accepted for future method-specific tuning
    # and to keep the signature stable with the set_defense_date tool.)
    forward = [("M1", "Topic", 1), ("M2", "Literature review", 3),
               ("M3", "Research design + questionnaire", 2),
               ("collect", "Data collection", coll), ("M4", "Data analysis", 2),
               ("M5", "Writing", 4), ("defense", "Defense prep", 1)]
    total = sum(w for _, _, w in forward)
    start = defense_date - timedelta(weeks=total)
    milestones, cursor = [], start
    for module, label, weeks in forward:
        end = cursor + timedelta(weeks=weeks)
        milestones.append({"module": module, "label": label,
                           "start": cursor.isoformat(), "end": end.isoformat(),
                           "weeks": weeks})
        cursor = end
    return {"milestones": milestones, "data_collection_weeks": coll,
            "total_weeks": total, "feasible": start >= today}

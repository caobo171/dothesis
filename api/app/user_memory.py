"""Per-user cross-project memory — Phase 0 (deterministic preferences).

This is the 4th memory tier (above the per-project context_store). It carries a
user's durable *preferences* across their thesis projects so a returning user
does not re-enter the same setup every time and the agent can frame guidance to
their habits.

ANTI-FABRICATION INVARIANT (see docs/architecture/2026-06-24-cross-project-user-
memory.md): this layer stores ONLY whitelisted preference keys. It must never
hold thesis content, literature sources, citations, hypotheses, or numeric
results — those are per-project and leaking them across projects is fabrication.
`write_user_prefs` REJECTS (raises) any non-whitelisted key rather than silently
dropping it, so a regression is loud.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from .models import UserMemory

# Hard whitelist of keys allowed in user memory. Mirrors how the agent whitelists
# slice keys via SLICE_OWNERSHIP. Anything not here is forbidden.
#
# Phase 0 writes only the deterministic four (captured from the project form).
# The rest are reserved for Phase 1 (LLM-distilled soft preferences) and are
# whitelisted now so the schema is forward-compatible.
USER_MEMORY_KEYS: frozenset[str] = frozenset({
    # Phase 0 — deterministic, captured from the project setup form
    "language",
    "citation_style",
    "research_approach",
    "field",
    # Phase 1 — inferred (reserved)
    "education_level",
    "writing_formality",
    "option_presentation",
    "auto_approve_default",
    # F4 — cross-project advisor learning. institution_default seeds a new
    # project's institution_profile; recurring_advisor_themes are the recurring
    # ADDRESSED directives so a new project starts pre-warned. Both are
    # preferences/patterns, not thesis content — safe under the anti-fabrication
    # invariant (no sources/citations/results cross projects).
    "institution_default",
    "recurring_advisor_themes",
    # F11 — weekly-nudge opt-in. A durable per-user preference (defaults True at
    # send time), not thesis content — safe under the anti-fabrication invariant.
    "nudge_opt_in",
})


class ForbiddenMemoryKey(ValueError):
    """Raised when a write targets a key outside USER_MEMORY_KEYS."""


def load_user_memory_row(db: Session, user_id: uuid.UUID) -> UserMemory | None:
    return db.get(UserMemory, user_id)


def load_user_prefs(db: Session, user_id: uuid.UUID) -> dict[str, Any]:
    """Flat {key: value} of a user's preferences ({} if none).

    Strips provenance — callers (form pre-fill, prompt header) want the values.
    Use load_user_memory_row for the full provenance-carrying rows.
    """
    row = db.get(UserMemory, user_id)
    if row is None or not row.prefs:
        return {}
    out: dict[str, Any] = {}
    for key, entry in row.prefs.items():
        if key not in USER_MEMORY_KEYS:
            continue  # defensive: ignore stale/forbidden keys on read
        out[key] = entry.get("value") if isinstance(entry, dict) else entry
    return out


def write_user_prefs(
    db: Session,
    user_id: uuid.UUID,
    updates: dict[str, Any],
    *,
    source_project_id: uuid.UUID | None = None,
    confidence: float = 1.0,
) -> None:
    """Upsert a user's preferences, merging per-key with provenance.

    - Rejects any key not in USER_MEMORY_KEYS (raises ForbiddenMemoryKey).
    - Skips None / empty-string values (don't clobber a real pref with a blank).
    - Caller owns the transaction (we flush, not commit) so this composes with
      the surrounding request.
    """
    bad = set(updates) - USER_MEMORY_KEYS
    if bad:
        raise ForbiddenMemoryKey(
            f"user_memory write rejected — forbidden keys: {sorted(bad)}"
        )

    clean = {
        k: v for k, v in updates.items()
        if v is not None and not (isinstance(v, str) and not v.strip())
    }
    if not clean:
        return

    now_iso = datetime.now(timezone.utc).isoformat()
    src = str(source_project_id) if source_project_id else None

    row = db.get(UserMemory, user_id)
    if row is None:
        row = UserMemory(user_id=user_id, prefs={})
        db.add(row)

    # Reassign a NEW dict so SQLAlchemy detects the JSONB mutation (in-place
    # mutation of a JSON column is not tracked).
    merged = dict(row.prefs or {})
    for key, value in clean.items():
        merged[key] = {
            "value": value,
            "source_project_id": src,
            "confidence": confidence,
            "updated_at": now_iso,
        }
    row.prefs = merged
    db.flush()


def distill_advisor_themes(db, user_id, advisor_feedback, source_project_id=None) -> None:
    """Summarize recurring ADDRESSED advisor directives into cross-project memory so a
    new project starts pre-warned. Cheap recurrence heuristic (issues seen >=2 become
    themes) rather than an LLM summary — deterministic and safe for a cross-project
    write. Best-effort — never breaks the caller (feedback loop must not crash a turn)."""
    from collections import Counter
    try:
        addressed = [d.get("issue", "").strip().lower()
                     for d in (advisor_feedback or []) if d.get("status") == "addressed"]
        themes = [issue for issue, n in Counter(addressed).items() if issue and n >= 2]
        if themes:
            write_user_prefs(db, user_id, {"recurring_advisor_themes": themes},
                             source_project_id=source_project_id, confidence=0.7)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("distill_advisor_themes failed")

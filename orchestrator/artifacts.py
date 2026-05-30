"""Artifact dependency DAG + definition-of-done (DoD) validators.

The thesis is modelled as a graph of deliverables ("artifacts"), each with
explicit prerequisites (`depends_on`) and a DoD validator that decides whether
the artifact is actually complete — checking real content, not just a
`confirmed_at` timestamp (which can mark an empty slice "done").

This module is PURE and additive: it reads a `ContextStore` and returns
readiness, but nothing routes on it yet. The planner (a later phase) will use
`readiness()` to decide what to work on and which prerequisites to backfill.

Design notes:
- v1 keeps M1-M4 as single artifacts (topic, literature, design, analysis) and
  splits M5 into per-chapter artifacts, so a student stuck on one chapter can be
  placed precisely. (Decision D5 default — see docs/design/guided-agent-architecture.md.)
- v1 validators are deterministic Python checks (Decision D3 default). LLM-judge
  validators for prose quality are a later refinement.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class DoD:
    """Definition-of-done result: is the artifact complete, and if not, what's missing.

    `gaps` is the actionable list of what's still needed — it's what the planner
    drives work from and what intake uses to assess an uploaded artifact.
    """
    done: bool
    gaps: list[str]


@dataclass(frozen=True)
class Artifact:
    """One thesis deliverable in the dependency DAG.

    - key:        stable identifier ("topic", "design", "ch_methodology", ...)
    - slice:      the ContextStore field it reads ("m1_topic", "m5_writing", ...)
    - depends_on: prerequisite artifact keys that must be done first
    - dod:        validator that receives the slice dict (or {}) and returns a DoD
    """
    key: str
    slice: str
    depends_on: tuple[str, ...]
    dod: Callable[[dict], DoD]


# ---------------------------------------------------------------------------
# DoD validators — deterministic content checks per artifact slice.
# Each receives the slice dict (or {} when the slice is None/untouched) and
# returns a DoD whose `gaps` always mention the offending field name, so the
# planner/intake can surface them directly.
# ---------------------------------------------------------------------------

def _missing_strings(slice_: dict, fields: tuple[str, ...]) -> list[str]:
    """Gaps for required string fields that are absent or blank."""
    return [
        f"missing {f}" for f in fields
        if not (isinstance(slice_.get(f), str) and slice_.get(f).strip())
    ]


def _empty_lists(slice_: dict, fields: tuple[str, ...]) -> list[str]:
    """Gaps for required list fields that are absent or empty."""
    return [
        f"{f} is empty" for f in fields
        if not (isinstance(slice_.get(f), list) and slice_.get(f))
    ]


def dod_topic(slice_: dict) -> DoD:
    """M1 topic: title/field/type/population/scope set + ≥1 objective & RQ."""
    slice_ = slice_ or {}
    gaps = _missing_strings(slice_, (
        "research_title", "field", "research_type", "target_population", "scope",
    ))
    gaps += _empty_lists(slice_, ("objectives", "research_questions"))
    return DoD(done=not gaps, gaps=gaps)

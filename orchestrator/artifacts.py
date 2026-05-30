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


def dod_design(slice_: dict) -> DoD:
    """M3 design: common fields + paradigm-specific artifacts.

    Mirrors M3Output._require_by_paradigm (orchestrator/schemas/m3.py) but as a
    content check over the persisted dict rather than a pydantic validator —
    quantitative needs conceptual_model + scale_items; qualitative needs themes
    + interview_guide + purposive_criteria; mixed needs both plus mixed_design_type.
    """
    slice_ = slice_ or {}
    gaps = _missing_strings(slice_, ("paradigm", "design", "tool", "sampling_strategy"))
    size = slice_.get("target_sample_size")
    if not (isinstance(size, int) and not isinstance(size, bool) and size > 0):
        gaps.append("missing target_sample_size")

    paradigm = slice_.get("paradigm")
    if paradigm == "quantitative":
        if not slice_.get("conceptual_model"):
            gaps.append("missing conceptual_model")
        gaps += _empty_lists(slice_, ("scale_items",))
    elif paradigm == "qualitative":
        gaps += _empty_lists(slice_, ("themes", "purposive_criteria"))
        if not slice_.get("interview_guide"):
            gaps.append("missing interview_guide")
    elif paradigm == "mixed":
        gaps += _missing_strings(slice_, ("mixed_design_type",))
        if not slice_.get("conceptual_model"):
            gaps.append("missing conceptual_model")
        gaps += _empty_lists(slice_, ("scale_items", "themes", "purposive_criteria"))
        if not slice_.get("interview_guide"):
            gaps.append("missing interview_guide")
    return DoD(done=not gaps, gaps=gaps)


def dod_literature(slice_: dict) -> DoD:
    """M2 literature: synthesis + ≥1 gap + framework + Ch2 draft + ≥1 citation."""
    slice_ = slice_ or {}
    gaps = _missing_strings(slice_, (
        "research_state_summary", "theoretical_framework", "literature_review_doc",
    ))
    gaps += _empty_lists(slice_, ("research_gaps", "citation_list"))
    return DoD(done=not gaps, gaps=gaps)


def dod_analysis(slice_: dict) -> DoD:
    """M4 analysis: a detected data type, an outline, ≥1 result.

    Mirrors M4Output._require_artifacts_on_confirm: qualitative additionally
    needs qual_codes + qual_themes.
    """
    slice_ = slice_ or {}
    gaps = _missing_strings(slice_, ("data_type_detected",))
    if not slice_.get("analysis_outline"):
        gaps.append("missing analysis_outline")
    if not slice_.get("results"):
        gaps.append("results is empty")
    if slice_.get("data_type_detected") == "Qualitative":
        gaps += _empty_lists(slice_, ("qual_codes", "qual_themes"))
    return DoD(done=not gaps, gaps=gaps)


def dod_chapter(chapter_name: str) -> Callable[[dict], DoD]:
    """Factory: DoD for one M5 chapter — done when m5_writing.chapters[name].prose
    is non-blank. Chapters are separate artifacts so a student stuck on a single
    chapter can be placed precisely (Decision D5)."""
    def _dod(slice_: dict) -> DoD:
        chapters = (slice_ or {}).get("chapters") or {}
        prose = (chapters.get(chapter_name) or {}).get("prose")
        if isinstance(prose, str) and prose.strip():
            return DoD(done=True, gaps=[])
        return DoD(done=False, gaps=[f"chapter '{chapter_name}' has no prose yet"])
    return _dod

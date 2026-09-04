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
    quantitative needs conceptual_model (which now carries both paths AND per-
    construct Likert items as node.questions, since the 2026-06 design merge
    folded the former scale_items field into the flow_chart shape); qualitative
    needs themes + interview_guide + purposive_criteria; mixed needs both plus
    mixed_design_type.
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
    elif paradigm == "qualitative":
        gaps += _empty_lists(slice_, ("themes", "purposive_criteria"))
        if not slice_.get("interview_guide"):
            gaps.append("missing interview_guide")
    elif paradigm == "mixed":
        gaps += _missing_strings(slice_, ("mixed_design_type",))
        if not slice_.get("conceptual_model"):
            gaps.append("missing conceptual_model")
        gaps += _empty_lists(slice_, ("themes", "purposive_criteria"))
        if not slice_.get("interview_guide"):
            gaps.append("missing interview_guide")
    return DoD(done=not gaps, gaps=gaps)


def dod_design_structural(slice_: dict) -> DoD:
    """Lighter gate for a RECONSTRUCTED design — structural/identifying fields
    only (paradigm, method, tool, sampling, sample size), NOT the detail
    artifacts (conceptual_model/scale_items/themes/interview_guide) that can't be
    inferred from downstream analysis.

    The Phase-3 eval showed reconstruction nails the skeleton but (correctly) does
    not fabricate the detail fields, so the full `dod_design` is the wrong bar for
    accepting a reconstructed prerequisite. This gate lets a confirmed skeleton
    unblock downstream work; the detail fields are surfaced for review/fill.

    Detail fields the skeleton skips: conceptual_model (flow_chart: paths +
    per-construct Likert items), themes, interview_guide.
    """
    slice_ = slice_ or {}
    gaps = _missing_strings(slice_, ("paradigm", "design", "tool", "sampling_strategy"))
    size = slice_.get("target_sample_size")
    if not (isinstance(size, int) and not isinstance(size, bool) and size > 0):
        gaps.append("missing target_sample_size")
    return DoD(done=not gaps, gaps=gaps)


def dod_literature(slice_: dict) -> DoD:
    """M2 literature: at least one grounded gap and one verified source.

    Decision: synthesis/framework prose belongs to M5 output generation, not to
    the literature-evidence gate. Requiring it kept fully reconstructed projects
    in M2 even after the system had already found sources and defensible gaps.
    """
    slice_ = slice_ or {}
    sources = slice_.get("literature_sources") or slice_.get("citation_list") or []
    verified = [source for source in sources
                if isinstance(source, dict) and source.get("verified") is not False]
    gaps = []
    if not verified:
        gaps.append("missing verified literature source")
    if not (slice_.get("research_gaps") or []):
        gaps.append("missing research_gaps")
    return DoD(done=not gaps, gaps=gaps)


# An imported analysis chapter, in characters. A finished thesis lands as one
# large blob; a stub ("TODO: run the analysis") must not clear the bar. Set well
# above a note and well below any real chapter — the observed import was 37,916.
_IMPORTED_WRITEUP_MIN = 1500


def dod_analysis(slice_: dict) -> DoD:
    """M4 analysis: a detected data type, an outline, ≥1 result.

    Mirrors M4Output._require_artifacts_on_confirm: qualitative additionally
    needs qual_codes + qual_themes.

    EXCEPT for an imported write-up. A student who uploads a finished thesis has
    demonstrably done the analysis, but their document arrives as one
    `analysis_results` STRING and none of the structured keys above. Worse,
    `data_type_detected` and `results` are not M4-owned (agent/state.py), so on
    the imported path there is no way for them to ever arrive — the module sat
    in_progress permanently while the agent asked the student to plan an
    analysis they had already run, and M5 stayed locked behind it.

    The escape is deliberately narrow: a STRING (the engine writes a dict, and
    that path must keep the strict DoD or a half-finished run would report done)
    of real length (a stub is not a chapter).

    A PARSED import also passes, under a narrower test. The import used to store
    the document as that raw string; it now extracts the structured
    analysis_results block, which is strictly BETTER evidence of a finished
    analysis — but it is a dict, so the string escape above stopped firing and
    the module went back to sitting in_progress forever, the exact failure this
    function was written to end. The dict is accepted only when it carries
    completed hypothesis tests AND the engine's own keys are absent: a
    mid-flight engine run always has `analysis_outline`, so it still faces the
    strict gate below and a half-finished run cannot report done.
    """
    slice_ = slice_ or {}
    imported = slice_.get("analysis_results")
    if isinstance(imported, str) and len(imported.strip()) >= _IMPORTED_WRITEUP_MIN:
        return DoD(done=True, gaps=[])
    if (isinstance(imported, dict) and imported.get("hypothesis_tests")
            and not slice_.get("analysis_outline")
            and not slice_.get("data_type_detected")):
        return DoD(done=True, gaps=[])
    gaps = _missing_strings(slice_, ("data_type_detected",))
    if not slice_.get("analysis_outline"):
        gaps.append("missing analysis_outline")
    if not slice_.get("results"):
        gaps.append("results is empty")
    if slice_.get("data_type_detected") == "Qualitative":
        gaps += _empty_lists(slice_, ("qual_codes", "qual_themes"))
    return DoD(done=not gaps, gaps=gaps)


# The chapters a thesis must actually have prose for before M5 can call itself
# done. A Vietnamese thesis merges discussion and conclusion into one final
# chapter ("KẾT LUẬN VÀ KIẾN NGHỊ"), which is now the only closing chapter in
# the canonical order — so this is a single name rather than a pair.
_M5_CORE_CHAPTERS = ("intro", "lit_review", "methodology", "results")
_M5_CLOSING_CHAPTER = "conclusion"


def _m5_chapter_prose(slice_: dict) -> dict[str, str]:
    """Chapter name -> prose, from EITHER M5 shape.

    `chapters` is the editor's canonical dict, but it is only materialised when
    the student opens the editor (api/app/routers/m5_editor.py). The
    conversational, compose and import paths all write the flat `final_sections`
    list instead. Reading only one shape would make M5 completable only after
    visiting a particular screen.
    """
    slice_ = slice_ or {}
    from orchestrator.tools.m5_writing import canonical_chapter  # noqa: PLC0415

    chapters = slice_.get("chapters")
    if isinstance(chapters, dict) and chapters:
        out: dict[str, str] = {}
        for stored, c in chapters.items():
            name = canonical_chapter(stored)
            # A real `conclusion` beats a legacy `discussion` aliased onto it —
            # an in-flight project that has both must not have its written
            # conclusion clobbered by an older discussion draft.
            if name is None or (name in out and stored != name):
                continue
            out[name] = (c or {}).get("prose") or "" if isinstance(c, dict) else ""
        return out
    from orchestrator.tools.m5_writing import chapters_from_final_sections

    mapped = chapters_from_final_sections(slice_.get("final_sections") or [])
    return {name: (c or {}).get("prose") or "" for name, c in mapped.items()}


def dod_writing(slice_: dict) -> DoD:
    """M5 writing: prose for the core chapters, plus the closing chapter.

    M5 had no module-level DoD at all — `done` fired on `confirmed_at` alone —
    so a thesis with every chapter written still reported `in_progress` and no
    amount of work could change that. This is the same shape of bug as
    dod_analysis: module state decided by bookkeeping rather than by whether the
    work exists.
    """
    prose = _m5_chapter_prose(slice_)
    have = {name for name, text in prose.items() if (text or "").strip()}
    gaps = [f"chapter '{n}' has no prose yet" for n in _M5_CORE_CHAPTERS
            if n not in have]
    if _M5_CLOSING_CHAPTER not in have:
        gaps.append("no conclusion chapter yet")
    return DoD(done=not gaps, gaps=gaps)


def dod_chapter(chapter_name: str) -> Callable[[dict], DoD]:
    """Factory: DoD for one M5 chapter — done when m5_writing.chapters[name].prose
    is non-blank. Chapters are separate artifacts so a student stuck on a single
    chapter can be placed precisely (Decision D5).

    Routed through `_m5_chapter_prose` rather than reading `chapters.get(name)`
    directly: this DoD is what `readiness()` evaluates per chapter, and it is
    exposed live as the `ch_conclusion` artifact through
    api/app/routers/chat.py's artifacts/impact/reconstruct routes (the
    "enter at any step" UI). A legacy project whose closing chapter is still
    stored under the retired `discussion` key has no `conclusion` entry at all
    — reading the raw dict would report that finished chapter as permanently
    unfinished at the artifact level even though dod_writing (module-level)
    already accepts it via the same alias. Reusing `_m5_chapter_prose` keeps
    the alias rule ("resolve through canonical_chapter, real key beats aliased
    key") in the one place that already implements it, instead of a second
    hand-rolled `.get('discussion')` fallback drifting out of sync with it.
    """
    def _dod(slice_: dict) -> DoD:
        prose = _m5_chapter_prose(slice_).get(chapter_name)
        if isinstance(prose, str) and prose.strip():
            return DoD(done=True, gaps=[])
        return DoD(done=False, gaps=[f"chapter '{chapter_name}' has no prose yet"])
    return _dod


# ---------------------------------------------------------------------------
# The DAG. v1: M1-M4 are single artifacts (D5 "as-is"); M5 splits into chapters.
# `depends_on` references other artifact keys (validated by the registry test).
# ---------------------------------------------------------------------------
ARTIFACTS: tuple[Artifact, ...] = (
    Artifact("topic",          "m1_topic",      (),                            dod_topic),
    Artifact("literature",     "m2_literature", ("topic",),                    dod_literature),
    Artifact("design",         "m3_design",     ("topic", "literature"),       dod_design),
    Artifact("analysis",       "m4_analysis",   ("design",),                   dod_analysis),
    Artifact("ch_intro",       "m5_writing",    ("topic", "literature"),       dod_chapter("intro")),
    Artifact("ch_lit_review",  "m5_writing",    ("literature",),               dod_chapter("lit_review")),
    Artifact("ch_methodology", "m5_writing",    ("design",),                   dod_chapter("methodology")),
    Artifact("ch_results",     "m5_writing",    ("analysis",),                 dod_chapter("results")),
    # ch_discussion is gone with the five-chapter collapse; ch_conclusion
    # inherits its dependencies. `analysis` is not restated because ch_results
    # already declares it, so it stays reachable transitively.
    Artifact("ch_conclusion",  "m5_writing",    ("ch_results", "topic"),       dod_chapter("conclusion")),
)


_ARTIFACT_BY_KEY = {a.key: a for a in ARTIFACTS}

# Artifacts graded by something other than their registry DoD. `design` is the
# only one: a RECONSTRUCTED design is judged on its skeleton, because
# reconstruction correctly declines to fabricate the detail fields.
_GATE_OVERRIDES = {"design": dod_design_structural}


def gate_for(artifact: str):
    """The DoD that decides whether `artifact` is complete.

    Public because this choice had two identical copies — one in
    orchestrator/backfill.py, one in api/app/routers/chat.py — each carrying its
    own comment warning that they must stay identical, which is the surest sign
    a rule wants one home. A third caller (the commit-time advisory in
    agent/tools/state_tools.py) would have made three.
    """
    return _GATE_OVERRIDES.get(artifact, _ARTIFACT_BY_KEY[artifact].dod)

# Maps each context_store slice to the graph module that owns it. Used to turn
# an artifact-level planner decision into a module-level routing target.
_SLICE_TO_MODULE = {
    "m1_topic": "M1", "m2_literature": "M2", "m3_design": "M3",
    "m4_analysis": "M4", "m5_writing": "M5",
}


def artifact_to_module(key: str) -> str:
    """Return the graph module (M1-M5) that owns the given artifact.

    Chapters all map to M5 (which owns chapter composition). Lets the supervisor
    route to a module from an artifact-level planner decision.
    """
    return _SLICE_TO_MODULE[_ARTIFACT_BY_KEY[key].slice]


# Inverse of artifact_to_module for the reconstruction path: a module maps back
# to the single "primary" artifact key that reconstruct_artifact can infer for
# it. M5 is deliberately absent — it splits into per-chapter artifacts and is
# never an *upstream* reconstruction target (you reconstruct M1-M4 as the
# prerequisites of imported work, not the write-up).
MODULE_TO_ARTIFACT: dict[str, str] = {
    "M1": "topic", "M2": "literature", "M3": "design", "M4": "analysis",
}


def dependents_closure(key: str) -> set[str]:
    """All artifacts that transitively depend on `key` (reverse of depends_on).

    Used to compute what's affected when an upstream artifact changes — the basis
    for "editing this step may invalidate these later steps".
    """
    seen: set[str] = set()
    stack = [a.key for a in ARTIFACTS if key in a.depends_on]
    while stack:
        k = stack.pop()
        if k in seen:
            continue
        seen.add(k)
        stack.extend(a.key for a in ARTIFACTS if k in a.depends_on)
    return seen


def stale_after_change(context_store, changed_key: str) -> list[str]:
    """Completed downstream artifacts that may need review after `changed_key`
    changes — i.e. the done dependents of the changed artifact, in DAG order.

    Not-yet-done dependents are ignored (there's nothing committed to invalidate).
    Makes "go back and edit an early step" safe by surfacing the blast radius.
    """
    status = readiness(context_store)
    affected = dependents_closure(changed_key)
    return [a.key for a in ARTIFACTS
            if a.key in affected and status.get(a.key) == "done"]


def readiness(context_store) -> dict[str, str]:
    """Classify every artifact as 'done' | 'ready' | 'blocked'.

    - done:    its DoD validator passes on the current slice content
    - ready:   not done, but ALL prerequisites are done → safe to work on
    - blocked: not done and at least one prerequisite is unmet

    Pure function over a ContextStore. This is what the planner (later phase)
    walks to pick the next-best action and to detect which prerequisites a
    targeted artifact needs backfilled.
    """
    done: dict[str, bool] = {}
    for art in ARTIFACTS:
        slice_ = getattr(context_store, art.slice, None) or {}
        # A user-confirmed slice is "done" regardless of the content-only DoD —
        # confirmation is the authoritative approval signal in the live flow, and
        # this stops the planner looping on a confirmed-but-imperfect slice.
        done[art.key] = bool(slice_.get("confirmed_at")) or art.dod(slice_).done

    status: dict[str, str] = {}
    for art in ARTIFACTS:
        if done[art.key]:
            status[art.key] = "done"
        elif all(done.get(dep, False) for dep in art.depends_on):
            status[art.key] = "ready"
        else:
            status[art.key] = "blocked"
    return status

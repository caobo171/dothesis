"""Brief §1.5 — `read` intent handler.

When the user asks about a module OTHER than the current focus ("remind me
what gap 2 was while I'm in M4"), we answer from the module's slice and
change nothing. This is cheaper than running the full module.step() (which
runs a clarification loop and can write the slice on prompt-extraction
false-positives) and preserves the conversation focus per brief §1.5.

Single entry point: `read_slice(target, message, cs, llm=...) -> str`.
Pure on `cs` — never writes, never mutates the slice.
"""
from __future__ import annotations

import logging
import os
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage

from orchestrator.agents.base import bounded_invoke
from orchestrator.state import ContextStore, ModuleKey, get_module_slice

logger = logging.getLogger(__name__)


_MODULE_DESCRIPTIONS = {
    "M1": "Topic Discovery — research title, field, type, target population, scope, objectives, research questions",
    "M2": "Literature Review — research-state summary, theoretical framework, gaps, citations, literature review doc",
    "M3": "Research Design — paradigm, design, tool, sampling, conceptual model, scale items, themes, interview guide",
    "M4": "Data Analysis — detected data type, analysis outline, results, qualitative codes/themes",
    "M5": "Writing — drafted chapters (intro, lit review, methodology, results, discussion, conclusion)",
}


def _default_llm():
    """Gemini Flash. Read answers are short conversational paraphrases of
    structured data — Flash is fast and cheap enough for this; latency is
    the explicit win of `read` over `module.step()`.

    Routes through the engine-wide factory (ORCHESTRATOR_LLM_ROUTE) so the whole
    engine is switchable. ORCHESTRATOR_READ_MODEL still overrides the model when
    set; unset → model=None so the factory applies its ORCHESTRATOR_LLM_MODEL /
    gemini-2.5-flash default (identical resolution). temperature=0.0 + timeout
    are this site's original settings."""
    from orchestrator.llm import get_orchestrator_llm
    return get_orchestrator_llm(
        model=os.getenv("ORCHESTRATOR_READ_MODEL"),
        temperature=0.0,
        timeout=int(os.getenv("ORCHESTRATOR_LLM_TIMEOUT", "20")),
    )


def _build_prompt(target: ModuleKey, slice_: dict) -> str:
    """System prompt for the read call.

    We pass the FULL slice (it's small — every module's slice is bounded
    by its Pydantic schema, typically <2KB) so the LLM can quote specifics.
    The "do NOT propose changes" instruction is what enforces the brief's
    "change nothing" semantics from the LLM side, in addition to the
    structural guarantee that nothing in this handler writes to the slice.
    """
    desc = _MODULE_DESCRIPTIONS.get(target, target)
    return (
        f"You are a thesis assistant answering a quick READ question about "
        f"module {target} ({desc}). The student is currently working on a "
        f"different module — they're just asking to see what's in {target}.\n\n"
        f"Module {target} data (JSON):\n{slice_}\n\n"
        f"Rules:\n"
        f"  - Answer the question by quoting/summarizing the data above.\n"
        f"  - Do NOT propose changes, edits, or next steps.\n"
        f"  - Do NOT ask the student a question — they did not ask you to work "
        f"on this module, only to look at it.\n"
        f"  - If the data field they're asking about is missing, say so "
        f"directly (e.g. 'No gaps have been captured in M2 yet').\n"
        f"  - Keep it short: 1–3 sentences unless the question asks for detail."
    )


def read_slice(
    target: ModuleKey,
    message: str,
    cs: ContextStore,
    *,
    llm=None,
    max_seconds: int = 15,
) -> str:
    """Answer `message` from the `target` module's slice. NEVER writes.

    Returns the assistant reply text. Caller (router_agent_node) wraps it in
    an AIMessage and emits — focus is unchanged, status is unchanged, no
    propagation, no slice write. That makes this a true read per brief §1.5.

    Failure mode: any LLM error falls back to a templated reply that quotes
    the slice verbatim. We never raise — read is a best-effort optimization,
    and a stale-feeling answer beats a dropped turn.
    """
    slice_ = get_module_slice(cs, target)
    if not slice_:
        # Brief §8.4 — soft locks. The module hasn't been touched yet; tell
        # the user plainly rather than guessing or routing them away.
        return (
            f"Module {target} hasn't been started yet — there's no data to "
            f"show. Want to switch to it, or keep going where you are?"
        )

    llm = llm or _default_llm()
    prompt = _build_prompt(target, slice_)
    try:
        ai = bounded_invoke(
            llm,
            [SystemMessage(content=prompt), HumanMessage(content=message)],
            max_seconds=max_seconds,
            retries=0,
        )
        return getattr(ai, "content", "") or _fallback_summary(target, slice_)
    except Exception:
        logger.exception("read_slice LLM failed; falling back to templated summary")
        return _fallback_summary(target, slice_)


def _fallback_summary(target: ModuleKey, slice_: dict) -> str:
    """Templated fallback when the LLM is unavailable.

    Returns a short prose summary of the slice's user-facing fields. Skips
    meta keys (_awaiting_field, _needs_review, …) — they're routing state,
    not user content. The list is short on purpose; full data is in the
    slice itself, which the UI exposes separately via the ContextPanel.
    """
    visible = {k: v for k, v in slice_.items()
               if not k.startswith("_") and k != "confirmed_at"
               and v not in (None, "", [], {})}
    if not visible:
        return f"Module {target} hasn't been filled in yet."
    bullets = "\n".join(f"  - {k}: {v}" for k, v in visible.items())
    return f"Here's what's in {target}:\n{bullets}"


# --- Intent classification ----------------------------------------------------
# Brief §1.5 — distinguish read vs mutate. The router picks a target module
# first; this classifier then decides whether the user wants to LOOK at it
# (read, no write) or WORK on it (mutate / continue, run module.step).
#
# Heuristic-first because most cross-module questions are obvious from
# surface form. Only ambiguous cases hit the LLM — keeps median latency low.

Intent = Literal["continue", "read", "mutate"]


# Surface markers we trust without an LLM. Tight on purpose: false positives
# here mean "treat a mutate as a read" → user's edit gets ignored. Better to
# be conservative and let ambiguous cases route through the LLM.
_READ_PREFIXES = (
    "what ", "what's ", "what is ", "show ", "show me ", "tell me ", "remind ",
    "remind me ", "list ", "summarise ", "summarize ", "summary of ",
    "explain ", "describe ", "give me ", "view ",
)


def classify_intent_heuristic(message: str, *, target_is_focus: bool) -> Intent | None:
    """Cheap rule-based intent pick. Returns None if the heuristic is
    not confident — caller falls back to LLM or treats as continue.

    - target_is_focus=True → always continue. The user is working on the
      focus module; intent doesn't matter for routing (no propagation).
    - Cross-module question-shape → read.
    - Cross-module with explicit edit verb → mutate.
    - Anything else → None (let the LLM classifier or default kick in).
    """
    if target_is_focus:
        return "continue"
    msg = (message or "").lstrip().lower()
    if not msg:
        return None
    if msg.endswith("?") or msg.startswith(_READ_PREFIXES):
        return "read"
    # Explicit edit verbs — when present we treat as mutate without an LLM
    # call so the propagation rule fires on obvious cases ("add a gap about
    # remote work", "change the methodology to qualitative"). The brief's
    # worked example in §4 uses this exact phrasing.
    edit_verbs = ("add ", "change ", "edit ", "update ", "remove ", "delete ",
                  "rename ", "switch to ", "redo ")
    if any(verb in msg for verb in edit_verbs):
        return "mutate"
    return None

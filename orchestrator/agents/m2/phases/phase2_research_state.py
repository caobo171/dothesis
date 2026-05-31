"""Phase 2 — Research_State."""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from orchestrator.agents.base import BoundedInvokeTimeout, bounded_invoke
from orchestrator.agents.m2.intent import classify_phase_intent
from orchestrator.agents.m2.state import M2SubGraphState
from orchestrator.agents.widgets import CardGridHint, CardOption
from orchestrator.message_utils import text_of
from orchestrator.tools.m2_literature import scout_citations


def _confirm_hint() -> dict:
    """Card grid attached to every synthesis draft (first call AND post-refine).

    W3: 'just type confirm or describe the change' was the hardest UX step in
    M2 — most users stalled at the draft because they couldn't quickly
    distinguish 'accept' from 'tweak'. Cards spell it out and route 'Other'
    through the text input for free-form refinement.
    """
    return CardGridHint(
        widget_type="card_grid",
        field_name="research_state_confirm",
        title="What next?",
        options=[
            CardOption(
                value="confirm",
                label="Confirm — this synthesis works",
                description="Lock it in and move on to research gaps.",
            ),
            CardOption(
                value="Other",
                label="Refine — let me describe the change",
                description=("Tell me what to add, drop, or re-focus and I'll "
                             "rewrite the synthesis."),
            ),
            CardOption(
                value="navigate",
                label="Go back to literature search",
                description=("Re-run citation discovery with different terms "
                             "before drafting again."),
            ),
        ],
        columns=3,
    ).model_dump()

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "prompts" / "m2"
_PROMPT = (_PROMPT_DIR / "2_research_state.md").read_text()
_STYLE = (_PROMPT_DIR / "_style.md").read_text()

_PHASE_KEY = "research_state"

logger = logging.getLogger(__name__)


def _regen_cap() -> int:
    return int(os.getenv("M2_REGEN_CAP", "5"))


def _no_citations_help_message(title: str) -> str:
    """User-facing help text when scout returns 0 citations.

    Surfaces both likely cause (typos / niche topic) and recovery actions
    (go back, upload papers, try different keywords). This message replaces
    the silent fabrication path the user hit on 'gen Z + titok affectiveness'.
    """
    safe_title = title if title else "your topic"
    return (
        f"⚠ I couldn't find academic citations for **\"{safe_title}\"**.\n\n"
        "Common causes:\n"
        "  • typos in the title (e.g. \"titok\" → \"tiktok\", "
        "\"affectiveness\" → \"effectiveness\")\n"
        "  • the topic phrasing doesn't match how academic papers index it\n"
        "  • the topic is genuinely too niche for our citation databases\n\n"
        "What you can do:\n"
        "  1. **Go back to refine the title** — say \"go back to topic\"\n"
        "  2. **Try different search terms** — say \"try X Y Z\" "
        "and I'll re-search\n"
        "  3. **Upload academic papers** via the attachment button (📎)\n\n"
        "I won't continue with empty citations — the literature review "
        "needs real sources."
    )


def _safe_scout(topic: str) -> list[dict]:
    """Scout citations, but never let a scout failure crash the chat turn.

    The scout tool raises (e.g. ValueError on its citation quality-gate, or when
    its search-provider API keys are missing) when it can't gather enough
    sources. That's a best-effort enrichment step, not a hard requirement for the
    conversation to continue — a hard crash here surfaced to the user as the M2
    turn producing no reply (i.e. "stuck"). Degrade to an empty citation list and
    let synthesis proceed; the user can refine or upload papers afterwards.
    """
    try:
        return _scout(topic)
    except Exception:  # noqa: BLE001 - scout is best-effort; must not wedge M2
        logger.warning("M2 phase2 scout failed for %r; continuing with no "
                       "auto-sourced citations", topic, exc_info=True)
        return []


def _get_llm():
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.5-flash"),
        temperature=0.5,
    )


def _scout(topic: str, min_n: int = 20) -> list[dict]:
    # Indirection allows monkeypatching in tests without touching the tool itself
    return scout_citations.invoke({"topic": topic, "min_n": min_n})


_PAGE_PLACEHOLDER_RE = re.compile(
    # Match the optional comma + space, then 'p.' or 'pp.' (optional), then
    # whitespace and the placeholder token. We bind the whole ', p. page?' or
    # ', [page?]' or 'p.?' shapes so deleting the match leaves the surrounding
    # punctuation tidy.
    r"(?:,\s*)?"                                  # optional leading ', '
    r"(?:\[)?"                                    # optional opening '['
    r"(?:p\.?\s*)?"                               # optional 'p.' or 'p'
    r"(?:page\s*\?|\?)"                           # the placeholder itself
    r"(?:\])?"                                    # optional closing ']'
    , re.IGNORECASE,
)


def _scrub_page_placeholders(text: str) -> str:
    """Strip '[page?]', 'p. page?', 'p.?', etc. from synthesized prose.

    Defense-in-depth: the M2 style guide tells the model to OMIT the page
    when unknown, but models drift. Without this cleanup, the user sees
    '(Vickery, 2023, [page?])' four times in a single paragraph (the exact
    bug report Z). Real numeric pages like 'p. 118' survive — only the
    placeholder shapes are removed.
    """
    return _PAGE_PLACEHOLDER_RE.sub("", text)


def _max_synth_seconds() -> int:
    """Wall-clock cap for one synthesize call. Default 90s — generous enough
    for Gemini's normal range but short enough that a stalled call (5+ min)
    falls back to the template instead of hanging M2 indefinitely."""
    return int(os.getenv("M2_SYNTHESIZE_MAX_SECONDS", "90"))


def _citations_block(citations: list) -> str:
    return "\n".join(
        f"- {c.get('authors', '?')} ({c.get('year', '?')}). {c.get('title', '?')}."
        for c in citations[:30]
    )


def _templated_synthesis(state: M2SubGraphState, citations: list,
                         refinements: list[str], reason: str = "") -> str:
    """Deterministic fallback when the LLM synthesize times out / fails.

    Always produces a usable research_state_draft so M2 can advance — the agent
    can re-synthesize later in interactive mode if the user refines. Cites the
    scout's actual finds so M5's chapter composition has real references.
    """
    title = state.get("research_title", "this topic")
    rtype = state.get("research_type", "study")
    bullets = _citations_block(citations) or "- (no auto-sourced citations available)"
    refines = ("\n\nRefinements requested: " + "; ".join(refinements)) if refinements else ""
    note = f"\n\n_Note: auto-templated synthesis — {reason}._" if reason else ""
    return (
        f"## Current state of research — {title}\n\n"
        f"The current literature on \"{title}\" — examined here from a {rtype} "
        f"perspective — draws on the following sources:\n\n"
        f"{bullets}\n\n"
        f"These works together establish the conceptual and empirical groundwork "
        f"for the present study. Further synthesis (theoretical lenses, debates, "
        f"and gaps) will be developed in subsequent iterations.{refines}{note}"
    )


def _synthesize(state: M2SubGraphState, refinements: list[str]) -> str:
    """Generate the research-state writeup. Bounded LLM call + safe fallback.

    Gemini's invoke() occasionally takes 5+ minutes for a single call (its
    internal retries respect per-RPC timeouts but the wall-clock blows out),
    which used to hang the entire M2 turn. bounded_invoke caps the wall-clock
    and on timeout/error we fall back to a templated synthesis built from the
    citations — M2 always advances, never hangs the graph.
    """
    citations = state.get("research_state_citations", [])
    refinement_block = ""
    if refinements:
        refinement_block = "User refinements:\n" + "\n".join(f"- {r}" for r in refinements)
    n = len(citations)
    # Z: explicit per-call steer. The previous prompt let the model cite the
    # same paper four times because nothing budgeted distinct sources. Now we
    # name the floor ("at least N") and forbid the placeholder shapes that
    # the style guide already told it to avoid (belt-and-braces — model
    # compliance drops when only one place mentions the rule).
    diversity_floor = max(3, min(n, n // 2 + 1)) if n else 0
    diversity_note = (
        f"You have {n} citations available below. Weave in as many distinct "
        f"sources as you can — at least {diversity_floor} different "
        f"author-year pairs should appear in your synthesis. Do NOT cite the "
        f"same source repeatedly when others are relevant. Cite as "
        f"(Author, Year). NEVER include a placeholder page marker (e.g. a "
        f"question mark in brackets, or 'p.' followed by '?'). If you don't "
        f"have the page number, omit the page reference entirely."
    ) if n else ""
    user_prompt = (
        f"{_STYLE}\n\n{_PROMPT}\n\n"
        f"Topic: {state.get('research_title')}\n"
        f"Research type: {state.get('research_type')}\n"
        f"Language: {state.get('language')}\n\n"
        f"{diversity_note}\n\n"
        f"Citations available:\n{_citations_block(citations)}\n\n"
        f"{refinement_block}"
    )
    try:
        raw = bounded_invoke(_get_llm(), user_prompt,
                             max_seconds=_max_synth_seconds(), retries=0).content
        # Z: scrub leftover placeholder markers even when the model obeys the
        # prompt 90% of the time. One '[page?]' in an otherwise good draft
        # still looks broken to the user.
        return _scrub_page_placeholders(raw)
    except BoundedInvokeTimeout:
        logger.warning("M2 phase2 synthesize hit %ss wall-clock cap; using template",
                       _max_synth_seconds())
        return _templated_synthesis(state, citations, refinements,
                                    reason=f"LLM exceeded {_max_synth_seconds()}s")
    except Exception:  # noqa: BLE001 - never let synthesize wedge M2
        logger.exception("M2 phase2 synthesize failed; using template")
        return _templated_synthesis(state, citations, refinements,
                                    reason="LLM error")


def run(state: M2SubGraphState) -> dict:
    mode = state.get("mode", "interactive")

    # Auto mode: scout → synthesize → advance in one shot
    if mode == "auto":
        citations = state.get("research_state_citations") or _safe_scout(state.get("research_title", ""))
        # B1 GATE (auto): if scout came back empty AND no uploaded papers, log
        # loud + leave research_state UNCONFIRMED so the downstream auto chain
        # doesn't silently produce a thesis full of '(Author, Year)' fakes.
        # The autodraft run will halt here — the caller surfaces this status.
        if not citations and not state.get("paper_uris"):
            msg = _no_citations_help_message(state.get("research_title", ""))
            logger.warning("M2 phase2 [auto]: scout returned 0 citations and no "
                           "papers uploaded — halting before gap_analysis")
            return {
                "research_state_citations": [],
                "research_state_draft": msg,
                "_citation_search_failed": True,
                "research_state_confirmed": False,
                # NOTE: NOT advancing current_phase — auto run stops here.
            }
        new_state = dict(state)
        new_state["research_state_citations"] = citations
        draft = _synthesize(new_state, refinements=[])
        return {
            "research_state_citations": citations,
            "research_state_draft": draft,
            "research_state_confirmed": True,
            "current_phase": "gap_analysis",
        }

    last_user = next(
        (text_of(m) for m in reversed(state.get("messages") or [])
         if isinstance(m, HumanMessage)),
        "",
    )

    # First call: no draft yet — scout citations and synthesize
    if not state.get("research_state_draft"):
        citations = _safe_scout(state.get("research_title", ""))
        # B1 HARD GATE: if scout came back empty AND the user has not uploaded
        # papers, refuse to advance. Without this, phase3 was generating "gaps"
        # with literal placeholder strings ({"author": "Author", "year": "Year",
        # "page": "page?"}) because the LLM had no real citations to cite and
        # the prompt asked it to cite anyway. Fail loudly here so the user can
        # refine the title or upload papers — never silently fabricate.
        if not citations and not state.get("paper_uris"):
            msg = _no_citations_help_message(state.get("research_title", ""))
            return {
                "research_state_citations": [],
                "research_state_draft": msg,
                "_citation_search_failed": True,
                "research_state_confirmed": False,
                "messages": [AIMessage(content=msg)],
            }
        new_state = dict(state)
        new_state["research_state_citations"] = citations
        draft = _synthesize(new_state, refinements=state.get("research_state_refinements", []))
        # W3: every synthesis draft ships with the confirm/refine/navigate card
        # grid so the user clicks instead of typing.
        hint = _confirm_hint()
        ai = AIMessage(content=draft, additional_kwargs={"tool_calls_json": hint})
        return {
            "research_state_citations": citations,
            "research_state_draft": draft,
            "research_state_confirmed": False,
            "messages": [ai],
            "tool_calls_json": hint,
        }

    # Draft exists: classify what the user wants to do with it
    intent = classify_phase_intent(
        last_user_message=last_user,
        current_phase=_PHASE_KEY,
        mode="interactive",
    )

    # B1 RECOVERY: if the prior scout failed, the only useful actions are
    # navigate (back to M1 to fix the title) or refine-with-new-search-terms
    # (re-runs scout with whatever the user typed). Block confirm — the user
    # must not be able to lock in an empty research state.
    if state.get("_citation_search_failed"):
        if intent.action == "navigate":
            return {"current_phase": intent.target_phase or "familiarize"}
        if intent.action == "refine":
            new_terms = (intent.refinement_text or last_user).strip()
            citations = _safe_scout(new_terms)
            if citations:
                # Recovered — clear the flag and synthesize with these citations.
                new_state = dict(state)
                new_state["research_state_citations"] = citations
                draft = _synthesize(new_state, refinements=[])
                # W3: recovery path also gets the confirm card grid — same UX
                # whether this is the first draft or the comeback after retry.
                hint = _confirm_hint()
                ai = AIMessage(content=draft,
                               additional_kwargs={"tool_calls_json": hint})
                return {
                    "research_state_citations": citations,
                    "research_state_draft": draft,
                    "_citation_search_failed": False,
                    "research_state_confirmed": False,
                    "messages": [ai],
                    "tool_calls_json": hint,
                }
            return {
                "messages": [AIMessage(content=(
                    f"Still no citations for \"{new_terms[:80]}\". "
                    "Try different keywords, or upload papers."
                ))],
            }
        # confirm / select / other → re-emit the help message; don't advance.
        return {
            "messages": [AIMessage(content=(
                "I still don't have any citations to work with. Please "
                "go back to refine the title, give me new search terms, "
                "or upload papers — I won't advance with empty sources."
            ))],
        }

    if intent.action == "navigate":
        # Navigate back to a prior phase
        return {"current_phase": intent.target_phase or "familiarize"}

    if intent.action == "confirm":
        return {
            "research_state_confirmed": True,
            "current_phase": "gap_analysis",
        }

    if intent.action == "refine":
        counts = dict(state.get("regeneration_count") or {})
        current_count = counts.get(_PHASE_KEY, 0)
        if current_count >= _regen_cap():
            # Hit the cap — block further regen and prompt the user
            return {
                "messages": [AIMessage(content=(
                    f"We've regenerated {_regen_cap()} times — let's lock this in "
                    "or move on. Reply 'confirm' to advance, or 'force-continue' "
                    "to bypass the cap once."
                ))],
            }
        counts[_PHASE_KEY] = current_count + 1
        refinements = list(state.get("research_state_refinements") or []) + [
            intent.refinement_text or last_user
        ]
        new_state = dict(state)
        new_state["research_state_refinements"] = refinements
        # Reuse cached citations — no re-scout on refine
        draft = _synthesize(new_state, refinements=refinements)
        hint = _confirm_hint()  # W3: same cards on the refined draft
        ai = AIMessage(content=draft, additional_kwargs={"tool_calls_json": hint})
        return {
            "research_state_refinements": refinements,
            "regeneration_count": counts,
            "research_state_draft": draft,
            "messages": [ai],
            "tool_calls_json": hint,
        }

    # Ambiguous input — ask for clarification
    return {
        "messages": [AIMessage(content=(
            "I'm not sure what you'd like. Reply 'confirm' to advance, "
            "or describe how you'd like the synthesis changed."
        ))],
    }

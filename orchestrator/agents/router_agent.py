"""Stage-1 router agent — conversational supervisor that owns the dialogue
and delegates per-turn work to module subagents via tool calls.

Replaces orchestrator/agents/supervisor.py + the conditional edges in
orchestrator/graph.py with ONE LangGraph node (`router_agent_node`,
defined in graph_v2.py) that calls this module's `route_turn(state)` and
returns the same state-patch shape the old `_agent_node_factory` produced.
Modules themselves are unchanged.

## Why not langgraph.prebuilt.create_react_agent

The plan-agent recommended `create_react_agent`. After looking at the
contract more closely, ReAct's loop (LLM → tool → LLM → tool …) is
overkill for our use case: we want EXACTLY ONE tool call per turn (the
tool itself owns the user-facing reply and decides whether to wait for
the user). The simpler shape is:

  1. LLM.bind_tools(tools, tool_choice="any").invoke(messages)
  2. Dispatch the first tool_call to the matching @tool function.
  3. Read the scratchpad for the resulting ModuleStepResult.

This is cheaper (no agent scratchpad accumulation, no second LLM call to
"summarize the tool result" that we'd just throw away), easier to test
(no nested graph), and more deterministic (no possibility of the agent
deciding to call a second tool or reply in prose).

## Short-circuits

Two paths skip the LLM call entirely, because the right tool is obvious:

  - **Cold-start**: no module confirmed yet → call M1. The first turn of
    every project is M1, no exceptions.
  - **Awaiting-field**: any module slice has `_awaiting_field` set → call
    THAT module. The user is answering a pending question; routing
    elsewhere would lose the answer. This also fixes the live regression
    where domain answers like "PLS-SEM" got mis-classified as nav by an
    LLM-only router.

The LLM only fires when neither short-circuit applies — i.e. when no
module is currently mid-question AND at least one is confirmed (so there
are genuine routing choices).
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from orchestrator.agents.base import ModuleStepResult, bounded_invoke
from orchestrator.agents.module_tools import (
    _AGENT_BY_KEY, _CURRENT_STATE, _TOOL_RESULTS, ALL_TOOLS,
)
from orchestrator.agents.read_handler import (
    Intent, classify_intent_heuristic, read_slice,
)
from orchestrator.message_utils import text_of
from orchestrator.state import (
    OrchestratorState, get_module_slice, next_unconfirmed_module,
)

logger = logging.getLogger(__name__)


_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "router.md"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text()

_MODULE_KEYS = ("M1", "M2", "M3", "M4", "M5")
_TOOL_NAME_TO_KEY = {
    "m1_topic_step": "M1",
    "m2_literature_step": "M2",
    "m3_design_step": "M3",
    "m4_analysis_step": "M4",
    "m5_writing_step": "M5",
}


def _router_llm():
    """Gemini Flash for routing — same model the modules use so we don't
    pay for a second model warm-up. temperature=0 + bind_tools(tool_choice
    ="any") enforces deterministic tool selection."""
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_ROUTER_MODEL",
                        os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.5-flash")),
        temperature=0.0,
        timeout=int(os.getenv("ORCHESTRATOR_LLM_TIMEOUT", "20")),
    )


def _router_max_seconds() -> int:
    """Wall-clock cap on the router LLM call. Short by default — routing
    is a small prompt and Gemini usually answers in 1–2s. On timeout we
    fall back to the rule-based pick."""
    return int(os.getenv("ORCHESTRATOR_ROUTER_MAX_SECONDS", "8"))


def _build_digest(state: OrchestratorState) -> str:
    """One-line-per-module summary the router LLM uses to decide.

    Includes only routing-relevant facts: confirmed/not, what field is
    awaiting answer (if any), and the count of filled fields (rough
    progress indicator). The actual content of each slice stays out of
    the router prompt — keeps tokens low and forces the router to
    delegate when the user asks content questions (the module sees the
    full slice via state)."""
    cs = state["context_store"]
    lines: list[str] = []
    for key in _MODULE_KEYS:
        slice_ = get_module_slice(cs, key)
        confirmed = "confirmed" if slice_.get("confirmed_at") else "not confirmed"
        awaiting = slice_.get("_awaiting_field")
        filled = sum(1 for k, v in slice_.items()
                     if not k.startswith("_") and k != "confirmed_at"
                     and v not in (None, "", []))
        bits = [confirmed, f"{filled} field(s) filled"]
        if awaiting:
            bits.append(f"AWAITING field '{awaiting}'")
        lines.append(f"- {key}: {'; '.join(bits)}")
    nxt = next_unconfirmed_module(cs)
    lines.append(f"\nNext unconfirmed (sequential rule): {nxt}")
    return "\n".join(lines)


def _any_module_confirmed(cs) -> bool:
    """True if at least one module has been confirmed. Mirrors the helper
    in supervisor.py — duplicated here so this module doesn't import
    supervisor.py (which Stage 1 keeps around but routes around)."""
    for key in _MODULE_KEYS:
        if get_module_slice(cs, key).get("confirmed_at"):
            return True
    return False


def _awaiting_module(cs) -> str | None:
    """Return the module key whose slice has `_awaiting_field` set, if any.

    Walks in canonical order so the result is deterministic if (for some
    odd reason — shouldn't happen) two slices both have the flag. The
    first one wins; the supervisor used to allow this implicitly via
    `current_module` and we preserve that ordering."""
    for key in _MODULE_KEYS:
        if get_module_slice(cs, key).get("_awaiting_field"):
            return key
    return None


def _pick_module_via_llm(state: OrchestratorState) -> str:
    """Ask the router LLM which module-tool to call. Returns the module
    key (e.g. "M3"). Falls back to next_unconfirmed_module on any LLM
    failure — better to route by rules than to hang the turn."""
    last_user = next(
        (text_of(m) for m in reversed(state.get("messages") or [])
         if isinstance(m, HumanMessage)),
        "",
    )
    digest = _build_digest(state)
    # tool_choice="any" forces a tool call (no free-text reply). Gemini's
    # function-calling honors this; we don't need create_react_agent's
    # loop for our one-tool-per-turn contract.
    llm = _router_llm().bind_tools(ALL_TOOLS, tool_choice="any")
    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        SystemMessage(content=f"Project context digest:\n{digest}"),
        HumanMessage(content=last_user or "(no user message)"),
    ]

    t0 = time.monotonic()
    try:
        ai = bounded_invoke(
            llm, messages,
            max_seconds=_router_max_seconds(),
            retries=0,
        )
    except Exception:
        # Any LLM failure (timeout, parse, transport) → fall back to rules.
        # Logging at exception level so prod can see when this kicks in.
        logger.exception("router LLM failed; falling back to next_unconfirmed_module")
        return next_unconfirmed_module(state["context_store"])
    latency_ms = int((time.monotonic() - t0) * 1000)

    tool_calls = getattr(ai, "tool_calls", None) or []
    if not tool_calls:
        # Shouldn't happen with tool_choice="any", but defend against it —
        # Gemini occasionally returns content="" with no tool_calls under
        # safety filters. Fall back to rules in that case.
        logger.warning(
            "router LLM returned no tool_calls (latency_ms=%d); falling back",
            latency_ms,
        )
        return next_unconfirmed_module(state["context_store"])

    tool_name = tool_calls[0].get("name") if isinstance(tool_calls[0], dict) \
        else tool_calls[0].name
    picked = _TOOL_NAME_TO_KEY.get(tool_name)
    if picked is None:
        logger.warning("router LLM picked unknown tool %r; falling back", tool_name)
        return next_unconfirmed_module(state["context_store"])

    logger.info(
        "router decision: tool=%s module=%s latency_ms=%d",
        tool_name, picked, latency_ms,
    )
    return picked


def route_turn(state: OrchestratorState) -> tuple[str, ModuleStepResult, Intent]:
    """Drive ONE conversational turn: pick target module, classify intent,
    dispatch read OR step, return (module_key, ModuleStepResult, intent).

    Brief §1.5 — three intents:
      - continue: target == focus → run module.step() (normal work)
      - read:     target != focus AND user is asking ABOUT it → run
                  read_slice (returns a ModuleStepResult with empty
                  context_patch so no downstream code writes the slice)
      - mutate:   target != focus AND user wants to edit → run
                  module.step() (graph_v2 then propagates needs_review)

    The intent return value lets graph_v2.router_agent_node skip the
    propagation block when intent == 'read' (defense in depth — the
    no-write guard already covers it, but an explicit intent flag means
    no surprise propagation if a future read_handler change starts
    writing the slice).

    Mode handling: auto-mode is NOT migrated in Stage 1 (per the
    architectural plan). graph_v2 routes interactive-mode traffic only;
    the v1 graph still owns auto-mode end-to-end. So we don't need a
    mode='auto' branch here — if we somehow get one, fall through to the
    LLM router (which will pick the next unconfirmed module anyway).
    """
    cs = state["context_store"]

    # Short-circuit 1: cold-start → M1, no LLM call. Always continue.
    if not _any_module_confirmed(cs):
        logger.debug("router: cold-start short-circuit → M1")
        picked = "M1"
        intent: Intent = "continue"
    else:
        # Short-circuit 2: a module is mid-question (`_awaiting_field` set)
        # → that module owns this turn. Prevents domain answers like
        # "PLS-SEM" from being mis-classified by the LLM as a nav request.
        # Always continue — the user is answering, not asking or editing.
        awaiting = _awaiting_module(cs)
        if awaiting is not None:
            logger.debug("router: awaiting-field short-circuit → %s", awaiting)
            picked = awaiting
            intent = "continue"
        else:
            picked = _pick_module_via_llm(state)
            intent = "continue"  # default; overridden below when cross-module

    # next_unconfirmed_module can return "DONE" when everything is
    # confirmed; we don't have a tool for that. In that case the LLM
    # router path will return "DONE" too. Treat DONE as M5 (the last
    # module, the only one that can sensibly "handle" a post-completion
    # message like "edit chapter 3"). v1 routes DONE → END instead; in
    # v2 we don't END the graph here — we just call M5 and let it
    # respond appropriately (it has the data; it can answer questions
    # about the finished thesis).
    if picked == "DONE":
        picked = "M5"

    # Intent classification — only matters for cross-module turns
    # (target != focus). Same-module work is always 'continue'. Brief §1.5
    # explicitly scopes read/mutate to cross-module interactions.
    focus = state.get("focus")
    last_user = next(
        (text_of(m) for m in reversed(state.get("messages") or [])
         if isinstance(m, HumanMessage)),
        "",
    )
    if focus is not None and picked != focus and intent == "continue":
        # Try heuristic first — read prefixes / edit verbs are unambiguous.
        # LLM intent classification could go here as a fallback (per the
        # design doc's 3-tool tool_choice), but the heuristic catches the
        # cases from the brief's §4 worked example, so we ship the cheap
        # path now and add LLM fallback if production turns up ambiguous
        # cases the heuristic misses.
        heur = classify_intent_heuristic(last_user, target_is_focus=False)
        if heur == "read":
            intent = "read"
        elif heur == "mutate":
            intent = "mutate"
        else:
            # No clear signal → treat cross-module as mutate by default.
            # Safer than read in the ambiguous case: a missed mutate
            # leaves stale downstream needs_review unflagged (bad), while
            # a "mutate" that doesn't actually write the slice is caught
            # by the no-write guard in graph_v2 → no propagation, no harm.
            intent = "mutate"

    # Dispatch.
    if intent == "read":
        text = read_slice(picked, last_user, cs)
        # Wrap in a ModuleStepResult shaped like a paused module turn so
        # graph_v2 emits the AI message without writing a slice. transition
        # = True because the read is complete (no follow-up); context_patch
        # = the existing slice unchanged so the no-write guard recognizes
        # this as a non-mutate.
        result = ModuleStepResult(
            assistant_message=text,
            context_patch=get_module_slice(cs, picked),
            transition=True,
            needs_user_reply=False,
        )
        return picked, result, intent

    agent = _AGENT_BY_KEY[picked]
    result = agent.step(state)
    return picked, result, intent

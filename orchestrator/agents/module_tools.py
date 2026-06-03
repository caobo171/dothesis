"""Module-as-tool wrappers exposed to the Stage-1 router agent.

Each of the five thesis modules (M1..M5) becomes a single tool the router
can call. The tool body is a thin wrapper around the existing
`ModuleAgent.step()` — modules themselves are UNCHANGED in Stage 1; only
the routing layer above them is being replaced.

## Why contextvars instead of tool arguments

A LangChain `@tool` exposes its argument schema to the LLM as JSON Schema.
We can't make the LLM produce an `OrchestratorState` (it's a giant nested
TypedDict with non-JSON-serializable BaseMessage objects), so we keep the
state out of the tool's visible signature and stash it in a contextvar that
the router_agent_node sets at the start of each turn. The tool body reads
it, runs the module, and writes the result back through a "scratchpad"
contextvar that the router node drains after the React agent finishes.

This is the same pattern LangChain itself recommends for hidden tool state
(see langchain docs > "Pass run time values to tools"): the LLM sees only
the semantic argument (`user_intent`), while the framework injects the
plumbing values via context.

## Why a scratchpad list (not a single var)

The React agent can call multiple tools per turn (rare in our flow, but
possible if it decides to backfill). Each call's result needs to survive
back to the router_agent_node so it can pick the LAST one as the user-
facing reply (the others are intermediate). A list preserves the order;
the node reads `[-1]` for the final result.
"""
from __future__ import annotations

import contextvars
import logging
from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from orchestrator.agents.base import ModuleStepResult
from orchestrator.agents.m1_topic import M1Agent
from orchestrator.agents.m2 import M2Agent
from orchestrator.agents.m3_design import M3Agent
from orchestrator.agents.m4_analysis import M4Agent
from orchestrator.agents.m5_writing import M5Agent
from orchestrator.state import OrchestratorState

logger = logging.getLogger(__name__)


# Agent singletons — matches the v1 graph (orchestrator/graph.py:_AGENT_BY_KEY).
# ModuleAgent.step() is stateless; all mutable data lives in OrchestratorState,
# so one instance per process is fine and avoids re-paying the prompt-load cost.
_AGENT_BY_KEY = {
    "M1": M1Agent(),
    "M2": M2Agent(),
    "M3": M3Agent(),
    "M4": M4Agent(),
    "M5": M5Agent(),
}


# Hidden state plumbing — set by router_agent_node at the start of each turn,
# read by the tool bodies. Default to None so accidental tool calls outside a
# router turn raise a clear error instead of silently corrupting state.
_CURRENT_STATE: contextvars.ContextVar[OrchestratorState | None] = (
    contextvars.ContextVar("router_current_state", default=None)
)

# Each tool call appends its (module_key, ModuleStepResult) here. The router
# node drains the list after the React agent returns to pick the final reply.
# A list (not a single var) because the agent MAY call multiple tools per turn
# during backfill; the last one is the user-facing reply.
_TOOL_RESULTS: contextvars.ContextVar[list[tuple[str, ModuleStepResult]] | None] = (
    contextvars.ContextVar("router_tool_results", default=None)
)


class ModuleToolInput(BaseModel):
    """LLM-facing argument schema. Kept intentionally small — the module
    itself reads the full conversation from state; this string is just a
    nudge the LLM uses to justify its tool choice, and a debug breadcrumb."""
    user_intent: str = Field(
        description=(
            "One short line describing what the user wants from this module "
            "(e.g. 'continue answering the current question', 'show me the "
            "literature review', 'revise the research topic'). The module "
            "reads the full conversation from state, so this is mostly a "
            "self-justification for which tool you picked."
        )
    )


def _run_module(module_key: Literal["M1", "M2", "M3", "M4", "M5"],
                user_intent: str) -> str:
    """Shared body for the five per-module tool functions.

    Returns a short status string for the LLM (the React agent uses this
    to decide whether to stop or call another tool). The actual user-facing
    `assistant_message` flows through the scratchpad — the LLM doesn't see
    or paraphrase it (that would risk distortion).
    """
    state = _CURRENT_STATE.get()
    scratchpad = _TOOL_RESULTS.get()
    if state is None or scratchpad is None:
        # Defensive: a tool call outside a router turn is a programmer error
        # (the router_agent_node forgot to bind contextvars). Fail loud.
        raise RuntimeError(
            "Module tool called outside a router turn — "
            "router_agent_node must bind _CURRENT_STATE and _TOOL_RESULTS first."
        )

    agent = _AGENT_BY_KEY[module_key]
    logger.info("router: invoking %s tool (intent=%r)", module_key, user_intent[:80])
    result = agent.step(state)
    scratchpad.append((module_key, result))

    # Status hint for the LLM. Two outcomes only: the module advanced (probably
    # done for this turn unless backfill is needed) or it paused for the user.
    # We don't return the full assistant_message — the framework handles that;
    # exposing the content would tempt the LLM to summarise/restate it.
    if result.transition:
        return (
            f"{module_key} advanced (this step is complete). "
            f"You should stop and let the user reply."
        )
    return (
        f"{module_key} is waiting for the user's reply. Stop now."
    )


@tool("m1_topic_step", args_schema=ModuleToolInput)
def m1_topic_step(user_intent: str) -> str:
    """Run one turn of the M1 (Topic) module: research topic, questions,
    objectives, scope. Use when the user wants to work on or revisit topic-
    level decisions, or when M1 is the next unconfirmed module."""
    return _run_module("M1", user_intent)


@tool("m2_literature_step", args_schema=ModuleToolInput)
def m2_literature_step(user_intent: str) -> str:
    """Run one turn of the M2 (Literature) module: paper search, gap
    analysis, literature review. Use when the user wants to work on or
    revisit the literature, or asks to see/reformat existing lit data."""
    return _run_module("M2", user_intent)


@tool("m3_design_step", args_schema=ModuleToolInput)
def m3_design_step(user_intent: str) -> str:
    """Run one turn of the M3 (Design) module: research design, conceptual
    model, scale items / interview guide, sampling. Use when the user wants
    to work on or revisit design decisions, or asks to see/reformat
    questionnaire / themes / constructs."""
    return _run_module("M3", user_intent)


@tool("m4_analysis_step", args_schema=ModuleToolInput)
def m4_analysis_step(user_intent: str) -> str:
    """Run one turn of the M4 (Analysis) module: data analysis (PLS-SEM,
    regression, thematic coding, …). Use when the user wants to work on
    analysis, or asks about analysis results."""
    return _run_module("M4", user_intent)


@tool("m5_writing_step", args_schema=ModuleToolInput)
def m5_writing_step(user_intent: str) -> str:
    """Run one turn of the M5 (Writing) module: chapter drafting and
    assembly. Use when the user wants to work on the written draft, or
    asks about chapter content."""
    return _run_module("M5", user_intent)


# Ordered tool list — the router agent registers these as its toolbox.
ALL_TOOLS = [
    m1_topic_step,
    m2_literature_step,
    m3_design_step,
    m4_analysis_step,
    m5_writing_step,
]

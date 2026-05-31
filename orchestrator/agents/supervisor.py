"""Supervisor — routes between module agents based on rules + (interactive only) LLM intent."""
from __future__ import annotations

import logging
import os
from typing import Literal

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from orchestrator.message_utils import text_of
from orchestrator.state import (
    ModuleKey, OrchestratorState, get_module_slice, next_unconfirmed_module,
)

logger = logging.getLogger(__name__)


class RouteDecision(BaseModel):
    next_module: Literal["M1", "M2", "M3", "M4", "M5", "DONE"]
    reason: str
    needs_user_acknowledgement: bool = False


class IntentClassification(BaseModel):
    wants_navigation: bool = Field(...)
    target_module: Literal["M1", "M2", "M3", "M4", "M5"] | None = None
    confidence: float = 0.0


def _intent_llm():
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.5-flash"),
        temperature=0.0,
    )


def _rule_based(state: OrchestratorState) -> RouteDecision:
    nxt = next_unconfirmed_module(state["context_store"])
    return RouteDecision(
        next_module=nxt,
        reason="sequential" if nxt != "DONE" else "all_modules_confirmed",
    )


def supervisor_node(state: OrchestratorState) -> dict:
    """Returns a state patch with the updated current_module."""
    # Targeted routing (enter-at-any-step): when the user is heading for a
    # specific artifact, let the planner pick the next step toward it —
    # backfilling missing prerequisites — instead of the sequential rule. Active
    # ONLY when target_artifact is set, so the default flow is byte-for-byte
    # unchanged. Cleared once the target is reached (resume normal sequence).
    target = state.get("target_artifact")
    target_reached = False
    if target:
        from orchestrator.artifacts import artifact_to_module
        from orchestrator.planner import plan_next
        try:
            pdec = plan_next(state["context_store"], target=target)
        except KeyError:
            pdec = None  # unknown target → drop it, resume normal routing
        if pdec and pdec.action in ("work", "backfill"):
            module = artifact_to_module(pdec.artifact)
            return {
                "current_module": module,
                "pending_confirmations": [RouteDecision(
                    next_module=module,
                    reason=f"targeting {target}: {pdec.reason}",
                    needs_user_acknowledgement=(pdec.action == "backfill"),
                ).model_dump_json()],
            }
        target_reached = True  # already_done / done / unknown → clear below

    decision = _rule_based(state)

    if state.get("mode") == "interactive":
        last_user = next(
            (text_of(m) for m in reversed(state.get("messages") or [])
             if isinstance(m, HumanMessage)),
            "",
        )
        # Skip nav classification while the current module is mid-question: the
        # user's reply is an ANSWER to a field/confirm, not a navigation request.
        # The classifier over-triggers on domain answers — "PLS-SEM"/"SmartPLS"
        # wrongly jumped M3→M4, "quantitative survey" jumped to M3 — derailing
        # the flow. Genuine navigation mid-collection is still caught by the
        # module's own intent classifier. We only consult the nav classifier when
        # the current module is NOT awaiting input.
        cur_slice = get_module_slice(state["context_store"], decision.next_module)
        mid_question = ("_awaiting_field" in cur_slice
                        or "_awaiting_confirm" in cur_slice
                        or "_phase_state" in cur_slice)
        # Always ask the LLM whether the user wants cross-module navigation.
        # Confidence threshold (>=0.7) protects against false positives.
        if last_user and not mid_question:
            try:
                llm = _intent_llm().with_structured_output(IntentClassification)
                intent = llm.invoke(
                    f"Is the user requesting navigation to a specific module "
                    f"(M1=topic, M2=literature, M3=design, M4=analysis, "
                    f"M5=writing)? Message: {last_user}"
                )
                if intent.wants_navigation and intent.confidence >= 0.7 and intent.target_module:
                    decision = RouteDecision(
                        next_module=intent.target_module,
                        reason=f"user requested {intent.target_module}",
                        needs_user_acknowledgement=True,
                    )
            except Exception:
                logger.exception("supervisor intent classifier failed; falling back to rules")

    patch = {
        "current_module": decision.next_module,
        "pending_confirmations": [decision.model_dump_json()],
    }
    if target_reached:
        patch["target_artifact"] = None  # drop the reached target; resume sequence
    return patch


def route_from_supervisor(state: OrchestratorState) -> str:
    """Used by graph.py's add_conditional_edges."""
    return state["current_module"]

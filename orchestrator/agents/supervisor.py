"""Supervisor — routes between module agents based on rules + (interactive only) LLM intent."""
from __future__ import annotations

import logging
import os
from typing import Literal

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from orchestrator.message_utils import text_of
from orchestrator.state import ModuleKey, OrchestratorState, next_unconfirmed_module

logger = logging.getLogger(__name__)

_NAV_KEYWORDS = (
    "go back", "skip", "redo", "i already have", "jump to", "start over",
    "quay lại", "bỏ qua", "làm lại",
)


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


def _looks_like_navigation(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in _NAV_KEYWORDS)


def _rule_based(state: OrchestratorState) -> RouteDecision:
    nxt = next_unconfirmed_module(state["context_store"])
    return RouteDecision(
        next_module=nxt,
        reason="sequential" if nxt != "DONE" else "all_modules_confirmed",
    )


def supervisor_node(state: OrchestratorState) -> dict:
    """Returns a state patch with the updated current_module."""
    decision = _rule_based(state)

    if state.get("mode") == "interactive":
        last_user = next(
            (text_of(m) for m in reversed(state.get("messages") or [])
             if isinstance(m, HumanMessage)),
            "",
        )
        if last_user and _looks_like_navigation(last_user):
            try:
                llm = _intent_llm().with_structured_output(IntentClassification)
                intent = llm.invoke(
                    f"Is the user requesting navigation to a specific module? "
                    f"Message: {last_user}"
                )
                if intent.wants_navigation and intent.confidence >= 0.7 and intent.target_module:
                    decision = RouteDecision(
                        next_module=intent.target_module,
                        reason=f"user requested {intent.target_module}",
                        needs_user_acknowledgement=True,
                    )
            except Exception:
                logger.exception("supervisor intent classifier failed; falling back to rules")

    return {
        "current_module": decision.next_module,
        "pending_confirmations": [decision.model_dump_json()],
    }


def route_from_supervisor(state: OrchestratorState) -> str:
    """Used by graph.py's add_conditional_edges."""
    return state["current_module"]

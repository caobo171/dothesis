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
    # timeout=20 matches base.py:_get_llm; without it, a stalled Gemini call
    # could block every single interactive turn (it runs before any module).
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.5-flash"),
        temperature=0.0,
        timeout=int(os.getenv("ORCHESTRATOR_LLM_TIMEOUT", "20")),
    )


def _nav_max_seconds() -> int:
    """Wall-clock cap for the nav classifier; the request-level timeout alone
    isn't enough (Gemini's internal retries can stretch wall-clock past it).
    8s default: a small simple prompt should answer in 1-2s — if Gemini takes
    longer, the rule-based fallback is fine and the user shouldn't wait."""
    return int(os.getenv("ORCHESTRATOR_NAV_MAX_SECONDS", "8"))


_SLICE_FIELDS = ("m1_topic", "m2_literature", "m3_design",
                 "m4_analysis", "m5_writing")

_MODULE_KEYS: tuple[str, ...] = ("M1", "M2", "M3", "M4", "M5")


def _awaiting_module_and_field(cs) -> tuple[str | None, str | None]:
    """Return (module_key, field_name) of whichever slice has _awaiting_field
    set, or (None, None) if no module is mid-question.

    Used to give the nav classifier the missing context that caused the
    'PLS-SEM mid-design routes to M4' bug — without the awaiting field in
    the prompt, the LLM has no way to know the user's reply is an ANSWER
    rather than a navigation request to a different module.
    """
    for key in _MODULE_KEYS:
        slice_ = get_module_slice(cs, key)
        field = slice_.get("_awaiting_field")
        if field:
            return key, field
    return None, None


def _build_nav_prompt(last_user: str, awaiting_module: str | None,
                      awaiting_field: str | None) -> str:
    """Nav classifier prompt. Includes mid-question context when applicable so
    the classifier doesn't mis-fire domain answers as nav requests.

    Live bug fixed: when M3 was asking for `design` and the user picked
    'PLS-SEM', the prior one-line prompt sent only the message to Gemini.
    Gemini saw a M4-flavored term (PLS-SEM is analyzed in SmartPLS, an M4
    tool) and returned target_module=M4 with high confidence. The
    cross-module guard in supervisor_node then honored it and jumped the
    user into M4 mid-design-pick.

    The awaiting-field block tells the classifier the prior probability of
    'this is an answer to the pending question' is ~1, so domain terms that
    overlap module vocabularies (PLS-SEM, ANOVA, SmartPLS, convenience
    sampling, …) are correctly classified as answers, not navigation.
    Block is conditional — when no module is mid-question we don't want a
    fake answering bias suppressing legitimate nav.
    """
    legend = ("M1=topic, M2=literature, M3=design, "
              "M4=analysis, M5=writing")
    head = (
        f"You decide whether the user is requesting NAVIGATION to a different "
        f"module of a thesis-writing assistant ({legend}).\n\n"
        f"User message: \"{last_user}\"\n"
    )
    if awaiting_module and awaiting_field:
        # The phrase 'currently asking the user for' is what the test pins —
        # anchor on something specific so a future prompt rewrite can't
        # silently drop the awaiting context (which is the entire point).
        head += (
            f"\nContext: module {awaiting_module} is currently asking the "
            f"user for the field '{awaiting_field}'. The default assumption "
            f"is that the user's message is an ANSWER to that question.\n"
            f"Set wants_navigation=true ONLY for explicit cross-module "
            f"requests like 'go to M2', 'let me redo the topic', 'back to "
            f"literature'.\n"
            f"Domain terms that overlap module vocabularies are answers, "
            f"NOT navigation:\n"
            f"  - 'PLS-SEM', 'ANOVA', 'regression' while M3 asks `design` "
            f"→ wants_navigation=false\n"
            f"  - 'SmartPLS', 'SPSS', 'NVivo' while M3 asks `tool` "
            f"→ wants_navigation=false\n"
            f"  - 'convenience', 'purposive' while M3 asks "
            f"`sampling_strategy` → wants_navigation=false\n"
        )
    return head


def _any_module_confirmed(cs) -> bool:
    """True if at least one module has been confirmed (has confirmed_at)."""
    for slot in _SLICE_FIELDS:
        slice_ = getattr(cs, slot, None) or {}
        if slice_.get("confirmed_at"):
            return True
    return False


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
        # Cold-start fast-path: no module confirmed yet → there's nothing to
        # navigate FROM, so the classifier's only effect is latency. Crucial for
        # 'Hello' on a fresh project — used to cost a full Gemini RTT (~8-20s).
        cold_start = not _any_module_confirmed(state["context_store"])
        # Architectural shift: we used to skip the nav classifier entirely while
        # a module was mid-question (`_awaiting_field` / `_awaiting_confirm` set)
        # to protect against false-positives where domain answers like "PLS-SEM"
        # got mis-classified as "go to M4". The downside surfaced in user
        # feedback: once any module set `_awaiting_field`, the user was LOCKED
        # IN and couldn't revisit a prior module to fix missing data ("M3
        # missing data … I cannot claim it again"). The new defense is narrower
        # and lets users navigate any time:
        #   1. Higher confidence threshold (0.85) — domain answers usually get
        #      lower scores.
        #   2. Reject self-routes — if the classifier picks the SAME module
        #      we'd already route to (via rules), it's almost certainly the
        #      domain-answer false-positive ("PLS-SEM" while routed-to M3),
        #      not navigation. Honor only cross-module picks.
        if last_user and not cold_start:
            try:
                from orchestrator.agents.base import bounded_invoke
                llm = _intent_llm().with_structured_output(IntentClassification)
                # Read which module (if any) is mid-question so the nav
                # classifier prompt can anchor on the user's most likely
                # intent (answering vs navigating). See _build_nav_prompt
                # for the live bug this context fixes.
                awaiting_module, awaiting_field = _awaiting_module_and_field(
                    state["context_store"]
                )
                # Wall-clock-bounded: a stalled Gemini call here used to hang
                # every interactive turn before any module could run.
                intent = bounded_invoke(
                    llm,
                    _build_nav_prompt(
                        last_user, awaiting_module, awaiting_field
                    ),
                    max_seconds=_nav_max_seconds(),
                    retries=0,
                )
                if (intent.wants_navigation
                        and intent.confidence >= 0.85
                        and intent.target_module
                        and intent.target_module != decision.next_module):
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

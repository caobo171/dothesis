"""Phase 1 — Familiarize."""
from __future__ import annotations

import os
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from orchestrator.agents.m2.intent import classify_phase_intent
from orchestrator.agents.m2.state import M2SubGraphState
from orchestrator.agents.widgets import CardGridHint, CardOption
from orchestrator.message_utils import text_of


def _build_familiarize_hint(paper_uris: list[str]) -> dict:
    """Build the card_grid hint for phase 1's opening question.

    User principle: every M2 question must come with interactive components —
    no more plain prose for branching choices. The 'familiarize' fork is
    binary-ish (use my papers / let AI search / both), so cards are the
    natural fit. The hint is also attached to the AIMessage so the existing
    frontend WidgetRenderer (driven by additional_kwargs.tool_calls_json)
    can render without any extra plumbing.
    """
    options: list[CardOption] = []
    if paper_uris:
        n = len(paper_uris)
        options.append(CardOption(
            value="use_papers",
            label=f"Use my {n} uploaded paper{'s' if n != 1 else ''}",
            description=("Cite from the papers you've already uploaded; "
                         "skip the AI literature search."),
        ))
        options.append(CardOption(
            value="ai_search",
            label="Let AI search for citations",
            description=("Search Crossref, OpenAlex and Semantic Scholar "
                         "for relevant peer-reviewed sources."),
        ))
        options.append(CardOption(
            value="both",
            label="Combine both",
            description="Use your papers AND add AI-discovered citations.",
        ))
    else:
        options.append(CardOption(
            value="ai_search",
            label="Let AI search for citations",
            description=("Search Crossref, OpenAlex and Semantic Scholar "
                         "for relevant peer-reviewed sources."),
        ))
        options.append(CardOption(
            value="upload_first",
            label="I'll upload my own papers first",
            description=("Pause here so you can upload PDFs in the project "
                         "page, then come back."),
        ))
    return CardGridHint(
        widget_type="card_grid",
        field_name="familiarize_choice",
        title=("Do you want to use your uploaded papers, let AI search, "
               "or both?") if paper_uris else
              "How do you want to source citations for the literature review?",
        options=options,
        columns=3 if paper_uris else 2,
    ).model_dump()

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "prompts" / "m2"
_PROMPT = (_PROMPT_DIR / "1_familiarize.md").read_text()
_STYLE = (_PROMPT_DIR / "_style.md").read_text()


def _get_llm():
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.5-flash"),
        temperature=0.4,
    )


def run(state: M2SubGraphState) -> dict:
    mode = state.get("mode", "interactive")
    paper_uris = state.get("paper_uris", [])

    # Auto mode: skip conversational loop — set fact and advance
    if mode == "auto":
        return {
            "has_uploaded_papers": bool(paper_uris),
            "current_phase": "research_state",
        }

    if state.get("has_uploaded_papers") is None:
        last_user = next(
            (text_of(m) for m in reversed(state.get("messages") or [])
             if isinstance(m, HumanMessage)),
            "",
        )
        # If there is user input, check whether it's a confirm/skip intent
        if last_user.strip():
            intent = classify_phase_intent(
                last_user_message=last_user,
                current_phase="familiarize",
                mode="interactive",
            )
            if intent.action in {"confirm", "skip"}:
                # "confirm" means they agree to use uploaded papers (if any),
                # "skip" means they want to skip upload and use AI search
                return {
                    "has_uploaded_papers": (intent.action == "confirm") or bool(paper_uris),
                    "current_phase": "research_state",
                }

        # First turn (or non-actionable input): ask the opening question
        if paper_uris:
            user_prompt = (
                f"{_STYLE}\n\n{_PROMPT}\n\n"
                f"The project has {len(paper_uris)} uploaded paper(s). "
                f"Ask whether to use them as primary citation sources, or fall back to AI search."
            )
        else:
            user_prompt = (
                f"{_STYLE}\n\n{_PROMPT}\n\n"
                f"The project has no uploaded papers. "
                f"Ask whether the user wants to upload some, or proceed with AI search."
            )
        msg = _get_llm().invoke(user_prompt).content
        # W1: attach a card_grid widget hint so the user clicks a card rather
        # than typing free-form text. Without this every M2 turn forced the
        # user into a chat box, which is how 'Other / Specify' got stored as
        # a literal answer for adjacent fields (bug X).
        hint = _build_familiarize_hint(paper_uris)
        ai = AIMessage(content=msg, additional_kwargs={"tool_calls_json": hint})
        return {
            "messages": [ai],
            "has_uploaded_papers": None,
            "tool_calls_json": hint,
        }

    # has_uploaded_papers already resolved — advance to next phase
    return {"current_phase": "research_state"}

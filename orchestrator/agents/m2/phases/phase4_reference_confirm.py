"""Phase 4 — Reference_Confirm."""
from __future__ import annotations

import os
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from orchestrator.agents.m2.intent import classify_phase_intent
from orchestrator.agents.m2.state import M2SubGraphState
from orchestrator.tools.m2_literature import verify_page_numbers

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "prompts" / "m2"
_PROMPT = (_PROMPT_DIR / "4_reference_confirm.md").read_text()
_STYLE = (_PROMPT_DIR / "_style.md").read_text()

_PHASE_KEY = "reference_confirm"


def _get_llm():
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.5-flash"),
        temperature=0.0,
    )


def _auto_verify(paper_uris: list[str], refs: list[dict]) -> list[dict]:
    """Attempt to match each reference to an uploaded PDF and pre-verify it.

    Uses a simple heuristic: if the last name of the author and the year both
    appear in the URI, assume it's a match and call verify_page_numbers on it.
    Only sets verified=True when the tool returns status="verified".
    """
    if not paper_uris:
        return refs
    result = []
    for ref in refs:
        author = (ref.get("author") or "").split()[-1].lower() if ref.get("author") else ""
        year = str(ref.get("year") or "")
        matched_uri = None
        for uri in paper_uris:
            uri_lower = uri.lower()
            if author and year and author in uri_lower and year in uri_lower:
                matched_uri = uri
                break
        if matched_uri:
            try:
                outcome = verify_page_numbers.invoke({"claim": {**ref, "pdf_path": matched_uri}})
                if outcome.get("status") == "verified":
                    result.append({**ref, "verified": True})
                    continue
            except Exception:
                pass
        result.append(ref)
    return result


def _gather_pending(state: M2SubGraphState) -> list[dict]:
    """Extract references with page numbers from the selected gaps."""
    gaps = state.get("candidate_gaps") or []
    selected = set(state.get("selected_gap_ids") or [])
    pending = []
    for gap in gaps:
        if str(gap.get("id")) in selected:
            for paper in gap.get("supporting_papers", []):
                if paper.get("page") is not None:
                    pending.append({**paper, "verified": False})
    return pending


def _ask_at_cursor(pending: list[dict], cursor: int) -> str:
    """Format the verification question for the reference at the given cursor."""
    if cursor >= len(pending):
        return ""
    ref = pending[cursor]
    return (
        f"Citation: {ref.get('author')} ({ref.get('year')}), "
        f"page {ref.get('page')}. Can you verify? "
        "(yes / correct page <n> / skip / skip all)"
    )


def run(state: M2SubGraphState) -> dict:
    mode = state.get("mode", "interactive")

    # First call: build the queue and attempt auto-verification
    if not state.get("pending_page_checks"):
        raw = _gather_pending(state)
        verified_in_advance = _auto_verify(state.get("paper_uris", []), raw)

        # Advance cursor past any references already auto-verified
        cursor = 0
        while cursor < len(verified_in_advance) and verified_in_advance[cursor].get("verified"):
            cursor += 1

        if mode == "auto":
            # Auto mode: mark all remaining as unverified and advance
            final = [r if r.get("verified") else {**r, "verified": False}
                     for r in verified_in_advance]
            return {
                "pending_page_checks": final,
                "verified_refs": final,
                "page_check_cursor": len(final),
                "current_phase": "output_gen",
            }

        if cursor >= len(verified_in_advance):
            # All references were auto-verified — skip to next phase
            return {
                "pending_page_checks": verified_in_advance,
                "verified_refs": verified_in_advance,
                "page_check_cursor": cursor,
                "current_phase": "output_gen",
            }

        # Ask about the first unverified reference
        return {
            "pending_page_checks": verified_in_advance,
            "page_check_cursor": cursor,
            "messages": [AIMessage(content=_ask_at_cursor(verified_in_advance, cursor))],
        }

    # Subsequent calls: process user's response for the current reference
    last_user = next(
        (m.content for m in reversed(state.get("messages") or [])
         if isinstance(m, HumanMessage)),
        "",
    )
    intent = classify_phase_intent(
        last_user_message=last_user,
        current_phase=_PHASE_KEY,
        mode="interactive",
    )

    pending = list(state.get("pending_page_checks") or [])
    cursor = state.get("page_check_cursor") or 0
    verified = list(state.get("verified_refs") or [])

    if intent.action == "navigate":
        return {"current_phase": intent.target_phase or "gap_analysis"}

    if intent.action == "skip_all":
        # Mark all remaining references as unverified and advance
        remaining = pending[cursor:]
        for r in remaining:
            verified.append({**r, "verified": False})
        for r in pending[:cursor]:
            if r not in verified:
                verified.append(r)
        return {
            "verified_refs": verified,
            "page_check_cursor": len(pending),
            "current_phase": "output_gen",
        }

    # Process the current reference at cursor
    current = pending[cursor] if cursor < len(pending) else None
    if current is not None:
        if intent.action == "correct_page" and intent.corrected_page is not None:
            # User corrected the page number — record the corrected value
            verified.append({**current, "page": intent.corrected_page, "verified": True})
        elif intent.action == "skip":
            verified.append({**current, "verified": False})
        else:
            # Treat confirm and any other positive response as verified
            verified.append({**current, "verified": True})

    # Advance past any already-verified references in the queue
    new_cursor = cursor + 1
    while new_cursor < len(pending) and pending[new_cursor].get("verified"):
        verified.append(pending[new_cursor])
        new_cursor += 1

    if new_cursor >= len(pending):
        # All references processed — move to output generation
        return {
            "verified_refs": verified,
            "page_check_cursor": new_cursor,
            "current_phase": "output_gen",
        }

    return {
        "verified_refs": verified,
        "page_check_cursor": new_cursor,
        "messages": [AIMessage(content=_ask_at_cursor(pending, new_cursor))],
    }

"""Phase 4 — Reference_Confirm."""
from __future__ import annotations

from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

from orchestrator.agents.m2.intent import classify_phase_intent
from orchestrator.llm import get_orchestrator_llm
from orchestrator.agents.m2.state import M2SubGraphState
from orchestrator.agents.widgets import CardGridHint, CardOption
from orchestrator.message_utils import text_of
from orchestrator.tools.m2_literature import verify_page_numbers


def _lookup_source_link(ref: dict, citations: list[dict]) -> str | None:
    """Find a clickable link for `ref` by joining on (last-name, year) against
    the phase-2 citation pool. Returns the URL if available, else doi.org/<doi>,
    else None.

    The gap supporting_papers dicts only carry author/year/page — the URL and
    DOI live in research_state_citations from the API scout. Without this
    join, the user verifying a page is asked to judge 'Wang 2011 p. 118' with
    no link, which is exactly the 'really hard to decide' UX the user
    reported.
    """
    ref_last = (ref.get("author") or "").split(",")[0].split()[-1].lower()
    ref_year = str(ref.get("year") or "").strip()
    if not ref_last or not ref_year:
        return None
    for c in citations or []:
        authors = (c.get("authors") or "").lower()
        year = str(c.get("year") or "").strip()
        if ref_last in authors and year == ref_year:
            if c.get("url"):
                return c["url"]
            if c.get("doi"):
                return f"https://doi.org/{c['doi']}"
    return None


def _verify_hint() -> dict:
    """Card grid for the reference-verification question.

    Cards map to the four intent classifier actions for this phase:
      yes      → confirm the page is right as cited
      skip     → can't verify; leave the marker but don't claim verified
      skip_all → bail on every remaining reference
      Other    → opens text input where the user types the correct page
                 (the synthesizer wraps it as 'correct page <n>' so the
                  classifier's regex catches it)."""
    return CardGridHint(
        widget_type="card_grid",
        field_name="reference_verify",
        title="Does this citation check out?",
        options=[
            CardOption(value="yes", label="Yes — page is correct",
                       description="Lock in the citation as written."),
            CardOption(value="Other", label="Wrong page — let me type it",
                       description="Opens an input for the correct page number."),
            CardOption(value="skip", label="Skip — can't verify",
                       description="Keep the citation but mark page unverified."),
            CardOption(value="skip_all", label="Skip all remaining",
                       description="Stop asking and accept everything as-is."),
        ],
        columns=2,
    ).model_dump()

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "prompts" / "m2"
_PROMPT = (_PROMPT_DIR / "4_reference_confirm.md").read_text(encoding="utf-8")
_STYLE = (_PROMPT_DIR / "_style.md").read_text(encoding="utf-8")

_PHASE_KEY = "reference_confirm"


def _get_llm():
    # Route through the engine-wide factory (ORCHESTRATOR_LLM_ROUTE); temperature
    # 0.0 is this phase's original per-site setting. No timeout kwarg here — the
    # old construction never set one, so this stays byte-for-byte.
    return get_orchestrator_llm(temperature=0.0)


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


def _ask_at_cursor(pending: list[dict], cursor: int,
                   citations: list[dict] | None = None) -> str:
    """Format the verification question for the reference at the given cursor.

    When the phase-2 citations are passed in we look up a DOI/URL for the
    reference and embed it as a markdown link — gives the user a 1-click
    way to open the source and check the page themselves instead of
    guessing.
    """
    if cursor >= len(pending):
        return ""
    ref = pending[cursor]
    link = _lookup_source_link(ref, citations or [])
    link_part = f"  \n📄 Open source: {link}" if link else ""
    return (
        f"**Citation:** {ref.get('author')} ({ref.get('year')}), "
        f"page {ref.get('page')}.{link_part}\n\n"
        "Does this check out? Pick a card below."
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

        # Ask about the first unverified reference — body carries the link,
        # widget carries the answer cards.
        citations = state.get("research_state_citations") or []
        body = _ask_at_cursor(verified_in_advance, cursor, citations)
        hint = _verify_hint()
        ai = AIMessage(content=body, additional_kwargs={"tool_calls_json": hint})
        return {
            "pending_page_checks": verified_in_advance,
            "page_check_cursor": cursor,
            "messages": [ai],
            "tool_calls_json": hint,
        }

    # Subsequent calls: process user's response for the current reference
    last_user = next(
        (text_of(m) for m in reversed(state.get("messages") or [])
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

    citations = state.get("research_state_citations") or []
    body = _ask_at_cursor(pending, new_cursor, citations)
    hint = _verify_hint()
    ai = AIMessage(content=body, additional_kwargs={"tool_calls_json": hint})
    return {
        "verified_refs": verified,
        "page_check_cursor": new_cursor,
        "messages": [ai],
        "tool_calls_json": hint,
    }

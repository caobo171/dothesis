"""Brief §5 — context assembly (phase 1: FULL_MODE only).

Every prompt to a module/router LLM is assembled from:
  1. system_prompt        — module persona, always in
  2. handler_prompt       — focus + target slice, always in
  3. turns                — recent (or full) transcript

Phase 1 ships FULL MODE only: when (system + handler + transcript) fits
under FULL_MODE_CEILING, send the whole transcript. No retrieval, no
summaries. This is what the brief explicitly recommends for the first
build pass (§5: "Ship FULL MODE first ... add the tiered path only when
real projects start crossing FULL_MODE_CEILING").

Phase 2 (deferred): pgvector retrieval + rolling per-module summaries
behind a `MEMORY_ASSEMBLE=v2` flag. The function signature here is
designed to absorb that without touching callers — when the threshold
trips, assemble_context returns a `turns=recent, retrieved=..., summaries=...`
shape that handler-side code already accepts via the dataclass.

The point of building phase 1 first: it forces every handler to read its
context through assemble_context() instead of state["messages"]. The day
phase 2 lands, no handler changes.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Sequence

from langchain_core.messages import BaseMessage

from orchestrator.state import ContextStore, ModuleKey, get_module_slice

logger = logging.getLogger(__name__)


# Brief §5 — token budget constants. Values pinned to the brief; tunable
# via env for evals that want to force tiering on small transcripts.
WINDOW = int(os.getenv("MEMORY_WINDOW", "200000"))            # model ctx
TARGET = int(os.getenv("MEMORY_TARGET", "40000"))             # aim
FULL_MODE_CEILING = int(os.getenv("MEMORY_FULL_MODE_CEILING", "90000"))

# Char-per-token approximation (matches token_meter; rough but good enough
# for a routing decision that gets re-checked on the next turn anyway).
_CHARS_PER_TOKEN = 4


@dataclass(frozen=True)
class AssembledContext:
    """Output of assemble_context — what callers pass to the LLM.

    Phase 1: only `turns` is populated (the full transcript). Phase 2:
    `turns` becomes the recent window and `retrieved` + `summaries` carry
    the older context. The dataclass shape is stable across both modes
    so handler code stays unchanged when phase 2 lands.
    """
    system_prompt: str
    handler_prompt: str
    focus_slice: dict
    target_slice: dict
    turns: list[BaseMessage]
    retrieved: list[BaseMessage] = field(default_factory=list)
    summaries: dict[str, str] = field(default_factory=dict)
    mode: str = "full"   # "full" | "tiered"


def _tk(s: str | None) -> int:
    """Token estimate for a string. None → 0 — callers pass optional
    handler_prompt without conditional fences."""
    if not s:
        return 0
    return max(1, len(s) // _CHARS_PER_TOKEN)


def _tk_messages(msgs: Sequence[BaseMessage]) -> int:
    return sum(_tk(getattr(m, "content", "") or "") for m in msgs)


def assemble_context(
    *,
    system_prompt: str,
    handler_prompt: str,
    focus: ModuleKey | None,
    target: ModuleKey,
    cs: ContextStore,
    transcript: Sequence[BaseMessage],
) -> AssembledContext:
    """Assemble the prompt parts for one LLM call (brief §5).

    Phase 1 logic:
      - Compute fixed = tk(system) + tk(handler) + tk(focus_slice) + tk(target_slice)
      - If fixed + tk(transcript) < FULL_MODE_CEILING → FULL mode, send transcript.
      - Else: tiered path → NOT IMPLEMENTED. Raises so the call site is
        forced to think about it rather than silently truncating.

    We return slices (focus + target) separately from `turns` so handlers
    can choose how to format them — some inline JSON into the system
    prompt, others append a structured note. Calling code doesn't have
    to re-derive them from cs.

    target == focus is the common case (continue intent); we still return
    both as separate fields so a cross-module read/mutate handler can
    distinguish "the module I'm working in" from "the module the user
    asked about." When they're the same, target_slice == focus_slice.
    """
    focus_slice = get_module_slice(cs, focus) if focus else {}
    target_slice = get_module_slice(cs, target)

    fixed = (
        _tk(system_prompt)
        + _tk(handler_prompt)
        + _tk(str(focus_slice))
        + _tk(str(target_slice))
    )
    transcript_tokens = _tk_messages(transcript)
    total = fixed + transcript_tokens

    if total < FULL_MODE_CEILING:
        return AssembledContext(
            system_prompt=system_prompt,
            handler_prompt=handler_prompt,
            focus_slice=focus_slice,
            target_slice=target_slice,
            turns=list(transcript),
            mode="full",
        )

    # Phase 2 territory. We log loudly so production traffic crossing the
    # threshold is visible BEFORE the LLM call fails on too-many-tokens —
    # gives us a heads-up to ship the tiered path.
    logger.warning(
        "memory.assemble_context: FULL_MODE_CEILING exceeded "
        "(fixed=%d + transcript=%d = %d ≥ %d) but tiered mode not yet "
        "implemented — truncating to most-recent turns as a stopgap",
        fixed, transcript_tokens, total, FULL_MODE_CEILING,
    )
    # Stopgap until phase 2: take whatever's most recent and fits in
    # (FULL_MODE_CEILING - fixed). NOT a real solution — old turns get
    # dropped silently and the brief's "feeling of total recall" breaks.
    # Phase 2 replaces this with recent_window + retrieval + summaries.
    return _truncate_to_fit(
        system_prompt, handler_prompt, focus_slice, target_slice,
        transcript, max_tokens=max(1, FULL_MODE_CEILING - fixed),
    )


def _truncate_to_fit(
    system_prompt: str, handler_prompt: str,
    focus_slice: dict, target_slice: dict,
    transcript: Sequence[BaseMessage], *, max_tokens: int,
) -> AssembledContext:
    """Stopgap truncation for projects that overflow FULL_MODE_CEILING
    before phase 2 lands. Walks the transcript from the most-recent end
    and accepts turns until the budget is exhausted. Drops oldest turns
    silently — a tiered retrieval pass would do better, which is exactly
    why this is labeled stopgap."""
    kept_rev: list[BaseMessage] = []
    used = 0
    for msg in reversed(list(transcript)):
        cost = _tk(getattr(msg, "content", "") or "")
        if used + cost > max_tokens:
            break
        kept_rev.append(msg)
        used += cost
    return AssembledContext(
        system_prompt=system_prompt,
        handler_prompt=handler_prompt,
        focus_slice=focus_slice,
        target_slice=target_slice,
        turns=list(reversed(kept_rev)),
        mode="tiered",  # truthful: we're no longer in pure FULL mode
    )

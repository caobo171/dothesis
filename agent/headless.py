"""Headless run spine (convergence spec §1/§4).

The runner plays the STUDENT's part against the same build_agent/stream_turn
brain chat uses. Mode differences are DATA held by this caller — neither
stream_turn nor build_agent ever inspects a profile, which is what preserves
the headless invariant: chat features cannot gate headless, because headless
runs the same code with a different caller.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from agent.state import MODULES, ProjectStateStore


def record_decision(
    store: ProjectStateStore,
    *,
    options: list[str],
    choice: str,
    rationale: str,
) -> dict:
    """Append one auto-decision to the audit trail, through commit_slice.

    Spec §4: decisions ride INSIDE the owned slice ("decisions" is in every
    module's SLICE_OWNERSHIP) so DbProjectStateStore persists them via the
    existing ownership machinery — a new top-level key would pass file-store
    tests and vanish in prod. Worse data modelling, considerably safer.

    status_overrides snapshots every module's CURRENT status because
    commit_slice's normal side effects (module -> in_progress, downstream
    needs_review propagation) belong to content commits; an audit append that
    regressed a `done` module or flagged reviews would corrupt the very run it
    is auditing. Overrides are applied after commit_slice's own status writes
    (agent/state.py), so the snapshot always wins.
    """
    state = store.load()
    module = state.get("focus") or "M1"
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "module": module,
        "options": list(options),
        "choice": choice,
        "rationale": rationale,
    }
    decisions = list(state["contextStore"].get("decisions") or []) + [record]
    store.commit_slice(
        module,
        {"decisions": decisions},
        reason=f"headless auto-decision: {choice[:80]}",
        status_overrides={m: state["status"].get(m, "locked") for m in MODULES},
    )
    return record


@dataclass
class RunProfile:
    """Mode differences as DATA (spec §1). Only the runner reads this —
    stream_turn/build_agent never see it, so a chat feature physically cannot
    gate a headless run."""
    interactive: bool = False
    max_turns: int = 40
    wall_clock_s: int = 1800
    # 5 (was 3): the stall nudge in run_headless needs a couple of turns to pull a
    # spinning model out of a read-only loop before we give up. Still a firm bound.
    max_stalls: int = 5
    on_options: str = "auto"  # "auto": decide + record | "ask": stop, surface options
    # Which modules must be `done` for THIS run to be done. None = all of MODULES,
    # which is what every caller that doesn't care gets (and what the runner did
    # unconditionally before). A caller asking for a chapter SUBSET — partner's
    # analysis_report needs no literature review — would otherwise have to drive
    # modules its request never reads to completion just to avoid a hard failure,
    # turning "give me 4 chapters" into a full thesis run. Which modules a request
    # needs is a property of the request, so it rides here as DATA rather than
    # forking the spine.
    required_modules: frozenset[str] | None = None


@dataclass
class RunResult:
    status: str   # "done" | "failed" | "needs_input"
    reason: str   # "roadmap_done" | "max_turns" | "wall_clock" | "max_stalls" | "awaiting_options"
    turns: int = 0
    decisions: list = field(default_factory=list)
    pending_options: list | None = None


def pick_option(options: list[str]) -> tuple[str, str]:
    """Headless option policy: FIRST option.

    SYSTEM_PROMPT's [OPTIONS] rules tell the model to put the recommended /
    advance choice first, so first-pick is the fire-and-forget default.

    That ordering is an UNENFORCED PROMPT CONVENTION, not a boundary: the model
    can ignore it and nothing here detects that, so headless output quality
    leans on a card order this code cannot verify. Which is exactly why every
    pick flows through record_decision — a bad auto-pick is then auditable
    after the fact and overridable, instead of invisible.

    First-option (not "smartest option") keeps the policy deterministic, hence
    testable.
    """
    return options[0], "auto: first option (headless default policy)"


def _options_from_events(events: list[dict]) -> list[str] | None:
    """[OPTIONS] surfaces as a card_grid tool_calls event — reuse the runtime's
    parser output instead of re-parsing prose here (one parser, one truth).
    papers_panel / export hints also ride tool_calls, hence the widget filter."""
    for ev in reversed(events):
        if ev.get("type") == "tool_calls":
            payload = ev.get("payload") or {}
            if payload.get("widget_type") == "card_grid":
                return [o["value"] for o in payload.get("options") or []]
    return None


def _all_done(state: dict, required: frozenset[str] | None = None) -> bool:
    # Terminal condition. roadmap.next_action never returns a "done" sentinel —
    # with everything done it returns the export/defense CTA — so the runner
    # reads the status map directly. `required` narrows it to the modules THIS
    # request needs; None keeps the historical "all five" meaning.
    status = state.get("status") or {}
    return all(status.get(m) == "done" for m in (required or MODULES))


async def run_headless(
    agent,
    store: ProjectStateStore,
    profile: RunProfile,
    *,
    thread_id: str = "headless",
    initial_prompt: str = "continue",
    on_event=None,
    _clock=time.monotonic,
) -> RunResult:
    """Drive the deep agent to roadmap completion with no human present.

    ALL THREE budgets fail the run — exhaustion is a failed run with partial
    state preserved (everything commit_slice wrote stays), never a silent
    success. Stall detection is deterministic: store.load() before vs after
    the turn catches "nothing happened" regardless of cause (missing [OPTIONS]
    marker, off-script model, unresolvable blocker, silently failing tool).
    It bounds the damage of prose-asking; it does not make auto-decide an
    enforced boundary (spec Risk 1).

    _clock is injectable so wall-clock tests are deterministic instead of
    sleeping (a slow test IS a budget bug's favorite hiding place).
    """
    from agent.runtime import stream_turn  # noqa: PLC0415 — keeps headless import-light

    started = _clock()
    stalls = 0
    turns = 0
    decisions: list[dict] = []
    next_prompt = initial_prompt

    while True:
        before = store.load()
        if _all_done(before, profile.required_modules):
            return RunResult("done", "roadmap_done", turns, decisions)
        if turns >= profile.max_turns:
            return RunResult("failed", "max_turns", turns, decisions)
        remaining = profile.wall_clock_s - (_clock() - started)
        if remaining <= 0:
            return RunResult("failed", "wall_clock", turns, decisions)

        events: list[dict] = []

        async def _drain(prompt: str) -> None:
            async for ev in stream_turn(agent, thread_id, prompt, store=store):
                events.append(ev)
                if on_event is not None:
                    on_event(ev)

        try:
            # Hard wall-clock: a single runaway turn cannot overrun the budget
            # (bounded_invoke at orchestrator/agents/base.py is the precedent
            # for per-call wall-clock discipline).
            # NOTE: `remaining` comes from _clock, but wait_for measures REAL
            # time — the two agree in prod (_clock defaults to time.monotonic)
            # and diverge under a fake clock. So this branch is UNTESTABLE as
            # written, not merely untested: a fake clock that advances fast
            # enough to expire the budget trips the pre-turn check above first.
            # Covering it needs a genuinely blocking model (asyncio.sleep) plus
            # a small REAL wall_clock_s. Left as-is deliberately: the injected
            # clock keeps budget tests fast and deterministic, worth more than
            # covering this 3-line second line of defence.
            await asyncio.wait_for(_drain(next_prompt), timeout=max(remaining, 0.001))
        except asyncio.TimeoutError:
            return RunResult("failed", "wall_clock", turns + 1, decisions)
        turns += 1

        options = _options_from_events(events)
        after = store.load()
        # Progress = observable change OR an explicit question. Errors surface
        # as {"type":"error"} events with no state change → they land in the
        # stall path and get bounded, not retried forever.
        progressed = (after != before) or bool(options)
        if not progressed:
            stalls += 1
            if stalls >= profile.max_stalls:
                return RunResult("failed", "max_stalls", turns, decisions)
            # A bland "continue" lets a spinning model repeat the same read-only
            # turn — the observed stall is qwen re-reading context at M3 (the most
            # complex module) without committing anything, so the store never
            # changes and it dies at max_stalls. Nudge it to WRITE or declare a
            # blocker instead of reading more; escalate on repeat.
            next_prompt = (
                "STOP. Last turn produced NO change to the project — you only "
                "read/inspected, you did not write. Do NOT read any more files or "
                "slices this turn. Take ONE concrete write action now: call "
                "commit_slice with your best current work for the module you are on "
                "(for M3, commit the conceptual_model and hypotheses), which advances "
                "the roadmap. If a specific obstacle truly blocks you, call "
                "flag_blocker. Reading again is not allowed this turn."
            )
            if stalls >= 2:
                next_prompt = (
                    "You are stuck in a read-only loop. Commit whatever you have for "
                    "the current module RIGHT NOW with commit_slice — even a "
                    "minimal-but-valid slice is better than nothing. Do not read; write."
                )
            continue
        stalls = 0

        if options:
            if profile.on_options == "ask":
                return RunResult("needs_input", "awaiting_options", turns,
                                 decisions, pending_options=options)
            choice, rationale = pick_option(options)
            decisions.append(record_decision(
                store, options=options, choice=choice, rationale=rationale))
            # The choice IS the next user turn — exactly what a student
            # clicking the card would have sent.
            next_prompt = choice
        else:
            next_prompt = "continue"

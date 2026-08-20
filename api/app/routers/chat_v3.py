"""v3 chat turn — the deep agent behind the same SSE contract.

When DOTHESIS_AGENT_V3=1, send_message delegates here instead of the
graph_v2 path. Same event vocabulary the web already renders (token /
progress / error / done), same persistence (assistant Message row), same
state sync — except sync is built-in: the agent's commit_slice writes the
context_store/module_status/focus rows directly through DbProjectStateStore,
so there is no end-of-turn copy step.

Tool activity is forwarded as `progress` events, which the frontend already
renders as the live ProgressBubble — the user watches the agent read skills
and call tools in real time (the PDF session's trust-building beat).
"""
from __future__ import annotations

import logging
import re
import uuid

from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..credit_ledger import debit
from ..models import Message, PaperUpload, Project, Thread, User
from ..sse import sse_pack
from ..workspace import workspace_dir

logger = logging.getLogger(__name__)


# Reader of the progress bubble is a thesis student, not an engineer — never
# leak raw tool names (`commit_slice`, `read_file`). Maps the deep-agent tool
# (name + args) to a plain-language line. Mirrors the web fallback in
# useChat.ts; kept here because tool args (e.g. read_file's path) only exist
# on the backend event.
_MODULE_NOUN = {
    "M1": "topic", "M2": "literature review", "M3": "research design",
    "M4": "data analysis", "M5": "writing",
}
_STATS_LABEL = {
    "detect": "Inspecting your dataset…",
    "describe": "Summarizing your data…",
    "corr": "Checking correlations…",
    "cronbach": "Checking reliability (Cronbach's α)…",
    "regression": "Running the regression…",
    "ttest": "Running a t-test…",
}
_TOOL_LABEL = {
    "read_slice": "Checking your project so far…",
    "write_file": "Saving to your workspace…",
    "edit_file": "Updating your draft…",
    "ls": "Looking through your files…",
    "glob": "Looking through your files…",
    "grep": "Searching your files…",
    "write_todos": "Planning the next steps…",
    "task": "Working on a sub-task…",
    "research_scout": "Searching for relevant research…",
    "parse_reference": "Reading a reference…",
    "export_docx": "Building your Word document…",
}


def _tool_progress_label(name: str, args: dict) -> str:
    if name == "read_file":
        path = str(args.get("file_path") or args.get("path") or "")
        if "/skills/" in path:
            return "Reading the guide for this step…"
        if "upload" in path:
            return "Reading your uploaded file…"
        return "Looking something up…"
    if name == "commit_slice":
        noun = _MODULE_NOUN.get(str(args.get("module") or ""))
        return f"Saving your {noun}…" if noun else "Saving your progress…"
    if name == "run_stats":
        return _STATS_LABEL.get(str(args.get("op") or ""), "Analyzing your data…")
    return _TOOL_LABEL.get(name, "Working on it…")

# One agent per project per process. Tools close over the project's store and
# workspace, so the cache key is the project id; the checkpointer inside is
# shared (thread_id scopes conversations).
_agents: dict[uuid.UUID, object] = {}
_checkpointer = None


async def _get_checkpointer():
    """AsyncPostgresSaver over the api process's shared async pool.

    Reuses app.db's pool (moved out of orchestrator/graph.py during the
    Auto Thesis migration — see app/db.py's get_async_pool docstring) so the
    api process keeps one Postgres pool regardless of which brain (graph or
    agent) serves a project.
    """
    global _checkpointer
    if _checkpointer is None:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from ..db import get_async_pool
        pool = await get_async_pool()
        saver = AsyncPostgresSaver(pool)
        # Publish only AFTER setup lands. Assigning the global first meant a
        # transient DB blip during setup() (it runs the checkpoint migrations)
        # 500'd that request and then left every later request holding a saver
        # whose migrations never ran — the cache made a one-off network failure
        # permanent, and silently. Now the next request just retries.
        await saver.setup()
        _checkpointer = saver
    return _checkpointer


# Re-exported so the many `from .chat_v3 import _workspace_dir` callers keep
# working; the definition moved to app.workspace so the HEADLESS entrypoint can
# resolve a path without importing this chat router (see app/workspace.py).
_workspace_dir = workspace_dir


def _clicked_a_previous_option(db: Session, thread_pk, text: str) -> bool:
    """Did this message come from clicking a card the last turn offered?

    Inferred server-side rather than flagged by the client, for two reasons:
    every existing client keeps working without a change, and no client can
    forget to send it — headless and partner runs pick options too.

    The signal is exact-match against the options actually persisted on the
    previous assistant message, so a student who happens to TYPE the same
    sentence gets the same treatment, which is correct: they asked for that
    thing either way.
    """
    if not (text or "").strip():
        return False
    row = db.execute(
        select(Message)
        .where(Message.thread_id == thread_pk, Message.role == "assistant")
        .order_by(Message.created_at.desc())
        .limit(1)
    ).scalars().first()
    hint = getattr(row, "tool_calls_json", None)
    if not isinstance(hint, dict):
        return False
    # Two shapes are persisted: a bare widget hint, and {"widgets": [...]} when
    # one turn emitted several.
    hints = hint.get("widgets") if isinstance(hint.get("widgets"), list) else [hint]
    wanted = text.strip().casefold()
    for h in hints:
        if not isinstance(h, dict) or h.get("widget_type") != "card_grid":
            continue
        for opt in h.get("options") or []:
            if isinstance(opt, dict) and str(opt.get("value", "")).strip().casefold() == wanted:
                return True
    return False


_DIRECT_REQUEST_RE = re.compile(
    r"(?:\b(?:please|write|create|build|update|revise|finalize|finalise|save|"
    r"export|review|check|generate|give\s+me|i\s+(?:need|want))\b|"
    r"\b(?:hãy|làm|viết|tạo|xuất|cập\s*nhật|chốt|sửa|đánh\s*giá|kiểm\s*tra|"
    r"cho\s+tôi|tôi\s+(?:cần|muốn)|đồng\s*ý)\b|"
    r"\b(?:hay|lam|viet|tao|xuat|cap\s*nhat|chot|sua|danh\s*gia|kiem\s*tra|"
    r"cho\s+toi|toi\s+(?:can|muon)|dong\s*y)\b)",
    re.IGNORECASE,
)
_DIRECT_QUESTION_RE = re.compile(
    r"^\s*(?:what|which|who|why|how|when|where|can|could|is|are|do|does|"
    r"ai|gì|gi|sao|tại\s*sao|tai\s*sao|như\s*thế\s*nào|nhu\s*the\s*nao|"
    r"đang|dang)\b",
    re.IGNORECASE,
)
_VIETNAMESE_RE = re.compile(
    r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợ"
    r"úùủũụứừửữựýỳỷỹỵ]",
    re.IGNORECASE,
)


def _direct_request(text: str) -> bool:
    """A self-contained request should be answered or executed, not re-menued.

    This is deliberately deterministic: relying on the model to decide whether
    “OK, chốt và cập nhật” is confirmation produced the repeated-question loop
    seen in production. A question mark is also a redirect from the roadmap.
    """
    value = (text or "").strip()
    return bool(value and (
        "?" in value
        or _DIRECT_REQUEST_RE.search(value)
        or _DIRECT_QUESTION_RE.search(value)
    ))


def _chapter_export_directive(
    text: str, recent_user_texts: tuple[str, ...] | list[str] = (),
) -> str | None:
    """Route explicit and immediate follow-up requests for Chapters 1–3.

    Decision: short corrections such as ``đủ hết rồi, xuất ra`` inherit the
    most recent explicit chapter scope. Without this conversational continuity,
    a checkpoint can preserve an earlier, incorrect chapter mapping.
    """
    value = (text or "").casefold()

    def _explicit_scope(candidate: str) -> bool:
        mentions_chapters = "chương" in candidate or "chapter" in candidate
        asks_to_write = bool(re.search(
            r"\b(?:viết|viet|write|draft|soạn|soan|hoàn\s*chỉnh|hoan\s*chinh)\b",
            candidate,
        ))
        numbers = set(re.findall(r"(?<!\d)[123](?!\d)", candidate))
        return mentions_chapters and asks_to_write and {"1", "2", "3"}.issubset(numbers)

    explicit = _explicit_scope(value)
    names_a_chapter = "chương" in value or "chapter" in value
    continuation = bool(re.search(
        r"\b(?:xuất|xuat|export|làm\s*ngay|lam\s*ngay|hoàn\s*chỉnh|"
        r"hoan\s*chinh|không\s*đúng|khong\s*dung|đủ\s*hết|du\s*het)\b",
        value,
    ))
    inherited = (
        not names_a_chapter
        and continuation
        and any(_explicit_scope((item or "").casefold()) for item in recent_user_texts)
    )
    if explicit or inherited:
        return (
            "[REQUESTED OUTPUT] Write the complete first three pre-results chapters "
            "from the existing M1–M3 state and call export_docx with scope "
            '"chapter:intro|lit_review|methodology" in this turn. Do not require M4 '
            "survey/interview results and do not answer with an outline or another question."
        )
    return None


def _tool_only_reply(user_text: str, tool_results: list[tuple[str, str]]) -> str:
    """Give a silent tool turn an honest, localized completion message."""
    successful = [name for name, preview in tool_results
                  if not re.search(r'(^|["{\s])error["\s:]', preview or "", re.I)]
    vi = bool(_VIETNAMESE_RE.search(user_text or ""))
    if "export_docx" in successful:
        return ("Đã tạo tài liệu. Bạn có thể tải bản DOCX/PDF từ thẻ tải xuống."
                if vi else
                "The document is ready. Download the DOCX/PDF from the download card.")
    if "commit_slice" in successful:
        return ("Đã cập nhật nội dung vào dự án."
                if vi else "The project has been updated.")
    if successful:
        return "Đã hoàn tất yêu cầu." if vi else "Done."
    return ("Mình chưa tạo được kết quả cho yêu cầu này. Vui lòng thử lại."
            if vi else
            "I couldn't produce a result for that request. Please try again.")


def _materialize_attachments(
    db: Session,
    project_id: uuid.UUID,
    upload_ids: list[uuid.UUID],
) -> list:
    """Look up each upload row, read its bytes from the workspace mirror,
    return a list of `agent.multimodal.Attachment` ready to ship to the
    runtime.

    Misses (id not found / wrong project / file missing on disk) are
    logged + skipped; we never want one bad upload id to torch the whole
    message. The user might re-upload from the chip row if they care.
    """
    if not upload_ids:
        return []
    # Lazy import: don't pull in google-genai at chat-router import time.
    from agent.multimodal import Attachment

    workspace = _workspace_dir(project_id)
    out: list[Attachment] = []
    for uid in upload_ids:
        row = db.get(PaperUpload, uid)
        if row is None or row.project_id != project_id:
            logger.warning("attachment %s missing or cross-project — skipped", uid)
            continue
        path = workspace / "uploads" / row.filename
        if not path.exists():
            logger.warning(
                "attachment %s (%s) missing on disk at %s — skipped",
                uid, row.filename, path,
            )
            continue
        try:
            data = path.read_bytes()
        except Exception:
            logger.exception("attachment %s read failed — skipped", uid)
            continue
        out.append(Attachment(
            filename=row.filename,
            bytes=data,
            mime_type=row.mime_type or "application/octet-stream",
            display_name=row.filename,
        ))
    return out


async def _get_agent(db: Session, project_id: uuid.UUID):
    if project_id in _agents:
        return _agents[project_id]
    from agent.runtime import build_agent
    from ..agent_state import DbProjectStateStore

    store = DbProjectStateStore(db.bind, project_id, _workspace_dir(project_id))
    agent = build_agent(
        _workspace_dir(project_id),
        checkpointer=await _get_checkpointer(),
        store=store,
    )
    _agents[project_id] = agent
    return agent


# Credit-per-token scaling by active model lives in pricing.py so the chat turn
# and the Auto Thesis run (job_runner) charge off one source of truth.
from ..pricing import credit_multiplier as _credit_multiplier


async def send_message_v3(
    t: Thread,
    text: str,
    db: Session,
    *,
    upload_ids: list[uuid.UUID] | None = None,
) -> StreamingResponse:
    """Persist the user message, run one agent turn, stream SSE.

    `upload_ids` references files the user attached to this message. Each
    is materialized from the workspace mirror written by the /uploads
    route (`<workspace>/uploads/<filename>`) and handed to the runtime
    as an `Attachment`. The runtime calls `agent.multimodal.build_user_message`
    which formats it for whichever provider is active (Gemini inline ≤20MB
    or Files API URI for larger files).
    """
    # Persist the file refs on the user Message so the bubble can render
    # chips on reload. `tool_calls_json` is unused on user rows (it's for
    # assistant widget hints), so we reuse it under an explicit
    # `{"attachments": [...]}` key — never ambiguous with widget shapes
    # which carry `field_name`. Metadata (not bytes) is pulled from
    # `paper_uploads` so the chip can show filename + size + mime without
    # the frontend doing N extra round-trips.
    user_tool_calls: dict | None = None
    if upload_ids:
        rows = [db.get(PaperUpload, uid) for uid in upload_ids]
        chips = [
            {
                "upload_id": str(r.id),
                "filename": r.filename,
                "size_bytes": r.size_bytes,
                "mime_type": r.mime_type,
            }
            for r in rows
            if r is not None and r.project_id == t.project_id
        ]
        if chips:
            user_tool_calls = {"attachments": chips}
    # BEFORE the insert — it reads the newest assistant row, and the user row
    # we are about to add would not change that, but the ordering is load-
    # bearing if the roles ever widen. Cheap, and it must never fail a turn.
    try:
        clicked_option = _clicked_a_previous_option(db, t.id, text)
    except Exception:
        logger.exception("clicked-option detection failed")
        clicked_option = False
    execute_now = clicked_option or _direct_request(text)

    # Read before inserting this turn so terse corrections inherit the user's
    # last explicit scope, while a newly named chapter always wins.
    recent_user_texts = tuple(db.scalars(
        select(Message.content)
        .where(Message.thread_id == t.id, Message.role == "user")
        .order_by(Message.id.desc())
        .limit(6)
    ).all())
    chapter_directive = _chapter_export_directive(text, recent_user_texts)

    db.add(Message(thread_id=t.id, role="user", content=text,
                   tool_calls_json=user_tool_calls))
    db.commit()

    agent = await _get_agent(db, t.project_id)
    agent_thread_id = f"v3:{t.langgraph_thread_id}"

    from agent.runtime import stream_turn
    from ..agent_state import DbProjectStateStore

    # Materialize attachments BEFORE entering the async generator so that
    # any read failure surfaces as a 500 the client can retry — once we're
    # inside `gen()` failures are SSE error events the user might miss.
    attachments = _materialize_attachments(db, t.project_id, upload_ids or [])

    engine = db.bind
    project_id = t.project_id
    thread_pk = t.id
    langgraph_thread_id = t.langgraph_thread_id

    async def gen():
        import time as _time
        _turn_t0 = _time.monotonic()
        # Accumulate token usage across every LLM step in the turn (tool loops
        # included) so the per-response cost reflects the whole turn.
        _usage_in = 0
        _usage_out = 0
        # F10: models that actually served steps this turn. On the OpenRouter
        # route the primary can silently fail over to a pricier fallback; we emit
        # a `model_served` analytics signal when the served model != the requested
        # primary so a silent, costlier switch is visible rather than invisible.
        _served_models: set[str] = set()
        chunks: list[str] = []
        # Captured from `tool_calls` events emitted by the runtime (an
        # `[OPTIONS]` card, a `[PAPERS]` panel, an export download card, …).
        # A single turn can emit SEVERAL (e.g. export + papers panel) — collect
        # ALL of them, not just the last, so none clobbers another. Persisted
        # onto the Message row so MessageBubble can render them all on reload.
        widget_hints: list[dict] = []
        tool_results: list[tuple[str, str]] = []

        # Engine progress beats (research_scout's 30–90s search) reach the
        # SSE stream through the same registry the graph path used.
        import asyncio as _asyncio
        events_q: _asyncio.Queue = _asyncio.Queue()
        loop = _asyncio.get_running_loop()

        def progress_emitter(payload: dict) -> None:
            # Diagnostic stderr beat — same as the v2 chat router. Tells us
            # whether engine progress is reaching the v3 SSE pipe.
            import sys as _sys
            print(f"[v3-emitter] stage={payload.get('stage')!r} msg={payload.get('message','')[:80]!r}",
                  file=_sys.stderr, flush=True)
            try:
                # Tag the payload as a "progress" event in the multiplexed
                # queue so the consumer can distinguish it from agent
                # events arriving from the pump task.
                loop.call_soon_threadsafe(
                    events_q.put_nowait, ("progress", payload))
            except Exception:  # noqa: BLE001
                pass

        from engine.utils import progress as _engine_progress
        _engine_progress.register(langgraph_thread_id, progress_emitter)
        # Diagnostic counters so a single line at end of turn tells us how
        # many of each event type fired — quick read whether the agent
        # streamed nothing, only tokens, or only tool events.
        _counts = {"token": 0, "tool_start": 0, "tool_end": 0, "error": 0,
                   "done": 0, "engine_progress": 0}
        import sys as _sys
        print(f"[v3] turn start thread={langgraph_thread_id} text={text[:60]!r}",
              file=_sys.stderr, flush=True)
        # Bind the progress emitter as the active ContextVar for the
        # duration of the agent turn. Why: the registry path
        # (`register(thread_id, …)`) is for callers that have the thread_id
        # in hand — M2Agent.step does. But research_scout has no thread_id
        # to look up with; the engine's `safe_print → _safe_print_hook →
        # current_emitter()` chain reads from the ContextVar (PEP 567), not
        # the registry. Binding here means asyncio.to_thread workers and
        # the engine's `submit_with_context`-wrapped ThreadPoolExecutor
        # batches all inherit the emitter — no per-tool plumbing needed.
        # Sync `with` over `async for` is fine: the ContextVar token is
        # held by this frame across every await yield.
        try:
            _bind_ctx = _engine_progress.bind(progress_emitter)
        except Exception:  # noqa: BLE001 — never let progress break a turn
            _bind_ctx = None
        async def _pump_agent():
            """Drain stream_turn into the shared queue. A sentinel marks
            completion so the consumer below can exit cleanly even if the
            agent finishes silently."""
            try:
                # Pass a store so the runtime can prepend the authoritative
                # [PROJECT STATE] status line — keeps the agent's "done" claims
                # honest against the real module statuses.
                turn_store = DbProjectStateStore(engine, project_id, _workspace_dir(project_id))
                from agent.runtime import EXECUTE_NOW_MARKER
                _runtime_text = "\n".join(part for part in (
                    EXECUTE_NOW_MARKER if execute_now else None,
                    chapter_directive,
                    text,
                ) if part)
                async for ev in stream_turn(
                    agent, agent_thread_id, _runtime_text,
                    attachments=attachments, store=turn_store,
                ):
                    await events_q.put(("agent", ev))
            finally:
                await events_q.put(("done", None))

        pump_task = None
        _finalized = False

        def _finalize():
            """Persist the (partial-or-full) assistant reply + charge for tokens
            used so far; return the `done` payload. Idempotent — runs exactly
            once whether the turn completed normally, errored, or the client
            disconnected mid-stream (browser close/reload). On disconnect this is
            what SAVES the partial answer instead of throwing it away, and the
            charge reflects only the tokens actually spent."""
            nonlocal _finalized
            if _finalized:
                return None
            _finalized = True
            total_tokens = _usage_in + _usage_out
            duration_ms = int((_time.monotonic() - _turn_t0) * 1000)
            # Scale credits by the active model's relative cost (see
            # _credit_multiplier) so a Pro turn isn't charged like a Flash turn.
            #
            # Price the model this turn ACTUALLY RAN, by asking the same resolver
            # that chose it: _get_agent -> build_agent -> _default_model ->
            # make_model -> spec_from_env(). This used to be a SECOND, independent
            # guess — credit_multiplier(getenv("DOTHESIS_AGENT_MODEL",
            # "gemini-3.5-flash")) — carrying its own default, and the two defaults
            # drifted: on route=ofox with DOTHESIS_AGENT_MODEL unset, spec_from_env
            # resolved the route's default while billing charged 3.5-flash's rate —
            # an overcharge to students, one uncommented .env.example line away (the
            # route and the model were commented on separate lines back then; both
            # that split and the name-matching multipliers are since fixed).
            # This is the chat-side twin of d4382a6, and the same principle: billing
            # reads the model that served the call, never re-derives it from env.
            #
            # Sourcing it from spec_from_env makes billed-model == run-model by
            # CONSTRUCTION — one resolver, so there is no second copy left to drift.
            # Two alternatives rejected: (a) fixing the default string re-creates
            # two copies and is right only until the next default moves; (b) billing
            # per `_served_models` (the d4382a6 ledger-row shape) doesn't fit here —
            # chat debits an aggregate of the streamed `usage` events, whose `model`
            # is best-effort and absent on most routes (agent/runtime.py), so it
            # would need an env fallback for exactly the cases where drift lives and
            # would make the charge depend on whether metadata happened to arrive.
            # Residual gap, deliberately: an OpenRouter cascade that silently fails
            # over to a pricier fallback still bills the requested primary — that
            # switch is surfaced by the `model_served` analytics event below.
            from agent.model_factory import spec_from_env  # agent-layer: safe to import

            _mult = _credit_multiplier(spec_from_env().model)
            cost_credits = max(1, round(total_tokens / 1000 * _mult)) if total_tokens else 0

            full = "".join(chunks)
            # A turn can finish with NO streamed text — e.g. the agent only ran
            # tools, or a resumed checkpoint re-committed state silently. Saving
            # nothing leaves the user staring at their own message with no reply
            # (the exact "again"/"hello?" silence we hit). When the turn produced
            # no text AND didn't already surface an error, persist a neutral
            # fallback so every turn yields a visible assistant bubble. Errors
            # are skipped: the error event already told the user what happened.
            if not full and _counts.get("error", 0) == 0:
                full = _tool_only_reply(text, tool_results)
            # Collapse the turn's widget hints into the single tool_calls_json
            # slot: none → null, one → that hint (back-compat), many → a `multi`
            # wrapper the frontend expands so an export card + papers panel both
            # render (previously the last hint clobbered the rest).
            final_tool_calls = (
                None if not widget_hints
                else widget_hints[0] if len(widget_hints) == 1
                else {"widget_type": "multi", "widgets": widget_hints}
            )
            if full:
                focus = DbProjectStateStore(
                    engine, project_id, _workspace_dir(project_id)
                ).load()["focus"]
                with engine.connect() as conn:
                    conn.execute(Message.__table__.insert().values(
                        thread_id=thread_pk, role="assistant",
                        content=full, module_tag=focus,
                        tool_calls_json=final_tool_calls,
                        cost_credits=cost_credits,
                        duration_ms=duration_ms,
                        total_tokens=total_tokens,
                    ))
                    conn.commit()

            credit_balance = None
            if cost_credits > 0:
                try:
                    with Session(engine) as _s:
                        proj = _s.get(Project, project_id)
                        owner = _s.get(User, proj.user_id) if proj else None
                        if owner is not None:
                            charge = min(cost_credits, owner.credit or 0)
                            if charge > 0:
                                debit(_s, owner, delta=charge, reason="chat_turn",
                                      ref_type="thread", ref_id=thread_pk)
                                _s.commit()
                            credit_balance = owner.credit
                except Exception:  # noqa: BLE001
                    logger.exception("credit debit failed for thread %s", thread_pk)

            # F10: flag a silent fallback. If any served model differs from the
            # requested primary (spec_from_env().model), emit `model_served` so a
            # switch to a pricier fallback is observable. Best-effort, never
            # blocks the turn. spec_from_env is agent-layer (safe to import).
            try:
                from agent.model_factory import spec_from_env

                primary = spec_from_env().model
                switched = {m for m in _served_models if m and m != primary}
                if switched:
                    from .. import analytics

                    with Session(engine) as _s2:
                        _proj = _s2.get(Project, project_id)
                        _uid = str(_proj.user_id) if _proj else None
                    for served in switched:
                        analytics.emit("model_served", _uid,
                                       {"requested": primary, "served": served,
                                        "thread_id": thread_pk})
            except Exception:  # noqa: BLE001
                logger.exception("model_served emit failed for thread %s", thread_pk)

            return {"type": "done", "cost_credits": cost_credits,
                    "duration_ms": duration_ms, "total_tokens": total_tokens,
                    "credit_balance": credit_balance}

        try:
            if _bind_ctx is not None:
                _bind_ctx.__enter__()
            # MULTIPLEX: previously this loop did `async for ev in
            # stream_turn(...)` and drained engine progress only at the top
            # of the loop body — so while the agent blocked on a 60-90s
            # tool call (research_scout), the body never executed and engine
            # progress events sat in the queue, invisible to the UI. The
            # pump task runs stream_turn in parallel and writes to the same
            # queue the engine writes to; the consumer below yields events
            # the moment EITHER producer puts one. This is the same pattern
            # the v2 chat router uses (chat.py:537-557).
            pump_task = _asyncio.create_task(_pump_agent())

            while True:
                src, item = await events_q.get()
                if src == "done":
                    break
                if src == "progress":
                    # Engine progress beat — forward in real time.
                    _counts["engine_progress"] += 1
                    print(f"[v3-yield] progress #{_counts['engine_progress']} stage={item.get('stage')!r}",
                          file=_sys.stderr, flush=True)
                    yield sse_pack({"type": "progress", "payload": item})
                    continue
                # src == "agent"
                ev = item
                kind = ev["type"]
                _counts[kind] = _counts.get(kind, 0) + 1
                if kind == "token":
                    chunks.append(ev["text"])
                    yield sse_pack({"type": "token", "module": None, "text": ev["text"]})
                elif kind == "tool_start":
                    print(f"[v3] tool_start name={ev.get('name')!r}",
                          file=_sys.stderr, flush=True)
                    # Student-facing label, not the raw tool name (`commit_slice`
                    # meant nothing to the thesis-writer watching the bubble).
                    # Built here because this is the only layer with the tool
                    # args (read_file needs the path to say "guide" vs "upload").
                    yield sse_pack({"type": "progress", "payload": {
                        "stage": ev["name"],
                        "message": _tool_progress_label(ev.get("name", ""), ev.get("args") or {}),
                    }})
                elif kind == "tool_end":
                    # No progress line on tool_end: it carries no args, so a
                    # read_file end can't reproduce the start's friendly label
                    # and would show a mismatched duplicate. The start line
                    # already told the user what's happening; the next event
                    # (another tool or the reply tokens) supersedes it.
                    print(f"[v3] tool_end name={ev.get('name')!r}",
                          file=_sys.stderr, flush=True)
                    tool_results.append((str(ev.get("name") or ""),
                                         str(ev.get("preview") or "")))
                elif kind == "tool_calls":
                    # Interactive widget hint — render as clickable cards
                    # in MessageBubble. Collect every hint this turn emits.
                    _payload = ev.get("payload")
                    # Decision: after a direct command/question, suppress a
                    # fresh choice menu. Papers and artifact cards still pass;
                    # only the autonomy-killing follow-up grid is removed.
                    if execute_now and isinstance(_payload, dict) \
                            and _payload.get("widget_type") == "card_grid":
                        continue
                    if _payload:
                        widget_hints.append(_payload)
                    yield sse_pack({"type": "tool_calls", "payload": _payload})
                elif kind == "usage":
                    # Token usage for this LLM step — accumulate (don't forward
                    # mid-stream; the total is persisted + sent in `done`).
                    _usage_in += int(ev.get("input_tokens", 0) or 0)
                    _usage_out += int(ev.get("output_tokens", 0) or 0)
                    if ev.get("model"):
                        _served_models.add(str(ev["model"]))
                elif kind == "error":
                    logger.error("agent turn error for thread %s: %s", thread_pk, ev["message"])
                    print(f"[v3] ERROR msg={ev.get('message')!r}",
                          file=_sys.stderr, flush=True)
                    yield sse_pack({"type": "error", "message": ev["message"]})
                elif kind == "done":
                    break
            # Re-raise any exception the pump task captured.
            await pump_task
            # Normal completion: persist + charge, then send `done`. Done inside
            # the try (before the finally) so the finally's _finalize() is a
            # no-op here and the done event still reaches the client.
            done_payload = _finalize()
            if done_payload is not None:
                yield sse_pack(done_payload)
            # Auto-name the thread once (cost-aware): free from M1 research_title
            # if present, else one cheap flash-lite summary of this message.
            # Runs in a background worker so it never delays the stream.
            try:
                from ..thread_namer import schedule_autoname, schedule_autoname_project
                schedule_autoname(engine, thread_pk, text)
                # Same for the project title while it's still "Untitled thesis"
                # — uses gemini-2.5-flash; no-op once a real name is set.
                schedule_autoname_project(engine, project_id, text)
            except Exception:  # noqa: BLE001
                logger.exception("schedule_autoname failed for thread %s", thread_pk)
        except Exception as _e:
            # If stream_turn raises outside its own try (or the for loop
            # itself dies), the user gets a silent stream end. Surface it.
            import traceback as _tb
            print(f"\n=== chat_v3 stream crashed for thread {thread_pk} ===",
                  file=_sys.stderr, flush=True)
            _tb.print_exc(file=_sys.stderr)
            print("=== end traceback ===\n", file=_sys.stderr, flush=True)
            yield sse_pack({"type": "error",
                            "message": f"{type(_e).__name__}: {_e}"})
            # Persist whatever streamed before the crash + charge for it.
            done_payload = _finalize()
            if done_payload is not None:
                yield sse_pack(done_payload)
        finally:
            # Client gone (browser close/reload) → GeneratorExit/CancelledError
            # skip both branches above. Cancel the agent task so its research /
            # LLM calls stop instead of running orphaned to completion (which
            # kept burning tokens for output nobody receives), then persist
            # whatever streamed so the partial answer isn't lost. _finalize is
            # idempotent, so the normal/error paths above already ran it and
            # this is a no-op there.
            if pump_task is not None and not pump_task.done():
                pump_task.cancel()
            if _bind_ctx is not None:
                try:
                    _bind_ctx.__exit__(None, None, None)
                except Exception:  # noqa: BLE001
                    pass
            _engine_progress.unregister(langgraph_thread_id)
            _finalize()
            print(f"[v3] turn done counts={_counts}",
                  file=_sys.stderr, flush=True)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})

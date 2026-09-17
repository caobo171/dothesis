"""Durable, token-accurate accounting for claim-review model invocations.

`ToolRun` is intentionally reused as the durable invocation receipt: it already
survives request crashes and has a JSON metrics slot for the review/chunk key.
The cache calls this module only inside its miss ``compute`` function, so a
cached model result cannot create a receipt or debit credits.
"""
from __future__ import annotations

import logging
import hashlib
import copy
import os
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator

from sqlalchemy import bindparam, select, text

from agent.usage import extract_usage
from orchestrator.agents.base import bounded_invoke
from orchestrator.token_meter import LedgerCallback
from orchestrator.llm import resolve_orchestrator_model

from .credit_ledger import InsufficientCredit, debit
from .db import get_session_factory
from .models import TokenLedger, ToolRun, User
from .tool_billing import tool_cost


logger = logging.getLogger(__name__)
TOOL = "claim-review-llm"
DEFAULT_CREDIT_LIMIT = 20
PENDING_LEASE_SECONDS = 600

# This connection is intentionally outside request/session lifecycle. PostgreSQL
# advisory locks are session-scoped, so returning it to SQLAlchemy's pool would
# make a receipt look owned by an unrelated future request.
_OWNER_STATE_LOCK = threading.Lock()
_owner_connection = None
_owner_engine = None
_owner_lock_id: int | None = None
_owner_pid: int | None = None


class ClaimReviewBudgetExceeded(RuntimeError):
    """The resumable review reached its configured soft credit checkpoint."""


class ClaimReviewPending(ClaimReviewBudgetExceeded):
    """A previous model invocation is still settling, not a credit shortage."""


class ClaimReviewOwnerUnavailable(RuntimeError):
    """The process cannot safely prove ownership of a newly billed call."""


def _reset_owner_state(*, close: bool) -> None:
    """Forget a process owner; only engine replacement may close it deliberately."""
    global _owner_connection, _owner_engine, _owner_lock_id, _owner_pid
    connection = _owner_connection
    _owner_connection = _owner_engine = None
    _owner_lock_id = _owner_pid = None
    if close and connection is not None:
        try:
            connection.close()
        except Exception:
            pass


def _connection_is_healthy(connection) -> bool:
    try:
        cursor = connection.cursor()
        try:
            cursor.execute("SELECT 1")
            cursor.fetchone()
            connection.commit()
        finally:
            cursor.close()
        return True
    except Exception:
        return False


def _ensure_process_owner_lock() -> int | None:
    """Return this process's live advisory-lock identity for a new receipt.

    A dead owner connection is not silently re-registered with a new ID. Its
    late worker may still settle a started receipt, and swapping identities
    would make that active work appear orphaned. A fresh process (or a test's
    replaced engine) receives a fresh key instead.
    """
    global _owner_connection, _owner_engine, _owner_lock_id, _owner_pid
    from .db import get_engine  # lazy: test engines can be rebound
    engine = get_engine()
    if engine.dialect.name != "postgresql":
        return None
    pid = os.getpid()
    with _OWNER_STATE_LOCK:
        if _owner_pid is not None and _owner_pid != pid:
            # Forked children inherit Python globals but not process ownership.
            # Do not close the inherited descriptor: it belongs to the parent.
            _reset_owner_state(close=False)
        elif _owner_engine is not None and _owner_engine is not engine:
            _reset_owner_state(close=True)
        if _owner_connection is not None:
            if _connection_is_healthy(_owner_connection):
                return _owner_lock_id
            raise ClaimReviewOwnerUnavailable("Không thể xác thực phiên sở hữu lượt gọi đang hoạt động.")

        # A positive signed 63-bit key maps cleanly to pg_locks' classid/objid.
        lock_id = uuid.uuid4().int & ((1 << 63) - 1)
        if lock_id == 0:
            lock_id = 1
        connection = engine.raw_connection()
        try:
            cursor = connection.cursor()
            try:
                cursor.execute("SELECT pg_try_advisory_lock(%s)", (lock_id,))
                acquired = cursor.fetchone()[0]
                if not acquired:
                    raise ClaimReviewOwnerUnavailable("Không thể đăng ký phiên sở hữu lượt gọi.")
                # Advisory locks are session-scoped, but commit avoids retaining
                # an idle transaction for this process-lifetime connection.
                connection.commit()
            finally:
                cursor.close()
            # Detach so normal pool cleanup cannot close or reuse this session.
            connection.detach()
        except Exception:
            try:
                connection.close()
            except Exception:
                pass
            raise
        _owner_connection = connection
        _owner_engine = engine
        _owner_lock_id = lock_id
        _owner_pid = pid
        return lock_id


def _metrics(row: ToolRun) -> dict[str, Any]:
    value = row.metrics
    # JSON columns do not reliably mark an in-place nested mutation dirty.
    return dict(value) if isinstance(value, dict) else {}


def _receipt_rows(session, *, project_id: uuid.UUID, user_id: uuid.UUID, review_id: str,
                  lock: bool = False) -> list[ToolRun]:
    statement = select(ToolRun).where(
        ToolRun.project_id == project_id, ToolRun.user_id == user_id, ToolRun.tool == TOOL,
    )
    if lock:
        statement = statement.with_for_update()
    # ToolRun.metrics is deliberately not indexed by this short-lived review
    # id. Limit the scan to this user/project then filter the compact receipt.
    return [row for row in session.scalars(statement).all()
            if _metrics(row).get("review_id") == review_id]


def _usage_row(metrics: dict[str, Any]) -> dict[str, Any] | None:
    usage = metrics.get("usage")
    if not isinstance(usage, dict):
        return None
    return {
        "model": str(usage.get("model") or "unknown"),
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
    }


def _expired(row: ToolRun) -> bool:
    created = row.created_at
    if created is None:
        return False
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - created).total_seconds() > PENDING_LEASE_SECONDS


def _owner_id(metrics: dict[str, Any]) -> int | None:
    try:
        value = int(metrics.get("owner_lock_id"))
    except (TypeError, ValueError):
        return None
    return value if 0 < value < (1 << 63) else None


def _active_owner_lock_ids(session, owner_ids: set[int]) -> set[int] | None:
    """Read all relevant process locks in one query, failing closed on errors."""
    if not owner_ids or session.bind is None or session.bind.dialect.name != "postgresql":
        return None
    statement = text("""
        SELECT ((classid::bigint << 32) + objid::bigint) AS owner_lock_id
        FROM pg_locks
        WHERE locktype = 'advisory' AND granted = true AND objsubid = 1
          AND database = (SELECT oid FROM pg_database WHERE datname = current_database())
          AND ((classid::bigint << 32) + objid::bigint) IN :owner_ids
    """).bindparams(bindparam("owner_ids", expanding=True))
    try:
        return {int(row.owner_lock_id) for row in session.execute(statement, {"owner_ids": sorted(owner_ids)})}
    except Exception:
        # A database visibility problem must block new dispatch, not declare an
        # active worker dead and risk a second paid provider request.
        logger.warning("claim review owner-lock check unavailable; retaining pending receipts")
        return None


def _interrupt_receipt(row: ToolRun, metrics: dict[str, Any], *, orphaned_owner: bool) -> None:
    row.metrics = {**metrics, "status": "interrupted", "usage_unknown": True,
                   **({"orphaned_owner": True} if orphaned_owner else {})}
    row.status = "failed"


def _reconcile_started_receipts(session, rows: list[ToolRun]) -> int:
    """Clear only receipts whose recorded owner is provably gone.

    Owner-marked rows never use age as a liveness signal. Rows created before
    this rollout have no durable owner identity, so they retain the bounded TTL
    fallback that prevents a legacy permanent dispatch lock.
    """
    started = [(row, _metrics(row)) for row in rows if _metrics(row).get("status") == "started"]
    active = _active_owner_lock_ids(session, {owner for _, metrics in started if (owner := _owner_id(metrics)) is not None})
    changed = 0
    for row, metrics in started:
        owner = _owner_id(metrics)
        if owner is not None:
            if active is not None and owner not in active:
                _interrupt_receipt(row, metrics, orphaned_owner=True)
                changed += 1
        elif _expired(row):
            _interrupt_receipt(row, metrics, orphaned_owner=False)
            changed += 1
    return changed


def _summary(rows: list[ToolRun], *, credit_limit: int, balance: int | None = None) -> dict[str, Any]:
    usage = [item for row in rows if (item := _usage_row(_metrics(row))) is not None]
    cost = tool_cost(TOOL, usage=usage, ok=True)
    charged = sum(max(0, int(row.credits_charged or 0)) for row in rows)
    completed = sum(_metrics(row).get("settled") is True for row in rows)
    # This checkpoint is deliberately cumulative. Charging minimum one credit
    # per short call would make a 166-chunk review cost far more than its tokens.
    return {
        "calls": len(rows), "settled_calls": completed,
        # Owner-marked receipts are pending until their process lock is proven
        # absent. Age remains only the compatibility fallback for legacy rows.
        "pending_calls": sum(_metrics(row).get("status") == "started" for row in rows),
        "prompt_tokens": sum(item["prompt_tokens"] for item in usage),
        "completion_tokens": sum(item["completion_tokens"] for item in usage),
        "credits_cost": cost, "credits_charged": charged,
        "credit_limit": max(0, credit_limit), "credits_limit": max(0, credit_limit),
        "balance": balance, "credit_balance": balance,
        "checkpoint_reached": cost >= max(0, credit_limit) if credit_limit else False,
    }


def get_review_billing(project_id: uuid.UUID, user_id: uuid.UUID, review_id: str,
                       credit_limit: int = DEFAULT_CREDIT_LIMIT) -> dict[str, Any]:
    """Return compact billing data, reconciling durable orphan metadata only."""
    Session = get_session_factory()
    with Session.begin() as session:
        user = session.get(User, user_id)
        rows = _receipt_rows(session, project_id=project_id, user_id=user_id, review_id=str(review_id), lock=True)
        _reconcile_started_receipts(session, rows)
        return _summary(rows,
                        credit_limit=credit_limit, balance=(user.credit if user else 0))


def reconcile_claim_review_orphans() -> int:
    """Startup/preflight recovery for receipts whose owning API process died."""
    Session = get_session_factory()
    with Session.begin() as session:
        rows = session.scalars(select(ToolRun).where(ToolRun.tool == TOOL, ToolRun.status == "running").with_for_update()).all()
        return _reconcile_started_receipts(session, list(rows))


@dataclass
class ClaimReviewBilling:
    project_id: uuid.UUID
    user_id: uuid.UUID
    review_id: str
    chunk_index: int
    credit_limit: int = DEFAULT_CREDIT_LIMIT

    def __post_init__(self) -> None:
        self.review_id = str(self.review_id)
        self.credit_limit = max(0, int(self.credit_limit))

    def _check_locked(self, session) -> None:
        """Validate dispatch eligibility while holding the same user lock."""
        user = session.scalar(select(User).where(User.id == self.user_id).with_for_update())
        if user is None or (user.credit or 0) <= 0:
            raise ClaimReviewBudgetExceeded("Không đủ tín dụng để tiếp tục kiểm tra nhận định.")
        rows = _receipt_rows(session, project_id=self.project_id, user_id=self.user_id,
                             review_id=self.review_id, lock=True)
        _reconcile_started_receipts(session, rows)
        summary = _summary(rows, credit_limit=self.credit_limit, balance=user.credit)
        if self.credit_limit > 0 and summary["credits_cost"] >= self.credit_limit:
            raise ClaimReviewBudgetExceeded("Đã đạt ngưỡng tín dụng của lượt kiểm tra; bạn có thể tiếp tục sau.")
        if any(_metrics(row).get("status") == "started" for row in rows):
            # bounded_invoke cannot kill its timed-out thread. Waiting for
            # that receipt avoids dispatching a duplicate paid request.
            raise ClaimReviewPending("Lượt gọi trước vẫn đang hoàn tất; vui lòng thử lại sau.")

    def preflight(self) -> None:
        """Public read/check boundary for callers that need an early status."""
        Session = get_session_factory()
        with Session.begin() as session:
            self._check_locked(session)

    def _begin(self, *, stage: str, prompt_key: str) -> int:
        owner_lock_id = _ensure_process_owner_lock()
        Session = get_session_factory()
        with Session.begin() as session:
            # Decision: validation and receipt creation are one lock-held
            # transaction. A timeout/retry cannot pass a stale preflight gap.
            self._check_locked(session)
            row = ToolRun(user_id=self.user_id, project_id=self.project_id, tool=TOOL,
                          surface="web", ok=False, status="running", progress_done=0, progress_total=1,
                          metrics={"review_id": self.review_id, "chunk_index": self.chunk_index,
                                   "stage": stage, "prompt_key": prompt_key, "status": "started",
                                   **({"owner_lock_id": owner_lock_id} if owner_lock_id is not None else {})})
            session.add(row)
            session.flush()
            return int(row.id)

    def _settle(self, receipt_id: int, response: Any, duration_ms: int) -> None:
        """Settle in the invoking worker; a route timeout cannot lose its cost."""
        usage = extract_usage(response)
        metadata = getattr(response, "response_metadata", None) or {}
        model = str(metadata.get("model_name") or metadata.get("model") or
                    getattr(response, "model", None) or resolve_orchestrator_model())
        row_usage = {"model": model, "prompt_tokens": int(usage.get("in") or 0),
                     "completion_tokens": int(usage.get("out") or 0)}
        Session = get_session_factory()
        try:
            with Session.begin() as session:
                # Keep lock order stable: user first, then this receipt and the
                # review's receipts. This also serializes two workers settling.
                user = session.scalar(select(User).where(User.id == self.user_id).with_for_update())
                receipt = session.scalar(select(ToolRun).where(ToolRun.id == receipt_id).with_for_update())
                if user is None or receipt is None:
                    return
                metrics = dict(_metrics(receipt))
                if metrics.get("settled") is True:
                    return
                rows = _receipt_rows(session, project_id=self.project_id, user_id=self.user_id,
                                     review_id=self.review_id, lock=True)
                prior = _summary([row for row in rows if row.id != receipt.id],
                                 credit_limit=self.credit_limit, balance=user.credit)
                projected_usage = [_usage_row(_metrics(row)) for row in rows if row.id != receipt.id]
                projected_usage = [item for item in projected_usage if item is not None] + [row_usage]
                due_total = tool_cost(TOOL, usage=projected_usage, ok=True)
                capped_due = min(due_total, max(0, self.credit_limit)) if self.credit_limit > 0 else due_total
                increment = max(0, capped_due - prior["credits_charged"])
                charged = min(increment, max(0, user.credit or 0))
                # Token telemetry is recorded even when the live balance cannot
                # cover it. A zero/unknown usage is never converted to a guess.
                session.add(TokenLedger(project_id=self.project_id, user_id=self.user_id,
                                        action_kind=TOOL, model=model,
                                        prompt_tokens=row_usage["prompt_tokens"],
                                        completion_tokens=row_usage["completion_tokens"],
                                        reserved=0, duration_ms=max(0, duration_ms)))
                if charged:
                    debit(session, user, delta=charged, reason="claim_review",
                          ref_type="tool_run", ref_id=uuid.UUID(int=receipt.id))
                metrics.update({"status": "settled", "settled": True, "usage": row_usage})
                receipt.metrics = metrics
                receipt.ok = True
                receipt.status = "done"
                receipt.prompt_tokens = row_usage["prompt_tokens"]
                receipt.completion_tokens = row_usage["completion_tokens"]
                receipt.duration_ms = max(0, duration_ms)
                receipt.credits_cost = max(0, due_total - prior["credits_cost"])
                receipt.credits_charged = charged
        except Exception:
            # Accounting cannot discard a model response. The started receipt
            # remains visible for forensics/reconciliation instead of faking a
            # successful debit.
            logger.exception("claim review billing settlement failed receipt=%s", receipt_id)

    def _fail(self, receipt_id: int, duration_ms: int) -> None:
        Session = get_session_factory()
        try:
            with Session.begin() as session:
                receipt = session.scalar(select(ToolRun).where(ToolRun.id == receipt_id).with_for_update())
                if receipt is not None and not _metrics(receipt).get("settled"):
                    metrics = dict(_metrics(receipt)); metrics["status"] = "provider_failed"
                    receipt.metrics = metrics; receipt.status = "failed"; receipt.duration_ms = max(0, duration_ms)
        except Exception:
            logger.exception("claim review billing failure receipt update failed receipt=%s", receipt_id)

    def invoke(self, llm: Any, prompt: Any, *, stage: str = "review", prompt_key: str = "",
               max_seconds: int = 45, on_response=None) -> Any:
        """Invoke with late-worker settlement rather than post-timeout billing."""
        prompt_key = prompt_key or hashlib.sha256(str(prompt).encode("utf-8")).hexdigest()
        receipt_id = self._begin(stage=stage, prompt_key=prompt_key)
        billing = self

        class SettlingLLM:
            def invoke(self, inner_prompt: Any) -> Any:
                started = time.monotonic()
                # `_get_llm()` creates a fresh model for this request. Remove
                # only its unattributed callback: this receipt writes the
                # project/user-attributed ledger row and must not double-meter.
                model = llm
                callbacks = getattr(llm, "callbacks", None)
                if isinstance(callbacks, list):
                    # Do not mutate the factory model: callers may reuse it in
                    # another thread. A shallow copy keeps provider config and
                    # all non-ledger callbacks intact.
                    model = copy.copy(llm)
                    model.callbacks = [callback for callback in callbacks
                                       if not (isinstance(callback, LedgerCallback) and callback.project_id is None)]
                try:
                    response = model.invoke(inner_prompt)
                except Exception:
                    billing._fail(receipt_id, int((time.monotonic() - started) * 1000))
                    raise
                # Cache publication precedes clearing pending so a resumed request
                # can consume a late response instead of buying it again.
                try:
                    if on_response is not None:
                        on_response(response)
                finally:
                    billing._settle(receipt_id, response, int((time.monotonic() - started) * 1000))
                return response

        return bounded_invoke(SettlingLLM(), prompt, max_seconds=max_seconds, retries=0)

    def summary(self) -> dict[str, Any]:
        return get_review_billing(project_id=self.project_id, user_id=self.user_id,
                                  review_id=self.review_id, credit_limit=self.credit_limit)


@contextmanager
def claim_review_billing(*, project_id: uuid.UUID, user_id: uuid.UUID, review_id: str,
                         chunk_index: int, credit_limit: int = DEFAULT_CREDIT_LIMIT) -> Iterator[ClaimReviewBilling]:
    """Scope explicit request identity; it carries no global/env user state."""
    yield ClaimReviewBilling(project_id, user_id, review_id, chunk_index, credit_limit)

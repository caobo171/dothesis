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
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

from sqlalchemy import select

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


class ClaimReviewBudgetExceeded(RuntimeError):
    """The resumable review reached its configured soft credit checkpoint."""


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


def _summary(rows: list[ToolRun], *, credit_limit: int, balance: int | None = None) -> dict[str, Any]:
    usage = [item for row in rows if (item := _usage_row(_metrics(row))) is not None]
    cost = tool_cost(TOOL, usage=usage, ok=True)
    charged = sum(max(0, int(row.credits_charged or 0)) for row in rows)
    completed = sum(_metrics(row).get("settled") is True for row in rows)
    # This checkpoint is deliberately cumulative. Charging minimum one credit
    # per short call would make a 166-chunk review cost far more than its tokens.
    return {
        "calls": len(rows), "settled_calls": completed,
        "prompt_tokens": sum(item["prompt_tokens"] for item in usage),
        "completion_tokens": sum(item["completion_tokens"] for item in usage),
        "credits_cost": cost, "credits_charged": charged,
        "credit_limit": max(0, credit_limit), "credits_limit": max(0, credit_limit),
        "balance": balance, "credit_balance": balance,
        "checkpoint_reached": cost >= max(0, credit_limit) if credit_limit else False,
    }


def get_review_billing(project_id: uuid.UUID, user_id: uuid.UUID, review_id: str,
                       credit_limit: int = DEFAULT_CREDIT_LIMIT) -> dict[str, Any]:
    """Read-only compact accounting payload safe for the review UI."""
    Session = get_session_factory()
    with Session() as session:
        user = session.get(User, user_id)
        return _summary(_receipt_rows(session, project_id=project_id, user_id=user_id, review_id=str(review_id)),
                        credit_limit=credit_limit, balance=(user.credit if user else 0))


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
        summary = _summary(rows, credit_limit=self.credit_limit, balance=user.credit)
        if self.credit_limit > 0 and summary["credits_cost"] >= self.credit_limit:
            raise ClaimReviewBudgetExceeded("Đã đạt ngưỡng tín dụng của lượt kiểm tra; bạn có thể tiếp tục sau.")
        if any(_metrics(row).get("status") == "started" for row in rows):
            # bounded_invoke cannot kill its timed-out thread. Waiting for
            # that receipt avoids dispatching a duplicate paid request.
            raise ClaimReviewBudgetExceeded("Lượt gọi trước vẫn đang hoàn tất; vui lòng thử lại sau.")

    def preflight(self) -> None:
        """Public read/check boundary for callers that need an early status."""
        Session = get_session_factory()
        with Session.begin() as session:
            self._check_locked(session)

    def _begin(self, *, stage: str, prompt_key: str) -> int:
        Session = get_session_factory()
        with Session.begin() as session:
            # Decision: validation and receipt creation are one lock-held
            # transaction. A timeout/retry cannot pass a stale preflight gap.
            self._check_locked(session)
            row = ToolRun(user_id=self.user_id, project_id=self.project_id, tool=TOOL,
                          surface="web", ok=False, status="running", progress_done=0, progress_total=1,
                          metrics={"review_id": self.review_id, "chunk_index": self.chunk_index,
                                   "stage": stage, "prompt_key": prompt_key, "status": "started"})
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
               max_seconds: int = 45) -> Any:
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

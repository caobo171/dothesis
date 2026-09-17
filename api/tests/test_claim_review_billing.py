import uuid
import time
import threading

import pytest
from sqlalchemy.orm import Session

from app.claim_review_billing import (
    ClaimReviewBudgetExceeded, ClaimReviewBilling, ClaimReviewPending,
    get_review_billing, reconcile_claim_review_orphans,
)
import app.claim_review_billing as billing_module
from app.db import get_engine
from app.models import CreditTransaction, Project, TokenLedger, ToolRun, User
from tests.conftest import make_user
from orchestrator.tools.research_cache import cached_call


class Response:
    usage_metadata = {"input_tokens": 1200, "output_tokens": 300}
    response_metadata = {"model_name": "gemini-2.5-flash"}


class LLM:
    def __init__(self):
        self.calls = 0

    def invoke(self, _prompt):
        self.calls += 1
        return Response()


def _scope(credit=100, limit=20):
    with Session(get_engine()) as db:
        user = make_user(db, credit=credit)
        project = Project(user_id=user.id, name="T", current_module="M5", status="draft")
        db.add(project); db.commit()
        return ClaimReviewBilling(project.id, user.id, str(uuid.uuid4()), 0, limit), project.id, user.id


def test_real_invocation_records_usage_and_charges_even_if_caller_rejects_result():
    billing, project_id, user_id = _scope()
    # Billing happens before the caller parses JSON, so a malformed structured
    # result is still a paid provider response rather than a silent free call.
    assert isinstance(billing.invoke(LLM(), "invalid-json-response", stage="extract"), Response)
    summary = get_review_billing(project_id=project_id, user_id=user_id, review_id=billing.review_id)
    assert summary["calls"] == summary["settled_calls"] == 1
    assert summary["prompt_tokens"] == 1200 and summary["completion_tokens"] == 300
    assert summary["credits_charged"] > 0
    with Session(get_engine()) as db:
        assert db.query(TokenLedger).filter_by(project_id=project_id, user_id=user_id).count() == 1
        assert db.query(CreditTransaction).filter_by(user_id=user_id, reason="claim_review").count() == 1


def test_settlement_receipt_is_idempotent():
    billing, project_id, user_id = _scope()
    receipt = billing._begin(stage="evaluate", prompt_key="same")
    billing._settle(receipt, Response(), 12)
    billing._settle(receipt, Response(), 12)
    with Session(get_engine()) as db:
        assert db.query(ToolRun).filter_by(id=receipt).one().metrics["settled"] is True
        assert db.query(TokenLedger).filter_by(project_id=project_id, user_id=user_id).count() == 1
        assert db.query(CreditTransaction).filter_by(user_id=user_id, reason="claim_review").count() == 1


def test_small_calls_are_priced_cumulatively_instead_of_one_credit_each():
    billing, project_id, user_id = _scope()
    llm = LLM()
    billing.invoke(llm, "first")
    billing.invoke(llm, "second")
    summary = get_review_billing(project_id, user_id, billing.review_id)
    assert summary['calls'] == 2
    assert summary['prompt_tokens'] == 2400
    assert summary['credits_charged'] == 1


def test_cache_hit_never_creates_a_receipt_or_charge(tmp_path, monkeypatch):
    monkeypatch.setenv("DOTHESIS_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    billing, project_id, user_id = _scope()
    llm = LLM()
    def compute():
        billing.invoke(llm, "same")
        return {"parsed": True}
    first = cached_call("claim-test", {"prompt": "same"}, compute)
    second = cached_call("claim-test", {"prompt": "same"}, compute)
    assert first == second == {"parsed": True} and llm.calls == 1
    assert get_review_billing(project_id=project_id, user_id=user_id, review_id=billing.review_id)["calls"] == 1


def test_zero_balance_and_cumulative_checkpoint_stop_before_another_call():
    billing, _project_id, _user_id = _scope(credit=0)
    llm = LLM()
    with pytest.raises(ClaimReviewBudgetExceeded):
        billing.invoke(llm, "not sent")
    assert llm.calls == 0

    limited, _project_id, _user_id = _scope(credit=100, limit=1)
    limited.invoke(LLM(), "first")
    with pytest.raises(ClaimReviewBudgetExceeded):
        limited.invoke(LLM(), "second")


def test_timed_out_request_settles_late_and_blocks_duplicate_dispatch():
    class SlowLLM(LLM):
        def invoke(self, prompt):
            entered.set()
            assert release.wait(2)
            return super().invoke(prompt)

    billing, project_id, user_id = _scope()
    entered, release = threading.Event(), threading.Event()
    with pytest.raises(TimeoutError):
        billing.invoke(SlowLLM(), "late", max_seconds=.01)
    assert entered.wait(1)
    with pytest.raises(ClaimReviewBudgetExceeded):
        billing.invoke(LLM(), "duplicate")
    release.set()
    deadline = time.monotonic() + 2
    summary = get_review_billing(project_id, user_id, billing.review_id)
    while summary["settled_calls"] != 1 and time.monotonic() < deadline:
        time.sleep(.01)
        summary = get_review_billing(project_id, user_id, billing.review_id)
    assert summary["settled_calls"] == 1 and summary["credits_charged"] > 0
    assert summary["credits_limit"] == 20 and summary["credit_balance"] is not None


def test_expired_receipt_does_not_permanently_lock_review_or_invent_usage():
    from datetime import datetime, timedelta, timezone
    from app.claim_review_billing import PENDING_LEASE_SECONDS
    billing, pid, uid = _scope()
    receipt = billing._begin(stage='evaluate', prompt_key='orphan')
    with Session(get_engine()) as db:
        row = db.get(ToolRun, receipt)
        # This fixture models a receipt written before owner-lock metadata was
        # introduced. New owner-marked receipts must never expire by age.
        row.metrics = {key: value for key, value in row.metrics.items() if key != 'owner_lock_id'}
        row.created_at = datetime.now(timezone.utc) - timedelta(seconds=PENDING_LEASE_SECONDS + 1)
        db.commit()
    billing.preflight()
    with Session(get_engine()) as db:
        row = db.get(ToolRun, receipt)
        assert row.metrics['status'] == 'interrupted'
        assert row.metrics['usage_unknown'] is True
        assert not row.metrics.get('usage')
    assert billing.summary()['pending_calls'] == 0
    # A real late receipt remains chargeable exactly once.
    billing._settle(receipt, Response(), 100)
    billing._settle(receipt, Response(), 100)
    assert billing.summary()['settled_calls'] == 1


def test_recent_receipt_with_absent_owner_lock_is_reconciled_without_ttl(monkeypatch):
    """A restarted API can release a fresh receipt whose owner process died."""
    owner_lock_id = 7_654_321
    monkeypatch.setattr(billing_module, "_ensure_process_owner_lock", lambda: owner_lock_id)
    monkeypatch.setattr(billing_module, "_active_owner_lock_ids", lambda _session, _ids: set())
    billing, pid, uid = _scope()
    receipt = billing._begin(stage="evaluate", prompt_key="fresh-owner")
    with Session(get_engine()) as db:
        row = db.get(ToolRun, receipt)
        assert row.metrics["owner_lock_id"] == owner_lock_id
        assert not row.metrics.get("usage_unknown")

    assert billing.summary()["pending_calls"] == 0
    with Session(get_engine()) as db:
        row = db.get(ToolRun, receipt)
        assert row.metrics["status"] == "interrupted"
        assert row.metrics["orphaned_owner"] is True
        assert row.metrics["usage_unknown"] is True
    # A new invocation may proceed; no old receipt is treated as a live worker.
    billing.preflight()


def test_foreign_live_owner_lock_keeps_fresh_receipt_pending_across_startup(monkeypatch):
    """One API process must never orphan another process's active model call."""
    owner_lock_id = 8_765_432
    monkeypatch.setattr(billing_module, "_ensure_process_owner_lock", lambda: owner_lock_id)
    monkeypatch.setattr(billing_module, "_active_owner_lock_ids", lambda _session, _ids: {owner_lock_id})
    billing, _pid, _uid = _scope()
    receipt = billing._begin(stage="evaluate", prompt_key="foreign-live")

    assert reconcile_claim_review_orphans() == 0
    assert billing.summary()["pending_calls"] == 1
    with pytest.raises(ClaimReviewPending):
        billing.preflight()
    with Session(get_engine()) as db:
        assert db.get(ToolRun, receipt).metrics["status"] == "started"


def test_recent_legacy_receipt_without_owner_keeps_ttl_fallback(monkeypatch):
    """Unknown pre-rollout ownership cannot be guessed dead at API startup."""
    monkeypatch.setattr(billing_module, "_ensure_process_owner_lock", lambda: None)
    billing, _pid, _uid = _scope()
    receipt = billing._begin(stage="evaluate", prompt_key="legacy-recent")

    assert reconcile_claim_review_orphans() == 0
    assert billing.summary()["pending_calls"] == 1
    with pytest.raises(ClaimReviewPending):
        billing.preflight()
    with Session(get_engine()) as db:
        row = db.get(ToolRun, receipt)
        assert "owner_lock_id" not in row.metrics
        assert row.metrics["status"] == "started"


def test_late_response_is_retained_before_pending_is_cleared():
    billing, pid, uid = _scope()
    entered, release, retained = threading.Event(), threading.Event(), threading.Event()
    class Slow(LLM):
        def invoke(self, prompt):
            entered.set()
            assert release.wait(2)
            return Response()
    def retain(response):
        assert billing.summary()['pending_calls'] == 1
        retained.set()
    with pytest.raises(TimeoutError):
        billing.invoke(Slow(), 'late-cached', max_seconds=.01, on_response=retain)
    assert entered.wait(1)
    release.set()
    assert retained.wait(2)
    deadline = time.monotonic() + 2
    while billing.summary()['pending_calls'] and time.monotonic() < deadline:
        time.sleep(.01)
    assert billing.summary()['pending_calls'] == 0
    assert billing.summary()['settled_calls'] == 1


def test_real_postgres_session_close_releases_fresh_receipt_immediately(monkeypatch):
    owner = get_engine().raw_connection()
    owner.detach()
    lock_id = (uuid.uuid4().int & ((1 << 63) - 1)) or 1
    try:
        cursor = owner.cursor()
        cursor.execute('SELECT pg_advisory_lock(%s)', (lock_id,))
        owner.commit()
        cursor.close()
        monkeypatch.setattr(billing_module, '_ensure_process_owner_lock', lambda: lock_id)
        billing, _, _ = _scope()
        receipt = billing._begin(stage='evaluate', prompt_key='real-session')
        assert reconcile_claim_review_orphans() == 0
        assert billing.summary()['pending_calls'] == 1
        with pytest.raises(ClaimReviewPending):
            billing.preflight()
    finally:
        # A process exit closes this physical session; no mocked pg_locks lookup.
        owner.close()
    assert reconcile_claim_review_orphans() == 1
    assert billing.summary()['pending_calls'] == 0
    billing.preflight()
    with Session(get_engine()) as db:
        row = db.get(ToolRun, receipt)
        assert row.metrics['orphaned_owner'] is True
        assert row.credits_charged == 0

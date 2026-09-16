import uuid
import time
import threading

import pytest
from sqlalchemy.orm import Session

from app.claim_review_billing import (
    ClaimReviewBudgetExceeded, ClaimReviewBilling, get_review_billing,
)
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

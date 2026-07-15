"""DOTHESIS_AGENT_V3 — the deep-agent turn behind the same SSE contract."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import Message, User


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "true")
    monkeypatch.setenv("DOTHESIS_AGENT_V3", "1")
    return TestClient(create_app())


def _setup_project(client) -> tuple[uuid.UUID, uuid.UUID]:
    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"u{uuid.uuid4().hex[:6]}@x",
                 username=f"u{uuid.uuid4().hex[:6]}",
                 password_hash="x", email_verified=True, credit=10000)
        db.add(u); db.commit()
        from app.security import create_session
        token = create_session(db, u)
    client.headers["Authorization"] = f"Bearer {token}"
    pid = client.post("/api/v1/projects", json={"name": "T"}).json()["id"]
    # GET→POST migration: list route renamed to /threads/list (POST).
    tid = client.post(f"/api/v1/projects/{pid}/threads/list").json()[0]["id"]
    return uuid.UUID(pid), uuid.UUID(tid)


def test_v3_turn_streams_and_persists(client, monkeypatch):
    pid, tid = _setup_project(client)

    # Stub the agent layer: a fixed event stream instead of a model call.
    # The contract under test is chat_v3's bridging — SSE shapes + Message
    # persistence — not deepagents itself.
    async def fake_stream_turn(agent, thread_id, text, attachments=None, store=None):
        for ev in [
            {"type": "tool_start", "name": "read_slice", "args": {"module": "M1"}},
            {"type": "tool_end", "name": "read_slice", "preview": "{}"},
            {"type": "token", "text": "Xin chào! "},
            {"type": "token", "text": "Bạn đã có gì cho luận văn?"},
            {"type": "done"},
        ]:
            yield ev

    async def fake_get_agent(db, project_id):
        return object()

    monkeypatch.setattr("app.routers.chat_v3._get_agent", fake_get_agent)
    monkeypatch.setattr("agent.runtime.stream_turn", fake_stream_turn)

    resp = client.post(f"/api/v1/threads/{tid}/messages", json={"text": "hello"})
    assert resp.status_code == 200
    body = resp.text
    # Tool activity rides the existing progress event the web renders live.
    assert '"type": "progress"' in body
    assert "read_slice" in body
    assert '"type": "token"' in body
    assert '"type": "done"' in body

    sf = get_session_factory()
    with sf() as db:
        msgs = db.query(Message).filter_by(thread_id=tid).order_by(Message.id).all()
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[1].content == "Xin chào! Bạn đã có gì cho luận văn?"


def test_v3_turn_debits_credits_and_records_transaction(client, monkeypatch):
    pid, tid = _setup_project(client)

    # Pin the billed model. The charge scales by credit_multiplier(), so leaving
    # this to the env default made the expectation silently track whatever that
    # default happened to be — which is how this test rotted: it was written
    # pre-multiplier and kept asserting an implicit 1.0 while the code correctly
    # billed 4.0. State the rate here so a model/default change fails loudly.
    # ⚠️ REPRICED 4.0 → 12.86: the multiplier now reads quality/model_prices.py
    # ($1.50/$9.00 — July-2026 research, corroborated by the live Ofox gateway pull)
    # instead of engine/utils/model_config.py's stale Feb-2026 $0.50/$3.00. This is a
    # ~3.2x charge increase on the CURRENT PRODUCTION DEFAULT and a business decision,
    # not arithmetic — see .superpowers/sdd/fix-credit-multiplier-report.md.
    monkeypatch.setenv("DOTHESIS_AGENT_MODEL", "gemini-3.5-flash")  # multiplier 12.86

    async def fake_stream_turn(agent, thread_id, text, attachments=None, store=None):
        yield {"type": "token", "text": "hi"}
        # 3000 tokens → max(1, round(3000/1000 * 12.857)) = 39 credits.
        yield {"type": "usage", "input_tokens": 1500, "output_tokens": 1500}
        yield {"type": "done"}

    async def fake_get_agent(db, project_id):
        return object()

    monkeypatch.setattr("app.routers.chat_v3._get_agent", fake_get_agent)
    monkeypatch.setattr("agent.runtime.stream_turn", fake_stream_turn)

    resp = client.post(f"/api/v1/threads/{tid}/messages", json={"text": "hello"})
    assert resp.status_code == 200
    assert '"type": "done"' in resp.text

    from app.models import CreditTransaction, Project
    sf = get_session_factory()
    with sf() as db:
        proj = db.get(Project, pid)
        owner = db.get(User, proj.user_id)
        assert owner.credit == 10000 - 39  # balance reduced
        txns = (db.query(CreditTransaction)
                  .filter_by(user_id=owner.id, reason="chat_turn").all())
        assert len(txns) == 1
        assert txns[0].delta == -39
        assert str(txns[0].ref_id) == str(tid)


def test_v3_turn_bills_the_model_it_actually_runs(client, monkeypatch):
    """The billed multiplier must come from the SAME resolution that picks the model.

    Regression (the chat-side twin of d4382a6): the charge scaled by
    credit_multiplier(getenv("DOTHESIS_AGENT_MODEL", "gemini-3.5-flash")) — an env
    guess with its OWN default, re-deriving what spec_from_env() had already
    decided. The two defaults disagree: on route=ofox with DOTHESIS_AGENT_MODEL
    unset, spec_from_env() resolves google/gemini-2.5-flash while billing charged
    3.5-flash's rate — an overcharge to students, one uncommented .env line away
    from production. (At the time both multipliers came from name matching, 1.0 vs
    4.0; they are now table-derived, but the disagreement this guards is the same.)

    This config is the one the ofox migration ships (.env.example comments the route
    and the model on separate lines, so the route alone gets uncommented), and it is
    exactly the config the 4.0x test above does NOT cover.
    """
    pid, tid = _setup_project(client)

    # The live-migration config: route flipped, model left to the route's default.
    monkeypatch.setenv("DOTHESIS_MODEL_ROUTE", "ofox")
    monkeypatch.delenv("DOTHESIS_AGENT_MODEL", raising=False)

    from agent.model_factory import spec_from_env
    from app.pricing import credit_multiplier

    # Derive the expectation from the run-model resolution rather than hardcoding a
    # number: the property under test is "billed model == model actually run", so
    # the test must fail on DISAGREEMENT, not on the constants changing.
    resolved = spec_from_env().model
    assert resolved == "google/gemini-2.5-flash"  # guard: pin the config we mean to test
    # Deliberately NOT a literal: the property is "billed model == model run", so this
    # must track the resolver. (The value moved 3 → 10 when pricing moved to the table:
    # the Ofox gateway resells 2.5-flash at 0.30/2.50, not Google's native 0.15/0.60,
    # so this route was never actually the 1.0 baseline the old matcher assumed.)
    expected = max(1, round(3000 / 1000 * credit_multiplier(resolved)))

    async def fake_stream_turn(agent, thread_id, text, attachments=None, store=None):
        yield {"type": "token", "text": "hi"}
        yield {"type": "usage", "input_tokens": 1500, "output_tokens": 1500}
        yield {"type": "done"}

    async def fake_get_agent(db, project_id):
        return object()

    monkeypatch.setattr("app.routers.chat_v3._get_agent", fake_get_agent)
    monkeypatch.setattr("agent.runtime.stream_turn", fake_stream_turn)

    resp = client.post(f"/api/v1/threads/{tid}/messages", json={"text": "hello"})
    assert resp.status_code == 200

    from app.models import CreditTransaction, Project
    sf = get_session_factory()
    with sf() as db:
        proj = db.get(Project, pid)
        owner = db.get(User, proj.user_id)
        assert owner.credit == 10000 - expected
        txns = (db.query(CreditTransaction)
                  .filter_by(user_id=owner.id, reason="chat_turn").all())
        assert len(txns) == 1
        assert txns[0].delta == -expected


def test_v3_error_event_surfaces(client, monkeypatch):
    pid, tid = _setup_project(client)

    async def fake_stream_turn(agent, thread_id, text, attachments=None, store=None):
        yield {"type": "error", "message": "BoomError: model exploded"}
        yield {"type": "done"}

    async def fake_get_agent(db, project_id):
        return object()

    monkeypatch.setattr("app.routers.chat_v3._get_agent", fake_get_agent)
    monkeypatch.setattr("agent.runtime.stream_turn", fake_stream_turn)

    resp = client.post(f"/api/v1/threads/{tid}/messages", json={"text": "hi"})
    assert '"type": "error"' in resp.text
    assert "BoomError" in resp.text

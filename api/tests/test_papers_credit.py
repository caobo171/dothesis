import uuid
import pytest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import CreditTransaction, Paper, User


@pytest.fixture
def buyer():
    Session = get_session_factory()
    with Session() as s:
        u = User(email="creator@e.com", password_hash="x", credit=1000)
        s.add(u)
        s.commit()
        return u


@pytest.fixture
def client_for(buyer):
    app = create_app()
    from app.deps import current_user
    app.dependency_overrides[current_user] = lambda: buyer
    yield TestClient(app)
    app.dependency_overrides.clear()


def _payload(tier: str = "standard", level: str = "master"):
    return {
        "topic": "Cargo cult engineering in cloud-native stacks",
        "research_question": "How does it spread?",
        "academic_level": level,
        "language": "en",
        "citation_style": "apa",
        "model_tier": tier,
    }


def test_create_paper_with_standard_tier_deducts_240_credits(client_for, buyer):
    with patch("app.routers.papers.spawn_job"):
        r = client_for.post("/api/v1/papers", json=_payload(tier="standard", level="master"))
    assert r.status_code == 201, r.text
    Session = get_session_factory()
    with Session() as s:
        u = s.get(User, buyer.id)
        assert u.credit == 760
        tx = list(s.scalars(__import__("sqlalchemy").select(CreditTransaction)))
        assert len(tx) == 1
        assert tx[0].delta == -240
        assert tx[0].reason == "paper_run"
        assert tx[0].ref_type == "paper"
        assert tx[0].ref_id is not None


def test_create_paper_with_premium_tier_deducts_more(client_for, buyer):
    with patch("app.routers.papers.spawn_job"):
        r = client_for.post("/api/v1/papers", json=_payload(tier="premium", level="master"))
    assert r.status_code == 201
    Session = get_session_factory()
    with Session() as s:
        u = s.get(User, buyer.id)
        assert u.credit == 400  # 1000 - 600


def test_create_paper_returns_402_when_insufficient():
    Session = get_session_factory()
    with Session() as s:
        u = User(email="broke@e.com", password_hash="x", credit=10)
        s.add(u)
        s.commit()
        broke_id = u.id

    app = create_app()
    from app.deps import current_user
    with Session() as s:
        u = s.get(User, broke_id)
        app.dependency_overrides[current_user] = lambda: u

        client = TestClient(app)
        with patch("app.routers.papers.spawn_job"):
            r = client.post("/api/v1/papers", json=_payload(tier="premium", level="phd"))
        assert r.status_code == 402
        body = r.json()
        assert body["detail"]["error"]["code"] == "insufficient_credit"
        assert body["detail"]["error"]["required"] == 1200
        assert body["detail"]["error"]["balance"] == 10

    with Session() as s:
        u2 = s.get(User, broke_id)
        assert u2.credit == 10  # untouched
    app.dependency_overrides.clear()


def test_create_paper_rejects_unknown_tier(client_for, buyer):
    with patch("app.routers.papers.spawn_job"):
        r = client_for.post("/api/v1/papers", json=_payload(tier="ultra"))
    assert r.status_code == 422

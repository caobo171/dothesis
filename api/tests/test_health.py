from fastapi.testclient import TestClient

from app.main import create_app


def test_health_returns_ok():
    client = TestClient(create_app())
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json() == {"ok": True}

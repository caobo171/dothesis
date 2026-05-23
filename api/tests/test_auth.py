from fastapi.testclient import TestClient

from app.main import create_app


def _client():
    return TestClient(create_app())


def test_signup_login_me_logout_flow():
    c = _client()

    r = c.post("/api/v1/auth/signup", json={"email": "a@b.com", "password": "supersecret"})
    assert r.status_code == 201, r.text
    assert r.json()["email"] == "a@b.com"
    assert c.cookies.get("opendraft_session")

    r = c.get("/api/v1/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == "a@b.com"

    r = c.post("/api/v1/auth/logout")
    assert r.status_code == 204
    c.cookies.clear()
    assert c.get("/api/v1/auth/me").status_code == 401

    r = c.post("/api/v1/auth/login", json={"email": "a@b.com", "password": "supersecret"})
    assert r.status_code == 200
    assert c.get("/api/v1/auth/me").status_code == 200


def test_signup_duplicate_returns_409():
    c = _client()
    c.post("/api/v1/auth/signup", json={"email": "x@y.com", "password": "supersecret"})
    r = c.post("/api/v1/auth/signup", json={"email": "x@y.com", "password": "supersecret"})
    assert r.status_code == 409


def test_login_wrong_password_returns_401():
    c = _client()
    c.post("/api/v1/auth/signup", json={"email": "a@b.com", "password": "supersecret"})
    r = c.post("/api/v1/auth/login", json={"email": "a@b.com", "password": "nope1234"})
    assert r.status_code == 401

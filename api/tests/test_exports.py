"""Tests for the SP6 M5 export download endpoint."""
import os
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import Export, User
from app.security import create_session


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "true")
    monkeypatch.setenv("AWS_S3_BUCKET", "test-bucket")
    return TestClient(create_app(), follow_redirects=False)


def _setup_user_and_project(client) -> tuple[uuid.UUID, User]:
    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"u{uuid.uuid4().hex[:6]}@x",
                 username=f"u{uuid.uuid4().hex[:6]}",
                 password_hash="x", email_verified=True)
        db.add(u); db.commit(); db.refresh(u)
        token = create_session(db, u)
    client.headers["Authorization"] = f"Bearer {token}"
    pid = client.post("/api/v1/projects", json={"name": "T"}).json()["id"]
    return uuid.UUID(pid), u


def _add_export(project_id: uuid.UUID, filename: str):
    """Record an export where the download route actually looks it up.

    The route's source of truth moved to the exports table; this helper used to
    seed only m5_writing.export_artifacts, the location that comment calls
    deprecated, so every download 404'd. kind and scope are set because the
    route reads both to build the download filename.
    """
    sf = get_session_factory()
    with sf() as db:
        db.add(Export(project_id=project_id, scope="full", kind="docx",
                      s3_key=f"projects/{project_id}/exports/{filename}",
                      filename=filename, size_bytes=0))
        db.commit()


def test_download_redirects_to_signed_url(client, monkeypatch):
    """Happy path — 302 to a fresh signed URL."""
    pid, _ = _setup_user_and_project(client)
    _add_export(pid, "thesis-abc.docx")

    fake_s3 = MagicMock()
    fake_s3.generate_presigned_url.return_value = (
        "https://test-bucket.s3.amazonaws.com/projects/abc/exports/thesis-abc.docx?sig=xyz"
    )
    monkeypatch.setattr("app.routers.exports.s3_from_env", lambda: fake_s3)

    # Download route stays GET but the JWT is no longer accepted via URL/Bearer;
    # mint a short-lived stream token scoped to this exact project/filename.
    fname = "thesis-abc.docx"
    token = client.headers["Authorization"].split(" ", 1)[1]
    st = client.post("/api/v1/auth/stream-token",
                     json={"access_token": token,
                           "scope": f"project-export:{pid}/{fname}"}).json()["stream_token"]
    resp = client.get(f"/api/v1/projects/{pid}/exports/{fname}?st={st}")
    assert resp.status_code == 302
    assert resp.headers["location"].startswith("https://test-bucket.s3.amazonaws.com")
    # Signed URL was generated for the right key
    call_kwargs = fake_s3.generate_presigned_url.call_args.kwargs
    assert call_kwargs["Params"]["Key"] == f"projects/{pid}/exports/thesis-abc.docx"
    assert call_kwargs["ExpiresIn"] == 300


def test_download_404_when_filename_unknown(client, monkeypatch):
    pid, _ = _setup_user_and_project(client)
    _add_export(pid, "thesis-abc.docx")
    monkeypatch.setattr("app.routers.exports.s3_from_env", lambda: MagicMock())
    # Mint a token for the requested filename so auth passes; the 404 then comes
    # from the artifact lookup (no exports row matches this filename's s3_key).
    fname = "wrong-filename.docx"
    token = client.headers["Authorization"].split(" ", 1)[1]
    st = client.post("/api/v1/auth/stream-token",
                     json={"access_token": token,
                           "scope": f"project-export:{pid}/{fname}"}).json()["stream_token"]
    resp = client.get(f"/api/v1/projects/{pid}/exports/{fname}?st={st}")
    assert resp.status_code == 404


def test_download_404_when_user_does_not_own_project(client, monkeypatch):
    pid, _ = _setup_user_and_project(client)
    _add_export(pid, "thesis-abc.docx")
    # Switch to a different user
    sf = get_session_factory()
    with sf() as db:
        u2 = User(email=f"u2{uuid.uuid4().hex[:6]}@x",
                   username=f"u2{uuid.uuid4().hex[:6]}",
                   password_hash="x", email_verified=True)
        db.add(u2); db.commit(); db.refresh(u2)
        token2 = create_session(db, u2)
    client.headers["Authorization"] = f"Bearer {token2}"
    # Mint with the second user's token so stream-token auth passes; the 404
    # then comes from the ownership check (u2 does not own pid).
    fname = "thesis-abc.docx"
    st = client.post("/api/v1/auth/stream-token",
                     json={"access_token": token2,
                           "scope": f"project-export:{pid}/{fname}"}).json()["stream_token"]
    resp = client.get(f"/api/v1/projects/{pid}/exports/{fname}?st={st}")
    assert resp.status_code == 404


def test_download_allowed_for_super_admin(client, monkeypatch):
    """A super admin can download another user's artifact.

    Regression: the chat read path was widened to owner-or-admin
    (auth_admin.readable_project) so an admin can open a student's thread to
    debug a run, but the export routes kept the owner-only check. The result
    was a thread that rendered its DOCX/PDF download card and then 404'd on
    click. Downloading a finished artifact is a read, so it follows the read
    gate. The write asymmetry is unaffected — admins still cannot post.
    """
    pid, _ = _setup_user_and_project(client)
    _add_export(pid, "thesis-abc.docx")
    monkeypatch.setattr("app.routers.exports.s3_from_env", lambda: MagicMock())

    # An email on the super-admin seed allowlist (app/admin_config.py).
    sf = get_session_factory()
    with sf() as db:
        admin = User(email="caotest171@gmail.com",
                     username=f"admin{uuid.uuid4().hex[:6]}",
                     password_hash="x", email_verified=True)
        db.add(admin); db.commit(); db.refresh(admin)
        admin_token = create_session(db, admin)
    client.headers["Authorization"] = f"Bearer {admin_token}"

    fname = "thesis-abc.docx"
    st = client.post("/api/v1/auth/stream-token",
                     json={"access_token": admin_token,
                           "scope": f"project-export:{pid}/{fname}"}).json()["stream_token"]
    resp = client.get(f"/api/v1/projects/{pid}/exports/{fname}?st={st}")
    assert resp.status_code == 302

    # …and the exports panel beside it lists the artifact rather than 404ing.
    listed = client.post(f"/api/v1/projects/{pid}/exports/list",
                         json={"access_token": admin_token})
    assert listed.status_code == 200
    assert [r["filename"] for r in listed.json()] == [fname]

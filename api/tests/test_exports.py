"""Tests for the SP6 M5 export download endpoint."""
import os
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import ContextStore, Project, User
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


def _add_m5_artifact(project_id: uuid.UUID, filename: str):
    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, project_id)
        cs.m5_writing = {
            "export_artifacts": [
                {"kind": "docx",
                 "s3_key": f"projects/{project_id}/exports/{filename}",
                 "download_url": f"/api/v1/projects/{project_id}/exports/{filename}",
                 "size_bytes": 0,
                 "uri": ""},
            ],
        }
        db.commit()


def test_download_redirects_to_signed_url(client, monkeypatch):
    """Happy path — 302 to a fresh signed URL."""
    pid, _ = _setup_user_and_project(client)
    _add_m5_artifact(pid, "thesis-abc.docx")

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
    _add_m5_artifact(pid, "thesis-abc.docx")
    monkeypatch.setattr("app.routers.exports.s3_from_env", lambda: MagicMock())
    # Mint a token for the requested filename so auth passes; the 404 then comes
    # from the artifact lookup (filename not in export_artifacts).
    fname = "wrong-filename.docx"
    token = client.headers["Authorization"].split(" ", 1)[1]
    st = client.post("/api/v1/auth/stream-token",
                     json={"access_token": token,
                           "scope": f"project-export:{pid}/{fname}"}).json()["stream_token"]
    resp = client.get(f"/api/v1/projects/{pid}/exports/{fname}?st={st}")
    assert resp.status_code == 404


def test_download_404_when_user_does_not_own_project(client, monkeypatch):
    pid, _ = _setup_user_and_project(client)
    _add_m5_artifact(pid, "thesis-abc.docx")
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

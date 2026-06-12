"""Tests for /api/v1/projects/{pid}/uploads + /api/v1/uploads/{id}."""
import io
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import PaperUpload, Project, User
from app.security import create_session

FIXTURE = Path(__file__).parent / "fixtures" / "sample.pdf"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "true")
    return TestClient(create_app())


def _login(client) -> uuid.UUID:
    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"u{uuid.uuid4().hex[:6]}@x",
                 username=f"u{uuid.uuid4().hex[:6]}",
                 password_hash="x", email_verified=True)
        db.add(u); db.commit()
        client.headers["Authorization"] = f"Bearer {create_session(db, u)}"
        return u.id


def _project(client) -> uuid.UUID:
    return uuid.UUID(client.post("/api/v1/projects", json={"name": "T"}).json()["id"])


def test_upload_pdf_returns_id_and_extracted_text(client, monkeypatch):
    fake_s3 = MagicMock()
    monkeypatch.setattr("app.routers.uploads.s3_from_env", lambda: fake_s3)

    _login(client)
    pid = _project(client)

    with FIXTURE.open("rb") as f:
        r = client.post(
            f"/api/v1/projects/{pid}/uploads",
            files={"file": ("sample.pdf", f, "application/pdf")},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "upload_id" in body
    assert body["filename"] == "sample.pdf"
    assert body["size_bytes"] > 0
    assert body["page_count"] == 1

    assert fake_s3.put_object.call_count == 2

    sf = get_session_factory()
    with sf() as db:
        row = db.query(PaperUpload).filter_by(project_id=pid).one()
        assert row.text_extracted_at is not None
        assert row.page_count == 1


def test_upload_rejects_oversized_file(client, monkeypatch):
    monkeypatch.setattr("app.routers.uploads.s3_from_env", lambda: MagicMock())
    monkeypatch.setenv("M2_UPLOAD_MAX_BYTES", "100")

    _login(client)
    pid = _project(client)

    payload = b"x" * 200
    r = client.post(
        f"/api/v1/projects/{pid}/uploads",
        files={"file": ("big.pdf", io.BytesIO(payload), "application/pdf")},
    )
    assert r.status_code == 413


def test_upload_rejects_disallowed_mime_type(client, monkeypatch):
    monkeypatch.setattr("app.routers.uploads.s3_from_env", lambda: MagicMock())

    _login(client)
    pid = _project(client)

    r = client.post(
        f"/api/v1/projects/{pid}/uploads",
        files={"file": ("data.bin", io.BytesIO(b"x"), "application/octet-stream")},
    )
    assert r.status_code == 415


def test_list_uploads_returns_project_scoped(client, monkeypatch):
    monkeypatch.setattr("app.routers.uploads.s3_from_env", lambda: MagicMock())
    _login(client)
    pid = _project(client)
    with FIXTURE.open("rb") as f:
        client.post(f"/api/v1/projects/{pid}/uploads",
                    files={"file": ("a.pdf", f, "application/pdf")})

    r = client.get(f"/api/v1/projects/{pid}/uploads")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["filename"] == "a.pdf"


def test_delete_upload_removes_row(client, monkeypatch):
    monkeypatch.setattr("app.routers.uploads.s3_from_env", lambda: MagicMock())
    _login(client)
    pid = _project(client)
    with FIXTURE.open("rb") as f:
        upload_id = client.post(
            f"/api/v1/projects/{pid}/uploads",
            files={"file": ("a.pdf", f, "application/pdf")},
        ).json()["upload_id"]

    r = client.delete(f"/api/v1/uploads/{upload_id}")
    assert r.status_code == 204

    sf = get_session_factory()
    with sf() as db:
        assert db.query(PaperUpload).filter_by(id=uuid.UUID(upload_id)).count() == 0


def test_get_upload_text_returns_extracted_body(client, monkeypatch):
    fake_s3 = MagicMock()
    fake_s3.get_object.return_value = {"Body": io.BytesIO(b"extracted text body")}
    monkeypatch.setattr("app.routers.uploads.s3_from_env", lambda: fake_s3)
    _login(client)
    pid = _project(client)
    with FIXTURE.open("rb") as f:
        upload_id = client.post(
            f"/api/v1/projects/{pid}/uploads",
            files={"file": ("a.pdf", f, "application/pdf")},
        ).json()["upload_id"]

    r = client.get(f"/api/v1/uploads/{upload_id}/text")
    assert r.status_code == 200
    assert "extracted" in r.text


def test_upload_with_no_extractable_text_leaves_text_extracted_at_null(client, monkeypatch):
    monkeypatch.setattr("app.routers.uploads.s3_from_env", lambda: MagicMock())
    monkeypatch.setattr("app.routers.uploads.extract_pdf_text", lambda b: ("", 0))

    _login(client)
    pid = _project(client)
    with FIXTURE.open("rb") as f:
        r = client.post(
            f"/api/v1/projects/{pid}/uploads",
            files={"file": ("a.pdf", f, "application/pdf")},
        )
    assert r.status_code == 200

    sf = get_session_factory()
    with sf() as db:
        row = db.query(PaperUpload).filter_by(project_id=pid).one()
        assert row.text_extracted_at is None
        assert row.text_extract_uri is None

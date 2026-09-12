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


def _login(client, email: str | None = None) -> uuid.UUID:
    # `email` is optional so a test can log in AS a specific identity — the
    # super-admin allowlist is keyed by email (app/admin_config._SEED), so the
    # admin-read tests below can't use the random address.
    sf = get_session_factory()
    with sf() as db:
        u = User(email=email or f"u{uuid.uuid4().hex[:6]}@x",
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

    r = client.post(f"/api/v1/projects/{pid}/uploads/list")
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

    r = client.post(f"/api/v1/uploads/{upload_id}/text")
    assert r.status_code == 200
    assert "extracted" in r.text


def test_raw_upload_supports_unicode_filename(client, monkeypatch):
    """A Vietnamese filename must not crash Starlette's Latin-1 headers."""
    fake_s3 = MagicMock()
    fake_s3.get_object.return_value = {"Body": io.BytesIO(b"docx bytes")}
    monkeypatch.setattr("app.routers.uploads.s3_from_env", lambda: fake_s3)
    _login(client)
    pid = _project(client)
    filename = "BẢNG HỎI.docx"  # decomposed marks reproduce the production crash
    upload_id = client.post(
        f"/api/v1/projects/{pid}/uploads",
        files={"file": (filename, io.BytesIO(b"not-a-real-docx"),
                         "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    ).json()["upload_id"]

    st = _stream_token(client, f"project-upload:{upload_id}")
    r = client.get(f"/api/v1/uploads/{upload_id}/raw?st={st}")

    assert r.status_code == 200, r.text
    assert "filename*=UTF-8''" in r.headers["content-disposition"]
    assert r.content == b"docx bytes"


# --- owner-or-admin reads --------------------------------------------------
# An email on the super-admin seed allowlist (app/admin_config.py).
ADMIN_EMAIL = "caotest171@gmail.com"


def _student_upload(client, monkeypatch) -> str:
    """A student's project with one uploaded PDF. Returns the upload id.

    Leaves `client` authenticated as the student; the admin tests re-login.
    """
    fake_s3 = MagicMock()
    fake_s3.generate_presigned_url.return_value = "https://s3.example/x?sig=y"
    fake_s3.get_object.return_value = {"Body": io.BytesIO(b"extracted text body")}
    monkeypatch.setattr("app.routers.uploads.s3_from_env", lambda: fake_s3)
    _login(client)
    pid = _project(client)
    with FIXTURE.open("rb") as f:
        return client.post(f"/api/v1/projects/{pid}/uploads",
                           files={"file": ("a.pdf", f, "application/pdf")}).json()["upload_id"]


def _stream_token(client, scope: str) -> str:
    token = client.headers["Authorization"].split(" ", 1)[1]
    return client.post("/api/v1/auth/stream-token",
                       json={"access_token": token, "scope": scope}).json()["stream_token"]


def test_download_upload_allowed_for_super_admin(client, monkeypatch):
    """A super admin can download a file from another user's project.

    Regression: uploads/list was widened to owner-or-admin (readable_project)
    so the chat context panel renders for an admin debugging a student's run —
    but this download route kept the owner-only check, so the panel listed the
    file and the download button answered `project not found`. Downloading is a
    read, so it takes the read gate. Writes below stay owner-only.
    """
    upload_id = _student_upload(client, monkeypatch)

    _login(client, email=ADMIN_EMAIL)
    st = _stream_token(client, f"project-upload:{upload_id}")
    r = client.get(f"/api/v1/uploads/{upload_id}/download?st={st}",
                   follow_redirects=False)
    assert r.status_code == 302, r.text


def test_download_upload_presigns_unicode_filename_with_ascii_header(client, monkeypatch):
    fake_s3 = MagicMock()
    fake_s3.generate_presigned_url.return_value = "https://s3.example/signed"
    monkeypatch.setattr("app.routers.uploads.s3_from_env", lambda: fake_s3)
    _login(client)
    pid = _project(client)
    filename = "BẢNG HỎI.docx"
    upload_id = client.post(
        f"/api/v1/projects/{pid}/uploads",
        files={"file": (filename, io.BytesIO(b"not-a-real-docx"),
                         "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    ).json()["upload_id"]

    st = _stream_token(client, f"project-upload:{upload_id}")
    response = client.get(f"/api/v1/uploads/{upload_id}/download?st={st}",
                          follow_redirects=False)
    assert response.status_code == 302
    disposition = fake_s3.generate_presigned_url.call_args.kwargs["Params"][
        "ResponseContentDisposition"]
    assert disposition.isascii()
    assert "filename*=UTF-8''" in disposition


def test_get_upload_text_allowed_for_super_admin(client, monkeypatch):
    """Same gate for the text sibling — the panel's preview must not 404 either."""
    upload_id = _student_upload(client, monkeypatch)

    _login(client, email=ADMIN_EMAIL)
    r = client.post(f"/api/v1/uploads/{upload_id}/text")
    assert r.status_code == 200, r.text
    assert "extracted" in r.text


def test_download_upload_404_for_unrelated_user(client, monkeypatch):
    """The gate widened for admins only — a normal stranger still gets 404."""
    upload_id = _student_upload(client, monkeypatch)

    _login(client)  # random, non-admin email
    st = _stream_token(client, f"project-upload:{upload_id}")
    r = client.get(f"/api/v1/uploads/{upload_id}/download?st={st}",
                   follow_redirects=False)
    assert r.status_code == 404


def test_admin_cannot_delete_someone_elses_upload(client, monkeypatch):
    """The write half of the asymmetry: reading a student's file is allowed,
    destroying it is not."""
    upload_id = _student_upload(client, monkeypatch)

    _login(client, email=ADMIN_EMAIL)
    assert client.delete(f"/api/v1/uploads/{upload_id}").status_code == 404

    sf = get_session_factory()
    with sf() as db:
        assert db.query(PaperUpload).filter_by(id=uuid.UUID(upload_id)).count() == 1


def test_upload_with_no_extractable_text_leaves_text_extracted_at_null(client, monkeypatch):
    monkeypatch.setattr("app.routers.uploads.s3_from_env", lambda: MagicMock())
    # **kw so the stub tolerates the ingest flag (ocr_if_hollow) the router now
    # passes; the case under test is still "extraction yields nothing at all".
    monkeypatch.setattr("app.routers.uploads.extract_pdf_text", lambda b, **kw: ("", 0))

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


def _docx_with_table_between_chapters():
    """chapter 4 heading, its result table, then the chapter 5 heading —
    the shape of a finished quantitative thesis."""
    import io
    from docx import Document
    d = Document()
    d.add_paragraph("CHƯƠNG 4: KẾT QUẢ NGHIÊN CỨU")
    # Long enough on BOTH sides to clear split_final_chapter's 400-char gates —
    # a shorter fixture makes the split decline and the test pass for the wrong
    # reason.
    d.add_paragraph("Kết quả phân tích độ tin cậy được trình bày dưới đây. " * 12)
    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text = "Thang đo"; t.cell(0, 1).text = "Cronbach's Alpha"
    t.cell(1, 0).text = "ATT"; t.cell(1, 1).text = "0.8431"
    d.add_paragraph("CHƯƠNG 5: KẾT LUẬN VÀ KHUYẾN NGHỊ")
    d.add_paragraph("Nghiên cứu đóng góp vào lý thuyết hiện có. " * 12)
    buf = io.BytesIO(); d.save(buf)
    return buf.getvalue()


def test_docx_text_keeps_tables_in_document_order():
    """A result table must stay where it was written, not be moved to the end.

    Extraction used to emit every paragraph and THEN every table, so a thesis's
    result tables all landed in one block after the final chapter. The import's
    chapter split then cut on the last chapter heading and sent every table to
    the M5 side, leaving M4 — the analysis module — with no numbers; when the
    writer regenerated chapter 5, the student's tables were overwritten and
    vanished from the export.
    """
    from app.routers.uploads import _extract_docx_text
    text, _, _ = _extract_docx_text(_docx_with_table_between_chapters())

    assert "0.8431" in text                       # the table survived at all
    # and it sits BETWEEN the two chapter headings, where it was written.
    assert text.index("CHƯƠNG 4") < text.index("0.8431") < text.index("CHƯƠNG 5")


def test_the_chapter_split_leaves_result_tables_with_the_analysis():
    """The property that actually matters to the student: after the import
    splits chapter 5 off, the numbers are still on the analysis side."""
    from app.routers.uploads import _extract_docx_text
    from orchestrator.chapter_split import split_final_chapter

    text, _, _ = _extract_docx_text(_docx_with_table_between_chapters())
    split = split_final_chapter(text)
    assert split is not None
    head, tail = split
    assert "0.8431" in head                       # M4 keeps its results
    assert "0.8431" not in tail


# --- the workspace mirror ---------------------------------------------------
#
# The route that WRITES the student's file into the agent's workspace had its
# own inline copy of the path, so fixing the shared helper did not reach it and
# a fresh upload still landed under the API's cwd. Measured after that fix
# shipped: the file went to api/var/jobs/… while every reader looked in
# var/jobs/…, and the run wrote a thesis with an empty Results chapter.

def test_the_upload_lands_where_the_agent_looks_for_it(client, monkeypatch, tmp_path):
    """Asserted through workspace_dir() on purpose. Spelling the path out here
    would just re-create the duplicate that caused this."""
    from app.workspace import workspace_dir

    monkeypatch.setattr("app.routers.uploads.s3_from_env", lambda: MagicMock())
    monkeypatch.setenv("JOB_WORKDIR_ROOT", str(tmp_path))
    _login(client)
    pid = _project(client)

    with FIXTURE.open("rb") as f:
        r = client.post(f"/api/v1/projects/{pid}/uploads",
                        files={"file": ("sample.pdf", f, "application/pdf")})
    assert r.status_code == 200, r.text

    uploads = workspace_dir(pid) / "uploads"
    assert (uploads / "sample.pdf").exists(), "the raw file the agent parses"
    assert (uploads / "sample.pdf.txt").exists(), "the sidecar the agent reads"


def test_a_relative_workdir_root_still_lands_where_the_agent_looks(client, monkeypatch):
    """The exact production shape: JOB_WORKDIR_ROOT=./var/jobs, with the API
    serving from api/ and the run spawned from the repo root."""
    from app.workspace import workspace_dir

    monkeypatch.setattr("app.routers.uploads.s3_from_env", lambda: MagicMock())
    monkeypatch.setenv("JOB_WORKDIR_ROOT", "./var/jobs")
    monkeypatch.chdir(Path(__file__).resolve().parents[1])   # api/, as the server runs
    _login(client)
    pid = _project(client)

    with FIXTURE.open("rb") as f:
        r = client.post(f"/api/v1/projects/{pid}/uploads",
                        files={"file": ("sample.pdf", f, "application/pdf")})
    assert r.status_code == 200, r.text

    try:
        assert (workspace_dir(pid) / "uploads" / "sample.pdf").exists()
    finally:
        import shutil
        shutil.rmtree(workspace_dir(pid), ignore_errors=True)


def test_nothing_else_builds_the_workspace_path_by_hand():
    """One definition. uploads.py used to spell it out inline — 'the workspace
    path matches chat_v3._workspace_dir', said the comment, and it did until the
    helper changed underneath it."""
    import re
    app_dir = Path(__file__).resolve().parents[1] / "app"
    offenders = [
        p.relative_to(app_dir.parent)
        for p in app_dir.rglob("*.py")
        if p.name != "workspace.py"
        and re.search(r'"agent_projects"|\'agent_projects\'', p.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"call workspace_dir() instead: {offenders}"


# --- survey datasets and results exports ------------------------------------
# The M4 skill tells the student "upload your survey dataset (.sav / .csv /
# .xlsx)" and agent/tools/stats.py already reads all three off the workspace,
# but the gate here used to 415 every one of them.

def _xlsx(rows: int = 3) -> io.BytesIO:
    pd = pytest.importorskip("pandas")
    pytest.importorskip("openpyxl")
    buf = io.BytesIO()
    pd.DataFrame({"EX1": [5] * rows, "EX2": [4] * rows}).to_excel(buf, index=False)
    buf.seek(0)
    return buf


@pytest.mark.parametrize("name,mime", [
    ("survey.csv", "text/csv"),
    ("survey.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ("survey.sav", "application/octet-stream"),
    ("results.htm", "text/html"),
])
def test_upload_accepts_data_and_results_exports(client, monkeypatch, name, mime):
    monkeypatch.setattr("app.routers.uploads.s3_from_env", lambda: MagicMock())
    _login(client)
    pid = _project(client)

    payload = _xlsx() if name.endswith(".xlsx") else io.BytesIO(b"EX1,EX2\n5,4\n")
    r = client.post(f"/api/v1/projects/{pid}/uploads",
                    files={"file": (name, payload, mime)})
    assert r.status_code == 200, r.text


def test_a_dataset_extracts_as_a_profile_not_zip_mojibake(client, monkeypatch):
    """A .xlsx is a ZIP. The old else-branch UTF-8 decoded whatever it was
    handed, so the cached 'extracted text' for a dataset was archive noise —
    which import_route then fed to the model as if it were the student's data."""
    written: dict[str, bytes] = {}
    fake_s3 = MagicMock()
    fake_s3.put_object.side_effect = lambda **kw: written.__setitem__(kw["Key"], kw["Body"])
    monkeypatch.setattr("app.routers.uploads.s3_from_env", lambda: fake_s3)

    _login(client)
    pid = _project(client)
    r = client.post(f"/api/v1/projects/{pid}/uploads",
                    files={"file": ("survey.xlsx", _xlsx(),
                                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200, r.text

    extracted = [v for k, v in written.items() if k.endswith("extracted.txt")]
    assert extracted, "a dataset should still cache something readable"
    text = extracted[0].decode("utf-8")
    assert "3 rows x 2 columns" in text
    assert "EX1" in text
    assert "uploads/survey.xlsx" in text, "the path the stats tools need"


def test_a_dataset_lands_in_the_workspace_for_the_stats_tools(client, monkeypatch, tmp_path):
    from app.workspace import workspace_dir

    monkeypatch.setattr("app.routers.uploads.s3_from_env", lambda: MagicMock())
    monkeypatch.setenv("JOB_WORKDIR_ROOT", str(tmp_path))
    _login(client)
    pid = _project(client)

    r = client.post(f"/api/v1/projects/{pid}/uploads",
                    files={"file": ("survey.xlsx", _xlsx(),
                                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200, r.text
    assert (workspace_dir(pid) / "uploads" / "survey.xlsx").exists()


def test_upload_still_rejects_a_type_nothing_can_read(client, monkeypatch):
    """Widening the allowlist must not turn it into 'anything goes'."""
    monkeypatch.setattr("app.routers.uploads.s3_from_env", lambda: MagicMock())
    _login(client)
    pid = _project(client)

    r = client.post(f"/api/v1/projects/{pid}/uploads",
                    files={"file": ("thesis.zip", io.BytesIO(b"PK\x03\x04"),
                                    "application/zip")})
    assert r.status_code == 415


# --- re-uploading the same file must not re-pay for reading it --------------

_DOCX_M = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture
def dedupe_env(client, monkeypatch, tmp_path):
    """S3 + workspace stubbed, and a counted docx extraction."""
    fake_s3 = MagicMock()
    monkeypatch.setattr("app.routers.uploads.s3_from_env", lambda: fake_s3)
    monkeypatch.setattr("app.routers.uploads.workspace_dir", lambda _pid: tmp_path)
    calls: list[int] = []

    def fake_extract(body, *, stem=""):
        calls.append(len(body))
        return (f"EXTRACTED {len(calls)}", 0, [])

    monkeypatch.setattr("app.routers.uploads._extract_docx_text", fake_extract)
    _login(client)
    return calls, _project(client)


def _post_docx(client, pid, data: bytes, name="Result.docx"):
    return client.post(f"/api/v1/projects/{pid}/uploads",
                       files={"file": (name, io.BytesIO(data), _DOCX_M)})


def test_re_uploading_identical_bytes_reuses_the_extraction(client, dedupe_env):
    """Five byte-identical copies of one results .docx were uploaded to a real
    project in a single morning, each paying a vision call per screenshot.

    The file is unchanged, so the reading of it is too. A second upload still
    gets its own row and id — students re-upload to mean "use this one" — it
    just doesn't buy the same transcription twice.
    """
    calls, pid = dedupe_env
    data = b"PK\x03\x04 pretend this is a results docx"

    first = _post_docx(client, pid, data)
    second = _post_docx(client, pid, data)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert len(calls) == 1, f"identical upload was extracted {len(calls)} times"
    assert first.json()["upload_id"] != second.json()["upload_id"]

    sf = get_session_factory()
    with sf() as db:
        rows = db.query(PaperUpload).filter_by(project_id=pid).all()
        assert len(rows) == 2
        assert all(r.text_extract_uri for r in rows), "reused row lost its text"


def test_different_bytes_under_the_same_filename_are_extracted_again(client, dedupe_env):
    """The dedupe key is CONTENT, not the name. A student who fixes their
    analysis and re-exports `Result.docx` must get the new numbers read."""
    calls, pid = dedupe_env

    _post_docx(client, pid, b"PK\x03\x04 version one")
    _post_docx(client, pid, b"PK\x03\x04 version two, with corrected EFA")

    assert len(calls) == 2


def test_an_extraction_from_before_the_epoch_is_never_reused(client, dedupe_env, monkeypatch):
    """A cached extraction is only as trustworthy as the model that produced it.

    gemini-2.5-flash mis-assigned every outer loading on a real SmartPLS path
    diagram; those wrong numbers are still cached against real projects. Re-
    uploading the file is how a student fixes that, so content-dedupe must not
    hand the stale transcription straight back. The epoch is bumped whenever
    the vision model or prompt changes.
    """
    from datetime import datetime, timedelta, timezone
    calls, pid = dedupe_env
    data = b"PK\x03\x04 a results docx read by the old model"

    _post_docx(client, pid, data)
    assert len(calls) == 1

    # Backdate the first extraction to before the epoch, as a real pre-upgrade
    # row would be.
    sf = get_session_factory()
    with sf() as db:
        row = db.query(PaperUpload).filter_by(project_id=pid).one()
        row.text_extracted_at = (
            __import__("app.routers.uploads", fromlist=["x"])._EXTRACTION_EPOCH
            - timedelta(days=1))
        db.commit()

    _post_docx(client, pid, data)

    assert len(calls) == 2, "a pre-epoch extraction was reused"


# --- the screenshots behind the numbers -------------------------------------

def _docx_with_one_image() -> bytes:
    """A results .docx whose table is a pasted screenshot — the ordinary case."""
    import io

    from docx import Document
    from agent.tests.test_docx_extract import _png

    d = Document()
    d.add_paragraph("ĐỘ TIN CẬY")
    d.add_paragraph().add_run().add_picture(io.BytesIO(_png(300, 200, noisy=True)))
    buf = io.BytesIO(); d.save(buf)
    return buf.getvalue()


def test_docx_extraction_returns_images_for_the_workspace(monkeypatch):
    """The sidecar names the file each [Hình n] came from, so the agent can
    point a results block at the original screenshot instead of describing it."""
    import agent.multimodal as mm
    monkeypatch.setattr(mm, "_transcribe_via_vision",
                        lambda att, prompt=None: "| A |\n|---|\n| 1 |")
    from app.routers.uploads import _extract_docx_text

    text, _pages, images = _extract_docx_text(_docx_with_one_image(), stem="_Result.docx")

    assert len(images) == 1
    assert images[0]["figure"] == 1
    assert images[0]["relpath"] == "uploads/_Result.docx.img/hinh-01.png"
    assert "[Hình 1] (ảnh gốc: uploads/_Result.docx.img/hinh-01.png)" in text


def test_image_extraction_transcribes_pasted_screenshot(monkeypatch):
    import agent.multimodal as mm
    monkeypatch.setattr(mm, "_transcribe_via_vision",
                        lambda att, prompt=None: "β = 0.42, p < 0.05")
    from app.routers.uploads import _extract_image_text

    png = b"\x89PNG\r\n\x1a\n" + b"x" * 32
    text, pages, images = _extract_image_text(png, "image/png", "pasted-screenshot-1.png")

    assert pages == 1
    assert len(images) == 1
    assert images[0]["figure"] == 1
    assert "β = 0.42" in text
    assert "uploads/pasted-screenshot-1.png.img/hinh-01.png" in text


def test_docx_extraction_without_images_still_returns_a_triple():
    from app.routers.uploads import _extract_docx_text
    text, _pages, images = _extract_docx_text(_docx_with_table_between_chapters())
    assert images == []
    assert "0.8431" in text

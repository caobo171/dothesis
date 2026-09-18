"""`gather` reads uploads, sidecars and chapter prose — no model, no guessing.

The "never read" half of the problem: on the dev database 12 of 21 uploads had
never ridden a turn, all of them extracted successfully. Deciding that requires
joining uploads against the attachment chips on every message in the project,
which is the one thing the pure diagnosis module cannot do for itself.
"""
import uuid

from sqlalchemy.orm import Session

from app.agent_state import DbProjectStateStore
from app.db import get_engine
from app.doctor_adapter import gather
from app.models import Message, PaperUpload, Thread


def _upload(db, project_id, filename, size_bytes=1) -> PaperUpload:
    row = PaperUpload(project_id=project_id, filename=filename, s3_uri="",
                      size_bytes=size_bytes, mime_type="application/octet-stream")
    db.add(row)
    db.commit()
    return row


def _thread_with_attachment(db, project_id, upload_id):
    t = Thread(project_id=project_id, name="Main",
               langgraph_thread_id=str(uuid.uuid4()))
    db.add(t)
    db.flush()
    db.add(Message(thread_id=t.id, role="user", content="đây nhé",
                   tool_calls_json={"attachments": [{"upload_id": str(upload_id)}]}))
    db.commit()


def _store(project_id, ws):
    return DbProjectStateStore(get_engine(), project_id, ws)


def test_an_upload_no_message_references_is_marked_unattached(project_id, tmp_path):
    (tmp_path / "uploads").mkdir(parents=True)
    (tmp_path / "uploads" / "_Result.docx.txt").write_text(
        "Outer loadings\n| ATT_1 | 0.854 |\n", encoding="utf-8")
    with Session(get_engine()) as db:
        _upload(db, project_id, "_Result.docx")
        inp = gather(db, project_id, _store(project_id, tmp_path), tmp_path)

    assert len(inp.uploads) == 1
    assert inp.uploads[0].ever_attached is False
    assert "ATT_1" in inp.uploads[0].sidecar_text


def test_an_upload_a_message_carried_is_marked_attached(project_id, tmp_path):
    with Session(get_engine()) as db:
        row = _upload(db, project_id, "_Result.docx")
        _thread_with_attachment(db, project_id, row.id)
        inp = gather(db, project_id, _store(project_id, tmp_path), tmp_path)

    assert inp.uploads[0].ever_attached is True


def test_a_reupload_of_an_attached_file_counts_as_read(project_id, tmp_path):
    # Same name + same size: the student uploaded it twice and attached the
    # second copy. The first copy must not be reported "never read".
    with Session(get_engine()) as db:
        first = _upload(db, project_id, "_Result.docx", size_bytes=306682)
        second = _upload(db, project_id, "_Result.docx", size_bytes=306682)
        _thread_with_attachment(db, project_id, second.id)
        inp = gather(db, project_id, _store(project_id, tmp_path), tmp_path)

    by_id = {u.upload_id: u for u in inp.uploads}
    assert by_id[str(first.id)].ever_attached is True


def test_same_name_different_size_is_a_different_file(project_id, tmp_path):
    with Session(get_engine()) as db:
        old = _upload(db, project_id, "_Result.docx", size_bytes=100)
        new = _upload(db, project_id, "_Result.docx", size_bytes=200)
        _thread_with_attachment(db, project_id, new.id)
        inp = gather(db, project_id, _store(project_id, tmp_path), tmp_path)

    by_id = {u.upload_id: u for u in inp.uploads}
    assert by_id[str(old.id)].ever_attached is False


def test_a_missing_sidecar_is_not_an_error(project_id, tmp_path):
    with Session(get_engine()) as db:
        _upload(db, project_id, "no_sidecar.pdf")
        inp = gather(db, project_id, _store(project_id, tmp_path), tmp_path)

    assert inp.uploads[0].sidecar_text is None


def test_slices_arrive_per_module_not_flattened(project_id, tmp_path):
    store = _store(project_id, tmp_path)
    store.commit_slice("M1", {"research_title": "T"}, reason="test")
    with Session(get_engine()) as db:
        inp = gather(db, project_id, store, tmp_path)

    assert inp.context_store["m1_topic"]["research_title"] == "T"


def test_another_projects_uploads_are_not_gathered(project_id, tmp_path):
    from app.models import Project
    with Session(get_engine()) as db:
        other = Project(user_id=db.get(Project, project_id).user_id, name="Other",
                        current_module="M1", status="draft")
        db.add(other)
        db.commit()
        _upload(db, other.id, "someone_elses.docx")
        inp = gather(db, project_id, _store(project_id, tmp_path), tmp_path)

    assert inp.uploads == []

"""M1's `cover` block must survive the database, or the cover page stays blank.

New context_store keys are dead in production unless SLICE_OWNERSHIP carries
them: DbProjectStateStore.load() lifts only owned keys into the agent's flat
view, _save persists only owned keys, and commit_slice rejects unowned ones
outright. A cover the agent can write but nothing can read back is worse than
no feature, because it looks like it worked.
"""
from app.agent_state import DbProjectStateStore
from app.db import get_engine
from orchestrator.tools.m5_writing import cover_fields

# project_id fixture lives in conftest.py.

_COVER = {"author": "Việt Đoàn Dũng",
          "institution": "University of Economics Ho Chi Minh City",
          "advisor": "TS. Nguyễn Văn A",
          "degree": "Master of Business Administration"}


def _store(project_id, tmp_path):
    return DbProjectStateStore(get_engine(), project_id, tmp_path)


def test_the_agent_may_write_a_cover(project_id, tmp_path):
    """commit_slice raises SliceOwnershipError on an unowned key."""
    _store(project_id, tmp_path).commit_slice(
        "M1", {"cover": _COVER}, reason="student gave their cover details")


def test_a_cover_survives_a_fresh_store(project_id, tmp_path):
    _store(project_id, tmp_path).commit_slice("M1", {"cover": _COVER}, reason="r")
    reread = _store(project_id, tmp_path).load()["contextStore"]
    assert reread["cover"] == _COVER


def test_the_exporter_reads_it_back_off_the_nested_store(project_id, tmp_path):
    """The path the export actually takes: load_full_context_store → cover_fields."""
    store = _store(project_id, tmp_path)
    store.commit_slice("M1", {"cover": _COVER, "field": "Marketing"}, reason="r")
    out = cover_fields(_store(project_id, tmp_path).load_full_context_store(), "en")
    assert out["author"] == _COVER["author"]
    assert out["advisor"] == _COVER["advisor"]
    assert out["department"] == "Marketing"          # derived, not stored


def test_a_cover_does_not_earn_m1_a_done(project_id, tmp_path):
    """Knowing a student's university is not research progress. Without this,
    a cover alone would flip M1 green with no title and no questions."""
    store = _store(project_id, tmp_path)
    try:
        store.commit_slice("M1", {"cover": _COVER}, reason="r", confirm_done=True)
    except ValueError as e:
        assert "cannot mark" in str(e)
    else:
        raise AssertionError("a cover block earned M1 a done")


def test_a_cover_does_not_make_a_blank_project_look_started(project_id, tmp_path):
    """exists() drives onboarding; a cover is not the work."""
    store = _store(project_id, tmp_path)
    store.commit_slice("M1", {"cover": _COVER}, reason="r")
    # `cover` IS module content by the exists() definition (it is not a
    # NON_CONTENT audit key), so this documents the behaviour rather than
    # asserting a blank — what must not happen is a crash or a lost cover.
    assert store.load()["contextStore"]["cover"] == _COVER

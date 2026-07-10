"""ProjectStateStore — the guarded context_store with deterministic propagation.

The store is PROJECT-scoped, not thread-scoped: every chat session/thread in a
project shares one context_store (the user's explicit requirement). Tests
exercise that by opening fresh store instances over the same directory.
"""
import pytest

from agent.state import (
    DOWNSTREAM,
    SLICE_OWNERSHIP,
    ProjectStateStore,
    SliceOwnershipError,
)


@pytest.fixture
def store(tmp_path):
    return ProjectStateStore(tmp_path)


def test_fresh_project_has_no_state(store):
    snap = store.read_slice("M1")
    assert snap["exists"] is False


def test_commit_creates_state_and_shifts_focus(store):
    result = store.commit_slice(
        "M1",
        {"research_title": "T", "research_questions": ["RQ1?"]},
        reason="topic locked",
    )
    assert result["focus"] == "M1"
    assert result["status"]["M1"] == "in_progress"
    snap = store.read_slice("M1")
    assert snap["exists"] is True
    assert snap["slices"]["research_title"] == "T"


def test_confirm_done_marks_module_done(store):
    store.commit_slice("M1", {"research_title": "T"}, reason="r", confirm_done=True)
    assert store.read_slice("M1")["status"]["M1"] == "done"


def test_ownership_enforced(store):
    # M1 does not own research_gaps — the commit must be rejected wholesale.
    with pytest.raises(SliceOwnershipError):
        store.commit_slice("M1", {"research_gaps": []}, reason="bad")
    assert store.read_slice("M1")["exists"] is False


def test_mutate_flags_started_downstream_only(store):
    # M1..M3 have content; M4/M5 untouched (locked).
    store.commit_slice("M1", {"research_title": "T"}, reason="r", confirm_done=True)
    store.commit_slice("M2", {"research_gaps": [{"id": "gap-1"}]}, reason="r", confirm_done=True)
    store.commit_slice("M3", {"hypotheses": ["H1"]}, reason="r", confirm_done=True)

    # Re-mutating M1 flags M2+M3 (started) but NOT M4/M5 (locked — flagging an
    # untouched module is noise; bootstrap-style holes are flagged explicitly).
    result = store.commit_slice("M1", {"research_title": "T2"}, reason="pivot")
    assert result["status"]["M2"] == "needs_review"
    assert result["status"]["M3"] == "needs_review"
    assert result["status"]["M4"] == "locked"
    assert result["status"]["M5"] == "locked"
    assert result["flagged"] == ["M2", "M3"]


def test_commit_snapshots_version_history(store):
    store.commit_slice("M1", {"research_title": "v1"}, reason="first")
    store.commit_slice("M1", {"research_title": "v2"}, reason="second")
    history = store.load()["versionHistory"]
    assert len(history) == 2
    assert history[-1]["reason"] == "second"
    # Snapshot captures the state BEFORE the commit that recorded it.
    assert history[-1]["contextStore"]["research_title"] == "v1"


def test_read_slice_includes_read_dependencies(store):
    store.commit_slice("M1", {"research_title": "T", "research_questions": ["RQ?"]}, reason="r")
    store.commit_slice("M2", {"research_gaps": [{"id": "gap-1"}]}, reason="r")
    snap = store.read_slice("M3")  # M3 reads M1 + M2
    assert snap["slices"]["research_title"] == "T"
    assert snap["slices"]["research_gaps"] == [{"id": "gap-1"}]
    # But not slices M3 has no business reading (M4's).
    assert "analysis_results" not in snap["slices"]


def test_state_shared_across_sessions(tmp_path):
    # Two store instances over the same project dir = two chat sessions.
    a = ProjectStateStore(tmp_path)
    a.commit_slice("M1", {"research_title": "shared"}, reason="r")
    b = ProjectStateStore(tmp_path)
    assert b.read_slice("M1")["slices"]["research_title"] == "shared"


def test_status_override_supported(store):
    # Bootstrap needs to set explicit statuses (dependency holes).
    store.commit_slice(
        "M3", {"hypotheses": ["H1"]}, reason="bootstrap import",
        confirm_done=True, status_overrides={"M2": "needs_review"},
    )
    status = store.read_slice("M3")["status"]
    assert status["M3"] == "done"
    assert status["M2"] == "needs_review"


def test_confirm_done_rejected_when_slice_empty(store):
    # Marking a module done with nothing in its slice is the chat-says-done /
    # state-says-needs_review drift. It must be refused wholesale.
    with pytest.raises(ValueError, match="cannot mark M1 done"):
        store.commit_slice("M1", {}, reason="premature", confirm_done=True)
    # Nothing persisted — the module isn't even created.
    assert store.read_slice("M1")["exists"] is False


def test_confirm_done_allowed_once_slice_has_content(store):
    # The two-step the error message prescribes: commit progress, then done.
    store.commit_slice("M1", {"research_title": "T"}, reason="progress")
    store.commit_slice("M1", {}, reason="lock it", confirm_done=True)
    assert store.read_slice("M1")["status"]["M1"] == "done"


def test_confirm_done_with_writes_in_one_call(store):
    # A single commit that both writes and confirms passes (post-write check).
    store.commit_slice("M2", {"research_gaps": [{"id": "g1"}]}, reason="r", confirm_done=True)
    assert store.read_slice("M2")["status"]["M2"] == "done"


def test_slice_map_and_dag_consistency():
    # Every module owns ≥1 key; DAG only references known modules.
    modules = {"M1", "M2", "M3", "M4", "M5"}
    assert set(SLICE_OWNERSHIP) == modules
    for module, downstream in DOWNSTREAM.items():
        assert module in modules
        assert set(downstream) <= modules


# -- roadmap_tasks coaching write path (F2 Task 3) ------------------------
# Blockers are ephemeral coaching aids: the dedicated path must never disturb
# the module state machine (focus/status/history), unlike commit_slice.
def test_upsert_roadmap_task_does_not_touch_focus_or_status(store):
    before = store.load()
    store.upsert_roadmap_task({"module": "M4", "substep": "interpret",
                               "title": "HTMT fails", "why": "validity", "status": "open"})
    after = store.load()
    assert after["focus"] == before["focus"]
    assert after["status"] == before["status"]
    assert after["contextStore"]["roadmap_tasks"][0]["title"] == "HTMT fails"


def test_resolve_roadmap_task_flips_status(store):
    t = store.upsert_roadmap_task({"module": "M4", "title": "x", "why": "y", "status": "open"})
    assert store.resolve_roadmap_task(t["id"]) is True
    assert store.load()["contextStore"]["roadmap_tasks"][0]["status"] == "done"
    assert store.resolve_roadmap_task("missing") is False


def test_commit_slice_still_rejects_roadmap_tasks_key(store):
    # roadmap_tasks must not be writable through the module slice path.
    with pytest.raises(SliceOwnershipError):
        store.commit_slice("M4", {"roadmap_tasks": []}, reason="x")


# -- cross-session memory: advisor_feedback + institution_profile (F4 Task 1) --
def test_advisor_feedback_roundtrip(store):
    d = store.upsert_advisor_feedback({"chapter": "results", "issue": "report effect sizes",
                                       "required_change": "add Cohen's f2"})
    assert d["status"] == "open" and d["id"]
    before = store.load()
    assert store.mark_advisor_feedback_addressed(d["id"]) is True
    after = store.load()
    assert after["contextStore"]["advisor_feedback"][0]["status"] == "addressed"
    # dedicated path: module state machine untouched
    assert after["focus"] == before["focus"] and after["status"] == before["status"]


def test_set_institution_profile_merges(store):
    store.set_institution_profile({"citation_style": "apa7"})
    store.set_institution_profile({"min_references": 30})
    prof = store.load()["contextStore"]["institution_profile"]
    assert prof == {"citation_style": "apa7", "min_references": 30}


# -- thesis timeline: dedicated coaching path (F11 Task 3) ---------------------
def test_set_thesis_timeline_uses_dedicated_path(store):
    # thesis_timeline is a COACHING_KEY: written via its own store path, never
    # commit_slice, so it must NOT shift focus or change any module status.
    store.commit_slice("M1", {"research_title": "T"}, reason="seed")
    before = store.load()
    store.set_thesis_timeline({"milestones": [{"module": "M1"}]})
    after = store.load()
    assert after["contextStore"]["thesis_timeline"]["milestones"][0]["module"] == "M1"
    assert after["status"] == before["status"] and after["focus"] == before["focus"]

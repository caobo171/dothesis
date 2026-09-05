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


def test_mutate_marks_done_downstream_stale_without_touching_status(store):
    # M1..M3 have content; M4/M5 untouched (locked).
    store.commit_slice("M1", {"research_title": "T"}, reason="r", confirm_done=True)
    store.commit_slice("M2", {"research_gaps": [{"id": "gap-1"}]}, reason="r", confirm_done=True)
    store.commit_slice("M3", {"hypotheses": ["H1"]}, reason="r", confirm_done=True)

    # Re-mutating M1 marks M2+M3 stale. They STAY done — this used to write
    # needs_review into status, which demoted them and made the roadmap route
    # the student back before anything could move forward.
    result = store.commit_slice("M1", {"research_title": "T2"}, reason="pivot")
    assert result["status"]["M2"] == "done"
    assert result["status"]["M3"] == "done"
    assert result["status"]["M4"] == "locked"
    assert result["status"]["M5"] == "locked"
    assert result["flagged"] == ["M2", "M3"]
    assert result["stale"] == ["M2", "M3"]


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


def test_confirm_done_rejected_when_slice_holds_only_non_earning_keys(store):
    # `language` (and `user_context`) are OWNED by M1 and persisted, but they are
    # caller-supplied inputs, not module output — partner seeding sets a language
    # on every project at creation. If they counted, every seeded project would
    # be M1-done-eligible on a 2-letter locale code, which is exactly the
    # narrated-done the gate exists to refuse.
    with pytest.raises(ValueError, match="cannot mark M1 done"):
        store.commit_slice("M1", {"language": "vi", "user_context": "make it good"},
                           reason="seed", confirm_done=True)


def test_done_gate_message_lists_only_earnable_keys(store):
    # The message tells the agent HOW to earn the done, so it must not advertise
    # keys that cannot satisfy the gate — that routes it down a dead end.
    with pytest.raises(ValueError) as exc:
        store.commit_slice("M1", {}, reason="premature", confirm_done=True)
    assert "language" not in str(exc.value)
    assert "user_context" not in str(exc.value)
    assert "decisions" not in str(exc.value)
    assert "research_title" in str(exc.value)


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


def test_one_obstacle_stays_one_task(store):
    """Measured on a real run: M4 could not find the student's dataset, said so,
    retried, and said it again — seven open tasks for one obstacle, each worded
    differently, none of which the student could ever finish clearing. Only the
    first is ever surfaced (roadmap.next_action returns the first open task), so
    the other six were invisible noise sitting in durable state."""
    for title in ("Thiếu dữ liệu khảo sát để chạy phân tích",
                  "Chưa có tệp dữ liệu phân tích",
                  "Thiếu dữ liệu đầu vào để phân tích"):
        store.upsert_roadmap_task({"module": "M4", "substep": "run_per_step",
                                   "title": title, "why": "no dataset",
                                   "status": "open"})

    tasks = store.load()["contextStore"]["roadmap_tasks"]
    assert len(tasks) == 1
    # The newest wording wins: it is the agent's latest read of the obstacle.
    assert tasks[0]["title"] == "Thiếu dữ liệu đầu vào để phân tích"


def test_the_task_id_survives_being_restated(store):
    """Whatever is holding the id — a resolve call, a UI row — must still work
    after the agent restates the same blocker."""
    first = store.upsert_roadmap_task({"module": "M4", "substep": "run_per_step",
                                       "title": "no data", "status": "open"})
    again = store.upsert_roadmap_task({"module": "M4", "substep": "run_per_step",
                                       "title": "still no data", "status": "open"})
    assert again["id"] == first["id"]
    assert store.resolve_roadmap_task(first["id"]) is True


def test_a_new_blocker_after_a_resolve_is_a_new_task(store):
    """Collapsing onto the open one must not resurrect a cleared task."""
    first = store.upsert_roadmap_task({"module": "M4", "substep": "run_per_step",
                                       "title": "no data", "status": "open"})
    store.resolve_roadmap_task(first["id"])
    second = store.upsert_roadmap_task({"module": "M4", "substep": "run_per_step",
                                        "title": "HTMT fails", "status": "open"})

    tasks = store.load()["contextStore"]["roadmap_tasks"]
    assert second["id"] != first["id"]
    assert len(tasks) == 2
    assert [t["status"] for t in tasks] == ["done", "open"]


def test_advisor_directives_are_not_collapsed_into_each_other(store):
    """Every one of a supervisor's comments is its own piece of work, and they
    all land on (module, substep="") — so the dedupe key cannot be that pair
    alone or four comments on chapter 4 would become one."""
    for i in (1, 2, 3):
        store.upsert_roadmap_task({"module": "M4", "substep": "",
                                   "title": f"Advisor: comment {i}",
                                   "status": "open", "feedback_id": f"fb{i}"})
    assert len(store.load()["contextStore"]["roadmap_tasks"]) == 3


def test_re_ingesting_the_same_advisor_comment_updates_its_task(store):
    a = store.upsert_roadmap_task({"module": "M4", "substep": "", "title": "Advisor: fix Table 4.2",
                                   "status": "open", "feedback_id": "fb1"})
    b = store.upsert_roadmap_task({"module": "M4", "substep": "", "title": "Advisor: fix Table 4.2 caption",
                                   "status": "open", "feedback_id": "fb1"})
    tasks = store.load()["contextStore"]["roadmap_tasks"]
    assert len(tasks) == 1 and b["id"] == a["id"]
    assert tasks[0]["title"] == "Advisor: fix Table 4.2 caption"


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


# -- reconstructed upstream modules -------------------------------------------
# Backfill used to sit behind a per-module Confirm card. It saves itself now, so
# these pin what "saving itself" is allowed to do to the student's position.

def test_commit_reconstructed_counts_as_done(store):
    store.commit_slice("M4", {"analysis_results": "PLS-SEM A->B"}, reason="import")
    res = store.commit_reconstructed("M1", {"research_title": "T",
                                            "research_questions": ["RQ1?"]})
    state = store.load()
    assert res["status"] == "done" and state["status"]["M1"] == "done"
    # The already-started M4 keeps its status — filling in a step BELOW it did
    # not invalidate it.
    assert state["status"]["M4"] == "in_progress"


def test_commit_reconstructed_strips_meta_and_audit_keys(store):
    store.commit_reconstructed("M1", {
        "research_title": "T",
        "_source": "client-junk", "confirmed_at": "2020-01-01",
        "decisions": [{"choice": "FORGED"}],
    })
    cs = store.load()["contextStore"]
    assert cs["research_title"] == "T"
    assert "decisions" not in cs and "_source" not in cs


def test_commit_reconstructed_falls_back_to_in_progress_when_thin(store):
    # Nothing the module OWNS → can't earn a done. Keep what there is rather
    # than losing the backfill entirely.
    res = store.commit_reconstructed("M3", {"paradigm": "quantitative"})
    assert res["status"] == "in_progress"
    assert store.load()["status"]["M3"] == "in_progress"


def test_commit_reconstructed_advances_focus_past_finished_steps(store):
    # The mid-journey import case: M4 imported, student sitting at M1, M1-M3
    # reconstructed → they should land on M4, not be walked back through M1.
    store.commit_slice("M4", {"analysis_results": "r"}, reason="import")
    store.commit_slice("M1", {}, reason="park", status_overrides={"M1": "locked"})
    for module, slice_ in (("M1", {"research_title": "T"}),
                           ("M2", {"research_gaps": [{"description": "g"}]}),
                           ("M3", {"conceptual_model": {"c": ["A"]}})):
        store.commit_reconstructed(module, slice_)
    assert store.load()["focus"] == "M4"


def test_commit_reconstructed_never_walks_focus_backwards(store):
    # Only M3 backfilled while M1 is still empty: "first module not done" is M1,
    # but the student is at M4 and must stay there.
    store.commit_slice("M4", {"analysis_results": "r"}, reason="import")
    store.commit_reconstructed("M3", {"conceptual_model": {"c": ["A"]}})
    assert store.load()["focus"] == "M4"


def test_a_module_whose_dod_is_satisfied_reads_done_without_an_explicit_confirm(store):
    """Status was set from the confirm_done FLAG alone, never from the evidence.

    So an imported thesis — whose M4 demonstrably satisfies dod_analysis — was
    written as in_progress on every commit, and stayed there. compute_status_map
    said done, the stored status said in_progress, and the UI reads the stored
    one. Two notions of "done" that disagreed, with the student shown the wrong
    one and asked to redo finished work.
    """
    written_up = ("CHƯƠNG 4: KẾT QUẢ NGHIÊN CỨU\n"
                  + ("Kết quả phân tích cho thấy mô hình phù hợp. " * 60))
    result = store.commit_slice("M4", {"analysis_results": written_up}, reason="import")
    assert result["status"]["M4"] == "done"


def test_a_module_that_does_not_meet_its_dod_stays_in_progress(store):
    """The DoD decides — it must not turn every commit into a finished module."""
    result = store.commit_slice("M4", {"analysis_results": "TODO: run it"},
                                reason="wip")
    assert result["status"]["M4"] == "in_progress"


def test_an_explicit_confirm_still_wins(store):
    """confirm_done is the student's own sign-off and must keep working even
    where no module-level DoD can speak."""
    store.commit_slice("M1", {"research_title": "T"}, reason="r", confirm_done=True)
    assert store.read_slice("M1")["status"]["M1"] == "done"


def test_setting_the_output_language_invalidates_nothing(store):
    """"Viết bài này bằng tiếng Anh" must not mark the whole thesis for review.

    `language` is owned by M1, so the agent persisted it with commit_slice —
    and that flagged M2/M3/M4/M5 as needs_review. A student whose thesis had
    just been reconstructed end-to-end was told all four modules needed
    re-reviewing because they picked the language the DRAFT comes out in.
    Nothing about their literature, design or analysis changed.
    """
    store.commit_slice("M1", {"research_title": "T"}, reason="r", confirm_done=True)
    store.commit_slice("M2", {"research_gaps": [{"id": "gap-1"}]}, reason="r", confirm_done=True)
    store.commit_slice("M3", {"hypotheses": ["H1"]}, reason="r", confirm_done=True)

    result = store.commit_slice("M1", {"language": "en"}, reason="write it in English")
    assert result["status"]["M2"] == "done"          # untouched, not flagged
    assert result["status"]["M3"] == "done"
    assert result["flagged"] == []
    # And it actually landed, so M5 renders in English.
    assert store.load()["contextStore"]["language"] == "en"


def test_a_real_m1_edit_still_flags_downstream(store):
    """The preference carve-out must not disarm the mechanism it sits in.

    Changing the research title genuinely does invalidate the work built on
    it — that propagation is the point, and a mixed write (title + language)
    is a real edit that happens to also set a preference.
    """
    store.commit_slice("M1", {"research_title": "T"}, reason="r", confirm_done=True)
    store.commit_slice("M2", {"research_gaps": [{"id": "gap-1"}]}, reason="r", confirm_done=True)

    result = store.commit_slice("M1", {"research_title": "T2", "language": "en"},
                                reason="pivot + language")
    assert result["flagged"] == ["M2"]
    assert result["stale"] == ["M2"]


def test_a_done_module_does_not_flap_back_on_a_later_write(store):
    """An approved module must not be demoted by re-grading it.

    Reading the evidence fixed "finished but reads in_progress"; it introduced
    the mirror image, because ANY later write to a done module re-ran its DoD.
    The real case: the import moves chapter 5 out of M4, and that re-commit
    re-graded the now-trimmed M4 and sent a module the student had signed off
    back to in_progress — with nothing about their work having changed.

    compute_status_map has always held confirmed_at authoritative on top of the
    DoD for exactly this reason. The two disagreed, and the UI reads this one.
    """
    store.commit_slice("M4", {"analysis_results": "x" * 4000},
                       reason="import", confirm_done=True)
    assert store.load()["status"]["M4"] == "done"

    # Trim it below whatever the DoD wants — the chapter-split re-commit.
    result = store.commit_slice("M4", {"analysis_results": "y" * 200},
                                reason="final chapter moved to M5")
    assert result["status"]["M4"] == "done"          # still theirs, still done


def test_invalidation_still_arrives_on_the_stale_channel(store):
    """The carve-out must not swallow real invalidation — that has its own
    channel, and it must still fire on a done module.

    What changed is where it lands: `stale`, not `status`. The signal survives;
    the gate it used to impose does not.
    """
    store.commit_slice("M1", {"research_title": "T"}, reason="r", confirm_done=True)
    store.commit_slice("M2", {"research_gaps": [{"id": "g"}]}, reason="r", confirm_done=True)
    assert store.load()["status"]["M2"] == "done"

    result = store.commit_slice("M1", {"research_title": "A different thesis"},
                                reason="pivot")
    assert result["stale"] == ["M2"]
    assert result["status"]["M2"] == "done"

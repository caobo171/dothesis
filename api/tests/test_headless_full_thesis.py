"""Consumer auto-draft runs the deep agent over ALL five modules.

The partner report path scopes a run to the chapters it ordered; a thesis
cannot be scoped that way, so mode=full_thesis must clear required_modules
and must not apply the report-only chapter/grounding context vars.
"""
from app.headless_entry import _build_profile, _is_full_thesis


def test_full_thesis_requires_every_module():
    profile = _build_profile({"mode": "full_thesis", "topic": "X"})
    assert profile.required_modules is None
    assert profile.interactive is False


def test_full_thesis_gets_a_bigger_budget_than_a_report():
    full = _build_profile({"mode": "full_thesis", "topic": "X"})
    report = _build_profile({"depth": "analysis_report"})
    assert full.max_turns > report.max_turns
    assert full.wall_clock_s > report.wall_clock_s


def test_explicit_params_still_win_over_the_mode_default():
    profile = _build_profile({"mode": "full_thesis", "max_turns": 7,
                              "wall_clock_s": 60})
    assert profile.max_turns == 7 and profile.wall_clock_s == 60


def test_report_mode_is_unchanged():
    profile = _build_profile({"depth": "analysis_report"})
    assert profile.required_modules is not None


def test_mode_predicate():
    assert _is_full_thesis({"mode": "full_thesis"}) is True
    assert _is_full_thesis({"depth": "analysis_report"}) is False
    assert _is_full_thesis({}) is False


def test_seed_brief_writes_topic_and_language(tmp_path):
    from agent.state import ProjectStateStore
    from app.headless_entry import _seed_brief

    store = ProjectStateStore(tmp_path / "proj")
    wrote = _seed_brief(store, {"mode": "full_thesis", "topic": "AI in SMEs",
                                "language": "vi", "citation_style": "APA"})
    assert wrote is True
    m1 = store.load()["contextStore"]
    assert m1["research_title"] == "AI in SMEs"
    assert m1["language"] == "vi"
    # The raw brief is kept for audit under the seeding-only key.
    assert m1["user_context"]["citation_style"] == "APA"


def test_seed_brief_does_not_overwrite_an_existing_topic(tmp_path):
    from agent.state import ProjectStateStore
    from app.headless_entry import _seed_brief

    store = ProjectStateStore(tmp_path / "proj")
    store.commit_slice("M1", {"research_title": "Student's own title"},
                       reason="prior work")
    wrote = _seed_brief(store, {"mode": "full_thesis", "topic": "Something else"})
    assert wrote is False
    assert store.load()["contextStore"]["research_title"] == "Student's own title"

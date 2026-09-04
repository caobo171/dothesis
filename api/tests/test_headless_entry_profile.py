"""The headless subprocess's RunProfile: budgets + what `done` means for the
request it was handed (convergence spec §1 — mode differences are DATA)."""
from pathlib import Path

import pytest

from agent.headless import RunProfile
from app.headless_entry import _build_profile
from app.partner_run import ReportError


def test_profile_requires_only_the_modules_the_request_needs():
    # analysis_report = intro/results/conclusion (ANALYSIS_CHAPTERS). A seeded
    # partner project usually has an EMPTY M2, and nobody asked for a literature
    # review — requiring one turned "give me 3 chapters" into a full thesis run
    # that failed the partner on work they never requested.
    p = _build_profile({"depth": "analysis_report"})
    assert p.required_modules == frozenset({"M4", "M5"})
    assert p.interactive is False


def test_profile_full_thesis_requires_every_chapter_owning_module():
    p = _build_profile({"depth": "full_thesis"})
    assert p.required_modules == frozenset({"M2", "M3", "M4", "M5"})


def test_profile_explicit_chapter_subset_narrows_the_required_set():
    p = _build_profile({"depth": "full_thesis", "chapters": ["lit_review"]})
    assert p.required_modules == frozenset({"M2"})


def test_profile_budgets_default_to_the_run_profile_defaults():
    # No unexplained second budget in the entrypoint: absent params, the run gets
    # exactly RunProfile's documented caps.
    p = _build_profile({"depth": "analysis_report"})
    assert p.max_turns == RunProfile.max_turns
    assert p.wall_clock_s == RunProfile.wall_clock_s


def test_profile_budgets_overridable_by_job_params():
    p = _build_profile({"depth": "analysis_report", "max_turns": 5,
                        "wall_clock_s": 60})
    assert p.max_turns == 5 and p.wall_clock_s == 60


def test_profile_rejects_a_bad_depth():
    # Fail before spending a single turn, with the router's stable error code.
    with pytest.raises(ReportError):
        _build_profile({"depth": "nonsense"})


def test_headless_entry_never_reaches_for_the_chat_router():
    # RunProfile's docstring promises chat features cannot gate headless, and
    # headless_entry used to import the chat router mid-`main()` for one path
    # helper — pulling the whole FastAPI chat surface into every headless
    # subprocess. That import is LAZY, so no import-time sys.modules check can
    # see it; the source is the only place the invariant is observable without
    # booting a real run.
    src = (Path(__file__).resolve().parents[1] / "app" / "headless_entry.py").read_text()
    assert "chat_v3" not in src

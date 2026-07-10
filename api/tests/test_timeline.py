"""F11 thesis timeline — pure, null-safe planning + progress functions."""
from datetime import date

from agent.timeline import build_timeline


def test_six_month_plan_is_feasible_and_ordered():
    tl = build_timeline(date(2026, 12, 31), "pls-sem", target_n=250, today=date(2026, 7, 1))
    assert tl["feasible"] is True
    ends = [m["end"] for m in tl["milestones"]]
    assert ends == sorted(ends)                       # chronological
    assert ends[-1] <= "2026-12-31"                   # finishes by defense
    assert tl["data_collection_weeks"] >= 3           # realistic buffer


def test_two_week_deadline_is_infeasible():
    tl = build_timeline(date(2026, 7, 15), "pls-sem", target_n=250, today=date(2026, 7, 1))
    assert tl["feasible"] is False

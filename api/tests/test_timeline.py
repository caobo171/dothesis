"""F11 thesis timeline — pure, null-safe planning + progress functions."""
from datetime import date

from agent.timeline import build_timeline, timeline_status


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


def _cs_with_timeline(milestones, actual_focus, status):
    return {"contextStore": {"thesis_timeline": {"milestones": milestones}},
            "focus": actual_focus, "status": status}


# A FULL milestone list (all phases with weeks) — the F0 correction requires this
# so the inclusive act_i..exp_i span has real phases to sum. Dates put today
# (2026-07-10) inside M4's window while M1-collect are already in the past.
_FULL_MS = [
    {"module": "M1", "label": "Topic", "start": "2026-01-01", "end": "2026-01-08", "weeks": 1},
    {"module": "M2", "label": "Literature review", "start": "2026-01-08", "end": "2026-01-29", "weeks": 3},
    {"module": "M3", "label": "Research design + questionnaire", "start": "2026-01-29", "end": "2026-02-12", "weeks": 2},
    {"module": "collect", "label": "Data collection", "start": "2026-02-12", "end": "2026-03-19", "weeks": 5},
    {"module": "M4", "label": "Data analysis", "start": "2026-07-01", "end": "2026-07-15", "weeks": 2},
    {"module": "M5", "label": "Writing", "start": "2026-07-15", "end": "2026-08-12", "weeks": 4},
    {"module": "defense", "label": "Defense prep", "start": "2026-08-12", "end": "2026-08-19", "weeks": 1},
]


def test_behind_schedule_detected():
    cs = _cs_with_timeline(_FULL_MS, "M2", {"M1": "done", "M2": "in_progress", "M3": "locked",
                                            "M4": "locked", "M5": "locked"})
    st = timeline_status(cs, date(2026, 7, 10))
    assert st["expected_phase"] == "M4" and st["actual_phase"] == "M2"
    assert st["weeks_behind"] >= 1 and st["on_track"] is False


def test_no_timeline_is_empty():
    assert timeline_status({"contextStore": {}, "status": {}}, date(2026, 7, 1)) == {}

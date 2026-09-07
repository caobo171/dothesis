"""WELE's publishing-schedule arithmetic, ported verbatim."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.blog import STATUS_PUBLISHED, STATUS_SCHEDULED
from app.blog.schedule import VN_TZ, go_live_at, parse_start_date, plan_status

START = datetime(2026, 9, 10, tzinfo=VN_TZ)


def test_the_first_row_goes_live_on_the_start_date():
    assert go_live_at(0, START, 40) == START


def test_a_full_week_of_rows_stays_inside_that_week():
    assert go_live_at(39, START, 40) < START + timedelta(days=7)
    assert go_live_at(39, START, 40) > START + timedelta(days=6)


def test_the_next_week_starts_exactly_seven_days_later():
    assert go_live_at(40, START, 40) == START + timedelta(days=7)
    assert go_live_at(80, START, 40) == START + timedelta(days=14)


def test_rows_inside_a_week_are_evenly_spaced():
    gaps = {go_live_at(i + 1, START, 7) - go_live_at(i, START, 7) for i in range(6)}
    assert gaps == {timedelta(days=1)}


def test_a_thousand_posts_at_forty_a_week_take_about_twenty_five_weeks():
    span = go_live_at(999, START, 40) - START
    assert timedelta(days=24 * 7) < span < timedelta(days=26 * 7)


def test_a_past_date_inserts_as_published():
    now = START + timedelta(days=1)
    status, published_at, scheduled_at = plan_status(START, now=now)
    assert status == STATUS_PUBLISHED
    assert published_at == START
    assert scheduled_at is None


def test_a_future_date_inserts_as_scheduled_and_keeps_published_at():
    now = START - timedelta(days=1)
    status, published_at, scheduled_at = plan_status(START, now=now)
    assert status == STATUS_SCHEDULED
    # published_at is set too, as WELE does: the row already knows the date it
    # will claim, so nothing has to write it back when the date arrives.
    assert published_at == START
    assert scheduled_at == START


def test_a_start_date_is_read_in_vietnam_time():
    # The audience is Vietnamese, so "2026-09-10" means midnight in Hanoi, not
    # midnight UTC — otherwise every tranche lands at 7am local.
    parsed = parse_start_date("2026-09-10")
    assert parsed == datetime(2026, 9, 10, tzinfo=timezone(timedelta(hours=7)))


def test_a_malformed_start_date_is_rejected():
    with pytest.raises(ValueError):
        parse_start_date("10/09/2026")


def test_per_week_must_be_at_least_one():
    with pytest.raises(ValueError):
        go_live_at(0, START, 0)

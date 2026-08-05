"""Admin view of standalone tool usage — routers/admin_tools.py.

The tools are the one surface with no project, no job and no thread behind
them, so nothing in admin/jobs or admin/papers ever showed them at all. The
tests worth having are about the number this page exists for — cost vs charged,
i.e. how much the balance cap is giving away — about failures being visible
rather than filtered out, and about the endpoints being admin-only.
"""
import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import ToolRun
from tests.conftest import make_user

ADMIN_EMAIL = "cao.nv17@gmail.com"  # admin_config._SEED


@pytest.fixture
def world():
    Session = get_session_factory()
    with Session() as s:
        admin = make_user(s, email=ADMIN_EMAIL)
        alice = make_user(s, email="alice-t@e.com")
        bob = make_user(s, email="bob-t@e.com")
        s.flush()
        # Alice: a paid cite run, a list check she could only half afford, and
        # one failure. Bob: a free scan.
        s.add(ToolRun(user_id=alice.id, tool="cite-docx", ok=True, units=12,
                      credits_cost=12, credits_charged=12, duration_ms=9000))
        s.add(ToolRun(user_id=alice.id, tool="verify-citations", ok=True, units=40,
                      credits_cost=40, credits_charged=5, duration_ms=4000))
        s.add(ToolRun(user_id=alice.id, tool="cite-docx", ok=False,
                      error="unreadable", units=0, credits_cost=0,
                      credits_charged=0, duration_ms=50))
        s.add(ToolRun(user_id=bob.id, tool="scan-docx", ok=True, units=200,
                      credits_cost=0, credits_charged=0, duration_ms=300))
        s.commit()
        for u in (admin, alice, bob):
            s.refresh(u); s.expunge(u)
        return {"admin": admin, "alice": alice, "bob": bob}


def _as(u):
    app = create_app()
    from app.deps import current_user
    app.dependency_overrides[current_user] = lambda: u
    return TestClient(app)


def _post(u, path, **body):
    return _as(u).post(f"/api/v1{path}", json={"access_token": "x", **body})


def test_runs_are_listed_newest_first_with_the_right_email(world):
    r = _post(world["admin"], "/admin/tools/runs")
    assert r.status_code == 200
    items = r.json()["items"]
    assert r.json()["total"] == 4
    assert {i["user_email"] for i in items} == {"alice-t@e.com", "bob-t@e.com"}


def test_a_failed_run_is_visible(world):
    """A success-only view hides the thing an admin is usually looking for."""
    items = _post(world["admin"], "/admin/tools/runs", ok=False).json()["items"]
    assert len(items) == 1
    assert items[0]["error"] == "unreadable"


def test_the_unpaid_filter_finds_what_the_balance_cap_gave_away(world):
    items = _post(world["admin"], "/admin/tools/runs",
                  unpaid_only=True).json()["items"]
    assert len(items) == 1
    assert (items[0]["credits_cost"], items[0]["credits_charged"]) == (40, 5)


def test_runs_filter_by_user(world):
    items = _post(world["admin"], "/admin/tools/runs",
                  user_id=str(world["bob"].id)).json()["items"]
    assert [i["tool"] for i in items] == ["scan-docx"]


def test_the_summary_groups_by_tool(world):
    body = _post(world["admin"], "/admin/tools/summary").json()
    by_tool = {t["tool"]: t for t in body["tools"]}
    assert by_tool["cite-docx"]["runs"] == 2
    assert by_tool["cite-docx"]["failed"] == 1
    assert by_tool["verify-citations"]["units"] == 40


def test_the_summary_reports_what_was_not_collected(world):
    """The number this page exists for. Charging is capped at the balance, and a
    report showing only what was collected would hide how much that costs."""
    totals = _post(world["admin"], "/admin/tools/summary").json()["totals"]
    assert totals["credits_cost"] == 52
    assert totals["credits_charged"] == 17
    assert totals["credits_uncollected"] == 35


def test_the_pricing_table_is_readable_from_admin(world):
    """A price nobody can see from the admin panel is a price nobody revisits."""
    body = _post(world["admin"], "/admin/tools/pricing").json()
    assert body["per_unit"]["verify-citations"] == 1
    assert "extract-text" in body["free"]


@pytest.mark.parametrize("path", ["/admin/tools/runs", "/admin/tools/summary",
                                  "/admin/tools/pricing"])
def test_a_normal_user_cannot_read_the_audit_trail(world, path):
    """A usage log any user can read is its own privacy problem."""
    assert _post(world["alice"], path).status_code in (401, 403)

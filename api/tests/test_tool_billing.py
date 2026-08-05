"""Every tool run is charged and recorded — app/tool_billing.py.

Before this, a tool either borrowed humanize's billing (and got stamped
action_kind="humanize" whatever it actually was) or charged nothing at all
because it called no model and there were no tokens to meter. Neither was a
decision; both fell out of billing being wired to token usage.

The tests worth having are about the edges of that, because the happy path is
arithmetic: what a FAILED run costs, what a user at zero is charged, that the
under-billing is visible rather than silent, and that the free tools are free on
purpose rather than by omission.
"""
import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import CreditTransaction, TokenLedger, ToolRun
from app.tool_billing import record_tool_run, tool_cost
from tests.conftest import make_user

USAGE_1K = [{"model": "gemini-2.5-flash", "prompt_tokens": 700, "completion_tokens": 300}]


@pytest.fixture
def user():
    Session = get_session_factory()
    with Session() as s:
        u = make_user(s, email="tb@e.com", credit=1000)
        s.commit(); s.refresh(u); s.expunge(u)
        return u


def _as(u):
    app = create_app()
    from app.deps import current_user
    app.dependency_overrides[current_user] = lambda: u
    return TestClient(app)


def _runs(user_id):
    Session = get_session_factory()
    with Session() as s:
        return s.query(ToolRun).filter_by(user_id=user_id).all()


def _balance(user_id):
    from app.models import User
    Session = get_session_factory()
    with Session() as s:
        return s.get(User, user_id).credit


def _session_user(u):
    """Re-attach the detached fixture user to a live session."""
    from app.models import User
    Session = get_session_factory()
    s = Session()
    return s, s.get(User, u.id)


# --- the price ---------------------------------------------------------------

def test_a_lookup_tool_is_billed_per_lookup():
    """Checking a 40-entry reference list costs 40x what checking one does. The
    unit is the CrossRef round trip, which is the work actually done."""
    assert tool_cost("verify-citations", units=1) == 1
    assert tool_cost("verify-citations", units=40) == 40


def test_a_failed_run_bills_its_tokens_but_not_its_lookups():
    """The two halves of a price part ways on failure. The model ran and we paid
    for it; a CrossRef timeout did no work for the student."""
    with_tokens = tool_cost("cite-docx", units=10, usage=USAGE_1K, ok=False)
    assert with_tokens > 0                       # tokens still billed
    assert with_tokens == tool_cost("cite-docx", units=0, usage=USAGE_1K)
    assert tool_cost("verify-citations", units=40, ok=False) == 0


def test_the_free_tools_are_free():
    """extract-text is the INPUT step for the paid tools — billing it charges a
    student twice for one file. The scans are the confirm-before-you-spend step;
    charging for the estimate defeats showing it."""
    for tool in ("extract-text", "scan-docx", "scan-cite-docx"):
        assert tool_cost(tool, units=500) == 0


# --- what gets recorded ------------------------------------------------------

def test_a_run_is_recorded_even_when_it_charges_nothing(user):
    s, u = _session_user(user)
    try:
        record_tool_run(s, u, tool="scan-docx", units=120)
    finally:
        s.close()
    rows = _runs(user.id)
    assert len(rows) == 1
    assert rows[0].tool == "scan-docx"
    assert rows[0].credits_cost == 0
    # A tool being used heavily for free is exactly what the table is for.
    assert rows[0].units == 120


def test_a_failed_run_is_recorded_with_its_error(user):
    s, u = _session_user(user)
    try:
        record_tool_run(s, u, tool="plagiarism-check", ok=False,
                        error="provider_not_configured")
    finally:
        s.close()
    row = _runs(user.id)[0]
    assert row.ok is False
    assert row.error == "provider_not_configured"
    assert row.credits_charged == 0


def test_the_ledger_records_the_tool_not_humanize(user):
    """Every token_ledger row used to say action_kind="humanize" whatever the
    tool was, which made the per-action cost table the ledger exists for
    unreadable."""
    s, u = _session_user(user)
    try:
        record_tool_run(s, u, tool="cite-docx", usage=USAGE_1K)
    finally:
        s.close()
    Session = get_session_factory()
    with Session() as s2:
        kinds = [r.action_kind for r in
                 s2.query(TokenLedger).filter_by(user_id=user.id).all()]
    assert kinds == ["cite-docx"]


def test_the_debit_names_the_tool(user):
    s, u = _session_user(user)
    try:
        record_tool_run(s, u, tool="verify-citations", units=5)
    finally:
        s.close()
    Session = get_session_factory()
    with Session() as s2:
        tx = s2.query(CreditTransaction).filter_by(user_id=user.id).all()
    assert [(t.reason, t.delta) for t in tx] == [("verify-citations", -5)]


# --- the balance cap ---------------------------------------------------------

def test_a_user_at_zero_is_under_billed_not_refused(user):
    """Refusing here would fail a document the student already waited a minute
    for. The trade is deliberate — and only defensible while it is visible."""
    Session = get_session_factory()
    with Session() as s:
        from app.models import User
        s.get(User, user.id).credit = 2
        s.commit()

    s, u = _session_user(user)
    try:
        charge = record_tool_run(s, u, tool="verify-citations", units=40)
    finally:
        s.close()

    assert charge.cost == 40
    assert charge.charged == 2          # capped at the balance
    assert charge.under_billed is True
    assert _balance(user.id) == 0

    row = _runs(user.id)[0]
    # BOTH numbers stored. A table recording only what was collected would hide
    # exactly how much is being given away.
    assert (row.credits_cost, row.credits_charged) == (40, 2)


def test_billing_failure_never_costs_the_caller_their_result(user, monkeypatch):
    """A tool must return its document even if the invoice cannot be written.

    Every caller is a route that has ALREADY done the work, so this function
    raising is the one outcome that turns an accounting bug into a lost thesis.
    """
    import app.tool_billing as tb

    def boom(*_a, **_k):
        raise RuntimeError("ledger on fire")

    monkeypatch.setattr(tb, "_charge", boom)
    s, u = _session_user(user)
    try:
        charge = record_tool_run(s, u, tool="verify-citations", units=1)
    finally:
        s.close()
    assert charge.charged == 0


# --- through the routes ------------------------------------------------------

def test_the_rhythm_tool_charges_and_records(user):
    text = ("Nghiên cứu này khảo sát hành vi mua sắm. Mẫu gồm hai trăm người. "
            "Kết quả cho thấy mối quan hệ dương. Thảo luận được trình bày sau.")
    r = _as(user).post("/api/v1/tools/writing-rhythm",
                       json={"access_token": "x", "text": text})
    assert r.status_code == 200
    assert r.json()["credits_charged"] == 1
    assert [x.tool for x in _runs(user.id)] == ["writing-rhythm"]


def test_a_passage_too_short_to_score_is_not_billed(user):
    r = _as(user).post("/api/v1/tools/writing-rhythm",
                       json={"access_token": "x", "text": "Một câu."})
    assert r.json()["verdict"] == "too_short"
    row = _runs(user.id)[0]
    assert (row.ok, row.credits_charged) == (False, 0)


def test_the_list_check_bills_per_reference_reached(user, monkeypatch):
    """A truncated run charges for the ones it checked, never for the ones it
    only found."""
    import app.routers.tools as t
    monkeypatch.setattr(t, "_crossref_by_doi", lambda doi: None)
    monkeypatch.setattr(t, "_crossref_by_text", lambda text: None)
    text = ("TÀI LIỆU THAM KHẢO\n"
            "Nguyen, A. (2019). Mot bai bao rat dai ve hanh vi tieu dung. Tap chi X.\n"
            "Tran, B. (2020). Mot bai bao khac cung rat dai ve thuong hieu. Tap chi Y.\n")
    r = _as(user).post("/api/v1/tools/verify-citations",
                       json={"access_token": "x", "text": text})
    assert r.status_code == 200
    assert r.json()["checked"] == 2
    assert r.json()["credits_charged"] == 2
    assert _runs(user.id)[0].units == 2


def test_nothing_found_is_recorded_but_not_billed(user):
    r = _as(user).post("/api/v1/tools/verify-citations",
                       json={"access_token": "x", "text": "Khong co trich dan nao o day."})
    assert r.json()["detected"] == 0
    assert r.json()["credits_charged"] == 0
    row = _runs(user.id)[0]
    assert (row.ok, row.error) == (False, "no_references_found")


def test_a_connector_call_is_filed_under_mcp(user):
    """Without the header every connector call is filed as a web run, and the
    admin view reports one number for two very different populations."""
    text = ("Nghiên cứu này khảo sát hành vi mua sắm. Mẫu gồm hai trăm người. "
            "Kết quả cho thấy mối quan hệ dương. Thảo luận được trình bày sau.")
    _as(user).post("/api/v1/tools/writing-rhythm",
                   json={"access_token": "x", "text": text},
                   headers={"X-DoThesis-Surface": "mcp"})
    assert _runs(user.id)[0].surface == "mcp"


def test_an_unknown_surface_is_not_stored(user):
    """The header is caller-supplied. An audit column that echoes arbitrary
    caller text is not an audit column."""
    text = ("Nghiên cứu này khảo sát hành vi mua sắm. Mẫu gồm hai trăm người. "
            "Kết quả cho thấy mối quan hệ dương. Thảo luận được trình bày sau.")
    _as(user).post("/api/v1/tools/writing-rhythm",
                   json={"access_token": "x", "text": text},
                   headers={"X-DoThesis-Surface": "<script>whatever</script>"})
    assert _runs(user.id)[0].surface == "web"


# --- the caller's own history ------------------------------------------------

def test_a_user_sees_their_own_runs(user):
    s, u = _session_user(user)
    try:
        record_tool_run(s, u, tool="verify-citations", units=7)
        record_tool_run(s, u, tool="scan-docx", units=100)
    finally:
        s.close()
    body = _as(user).post("/api/v1/tools/runs",
                          json={"access_token": "x"}).json()
    assert body["total"] == 2
    # Newest first, and the FREE run is listed too — a student asking why their
    # credits did not move needs to see the run that did not charge.
    assert [i["tool"] for i in body["items"]] == ["scan-docx", "verify-citations"]
    assert body["items"][0]["credits_charged"] == 0


def test_a_user_never_sees_another_users_runs(user):
    """Scoped to the caller with no override. A filter parameter here is how a
    user-facing history turns into the admin view by accident."""
    Session = get_session_factory()
    with Session() as s:
        other = make_user(s, email="someone-else@e.com", credit=100)
        s.flush()
        record_tool_run(s, other, tool="cite-docx", units=5)
        s.commit()

    body = _as(user).post("/api/v1/tools/runs", json={"access_token": "x"}).json()
    assert body["total"] == 0


def test_the_shortfall_is_visible_to_the_user_who_incurred_it(user):
    """A student whose balance ran out mid-document should learn it here, not as
    a surprise on the next run."""
    Session = get_session_factory()
    with Session() as s:
        from app.models import User
        s.get(User, user.id).credit = 3
        s.commit()
    s, u = _session_user(user)
    try:
        record_tool_run(s, u, tool="verify-citations", units=40)
    finally:
        s.close()
    item = _as(user).post("/api/v1/tools/runs",
                          json={"access_token": "x"}).json()["items"][0]
    assert (item["credits_cost"], item["credits_charged"]) == (40, 3)


def test_an_unconfigured_similarity_provider_bills_nothing(user, monkeypatch):
    """Charging for a check the deployment cannot perform is the clearest
    possible way to lose a customer's trust in the meter."""
    import orchestrator.tools.plagiarism as p
    monkeypatch.setattr(p, "get_provider", lambda: None)
    r = _as(user).post("/api/v1/tools/plagiarism-check",
                       json={"access_token": "x", "text": "mot doan van ban"})
    assert r.json()["error"] == "provider_not_configured"
    assert r.json()["credits_charged"] == 0
    assert _balance(user.id) == 1000

"""Pulling a dataset straight off a Google Sheets link.

Vietnamese students collect thesis data with Google Forms, so the data lives in
a Sheet and the link is what they paste into chat. Before this tool the agent
had no way to turn a URL into a file — every data tool takes a workspace path —
so it told them to download and re-upload, and blamed itself for "not being able
to read the link".

Two things this must never do, both of which are the reason it is a tool and not
an httpx call at the call site:

  - fetch a host nobody vetted. The URL arrives in a chat message, which is
    untrusted, and can be planted by a prompt injection inside an uploaded
    document. An unrestricted fetcher is an SSRF hole pointed at localhost:7100
    and the cloud metadata endpoint.
  - save Google's sign-in/404 HTML as the student's dataset. A private sheet
    answers an anonymous request with 8 KB of `text/html` and HTTP 404 —
    verified against a real student link — and writing that to uploads/ is the
    same silent-garbage failure the .docx and .xlsx paths were bitten by.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from agent.tools.data_fetch import make_data_fetch_tools

SHEET = ("https://docs.google.com/spreadsheets/d/"
         "1CpEqbtga3kyEBQo6IsHJsKpgMLtYuN5QyRLjfe72ifY/edit?gid=387461515#gid=387461515")

CSV = b"ID,Age,Edu,DEC_1,DEC_2\n1,23,3,5,4\n2,31,4,4,5\n3,27,2,3,3\n"

# What Google actually returns for a sheet that is not shared publicly.
PRIVATE_HTML = (b"<!DOCTYPE html><html lang=\"vi\"><head>"
                b"<title>Kh\xc3\xb4ng t\xc3\xacm th\xe1\xba\xa5y trang</title></head><body></body></html>")


def _tool(tmp_path):
    (tool,) = make_data_fetch_tools(tmp_path)
    return tool


@pytest.fixture
def http(monkeypatch):
    """Stub the network. Records every URL actually requested."""
    calls: list[str] = []
    state = {"status": 200, "body": CSV,
             "headers": {"content-type": "text/csv",
                         "content-disposition": 'attachment; filename="Khao sat - Form.csv"'}}

    def fake_get(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(status_code=state["status"], content=state["body"],
                               headers=state["headers"])

    import agent.tools.data_fetch as df
    monkeypatch.setattr(df, "httpx", SimpleNamespace(get=fake_get))
    return SimpleNamespace(calls=calls, state=state)


def test_a_sheets_link_lands_in_the_workspace_as_a_real_file(http, tmp_path):
    out = json.loads(_tool(tmp_path).invoke({"url": SHEET}))

    assert out.get("ok") is True, out
    written = tmp_path / out["file"]
    assert written.exists(), f"nothing written at {out['file']}"
    assert written.read_bytes() == CSV
    # The profile rides back with it, so the agent knows the columns without a
    # second round-trip through run_stats(op="detect").
    assert "Age" in out["profile"] and "DEC_1" in out["profile"]


def test_the_export_url_keeps_the_tab_the_student_was_looking_at(http, tmp_path):
    """A workbook has many tabs. `gid` in the pasted link is the one on screen —
    dropping it silently exports the FIRST sheet, which is usually the raw form
    responses rather than the cleaned data they meant."""
    _tool(tmp_path).invoke({"url": SHEET})

    (requested,) = http.calls
    assert "/export" in requested and "format=csv" in requested
    assert "gid=387461515" in requested
    assert "/edit" not in requested


def test_a_private_sheet_is_reported_not_saved(http, tmp_path):
    """The exact case that started this: Google answers an anonymous request for
    a private sheet with 404 + an HTML page. Writing that to uploads/ would hand
    the model 8 KB of markup as the student's data."""
    http.state.update(status=404, body=PRIVATE_HTML,
                      headers={"content-type": "text/html; charset=utf-8"})

    out = json.loads(_tool(tmp_path).invoke({"url": SHEET}))

    assert out.get("ok") is not True
    assert out["error"] == "sheet_not_public"
    # The message has to say what to CLICK, not just that it failed.
    fix = " ".join(out["how_to_fix"]).lower()
    assert "anyone with the link" in fix
    assert "download" in fix or "tải" in fix
    assert list((tmp_path / "uploads").glob("*")) == [] or not (tmp_path / "uploads").exists()


def test_html_masquerading_as_a_200_is_still_refused(http, tmp_path):
    """Google does not always use 404 — a consent or interstitial page can come
    back 200. Content, not status, decides whether this is a spreadsheet."""
    http.state.update(status=200, body=PRIVATE_HTML,
                      headers={"content-type": "text/html; charset=utf-8"})

    out = json.loads(_tool(tmp_path).invoke({"url": SHEET}))

    assert out.get("ok") is not True
    assert out["error"] == "sheet_not_public"


def test_a_host_nobody_allowlisted_is_refused_without_a_request(http, tmp_path):
    """SSRF gate. The refusal must happen BEFORE the request — a tool that
    connects first and judges after has already made the connection."""
    for url in ("http://localhost:7100/api/v1/credit/packages",
                "http://169.254.169.254/latest/meta-data/",
                "https://evil.example.com/data.csv"):
        out = json.loads(_tool(tmp_path).invoke({"url": url}))
        assert out["error"] == "host_not_allowed", (url, out)

    assert http.calls == [], f"a blocked host was still fetched: {http.calls}"


def test_an_oversized_download_is_refused(http, tmp_path):
    from agent.tools.data_fetch import _MAX_BYTES
    http.state.update(body=b"x" * (_MAX_BYTES + 1),
                      headers={"content-type": "text/csv"})

    out = json.loads(_tool(tmp_path).invoke({"url": SHEET}))

    assert out["error"] == "too_large"
    assert list((tmp_path / "uploads").glob("*")) == [] or not (tmp_path / "uploads").exists()


def test_a_link_that_is_not_a_spreadsheet_says_so(http, tmp_path):
    out = json.loads(_tool(tmp_path).invoke({"url": "https://docs.google.com/document/d/abc/edit"}))

    assert out["error"] == "not_a_spreadsheet"
    assert http.calls == []

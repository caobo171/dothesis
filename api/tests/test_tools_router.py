"""Stateless helper tools — routers/tools.py.

The assertions that matter here are about HONESTY, not plumbing. Both endpoints
report on things a student will act on: whether their writing looks machine-
generated, and whether a reference is real. Overstating either is worse than
returning nothing — one invites false confidence, the other invites deleting a
genuine source.
"""
import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from tests.conftest import make_user

EVEN = ("This is a sentence of words here. This is a sentence of words here. "
        "This is a sentence of words here. This is a sentence of words here.")
VARIED = ("Short. " + "The committee, having reviewed the sampling frame in "
          "considerable detail across three separate sessions, concluded that "
          "the stratification was defensible. It was not. " * 2)


@pytest.fixture
def user():
    Session = get_session_factory()
    with Session() as s:
        u = make_user(s, email="w@e.com")
        s.commit(); s.refresh(u); s.expunge(u)
        return u


def _as(user):
    app = create_app()
    from app.deps import current_user
    app.dependency_overrides[current_user] = lambda: user
    return TestClient(app)


# --- writing rhythm ---------------------------------------------------------

def test_uniform_sentences_score_high(user):
    r = _as(user).post("/api/v1/tools/writing-rhythm",
                       json={"access_token": "x", "text": EVEN})
    assert r.status_code == 200
    b = r.json()
    assert b["ok"] and b["score"] > 0.6
    assert b["verdict"] == "very_even"


def test_varied_sentences_score_lower(user):
    even = _as(user).post("/api/v1/tools/writing-rhythm",
                          json={"access_token": "x", "text": EVEN}).json()
    varied = _as(user).post("/api/v1/tools/writing-rhythm",
                            json={"access_token": "x", "text": VARIED}).json()
    assert varied["score"] < even["score"]


def test_too_short_is_declined_not_guessed(user):
    """Three sentences is the floor. Scoring one sentence would be a number with
    nothing behind it, which is worse than saying no."""
    r = _as(user).post("/api/v1/tools/writing-rhythm",
                       json={"access_token": "x", "text": "One sentence."})
    assert r.json()["ok"] is False
    assert r.json()["verdict"] == "too_short"


def test_the_response_never_claims_to_be_a_detector(user):
    """detector.py calls this a WEAK signal that must not be read as a verdict.
    If wording here ever implies Turnitin/GPTZero agreement, that is a product
    honesty regression, not a copy tweak."""
    b = _as(user).post("/api/v1/tools/writing-rhythm",
                       json={"access_token": "x", "text": EVEN}).json()
    blob = " ".join(str(v) for v in b.values()).lower()
    for banned in ("turnitin", "gptzero", "detector will", "will be flagged",
                   "ai-generated", "plagiar"):
        assert banned not in blob, f"response implies detection: {banned!r}"
    assert "burstiness" in b["basis"]


# --- citation verification --------------------------------------------------

def test_a_real_doi_is_confirmed(user, monkeypatch):
    import app.routers.tools as t
    monkeypatch.setattr(t, "_crossref_by_doi", lambda doi: {
        "DOI": doi, "title": ["Attention Is All You Need"],
        "author": [{"family": "Vaswani", "given": "Ashish"}],
        "issued": {"date-parts": [[2017]]},
        "container-title": ["NeurIPS"], "URL": "https://doi.org/x"})
    r = _as(user).post("/api/v1/tools/verify-citation",
                       json={"access_token": "x",
                             "reference": "Vaswani et al. 10.5555/3295222.3295349"})
    b = r.json()
    assert b["found"] is True
    assert b["matched_by"] == "doi"
    assert b["year"] == 2017
    # An exact DOI hit carries no fuzzy-match caveat.
    assert b["warning"] is None


def test_a_text_match_is_flagged_as_fuzzy(user, monkeypatch):
    """CrossRef returns its best guess for ANY query, so a title hit is evidence,
    not proof. Flattening that into found=true would be the dangerous shortcut."""
    import app.routers.tools as t
    monkeypatch.setattr(t, "_crossref_by_text", lambda q: {
        "DOI": "10.1/x", "title": ["Something Vaguely Similar"],
        "author": [], "issued": {"date-parts": [[2020]]}})
    b = _as(user).post("/api/v1/tools/verify-citation",
                       json={"access_token": "x",
                             "reference": "Some paper about widgets, 2020"}).json()
    assert b["found"] is True
    assert b["matched_by"] == "search"
    assert "Fuzzy" in b["warning"]


def test_a_missing_doi_does_not_call_it_fabricated(user, monkeypatch):
    """A typo looks identical to an invention here. The wording must not push a
    student into deleting a real source."""
    import app.routers.tools as t
    monkeypatch.setattr(t, "_crossref_by_doi", lambda doi: None)
    b = _as(user).post("/api/v1/tools/verify-citation",
                       json={"access_token": "x", "reference": "10.9999/nope"}).json()
    assert b["found"] is False
    assert "typo" in b["detail"].lower()


def test_no_crossref_match_explains_the_limits_of_crossref(user, monkeypatch):
    import app.routers.tools as t
    monkeypatch.setattr(t, "_crossref_by_text", lambda q: None)
    b = _as(user).post("/api/v1/tools/verify-citation",
                       json={"access_token": "x", "reference": "A book, 1998"}).json()
    assert b["found"] is False
    assert "not proof" in b["detail"].lower()


def test_a_network_failure_is_never_reported_as_not_found(user, monkeypatch):
    """The worst possible error: telling a student a real citation is fake
    because CrossRef was briefly unreachable."""
    import app.routers.tools as t

    def _boom(*a, **k):
        raise RuntimeError("connection reset")
    monkeypatch.setattr(t, "_crossref_by_text", _boom)
    b = _as(user).post("/api/v1/tools/verify-citation",
                       json={"access_token": "x", "reference": "Something, 2020"}).json()
    assert b["ok"] is False
    assert b["found"] is False
    assert "no conclusion" in b["detail"].lower()


# --- citation verification, whole list --------------------------------------
# This is the flow a student actually has: attach the finished thesis, ask which
# of its sources are real. The risks are the mirror image of the single check —
# checking things that are NOT references (noise the student learns to ignore)
# and silently checking only some of them (a clean bill of health for a list
# that was never fully read).

REF_DOC = """CHƯƠNG 4: KẾT QUẢ NGHIÊN CỨU

Chương 4 trình bày kết quả xử lý dữ liệu khảo sát năm 2023 từ những du khách
đã trực tiếp trải nghiệm sản phẩm City Tour Phố Cổ.

TÀI LIỆU THAM KHẢO

[1] Nguyen, T. (2021). Service quality in heritage tourism. Tourism Review.
[2] Vaswani, A. (2017). Attention is all you need. NeurIPS.
[3] Hair, J. F. (2019). Multivariate data analysis. Cengage.
"""


def test_a_reference_list_is_split_into_its_entries():
    from app.routers.tools import extract_references

    refs = extract_references(REF_DOC)
    assert len(refs) == 3
    # The numbering is stripped — "[1] " is formatting, not part of the citation.
    assert refs[0].startswith("Nguyen, T. (2021)")


def test_body_prose_before_the_heading_is_not_checked():
    """The chapter text above carries a year ("dữ liệu khảo sát năm 2023"), so
    without the heading cut it would be looked up as if it were a citation."""
    from app.routers.tools import extract_references

    refs = extract_references(REF_DOC)
    assert not any("City Tour" in r for r in refs)


def test_a_reference_wrapped_across_lines_is_rejoined():
    """PDF extraction breaks one reference over several lines. Checking each
    fragment separately would report three failures for one real source."""
    from app.routers.tools import extract_references

    refs = extract_references(
        "References\n\nNguyen, T., & Tran, H.\nService quality in heritage\n"
        "tourism contexts. Tourism Review, 2021.\n")
    assert len(refs) == 1
    assert "Tourism Review, 2021" in refs[0]


def test_lines_without_a_year_or_doi_are_left_alone():
    from app.routers.tools import extract_references

    assert extract_references("References\n\nSee the appendix.\nAcknowledgements\n") == []


def test_every_entry_gets_the_same_verdict_the_single_check_would_give(user, monkeypatch):
    import app.routers.tools as t
    monkeypatch.setattr(t, "_crossref_by_text", lambda q: {
        "DOI": "10.1/x", "title": ["Something Vaguely Similar"],
        "author": [], "issued": {"date-parts": [[2020]]}})

    b = _as(user).post("/api/v1/tools/verify-citations",
                       json={"access_token": "x", "text": REF_DOC}).json()
    assert b["ok"] is True
    assert b["detected"] == 3
    assert b["checked"] == 3
    assert b["truncated"] is False
    # Fuzzy stays fuzzy in bulk. A batch result that quietly upgraded these to
    # "confirmed" would be the whole danger of this endpoint.
    assert all(i["matched_by"] == "search" for i in b["items"])
    assert all("Fuzzy" in i["warning"] for i in b["items"])
    # Each verdict is attributable to the line it came from.
    assert b["items"][0]["reference"].startswith("Nguyen, T. (2021)")


def test_a_long_list_reports_that_it_was_truncated(user, monkeypatch):
    import app.routers.tools as t
    monkeypatch.setattr(t, "_crossref_by_text", lambda q: None)

    doc = "References\n\n" + "".join(
        f"Author{i}, A. (20{i:02d}). A paper about widgets number {i}. Journal.\n"
        for i in range(60))
    b = _as(user).post("/api/v1/tools/verify-citations",
                       json={"access_token": "x", "text": doc}).json()
    assert b["detected"] == 60
    assert b["checked"] == 50
    assert b["truncated"] is True


def test_a_full_length_thesis_is_accepted(user, monkeypatch):
    """The mode exists to take a whole thesis, and a 100-page Vietnamese one
    extracts to ~200k characters. The first cap was 40k, which 422'd the exact
    input the attach button produces."""
    import app.routers.tools as t
    monkeypatch.setattr(t, "_crossref_by_text", lambda q: None)

    filler = "Chương 4 trình bày kết quả xử lý dữ liệu khảo sát.\n" * 4000
    doc = filler + "\nTÀI LIỆU THAM KHẢO\n\nNguyen, T. (2021). Heritage tourism. Review.\n"
    assert len(doc) > 40000
    r = _as(user).post("/api/v1/tools/verify-citations",
                       json={"access_token": "x", "text": doc})
    assert r.status_code == 200, r.text
    assert r.json()["detected"] == 1


def test_a_document_with_no_reference_list_says_so(user):
    b = _as(user).post("/api/v1/tools/verify-citations",
                       json={"access_token": "x",
                             "text": "Chương 4 trình bày kết quả xử lý dữ liệu."}).json()
    assert b["ok"] is True
    assert b["detected"] == 0
    assert b["items"] == []
    assert "No references found" in b["detail"]


# --- transport ---------------------------------------------------------------

@pytest.mark.parametrize("path,body", [
    ("/api/v1/tools/writing-rhythm", {"text": EVEN}),
    ("/api/v1/tools/verify-citation", {"reference": "10.1/x"}),
])
def test_header_only_auth_works(user, path, body, monkeypatch):
    """The MCP path: the token is an Authorization header and there is NO
    access_token in the body. An AuthedBody schema here makes Pydantic 422 the
    request before current_user ever reads the header — which is exactly how
    both of these shipped broken and were caught only against production.

    Every test above passes access_token in the body, so none of them covered
    the transport the connector actually uses.
    """
    import app.routers.tools as t
    monkeypatch.setattr(t, "_crossref_by_doi", lambda doi: None)

    client = _as(user)
    r = client.post(path, json=body, headers={"Authorization": "Bearer irrelevant"})
    assert r.status_code == 200, r.text


# --- similarity / plagiarism ------------------------------------------------
# The one behaviour worth pinning: an unconfigured or broken provider must never
# be reported as "nothing matched". A student reads that as a clean bill of
# health and submits on it.

def test_unconfigured_provider_is_not_a_clean_result(user, monkeypatch):
    monkeypatch.delenv("PLAGIARISM_PROVIDER", raising=False)
    r = _as(user).post("/api/v1/tools/plagiarism-check",
                       json={"access_token": "x", "text": "Some thesis prose."})
    assert r.status_code == 200
    b = r.json()
    assert b["ok"] is False
    assert b["error"] == "provider_not_configured"
    # Not 0.0 — a zero score is indistinguishable from "we checked, you're clean".
    assert b["score"] is None
    assert b["matches"] == []
    assert "NOT checked" in b["detail"]


def test_provider_failure_is_not_a_clean_result(user, monkeypatch):
    class Boom:
        name = "boom"

        def check(self, text, *, language="vi"):
            raise RuntimeError("vendor down")

    monkeypatch.setattr("orchestrator.tools.plagiarism.get_provider", lambda: Boom())
    r = _as(user).post("/api/v1/tools/plagiarism-check",
                       json={"access_token": "x", "text": "Some thesis prose."})
    b = r.json()
    assert b["ok"] is False
    assert b["error"] == "provider_error"
    assert b["score"] is None


def test_configured_provider_result_is_passed_through(user, monkeypatch):
    class Fake:
        name = "fake"

        def check(self, text, *, language="vi"):
            return {"score": 0.23, "provider": "fake", "matches": [
                {"source": "Nguyen 2021", "url": None, "overlap": 0.23,
                 "excerpt": "…"},
            ]}

    monkeypatch.setattr("orchestrator.tools.plagiarism.get_provider", lambda: Fake())
    b = _as(user).post("/api/v1/tools/plagiarism-check",
                       json={"access_token": "x", "text": "Some thesis prose."}).json()
    assert b["ok"] is True
    assert b["score"] == 0.23
    assert b["provider"] == "fake"
    assert b["matches"][0]["source"] == "Nguyen 2021"


# --- writing anchor ---------------------------------------------------------
# Saving used to be a SIDE EFFECT of a successful humanize, so the sample the
# feature refuses to run without could only be stored by first paying for a
# rewrite — and a rewrite that failed verification discarded it.

def test_anchor_saves_and_reads_back(user):
    c = _as(user)
    sample = " ".join(["từ"] * 160)
    saved = c.post("/api/v1/tools/writing-anchor/save",
                   json={"access_token": "x", "anchor": sample}).json()
    assert saved["ok"] is True and saved["words"] == 160

    read = c.post("/api/v1/tools/writing-anchor", json={"access_token": "x"}).json()
    assert read["has_anchor"] is True
    assert read["words"] == 160


def test_anchor_rejects_a_sample_too_short_to_carry_rhythm(user):
    c = _as(user)
    r = c.post("/api/v1/tools/writing-anchor/save",
               json={"access_token": "x", "anchor": "quá ngắn"}).json()
    assert r["ok"] is False
    assert r["error"] == "too_short"
    # And nothing was stored, so a later humanize still asks for a real sample.
    assert c.post("/api/v1/tools/writing-anchor",
                  json={"access_token": "x"}).json()["has_anchor"] is False


def test_no_anchor_reads_as_absent_not_as_an_error(user):
    r = _as(user).post("/api/v1/tools/writing-anchor", json={"access_token": "x"}).json()
    assert r["ok"] is True
    assert r["has_anchor"] is False


# --- text extraction --------------------------------------------------------

def test_extract_reads_a_plain_text_file(user):
    r = _as(user).post(
        "/api/v1/tools/extract-text",
        files={"file": ("draft.txt", "Kết quả cho thấy tác động tích cực.".encode(), "text/plain")},
    )
    assert r.status_code == 200
    b = r.json()
    assert b["ok"] is True
    assert "Kết quả" in b["text"]
    assert b["filename"] == "draft.txt"


def test_extract_rejects_an_unsupported_type(user):
    r = _as(user).post(
        "/api/v1/tools/extract-text",
        files={"file": ("photo.png", b"\x89PNG\r\n", "image/png")},
    )
    assert r.status_code == 415


def test_empty_extraction_names_the_scan_problem(user):
    """A scanned PDF is images. "No text found" sends the student hunting for a
    bug in our parser; naming the cause tells them what to actually do."""
    r = _as(user).post(
        "/api/v1/tools/extract-text",
        files={"file": ("blank.txt", b"   \n  ", "text/plain")},
    ).json()
    assert r["ok"] is False
    assert r["error"] == "no_text"
    assert "scan" in (r["detail"] or "")


# --- document humanize ------------------------------------------------------
# The point of this path is that the student gets their DOCUMENT back. The text
# extractor flattens headings to plain lines and moves every table to the end,
# which is fine for feeding the agent and useless as the input to a rewrite
# someone will hand to a supervisor.

def _sample_docx() -> bytes:
    import io as _io
    from docx import Document
    d = Document()
    d.add_heading("4.3.3. Thang đo Chuyên môn của KOLs (EX)", level=3)
    d.add_paragraph(
        "Thang đo EX gồm 5 biến quan sát đo lường mức độ người tiêu dùng cảm nhận "
        "KOLs có kiến thức, kỹ năng và sự am hiểu về sản phẩm trong lĩnh vực họ "
        "giới thiệu tới khách hàng của mình.")
    d.add_paragraph("Bảng 4.7: Chi tiết độ tin cậy")   # caption — too short
    t = d.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text = "EXP_1"
    t.rows[0].cells[1].text = "0.694"
    buf = _io.BytesIO(); d.save(buf); return buf.getvalue()


def test_scan_counts_what_would_be_touched(user):
    r = _as(user).post("/api/v1/tools/document/scan",
                       files={"file": ("t.docx", _sample_docx(),
                                       "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
    assert r.status_code == 200
    b = r.json()
    assert b["ok"] is True
    assert b["body_paragraphs"] == 1      # only the real prose paragraph
    assert b["headings"] == 1             # heading skipped
    assert b["short_or_captions"] == 1    # "Bảng 4.7:" caption skipped
    assert b["tables"] == 1               # table skipped — it's data
    assert b["passages"] == 1


def test_scan_rejects_a_pdf(user):
    r = _as(user).post("/api/v1/tools/document/scan",
                       files={"file": ("t.pdf", b"%PDF-1.4", "application/pdf")})
    assert r.status_code == 415


def test_rewrite_replaces_prose_and_leaves_structure_alone(monkeypatch):
    """Headings, captions and tables must come out byte-identical."""
    from docx import Document
    import io as _io
    from orchestrator.tools.humanize_docx import humanize_docx

    def fake_humanize(text, **kw):
        return {"ok": True, "text": "ĐÃ VIẾT LẠI.", "usage": [{"model": "m",
                "prompt_tokens": 1, "completion_tokens": 1}]}

    out, report = humanize_docx(_sample_docx(), humanize_fn=fake_humanize)
    assert report["ok"] and report["rewritten"] == 1

    d = Document(_io.BytesIO(out))
    texts = [p.text for p in d.paragraphs]
    assert "4.3.3. Thang đo Chuyên môn của KOLs (EX)" in texts   # heading intact
    assert "Bảng 4.7: Chi tiết độ tin cậy" in texts              # caption intact
    assert "ĐÃ VIẾT LẠI." in texts                               # prose rewritten
    assert d.tables[0].rows[0].cells[1].text == "0.694"          # table untouched
    # And the heading is still a heading, not a flattened line.
    heading = next(p for p in d.paragraphs if p.text.startswith("4.3.3."))
    assert heading.style.name.lower().startswith("heading")


def test_a_batch_that_changes_paragraph_count_keeps_the_originals():
    """The batch is reassembled positionally, so a model that merges two
    paragraphs would shift every later one into the wrong slot. Refuse instead."""
    import io as _io
    from docx import Document
    from orchestrator.tools.humanize_docx import humanize_docx

    d = Document()
    for i in range(2):
        d.add_paragraph(f"Đoạn văn số {i} có đủ số từ để được coi là một đoạn "
                        f"văn thân bài thực sự trong tài liệu này nhé.")
    buf = _io.BytesIO(); d.save(buf)

    # Returns ONE paragraph where two were sent.
    out, report = humanize_docx(
        buf.getvalue(), humanize_fn=lambda t, **k: {"ok": True, "text": "Gộp lại."})
    assert report["rewritten"] == 0
    assert report["skipped"] == 2
    assert report["failures"][0]["error"] == "paragraph_count_changed"
    assert "Đoạn văn số 0" in [p.text for p in Document(_io.BytesIO(out)).paragraphs][0]

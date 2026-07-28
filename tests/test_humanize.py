"""Tests for the humanize pass.

Scope: the DETERMINISTIC half — frozen-token extraction, the verification gate,
AI-tell stripping, and anchor loading. The LLM half (router + rewrite) is
exercised with a fake model so the pipeline's control flow — reject, repair,
accept — is covered without network.

The frozen-token gate is the piece that must not be wrong: it is the only thing
standing between a humanized results chapter and a chapter whose p-values
quietly changed.
"""
from __future__ import annotations

import json

import pytest

from orchestrator.tools import humanize as H


# --- frozen tokens -------------------------------------------------------

def test_numbers_and_table_refs_are_frozen():
    t = ("Kết quả tại Bảng 4.3 cho thấy β = 0,412 với p = 0,003 và R² = 0,58 "
         "trên mẫu N = 245.")
    f = H.frozen_tokens(t)
    assert f["num:0,412"] == 1
    assert f["num:0,003"] == 1
    assert f["num:245"] == 1
    assert f["ref:bảng 4.3"] == 1


def test_dropping_a_number_is_a_violation():
    src = "Hệ số Cronbach's Alpha đạt 0,871 trên mẫu 245 quan sát."
    bad = "Hệ số Cronbach's Alpha đạt mức cao trên mẫu 245 quan sát."
    r = H.verify_frozen(src, bad)
    assert not r["ok"]
    assert "num:0,871" in r["missing"]


def test_inventing_a_number_is_a_violation():
    src = "Nhân tố này giải thích phần lớn phương sai."
    bad = "Nhân tố này giải thích 67,4% phương sai."
    r = H.verify_frozen(src, bad)
    assert not r["ok"]
    assert r["added"]


def test_rounding_a_p_value_is_caught():
    # The failure mode that motivates the whole gate: prose that reads better
    # and reports a different statistic.
    src = "với p = 0,032"
    bad = "với p = 0,03"
    assert not H.verify_frozen(src, bad)["ok"]


def test_pure_prose_rewrite_passes():
    src = ("Kết quả phân tích tại Bảng 4.3 cho thấy nhân tố Chất lượng dịch vụ "
           "có tác động tích cực đến Sự hài lòng (β = 0,412; p = 0,003).")
    good = ("Bảng 4.3 cho thấy Chất lượng dịch vụ tác động tích cực tới Sự hài "
            "lòng, với β = 0,412 và p = 0,003.")
    assert H.verify_frozen(src, good)["ok"]


def test_citation_may_move_between_parenthetical_and_narrative_form():
    # A rewrite is allowed to reflow a citation; it is not allowed to lose one.
    src = "Mô hình này đã được kiểm định trước đó (Nguyễn, 2019)."
    good = "Nguyễn (2019) đã kiểm định mô hình này trước đó."
    assert H.verify_frozen(src, good)["ok"]


def test_dropping_a_citation_is_a_violation():
    src = "Thang đo được kế thừa từ (Nguyễn, 2019) và (Trần, 2021)."
    bad = "Thang đo được kế thừa từ (Nguyễn, 2019)."
    r = H.verify_frozen(src, bad)
    assert not r["ok"]
    assert any("trần" in m for m in r["missing"])


def test_multi_author_citation_anchors_on_the_first_author():
    # Both forms must normalize to the same token, or every reflowed multi-author
    # citation would look like a drop + an invention.
    paren = "Mô hình được kế thừa (Trần & Nguyễn, 2021)."
    narrative = "Trần và Nguyễn (2021) đã đề xuất mô hình này."
    assert H.verify_frozen(paren, narrative)["ok"]
    assert H.frozen_tokens(narrative)["cite:trần|2021"] == 1


def test_two_citations_in_a_row_do_not_bleed_into_each_other():
    # Regression from a live run: walking back from "(2021)" crossed the 2019
    # citation via the joiner "và" and attributed 2021 to Nguyễn, so a faithful
    # rewrite was rejected.
    paren = "Phù hợp với Nguyễn (2019) và (Trần & Lê, 2021)."
    narrative = "Phù hợp với Nguyễn (2019) và Trần & Lê (2021)."
    f = H.frozen_tokens(narrative)
    assert f["cite:trần|2021"] == 1
    assert f["cite:nguyễn|2019"] == 1
    assert "cite:nguyễn|2021" not in f
    assert H.verify_frozen(paren, narrative)["ok"]


def test_et_al_narrative_citation_resolves_to_the_surname():
    assert H.frozen_tokens("Nguyễn et al. (2019) báo cáo kết quả tương tự.")[
        "cite:nguyễn|2019"] == 1


def test_lowercase_vietnamese_syllable_is_not_read_as_a_surname():
    # Regression: [A-ZÀ-Ỹ] matches 'ấ' (U+1EA5), which made "cho thấy (2019)"
    # register a surname of "ấy" and rejected every valid rewrite.
    assert H.frozen_tokens("kết quả cho thấy (2019) là năm bản lề.") == \
        H.frozen_tokens("kết quả cho thấy (2019) là năm bản lề.")
    assert not any(k.startswith("cite:ấy")
                   for k in H.frozen_tokens("cho thấy (2019)"))


def test_multi_source_parenthetical_keeps_every_citation():
    src = "Các nghiên cứu trước (Nguyễn, 2019; Trần, 2021) đều ủng hộ giả thuyết."
    f = H.frozen_tokens(src)
    assert f["cite:nguyễn|2019"] == 1
    assert f["cite:trần|2021"] == 1


def test_markdown_table_numbers_are_frozen():
    src = "| Nhân tố | AVE |\n|---|---|\n| CLDV | 0,612 |\n| SHL | 0,704 |"
    same_order = "| Nhân tố | AVE |\n|---|---|\n| CLDV | 0,612 |\n| SHL | 0,704 |"
    swapped = "| Nhân tố | AVE |\n|---|---|\n| CLDV | 0,704 |\n| SHL | 0,612 |"
    assert H.verify_frozen(src, same_order)["ok"]
    # Known limit, asserted so it stays a known limit: verification is a
    # multiset, so swapping two values inside a table is NOT caught. Tables are
    # rendered from verified state (render_verified_sections), not humanized —
    # that is what protects them.
    assert H.verify_frozen(src, swapped)["ok"]


# --- AI-tell stripping ---------------------------------------------------

def test_vi_padding_is_stripped():
    out = H.strip_ai_tells("Kết quả cho thấy rằng mô hình phù hợp.", "vi")
    assert "cho thấy rằng" not in out
    assert "cho thấy mô hình" in out


def test_sentence_opening_connector_is_stripped_and_next_word_capitalized():
    out = H.strip_ai_tells("Mô hình phù hợp. Bên cạnh đó, kết quả ổn định.", "vi")
    assert "Bên cạnh đó" not in out
    assert "Kết quả ổn định" in out


def test_connector_survives_mid_sentence():
    # The tell is the metronome at sentence starts, not the words themselves.
    src = "Kết quả ổn định và bên cạnh đó còn nhất quán."
    assert H.strip_ai_tells(src, "vi") == src


def test_stripping_never_touches_frozen_tokens():
    src = ("Hơn nữa, kết quả tại Bảng 4.3 cho thấy rằng β = 0,412 — với "
           "p = 0,003 (Nguyễn, 2019).")
    assert H.verify_frozen(src, H.strip_ai_tells(src, "vi"))["ok"]


def test_en_stripping_still_works():
    out = H.strip_ai_tells("We utilize the data. Furthermore, results hold.", "en")
    assert "use the data" in out
    assert "Furthermore" not in out


# --- anchor library ------------------------------------------------------

def test_no_anchors_installed_returns_no_anchor_not_a_rewrite(tmp_path, monkeypatch):
    monkeypatch.setenv("DOTHESIS_ANCHOR_DIR", str(tmp_path))
    assert H.load_anchors("vi") == []
    r = H.humanize_prose("Kết quả cho thấy mô hình phù hợp.", language="vi")
    assert r["ok"] is False
    assert r["error"] == "no_anchor"
    # Critical: the caller gets the ORIGINAL back, not an unanchored rewrite.
    assert r["text"] == "Kết quả cho thấy mô hình phù hợp."


def test_manifest_entry_with_missing_file_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setenv("DOTHESIS_ANCHOR_DIR", str(tmp_path))
    (tmp_path / "present.txt").write_text("Real human prose here.", encoding="utf-8")
    (tmp_path / "manifest.json").write_text(json.dumps({"anchors": [
        {"id": "present", "language": "vi", "file": "present.txt", "desc": "d"},
        {"id": "ghost", "language": "vi", "file": "ghost.txt", "desc": "d"},
    ]}), encoding="utf-8")
    ids = [a["id"] for a in H.load_anchors("vi")]
    assert ids == ["present"]


def test_anchors_filter_by_language(tmp_path, monkeypatch):
    monkeypatch.setenv("DOTHESIS_ANCHOR_DIR", str(tmp_path))
    (tmp_path / "a.txt").write_text("vi prose", encoding="utf-8")
    (tmp_path / "b.txt").write_text("en prose", encoding="utf-8")
    (tmp_path / "manifest.json").write_text(json.dumps({"anchors": [
        {"id": "a", "language": "vi", "file": "a.txt", "desc": "d"},
        {"id": "b", "language": "en", "file": "b.txt", "desc": "d"},
    ]}), encoding="utf-8")
    assert [a["id"] for a in H.load_anchors("vi")] == ["a"]
    assert [a["id"] for a in H.load_anchors("en")] == ["b"]


# --- pipeline control flow (fake LLM) ------------------------------------

class FakeLLM:
    """Returns queued strings in order; records the prompts it was given."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        class _M:
            content = self.replies.pop(0) if self.replies else ""
        return _M()


SRC = "Kết quả tại Bảng 4.3 cho thấy rằng β = 0,412 với p = 0,003 (Nguyễn, 2019)."


@pytest.fixture()
def user_anchor():
    return "toi viet cai nay hoi con di hoc, luc do chua biet gi ve AI ca"


def test_user_anchor_is_used_without_any_library(tmp_path, monkeypatch, user_anchor):
    monkeypatch.setenv("DOTHESIS_ANCHOR_DIR", str(tmp_path))
    good = "Bảng 4.3 cho thấy β = 0,412, p = 0,003, đúng như Nguyễn (2019) đã nêu."
    r = H.humanize_prose(SRC, language="vi", user_anchor=user_anchor,
                         llm=FakeLLM(good))
    assert r["ok"] is True
    assert r["anchor"] == "user_supplied"
    assert r["text"] == good


def test_frozen_violation_triggers_one_repair_then_accepts(tmp_path, monkeypatch,
                                                           user_anchor):
    monkeypatch.setenv("DOTHESIS_ANCHOR_DIR", str(tmp_path))
    bad = "Bảng 4.3 cho thấy β = 0,41, p = 0,003 (Nguyễn, 2019)."   # rounded β
    fixed = "Bảng 4.3 cho thấy β = 0,412, p = 0,003 (Nguyễn, 2019)."
    llm = FakeLLM(bad, fixed)
    r = H.humanize_prose(SRC, language="vi", user_anchor=user_anchor, llm=llm)
    assert r["ok"] is True
    assert r["repairs"] == 1
    assert r["text"] == fixed
    # The repair prompt must name the exact token that went missing.
    assert "0,412" in llm.prompts[-1]


def test_two_failures_keep_the_original(tmp_path, monkeypatch, user_anchor):
    monkeypatch.setenv("DOTHESIS_ANCHOR_DIR", str(tmp_path))
    bad = "Bảng 4.3 cho thấy β = 0,41, p = 0,003 (Nguyễn, 2019)."
    r = H.humanize_prose(SRC, language="vi", user_anchor=user_anchor,
                         llm=FakeLLM(bad, bad))
    assert r["ok"] is False
    assert r["error"] == "frozen_violation"
    assert r["text"] == SRC          # original, untouched
    assert r["changed"] is False


def test_llm_failure_returns_original(tmp_path, monkeypatch, user_anchor):
    monkeypatch.setenv("DOTHESIS_ANCHOR_DIR", str(tmp_path))

    class Boom:
        def invoke(self, prompt):
            raise RuntimeError("gateway down")

    r = H.humanize_prose(SRC, language="vi", user_anchor=user_anchor, llm=Boom())
    assert r["ok"] is False
    assert r["text"] == SRC


def test_frozen_tokens_reach_the_rewrite_prompt(tmp_path, monkeypatch, user_anchor):
    monkeypatch.setenv("DOTHESIS_ANCHOR_DIR", str(tmp_path))
    llm = FakeLLM(SRC)
    H.humanize_prose(SRC, language="vi", user_anchor=user_anchor, llm=llm)
    prompt = llm.prompts[0]
    assert "0,412" in prompt and "Bảng 4.3" in prompt
    assert "(nguyễn, 2019)" in prompt.lower()


def test_export_hook_is_inert_unless_asked(monkeypatch):
    # The export path is shared with headless auto-mode and the partner API.
    # Default-off must mean the pass is never even imported for those callers.
    from agent.tools.writing import _maybe_humanize

    def boom(*a, **k):
        raise AssertionError("humanize must not run when disabled")

    monkeypatch.setattr(H, "humanize_sections", boom)
    sections = [{"title": "Chương 4", "prose": SRC}]
    out, report = _maybe_humanize(sections, False, "vi")
    assert out == sections
    assert report is None


def test_export_hook_never_breaks_an_export(monkeypatch):
    from agent.tools.writing import _maybe_humanize

    monkeypatch.setattr(H, "humanize_sections",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    sections = [{"title": "Chương 4", "prose": SRC}]
    out, report = _maybe_humanize(sections, True, "vi")
    assert out == sections                       # exported as composed
    assert report == [{"ok": False, "error": "humanizer_failed"}]


def test_humanize_sections_skips_references_and_keeps_failures(tmp_path,
                                                               monkeypatch,
                                                               user_anchor):
    monkeypatch.setenv("DOTHESIS_ANCHOR_DIR", str(tmp_path))
    sections = [
        {"title": "Chương 4", "prose": SRC},
        {"title": "References", "prose": "Nguyễn, A. (2019). Một bài báo."},
    ]
    bad = "Bảng 4.3 cho thấy β = 0,41, p = 0,003 (Nguyễn, 2019)."
    out, report = H.humanize_sections(sections, language="vi",
                                      user_anchor=user_anchor,
                                      llm=FakeLLM(bad, bad))
    assert out[0]["prose"] == SRC              # rejected → original kept
    assert out[1]["prose"] == sections[1]["prose"]
    assert [r["title"] for r in report] == ["Chương 4"]   # References not touched
    assert report[0]["ok"] is False

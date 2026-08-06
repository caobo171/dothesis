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


class FakeScorer:
    """Returns queued AI-likelihood scores in order; records what it scored."""

    def __init__(self, *scores):
        self.scores = list(scores)
        self.calls = []

    def score(self, text):
        self.calls.append(text)
        return self.scores.pop(0) if self.scores else 0.0


# Rewrites that preserve every frozen token of SRC (num 4.3, Bảng 4.3, 0,412,
# 0,003, and the Nguyễn|2019 citation) — kept dash-free so strip_ai_tells leaves
# them byte-for-byte and the assertions can compare on identity.
_G1 = "Bảng 4.3 cho β = 0,412; p = 0,003 (Nguyễn, 2019). Kết quả một."
_G2 = "Bảng 4.3 cho β = 0,412 và p = 0,003, theo Nguyễn (2019). Kết quả hai."
_G3 = "β = 0,412 và p = 0,003 tại Bảng 4.3, phù hợp Nguyễn (2019). Kết quả ba."


def test_scorer_stops_early_when_below_threshold(tmp_path, monkeypatch, user_anchor):
    monkeypatch.setenv("DOTHESIS_ANCHOR_DIR", str(tmp_path))
    r = H.humanize_prose(SRC, language="vi", user_anchor=user_anchor,
                         llm=FakeLLM(_G1), scorer=FakeScorer(0.2))
    assert r["ok"] is True
    assert r["text"] == _G1
    assert r["score"] == 0.2
    assert r["rounds"] == 1          # one round, no escalation needed


def test_scorer_iterates_and_keeps_the_lowest_scoring_candidate(tmp_path,
                                                                monkeypatch,
                                                                user_anchor):
    monkeypatch.setenv("DOTHESIS_ANCHOR_DIR", str(tmp_path))
    # Pin the round budget instead of inheriting the default. test_live_crafter
    # does load_dotenv(".env", override=True) at IMPORT time, so collecting the
    # full suite pushes the real deployment config into os.environ — and the
    # measure-only setting there is HUMANIZE_MAX_ROUNDS=1, which caps this loop
    # at one round and fails an assertion about three. Passing in isolation and
    # failing in the suite is exactly the shape that wastes an afternoon.
    monkeypatch.setenv("HUMANIZE_MAX_ROUNDS", "4")
    # 0.9 and 0.7 stay above the 0.5 threshold, so the loop escalates; 0.3 wins.
    r = H.humanize_prose(SRC, language="vi", user_anchor=user_anchor,
                         llm=FakeLLM(_G1, _G2, _G3),
                         scorer=FakeScorer(0.9, 0.7, 0.3))
    assert r["ok"] is True
    assert r["text"] == _G3
    assert r["score"] == 0.3
    assert r["rounds"] == 3


def test_scorer_none_score_degrades_to_single_pass(tmp_path, monkeypatch,
                                                   user_anchor):
    # Backend down / unconfigured — take the first verified rewrite, don't loop.
    monkeypatch.setenv("DOTHESIS_ANCHOR_DIR", str(tmp_path))
    r = H.humanize_prose(SRC, language="vi", user_anchor=user_anchor,
                         llm=FakeLLM(_G1, _G2, _G3), scorer=FakeScorer(None))
    assert r["ok"] is True
    assert r["text"] == _G1
    assert r["score"] is None
    assert r["rounds"] == 1


def test_scorer_loop_never_ships_a_frozen_violation(tmp_path, monkeypatch,
                                                    user_anchor):
    # Even under scoring, a rewrite that can't hold the numbers is discarded and
    # the ORIGINAL is kept — the frozen gate outranks the detector score.
    monkeypatch.setenv("DOTHESIS_ANCHOR_DIR", str(tmp_path))
    monkeypatch.setenv("HUMANIZE_MAX_ROUNDS", "2")
    bad = "Bảng 4.3 cho β = 0,41 và p = 0,003 (Nguyễn, 2019)."   # β lost 0,412
    scorer = FakeScorer(0.1, 0.1)
    r = H.humanize_prose(SRC, language="vi", user_anchor=user_anchor,
                         llm=FakeLLM(bad, bad, bad, bad), scorer=scorer)
    assert r["ok"] is False
    assert r["error"] == "frozen_violation"
    assert r["text"] == SRC
    assert "score" not in r          # a rejected candidate is never scored
    assert scorer.calls == []


def test_humanize_llm_override_is_passed_through(monkeypatch):
    # HUMANIZE_LLM_ROUTE/MODEL let humanize run on Gemini while the report writer
    # stays on qwen — verify _get_llm forwards them to the factory.
    import orchestrator.llm as L
    captured = {}
    monkeypatch.setattr(L, "get_orchestrator_llm",
                        lambda **kw: captured.update(kw) or object())
    monkeypatch.setenv("HUMANIZE_LLM_ROUTE", "native")
    monkeypatch.setenv("HUMANIZE_LLM_MODEL", "gemini-2.5-flash")
    H._get_llm(0.95)
    assert captured["route"] == "native"
    assert captured["model"] == "gemini-2.5-flash"
    assert captured["temperature"] == 0.95


def test_humanize_llm_override_absent_forwards_none(monkeypatch):
    # No override env → route/model are None, so the engine default (qwen) stands.
    import orchestrator.llm as L
    captured = {}
    monkeypatch.setattr(L, "get_orchestrator_llm",
                        lambda **kw: captured.update(kw) or object())
    monkeypatch.delenv("HUMANIZE_LLM_ROUTE", raising=False)
    monkeypatch.delenv("HUMANIZE_LLM_MODEL", raising=False)
    H._get_llm(0.5)
    assert captured["route"] is None and captured["model"] is None


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


# --- token accounting (added with per-call metering) ------------------------

def test_humanize_prose_reports_token_usage_per_llm_call():
    """The API bills off this list, so it must be populated on the success path
    and one entry must appear per LLM call (anchor router + rewrite)."""
    from orchestrator.tools import humanize as h

    class _Resp:
        usage_metadata = {"input_tokens": 120, "output_tokens": 45}
        content = "Câu văn đã được viết lại hoàn toàn khác so với bản gốc ban đầu."

    class _LLM:
        model = "gemini-2.5-flash"

        def invoke(self, prompt):
            return _Resp()

    out = h.humanize_prose("Một câu. Hai câu ở đây. Ba câu dài hơn một chút nữa.",
                           language="vi", user_anchor="x " * 60, llm=_LLM())
    assert isinstance(out.get("usage"), list)
    assert out["usage"], "no usage captured — the API would bill nothing"
    assert out["usage"][0]["model"] == "gemini-2.5-flash"
    assert out["usage"][0]["prompt_tokens"] == 120


def test_usage_does_not_leak_between_concurrent_passes():
    """A ContextVar, not a module global: two students' passages must not add
    their tokens to each other's bill."""
    import threading

    from orchestrator.tools import humanize as h

    class _Resp:
        content = "Một bản viết lại hoàn toàn mới và khác biệt rõ ràng."

        def __init__(self, tok):
            self.usage_metadata = {"input_tokens": tok, "output_tokens": 0}

    class _LLM:
        model = "m"

        def __init__(self, tok):
            self.tok = tok

        def invoke(self, prompt):
            return _Resp(self.tok)

    results = {}

    def run(name, tok):
        results[name] = h.humanize_prose(
            "Một câu. Hai câu ở đây. Ba câu dài hơn một chút nữa.",
            language="vi", user_anchor="x " * 60, llm=_LLM(tok))

    ts = [threading.Thread(target=run, args=("a", 111)),
          threading.Thread(target=run, args=("b", 222))]
    for t in ts: t.start()
    for t in ts: t.join()

    for name, tok in (("a", 111), ("b", 222)):
        toks = {u["prompt_tokens"] for u in results[name]["usage"]}
        assert toks == {tok}, f"{name} was billed for another pass: {toks}"


def test_callers_without_a_collector_are_unaffected():
    """Export/eval paths call the inner function; metering is opt-in and must
    not change their return shape."""
    from orchestrator.tools import humanize as h
    assert h._USAGE.get() is None


# --- cross-script slips -----------------------------------------------------
# Observed in production: a Vietnamese passage came back reading
# "đánh giá तथा mua sắm sản phẩm" — तथा is Devanagari for "and", substituted for
# "và". Every gate passed it, because the frozen-token check only diffs numbers,
# table refs and citations, and a cross-script synonym touches none of those.

def test_devanagari_substitution_is_a_violation():
    from orchestrator.tools.humanize import verify_script, _verify
    orig = "khách hàng và cách người tiêu dùng tìm kiếm, đánh giá và mua sắm sản phẩm."
    bad = "khách hàng và cách người tiêu dùng tìm kiếm, đánh giá तथा mua sắm sản phẩm."
    assert verify_script(orig, bad) == ["DEVANAGARI"]
    assert _verify(orig, bad)["ok"] is False


def test_a_clean_vietnamese_rewrite_passes_the_script_gate():
    from orchestrator.tools.humanize import _verify
    orig = "khách hàng và cách người tiêu dùng tìm kiếm, đánh giá và mua sắm sản phẩm."
    good = "khách hàng cùng cách người tiêu dùng tìm kiếm, đánh giá và mua sắm sản phẩm."
    check = _verify(orig, good)
    assert check["ok"] is True
    assert check["foreign_scripts"] == []


def test_a_stray_greek_symbol_is_not_a_script_slip():
    """β and α are ordinary notation in a stats thesis. One glyph is not a
    language slip, so the gate needs 2+ letters before it calls foul —
    otherwise every rewrite that mentions a coefficient gets discarded."""
    from orchestrator.tools.humanize import verify_script
    assert verify_script("Kết quả cho thấy tác động.", "Kết quả β cho thấy tác động.") == []
    assert verify_script("Hệ số β = 0.42", "Hệ số β đạt 0.42") == []


def test_an_injected_cjk_word_is_a_violation():
    from orchestrator.tools.humanize import verify_script
    assert verify_script("Kết quả cho thấy", "Kết quả 结果 cho thấy") == ["CJK"]


def test_vietnamese_tone_marks_are_not_a_foreign_script():
    """Decomposed Vietnamese (NFD) carries combining marks; those are category
    Mn and must never register as another writing system."""
    import unicodedata
    from orchestrator.tools.humanize import verify_script
    nfc = "đánh giá hiệu quả"
    assert verify_script(nfc, unicodedata.normalize("NFD", nfc)) == []


# --- sentence case ----------------------------------------------------------
# Observed in a shipped .docx: a chapter opener came back "chương 4 trình bày
# kết quả…". Nothing deterministic lowercased it — strip_ai_tells and
# _clean_output preserve case, and _strip_start_connectors actively restores it.
# The model produced it, reading the paragraph as a continuation.

def test_lowercased_paragraph_opener_is_repaired():
    from orchestrator.tools.humanize import _restore_leading_case
    assert _restore_leading_case(
        "Chương 4 trình bày kết quả.", "chương 4 trình bày kết quả.",
    ) == "Chương 4 trình bày kết quả."


def test_every_paragraph_in_a_batch_is_repaired_not_just_the_first():
    """humanize_docx joins paragraphs with blank lines, so fixing only the
    leading character would leave paragraphs 2..n lowercased."""
    from orchestrator.tools.humanize import _restore_leading_case
    out = _restore_leading_case("Aaa bbb.\n\nCcc ddd.", "aaa xxx.\n\nccc yyy.")
    assert out == "Aaa xxx.\n\nCcc yyy."


def test_a_legitimately_lowercase_opener_is_left_alone():
    """Evidence comes from the SOURCE, not from a guess about orthography: a
    paragraph that really does open on a symbol or lowercase term keeps it."""
    from orchestrator.tools.humanize import _restore_leading_case
    assert _restore_leading_case("p-value nhỏ hơn 0.05.", "p-value dưới 0.05.") \
        == "p-value dưới 0.05."
    assert _restore_leading_case("β đạt 0.42.", "β là 0.42.") == "β là 0.42."


def test_case_repair_runs_inside_the_rewrite_path():
    """Not just the helper — the pass itself must emit repaired text."""
    from orchestrator.tools import humanize as H

    class FakeLLM:
        def invoke(self, prompt):
            class M:
                content = "chương 4 trình bày kết quả nghiên cứu của luận văn."
            return M()

    r = H.humanize_prose(
        "Chương 4 trình bày kết quả nghiên cứu.",
        language="vi", user_anchor="x " * 160, llm=FakeLLM())
    assert r["ok"] is True
    assert r["text"].startswith("Chương 4")


def test_case_repair_never_touches_a_greek_or_cjk_opener():
    """Regression: `"β".islower()` is True and `"β".upper()` is "Β", so a naive
    islower() check turned "β = 0,412…" into "Β = 0,412…" — corrupting a
    coefficient symbol the frozen-token gate does not cover (β is neither a
    number nor a citation). Caught by the v4 loop's own fixtures."""
    from orchestrator.tools.humanize import _restore_leading_case
    assert _restore_leading_case("Kết quả tại Bảng 4.3.", "β = 0,412 và p = 0,003.") \
        == "β = 0,412 và p = 0,003."
    assert _restore_leading_case("Kết quả cho thấy.", "结果 cho thấy.") == "结果 cho thấy."


# --- language must never change -------------------------------------------
#
# The failure these cover, from a real run: an ENGLISH dissertation was fed to
# /tools/document/humanize, which defaults `language` to "vi" and never asked
# the text what language it was in. The rewrite prompt says "Rewrite the user's
# text in Vietnamese", so the model did exactly that — 69 paragraphs came back
# translated, citations and numbers intact, and every existing gate passed them:
# verify_frozen only diffs numbers/refs/citations, and verify_script only
# catches a change of WRITING SYSTEM, which vi→en is not (both are Latin).

EN_SRC = ("Prior research has confirmed that leadership matters in hospitality, "
          "but three limitations restrict what it can tell a hotel manager "
          "(Bass, 1985).")
EN_OK = ("Earlier work has shown that leadership matters in hospitality, yet "
         "three limitations restrict what it tells a hotel manager (Bass, 1985).")
# Same content, same citation, same numbers — only the language changed. This is
# what actually shipped to the student.
VI_TRANSLATION = ("Các nghiên cứu trước đây đã khẳng định vai trò quan trọng của "
                  "lãnh đạo trong lĩnh vực khách sạn, nhưng ba hạn chế khiến kết "
                  "quả chưa đủ để hướng dẫn nhà quản lý khách sạn (Bass, 1985).")


def test_detect_language_reads_the_text():
    assert H.detect_language(EN_SRC) == "en"
    assert H.detect_language(VI_TRANSLATION) == "vi"


def test_detect_language_is_unsure_rather_than_wrong_on_a_fragment():
    """Too short to judge → None, so the caller's own value stays in charge."""
    assert H.detect_language("Bảng 4.3") is None
    assert H.detect_language("") is None


def test_an_english_name_does_not_make_a_paragraph_vietnamese():
    """An English paragraph citing a Vietnamese author is still English —
    measured: real English prose scores 0.0 diacritic density, real Vietnamese
    prose 0.31, so a stray name cannot cross the threshold."""
    assert H.detect_language(
        "The sample was drawn from hotels in Hanoi and analysed by "
        "Nguyễn (2019), whose instrument this study adapts.") == "en"


def test_english_source_is_rewritten_in_english_even_when_vi_was_requested(
        tmp_path, monkeypatch, user_anchor):
    """The document route defaults language to "vi"; the TEXT overrules it."""
    monkeypatch.setenv("DOTHESIS_ANCHOR_DIR", str(tmp_path))
    llm = FakeLLM(EN_OK)
    r = H.humanize_prose(EN_SRC, language="vi", user_anchor=user_anchor, llm=llm)
    assert "in English" in llm.prompts[0]
    assert "in Vietnamese" not in llm.prompts[0]
    assert r["ok"] is True


def test_a_translated_rewrite_is_rejected_and_the_original_kept(
        tmp_path, monkeypatch, user_anchor):
    """Even if the prompt is ignored, a translation must never ship."""
    monkeypatch.setenv("DOTHESIS_ANCHOR_DIR", str(tmp_path))
    r = H.humanize_prose(EN_SRC, language="en", user_anchor=user_anchor,
                         llm=FakeLLM(VI_TRANSLATION, VI_TRANSLATION))
    assert r["ok"] is False
    assert r["text"] == EN_SRC
    assert r["frozen"]["language_changed"] is True


def test_the_repair_call_is_told_the_language_changed(
        tmp_path, monkeypatch, user_anchor):
    monkeypatch.setenv("DOTHESIS_ANCHOR_DIR", str(tmp_path))
    llm = FakeLLM(VI_TRANSLATION, EN_OK)
    r = H.humanize_prose(EN_SRC, language="en", user_anchor=user_anchor, llm=llm)
    assert "English" in llm.prompts[-1]
    assert r["ok"] is True
    assert r["text"] == EN_OK


def test_vietnamese_still_routes_to_vietnamese(tmp_path, monkeypatch, user_anchor):
    """The VN-first path is unchanged — detection agrees with the old default."""
    monkeypatch.setenv("DOTHESIS_ANCHOR_DIR", str(tmp_path))
    llm = FakeLLM("Bảng 4.3 cho thấy β = 0,412, p = 0,003 (Nguyễn, 2019).")
    H.humanize_prose(SRC, language="vi", user_anchor=user_anchor, llm=llm)
    assert "in Vietnamese" in llm.prompts[0]


# --- AI-tell list, second pass --------------------------------------------
#
# Additions taken from a competing humanizer prompt, kept to the parts that are
# safe for a REWRITE: concrete word/phrase tells. Its content rules ("add an
# example", "give your own view") were rejected — this pass may not invent, and
# an invented sentence carrying no number or citation passes verify_frozen.

def test_ngoai_ra_and_dac_biet_la_are_stripped_as_openers():
    """The two highest-frequency LLM-Vietnamese openers missing from the list."""
    out = H.strip_ai_tells("Mô hình phù hợp. Ngoài ra, hệ số tải đều đạt yêu cầu.", "vi")
    assert "Ngoài ra" not in out
    assert "Hệ số tải đều đạt yêu cầu." in out
    out2 = H.strip_ai_tells("Kết quả ổn định. Đặc biệt là nhân tố EX đạt mức cao.", "vi")
    assert "Đặc biệt là" not in out2


def test_a_connector_mid_sentence_still_survives():
    """Same guarantee the existing connectors have: the tell is the metronome at
    the START of a sentence, not the words, which are ordinary Vietnamese."""
    src = "Thang đo được giữ nguyên ngoài ra không có thay đổi nào khác."
    assert H.strip_ai_tells(src, "vi") == src


def test_removing_a_padding_opener_hands_over_the_capital():
    """Regression: the phrase removals lived in _SUBS_EN, which deletes without
    recapitalizing — "The data holds. It is worth noting that results are
    stable." came out as "…holds. results are stable.", a lowercase sentence."""
    out = H.strip_ai_tells("The data holds. It is worth noting that results are stable.", "en")
    assert out == "The data holds. Results are stable."


def test_vietnamese_padding_opener_is_removed():
    out = H.strip_ai_tells(
        "Mẫu đạt yêu cầu. Không thể phủ nhận rằng lãnh đạo có ảnh hưởng.", "vi")
    assert "Không thể phủ nhận" not in out
    assert "Lãnh đạo có ảnh hưởng." in out


def test_crucial_role_is_treated_like_pivotal_role():
    assert "central role" in H.strip_ai_tells(
        "Leadership plays a crucial role in retention.", "en")


def test_in_todays_world_opener_is_removed():
    out = H.strip_ai_tells(
        "In today's rapidly changing world, hotels compete on service.", "en")
    assert out == "Hotels compete on service."


def test_the_new_tells_never_touch_a_frozen_token():
    """Same standard the whole stripper is held to."""
    src = ("Mô hình phù hợp. Ngoài ra, β = 0,412 với p = 0,003 tại Bảng 4.3 "
           "(Nguyễn, 2019).")
    assert H.verify_frozen(src, H.strip_ai_tells(src, "vi"))["ok"]


def test_the_prompt_warns_that_dang_ke_can_be_statistical():
    """The one word from that list which must NOT be auto-replaced: in a results
    passage "đáng kể"/"significant" reports statistical significance."""
    assert "đáng kể" not in [p.pattern for p, _ in H._SUBS_VI
                             if p.pattern == r"\bđáng kể\b"]
    assert "STATISTICAL significance" in H._REWRITE_PROMPT


# --- chatbot artifacts leaking into the document --------------------------
#
# From Wikipedia's "Signs of AI writing" group 4, via the cuongmeai handbook:
# the assistant-isms a chat model wraps around an answer. The rewrite prompt
# already says "no preamble, no commentary" — nothing ENFORCED it, and
# _clean_output stripped only code fences. In the .docx walk a preamble on its
# own line changes the paragraph count, so the batch is skipped (the student
# pays for a rewrite they don't get); on the SAME line it lands in the thesis.

def test_english_preamble_line_is_removed():
    assert H._clean_output(
        "Here is the rewritten text:\n\nLeadership shapes retention."
    ) == "Leadership shapes retention."


def test_vietnamese_inline_preamble_is_removed():
    """The corrupting shape: no extra paragraph, so the count check can't see it."""
    assert H._clean_output(
        "Bản viết lại: Lãnh đạo ảnh hưởng tới sự gắn bó của nhân viên."
    ) == "Lãnh đạo ảnh hưởng tới sự gắn bó của nhân viên."


def test_a_real_sentence_ending_in_a_colon_is_not_touched():
    """The false positive that matters: "Đây là …:" opens legitimate Vietnamese
    paragraphs. Only a lead-in that also names the REWRITE is a preamble."""
    src = "Đây là kết quả của mô hình: ba giả thuyết được chấp nhận."
    assert H._clean_output(src) == src
    src2 = "The model produced three results: H1, H2 and H4 were supported."
    assert H._clean_output(src2) == src2


def test_signoff_is_removed():
    assert H._clean_output(
        "Leadership shapes retention.\n\nHope this helps!"
    ) == "Leadership shapes retention."
    assert H._clean_output(
        "Lãnh đạo ảnh hưởng tới sự gắn bó.\n\nHy vọng bản viết lại này hữu ích!"
    ) == "Lãnh đạo ảnh hưởng tới sự gắn bó."


def test_stripping_never_empties_the_rewrite():
    """A reply that is ONLY a preamble must come back untouched, not blank —
    an empty rewrite is a lost paragraph, which is worse than a stray line."""
    assert H._clean_output("Here is the rewritten text:") == "Here is the rewritten text:"


def test_filler_phrases_are_shortened():
    out = H.strip_ai_tells(
        "The survey was sent in order to measure satisfaction, due to the fact "
        "that response rates vary.", "en")
    assert "in order to" not in out
    assert "due to the fact that" not in out
    assert "to measure satisfaction" in out and "because response rates" in out


def test_the_prompt_names_the_shape_tells():
    for fragment in ("em dash", "three", "-ing"):
        assert fragment in H._REWRITE_PROMPT


# --- burstiness: never ship a rewrite flatter than the original -----------
#
# Measured on a real Turnitin report (23% AI, 45 pages, 10,921 words). Splitting
# that document's body paragraphs by what the detector flagged:
#
#     flagged paragraphs   median sentence-length CV = 0.247
#     clean paragraphs     median sentence-length CV = 0.473
#
# Mean sentence LENGTH was near-identical between the two groups (24.0 vs 24.9
# words) and so was lexical diversity (TTR 0.79 vs 0.81). The separator is
# variance — uniform sentences, not long ones.
#
# On the same document our own rewrite changed 9 flagged paragraphs and made 4
# of them FLATTER than the student's original, one going 0.583 -> 0.204. The
# loop picked the best of its own candidates and never once compared them to the
# text it was handed.

# Same words, same frozen tokens, different rhythm — so the only thing these two
# differ on is the statistic under test. (An earlier draft spelled a number out
# in one and used the numeral in the other; the frozen gate rejected it before
# the rhythm check was ever reached, which is the gate working correctly.)
FLAT = ("Nghiên cứu khảo sát nhân viên tại các khách sạn ở Hà Nội. "
        "Dữ liệu được thu thập trong khoảng thời gian là ba tháng. "
        "Phân tích được thực hiện bằng phần mềm SmartPLS mới nhất. "
        "Kết quả cho thấy các giả thuyết đều được chấp nhận.")
BURSTY = ("Nghiên cứu khảo sát nhân viên tại các khách sạn ở Hà Nội, dữ liệu "
          "được thu thập trong khoảng thời gian là ba tháng và phân tích bằng "
          "phần mềm SmartPLS mới nhất để kiểm định các giả thuyết. "
          "Kết quả cho thấy các giả thuyết đều được chấp nhận. "
          "Không có giả thuyết nào bị bác bỏ.")


def test_burstiness_separates_a_metronome_from_real_rhythm():
    flat, bursty = H.burstiness(FLAT), H.burstiness(BURSTY)
    assert flat is not None and bursty is not None
    assert bursty > flat
    # The flagged/clean boundary measured above sits between these two.
    assert flat < 0.35 < bursty


def test_burstiness_is_none_when_there_is_not_enough_text_to_judge():
    """One sentence has no rhythm. Guessing would gate real rewrites on noise."""
    assert H.burstiness("Kết quả tại Bảng 4.3 cho thấy β = 0,412.") is None
    assert H.burstiness("") is None


def test_a_flatter_rewrite_is_refused_and_the_original_kept(tmp_path, monkeypatch,
                                                            user_anchor):
    """The regression this whole check exists for: the rewrite passed every
    frozen-token gate and still handed back text MORE machine-even than the
    student wrote."""
    monkeypatch.setenv("DOTHESIS_ANCHOR_DIR", str(tmp_path))
    r = H.humanize_prose(BURSTY, language="vi", user_anchor=user_anchor,
                         llm=FakeLLM(FLAT, FLAT))
    assert r["ok"] is False
    assert r["error"] == "flatter_than_original"
    assert r["text"] == BURSTY          # the student's own text, untouched
    assert r["changed"] is False


def test_a_burstier_rewrite_is_accepted(tmp_path, monkeypatch, user_anchor):
    monkeypatch.setenv("DOTHESIS_ANCHOR_DIR", str(tmp_path))
    r = H.humanize_prose(FLAT, language="vi", user_anchor=user_anchor,
                         llm=FakeLLM(BURSTY))
    assert r["ok"] is True
    assert r["text"] == BURSTY


def test_the_guard_stays_out_of_the_way_on_short_passages(tmp_path, monkeypatch,
                                                          user_anchor):
    """Below the sentence floor there is no rhythm to compare, so the frozen
    gate remains the only judge — as it was before this check existed."""
    monkeypatch.setenv("DOTHESIS_ANCHOR_DIR", str(tmp_path))
    good = "Bảng 4.3 cho thấy β = 0,412, p = 0,003, đúng như Nguyễn (2019) đã nêu."
    r = H.humanize_prose(SRC, language="vi", user_anchor=user_anchor,
                         llm=FakeLLM(good))
    assert r["ok"] is True
    assert r["text"] == good


def test_the_reported_burstiness_travels_out_with_the_result(tmp_path, monkeypatch,
                                                             user_anchor):
    """The caller can only tune what it can see."""
    monkeypatch.setenv("DOTHESIS_ANCHOR_DIR", str(tmp_path))
    r = H.humanize_prose(FLAT, language="vi", user_anchor=user_anchor,
                         llm=FakeLLM(BURSTY))
    assert r["burstiness"]["before"] < r["burstiness"]["after"]

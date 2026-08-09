"""An imported chapter is REUSED (and at most translated), never recomposed.

Regression cover for a real import: a Vietnamese thesis whose Chapter 4 carried
17 tables came back with the EFA, KMO, correlation and regression tables gone,
captions stranded above tables that no longer existed, and PLS columns (CR/AVE)
invented for an SPSS study that never computed them. The cause was structural —
compose_all_sections read only m1..m4 and wrote all six chapters from scratch,
so the student's own results chapter was never even consulted.

No LLM: composition and translation are both stubbed.

Translation is stubbed at `m5_inline._call_llm` — the seam its own docstring
nominates — and NOT by replacing the translate entry point. Replacing the entry
point is how this file previously certified a translation path that could never
run: it swapped in a plain function, while the real `translate_selection` is a
@tool, i.e. a StructuredTool instance that is not callable. Every preserved
chapter raised TypeError into a bare `except`, and the student got their
Vietnamese Chapter 4 back inside an English thesis with the tests green.
"""
import pytest

import orchestrator.tools.m5_writing as M


_VN_RESULTS = (
    "CHƯƠNG 4: KẾT QUẢ NGHIÊN CỨU\n"
    "Bảng 4.5: Kết quả phân tích EFA — KMO = 0.812, Bartlett Sig. = 0.000\n"
    + "Kết quả phân tích nhân tố khám phá cho thấy thang đo đạt yêu cầu. " * 30
)


class _Composer:
    """Stand-in for the compose_chapter StructuredTool (a pydantic model, so its
    .invoke cannot be monkeypatched in place)."""

    def __init__(self, fn):
        self.invoke = fn


@pytest.fixture
def no_compose(monkeypatch):
    """Any call to the composer during these tests is itself the failure."""
    def _boom(*a, **kw):
        raise AssertionError("compose_chapter ran for a chapter we already had")
    monkeypatch.setattr(M, "compose_chapter", _Composer(_boom))


def _store(**m5):
    return {"m1_topic": {"research_title": "T", "language": "vi"},
            "m2_literature": {}, "m3_design": {}, "m4_analysis": {},
            "m5_writing": m5}


def test_preserved_chapter_is_reused_verbatim(no_compose, monkeypatch):
    """The student's Chapter 4 — tables and all — must survive to the export."""
    monkeypatch.setattr("agent.run_context.scoped_chapters", lambda order: ["results"])
    out = M.compose_all_sections(_store(final_sections=[
        {"chapter_name": "results", "title": "CHƯƠNG 4", "prose": _VN_RESULTS}]))
    prose = "".join(s["prose"] for s in out)
    for marker in ("Bảng 4.5", "EFA", "KMO = 0.812", "Bartlett"):
        assert marker in prose, f"{marker} lost — the chapter was recomposed"


def _stub_llm(monkeypatch, fn):
    """Patch the ONE seam the real translate path bottoms out in."""
    import orchestrator.tools.m5_inline as inline
    monkeypatch.setattr(inline, "_call_llm", fn)
    return inline


def test_preserved_chapter_is_translated_when_the_language_differs(no_compose, monkeypatch):
    """"Write it in English" means translate their chapter, not write a new one."""
    monkeypatch.setattr("agent.run_context.scoped_chapters", lambda order: ["results"])
    seen = {"chars": 0, "calls": 0}

    def _fake_llm(prompt):
        seen["calls"] += 1
        # The batch is everything between the prompt's "## Passage" fence and
        # its "## Output" fence.
        body = prompt.split("## Passage", 1)[1].split("## Output", 1)[0].strip()
        seen["chars"] += len(body)
        assert "english" in prompt.lower() or " en" in prompt
        return body.replace("KẾT QUẢ NGHIÊN CỨU", "RESULTS").replace("Bảng", "Table")

    _stub_llm(monkeypatch, _fake_llm)

    cs = _store(final_sections=[
        {"chapter_name": "results", "title": "CHƯƠNG 4", "prose": _VN_RESULTS}])
    cs["m1_topic"]["language"] = "en"
    out = M.compose_all_sections(cs)

    assert seen["calls"] >= 1
    # The WHOLE chapter goes to the translator, not a summary of it. Batching
    # splits it across calls, so compare the total (blank-line joins between
    # batches are re-added on reassembly, hence the small tolerance).
    assert seen["chars"] >= len(_VN_RESULTS.strip()) - 4 * seen["calls"]
    assert "Table 4.5" in out[0]["prose"]          # the translation is used
    assert "KMO = 0.812" in out[0]["prose"]        # numbers cross the translation


def test_translation_runs_through_the_real_tool_object(monkeypatch):
    """Guards the exact defect: the translate entry point must be CALLED the way
    it is actually shaped, not the way a stub in this file made it look."""
    calls = []
    src = "Kết quả phân tích nhân tố khám phá cho thấy thang đo đạt yêu cầu. " * 8

    def _translate(prompt):
        calls.append(prompt)
        return "TRANSLATED: exploratory factor analysis met the threshold. " * 8

    _stub_llm(monkeypatch, _translate)
    out = M._match_language(src, "results", "en")
    assert calls, "nothing reached the LLM — the translate call raised again"
    assert out.startswith("TRANSLATED")


def test_same_language_is_not_sent_to_the_translator(monkeypatch):
    """No pointless LLM call — and no risk of mangling a chapter for nothing."""
    _stub_llm(monkeypatch,
              lambda prompt: (_ for _ in ()).throw(AssertionError("translated needlessly")))
    assert M._match_language(_VN_RESULTS, "results", "vi") == _VN_RESULTS


def test_a_failed_translation_keeps_the_original(monkeypatch):
    """A chapter in the wrong language is visible and askable-about; a chapter
    replaced by an error is silent data loss."""
    _stub_llm(monkeypatch, lambda prompt: (_ for _ in ()).throw(RuntimeError("provider down")))
    assert M._match_language(_VN_RESULTS, "results", "en") == _VN_RESULTS


def test_missing_chapters_are_still_composed(monkeypatch):
    """Preservation must not stop the backfill writing chapters 1-3."""
    monkeypatch.setattr("agent.run_context.scoped_chapters", lambda order: ["intro", "results"])
    monkeypatch.setattr(
        M, "compose_chapter",
        _Composer(lambda payload: {"prose": f"COMPOSED {payload['chapter_name']}"}))
    out = M.compose_all_sections(_store(final_sections=[
        {"chapter_name": "results", "title": "CHƯƠNG 4", "prose": _VN_RESULTS}]))
    joined = "\n".join(s["prose"] for s in out)
    assert "COMPOSED intro" in joined      # missing chapter written
    assert "Bảng 4.5" in joined            # preserved chapter untouched


def test_composed_sections_carry_their_canonical_chapter_name(monkeypatch):
    """chapter_name must survive the round-trip through final_sections.

    Emitting only {title, prose} destroyed the canonical name the first time
    sections were persisted, leaving chapters_from_final_sections a title
    reverse-lookup that a Vietnamese heading never matches. `preserved` then
    came back empty and the composer rewrote chapters it already had — the
    student's untranslated originals sat alongside fresh English duplicates.
    """
    monkeypatch.setattr("agent.run_context.scoped_chapters", lambda order: ["intro", "results"])
    monkeypatch.setattr(
        M, "compose_chapter",
        _Composer(lambda payload: {"prose": f"COMPOSED {payload['chapter_name']}"}))
    out = M.compose_all_sections(_store())
    assert [s["chapter_name"] for s in out] == ["intro", "results"]

    # And the round trip closes: feeding the output back in is recognised.
    again = M.chapters_from_final_sections(out)
    assert set(again) == {"intro", "results"}

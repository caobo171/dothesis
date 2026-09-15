"""The doctor's diagnosis is a pure function — no DB, no model, no disk."""
from orchestrator.doctor import DoctorInput, UploadRecord, diagnose


def _codes(findings):
    return {f.code for f in findings}


def test_an_upload_with_text_that_never_rode_a_turn_is_unread():
    inp = DoctorInput(
        context_store={},
        uploads=[UploadRecord(upload_id="u1", filename="_Result.docx",
                              sidecar_text="| ATT_1 | 0.854 |", ever_attached=False)],
        chapter_prose={},
    )
    assert "UNREAD_UPLOAD" in _codes(diagnose(inp))


def test_an_attached_upload_is_not_flagged_unread():
    inp = DoctorInput(
        context_store={},
        uploads=[UploadRecord(upload_id="u1", filename="a.docx",
                              sidecar_text="text", ever_attached=True)],
        chapter_prose={},
    )
    assert "UNREAD_UPLOAD" not in _codes(diagnose(inp))


def test_a_confirmed_module_failing_its_dod_is_false_done():
    # M4 confirmed with results {} — exactly project 500319a8 on 2026-09-15.
    inp = DoctorInput(
        context_store={"m4_analysis": {
            "analysis_outline": {"research_design": "Định lượng"},
            "results": {},
            "confirmed_at": "2026-09-15T05:33:22+00:00"}},
        uploads=[], chapter_prose={},
    )
    findings = [f for f in diagnose(inp) if f.code == "FALSE_DONE"]
    assert findings, "M4 confirmed with empty results must be FALSE_DONE"
    assert findings[0].payload["module"] == "M4"
    assert findings[0].repair == "deterministic"
    # Raw DoD gaps stay in the payload for the loop guard...
    assert "results is empty" in findings[0].payload["gaps"]
    # ...and never reach the student. A real reply read "M3 đang được đánh dấu
    # xong nhưng còn thiếu: missing target_sample_size", which names a schema
    # key the prompt explicitly forbids showing.
    assert "results is empty" not in findings[0].detail
    assert "kết quả phân tích" in findings[0].detail


def test_an_unmapped_gap_is_dropped_rather_than_printed_raw():
    inp = DoctorInput(
        context_store={"m3_design": {"instrument": {"items": [{"text": "q"}]},
                                     "confirmed_at": "2026-09-15T05:31:59+00:00"}},
        uploads=[], chapter_prose={},
    )
    f = [x for x in diagnose(inp) if x.code == "FALSE_DONE"][0]
    assert "missing" not in f.detail, f.detail
    assert "_" not in f.detail, f.detail


def test_an_unconfirmed_module_is_not_false_done():
    # Incomplete is normal. Only a module CLAIMING to be done is a defect.
    inp = DoctorInput(
        context_store={"m4_analysis": {"results": {}}},
        uploads=[], chapter_prose={},
    )
    assert "FALSE_DONE" not in _codes(diagnose(inp))


def test_a_refusal_chapter_is_rewritten_not_merely_reported():
    inp = DoctorInput(
        context_store={}, uploads=[],
        chapter_prose={"methodology": (
            "Chưa thể biên soạn Chương 3 theo các yêu cầu đã nêu vì các trường "
            "đầu vào quyết định cấu trúc và nội dung phương pháp hiện chưa có "
            "giá trị cụ thể. Để tạo chương hoàn chỉnh, cần cung cấp paradigm, "
            "research design, analysis tool và sampling strategy.")},
    )
    findings = [f for f in diagnose(inp) if f.code == "CHAPTERS_NEED_RECOMPOSE"]
    assert findings
    assert findings[0].payload["stub"] == ["methodology"]
    # The doctor rewrites it rather than asking. Asking was tried four times:
    # the agent narrowed the export scope and claimed five chapters rewritten,
    # and after the honesty guard caught that, the student typed the exact
    # phrasing they were told to and still nothing moved.
    assert findings[0].repair == "recompose"


def test_a_healthy_project_produces_no_findings():
    assert diagnose(DoctorInput(context_store={}, uploads=[], chapter_prose={})) == []


# --- uncited chapters -------------------------------------------------------

_SOURCES = {"m2_literature": {"citation_list": [
    {"title": "A", "year": 2024}, {"title": "B", "year": 2021}]}}


def test_a_long_chapter_citing_nothing_is_flagged():
    """The uncited-bibliography failure, measured on the real export: five
    verified sources in the reference list, zero citations in 84,684 chars of
    body. Chapter 2 was written while m2_literature was still null."""
    inp = DoctorInput(
        context_store=_SOURCES, uploads=[],
        chapter_prose={"lit_review": "Tiếp thị người ảnh hưởng là… " * 200},
    )
    found = [f for f in diagnose(inp) if f.code == "CHAPTERS_NEED_RECOMPOSE"]
    assert found
    assert found[0].payload["uncited"] == ["lit_review"]
    assert found[0].repair == "recompose"


def test_a_chapter_that_cites_is_not_flagged():
    for cited in ("(Nguyen, 2024)", "(Akram và Majeed 2026)", "{{cite: X | Y | z}}"):
        inp = DoctorInput(
            context_store=_SOURCES, uploads=[],
            chapter_prose={"lit_review": ("filler " * 400) + cited},
        )
        assert not [f for f in diagnose(inp) if f.code == "CHAPTERS_NEED_RECOMPOSE"], cited


def test_no_flag_when_the_project_has_no_sources_to_cite():
    # Nothing to cite WITH is a backfill problem, not an uncited-chapter one.
    inp = DoctorInput(context_store={}, uploads=[],
                      chapter_prose={"lit_review": "filler " * 400})
    assert not [f for f in diagnose(inp) if f.code == "CHAPTERS_NEED_RECOMPOSE"]


def test_a_short_stub_is_judged_as_a_stub_not_as_uncited():
    # It still needs rewriting — but because it is a stub. Counting it as
    # "cites nothing" would tell the student their literature review lacks
    # citations when in fact it has not been written.
    inp = DoctorInput(context_store=_SOURCES, uploads=[],
                      chapter_prose={"lit_review": "Chưa viết."})
    f = [x for x in diagnose(inp) if x.code == "CHAPTERS_NEED_RECOMPOSE"][0]
    assert f.payload["stub"] == ["lit_review"]
    assert f.payload["uncited"] == []


def test_results_and_conclusion_are_not_expected_to_cite():
    inp = DoctorInput(context_store=_SOURCES, uploads=[],
                      chapter_prose={"results": "filler " * 400,
                                     "conclusion": "filler " * 400})
    assert not [f for f in diagnose(inp) if f.code == "CHAPTERS_NEED_RECOMPOSE"]


# --- results stored but unrenderable ---------------------------------------

def _uploads_with_a_results_table():
    return [UploadRecord("u1", "_Result.docx",
                         "OUTER LOADINGS\n| ATT_1 | 0.854 |\n| ATT_2 | 0.815 |\n",
                         True)]


def test_results_keyed_by_path_are_flagged_as_unrenderable():
    """The real shape that shipped a thesis with 0 tables: keyed by path, so
    detect_family returns None and render_results_tables emits nothing."""
    inp = DoctorInput(
        context_store={"m4_analysis": {"results": {
            "ATT_to_INT": {"beta": 0.257}, "EXP_to_INT": {"beta": 0.269},
            "gender_MGA": {}, "measurement_model": "not a list"}}},
        uploads=_uploads_with_a_results_table(), chapter_prose={},
    )
    found = [f for f in diagnose(inp) if f.code == "RESULTS_NOT_RENDERABLE"]
    assert found
    assert found[0].repair == "reparse"
    assert found[0].payload["filename"] == "_Result.docx"
    assert "ATT_1" in found[0].payload["text"]


def test_an_already_renderable_block_is_left_alone():
    inp = DoctorInput(
        context_store={"m4_analysis": {"results": {
            "measurement_model": [{"construct": "ATT", "ave": 0.65}],
            "discriminant_validity": {"ATT": {"DEC": 0.5}},
            "structural_model": {"r2": {"INT": 0.52}, "tool": "SmartPLS"},
        }}},
        uploads=_uploads_with_a_results_table(), chapter_prose={},
    )
    assert not [f for f in diagnose(inp) if f.code == "RESULTS_NOT_RENDERABLE"]


def test_no_reparse_without_a_source_document_to_read():
    # Re-extracting from the mangled block itself would invent column meanings.
    inp = DoctorInput(
        context_store={"m4_analysis": {"results": {"ATT_to_INT": {"beta": 0.2}}}},
        uploads=[], chapter_prose={},
    )
    assert not [f for f in diagnose(inp) if f.code == "RESULTS_NOT_RENDERABLE"]


def test_empty_results_are_not_this_checks_problem():
    inp = DoctorInput(context_store={"m4_analysis": {"results": {}}},
                      uploads=_uploads_with_a_results_table(), chapter_prose={})
    assert not [f for f in diagnose(inp) if f.code == "RESULTS_NOT_RENDERABLE"]

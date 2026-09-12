from api.app.routers.chat_v3 import (
    _chapter_export_directive,
    _direct_request,
    _honest_assistant_reply,
    _save_state_directive,
    _tool_only_reply,
)


def test_direct_vietnamese_confirmation_executes_now():
    assert _direct_request("OK, chốt mô hình và cập nhật giúp tôi")


def test_vietnamese_save_to_project_memory_executes_now():
    assert _direct_request("lưu nó vào bộ nhớ của bài luận")


def test_save_state_directive_for_questionnaire():
    directive = _save_state_directive(
        "lưu nó vào bộ nhớ của bài luận",
        ["Bộ câu hỏi khảo sát gồm EXP_1 đến DEC_5."],
    )
    assert directive is not None
    assert '"module":"M3"' in directive
    assert '"key":"instrument"' in directive


def test_save_state_directive_does_not_guess_without_artifact_context():
    assert _save_state_directive("save it", []) is None


def test_explicit_chapter_overrides_questionnaire_history():
    directive = _save_state_directive(
        "Save chapter 5",
        ["The questionnaire contains 40 items."],
    )
    assert directive is not None
    assert '"module":"M5"' in directive
    assert '"key":"final_sections"' in directive


def test_false_saved_claim_is_replaced_when_no_commit():
    reply = _honest_assistant_reply(
        "## Đã lưu bộ câu hỏi vào bài luận",
        [],
        "lưu nó vào bộ nhớ của bài luận",
    )
    assert "Chưa lưu được" in reply
    assert "Đã lưu" not in reply


def test_saved_claim_kept_when_commit_succeeded():
    reply = _honest_assistant_reply(
        "## Đã lưu bộ câu hỏi vào bài luận",
        [("commit_slice", '{"status":"ok"}')],
        "lưu nó vào bộ nhớ của bài luận",
    )
    assert reply.startswith("## Đã lưu")


def test_direct_question_executes_now():
    assert _direct_request("Đang dùng model gì thế?")


def test_plain_greeting_does_not_force_execution():
    assert not _direct_request("hello")


def test_tool_only_commit_reply_is_localized_and_specific():
    reply = _tool_only_reply(
        "Cập nhật giúp tôi", [("commit_slice", '{"status":"done"}')])
    assert reply == "Đã cập nhật nội dung vào dự án."


def test_failed_tool_is_not_reported_as_success():
    reply = _tool_only_reply(
        "Xuất tài liệu", [("export_docx", '{"error":"needs_data"}')])
    assert "chưa tạo được" in reply


def test_vietnamese_chapters_one_to_three_route_to_preresults_export():
    directive = _chapter_export_directive("viết đầy đủ chương 1,2,3")
    assert directive is not None
    assert "chapter:intro|lit_review|methodology" in directive
    assert "Do not require M4" in directive


def test_other_chapter_request_does_not_get_wrong_scope():
    assert _chapter_export_directive("viết chương 4") is None


def test_export_correction_inherits_recent_chapters_one_to_three_scope():
    directive = _chapter_export_directive(
        "Không đúng, đủ hết rồi hãy xuất ra",
        ["viết đầy đủ chương 1,2,3"],
    )
    assert directive is not None
    assert "chapter:intro|lit_review|methodology" in directive


def test_new_chapter_request_does_not_inherit_old_scope():
    assert _chapter_export_directive(
        "xuất chương 4",
        ["viết đầy đủ chương 1,2,3"],
    ) is None

from api.app.routers.chat_v3 import (
    _chapter_export_directive,
    _direct_request,
    _tool_only_reply,
)


def test_direct_vietnamese_confirmation_executes_now():
    assert _direct_request("OK, chốt mô hình và cập nhật giúp tôi")


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

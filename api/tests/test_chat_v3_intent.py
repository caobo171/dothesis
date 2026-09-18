from api.app.routers.chat_v3 import (
    _TurnUsage,
    _chapter_export_directive,
    _direct_request,
    _honest_assistant_reply,
    _save_state_directive,
    _tool_only_reply,
)


def test_turn_usage_sums_billing_but_keeps_latest_context_snapshot():
    usage = _TurnUsage()
    usage.add(input_tokens=10_000, output_tokens=500, compact_at_tokens=170_000)
    usage.add(input_tokens=12_000, output_tokens=700, compact_at_tokens=170_000)

    assert usage.total_tokens == 23_200
    assert usage.context_tokens == 12_000
    assert usage.compact_at_tokens == 170_000


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


def test_false_saved_claim_is_flagged_when_no_commit():
    reply = _honest_assistant_reply(
        "## Đã lưu bộ câu hỏi vào bài luận",
        [],
        "lưu nó vào bộ nhớ của bài luận",
    )
    assert "Chưa lưu được" in reply


def test_flagged_reply_keeps_the_explanation():
    # The student asked "why?"; the answer mentioned a save and used to be
    # replaced wholesale by the one-liner, three turns running.
    body = "Lý do: phần kết quả đã lưu ở Chương 4, nhưng bước viết chương bị lỗi grounding."
    reply = _honest_assistant_reply(body, [], "giải thích kĩ hơn lý do được không ?")
    assert reply.startswith(body)
    assert "Chưa lưu được" in reply


def test_doctor_repair_this_turn_counts_as_a_save():
    reply = "Đã lưu 101 dòng kết quả vào Chương 4."
    assert _honest_assistant_reply(reply, [], "đây chương 4", saved_this_turn=True) == reply


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


def test_internal_writing_commit_is_valid_save_evidence():
    reply = "Đã lưu bản thảo mới"
    for tool in ("rewrite_thesis", "export_docx"):
        assert _honest_assistant_reply(reply, [(tool, '{"ok":true,"persisted":true}')], "lưu ngay") == reply
        assert _honest_assistant_reply(reply, [(tool, '{"ok":false,"persisted":false,"error":"failed"}')], "lưu ngay") != reply


def test_export_does_not_invent_questionnaire_failure_or_magic_phrase():
    reply = _honest_assistant_reply("Đã lưu bản final", [("export_docx", '{"ok":true,"generated":false}')], "export lại bản final")
    assert "tải" in reply
    assert "M3" not in reply and "bộ câu hỏi" not in reply and "Hãy gửi" not in reply


def test_rewrite_claim_does_not_ask_for_destructive_retry():
    from api.app.routers.chat_v3 import _honest_rewrite_reply
    reply = _honest_rewrite_reply("Đã viết lại các chương", {"intro":"same"}, {"intro":"same"}, "viết lại")
    assert "chưa hoàn tất" in reply
    assert "ghi đè" not in reply and "Hãy gửi" not in reply


def test_fingerprint_detects_same_length_edit():
    from api.app.routers.chat_v3 import chapter_fingerprint
    class Store:
        prose = "abc"
        def load_full_context_store(self):
            return {"m5_writing":{"chapters":{"intro":{"prose":self.prose}}}}
    store = Store()
    before = chapter_fingerprint(store)
    store.prose = "xyz"
    assert before != chapter_fingerprint(store)


def test_full_rewrite_and_immediate_save_use_writing_tool():
    from api.app.routers.chat_v3 import _rewrite_directive
    assert "rewrite_thesis" in _rewrite_directive("viết lại toàn bộ các chương, ghi đè bản cũ")
    assert "rewrite_thesis" in _rewrite_directive("Lưu ngay đi", ["Giờ hãy viết lại export lại bản final 1 lần nữa đi ạ"])
    assert _rewrite_directive("Xuất file hiện có") is None


def test_saved_draft_survives_export_failure():
    text = "Đã lưu chương mới, nhưng xuất file thất bại"
    assert _honest_assistant_reply(text, [("rewrite_thesis", '{"ok":false,"persisted":true,"error":"export_failed"}')], "viết lại các chương") == text


def test_questionnaire_rewrite_is_not_routed_to_thesis_composer():
    from api.app.routers.chat_v3 import _rewrite_directive
    assert _rewrite_directive("viết lại bộ câu hỏi") is None


def test_tool_only_rewrite_distinguishes_saved_from_exported():
    reply = _tool_only_reply("viết lại các chương", [("rewrite_thesis", '{"ok":false,"persisted":true,"exported":false,"error":"export_failed"}')])
    assert "Đã lưu" in reply and "chưa tạo được file" in reply

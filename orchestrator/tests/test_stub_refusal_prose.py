"""A chapter that OPENS by refusing to be a chapter is a stub, not content.

`_is_stub_prose` caught two things: the bracketed `[Composition failed …]`
markers, and anything under 120 characters. The composer learned to decline at
length instead, in fluent Vietnamese, and that sailed through every check.

From thread c10f6d13 (2026-09-15), the methodology slot of an exported thesis —
955 characters, well clear of the floor:

    Chưa thể biên soạn Chương 3 theo các yêu cầu đã nêu vì các trường đầu vào
    quyết định cấu trúc và nội dung phương pháp hiện chưa có giá trị cụ thể.
    Để tạo chương hoàn chỉnh, cần cung cấp:
    - Paradigm: định lượng, định tính hoặc hỗn hợp.
    …

It went into `final_sections`, `chapter_prose` put it in the docx because
`chapters` had no methodology to outrank it, and the student was never told
Chapter 3 was missing. It also prints internal schema names (Paradigm, Scale
items, Purposive criteria) as student-facing prose.

Anchored to the OPENING, not to the whole body: a real methodology chapter can
discuss what could not be measured without being a refusal. A chapter whose
first sentence declines to write it is a refusal at any length.
"""
from orchestrator.tools.m5_writing import _is_stub_prose

REAL_REFUSAL = (
    "Chưa thể biên soạn Chương 3 theo các yêu cầu đã nêu vì các trường đầu vào "
    "quyết định cấu trúc và nội dung phương pháp hiện chưa có giá trị cụ thể. "
    "Để tạo chương hoàn chỉnh, cần cung cấp:\n\n"
    "- Paradigm: định lượng, định tính hoặc hỗn hợp.\n"
    "- Research design: thiết kế nghiên cứu cụ thể.\n"
    "- Analysis tool: công cụ và phương pháp phân tích.\n"
    "- Sampling strategy: chiến lược chọn mẫu.\n"
    "- Target sample size: cỡ mẫu mục tiêu.\n\n"
    "Việc tự bổ sung các giá trị trên sẽ làm phát sinh thiết kế, cỡ mẫu, thang "
    "đo và phương pháp phân tích không có trong dữ liệu đầu vào, trái với yêu "
    "cầu không được bịa đặt thông tin."
)


def test_the_chapter_3_refusal_that_shipped_is_a_stub():
    # The fixture abridges the real 955-char bullet list, but must stay well
    # clear of the old 120-char floor — that floor is what it defeated.
    assert len(REAL_REFUSAL) > 500
    assert _is_stub_prose(REAL_REFUSAL)


def test_english_refusal_is_a_stub():
    assert _is_stub_prose(
        "I cannot write this chapter because the required design fields are "
        "not yet available. To produce a complete chapter, please provide the "
        "paradigm, the sampling strategy and the target sample size, none of "
        "which can be inferred from the evidence currently in the project."
    )


def test_a_real_chapter_that_merely_discusses_limits_is_not_a_stub():
    # The signal is a chapter that declines to exist, not one that reports a
    # limitation. This opens as a chapter and must survive.
    assert not _is_stub_prose(
        "## 3.1 Thiết kế nghiên cứu\n\nNghiên cứu sử dụng thiết kế định lượng "
        "với khảo sát cắt ngang và thang đo Likert năm mức. Mẫu được chọn theo "
        "phương pháp thuận tiện với cỡ mẫu mục tiêu 300 quan sát.\n\n"
        "## 3.2 Hạn chế\n\nMột số biến không thể đo lường trực tiếp trong phạm "
        "vi nghiên cứu này, do đó chưa thể kết luận về quan hệ nhân quả."
    )


def test_existing_behaviour_is_unchanged():
    assert _is_stub_prose("")
    assert _is_stub_prose("[Composition failed — please retry]")
    assert _is_stub_prose("too short")
    assert not _is_stub_prose(
        "## 3.1 Thiết kế nghiên cứu\n\nNghiên cứu sử dụng thiết kế định lượng "
        "với khảo sát cắt ngang, thang đo Likert năm mức và phân tích PLS-SEM "
        "trên phần mềm SmartPLS 4 với cỡ mẫu 320 quan sát hợp lệ."
    )

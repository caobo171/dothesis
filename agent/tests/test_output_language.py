"""The language generated prose is WRITTEN in.

Distinct from the language of the student's existing work. A student can upload
a Vietnamese draft and ask for the thesis in English — reconstructing their own
work in Vietnamese is right, and writing the new chapters in Vietnamese is not.

Reported from a live project: `m1_topic.language` was None, the three sites that
resolved it disagreed (two defaulted "vi", one "en"), and the student's stated
"viết bằng tiếng Anh" never became durable state.
"""
from agent.tools.writing import resolve_output_language


def test_an_explicit_project_language_wins():
    cs = {"m1_topic": {"language": "en"},
          "m4_analysis": {"analysis_results": "Toàn bộ luận văn bằng tiếng Việt."}}
    assert resolve_output_language(cs) == "en"


def test_unset_language_reads_the_students_own_work():
    """Never a blind default: with nothing stated, mirror what they wrote."""
    english = ("The survey instrument was distributed to hotel employees across "
               "the region and 218 valid responses were retained for analysis "
               "using partial least squares structural equation modelling.")
    assert resolve_output_language({"m4_analysis": {"analysis_results": english}}) == "en"

    vietnamese = ("Nghiên cứu sử dụng phương pháp chọn mẫu thuận tiện với 303 "
                  "đáp viên hợp lệ tại Thành phố Hồ Chí Minh, dữ liệu được xử lý "
                  "bằng phần mềm SPSS.")
    assert resolve_output_language({"m4_analysis": {"analysis_results": vietnamese}}) == "vi"


def test_falls_back_to_vietnamese_when_there_is_nothing_to_read():
    assert resolve_output_language({}) == "vi"
    assert resolve_output_language({"m1_topic": {}}) == "vi"


def test_a_malformed_slice_does_not_raise():
    """m1_topic has been seen as a non-dict; resolving language must not be the
    thing that takes an export down."""
    assert resolve_output_language({"m1_topic": "oops"}) == "vi"
    assert resolve_output_language(None) == "vi"

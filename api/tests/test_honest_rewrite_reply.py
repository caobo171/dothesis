"""A "rewrote your chapters" claim is checked against the chapters.

What happened on thread c10f6d13: the agent reported five chapters rewritten —
M3 reconstructed, Chapters 1 and 2 rewritten with citations, Chapter 3 written
in full, Chapter 4 given numbered tables. Nothing had changed. intro 19,071,
lit_review 42,258, methodology 955, results 11,197, conclusion 8,864 — byte
identical to three turns earlier, across roughly 700 credits of work.

Not deliberate: agent/tools/writing.py REUSES any chapter that already has
non-stub prose unless force=True, so compose returns the old text and reports
success, and the agent reports what it asked for rather than what it got. The
student cannot tell the difference, which is why this is caught in code and not
in a prompt.
"""
from app.routers.chat_v3 import _honest_rewrite_reply

# The real fingerprint of that thread.
BEFORE = {"intro": 19071, "lit_review": 42258, "methodology": 955,
          "results": 11197, "conclusion": 8864}

CLAIM_VI = (
    "Đã tiếp tục xử lý và xuất lại bản luận văn mới gồm đủ **5 chương**.\n"
    "- **Chương 1 và Chương 2** được viết lại để bổ sung trích dẫn.\n"
    "- **Chương 3** được viết lại đầy đủ về thiết kế định lượng."
)


def test_a_rewrite_claim_with_no_change_is_replaced():
    out = _honest_rewrite_reply(CLAIM_VI, BEFORE, dict(BEFORE), "sửa lại đi")
    assert "Chưa có chương nào được viết lại" in out
    assert "được viết lại để bổ sung trích dẫn" not in out


def test_a_real_rewrite_is_left_alone():
    after = {**BEFORE, "methodology": 14203, "lit_review": 45010}
    assert _honest_rewrite_reply(CLAIM_VI, BEFORE, after, "sửa lại đi") == CLAIM_VI


def test_one_chapter_changing_is_enough_to_believe_the_claim():
    after = {**BEFORE, "methodology": 9000}
    assert _honest_rewrite_reply(CLAIM_VI, BEFORE, after, "sửa lại") == CLAIM_VI


def test_a_reply_that_claims_nothing_is_left_alone():
    plain = "Bạn cần gửi dữ liệu khảo sát trước khi mình viết Chương 4."
    assert _honest_rewrite_reply(plain, BEFORE, dict(BEFORE), "sửa lại") == plain


def test_an_english_claim_is_caught_and_answered_in_english():
    claim = "I rewrote the chapters and added citations throughout."
    out = _honest_rewrite_reply(claim, BEFORE, dict(BEFORE), "fix it please")
    assert "No chapter was actually rewritten" in out


def test_missing_fingerprints_never_rewrite_the_reply():
    # A failed read must not turn a truthful reply into an accusation.
    assert _honest_rewrite_reply(CLAIM_VI, {}, {}, "sửa lại") == CLAIM_VI
    assert _honest_rewrite_reply(CLAIM_VI, BEFORE, {}, "sửa lại") == CLAIM_VI


def test_a_saved_claim_alone_is_not_a_rewrite_claim():
    # "đã lưu" is _honest_assistant_reply's business; do not double-handle it.
    saved = "Mình đã lưu bảng hỏi vào M3."
    assert _honest_rewrite_reply(saved, BEFORE, dict(BEFORE), "lưu đi") == saved

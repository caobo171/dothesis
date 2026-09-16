"""Student-facing explanations for deterministic checks, without losing evidence."""
from __future__ import annotations


def review_language(context: dict) -> str:
    language = str((context.get("m1_topic") or {}).get("language") or "vi").lower()
    return "vi" if language in {"vi", "vn", "vietnamese", "tiếng việt"} or language.startswith("vi-") else "en"


def present_coherence_finding(finding: dict, language: str = "vi") -> dict:
    """Translate by stable check code; never reinterpret a scientific result."""
    code = finding.get("check", "")
    location = finding.get("location") or {}
    observed = finding.get("observed") or {}
    observed = observed if isinstance(observed, dict) else {"value": observed}
    hypothesis = location.get("hypothesis") or observed.get("hypothesis") or "Giả thuyết"
    sentence = location.get("sentence") or observed.get("sentence")
    chapter = location.get("chapter") or "results"
    chapter = {"discussion": "conclusion", "framework": "lit_review"}.get(chapter, chapter)
    issue = finding.get("message", "")
    fix = "Compare the quoted passage with the saved analysis and correct the discrepancy."
    question = None
    if language == "vi":
        fix = "Đối chiếu câu được trích với kết quả đã lưu và sửa phần chưa khớp."
        if code == "coherence.undiscussed_hypothesis":
            issue = f"Chưa tìm thấy phần trình bày kết quả của {hypothesis} trong chương Kết quả hoặc Kết luận."
            fix = "Kiểm tra đoạn đã viết bằng tên quan hệ. Nếu còn thiếu, bổ sung mã giả thuyết, kết quả và ý nghĩa; không tự thêm số liệu."
            question = f"Kết quả của {hypothesis} được giải thích ở đoạn nào và có ý nghĩa gì đối với nghiên cứu?"
        elif code in {"coherence.number_mismatch", "coherence.number_mismatch_weak"}:
            metric = observed.get("metric") or "chỉ số"
            value, expected = observed.get("value"), finding.get("expected")
            issue = f"{hypothesis}: {metric} trong bài chưa khớp với kết quả phân tích đã lưu."
            if value is not None and expected is not None and metric != "p":
                issue += f" Bài đang ghi {value}; kết quả đối chiếu là {expected}."
            fix = "Kiểm tra đúng giả thuyết và loại phân tích, rồi sửa số liệu trong câu. Không sửa kết quả phân tích chỉ để khớp với bài viết."
            if metric == "p":
                fix = "Đối chiếu cả giá trị p và dấu <, > hoặc = với báo cáo nguồn. Không biến một ngưỡng được báo cáo thành giá trị p chính xác."
            question = f"Số liệu đang trích cho {hypothesis} thuộc kết quả chính hay một phân tích bổ sung?"
        elif code == "coherence.unsupported_diagnostic_claim":
            metric = observed.get("metric") or location.get("item") or "chỉ số kiểm định"
            metric = {"rho_a": "rho_A", "htmt": "HTMT", "loadings": "hệ số tải ngoài",
                      "reliability": "độ tin cậy", "validity": "giá trị thang đo"}.get(metric, metric)
            issue = f"Bài kết luận {metric} đạt yêu cầu nhưng dữ liệu phân tích hiện có chưa đủ bằng chứng để xác nhận."
            fix = "Đối chiếu bảng kết quả nguồn và bổ sung giá trị thực tế nếu có. Nếu chưa có, nêu rõ chưa đủ thông tin; không mặc định là đạt."
            question = f"Bảng hoặc giá trị nào trong báo cáo nguồn chứng minh kết luận về {metric}?"
        elif code == "grounding.construct_alias_conflict":
            construct = location.get("construct") or "Biến"
            issue = f"{construct} đang được gọi bằng tên của một biến khác trong thiết kế nghiên cứu."
            fix = f"Dùng đúng định nghĩa đã lưu: {construct} — {finding.get('expected')}. Kiểm tra lại phần giải thích liên quan."
        elif code == "coherence.ambiguous_path_attribution":
            issue = "Chưa xác định chắc chắn số liệu trong câu thuộc giả thuyết hoặc loại phân tích nào."
            fix = "Tách riêng từng quan hệ, ghi mã giả thuyết và phân biệt kết quả chính với so sánh nhóm hoặc tương tác. Đây là mục chưa kiểm tra được, không phải kết luận số liệu sai."
            question = "Câu này đang báo cáo hệ số chính, hệ số tương tác hay chênh lệch giữa các nhóm?"
        elif code in {"coherence.direction_prose", "coherence.direction_m3_m4"}:
            issue = f"Chiều quan hệ được mô tả cho {hypothesis} chưa khớp với dấu của hệ số trong kết quả đã lưu."
            fix = "Đối chiếu dấu của hệ số và chiều giả thuyết ban đầu. Điều chỉnh phần diễn giải hoặc kết luận ủng hộ; không đổi giả thuyết chỉ để làm kết quả đạt."
        elif code == "coherence.decision_prose":
            issue = f"Kết luận được hoặc không được ủng hộ của {hypothesis} chưa khớp với kết quả đã lưu."
            fix = "Đối chiếu kết luận kiểm định của đúng giả thuyết rồi sửa phần diễn giải cho thống nhất."
        elif code == "xtable.hypothesis_coverage":
            issue = f"Chưa có kết quả kiểm định được lưu cho {hypothesis}."
            fix = "Bổ sung kết quả từ phân tích thực tế, hoặc nêu rõ giả thuyết chưa được kiểm định. Không tự tạo hệ số hay kết luận."
        elif code == "coherence.orphan_result":
            issue = f"Kết quả {hypothesis} chưa nối được với giả thuyết trong thiết kế nghiên cứu."
            fix = "Kiểm tra mã giả thuyết; nếu đây là phân tích bổ sung, ghi rõ vai trò đó thay vì gán vào giả thuyết chính."
        elif code == "traceability.no_gaps":
            issue = "Chưa lưu khoảng trống nghiên cứu để đối chiếu cơ sở xây dựng các giả thuyết."
            fix = "Bổ sung khoảng trống nghiên cứu có căn cứ từ tổng quan tài liệu và chỉ rõ giả thuyết nào giải quyết từng khoảng trống."
        elif code == "traceability.hypothesis_gap":
            issue = f"Chưa nhận diện rõ mối liên hệ giữa {hypothesis} và khoảng trống nghiên cứu đã nêu."
            fix = "Kiểm tra và giải thích rõ cơ sở xây dựng giả thuyết từ tài liệu; đây là cảnh báo đối chiếu từ khóa, cần bạn xem lại."
        elif code == "traceability.discussion_uncited":
            issue = f"Phần thảo luận {hypothesis} chưa dẫn tài liệu để đối chiếu với nghiên cứu trước."
            fix = "Nếu đang so sánh với nghiên cứu trước, thêm nguồn đã xác minh và giải thích điểm giống hoặc khác. Không thêm citation chỉ để hết cảnh báo."

    # Decision: retain machine-readable evidence for highlighting and follow-up;
    # presentation must not throw away the exact passage the validator checked.
    return {
        "code": code, "issue": issue, "fix": fix, "chapter": chapter,
        "severity": finding.get("severity", "soft"), "hypothesis": location.get("hypothesis"),
        "evidence": {"sentence": sentence, "observed": observed, "expected": finding.get("expected")},
        "question": question,
    }

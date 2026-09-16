# Kiểm tra cảnh báo thiếu thảo luận giả thuyết

Project: `500319a8-5a06-47bf-bfd8-3ef921b36184`. Đọc dữ liệu lưu trong DB ngày 16/09/2026; không sửa nội dung project.

## Kết quả đối chiếu

Review tái hiện đúng 9 cảnh báo `coherence.undiscussed_hypothesis`, H1–H9. Chương 4 và 5 không viết nhãn H1–H9 nhưng đã trình bày các quan hệ tương ứng bằng mã biến và mũi tên. Vì vậy, 9 cảnh báo này không chứng minh phần diễn giải bị bỏ trống. Bộ kiểm tra chỉ nhận nhãn giả thuyết nên bỏ sót nội dung có thật.

“Câu hỏi cho tác giả” chỉ lặp lại tối đa 8 findings dưới dạng câu hỏi; không phải một lượt kiểm tra độc lập hay 8 lỗi mới.

| Giả thuyết | Quan hệ trong thiết kế đã lưu | β | t |
|---|---|---:|---:|
| H1 | Thái độ đối với du lịch nội địa → Ý định du lịch | 0,257 | 7,490 |
| H2 | Chuyên môn người ảnh hưởng → Ý định du lịch | 0,269 | 6,892 |
| H3 | Kết nối cảm xúc → Ý định du lịch | 0,382 | 10,441 |
| H4 | Khả năng truyền cảm hứng → Ý định du lịch | 0,288 | 7,594 |
| H5 | Sự tương đồng → Ý định du lịch | 0,260 | 7,330 |
| H6 | Độ tin cậy → Ý định du lịch | 0,318 | 8,994 |
| H7 | Ý định du lịch → Quyết định du lịch | 0,606 | 13,367 |
| H8 | Thu nhập → Quyết định du lịch | 0,193 | 4,705 |
| H9 | Thu nhập × Ý định du lịch → Quyết định du lịch | 0,446 | 8,927 |

Nguồn số liệu: `analysis_results` lưu từ báo cáo SmartPLS/SPSS người dùng cung cấp. Không phải kết quả tính lại từ dữ liệu khảo sát thô trong lần kiểm tra này. Các hàng trên lưu p dưới dạng `0.000`; khi viết nên trình bày `p < 0,001`, không diễn giải là xác suất bằng 0.

## Những vấn đề nội dung thực sự thấy được

1. M3 gọi ATT là “Thái độ đối với du lịch nội địa”, nhưng chương 4 chuyển thành “thái độ đối với người ảnh hưởng”. Đây là thay đổi nghĩa biến.
2. M3 gọi EXP là “Chuyên môn người ảnh hưởng”, nhưng chương 5 gọi là “trải nghiệm”. Cần thống nhất theo định nghĩa và thang đo đã chốt.
3. Chương 4 nói chưa có rho_A, tải ngoài và số liệu HTMT cụ thể; chương 5 khẳng định các chỉ số này đều đạt. Hai chương đang mâu thuẫn. Cần đối chiếu báo cáo gốc trước khi giữ kết luận đạt; lần audit này chưa xác minh các hình nguồn.
4. M4 còn giữ bản `results` cũ song song với `analysis_results`, và phần diễn giải cũ nói “chưa có kết quả”. Hàm dựng ngữ cảnh dùng `setdefault` khiến `results` cũ thắng bản canonical mới. Đây là lỗi cung cấp dữ liệu cho engine viết.

## Ví dụ diễn giải phù hợp

**H1:** Kết quả được lưu cho thấy thái độ đối với du lịch nội địa có quan hệ thuận chiều với ý định du lịch (β = 0,257; t = 7,490; p < 0,001), phù hợp với giả thuyết H1. Trong phạm vi mẫu khảo sát, thái độ tích cực hơn gắn với ý định du lịch cao hơn. Do nghiên cứu sử dụng thiết kế cắt ngang, kết quả này chưa đủ để khẳng định quan hệ nhân quả.

**H2:** Chuyên môn cảm nhận của người ảnh hưởng có quan hệ thuận chiều với ý định du lịch (β = 0,269; t = 6,892; p < 0,001), phù hợp với giả thuyết H2. Kết quả nên được diễn giải theo khái niệm chuyên môn của người ảnh hưởng, không đổi thành trải nghiệm của du khách.

**H9:** Hệ số tương tác giữa thu nhập và ý định du lịch mang dấu dương (β = 0,446; t = 8,927; p < 0,001), cung cấp bằng chứng phù hợp với giả thuyết điều tiết H9. Cần đối chiếu cách mã hóa thu nhập và phân tích độ dốc đơn trước khi kết luận cụ thể nhóm thu nhập nào có quan hệ ý định–quyết định mạnh hơn.

Một đoạn hoàn chỉnh nên nối mã giả thuyết, tên biến đúng, hệ số và mức ý nghĩa, kết luận được/không được ủng hộ, ý nghĩa trong bối cảnh nghiên cứu, và giới hạn bằng chứng. Phần đối chiếu nghiên cứu trước chỉ được bổ sung từ tài liệu đã kiểm chứng, không tự tạo citation.

## Bản sửa và giới hạn

- Bộ kiểm tra nhận thêm đường dẫn đúng chiều đã đăng ký trong M3, kể cả M3 lưu `path` và graph dùng tên hiển thị. Không dùng đuôi của đường dẫn tương tác để tính là tác động trực tiếp.
- Đối chiếu read-only trên chính project sau sửa: 9 cảnh báo thiếu thảo luận → 0. Đây không phải chứng nhận toàn bộ bài đúng; kiểm tra số liệu theo đường dẫn không có mã H vẫn chưa được mở rộng trong bản sửa coverage này.
- Ngữ cảnh viết ưu tiên `analysis_results` hiện hành. Đối chiếu thực tế xác nhận bảng đúng được chọn và danh sách H1–H9 có đúng định nghĩa ATT/EXP đã lưu.
- Nội dung chương và dữ liệu nghiên cứu trong DB chưa bị sửa hoặc tái sinh. Những mâu thuẫn học thuật đã nêu vẫn cần đối chiếu báo cáo nguồn trước khi chỉnh bài.

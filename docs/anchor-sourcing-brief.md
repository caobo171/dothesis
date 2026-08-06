# Brief cho Claude-trên-trình-duyệt: tìm nguồn văn mẫu (anchor)

Copy toàn bộ phần trong khung dưới và dán cho Claude có quyền duyệt web.
Chỉ TÌM và TRA CỨU những thứ đã tồn tại — không liên hệ ai, không đăng bài,
không hỏi xin.

---

## Bối cảnh cần hiểu trước khi tìm (phần quan trọng nhất)

Tôi cần các đoạn văn học thuật tiếng Việt (~200–400 chữ) để làm **mẫu văn phong**
cho một công cụ viết lại. Điều kiện quyết định, và nó ngược với trực giác tìm
kiếm thông thường:

**Văn càng dễ tìm thấy trên web thì càng VÔ DỤNG với tôi.**

Lý do: các mô hình ngôn ngữ được huấn luyện trên web. Một đoạn văn đã nằm trong
tập huấn luyện thì mô hình bắt chước nó sẽ cho ra kết quả *giống máy hơn*, không
phải ít hơn. Điều này đã được đo: dùng văn bản web (Wikipedia, blog, tài liệu tải
tự do) làm mẫu khiến điểm phát hiện AI **tăng lên** trên toàn bộ mẫu thử.

Nên nhiệm vụ của bạn KHÔNG phải là gom được càng nhiều văn càng tốt. Nhiệm vụ là
**lập danh mục nguồn, kèm đánh giá khả năng nguồn đó đã bị thu thập vào tập huấn
luyện hay chưa**.

## Tiêu chí

Một đoạn/nguồn ĐẠT khi:
- Tiếng Việt, văn phong học thuật (luận văn, luận án, bài tạp chí khoa học)
- Xuất bản/nộp **trước năm 2022** (trước khi ChatGPT phổ biến) — phải xác minh được năm
- Thuộc một trong các phần: cơ sở lý thuyết, phương pháp nghiên cứu, kết quả
  nghiên cứu định lượng, bàn luận
- Ưu tiên ngành: kinh tế, quản trị kinh doanh, marketing, du lịch – khách sạn,
  quản trị nhân lực

LOẠI ngay khi:
- Sau 2022 hoặc không xác định được năm
- Là bài báo mạng, blog, tin tức, nội dung SEO, Wikipedia
- Là bản dịch máy hoặc văn có dấu hiệu do AI viết
- Nằm trên các site tổng hợp tài liệu lớn: `123doc`, `tailieu.vn`, `scribd`,
  `academia.edu`, `researchgate` — đây là nhóm gần như chắc chắn đã bị crawl

## Phép thử bắt buộc: đoạn này đã bị index chưa

Với **mỗi** đoạn ứng viên, làm bước này và ghi lại kết quả:

1. Lấy một câu đặc trưng trong đoạn (12–20 chữ, có danh từ riêng hoặc con số càng tốt)
2. Tìm Google với câu đó **đặt trong ngoặc kép**
3. Ghi lại:
   - **0 kết quả** → `chưa index` → giá trị CAO
   - **chỉ trả về đúng file gốc** → `index nhẹ` → giá trị TRUNG BÌNH
   - **nhiều site đăng lại, có bản xem trước toàn văn** → `đã index` → **LOẠI**

Đây là phép xấp xỉ tốt nhất mà trình duyệt làm được: nằm trong chỉ mục tìm kiếm
tương quan rất mạnh với việc nằm trong dữ liệu huấn luyện.

Dấu hiệu phụ, cũng ghi lại:
- PDF là **bản scan ảnh** (không bôi đen chọn chữ được) → khả năng cao chưa vào
  corpus văn bản → giá trị CAO
- PDF có lớp text chọn được, tải tự do → giá trị thấp hơn

## Việc cần làm

### Nhiệm vụ 1 — Danh mục nguồn (ưu tiên cao nhất)

Lập bảng các nguồn có kho luận văn/tạp chí tiếng Việt **trước 2022**, mỗi dòng gồm:

| Cột | Nội dung |
|---|---|
| Tên nguồn | thư viện số / tạp chí / khoa |
| URL | link trang danh mục |
| Loại | luận văn ThS / luận án TS / tạp chí / kỷ yếu |
| Khoảng năm | ví dụ 2012–2021 |
| Ngành | |
| Truy cập | tải tự do / cần đăng nhập / chỉ xem / chỉ có bản in |
| Dạng file | text-PDF / scan ảnh / không có file |
| Đã index? | kết quả phép thử ngoặc kép ở trên |
| Giấy phép | ghi đúng câu ghi trên trang, không suy đoán |

Nguồn nên rà:
- Trang thư viện số / "luận văn" của các trường: Kinh tế Quốc dân, Ngoại thương,
  ĐHQG Hà Nội, ĐHQG TP.HCM, Kinh tế TP.HCM, Thương mại, Ngân hàng, Đà Nẵng, Huế, Cần Thơ
- Tạp chí khoa học của chính các trường trên (thường có mục "Số đã xuất bản")
- Kỷ yếu hội thảo khoa học cấp trường/khoa trước 2022
- Thư viện Quốc gia Việt Nam — mục luận án
- Kỷ yếu NCKH sinh viên

**Ghi rõ nguồn nào CHỈ CÓ BẢN IN hoặc chỉ có bản scan ảnh.** Đó là những dòng giá
trị nhất trong bảng, dù không tải được ngay.

### Nhiệm vụ 2 — Đoạn ứng viên

Với các nguồn truy cập hợp pháp được, trích tối đa **20 đoạn** (~200–400 chữ),
mỗi đoạn kèm:

- Trích dẫn nguồn đầy đủ (tác giả, tên, trường/tạp chí, năm)
- URL
- Loại phần (cơ sở lý thuyết / phương pháp / kết quả / bàn luận)
- Kết quả phép thử "đã index chưa"
- Ghi chú giấy phép

Chép nguyên văn, không sửa, không tóm tắt.

## Truy vấn gợi ý

```
"luận văn thạc sĩ" "sự hài lòng" 2018..2021 site:.edu.vn
"tạp chí khoa học" "kết quả nghiên cứu" "Cronbach" site:.edu.vn
thư viện số luận án tiến sĩ quản trị kinh doanh
kỷ yếu hội thảo khoa học 2019 quản trị -123doc -tailieu
"phân tích nhân tố khám phá" luận văn 2017..2021
"mô hình cấu trúc tuyến tính" OR "SmartPLS" luận văn -site:123doc.net
```

Với mỗi truy vấn, thêm biến thể `filetype:pdf` và biến thể không có nó — trang
danh mục thường giá trị hơn file lẻ.

## Không được làm

- Không vượt tường đăng nhập, không dùng tài khoản, không phá paywall
- Không nhắn tin, gửi email, đăng bài hay liên hệ bất kỳ ai
- Không thu thập thông tin cá nhân ngoài tên tác giả đã công bố công khai
- Không tải hàng loạt; chỉ lấy đủ số đoạn nêu trên
- Không đoán giấy phép — chép đúng chữ ghi trên trang, không có thì ghi "không rõ"

## Kết quả trả về

1. Bảng danh mục nguồn (Nhiệm vụ 1), sắp xếp theo **giá trị anchor giảm dần** —
   tiêu chí xếp hạng là *càng ít bị index càng cao*, không phải càng dễ tải càng cao
2. Các đoạn ứng viên (Nhiệm vụ 2), kèm đầy đủ thông tin trên
3. Một mục ngắn: nguồn nào chỉ có bản in / bản scan và cần đến tận nơi hoặc OCR

Nếu phần lớn thứ tìm được đều rơi vào nhóm "đã index", hãy nói thẳng điều đó —
đó là một phát hiện có ích, không phải thất bại.

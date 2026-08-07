# Prompt tìm anchor — dán thẳng vào Claude Code

Khác với `anchor-sourcing-brief.md` (viết cho Claude trên trình duyệt, chỉ tra
cứu), prompt này viết cho Claude Code: nó tự tải file, tự trích văn bản, tự ghi
vào `skills/dothesis-humanize/references/anchors/` và tự cập nhật manifest.

Copy toàn bộ phần trong khung dưới.

---

## Nhiệm vụ

Tìm và cài đặt các đoạn văn mẫu (anchor) tiếng Việt cho công cụ humanize của
DoThesis, ghi vào `skills/dothesis-humanize/references/anchors/`.

Đọc trước 3 file này rồi mới bắt đầu — chúng chứa toàn bộ ràng buộc:
- `skills/dothesis-humanize/references/anchors/README.md`
- `skills/dothesis-humanize/references/anchors/PROVENANCE.md`
- `docs/anchor-sourcing-brief.md`

## Điều quyết định thành bại

Anchor phải nằm **NGOÀI phân phối huấn luyện của LLM**.

Văn càng dễ tìm trên web thì càng vô dụng. Mô hình được huấn luyện trên web; bắt
chước một đoạn đã nằm trong tập huấn luyện sẽ kéo bản viết lại **về đúng** vùng
phân phối mà máy dò được huấn luyện để nhận ra. Đã đo: dùng văn web
(Wikipedia, blog, tài liệu tải tự do) làm mẫu khiến điểm AI **TĂNG** trên toàn bộ
mẫu thử — tệ hơn là không làm gì.

Đo trực tiếp trên sản phẩm ngày 2026-08-07: một bản viết lại đã đẩy điểm Turnitin
từ 23% lên 30%. Trên chính những đoạn bị viết lại, tỷ lệ bị gắn cờ tăng từ 16,4%
lên 36,6%. Nguyên nhân: bản viết lại đã "làm đẹp" những chỗ vụng của người thật
thành cụm từ học thuật chuẩn mực — mà cụm chuẩn mực chính là thứ mô hình sinh ra.

**Hệ quả cho việc chọn đoạn:** ưu tiên đoạn có nhịp không đều, câu dài ngắn xen
kẽ, cách diễn đạt hơi vụng, dấu câu không nhất quán. **Những chỗ vụng đó CHÍNH LÀ
giá trị.** Tuyệt đối không sửa, không làm mượt, không tóm tắt. Một đoạn văn trơn
tru hoàn hảo là một anchor vô dụng.

## ⚠️ Bài học bắt buộc đọc từ đợt tìm trước

Đợt trước có 5 nguồn được đánh giá "CAO / chưa bị index". Kiểm tra lại thì
**2 sai hoàn toàn, 1 phải loại vì lý do khác**:

| Nguồn | Chuyện gì đã xảy ra |
|---|---|
| Số 143/2020 | Bản PDF đầy đủ nằm trên ResearchGate |
| Số 142/2020 | Câu thử xuất hiện nguyên văn trên một site tổng hợp tài liệu |
| Số 140/2020 | Bài này sạch, nhưng chính nhóm tác giả đó có bài gần trùng nội dung đã nằm trên tapchicongthuong.vn |

**Điểm mấu chốt: câu thử THỨ NHẤT đã lọt ở cả hai trường hợp sai.** Chỉ thử một
câu là không đủ. Đây là lỗi phải tránh lặp lại.

## Phép thử bắt buộc — làm đủ 3 bước cho MỖI nguồn

1. **Thử câu thứ nhất.** Lấy một câu đặc trưng (12–20 chữ, có số hoặc danh từ
   riêng càng tốt), tìm trong ngoặc kép.
2. **Thử câu thứ hai, ở một phần khác của bài.** Bắt buộc. Không được bỏ.
3. **Tìm theo tên bài + tên tác giả.** Bước này để phát hiện bản sao trên
   ResearchGate / academia.edu / 123doc / tailieu.vn / studocu / scribd và các
   site tổng hợp khác.

Ghi lại kết quả từng bước. Chỉ nhận nguồn khi **cả ba** bước đều sạch.

Thêm một bước nữa: tìm tên nhóm tác giả kèm chủ đề, xem họ có bài gần trùng đã bị
index không. Nếu có → loại, vì giọng văn đó đã nằm trong corpus.

## Tiêu chí

ĐẠT khi:
- Tiếng Việt, văn học thuật thật (tạp chí khoa học, luận văn, luận án)
- Công bố **trước 2022**, phải xác minh được năm (đối chiếu ngày nhận bài, ngày
  duyệt đăng, hoặc CreationDate trong metadata PDF)
- Ngành: kinh tế, quản trị kinh doanh, marketing, du lịch – khách sạn, quản trị
  nhân lực, tài chính – ngân hàng
- Là văn xuôi liền mạch, không phải bảng biểu hay danh mục

LOẠI ngay:
- Sau 2022, hoặc không xác định được năm
- Báo mạng, blog, tin tức, nội dung SEO, Wikipedia
- Nằm trên 123doc, tailieu.vn, scribd, academia.edu, ResearchGate, studocu
- Có dấu hiệu do AI viết hoặc dịch máy
- **Sai register**: văn kiến nghị chính sách, văn nghị luận, văn hành chính. Loại
  kể cả khi phép thử index sạch — loại register này bão hòa trên web, chính từ
  vựng của nó đã bị gắn cờ.

## Các slot còn thiếu (ưu tiên theo thứ tự)

Hiện đã có 4 anchor, nhưng **3 trong 4 lấy từ cùng một bài báo** — đó là điểm yếu
lớn nhất hiện nay. Ưu tiên số một là **đa dạng nguồn**, không phải thêm số lượng.

| Ưu tiên | Slot | Ghi chú |
|---|---|---|
| 1 | Thay `vi_tongquan_nghiencuu` bằng bài của tác giả KHÁC | đang trùng nguồn với 2 anchor kia |
| 2 | Thay `vi_banluan_hoiquy` bằng bài của tác giả KHÁC | như trên |
| 3 | `vi_coso_lythuyet` — cơ sở lý thuyết, định nghĩa khái niệm | chưa có |
| 4 | `vi_ketluan_hamy` — kết luận và hàm ý quản trị | chưa có |
| 5 | `vi_thongke_motả` — thống kê mô tả mẫu nghiên cứu | chưa có |

Mỗi anchor **250–400 chữ**. Mỗi anchor phải đến từ **một bài khác nhau**.

## Bẫy khi trích xuất — đọc kỹ, đây là chỗ dễ hỏng ngầm

Tạp chí Việt Nam thường dàn **2 cột căn đều**, có bảng chèn giữa. Hai kiểu hỏng
mà mắt thường không thấy:

1. `pdftotext` thường **trộn hai cột vào cùng một dòng**, nối hai nửa câu không
   liên quan với nhau.
2. `pdftotext -x/-W` (cắt theo tọa độ) **nuốt mất ký tự cuối** của dòng chạm mép
   cột: "quản trị" thành "quản tr", "Kết quả" thành "Kế quả". Dấu tiếng Việt làm
   lỗi này rất khó phát hiện.

Cách làm đúng: dùng pdfminer phân tích layout, gán mỗi text box vào cột theo tâm
box so với đường giữa trang, rồi đọc lần lượt từng cột. Sau đó:
- bỏ tiêu đề chạy trang, số trang, chú thích bảng, dòng "Nguồn:"
- ghép lại đoạn theo quy tắc văn căn đều (dòng ngắn mà kết thúc bằng dấu chấm =
  hết đoạn)
- nối lại từ bị gạch nối ngắt dòng
- cắt ở dấu chấm cuối cùng để anchor không kết thúc giữa câu

**Bắt buộc đọc lại tiếng Việt của từng đoạn trước khi lưu.** Nếu có chữ cụt hoặc
câu đứt, làm lại — anchor sai chính tả sẽ dạy mô hình viết sai chính tả.

Không lấy: công thức, phương trình hồi quy dạng `Y = 0.338*X1 + ...`, bảng số.
Dấu `*` trong anchor có thể khiến mô hình sinh ra markdown trong bản viết lại.

## Cài đặt

1. Lưu `<id>.txt`, UTF-8, chỉ có văn xuôi, không front matter.
2. Thêm entry vào `manifest.json`. Trường `desc` viết như chỉ dẫn cho bộ chọn:
   `"PICK FOR: ... NOT FOR: ..."`, mô tả loại nội dung chứ không mô tả nguồn.
3. Cập nhật `PROVENANCE.md`: trích dẫn đầy đủ, URL, kết quả cả 3 bước thử index,
   và chép **nguyên văn** câu ghi bản quyền trên trang. Không đoán giấy phép —
   không thấy thì ghi "không rõ".
4. Ghi cả những nguồn bị LOẠI và lý do, để lần sau không nhập lại.
5. Kiểm tra nạp được:

```bash
./api/run.sh python -c "from orchestrator.tools.humanize import load_anchors; \
print([(a['id'], len(a['text'].split())) for a in load_anchors('vi')])"
```

6. Chạy test, phải xanh:

```bash
cd api && ./run.sh python -m pytest ../tests/test_humanize.py -q
```

Lưu ý: `tests/test_humanize.py` hiện có 2 test đang đỏ sẵn từ trước
(`test_a_translated_rewrite_is_rejected_and_the_original_kept`,
`test_content_expansion_is_rejected`) — không liên quan đến anchor. Đừng sửa
chúng, chỉ cần xác nhận không phát sinh test đỏ mới.

## Không được làm

- Không tự viết anchor, không dùng mô hình sinh ra anchor. Dùng văn máy làm mẫu
  cho văn máy là vòng lặp khép kín, không dạy được gì.
- Không vượt tường đăng nhập, không dùng tài khoản người khác, không phá paywall.
- Không nhắn tin, gửi email, liên hệ tác giả.
- Không tải hàng loạt — chỉ lấy đủ số đoạn cần.
- Không sửa lỗi chính tả, không làm mượt câu, không tóm tắt đoạn đã chọn.
- Không lấy quá 1 anchor từ cùng một bài báo.

## Báo cáo

1. Bảng nguồn đã nhận: trích dẫn, URL, năm, kết quả cả 3 bước thử.
2. Bảng nguồn đã loại kèm lý do.
3. Các anchor đã cài, kèm số chữ và slot tương ứng.
4. Kết quả lệnh kiểm tra nạp và kết quả test.
5. Nói thẳng nếu phần lớn thứ tìm được đều đã bị index — đó là phát hiện có ích,
   không phải thất bại. Đừng hạ chuẩn để lấp cho đủ slot.

# Kiến trúc Agent Hướng dẫn — vào ở bất kỳ bước nào, lo nốt phần còn lại, ít công nhất

> **Trạng thái:** Đề xuất (thiết kế) · **Ngày:** 2026-05-30
> **Phạm vi:** phần **orchestrator** (`/orchestrator`) chạy bằng LangGraph — KHÔNG phải engine cũ trong [`../ARCHITECTURE.md`](../ARCHITECTURE.md).
> Đây là bản tiếng Việt dễ đọc của [`guided-agent-architecture.md`](./guided-agent-architecture.md). Bản tiếng Anh là bản gốc đầy đủ + trích dẫn nghiên cứu.

---

## 0. Tóm tắt trong 30 giây

Hiện tại DoThesis bắt sinh viên đi **tuần tự M1 → M5** (Đề tài → Tổng quan tài liệu → Thiết kế → Phân tích → Viết). Ai cũng phải bắt đầu từ M1.

Mục tiêu mới: sinh viên đang **kẹt ở bất kỳ bước nào** (ví dụ "em có sẵn dữ liệu SPSS rồi nhưng chưa biết viết") thì hệ thống:
1. **Xem họ đang có gì** (đánh giá bài làm dở),
2. **Đặt họ vào đúng chỗ** trong quy trình,
3. **Làm bù** những bước trước mà bước hiện tại cần (nhưng họ bỏ qua),
4. **Dẫn họ tới đích** với **ít câu hỏi nhất**.

**Kết luận:** giữ nguyên LangGraph, chỉ thêm 3 lớp ở trên. Không cần đổi framework, không cần viết lại.

---

## 1. Hình dung bằng ví dụ xây nhà 🏠

Coi luận văn như **xây một căn nhà**:

- Bạn không thể **lợp mái** (viết chương Kết quả) khi chưa **đổ móng** (phân tích dữ liệu).
- Mỗi phần việc **phụ thuộc** vào phần trước → đó gọi là **quan hệ phụ thuộc (dependency)**.
- Nếu một anh thợ tới và nói "tôi muốn sơn tường luôn" nhưng tường còn chưa xây → người quản lý phải nói "khoan, xây tường trước đã". Đó chính là **làm bù bước thiếu (backfill)**.

Hệ thống hiện tại giống một **dây chuyền cứng**: bắt buộc làm móng → tường → mái theo đúng thứ tự, và luôn bắt đầu từ số 0. Cái mình muốn là một **người quản lý công trình thông minh**: ai tới ở khúc nào cũng được, nhìn cái đang có, rồi sắp xếp làm tiếp.

---

## 2. Vài thuật ngữ (giải thích đơn giản)

| Thuật ngữ | Nghĩa dễ hiểu |
|-----------|---------------|
| **Artifact** (sản phẩm) | Một "mảnh" của luận văn: đề tài, khung lý thuyết, thiết kế nghiên cứu, một chương cụ thể... |
| **DAG** (đồ thị phụ thuộc) | Sơ đồ "cái nào cần cái nào trước". Giống bản đồ thi công. |
| **DoD — Definition of Done** (định nghĩa "xong") | Tiêu chí kiểm tra một mảnh đã **thật sự xong chưa** — không phải chỉ bấm "Xác nhận" là xong. |
| **Validator** (bộ kiểm tra) | Cái máy chấm điểm "mảnh này đạt chưa", chạy **riêng** với cái máy tạo ra nó. |
| **Planner / Router** (bộ điều phối) | Bộ não quyết định "tiếp theo làm gì", nhìn DAG để biết cái nào xong / sẵn sàng / bị chặn. |
| **Intake / Triage** (cửa tiếp nhận) | Bước đầu: hỏi "bạn đang ở đâu, có sẵn gì" rồi xếp vào quy trình. |
| **Backfill** (làm bù) | Tự làm những bước trước bị thiếu mà bước hiện tại cần. |
| **Autonomy** (mức tự động) | Agent tự làm bao nhiêu phần, hỏi người dùng bao nhiêu. |

---

## 3. Hệ thống hiện tại đang chạy thế nào

```
Next.js (chat + thanh tiến độ M1–M5 + thẻ bấm "không cần gõ")
   │ SSE
FastAPI (/api/v1: projects, threads, messages, uploads)
   │ graph.astream()
LangGraph   START → _seed → supervisor → {M1│M2│M3│M4│M5│END}
Postgres   projects · threads · messages · context_store · paper_uploads
   + checkpoint của LangGraph (lưu trạng thái theo từng thread)
```

**5 mảnh việc:**

| Bước | Tạo ra cái gì |
|------|---------------|
| M1 Đề tài | tên đề tài, lĩnh vực, loại nghiên cứu, đối tượng, phạm vi, mục tiêu, câu hỏi nghiên cứu |
| M2 Tài liệu | tóm tắt hiện trạng nghiên cứu, khoảng trống, khung lý thuyết, giả thuyết, danh sách trích dẫn |
| M3 Thiết kế | hệ hình (định lượng/định tính/hỗn hợp), mô hình, thang đo / câu hỏi phỏng vấn, cỡ mẫu |
| M4 Phân tích | đọc dữ liệu SPSS/SmartPLS dán vào, ra bảng kết quả + diễn giải |
| M5 Viết | 6 chương + tài liệu tham khảo + xuất file docx/pdf |

**Cách định tuyến hiện tại:** `supervisor` gọi hàm `next_unconfirmed_module()` — "đi từ M1→M5, gặp mảnh nào chưa có dấu `confirmed_at` thì làm mảnh đó". Một mảnh coi là "xong" **chỉ khi** có dấu thời gian `confirmed_at`.

### Vì sao cách này chưa đủ cho mục tiêu mới

| Cần | Hiện tại | Thiếu |
|-----|----------|-------|
| Vào ở bước N bất kỳ | Luôn nhảy về mảnh trống **đầu tiên** | Không nhắm được bước cụ thể |
| Đánh giá bài làm sẵn | Luôn bắt đầu từ M1 | Chưa có |
| Làm bù bước thiếu | Không có mô hình phụ thuộc | Chưa có — **phần khó nhất** |
| Biết một bước **thật sự** xong chưa | Chỉ có cờ `confirmed_at` | Không kiểm tra nội dung (xác nhận mảnh rỗng vẫn "xong") |
| Sửa/lùi lại an toàn | Sửa M1 nhưng M3–M5 vẫn lặng lẽ sai lệch | Không đánh dấu "cần làm lại" |
| Ít công nhất | `auto` được ăn cả ngã về không | Không chỉnh được mức tự động từng bước |

Nói thẳng: cấu trúc hiện tại là **dây chuyền khoác áo agent**. Cần sửa ở **lớp mô hình hóa**, không phải đổi nền tảng.

---

## 4. Kiến trúc mới — thêm 3 lớp lên trên cái đang có

```
                    ┌─────────── PLANNER (bộ điều phối) ───────────┐
START → _seed →     │  tính xong / sẵn sàng / bị chặn cho từng mảnh │ → chạy 1 mảnh → quay lại PLANNER → …
        INTAKE  →   │  chọn việc tiếp theo tốt nhất; hỏi người dùng │            │
        (tiếp nhận) │  ĐÚNG 1 quyết định nhẹ nhàng (interrupt)      │            └→ END (chờ người dùng)
                    └──────────────────────────────────────────────┘
```

### 4.1 Sơ đồ phụ thuộc + bộ kiểm tra "đã xong" (DoD)

Thay "đường thẳng M1→M5" bằng một **sơ đồ các mảnh việc**, mỗi mảnh khai báo: **cần mảnh nào trước** + **làm sao biết là xong**.

```
đề tài ──┬─► khung lý thuyết ──┐
         │                     ├─► thiết kế ──► phân tích ──┐
         └─► khoảng trống      │                            ▼
                               └──► chương: phương pháp(←thiết kế)  kết quả(←phân tích)
                                          thảo luận(←kết quả, câu hỏi NC)  kết luận(←tất cả)
```

**Tại sao tách nhỏ hơn M5?** Sinh viên kẹt ở **chương Thảo luận** chỉ cần `kết quả` + `câu hỏi nghiên cứu`, **không cần** M3 hoàn hảo. Tách từng chương ra → vào đúng chỗ chính xác hơn.

**DoD trả về "xong? + danh sách chỗ còn thiếu"** chứ không chỉ đúng/sai. Cái danh sách thiếu đó chính là thứ:
- giúp planner biết cần làm gì tiếp,
- giúp bước tiếp nhận biết bài upload còn thiếu gì,
- và chính là **câu hỏi tiếp theo** nên hỏi người dùng.

> 💡 **2 nguyên tắc từ nghiên cứu:** (1) bộ kiểm tra phải **độc lập** với bộ tạo nội dung — đừng để cùng một LLM vừa viết vừa tự chấm (tự chấm không đáng tin — SagaLLM). (2) Trộn **kiểm tra cứng bằng code** (có đủ trường chưa) + **LLM chấm** (văn có mượt không).

### 4.2 Cửa tiếp nhận (Intake / Triage) — chỗ "em đang kẹt ở..."

Một bước chạy đầu khi dự án mới hoặc khi người dùng dán/đẩy bài làm sẵn vào:
1. Hỏi (bằng thẻ bấm) *"Bạn đang ở đâu? Có sẵn gì?"* — hoặc tự đọc file upload.
2. Một agent đánh giá **xếp bài làm vào sơ đồ** — ví dụ "đề tài xong, phương pháp làm dở, chưa có phân tích" — rồi **đổ sẵn dữ liệu vào các mảnh** thay vì tạo lại từ đầu.
3. Giao cho planner với sơ đồ đã điền sẵn.

👉 Đây là **mảnh ghép thiếu quan trọng nhất**: hiện tại mọi dự án đều phải bắt đầu từ M1.

### 4.3 Bộ điều phối (Planner) — thay cho `next_unconfirmed_module`

Nhìn trạng thái hiện tại, tính ra — **bằng luật rõ ràng** (sắp xếp theo phụ thuộc), chỉ dùng LLM khi mơ hồ:
- mỗi mảnh đang **xong / sẵn sàng / bị chặn**,
- **việc tiếp theo tốt nhất**: nếu người dùng muốn `chương Thảo luận` mà `phân tích` còn trống → **làm bù `phân tích` trước** (kèm 1 dòng giải thích lý do),
- và đưa ra **đúng 1 lựa chọn nhẹ nhàng** cho người dùng.

> Nên dùng luật cứng cho chắc. Log thực tế cho thấy bộ phân loại bằng LLM hiện tại từng định tuyến nhầm câu "em dùng khảo sát định lượng" → nhảy sang M3. Luật cứng dễ debug hơn.

### 4.4 Mức tự động lũy tiến — chính là "ít công nhất"

Nâng cấp cờ `interactive`/`auto` thành **mức tự động cho từng mảnh** (nghiên cứu *Levels of Autonomy*: mức tự động là **lựa chọn thiết kế**, tách rời khỏi năng lực của model):

- **Nháp trước, xác nhận nhẹ.** Mỗi bước tạo ra một **bản nháp hoàn chỉnh**, rồi chỉ hỏi "ok / chỉnh chỗ này" — **không** tra hỏi từng trường một. Thẻ bấm là công cụ lý tưởng.
- Để **tốn ít công nhất**, nghiêng về kiểu **"agent làm hết → người duyệt"** (cao hơn kiểu "đưa nháp rồi bắt sửa tay").
- Mỗi bước có 2 chế độ: `tự làm hết` và `đề xuất rồi chờ xác nhận`. Planner chọn dựa trên mức tự động + việc đó có cần thông tin riêng của người dùng không (dữ liệu của họ, quyết định mang tính phán đoán → bắt buộc phải hỏi).

### 4.5 Đánh dấu "cần làm lại" khi sửa bước trước

Khi một mảnh ở trên thay đổi (người dùng sửa câu hỏi nghiên cứu ở M1), đánh dấu các mảnh phụ thuộc là **lỗi thời (stale)** — đừng để chúng lặng lẽ sai. Hiện 1 dòng "N bước phía sau có thể cần xem lại". Đây là thứ giúp "quay lại sửa" trở nên **an toàn** (hiện tại thì không).

### 4.6 Giữ người dùng trong luồng — xử lý câu hỏi "trên trời rơi xuống"

Đây là giao diện chat, nên người dùng hay lạc đề: hỏi linh tinh, lo lắng, hỏi meta ("còn mấy bước nữa?"), hoặc "thôi em đổi đề tài". Agent phải xử lý **mọi tin nhắn như người thật** rồi kéo về luồng — **mà không bị cứng như tổng đài bấm phím**.

**Nguyên tắc: hai lớp; việc đang làm được *gửi tạm (park)*, không bị mất.** Tách **lớp hội thoại** (xử lý mọi tin nhắn) khỏi **lớp công việc** (sơ đồ phụ thuộc + planner). Bước hiện tại và câu hỏi đang chờ được "gửi tạm" trong checkpoint `interrupt()` của LangGraph → lạc đề không làm mất nó; quay lại chỉ là **nhắc lại câu đang chờ**.

```
tin nhắn → DISPATCHER (mỗi lượt): đúng việc? lạc đề? đổi hướng? meta? bực bội?
   đúng việc ──► chạy tiếp bước hiện tại
   lạc đề/meta► concierge: trả lời ngắn + nhắc lại câu đang chờ (dưới dạng thẻ bấm)
   đổi hướng ──► planner lập lại kế hoạch (đánh dấu bước sau là lỗi thời)
   bực bội ────► đề nghị làm đỡ ("để mình nháp cho nhé?") + kéo về
   ngoài phạm vi► từ chối lịch sự + hướng lại
```

**Cú "người thật" — Trả lời, rồi kéo về.** Đừng bao giờ phớt lờ, đừng chỉ hỏi lại. Một tin nhắn gồm 3 nhịp: (1) ghi nhận/trả lời ngắn cái họ vừa hỏi, (2) bắc cầu quay lại, (3) hiện lại câu đang chờ dưới dạng **thẻ bấm 1 chạm** để quay lại không tốn công. Vì thẻ luôn còn đó, "nãy mình đang làm gì nhỉ?" sẽ không xảy ra.

```
User:  khoan, APA 7 có cần DOI cho mọi nguồn không?
Agent: Hỏi hay đó — APA 7 cần DOI khi có, không thì dùng URL. Bước tài liệu tham
       khảo mình sẽ tự lo, bạn khỏi lăn tăn nhé. 🙂
       Quay lại phần thiết kế — bạn khảo sát được cỡ bao nhiêu người?
       [ ~100 ]  [ ~200 ]  [ 300+ ]  [ Chưa chắc — bạn chọn giúp ]
```

**Bộ phân loại mỗi lượt (mở rộng từ `_classify_user_intent` đang có):**

| Người dùng làm gì | Loại | Hành vi |
|-------------------|------|---------|
| Trả lời câu hỏi | `đúng việc` | Đưa vào bước hiện tại, đi tiếp |
| Hỏi kiến thức linh tinh | `lạc đề` | Trả lời 1 câu → kéo về |
| "Còn mấy bước? đang làm gì?" | `meta` | Hiện tiến độ từ sơ đồ (xong/sẵn sàng/bị chặn) → kéo về |
| Than thở, căng thẳng | `bực bội` | Đồng cảm → **đề nghị làm đỡ** ("mình nháp, bạn duyệt") → kéo về |
| "Thôi đổi đề tài" | `đổi hướng` | Là *thật* — đưa cho planner, đánh dấu bước sau lỗi thời, **đừng** ép quay lại |
| "Viết hộ em cái thư xin việc" | `ngoài phạm vi` | Từ chối lịch sự + hướng lại |
| "Không biết / bạn chọn đi" | `ủy quyền` | Chọn mặc định hợp lý, nói ra, đi tiếp (đã hỗ trợ) |

**Hai lan can để không bị cứng như tổng đài:**
- **Đừng kéo về quá đà.** Phải phân biệt *lạc đề* (gửi tạm rồi quay lại) với *muốn đổi hướng thật* (lập lại kế hoạch). Ép "quay lại bước 3!" khi họ muốn việc khác chính là kiểu robot.
- **Việc tiếp theo luôn hiển thị** — thẻ của bước hiện tại luôn còn đó, người dùng không bao giờ bị lạc.

> **Lỗ hổng hiện tại:** `base.py` đang xử lý `off_topic` bằng cách *phớt lờ rồi hỏi lại*. Đó là chỗ lạnh lùng. Đổi thành **trả-lời-rồi-kéo-về**, thêm nhánh `meta` + `bực bội`. Về kiến trúc, nó là một **node dispatcher bọc quanh planner**; chỗ "gửi tạm" chính là checkpoint `interrupt()` đã dùng cho "vào ở đâu cũng được" — không cần thêm gì mới.

### 4.7 Đưa đúng ngữ cảnh cho đúng thành phần — lịch sử có cửa sổ cho hội thoại, trạng thái chuẩn cho công việc

Để không bị robot, **lớp hội thoại phải thấy các tin nhắn gần đây, không chỉ tin hiện tại** — nếu không thì "ừ", "cái thứ hai", "như em nói lúc nãy" sẽ vô nghĩa, và không phân biệt được lạc đề với nói tiếp. Nhưng **nhiều ngữ cảnh ≠ tốt hơn**: phải tách rõ 3 loại ngữ cảnh.

| Ngữ cảnh | Nguồn | Ai dùng |
|----------|-------|---------|
| **Chat gần đây** (N lượt cuối, có cửa sổ) | `messages`, cắt bớt | Dispatcher + concierge — hiểu tham chiếu, giọng điệu, phát hiện lạc đề |
| **Trạng thái công việc** (mảnh hiện tại, câu đang chờ, chỗ thiếu DoD) | slice `context_store` có cấu trúc | Worker — **là chuẩn; KHÔNG đoán lại từ chat** |
| **Bộ nhớ dự án** (đề tài, lĩnh vực, lựa chọn trước, văn phong) | kho bộ nhớ dự án | Concierge + worker — cá nhân hóa |

**Quy tắc:** lịch sử chat để *hiểu con người*; trạng thái có cấu trúc là *nguồn sự thật cho công việc*. Đừng để worker tự suy ra "đang ở bước nào / đã điền gì" từ việc cuộn lại chat.

> **Bài học xương máu (lỗi thật trong repo này):** phase 1 của M2 đọc "tin nhắn mới nhất" và nuốt nhầm chữ **"yes"** vốn là *xác nhận của M1* → nó bỏ qua câu hỏi của mình và hội thoại bị kẹt. Cách sửa là dựa vào trạng thái có cấu trúc (`is_resume`), không phải "lấy tin cuối". Bài học hai chiều: cho **lớp hội thoại nhiều hơn** (một cửa sổ, để giống người); cho **lớp công việc đúng câu trả lời + trạng thái chuẩn** (để không bắn nhầm).

**Hai quy tắc thực dụng:** (1) **Cắt cửa sổ, đừng đổ hết** — đưa vài lượt cuối, không phải cả thread (tốn tiền, nhiễu, dễ vớ phải lệnh cũ); reducer `add_messages` giữ cả danh sách, mình cắt trước mỗi lần gọi LLM. (2) **Tóm tắt khi thread dài ra** — một bản "tóm tắt từ đầu" + vài lượt gần nhất (thread luận văn sẽ dài).

---

## 5. Phần KHÓ nhất: làm bù bước bị thiếu ⚠️

> **Đây là phần mà không tài liệu nghiên cứu nào "đỡ" được cho mình.** LangGraph có thể **chạy lại** các bước đã lưu; mô hình saga có thể **hoàn tác** việc đã làm. Nhưng **không cái nào tự tạo ra một bước mà sinh viên chưa hề làm.** Việc dựng lại `thiết kế` từ phần phân tích sẵn có của sinh viên là **logic riêng của mình, phải tự thiết kế và kiểm chứng.**

Hướng làm đề xuất (nên **làm thử cái này TRƯỚC** mọi thứ khác):
1. Planner phát hiện mảnh đích cần một mảnh đang **trống**.
2. Với mỗi mảnh thiếu, chạy bước đó ở chế độ **"dựng lại"**, mớm cho nó bằng bằng chứng phía sau đang có (ví dụ suy ra hệ hình/thiết kế từ phần phân tích sinh viên dán vào + đề tài), ra một **bản nháp** đánh dấu "do hệ thống suy luận".
3. **Chốt cửa:** chạy DoD + 1 lần xác nhận của người dùng ("bọn mình đoán thiết kế của bạn là khảo sát định lượng — đúng không?"). **Tuyệt đối không bịa bước trước một cách âm thầm.**
4. Xong rồi mới mở khóa cho mảnh đích.

Làm cái này thành **lát cắt đầu tiên** ([§7](#7-lộ-trình-triển-khai)) vì nếu chất lượng dựng lại kém thì cả lời hứa "vào ở đâu cũng được" sẽ lung lay.

---

## 6. Quyết định framework: GIỮ LangGraph

Không có lỗ hổng năng lực nào buộc phải đổi, và nguyên tắc "chỉ thêm phức tạp khi thật sự đáng" (Anthropic) cũng khuyên đừng đổi.

| Lựa chọn | Kết luận |
|----------|----------|
| **LangGraph** (đang dùng) | **Giữ.** Đã có sẵn: dừng-hỏi-người-dùng (`interrupt`), lưu trạng thái bền theo thread, "tua lại"/rẽ nhánh từ một điểm bất kỳ — đúng thứ cần cho "vào ở đâu cũng được + làm bù". *Nên dùng `interrupt()` chuẩn của LangGraph thay cho cờ `_module_paused` tự chế.* |
| Durable execution (Temporal/DBOS/Restate) | **Để sau.** Là lớp **bổ sung**, không thay thế. Postgres checkpoint đã đủ bền; chỉ thêm khi có nhu cầu chạy nhiều tuần thật sự cần độ tin cậy hạ tầng. |
| OpenAI Agents SDK / Pydantic-AI / CrewAI / AutoGen / LlamaIndex | **Không hơn.** Mấy cái này sinh ra cho **tự chủ mở** (agent tự quyết); còn mình cần **chắc chắn + kiểm soát + có cổng người duyệt**. Học **mẫu thiết kế** của họ (sơ đồ phụ thuộc, validator độc lập), không bê cả framework. |

---

## 7. Lộ trình triển khai (mỗi bước đều ship được)

0. **Dùng `interrupt()` chuẩn** thay cờ `_module_paused`. Dọn dẹp nhẹ, lợi về sau.
1. **Thêm metadata cho mỗi mảnh** — "cần gì trước" + hàm DoD (`orchestrator/artifacts.py`). Dây chuyền vẫn chạy như cũ, chưa định tuyến theo nó.
2. **API import + start-at** — mở khóa "đẩy luận văn dở vào là chạy tiếp". *(Đường nhanh nhất tới đúng lời hứa sản phẩm.)*
3. **🔬 Lát cắt làm-bù** — làm thử việc dựng lại bước thiếu ([§5](#5-phần-khó-nhất-làm-bù-bước-bị-thiếu-️)) cho MỘT trường hợp thực tế (vd: vào ở `phân tích`, dựng lại `thiết kế`). **Khử rủi ro trước khi làm rộng.**
4. **Cửa tiếp nhận (Intake)** — agent đánh giá đầu vào.
5. **Planner thay `next_unconfirmed_module`** — sắp xếp theo phụ thuộc; chỉ dùng LLM khi mơ hồ.
6. **Dispatcher + giữ người dùng trong luồng** ([§4.6](#46-giữ-người-dùng-trong-luồng--xử-lý-câu-hỏi-trên-trời-rơi-xuống)) — trả-lời-rồi-kéo-về; thêm nhánh `meta`/`bực bội`; đưa lịch sử có cửa sổ cho dispatcher ([§4.7](#47-đưa-đúng-ngữ-cảnh-cho-đúng-thành-phần--lịch-sử-có-cửa-sổ-cho-hội-thoại-trạng-thái-chuẩn-cho-công-việc)).
7. **Cờ "cần làm lại" + thanh chỉnh mức tự động + bộ nhớ dự án.**

Riêng bước 2–3 đã đủ tạo ra trải nghiệm "vào ở đâu cũng được", và bước 3 là chỗ rủi ro thật sự nằm.

---

## 8. Rủi ro & chỗ nghiên cứu CHƯA che được

1. **Làm bù bước thiếu là phần mới, chưa ai chứng minh** ([§5](#5-phần-khó-nhất-làm-bù-bước-bị-thiếu-️)). Chất lượng dựng lại là ẩn số quyết định. Làm thử trước.
2. **"Giữ hay đổi framework" là suy luận kỹ thuật, không phải số đo benchmark.** Chưa có nguồn nào đo chính xác phương án này so với việc đổi hẳn.
3. **Bản thân validator cũng có thể sai.** Cần quyết: kiểm bằng code / LLM chấm / cả hai — và làm sao kiểm tra lại chính cái bộ kiểm tra.
4. **LangGraph 1.x thay đổi nhanh.** `interrupt()`/`Command(resume=...)` là API hiện hành; kiểu cũ đã bị bỏ — kiểm tra lại tài liệu khi code.
5. **"Ít công nhất" còn tranh cãi.** Kiểu "agent làm hết → duyệt" tốn ít công hơn kiểu "đưa nháp rồi sửa tay" — nên thử với sinh viên thật.

---

## 9. Các quyết định cần ý kiến sản phẩm

| # | Quyết định | Mặc định đề xuất |
|---|------------|------------------|
| D1 | Dựng lại bước thiếu thế nào? | Chế độ "dựng lại" mớm bằng bằng chứng phía sau + 1 lần xác nhận ([§5](#5-phần-khó-nhất-làm-bù-bước-bị-thiếu-️)) |
| D2 | Mức tự động cho dự án mới | Nháp-trước (tạo bản hoàn chỉnh → duyệt/chỉnh); thêm thanh chỉnh từng bước sau |
| D3 | Validator: code hay LLM chấm | Cả hai — kiểm cứng trước, LLM chấm cho phần văn; giữ độc lập với bộ tạo |
| D4 | Có thêm durable execution không? | Không, tới khi xác định được tình huống hỏng cụ thể cần nó |
| D5 | Độ chi tiết của mảnh việc | Nhỏ hơn M5 — từng chương là một mảnh; M1–M4 tạm giữ nguyên |
| D6 | Cửa sổ lịch sử đưa cho dispatcher | ~3–5 lượt cuối + bản tóm tắt cho thread dài; không bao giờ cả thread ([§4.7](#47-đưa-đúng-ngữ-cảnh-cho-đúng-thành-phần--lịch-sử-có-cửa-sổ-cho-hội-thoại-trạng-thái-chuẩn-cho-công-việc)) |

---

*Bản gốc tiếng Anh + trích dẫn nghiên cứu đầy đủ: [`guided-agent-architecture.md`](./guided-agent-architecture.md). Engine cũ: [`../ARCHITECTURE.md`](../ARCHITECTURE.md).*

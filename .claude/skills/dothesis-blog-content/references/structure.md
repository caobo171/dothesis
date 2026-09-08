# Article structure

Derived from the pages that currently rank for these queries: phamlocblog.com,
xulysolieu.info, phantichspss.com and xulydinhluong.com, sampled through the SERP
sweep in `docs/seo/topic-bank/serp-head-terms-2026-09-07.tsv`. Those pages run 600
to 1,500 words, one or two screenshots, a threshold stated with no source, and no
worked output. The target below is what beats them without padding.

## Target shape

| Element | Target |
|---|---|
| Word count | 1,800 to 2,400. Under 1,500 fails QA |
| H2 sections | 6 to 9, taken from the archetype skeleton |
| H3 | one per step inside a procedure section, one per group inside a list |
| Tables | at least 1, at least 2 when the page is unmeasured. A threshold table or a worked output table, never a decorative one |
| Internal links | 4 or more distinct, 5 or more when the page is unmeasured: the category route, 2 to 3 siblings, `/landing` |
| FAQ | `## Câu hỏi thường gặp` with 4 to 6 `###` questions |
| Images | none by default. See `images.md` |
| CTA | exactly one, in the closing paragraph |

## The three rules that apply to every archetype

**1. The proprietary element.** Every post carries at least one of:

- a **threshold or decision table** whose every row names its canonical source
  from `canonical-sources.md`;
- a **worked example table** labelled `số liệu minh họa`, shaped like the real
  SPSS or SmartPLS output for this procedure, with plausible numbers that are
  clearly presented as an illustration and never as findings from a study;
- a **`cách viết vào luận văn` paragraph** giving one or two sentences in
  Vietnamese that the student can adapt directly, with the placeholders visible.

A post with none of those is a rewrite of a competitor page and does not ship.

**A post with no measured search volume carries two of the three, not one.** Its
`gate_status` is `unmeasured`, meaning no measurement stands behind the decision
to publish it, so the article itself is the entire case for its existence. The two
rows above double the same way: one more table and one more internal link than a
measured page. The QA gate also holds an unmeasured page to a stricter
near-duplicate threshold against every other body in the corpus. The calibrated
numbers are in `api/app/blog/content/qa.py`; read them there rather than from
here.

**2. The FAQ section.** Always `## Câu hỏi thường gặp`, always four to six `###`
questions, each answered in one to three paragraphs. Take the questions from what
students actually type: the `là gì`, `bao nhiêu là đạt`, `bị lỗi thì làm sao`
phrasings in the harvest, not from what would be tidy to answer. The web renderer
turns this section into FAQPage JSON-LD, so a question that is not a question
wastes the slot.

**3. The close.** One paragraph, no `## Kết luận` heading, no motivational send
off. Say what the reader should do next in their own file, then one CTA link to
`/landing` naming the module that does this step:

- **M3** thang đo và bảng hỏi: conceptual model, hypotheses, questionnaire.
- **M4** phân tích: running the statistics on the student's own `.sav` or `.csv`.
- **M5** viết chương: turning results into chapter prose.

One link. A second CTA fails QA as a warning and reads as an ad.

## Anchors

Do not write ids. The renderer slugs every H2 with the shared algorithm (lowercase,
strip diacritics, `đ` becomes `d`, non-alphanumerics become hyphens, numeric suffix
on repeats) and the contents box is generated from the H2 list. Two H2s with the
same text collide into `-1` and `-2` anchors that mean nothing, so keep headings
distinct.

## The ten archetypes

Each row of the backlog carries an `archetype`. The skeleton is the H2 spine for
that archetype. Adapt the wording to the unit, keep the order, and drop a section
only when the unit genuinely has nothing to put in it.

### `term-la-gi` — `{thuật ngữ} là gì`

139 of the 407 harvested keywords are this shape. The reader has an output table
open and a number they do not understand.

1. `{Thuật ngữ} là gì` — one paragraph of plain definition, then the formula or the
   thing it is computed from. No history.
2. `Ý nghĩa của {thuật ngữ} trong nghiên cứu định lượng` — what decision it drives.
3. `{Thuật ngữ} bao nhiêu là đạt` — the threshold table, every row cited.
4. `Cách đọc {thuật ngữ} trên output` — the worked `số liệu minh họa` table for
   SPSS or SmartPLS, with the column names as the software prints them.
5. `Khi {thuật ngữ} không đạt thì xử lý thế nào` — ordered options, honest about
   which ones a reviewer will accept.
6. `Phân biệt {thuật ngữ} với {chỉ số dễ nhầm}` — the confusion this term actually
   causes.
7. `Lỗi thường gặp`
8. `Câu hỏi thường gặp`
9. close

### `spss-howto` — `cách chạy {phân tích} trong SPSS`

1. `Khi nào dùng {phân tích}` — the research situation, tied to a hypothesis shape.
2. `Chuẩn bị dữ liệu trước khi chạy` — variable types, missing values, reverse
   coded items, what has to be true before the menu path works.
3. `Các bước chạy {phân tích} trong SPSS` — H3 per step, each naming the real menu
   path (`Analyze > ...`) and the dialog options that matter.
4. `Đọc kết quả output` — the worked table, named as SPSS names it.
5. `Tiêu chí đánh giá` — the threshold table, cited.
6. `Cách viết kết quả vào luận văn` — the adaptable sentence.
7. `Lỗi thường gặp khi chạy {phân tích}`
8. `Câu hỏi thường gặp`
9. close

### `smartpls-howto` — `{thủ tục} trong SmartPLS`

1. `{Thủ tục} trong SmartPLS dùng để làm gì`
2. `Chuẩn bị mô hình và dữ liệu` — measurement versus structural model, indicator
   naming, the `.csv` shape SmartPLS expects.
3. `Các bước thực hiện trong SmartPLS 4` — H3 per step. Say which version the path
   belongs to, because SmartPLS 3 and 4 moved menus.
4. `Đọc bảng kết quả` — the worked table.
5. `Ngưỡng đánh giá` — cited thresholds. Keep the PLS-SEM metric family clean:
   R², f², Q², path coefficients, CR, AVE, HTMT. Never mix in CFI, TLI or RMSEA,
   which belong to CB-SEM.
6. `Cách trình bày trong chương 4`
7. `Lỗi thường gặp`
8. `Câu hỏi thường gặp`
9. close

### `test` — `kiểm định {tên kiểm định}`

1. `{Kiểm định} kiểm định điều gì`
2. `Giả thuyết H0 và H1` — stated as sentences, not symbols alone.
3. `Điều kiện áp dụng` — the assumption table, cited, with how each assumption is
   checked in SPSS.
4. `Các bước chạy trong SPSS` — H3 per step.
5. `Đọc bảng kết quả và kết luận` — the worked table plus the decision rule on the
   p-value.
6. `Cách viết kết quả kiểm định vào luận văn`
7. `Khi vi phạm giả định thì dùng gì thay thế` — the honest alternative test.
8. `Lỗi thường gặp`
9. `Câu hỏi thường gặp`
10. close

### `model-theory` — `mô hình {x}`, `lý thuyết {x}`

1. `Mô hình {x} là gì` — the original author and year, from the allowlist only.
2. `Các thành phần trong mô hình` — table of constructs with their definitions.
3. `Mô hình gốc và các mở rộng phổ biến` — what later work added, again only from
   the allowlist.
4. `Thang đo thường dùng cho từng khái niệm` — table mapping construct to a cited
   source scale.
5. `Áp dụng vào đề tài của bạn` — a worked conceptual model with hypotheses H1 to
   H4 written out.
6. `Cách kiểm định mô hình bằng SPSS hoặc SmartPLS` — which tool fits this model
   and why.
7. `Lỗi thường gặp khi dùng mô hình này`
8. `Câu hỏi thường gặp`
9. close

### `scale` — `thang đo {khái niệm}`

1. `{Khái niệm} là gì và được đo bằng gì`
2. `Nguồn thang đo gốc` — table: author, year, number of items, original context.
   Only allowlist sources.
3. `Bộ biến quan sát tham khảo` — table of item codes and the Vietnamese wording,
   presented as a starting point the student must adapt, never as a validated
   translation.
4. `Điều chỉnh thang đo cho bối cảnh Việt Nam` — wording, reverse items, pilot.
5. `Kiểm định độ tin cậy và giá trị của thang đo` — which tests, in what order.
6. `Cách trình bày thang đo trong chương 3`
7. `Lỗi thường gặp`
8. `Câu hỏi thường gặp`
9. close

### `thesis-writing` — `cách viết {phần} luận văn`

1. `{Phần} trong luận văn là gì` — what it is for and roughly how long.
2. `Cấu trúc chuẩn của {phần}` — table: sub-section, what goes in it, rough length.
3. `Các bước viết {phần}` — H3 per step.
4. `Câu mẫu dùng được` — table of adaptable sentences with placeholders.
5. `Ví dụ {phần} rút gọn` — one short worked example.
6. `Lỗi thường gặp khiến hội đồng hỏi lại`
7. `Câu hỏi thường gặp`
8. close

### `survey` — `{x} khảo sát`, `cỡ mẫu {x}`

1. `{X} là gì trong nghiên cứu định lượng`
2. `Cách xác định {x}` — the formula or the rule of thumb, cited, plus a lookup
   table.
3. `Thiết kế bảng hỏi phục vụ mục tiêu này` — question types, Likert points,
   screening questions.
4. `Triển khai thu dữ liệu` — where the responses come from and how long it takes.
   Name fillform.info here: it is our own form tool for exactly this step, so say
   so plainly as ours. Google Forms is the honest alternative and gets named too.
5. `Làm sạch dữ liệu trước khi nhập SPSS` — straight-lining, incomplete responses,
   the columns to drop.
6. `Cách trình bày trong chương 3`
7. `Lỗi thường gặp`
8. `Câu hỏi thường gặp`
9. close

### `topic-list` — `đề tài luận văn {ngành}`

The one archetype where the list is the product. It still needs the model and the
data, or it is the same listicle everyone else published.

1. `Chọn đề tài {ngành} theo tiêu chí nào` — table of criteria, including whether
   the data is actually collectable by one student.
2. `Danh sách đề tài theo nhóm` — H3 per group, each topic given with its
   independent and dependent variables, not as a bare title.
3. `Mô hình và thang đo gợi ý` — table mapping topic group to a cited model.
4. `Dữ liệu lấy ở đâu và cỡ mẫu bao nhiêu`
5. `Những đề tài nên tránh` — and why, concretely.
6. `Lỗi thường gặp khi chốt đề tài`
7. `Câu hỏi thường gặp`
8. close

### `troubleshoot` — `{triệu chứng} phải làm sao`, `lỗi {x} SPSS`

`ma trận xoay` at 6,600 a month is this archetype. The reader is stuck tonight.

1. `Hiện tượng bạn đang gặp` — describe the screen, so the reader knows they are
   on the right page in the first ten seconds.
2. `Nguyên nhân thường gặp` — table: dấu hiệu, nguyên nhân, cách kiểm tra.
3. `Cách xử lý theo thứ tự ưu tiên` — H3 per fix, cheapest and most defensible
   first.
4. `Khi nào phải quay lại thu thêm dữ liệu` — the honest ceiling on fixing it in
   software.
5. `Cách giải trình với giảng viên hướng dẫn` — the adaptable sentence.
6. `Cách phòng từ bước thiết kế`
7. `Lỗi thường gặp khi sửa`
8. `Câu hỏi thường gặp`
9. close

## What belongs in a table

Good: a threshold table with a source column; a worked SPSS or SmartPLS output
block; an assumption checklist with how each is tested; a construct-to-source-scale
map; a menu-path summary; a sample-size lookup.

Bad: a table of things that are not comparable, a two-row table that should be a
sentence, or a table built so the post has a table.

Tables are GFM pipe tables. The renderer wraps them in a horizontally scrollable
container, so a five-column table is safe on a phone.

## Length discipline

Long is not the goal, complete is. Cut any paragraph that restates the previous one
and any section that exists because the skeleton lists it but this unit has nothing
to put there. A tight 1,900 words beats a padded 2,600, and QA warns above 3,000.

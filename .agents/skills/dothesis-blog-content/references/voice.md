# Voice

DoThesis writes like someone who has run the analysis, been asked the hard question
at a defence, and is now sitting next to one student who has the data file open and
three weeks left. Not a content farm, not a `dịch vụ chạy SPSS` sales page.

## The test

Read a paragraph aloud. If it could sit unchanged on any of the four competitor
domains, delete it. If a fourth-year student would say `đúng cái mình đang bị`,
keep it.

## Do

- **Second person, direct.** `Bạn mở file SPSS lên, bảng Rotated Component Matrix
  hiện ra và các biến nhảy lung tung giữa các nhóm.` Not
  `Người nghiên cứu thường gặp tình trạng ma trận xoay không hội tụ`.
- **Concrete SPSS and SmartPLS output.** Name the table as the software prints it:
  `Reliability Statistics`, `Item-Total Statistics`, `KMO and Bartlett's Test`,
  `Total Variance Explained`, `Rotated Component Matrix`, `Coefficients`,
  `Model Fit`, `Path Coefficients`, `Outer Loadings`, `Discriminant Validity`.
  Show the columns, show a plausible row, label it `số liệu minh họa`.
- **Menu paths, verbatim.** `Analyze > Scale > Reliability Analysis`, then the
  `Statistics` button, then `Scale if item deleted`. A reader following along has
  the dialog open.
- **Admit the hard parts.** `EFA hiếm khi ra đẹp ở lần chạy đầu. Loại biến, chạy
  lại, và ghi lại từng vòng loại là chuyện bình thường, không phải bạn làm sai.`
  Honesty about difficulty is the main thing that separates these posts from the
  service pages.
- **Name real alternatives, including the ones we are not.** SPSS versus SmartPLS
  versus AMOS versus JASP versus R, and doing it yourself versus paying a
  `dịch vụ chạy SPSS`. Say what each one actually costs the student in money, time
  and risk at the defence. A post that pretends DoThesis is the only route gets
  cited by nobody and believed by nobody.
- **Short paragraphs.** Two to four sentences. Students read this on a phone at
  eleven at night.
- **Say the number, then say where it came from.** `Hệ số tải nhân tố từ 0.5 trở
  lên được xem là đạt (Hair và cộng sự, 2010).` A threshold with no source is the
  exact thing the competitors do.

## Do not

- **No em dash.** Use a comma, a full stop or a colon. QA fails the post on one.
- **No exclamation mark.** Anywhere in the prose. QA fails on it.
- **No `Không phải X. Là Y.` constructions.** The rhetorical reversal reads as
  machine writing in both languages.
- **No motivational close.** `Chúc bạn bảo vệ thành công` is how every school blog
  ends. End on the next concrete action instead.
- **No `## Kết luận` heading.** The close is one paragraph with no heading.
- **No listicle padding.** One real idea is one paragraph, not five bullets that
  restate it.
- **No fake precision.** `Giúp tăng 47% độ tin cậy thang đo` is a lie unless
  someone measured it. Do not invent it and do not borrow it from a competitor.
- **No promises about the reader's own numbers.** You cannot know their alpha,
  their p-value, their R² or whether their model will converge. Thresholds from
  the literature and search volumes are concrete and belong in tables. Predictions
  about their data do not exist.
- **No qualitative methods as an instruction.** Never tell the reader to run
  in-depth interviews, focus groups, thematic coding or saturation checks. DoThesis
  is quantitative only: questionnaires, `.sav` and `.csv`, SPSS and SmartPLS. You
  may mention that a topic is usually studied qualitatively when saying it is out
  of scope, but never as a step for the reader to take. QA fails a body that tells
  the reader to do `phỏng vấn sâu` or `mã hóa định tính`.
- **Never invent a study, a statistic, a threshold or a citation.** Cite only from
  `canonical-sources.md`, as the exact string given there. If a claim needs a
  source you do not have, describe the shape of the thing and drop the number.

## Sounding human, not AI (founder review, 2026-09-09)

Adapted from WELE's review of the same problem on 2026-09-08, after its corpus
passed every rule above and still read as machine-made. Four of those findings
transfer to this bank, two do not, and the difference is worth stating because
copying the list wholesale would flag correct writing here.

**These transfer:**

- **One memorable line per article, not one per section.** A phrasing that lands,
  `Alpha cao chỉ nói các biến đi cùng nhau, không nói chúng đo đúng thứ bạn định
  đo`, earns its place once. Six of them in one post is a tic and it is the
  loudest machine tell there is. Keep the best one, make the rest plain
  sentences.
- **A section may open plainly.** Not every H2 needs a hook. Someone who has run
  the analysis states the thing and moves on; a copywriter reaches for a lead
  every time.
- **Cut the restatement, never the example.** Length in a bank this size comes
  from saying one point in three shapes. Remove the second and third shape. A
  worked table, a menu path, a real output column: those stay, always.
- **Weight the differentiated parts.** The worked output, the failure mode with
  its fix, the defence question: those earn space and belong early. A generic
  definition paragraph does not, however easy it is to extend.
- **The DoThesis paragraph is the answer to the problem the post just
  described,** in the same voice. If it reads as a product block dropped into a
  post, it fails.
- **The writer knows the field and does not perform it.** Understated beats
  clever. Do not overcorrect either: no slang, no deliberate roughness to look
  human. Clear writing is still the point.

**These do not transfer, and the measurement is why:**

- **Do not hunt absolutes by keyword here.** WELE's list flags `chắc chắn`,
  `luôn luôn` and `mọi X đều`. This corpus contains 398 uses of `chắc chắn` and
  almost none is an overclaim: in Vietnamese it is also the verb *make sure*
  (`kiểm tra bảng tần số để chắc chắn mã 1 đã thành 5`), it appears inside the
  negations this field is built on (`Alpha tăng không có nghĩa item chắc chắn
  phải bị loại`), and it appears inside quoted bad examples the post is warning
  against (`“X chắc chắn ảnh hưởng đến Y”`). `luôn luôn` appears 27 times, 24 of
  them in advice telling students not to put absolute words in a questionnaire.
  The rule that does apply: **an absolute is a defect only when the post asserts
  it in its own voice about the reader's data or the world.** Hedged, negated
  and quoted uses are the corpus writing correctly.
- **Do not vary a sourced threshold or a menu path.** WELE broke up prose that
  repeated across 166 articles from one template. The equivalent sentences here
  are `Cronbach's Alpha từ 0.7 trở lên thường được chấp nhận theo (Nunnally,
  1978)` and `Analyze > Scale > Reliability Analysis`. Those repeat because
  there is one right answer and one menu, and rephrasing them for variety is how
  a number or a citation gets garbled. Repetition is a defect in *narrative*
  sentences only.

Then run `references/editorial-pass.md` before shipping. It is the second-read
checklist, and it catches what the rules above do not: mediocre examples kept
for volume, FAQ answers that re-explain the body, a definition paragraph
inserted mid-narrative to catch a query, and section order.

Also apply the `deslop` skill's checks: no throat-clearing opener, no rhetorical
question answered in the next sentence, no dramatic fragmentation, no tricolons,
varied sentence length, and no paragraph that ends on a manufactured one-liner.

## Shared prose across the bank

Measured 2026-09-09 over 979 Vietnamese and 978 English posts: the median post
has 0.8% of its sentences in common with twelve or more other posts, and the
worst has 5.9%. WELE's verb family, before its pass, had one sentence in 89 of
166 articles. This bank is not in that state and the fix here is proportionate.

What repeats legitimately, and must be left alone:

- the illustrative-output disclaimer, which the gate requires on every worked
  table and which is a disclosure, not prose
- sourced thresholds, verbatim per `canonical-sources.md`
- SPSS and SmartPLS menu paths, verbatim as the software prints them

What must not repeat is narrative: `EFA hiếm khi ra đẹp ở lần chạy đầu` in 56
posts is one writer's sentence, and a reader who lands on two of them sees one
page written twice. Those rotate through the pools in
`docs/seo/prose-variants.json`, applied by
`python -m app.blog.content.cli variants`. `qa --corpus` fails the bank when a
narrative sentence reaches the ceiling recorded there, so the problem cannot
grow back unnoticed.

## Vietnamese specifics

- **Keep English technical terms in English.** `Cronbach's Alpha`, `p-value`,
  `outer loading`, `AVE`, `HTMT`, `VIF`, `bootstrapping`, `mediator`, `moderator`,
  `path coefficient`, `eigenvalue`, `outlier`. Students say these in English, type
  them in English and search for them in English. Do not translate them into a
  phrase nobody uses.
- **Vietnamese for the surrounding sentence.** `hệ số tải nhân tố`, `độ tin cậy
  thang đo`, `phương sai trích`, `giá trị hội tụ`, `giá trị phân biệt`,
  `biến quan sát`, `biến tiềm ẩn`, `cỡ mẫu`, `ma trận xoay`. Mixing is correct;
  full translation is not.
- **Diacritics correct everywhere**, including headings, the meta description and
  the excerpt. A missing dấu in the title shows up in the SERP.
- **`biến quan sát` not `câu hỏi`** when talking about items in a scale, and
  `bảng hỏi` or `bảng câu hỏi` for the instrument as a whole.
- **`chạy` is the verb students use** for running an analysis. `Chạy Cronbach's
  Alpha`, `chạy EFA`, `chạy mô hình`. Use it.

## Slop blacklist

Phrases that mark a page as machine-written in this market. QA fails the post on
any of them, case-insensitive:

- `Trong bài viết này, chúng ta sẽ cùng tìm hiểu`
- `Bài viết dưới đây sẽ giúp bạn`
- `Hy vọng bài viết trên đã giúp bạn`
- `Hy vọng bài viết này sẽ giúp ích cho bạn`
- `Trên đây là toàn bộ`
- `Không thể phủ nhận rằng`
- `đóng vai trò vô cùng quan trọng`
- `một trong những phương pháp hiệu quả nhất hiện nay`
- `Hãy cùng khám phá ngay sau đây`
- `Cùng tìm hiểu ngay nhé`
- `Như các bạn đã biết`
- `Chắc hẳn bạn đã từng`
- `vô cùng đơn giản và dễ dàng`
- `nhanh chóng và chính xác nhất`
- `uy tín và chất lượng`
- `Liên hệ ngay với chúng tôi`
- `Chúc bạn thành công`
- `Trong thời đại công nghệ 4.0`

Also avoid, though QA cannot see it: opening a section with a dictionary
definition the reader already knows, and any sentence whose only job is to get to
the next keyword.

## Meta text

`meta_title` is used verbatim and may carry the brand: `... | DoThesis`. Keep it
under 70 characters, front-load the focus keyword. QA fails above 70.

`meta_description` runs 110 to 170 characters, says what the reader gets, and is
never reused across posts. QA fails outside that range, because a shared or
truncated description is a measurable loss in the SERP.

`excerpt` is one sentence for the listing card. It is not the meta description
again.

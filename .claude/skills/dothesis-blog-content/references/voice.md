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

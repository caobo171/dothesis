# Research synthesis — FillForm support corpus → DoThesis agent behaviour

**Method:** retrospective analysis of support conversations (Facebook Page inbox export)
**Corpus:** 6,008 threads · 268,789 messages · 30 Oct 2023 → 4 Sep 2026 · 136,477 messages (50.8%) authored by the FillForm support team
**Source:** `facebook-fillformvn-04_09_2026-{KrLeD3Ga,oi7lc84U}.zip` (fillform.info / app.fillform.info support inbox)
**Analysed:** 2026-09-10 · language: Vietnamese

---

## Executive summary

FillForm's inbox is three years of a support team doing, by hand and at volume, exactly
the job DoThesis's agent is supposed to do: take a Vietnamese student who half-understands
their own quantitative research model, work out in two or three messages what they
actually need, and hand back an answer they can defend to their supervisor. **40% of all
threads (2,428) discuss the research model itself**; 37% discuss sample size, 23% SPSS,
14% SmartPLS.

The moat is not the domain facts — thresholds are in every textbook. The moat is the
**consulting behaviour**: a triage question that lands before any advice (994 threads),
a routing rule that picks the statistical tool from the shape of the model, a set of
questionnaire defects the team can spot on sight of a Google Form link, an argumentation
stance that turns a marginal coefficient into a defensible paragraph rather than a
pass/fail verdict, and a delivery discipline (draft first, batch the edits) that
survives contact with an anxious student on a deadline.

One boundary has to be stated plainly. FillForm's paid service is manufacturing survey
responses that pass Cronbach's α, EFA, CR/AVE, HTMT and bootstrap — "cam kết data đẹp
pass hết biến, giả thuyết, kiểm định" — and at least one thread coaches a customer on
degrading fabricated data so a committee will not notice it ("nếu bạn lo bị ảo quá hội
đồng nghi ngờ thì có thể … giảm cron… cho chân thực"). **None of that is ported.** It
contradicts DoThesis's existing hard rule that `analysis_results` may only contain
numbers that came from `run_stats` on real data. What is ported is everything around it:
the triage, the teaching, the questionnaire diagnostics, the deference to the supervisor,
and the delivery discipline — plus, newly, a scripted way to answer the customer who
arrives asking DoThesis to do the fabrication, because these are the same students.

---

## Key themes

### Theme 1 — Triage before advice: one question splits the whole population

**Prevalence:** 994 threads open with the team's binary triage question; 627 threads contain an explicit SPSS-vs-SmartPLS routing decision.

**Summary.** The team almost never answers the question as asked. The first move is a
forced choice that determines everything downstream: *does this student need descriptive
statistics only, or do they have a model that has to be estimated?* A second triage
follows for the model case — where in the lifecycle are they?

**Supporting evidence:**

- *"Bạn cần điền form cơ bản theo tỉ lệ mong muốn hay cần điền form data đẹp để chạy mô hình nghiên cứu định lượng bạn nhỉ?"* — the single most-repeated substantive message in the corpus (452 verbatim repetitions).
- *"Nghiên cứu của bạn có chạy lượng hay chỉ có thống kê mô tả? … Tình trạng nghiên cứu của bạn? 01 Bạn đang xây dựng đề tài và cần người hỗ trợ A→Z. 02 Bạn đã chốt mô hình, bảng hỏi, bắt đầu thu khảo sát. 03 Bạn đã thu thập xong khảo sát nhưng dữ liệu xấu."*
- The 4-question intake brief used for complex cases: research type · progress so far · model + questionnaire link · then data requirements (software, tests, sample, items to drop, hypotheses to accept/reject, supervisor's special requirements).

**Implication.** DoThesis's bootstrap asks *what artifacts do you have*. FillForm asks
*where are you stuck, and does your work even need inferential statistics*. The second
question routes better, because a student who cannot answer it is exactly the student who
will otherwise be walked through a model they do not need.

---

### Theme 2 — The model's shape picks the software (and the student cannot do this themselves)

**Prevalence:** 550 academic user questions concern the model/variables; the routing rule appears verbatim across hundreds of threads.

**Summary.** Students ask "can you run SPSS" when their model requires PLS-SEM, or panic
because their supervisor teaches SPSS and their model has a mediator. The team has a
one-sentence rule they reuse constantly, and they state the consequence, not just the rule.

**Supporting evidence:**

- *"Mô hình hồi quy là mô hình chỉ có 2 biến độc lập và phụ thuộc thì mô hình này có thể chạy SPSS, các mô hình khác biến hồi quy được gọi là mô hình SEM (có các biến khác như biến trung gian, điều tiết, kiểm soát…). Các mô hình SEM như mô hình của bạn thì nên chạy smartpls để có thể kiểm định được cả giả thuyết trung gian."*
- *"Chỉ nên tự thao tác nếu mô hình của bạn đơn giản … Còn mô hình có biến kiểm soát hoặc biến bậc cao như mô hình của bạn thì không tự thao tác được ạ."*
- On second-order constructs: *"Nó là bước kỹ thuật của two-stage bạn ạ — stage 1 … chỉ chạy algorithm kiểm định loadings, CA, htmt, vif các biến bậc 1 thôi, chưa cần kiểm định giả thuyết. Đến stage 2, mới lấy bậc 2 có quan sát là các latent variable của bậc 1 …"*

**Implication.** DoThesis already computes this via `run_stats(op="method_advice")`. What
is missing is the *student-facing one-liner* — the sentence that makes the recommendation
land and survives being repeated to a supervisor.

---

### Theme 3 — Questionnaire defects are visible before a single response is collected

**Prevalence:** 544 academic user questions concern the scale/questionnaire; the team diagnoses from a raw Google Form link.

**Summary.** The team opens the form and reads defects off it in seconds. The same
handful recur, and each one silently destroys the dataset later.

**Supporting evidence (each a distinct defect the team names):**

- Screening question not isolated in its own section: *"Nếu bạn có câu gạn lọc như trong ảnh thì nên tách section ra nhé. Mình thấy bạn đang để chung các câu hỏi nhân khẩu học với thang đo, như vậy những người chọn không ở câu trên thì vẫn điền các thang đo mô hình và bạn mất công lọc để bỏ những mẫu đó."*
- Mixed response formats inside one construct: *"Các câu hỏi quan sát trong cùng một biến phải đồng nhất thang đo với nhau … Một câu thì dùng chọn nhiều đáp án, một câu thì chọn một thì không biết đo kiểu gì bạn nhỉ?"*
- Constructs with too few items: *"Các nhân tố nên có tối thiểu 3 biến quan sát là yêu cầu chuẩn mực để đảm bảo độ tin cậy và sự nhận diện của mô hình."*
- A construct in the model missing from the form: *"Sao trong form của bạn thiếu mất biến thái độ với ý định mua rồi ạ?"*
- Second-order construct wrongly given its own items: *"Nếu là biến bậc 2 thì đâu cần biến quan sát đâu bạn, vì đã có các biến độc lập … để đo lường và giải thích cho biến thay đổi nhận diện rồi."*
- Model/questionnaire naming drift: *"Bạn kiểm tra lại tên biến giữa mô hình và bảng hỏi nhé bạn."*
- The consequence of un-aggregatable items: *"Vốn dĩ phân tích tương quan hồi quy là phân tích mối quan hệ giữa các biến độc lập - phụ thuộc. Bắt buộc phải gộp lại thì mới phân tích được ạ, mà thang likert không giống nhau thì chỉ nên làm thống kê mô tả và cronbach thôi nha."*

**Implication.** DoThesis's `questionnaire-quality.md` lists textbook item-writing faults
(double-barreled, leading, anchor consistency). It does not list the *structural* faults
above, which are the ones that actually appear in Vietnamese student forms and the ones
`audit_instrument` cannot catch without being told to look.

---

### Theme 4 — A marginal number is an argument to be made, not a verdict to be announced

**Prevalence:** 113 questions on reliability, 82 on EFA, 185 on SmartPLS indices; the argumentation pattern recurs throughout the team's longest replies.

**Summary.** When a coefficient sits just outside a cutoff, the team does not say "fail,
drop it". They produce a short defensible paragraph combining the statistical evidence
with the theoretical meaning of the item — the exact paragraph the student will need at
the viva.

**Supporting evidence:**

- Loading just under threshold: *"AT3 có hệ số tải 0.4927, thấp hơn một chút so với ngưỡng 0.5. Tuy nhiên, giá trị này gần ngưỡng quy ước, đồng thời AT3 có ý nghĩa nội dung rõ ràng theo lý thuyết (mô tả đúng khái niệm Attitude toward eco-packaging)."*
- Keep-or-drop rule: *"Outer loadings nếu dưới 0.7 mà trên 0.4 thì mình sẽ cân nhắc xét thêm cronbach alpha và AVE nếu các kiểm định này oki thì vẫn giữ lại biến quan sát được nha bạn."*
- A high α defended rather than apologised for: *"> 0,9 thì cũng không có quá cao đâu bạn, với mô hình này thì CFA chỉ gồm hai nhân tố và thang đo khá đồng nhất nên các biến quan sát thường có mức liên kết rất mạnh."*
- Cross-loading argued from content: *"WP2 cross-loading sang PC, nhưng nội dung vẫn rõ ràng là 'sẵn sàng chi trả nếu giá bằng nhau', nên vẫn giữ trong WP."*
- A Fornell–Larcker breach explained theoretically: *"BI là tiền báo trực tiếp cho HL, điều này làm tăng tương quan giữa hai construct và có thể khiến √AVE(HL) < r(BI,HL). Trong ngữ cảnh lý thuyết này, sự gần gũi cao giữa hai biến là hợp lý và không nhất thiết chỉ ra sai sót đo lường."*
- And the honest stop, when the argument cannot be made: *"Mình đang dừng ở cronbach alpha mà loại hết các biến rồi, không cần chạy tiếp nữa vì chạy tiếp thì vô nghĩa."*

**Implication.** DoThesis's `output-interpretation.md` gives the thresholds and a
narration template ("value → meaning → fix or limitation"). It stops short of the move
that makes a student defensible: assembling the *keep-it* argument from loading + α + AVE
+ content validity, and knowing when no such argument exists.

---

### Theme 5 — The supervisor is the real authority, and the student's dominant emotion is fear of them

**Prevalence:** 327 threads where the user themselves raises their supervisor, department, or defence committee.

**Summary.** Every decision is provisional until the supervisor approves it. Students
delay work waiting for approval, ask for numbers to be reshaped to match what the
supervisor expects, and are afraid of being asked a question they cannot answer.

**Supporting evidence:**

- *"Ad chờ mình tầm 1-2 ngày, để mình chốt lại mô hình và bảng câu hỏi lại với gvhd rồi mình sẽ tiến hành làm nha"*
- *"Mình đang có 1 quan ngại là vì thầy mình hướng dẫn sinh viên chạy spss nên nếu mình chạy 1 phần mềm khác thì có thể thầy sẽ không đồng ý…"*
- *"Em chưa bao giờ học và cũng chưa phân tích số liệu và chạy spss như này. Sau khi có kết quả cuối, em định nhờ AI diễn giải cách thức để phòng trường hợp bị hội đồng hỏi."*
- *"Ui thầy tui bữa h dạy spss thoi h qua smartpls không biết có bị hỏi không nữa🥲"*
- *"Bạn cứ giữ nguyên form, mô hình và giả thuyết cô đã duyệt giúp mình nhé."*
- The team's own deference: *"Về mặt thang đo và mô hình bạn nên trao đổi và chốt kĩ với GVHD sẽ chính xác nhất nha."* and *"Cái này bạn tìm hiểu thêm về cách đọc thông số SPSS nha, như vậy khi thầy hỏi bạn cũng trả lời được ạ."*

**Implication.** DoThesis already has an advisor-feedback loop and a mock-committee
skill — the strategically correct bets. The corpus adds two things the current skills
lack: an explicit rule that a supervisor-approved model outranks the agent's own
recommendation, and a real, observed question bank for defence prep (the anxieties above
are the questions students actually fear).

---

### Theme 6 — Delivery discipline: draft first, batch the edits, reset the scope

**Prevalence:** 661 threads use draft-first delivery; 376 explicitly ask for edits in one batch; 102 contain an explicit scope reset.

**Summary.** The team never delivers into the live artifact first. They work on a copy,
hand it over for review, ask for *all* corrections at once, and only then commit to the
real one. When a customer's expectation drifts past what was bought, they restate the
scope kindly and immediately.

**Supporting evidence:**

- *"Ad làm ở bản nháp rồi bạn check xem kết quả ok chưa nha rồi ad điền vào form chính của bạn ạ"*
- *"Bạn kiểm tra cần chỉnh sửa gì note lại một lượt để bên mình điều chỉnh cho bạn nhé ạ"*
- *"Điền form theo tỷ lệ cơ bản chỉ cam kết đúng theo tỷ lệ bạn mong muốn, phù hợp làm thống kê mô tả cơ bản thôi nhé. Mỗi tính năng sẽ đáp ứng đúng tính năng nó mang lại nhé bạn."*
- Warranty flow, stated as a process: *"khách feedback → ghi nhận → khắc phục gấp (<8h) → duyệt → hoàn thành"*, with the boundary named (*"thay đổi lớn như thay đổi về mô hình, bảng hỏi và cỡ mẫu … mình phụ phí tùy vào mức độ"*).

**Implication.** Directly transferable to the agent's revision behaviour: propose on a
draft, collect the full edit list in one pass, and say plainly what a given step does and
does not deliver.

---

## Insights → opportunities

| Insight | Opportunity | Impact | Effort |
|---|---|---|---|
| One triage question routes the whole population; DoThesis's entry asks for artifacts instead | Add the "descriptive-only vs model" + "where are you stuck" triage to bootstrap/router | High | Low |
| Model shape → software is a rule students cannot apply and supervisors will challenge | Ship the one-liner alongside `method_advice`'s ranked output | High | Low |
| Six structural questionnaire defects recur and are visible pre-fielding | Extend `questionnaire-quality.md`; teach `audit_instrument` follow-up prompts | High | Low |
| Marginal numbers need a keep-it argument, not a verdict | Add the argumentation pattern + worked cases to `output-interpretation.md` | High | Low |
| Supervisor authority outranks the agent; fear of the committee is the dominant emotion | Add an advisor-precedence rule; seed defence prep with the observed anxieties | High | Low |
| Draft-first + batched edits reduce rework and anxiety | Codify as revision protocol in the router skill | Medium | Low |
| The same students will ask DoThesis to fabricate passing data | Script a warm, non-preachy redirect instead of leaving it to improvisation | High | Low |
| 21 threads ask for coefficients to be reshaped to a target | Treat "make α ≈ 0.8" as a request to *interpret and defend*, not to alter | Medium | Low |

---

## User segments identified

| Segment | Characteristics | Needs | Rough size |
|---|---|---|---|
| Descriptive-only | No model; needs counts and percentages | To be told they do not need SEM at all | ~1 in 4 of triaged threads |
| Model not yet approved | Has a draft model, waiting on supervisor | Help closing the model, and patience about the approval gate | Large — 327 threads name the supervisor explicitly |
| Model locked, collecting data | Model + questionnaire approved, fielding | Questionnaire QA, sample-size justification | The core case |
| Data collected, results ugly | Has real responses, tests failing | Screening, keep/drop arguments, honest limitations | The highest-value case for DoThesis |
| Stats-anxious writer | Never studied statistics; must present results | Two-register explanations; defence rehearsal | Cuts across all of the above |

---

## Recommendations

1. **(High) Port the consulting behaviour as a first-class reference, not scattered edits.** The playbook — triage, routing one-liner, deference, delivery discipline, integrity redirect — belongs in one file the router skill points at, so it is read on every thesis conversation. → `skills/dothesis/references/support-playbook.md`.
2. **(High) Extend the questionnaire checklist with the six structural defects.** They are pre-fielding, cheap to catch, and fatal afterwards. → `skills/dothesis-m3-design/references/questionnaire-quality.md`.
3. **(High) Teach the keep-it argument in M4.** Thresholds already exist; the argumentation stance does not. → `skills/dothesis-m4-analysis/references/output-interpretation.md`.
4. **(Medium) Seed the mock committee with observed anxieties**, not textbook viva questions. → `skills/dothesis-defense/SKILL.md`.
5. **(Medium) Do not port the data-fabrication service or its detection-evasion advice.** Keep M4's existing hard rule, and add the redirect script so the refusal is warm and useful rather than improvised.

---

## Questions for further research

- Conversion: which triage branch actually converts, and where do threads die? The export carries no order/outcome labels beyond sparse `auto-label` lines, so funnel analysis is not possible from this data alone.
- Response latency and its effect on outcome (timestamps are present; outcomes are not).
- How often the supervisor rejects work after delivery — visible only anecdotally here.
- Whether students who received a *teaching* answer return with fewer follow-ups than those who received a *do-it-for-me* answer.

## Methodology notes

- Both archives were parsed; the `oi7lc84U` export contains media attachments only, so all message analysis is from `KrLeD3Ga`. Facebook's export mojibake (UTF-8 read as Latin-1) was repaired before analysis.
- Topic prevalence is regex tagging over Vietnamese keyword families, counted at thread level; a thread can carry several tags. Counts are indicative of prevalence, not precise classification.
- Quotes are reproduced verbatim from the team's own messages; customer names and identifying details are not reproduced.
- Limitation: this is a support inbox, so it over-represents users who hit friction and under-represents users who succeeded silently. Themes describe what students *ask about*, not the full population of what they do.

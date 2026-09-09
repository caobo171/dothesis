# Expansion axes

Which templates multiply into real pages, which collapse to zero, and the evidence
for each. All measurements Vietnam / `vi`, location code 2704, 2026-09-07, from
`docs/seo/topic-bank/`.

## How to read this

An axis is worth using when three things hold at once:

1. **The population is large.** Dozens to hundreds of units, not five.
2. **Each unit has its own query with measurable volume.** Proved by the gate, per
   unit, not assumed from the head term.
3. **Each page can say something genuinely different.** If two pages differ only by
   a swapped noun, the axis has failed test 3 even when it passes 1 and 2.

Test 3 is the one that gets skipped, and it is the one Google's doorway-page and
scaled-content-abuse policies are written about.

For this market the unit is a **methodological unit**: a statistic, a procedure, a
test, a model, a construct, a thesis section, a symptom. Each has its own
threshold, its own output table, its own failure mode. `Cronbach's Alpha` and
`EFA` are not the same document with a noun swapped, which is exactly why this
axis set works where audience segmentation does not.

## Validated axes

Each axis is one file under `docs/seo/topic-bank/axes/`, with columns `unit`,
`display`, `templates` (semicolon separated, `{unit}` and `{display}`
placeholders), `category`, `archetype`, `family`.

### Statistical term, about 200 units

| | |
|---|---|
| Templates | `{unit} là gì`, `{unit} trong spss`, `{unit} bao nhiêu là tốt` |
| Archetype | `term-la-gi` |
| Evidence | 139 of the 407 harvested keywords are `là gì` pages: độ lệch chuẩn, outlier, moderator, mediator, AVE, p-value, PLS, SEM, EFA, eigenvalue, communality. `d f` at 22,200 and `scale là gì` at 4,880 are the size of this shape |
| Distinctness | High. Each statistic has its own threshold, its own output column, its own failure mode |

The pattern to notice: the page targets the Vietnamese long-tail phrase and absorbs
the bare English term as a bonus. `df là gì` is the page; `d f` at 22,200 is what it
picks up.

### SPSS procedure, about 60 units

| | |
|---|---|
| Templates | `cách chạy {unit} trong spss`, `phân tích {unit} spss`, `{unit} trong spss` |
| Archetype | `spss-howto`, or `test` for the kiểm định family |
| Evidence | `spss` 14,800, `cách chạy spss` 480, `anova` 2,400, `t-test` 1,000, `hồi quy tuyến tính` 1,000 |
| Distinctness | High. Different menu path, different dialog, different output tables, different assumptions |

### SmartPLS procedure, about 40 units

| | |
|---|---|
| Templates | `{unit} trong smartpls`, `cách chạy {unit} smartpls 4` |
| Archetype | `smartpls-howto` |
| Evidence | `smartpls` 2,400, `pls-sem` 720, and `moderator` at 5,400 reached through a SmartPLS 4 page in the harvest |
| Distinctness | High, and the version matters: SmartPLS 3 and 4 moved menus, so say which one the path belongs to |

Smaller population than SPSS and higher value per page: SmartPLS content in
Vietnamese is thin, the reader is a master's student who has already committed to
PLS-SEM, and the pages map onto M3 and M4 directly.

### Theory or model, about 60 units

| | |
|---|---|
| Templates | `mô hình {unit}`, `lý thuyết {unit}`, `{unit} là gì` |
| Archetype | `model-theory` |
| Evidence | `mô hình nghiên cứu` 720 as the head; TAM, TPB, UTAUT, SERVQUAL are the models Vietnamese business theses actually use |
| Distinctness | High. Different constructs, different original scales, different hypotheses |

Every model page cites its original author from the allowlist. A model whose
original source is not yet in `canonical-sources.md` gets that entry added,
checked, before the page is written. The axis file lists the model either way, so
the missing-source gap is visible in `report` rather than silently dropped, and
the writer's fallback is to describe the constructs with no author and no year
rather than to guess one.

### Construct and scale, about 120 units

| | |
|---|---|
| Templates | `thang đo {unit}`, `{unit} là gì` |
| Archetype | `scale` |
| Evidence | `thang đo likert` 1,600, `scale là gì` 4,880, `thang đo` present across the harvest |
| Distinctness | Medium to high. The item pool and the source scale differ per construct. Two constructs measured from the same paper with the same five items are one page, not two |

This is the axis where test 3 is most at risk. If the only difference between
`thang đo sự hài lòng` and `thang đo sự trung thành` would be the noun, merge them
into one page about that model's scales.

### Thesis section, about 40 units

| | |
|---|---|
| Templates | `cách viết {unit} luận văn`, `{unit} trong luận văn là gì` |
| Archetype | `thesis-writing` |
| Evidence | `khóa luận tốt nghiệp` 2,900, `luận văn thạc sĩ` 1,000, `abstract` at 8,100 in the harvest, `viết luận văn` 140 |
| Distinctness | High. Each section has its own structure, its own sample sentences, its own examiner questions |

### Survey and data collection, about 30 units

| | |
|---|---|
| Templates | `{unit} khảo sát`, `cỡ mẫu {unit}` |
| Archetype | `survey` |
| Evidence | `phiếu khảo sát online` 14,800, `biểu mẫu khảo sát` 9,900, `form khảo sát` 6,600, `cỡ mẫu là gì` 4,400, `bảng câu hỏi khảo sát` 170 |
| Distinctness | Medium. Keep the population small and each page tied to a decision |

The largest single volume block in the harvest, and xulysolieu.info ranks it with
**one Google Forms page**. This is fillform.info's territory: our own form product,
named as ours in Vietnamese survey posts, with Google Forms named honestly as the
alternative.

### Troubleshooting symptom, about 40 units

| | |
|---|---|
| Templates | `{unit} phải làm sao`, `lỗi {unit} spss` |
| Archetype | `troubleshoot` |
| Evidence | `ma trận xoay` 6,600, and its long tail `ma trận xoay lộn xộn`, `ma trận xoay không hội tụ` |
| Distinctness | High. Different symptom, different causes, different fixes |

The highest-intent axis in the set. The reader is stuck at eleven at night and will
try what the page says immediately.

### Topic list by field, about 30 units

| | |
|---|---|
| Templates | `đề tài luận văn {unit}`, `đề tài nghiên cứu khoa học {unit}` |
| Archetype | `topic-list` |
| Evidence | `khóa luận tốt nghiệp` 2,900, `đề tài luận văn` present across the harvest with no volume of its own on the head phrasing |
| Distinctness | Medium. A marketing topic list and an accounting topic list are genuinely different content **only if** each topic carries its variables, its model and its data source. A bare list of titles is the same page twice |

Cap this axis at 30 fields and enforce the variables-and-model rule, or it turns
into the listicle farm the competitors already run.

## The depth budget

The most useful rule here and the least obvious. **A dimension multiplies once. The
second cross is dead.**

| Level | Query | Status |
|---|---|---|
| head | `hồi quy tuyến tính` | 1,000 |
| one cross, tool | `cách chạy hồi quy trong spss` | a page |
| one cross, symptom | `hồi quy bị đa cộng tuyến` | a page |
| **two crosses** | `cách chạy hồi quy trong spss cho sinh viên marketing` | **not a page** |
| **two crosses** | `cách chạy hồi quy trong spss 26 cho luận văn thạc sĩ` | **not a page** |

The unit crossed with the tool is a query a student types. The unit crossed with
the tool crossed with a course or a year is a phrase a content marketer types. Only
the gate can tell those apart, and the answer is never guessable, so the rule is
mechanical: **one cross, then stop**.

## Rejected axes

### Audience segmentation

Per university, per year of study, per major, per "sinh viên" versus "học viên
cao học". Fails test 2 in every market this has been measured in, and fails test 3
as well: the article for a marketing student and the article for an accounting
student would differ by the example variable names.

Use the audience as an **angle inside** a page that already has demand. A regression
how-to can carry a marketing example. It does not become its own URL.

### Software version pages

`spss 20`, `spss 22`, `spss 26`, `spss 27`. The pages would differ by a screenshot
and a menu label. That is the definition of a doorway set. Version differences
belong **inside** the procedure page, as a line saying which versions moved the
menu.

The one exception is SmartPLS 3 versus 4, where the interface genuinely changed
enough that the steps differ, and even there it is one sentence inside the page,
not two pages.

### Download and crack pages

`tải spss` 1,900, `spss download` 2,900, `cách tải spss` 880 and the crack variants
carry real volume and phamlocblog ranks number 2 for `spss` with one. They are
excluded permanently: distributing or instructing on cracked IBM software is
off-brand for a product students trust with their thesis, and it is legally
exposed. `exclusions.txt` drops them from the harvest so nobody re-adds them by
accident.

### Service pages

`dịch vụ spss` 1,900, `dịch vụ chạy spss`. Not because the volume is not real, but
because DoThesis is not a done-for-you service and a page targeting that query
would either lie about what we sell or bounce. The comparison belongs **inside**
how-to pages, honestly: what a service costs, what it risks at the defence, what
doing it yourself costs in hours.

### Answer keys and off-topic harvest rows

The competitors rank for TOEIC answer keys (`đáp án ets 2016 part 1234` at 27,100
is the single biggest row in the harvest), school algebra, programming syntax and
brand noise like `loc`. Volume without relevance. `exclusions.txt` carries a regex
per family, with a comment saying why.

## Total addressable page count

Sized 2026-09-07, then re-counted on 2026-09-08 after the axes were extended.
The right-hand column is what the files actually hold today, not an estimate.

| Source | Pages | Units on 2026-09-08 |
|---|---:|---:|
| Harvest after exclusions and clustering | about 250 | 407 distinct keywords, minus off-topic, clustered by intent |
| Statistical term | 200 to 260 | 268 |
| SPSS procedure | 70 to 96 | 96 |
| SmartPLS procedure | 40 to 56 | 56 |
| Theory or model | 80 to 130 | 130 |
| Construct and scale | 90 to 161 | 161 |
| Thesis section | 50 to 64 | 64 |
| Survey | 30 to 42 | 42 |
| Troubleshooting | 55 to 78 | 78 |
| Topic list | 40 to 51 | 51 |
| **Total** | **about 900 to 1,300** | 946 axis units |

The field axis carries 51 entries against the 30 this table first estimated.
The estimate was a guess at how many fields are taught in Vietnam, not a limit,
and the rule that governs the axis is the one below it: a field earns a page
when its vocabulary and its topic list are its own. Kế toán and điều dưỡng pass
that test. A second page for the same field under a synonym does not.

The target is 1,000 and the instruction is to **stop at the honest ceiling**
rather than pad. Under the rule in force since 2026-09-08 that ceiling is the
number of genuine units the domain supplies, not the number a keyword tool can
price. If the axes and the harvest yield 780 distinct pages, the bank is 780.

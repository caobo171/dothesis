# SERP observations, 2026-09-08

Competitor research for this blog is now done in a browser, not through a paid
keyword API. This file is the method demonstrated on six queries, and the
evidence behind the rule change recorded in the design spec.

## The method

For a topic you are about to write:

1. Search the exact Vietnamese query on Google, logged out, `hl=vi&gl=vn`.
2. Read page one. For each of the top results record four things: who owns the
   page, what shape it is (definition, procedure, troubleshooting, list,
   service page), how deep it goes, and what it does not answer.
3. Look at what Google itself puts above the results. An AI Overview is a
   structured summary of what Google currently treats as the answer, so its
   headings are the sections a competing page has to cover at minimum.
4. Note the non-article results. Videos, a Facebook thread of students asking
   the same thing, and a forum post are demand signals that no keyword tool
   reports.
5. Write down what is missing. That gap is the reason your page exists, and it
   goes in the brief.

Take the question, never the answer. Reading a competitor's page in a browser
makes copying easier than a keyword export ever did, so the rule matters more
now, not less. Their heading outline tells you the depth a reader expects.
Their sentences are theirs.

## What the six queries showed

Every query below was rejected or near-rejected by the paid demand gate on
2026-09-07. All six have competitive page-one results built by the four
incumbents.

| Query | Paid gate verdict | What page one actually holds |
|---|---|---|
| `cronbach alpha trong spss` | no volume, would have loaded as a permanent draft | Dedicated pages from Phạm Lộc Blog, Xử Lý Định Lượng, Xử Lý Số Liệu, Hỗ Trợ SPSS and mosl.vn, plus an AI Overview with five sections and a tutorial video |
| `ma trận xoay lộn xộn phải làm sao` | dropped | A dedicated Phạm Lộc Blog page, four of their videos on the exact symptom, a manhhungdigi page, and a Facebook thread of students asking it in those words |
| `biến điều tiết trong smartpls` | volume 10, bottom of the pile | Two Phạm Lộc Blog pages, one per SmartPLS version, a phantichspss page, and four long videos including a 1:36:00 lecture |
| `cỡ mẫu efa` | dropped | Two Phạm Lộc Blog pages and a phantichspss page, all three citing Hair et al. for the 5:1 and 10:1 rules |
| `cách viết mở đầu luận văn` | dropped | Studocu, Tri Thức Cộng Đồng, Kiemtratailieu and a university PDF, all with a numbered five-part structure |
| `thang đo lòng trung thành khách hàng` | dropped | **Different intent.** Page one is CRM and marketing metrics (NPS, CSAT, retention rate) from Gimasys, BSC Designer and kingofficehcm, not a research measurement scale |

## What the sample means

**Five of the six are real topics the paid gate threw away.** Volume of zero
meant "the tool has no row for this string", not "nobody searches this". The
incumbents did not build those pages by accident, and one of them is a query
students type verbatim into a Facebook group.

**The sixth is the case that justifies still doing research.** Nothing measured
would have told you that `thang đo lòng trung thành khách hàng` returns a
marketing SERP. A DoThesis page on the research scale would be competing on an
intent it does not serve. The right move there is to keep the page and target
the phrasing a thesis student uses, or to fold the construct into a broader
scale article. One minute in a browser produced a judgement no volume number
contains.

**Videos and forum threads are part of the reading.** On
`ma trận xoay lộn xộn`, the incumbent's four videos and the student thread are
better evidence of demand than any number, and they also show the format the
reader wants: symptom first, cause second, fix third.

## How this feeds the pipeline

Measured volume, where it exists, still decides which page gets written first,
because a page with a known query returns value sooner. It no longer decides
whether a page exists. That decision is the three gates in
`.claude/skills/dothesis-content-pipeline/SKILL.md`, and the distinctness half
of it is enforced mechanically by the corpus mode of the QA gate.

The committed harvest in this directory stays useful as an ordering signal and
as a record of what the incumbents ranked for on 2026-09-07 and 2026-09-08. It
is a snapshot, not a gate.

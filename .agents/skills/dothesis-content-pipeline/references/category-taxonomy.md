# Blog category taxonomy

Without a taxonomy a content batch is landfill. This file is the rule for what a
category is, the nine that exist, and the boundary against the product surface.

All volumes Vietnam / `vi`, measured 2026-09-07, in
`docs/seo/topic-bank/measured-heads-2026-09-07.tsv`.

## The rules

> **A category exists only if its own name has measured search volume.**

A category page is a page. It has to rank for something, and the thing it ranks for
is its name. A category named after the company can never rank, so it is
navigation, not a content asset, and it does not get a route.

> **One query, one URL.** If a category targets a head term, no post may also
> target it. The post takes a longer phrasing or it does not exist.

> **Ten posts or fold it.** A category that cannot honestly reach ten posts is
> folded into a broader one rather than shipped thin.

## The nine

| Slug | Display name | Target query | Volume | What lives here |
|---|---|---|---:|---|
| `spss` | SPSS | spss | 14,800 | Every SPSS procedure, test and error. The biggest bucket by far |
| `thong-ke` | Thống kê | thống kê | 14,800 | Statistical terms and concepts that are not tied to one tool |
| `khao-sat` | Khảo sát | khảo sát | 6,600 | Questionnaire design, sampling, data collection, cleaning |
| `nghien-cuu-khoa-hoc` | Nghiên cứu khoa học | nghiên cứu khoa học | 6,600 | Research method, design, ethics, the scientific-paper end |
| `khoa-luan-tot-nghiep` | Khóa luận tốt nghiệp | khóa luận tốt nghiệp | 2,900 | Undergraduate thesis writing and structure |
| `smartpls` | SmartPLS | smartpls | 2,400 | PLS-SEM procedures, SmartPLS 4 steps, PLS reporting |
| `phan-tich-du-lieu` | Phân tích dữ liệu | phân tích dữ liệu | 1,600 | Analysis planning, choosing a test, cross-tool comparisons |
| `luan-van-thac-si` | Luận văn thạc sĩ | luận văn thạc sĩ | 1,000 | Master's-level thesis writing, defence, supervisor work |
| `mo-hinh-nghien-cuu` | Mô hình nghiên cứu | mô hình nghiên cứu | 720 | Theories, models, constructs, scales, hypotheses |

Route: `/blog/{locale}/chu-de/{slug}`. Nine categories, every one of which names
something people search for, and the top four alone carry over 32,000 searches a
month at difficulty 0 to 4.

## Assigning a post to a category

One category per post, chosen by **which tool or artefact the post is about**, not
by which words appear in it. Almost every post mentions SPSS.

| If the post is about | Category |
|---|---|
| A menu path, a dialog, an output table in SPSS | `spss` |
| A statistic or a concept, tool-independent | `thong-ke` |
| The questionnaire, the sample, the responses | `khao-sat` |
| Method and design at the study level | `nghien-cuu-khoa-hoc` |
| Writing an undergraduate thesis | `khoa-luan-tot-nghiep` |
| Anything in SmartPLS or PLS-SEM | `smartpls` |
| Choosing between analyses or tools | `phan-tich-du-lieu` |
| Writing or defending a master's thesis | `luan-van-thac-si` |
| A theory, a model, a construct, a scale | `mo-hinh-nghien-cuu` |

Ambiguity resolves toward the **tool** category when a tool is named in the query,
because that is what the searcher typed. `cách chạy EFA trong SPSS` is `spss`, not
`thong-ke`. `EFA là gì` is `thong-ke`.

`plan` assigns the category from the axis file and the harvest row, so a
misassignment is a one-line fix in the axis TSV, not a per-post decision.

## Category page anatomy

Same shape for all nine, because a category that is only a filtered list ranks for
nothing.

1. An `<h1>` matching the target query near verbatim.
2. **300 to 500 words of hand-written Vietnamese intro** in `categories.json`. Why
   this area is hard, what order to approach it in, which posts to start with. This
   is the part that is not generated and not skipped.
3. The post list as real server-rendered anchors, not a client fetch.
4. Links across to sibling categories and up to `/blog/vi`.
5. A self-referencing canonical and an entry in the sitemap.

## The product boundary

DoThesis's product surface is `/landing`, `/chat` and the app. Those target
**transactional intent**: someone looking for something to do the work.

Blog categories target **informational intent**: someone looking for how, why, what
threshold, what to write.

Where both could chase one phrase, the product page keeps the transactional head
term and the blog category takes the informational one. `dịch vụ chạy spss` at 1,900
is transactional and belongs to neither: it is a service query and DoThesis is not a
service, so no URL chases it. See the rejected axes in `expansion-axes.md`.

Never let two DoThesis URLs chase one query. At a thousand posts that failure
multiplies faster than anything else in this pipeline.

## Before proposing a tenth category

1. Measure its name. No volume, no route.
2. Check it does not duplicate one of the nine or a product page.
3. Confirm ten posts will sit under it.
4. Write the intro by hand. If there is nothing honest to say about why the
   category exists, it does not exist.

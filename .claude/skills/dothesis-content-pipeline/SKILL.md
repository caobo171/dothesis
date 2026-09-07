---
name: dothesis-content-pipeline
description: >
  Use when scaling the DoThesis blog in batches rather than writing one article:
  harvesting competitor topics, expanding a methodological unit into a family of
  pages, gating candidates on measured search volume, planning a backlog, running
  the scripted writer, and publishing in tranches. Triggers on "scale the blog",
  "content bank", "nhân bản content", "batch bài viết", "content engine",
  "expand axis", "chạy demand gate", or any request to produce many DoThesis
  articles at once. For a single article use `dothesis-blog-content`; this skill
  applies that skill's rules per post through the writer.
---

# DoThesis content pipeline

## What this skill is for

`dothesis-blog-content` produces one good article. This skill decides **which
articles exist at all**, proves each one has demand before it is written, and stops
the batch from becoming a liability.

Read `dothesis-blog-content` too. Every post this pipeline queues is written to
that skill's structure, voice and citation rules; the writer's prompt is literally
built from those files at run time, so editing them changes the next batch.

## The one rule that makes this safe

> **No page gets written without measured search volume for its own primary query.**

This is not caution. Publishing hundreds of pages nobody searches for is what
Google's spam policy calls **scaled content abuse**, the policy covers
human-written pages as well as generated ones, and the penalty is domain-wide. A
thousand measured pages is an asset. A thousand pages of which four hundred have no
query is a manual action waiting for a reviewer.

The engine enforces it. `gate` refuses to pass a keyword with no volume, `plan`
only reads gate survivors and the harvest, and a row that cleared on its family
rather than on itself — the thin-keyword aggregate rule, or `--fill-unmeasured` —
is stamped `gate_status = family-inferred`, inserted as DRAFT and never scheduled
until it is measured on its own.

## The market, measured 2026-09-07

Vietnam, `vi`, location code 2704, through DataForSEO. Everything is committed
under `docs/seo/topic-bank/`.

Four sites own this space:

| Domain | Ranking keywords in the harvest |
|---|---:|
| xulysolieu.info | 426 |
| phamlocblog.com | 229 |
| phantichspss.com | 229 |
| xulydinhluong.com | 123 |

Their top 100 rows each were pulled: **752 rows, 407 distinct keywords, 278
distinct pages**. 142 keywords clear 1,000 a month and 264 sit between 100 and 999.
**Keyword difficulty is 0 to 4 almost everywhere**, which is the finding that makes
this market worth entering at all: the incumbents rank on coverage, not on
authority.

Head terms: `spss` 14,800, `thống kê` 14,800, `khảo sát` 6,600, `nghiên cứu khoa
học` 6,600, `khóa luận tốt nghiệp` 2,900, `smartpls` 2,400, `thang đo likert` 1,600,
`phân tích dữ liệu` 1,600, `cronbach alpha` 1,300, `phương pháp nghiên cứu` 1,300,
`hồi quy tuyến tính` 1,000, `luận văn thạc sĩ` 1,000, `mô hình nghiên cứu` 720,
`pls-sem` 720.

The archetypes that rank are in `dothesis-blog-content/references/structure.md`.
The axis populations behind them are in `references/expansion-axes.md`. The nine
categories and their measured names are in `references/category-taxonomy.md`.

## What "copy the competitor's articles" may and may not mean

**Allowed, and the whole basis of this pipeline:** harvest their topic list. Which
queries they rank for, which URL answers each, how deep the page goes, what the
heading outline covers.

**Not allowed:** reproducing their text, or paraphrasing an article closely enough
that it is the same document in new words. That is copyright infringement, and
separately it does not rank, because Google consolidates duplicates and the older,
stronger URL wins.

The line: **take the question, never the answer.** Then answer it from DoThesis's
own material, which is where the threshold table with its citation, the worked
output block and the `cách viết vào luận văn` paragraph earn their keep. The
competitor URL in a backlog row is a *question hint*, nothing else. Never fetch it
into the writer's context.

## Realistic scale

The harvest yields roughly 250 on-topic pages after clustering. The axes yield
another 400 to 700 after the gate. **The run targets 1,000 posts and stops at the
gate's ceiling if that is lower.** It never pads to hit a round number.

Crawl budget is the constraint on the far side, not writing capacity. Publishing
faster than Google crawls converts effort into "Discovered, currently not indexed".
`create` schedules 40 a week for that reason, and the staging gates below decide
whether the next tranche goes out at all.

## Workflow

### 1. Harvest (already done, redo per quarter)

Through OpenSEO MCP, one call per competitor:

```
get_ranked_keywords(projectId, target: "<domain>", locationCode: 2704,
                    languageCode: "vi", limit: 100, sortBy: "search_volume",
                    resultTypes: ["organic"])
```

The response exceeds the token limit and is auto-saved to a file. Aggregate it with
`jq` or a subagent per competitor, and land it as a TSV under
`docs/seo/topic-bank/` so the batch is reproducible. Never hand-edit the harvest:
add exclusions to `exclusions.txt` instead, so the reason a row was dropped is
committed.

### 2. Expand along an axis

```bash
cd api && ./run.sh python -m app.blog.content.cli expand
```

Reads every `docs/seo/topic-bank/axes/*.tsv` and writes `candidates.tsv` by
crossing each unit with its phrasing templates. Adding a unit to an axis file is
how the pipeline grows. Read `references/expansion-axes.md` before adding an axis;
the three tests there are what keep this from becoming a doorway-page farm.

### 3. Gate. Mandatory.

```bash
# five known keywords first, and read the printed cost before anything bulk
cd api && ./run.sh python -m app.blog.content.cli gate --source dataforseo --probe
cd api && ./run.sh python -m app.blog.content.cli gate --source dataforseo
```

DataForSEO's Google Ads search-volume endpoint, up to 1,000 keywords per request,
`location_code 2704`, `language_code vi`. Every response's `cost` field is printed
and totalled. OpenSEO is the fallback for small lists at about 1.7 credits a
keyword, not the bulk tool.

**Check the probe first.** On 2026-09-08 it returned `HTTP 402`, body
`status_code 40200, "Payment Required"`: the credentials are valid and the
account has no balance. Until it is topped up, measure through OpenSEO and feed
the result in with `gate --source tsv --file measured.tsv`, or work from the
harvest, whose volumes are already measured. Do not write pages while the gate
cannot answer.

Cut rules:

- **No volume returned, drop.** Not "write it anyway, it is cheap". Drop.
- **Under 10 a month, drop**, unless the family aggregate clears 500 and each page
  is genuinely distinct. Survivors on that rule are `family-inferred`.
- **Difficulty above 40, defer.** Google Ads volume carries no difficulty, so this
  applies only to rows measured through OpenSEO.

Output is `gate-{axis}.tsv` with `keyword`, `search_volume`, `verdict`, `reason`.
Commit it. The gate file is the evidence that a page was allowed to exist.

When the budget only stretches to a sample of the candidates, add
`--fill-unmeasured` to `gate --source tsv`. A candidate absent from the measured
TSV is then judged on its family: it needs at least three measured siblings, at
least half of them passing on their own, and a family aggregate over 500, or it
drops. Survivors are `family-inferred` like the thin-keyword ones, and the summary
counts measured, family-inferred and unmeasured-filled passes separately so you
can see how much of the bank is inference. Without the flag an unmeasured
candidate is still a plain drop — reach for it only when measurement is genuinely
blocked, not to make a thin axis look bigger.

### 4. Plan

```bash
cd api && ./run.sh python -m app.blog.content.cli plan
```

Merges the harvest, minus `exclusions.txt`, with the gate survivors; clusters
phrasings of one intent into a single page and keeps the losers as
`secondary_keywords`; assigns category and archetype; picks 3 to 5 siblings;
orders category round-robin by volume so the first tranche is the best page of
every category; writes `backlog.tsv`.

**Read the top 30 rows by hand before writing anything.** The clustering is
mechanical and it will occasionally merge two intents that deserve separate pages,
or split one that does not.

### 5. Dedupe against what exists. Mandatory.

```bash
cd api && ./run.sh python -m app.blog.content.cli plan   # skips slugs already in docs/blog-index.md
cd api && ./run.sh python -m app.blog.cli audit-seo --locale vi
```

A topic the audit lists as covered is a post to improve, not to write again. The
admin upsert route enforces the same rule at 0.6 overlap within one intent class,
so a duplicate that gets past the plan still gets refused at insert.

### 6. Write

```bash
cd api && ./run.sh python -m app.blog.content.cli write \
  --backlog docs/seo/topic-bank/backlog.tsv \
  --out api/data/blog-seeds/vi/posts --limit 5
```

Start at five. Read all five end to end. Fix the skeleton or the voice file, then
re-run those five with `--force`. Only then go to 50, then to the rest with
`--budget-usd 40`.

The writer is resumable: a row whose seed file already exists is skipped, so the
command can be interrupted and re-run. It stops on `--limit`, on the budget, and
on nothing else. `write-log.tsv` records `slug`, `status`, `attempts`,
`prompt_tokens`, `output_tokens`, `usd`, `seconds`, `failures` for every row.

A post that fails QA gets exactly one repair call carrying the failure list. If it
fails again it lands in `rejected/` and the run continues. Read `rejected/` after
every batch: three rejects with the same failure means the prompt is wrong, not the
model.

### 7. Gate the batch mechanically

```bash
python3 .claude/skills/dothesis-content-pipeline/scripts/qa_seeds.py api/data/blog-seeds/vi/posts
```

Exit 0 required. The rule list is in `dothesis-blog-content/references/voice.md`
and `seed-schema.md`; the implementation is `api/app/blog/content/qa.py`. The shim
runs on plain `python3`, no venv, because it is also the pre-publish check.

Then read ten posts by hand, chosen across archetypes, specifically for
**swapped-noun sameness**: two pages in one family that differ only by the term.
The QA script cannot see that and it is the failure that gets a domain classified
as scaled content abuse.

### 8. Publish in tranches

```bash
cd api && ./run.sh python -m app.blog.cli create --dir ../api/data/blog-seeds/vi/posts \
  --schedule-start <tomorrow> --per-week 40
cd api && ./run.sh python -m app.blog.cli export-index
cd api && ./run.sh python -m app.blog.content.cli report
```

Backlog priority order, so the highest-volume page of every category is in the
first tranche. The nine category pages go live with it, or the posts have nothing
to link up to.

A seed whose `gate_status` is `family-inferred` is inserted as a DRAFT — status 0,
no `published_at`, no `scheduled_at` — and does not consume a publishing slot; the
slot counter advances for measured seeds only, so a tranche of 40 is 40 real
pages rather than however many survived the mix. `create --reschedule` walks
status 2 and leaves the drafts where they are. `plan` already orders every
inferred row after every measured one for the same reason. A draft leaves this
state one way: measure its keyword, set `gate_status` to `measured`, and re-run
`update-from-seed`. It is written and waiting, not published on a guess.

### 9. Measure before enlarging

Two to three weeks after each tranche, through OpenSEO:

```
inspect_urls(projectId, urls: [...10 sampled from the tranche...])
get_search_console_performance(projectId, dimensions: ["page"], ...)
```

- Sampled indexation under 70%: **stop publishing** and fix crawlability. Do not
  push harder.
- A manual action in Search Console: **stop everything**, including scheduled
  posts still in status 2. Reschedule with `create --reschedule --per-week N`.

## Cadence

40 posts a week, which puts a 1,000-post bank live over about 25 weeks. The number
is set by crawl budget and by the indexation gate above, not by how fast the writer
can run. The writer can produce the whole bank in an afternoon for about $15, and
that is exactly why the cadence has to be enforced somewhere else.

## Cost

`gpt-5.6-luna` at $0.20 in and $1.20 out per million tokens. A 2,000-word
Vietnamese post is roughly 3,500 output tokens against a 3,000-token prompt, so
about $0.005 a post, plus a repair call on a fifth of them. **$12 to $20 for 1,000
posts.** DataForSEO adds a few dollars for the gate. The budget flag exists because
a runaway loop, not the unit price, is the risk.

## Hard rules

- **Measured volume or no page.** No exceptions for "it is cheap to generate".
- **Take the question, never the answer.** Competitor text is research input and
  never source material. Do not fetch competitor pages into the writer.
- **Expand by methodological unit, never by audience.** See
  `references/expansion-axes.md` for what that means and what it excludes.
- **A dimension multiplies once.** `cách chạy hồi quy trong spss` is a page.
  `cách chạy hồi quy trong spss cho sinh viên marketing` is not.
- **Every post carries something proprietary**: a cited threshold table, a worked
  `số liệu minh họa` block, or a `cách viết vào luận văn` paragraph.
- **The dedupe audit runs before every batch**, not after.
- **Never publish faster than Google crawls.** Check indexation between tranches.
- **Read `rejected/` and spot-read 10% of every batch.** The mechanical gate cannot
  see sameness, a wrong threshold, or a citation attached to the wrong claim.
- All of `dothesis-blog-content`'s hard rules still apply, including the citation
  allowlist, quantitative-only, and never inventing a statistic or a study.

## Files

- `references/expansion-axes.md` — the nine axes, their populations, the phrasing
  templates, the depth budget and the rejected axes
- `references/category-taxonomy.md` — the nine categories with measured volumes,
  and what a category is allowed to be
- `scripts/qa_seeds.py` — the mechanical gate, runnable with plain `python3`

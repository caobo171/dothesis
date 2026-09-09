---
name: dothesis-content-pipeline
description: >
  Use when scaling the DoThesis blog in batches rather than writing one article:
  researching what actually ranks, expanding a methodological unit into a family
  of pages, attaching measured volume where it exists, planning a backlog in
  payback order, running the scripted writer, and publishing in tranches. Triggers on "scale the blog",
  "content bank", "nhân bản content", "batch bài viết", "content engine",
  "expand axis", "chạy demand gate", or any request to produce many DoThesis
  articles at once. For a single article use `dothesis-blog-content`; this skill
  applies that skill's rules per post through the writer.
---

# DoThesis content pipeline

## What this skill is for

`dothesis-blog-content` produces one good article. This skill decides **which
articles exist at all**, proves each one is worth a reader's time before it is
written, and stops the batch from becoming a liability.

Read `dothesis-blog-content` too. Every post this pipeline queues is written to
that skill's structure, voice and citation rules; the writer's prompt is literally
built from those files at run time, so editing them changes the next batch.

## The rule that makes this safe

> **A page exists when three things hold: it has real content, it is genuinely
> useful to a student standing at this step, and it does not duplicate anything
> already in the bank. Measured search volume sets the order pages go out in. It
> has no veto.**

This replaced "no page without measured volume for its own primary query" on
2026-09-08. The trade is worth stating plainly. Volume was a cheap mechanical
proxy for "somebody wants this", and its whole virtue was that a script could
check it without an argument. Three judgements now stand where one number stood.
The risk that number was managing has not moved: publishing hundreds of pages that
say nothing is what Google's spam policy calls **scaled content abuse**, the
policy covers human-written pages as well as generated ones, and the penalty is
domain-wide.

So the weight lands on the third judgement, and it lands harder where the evidence
is thinner. **For a page with no measured volume the distinctness bar is twice as
heavy**, because for that page quality is the only thing between this bank and a
reviewer reading it as scaled content. An unmeasured page carries two of the three
proprietary elements rather than one, one more internal link and one more table
than a measured page, and it fails the corpus duplicate check at a stricter
threshold. The calibrated numbers are in `api/app/blog/content/qa.py`. Read them
there; a number copied into a doc drifts.

Measured volume still decides **order**, and the reason is payback rather than
safety. A page whose query carries a number is a page whose demand is known before
a word is written, so it earns impressions on a schedule instead of on a hope. A
page written on judgement may well be right, but it proves itself only after it
is live. Publishing the first kind first means the bank returns value soonest and
the pages taken on judgement ride behind traffic that already exists.

How the engine enforces it:

- `gate` drops nothing. It attaches measured volume where a measurement exists and
  stamps the rest `gate_status = unmeasured`; the older value `family-inferred` is
  a deprecated alias meaning exactly the same thing. Its summary prints measured
  against unmeasured, so the split is never buried inside a total.
- `plan` orders every measured row ahead of every unmeasured one. The vocabulary
  whitelist, the exclusions, the clustering and the category folds are unchanged.
- `create` schedules an unmeasured seed like any other page. Nothing is parked as
  a draft for want of a number.
- `qa` carries what the gate used to. Its corpus mode compares every seed body
  against every other body in the seed directory on word-5-gram shingles and fails
  near-duplicates, at a stricter threshold when either side is unmeasured, and its
  per-post rules apply the doubled proprietary requirement above.

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

Research now happens in a browser (step 1), which puts a competitor's sentences on
your screen where a TSV of keywords never did. That makes this rule harder to keep
and more important to keep. Close the tab, then write. What crosses from the
research note into the brief is the outline and the gap, never a phrasing.

## Realistic scale

The harvest yields roughly 250 on-topic pages after clustering. The axes yield
another 400 to 700 phrasings that survive clustering and the exclusions. **The run
targets 1,000 posts, and the ceiling is now the candidate set the axes and the
harvest supply rather than the count of rows that came back with a volume.**

Under the old rule the gate answered 421 (§19 of the design spec). That number
measured what DataForSEO and OpenSEO could price on the day, not what a student
needs. It stands as history and no longer as a limit.

The run still does not pad. The ceiling that binds is the third judgement: a
candidate that cannot be made genuinely distinct is not a page, and the QA corpus
check is where that is settled rather than argued.

Crawl budget is the constraint on the far side, not writing capacity. Publishing
faster than Google crawls converts effort into "Discovered, currently not indexed".
`create` schedules 40 a week for that reason, and the staging gates below decide
whether the next tranche goes out at all.

## Workflow

### 1. Competitor research, in a browser

**Do not pay to measure a competitor's SEO.** From 2026-09-08 the research method
for this project is a browser. `get_ranked_keywords` and `get_keyword_metrics`
bill credits per keyword to buy a number that no longer decides whether a page
exists, so neither is the required path any more.

Search the query on Google in Vietnamese, phrased the way a student in Vietnam
would type it, and read the top few results. For each one, record:

| What to record | Why it is worth recording |
|---|---|
| Who ranks | one of the four domains, a thesis-service page, a forum, or a university PDF. It tells you what kind of answer Google currently thinks the query wants |
| The shape of the page | definition, procedure, troubleshooting, or list. It picks the archetype |
| How deep it goes | word count, whether a threshold is stated, whether it is sourced, whether real SPSS or SmartPLS output appears |
| What it fails to answer | the brief. This is the column the article is written against |

The last row is the output of this step. The rest is context for it. The method
and six worked examples are in `docs/seo/topic-bank/serp-observations-2026-09-08.md`.

The harvest committed under `docs/seo/topic-bank/` stays where it is, and it is
exactly one thing: a snapshot of what these domains ranked for on 2026-09-07 and
2026-09-08. Its volumes are real measurements, so it remains the best ordering
input in the repo. It is not a gate and it is not re-bought on a schedule. Never
hand-edit it: add exclusions to `exclusions.txt` instead, so the reason a row was
dropped stays in version control.

### 2. Expand along an axis

```bash
cd api && ./run.sh python -m app.blog.content.cli expand
```

Reads every `docs/seo/topic-bank/axes/*.tsv` and writes `candidates.tsv` by
crossing each unit with its phrasing templates. Adding a unit to an axis file is
how the pipeline grows. Read `references/expansion-axes.md` before adding an axis;
the three tests there are what keep this from becoming a doorway-page farm.

### 3. Gate. It measures. It does not cut.

```bash
# optional, and worth doing. Five known keywords first, and read the printed cost
cd api && ./run.sh python -m app.blog.content.cli gate --source dataforseo --probe
cd api && ./run.sh python -m app.blog.content.cli gate --source dataforseo
```

`gate` attaches a monthly volume to every candidate it can measure and stamps
every candidate it cannot as `gate_status = unmeasured`. It drops nothing. The
summary prints measured against unmeasured, and that split is the number to read
before writing: it says how much of the batch is running on judgement rather than
on evidence, which is how much of the batch the QA corpus check has to carry.

Where measurement comes from, when it runs: DataForSEO's Google Ads search-volume
endpoint, up to 1,000 keywords per request, `location_code 2704`,
`language_code vi`, with every response's `cost` field printed and totalled.
OpenSEO is the fallback for short lists at about 1.7 credits a keyword, not the
bulk tool.

On 2026-09-08 the probe returned `HTTP 402`, body `status_code 40200, "Payment
Required"`: valid credentials, no balance. That used to stop the run. It no longer
does. Measure what is cheap to measure and feed it in with
`gate --source tsv --file measured.tsv`, or run on the harvest's committed
volumes, and let the rest through as `unmeasured`. What an empty balance costs is
publishing order, not permission.

What survives of the old cut rules:

- **Difficulty above 40, defer.** Still a real signal about how long a page takes
  to earn anything. Google Ads volume carries no difficulty, so this applies only
  to rows measured through OpenSEO.
- **No volume returned, and under 10 a month.** Neither drops any more. Both become
  `unmeasured`, and `plan` puts them behind every measured row.

Output is `gate-{axis}.tsv` with `keyword`, `search_volume`, `verdict`, `reason`.
Commit it. It is no longer the evidence that a page was allowed to exist. It is
the evidence for the order the pages went out in.

`--fill-unmeasured` on `gate --source tsv` predates the rule change. It existed to
let a candidate missing from the measured TSV pass on its family aggregate instead
of dropping for no volume. Nothing drops now, so it is **a deprecated no-op**: the
flag is still accepted, prints a line saying so, and changes nothing. Drop it from
your commands. `family-inferred` survives only as a value the loader still reads,
mapped to `unmeasured`, so that seeds written before 2026-09-08 still load
(`GATE_STATUSES` and `DEPRECATED_GATE_STATUSES` in `api/app/blog/seeds.py`).

### 4. Plan

```bash
cd api && ./run.sh python -m app.blog.content.cli plan
```

Merges the harvest with the gated candidates, measured and unmeasured alike. A
harvest row is kept only if it hits an axis unit or a whole-word entry in
`vocabulary.txt` (a whitelist, because a blacklist alone let a thesis-service
site's generic Q&A pages through); every drop is written to `plan-rejected.tsv`
with its reason, so read that file for false rejections. `category-folds.tsv`
then folds any category that cannot clear ten posts into a broader one. It
clusters phrasings of one intent into a single page and keeps the losers as
`secondary_keywords`; assigns category and archetype; picks 3 to 5 siblings;
**orders every measured row ahead of every unmeasured one**, then category
round-robin by volume inside each band, so the first tranche is the highest-volume
measured page of every category; writes `backlog.tsv`.

The rule change moved the ordering key and nothing else here. The vocabulary
whitelist, the exclusions, the clustering and the category folds behave exactly as
before.

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
so a duplicate that gets past the plan still gets refused at insert. This audit
compares focus keywords and intent; the QA corpus check in step 7 compares
bodies. Both run, because a batch can duplicate on either.

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
on nothing else. `write-log.tsv` records `slug`, `status`, `attempts`, `unlinked`,
`prompt_tokens`, `output_tokens`, `usd`, `seconds`, `failures` for every row.

`unlinked` counts internal links the writer removed before the gate ran, because
they pointed at a page nobody has planned. Anchor text is kept, the link goes. A
few per batch is the model guessing; a column full of them means the brief's link
list is too thin for that archetype.

A post that fails QA gets exactly one repair call carrying the failure list. If it
fails again it lands in `rejected/` and the run continues. Read `rejected/` after
every batch: three rejects with the same failure means the prompt is wrong, not the
model.

### 7. Gate the batch mechanically

```bash
python3 .Codex/skills/dothesis-content-pipeline/scripts/qa_seeds.py \
  api/data/blog-seeds/vi/posts --corpus
```

Exit 0 required. The rule list is in `dothesis-blog-content/references/voice.md`
and `seed-schema.md`; the implementation is `api/app/blog/content/qa.py`. The shim
runs on plain `python3`, no venv, because it is also the pre-publish check.

This gate carries the weight the volume gate used to carry. Two of its checks are
the reason the new rule is safe to hold:

- **Corpus mode, behind `--corpus`.** Every seed body is compared against every
  other body in the seed directory on word-5-gram shingles, and a near-duplicate
  pair fails, at a stricter threshold when either page is unmeasured. Pass the
  flag and point it at the whole seed directory. Without the flag, or aimed at a
  single new file, the check has nothing to compare against and the batch's one
  real defence against sameness never runs.
- **The doubled per-post bar for unmeasured pages.** Two of the three proprietary
  elements instead of one, one more internal link, one more table. The calibrated
  numbers are in `qa.py`.

Link resolution uses the seed directory plus `backlog.tsv`. When that file is not
on disk, or the batch links to pages that are already live and no longer in the
backlog, pass `--known-slugs <file>`, one slug per line.

Then read ten posts by hand, chosen across archetypes, specifically for
**swapped-noun sameness**: two pages in one family that differ only by the term.
Shingle overlap catches two bodies that share sentences. It does not catch two
bodies that say nothing, differently, and that is the failure that gets a domain
classified as scaled content abuse. Weight the sample towards unmeasured pages.
Those are the ones where no measured search behaviour is standing behind the
decision to publish.

### 8. Publish in tranches

```bash
cd api && ./run.sh python -m app.blog.cli create --dir ../api/data/blog-seeds/vi/posts \
  --schedule-start <tomorrow> --per-week 40
cd api && ./run.sh python -m app.blog.cli export-index
cd api && ./run.sh python -m app.blog.content.cli report
```

Backlog priority order, so the highest-volume measured page of every category is
in the first tranche and the unmeasured pages follow behind them. The nine
category pages go live with it, or the posts have nothing to link up to.

Every seed schedules, whatever its `gate_status`. The loader no longer forces an
unmeasured seed to DRAFT and no longer skips it in the slot counter, so a tranche
of 40 is 40 pages in backlog order with mixed status. `create --reschedule` walks
status 2 as before. What keeps a weak page out of the bank is the QA gate, not the
loader: an unmeasured page that cannot clear the doubled distinctness bar never
reaches `create` at all.

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
posts.** DataForSEO adds a few dollars when the gate measures, which is now
optional. Competitor research costs nothing: it is a browser. The budget flag
exists because a runaway loop, not the unit price, is the risk.

## Hard rules

- **Real content, genuinely useful, not a duplicate.** All three, per page. No
  exceptions for "it is cheap to generate". Measured volume orders the queue and
  vetoes nothing.
- **An unmeasured page clears twice the distinctness bar.** Two of the three
  proprietary elements, an extra internal link, an extra table, a stricter
  near-duplicate threshold. Numbers in `api/app/blog/content/qa.py`.
- **Take the question, never the answer.** Competitor text is research input and
  never source material. Read competitor pages in a browser, write from DoThesis's
  own material, and never fetch a competitor page into the writer.
- **Never pay to measure a competitor.** The browser is the research method. Paid
  rank and volume endpoints buy ordering information, nothing more.
- **Expand by methodological unit, never by audience.** See
  `references/expansion-axes.md` for what that means and what it excludes.
- **A dimension multiplies once.** `cách chạy hồi quy trong spss` is a page.
  `cách chạy hồi quy trong spss cho sinh viên marketing` is not.
- **Every post carries something proprietary**: a cited threshold table, a worked
  `số liệu minh họa` block, or a `cách viết vào luận văn` paragraph. One for a
  measured page, two of the three for an unmeasured one.
- **The dedupe audit runs before every batch**, not after, and the QA corpus check
  runs over the whole seed directory rather than the new files.
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

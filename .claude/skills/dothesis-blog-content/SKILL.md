---
name: dothesis-blog-content
description: >
  Use when writing, planning, or improving one blog post for DoThesis (Vietnamese
  students writing a quantitative thesis with SPSS and SmartPLS). Covers
  grounding the topic in the measured topic bank or in what actually ranks
  today, the ten article archetypes that rank in this market, the editorial
  voice, the citation allowlist, the seed-JSON schema and publishing. Triggers
  on "viết bài blog cho DoThesis", "write a blog post", "bài viết SEO về SPSS",
  "blog content", "improve the blog", or any request to produce one DoThesis
  article.
---

# DoThesis blog content

## Why this skill exists

Four sites own Vietnamese quantitative-thesis search: phamlocblog.com,
xulysolieu.info, phantichspss.com and xulydinhluong.com. Measured on 2026-09-07
they hold 752 ranking rows across 407 distinct keywords in the harvest, at a
keyword difficulty of 0 to 4 almost everywhere. The market is wide open on
difficulty and closed on coverage: they have the pages, DoThesis has none.

Their pages are also thin. A typical `X là gì` page on those domains is 600 to
1,200 words, one screenshot, no threshold table, no source for the number it
tells you to use. That gap is the opening, and this skill is the format that
takes it: 1,800 to 2,400 words, a threshold table with its canonical citation,
a worked example with real SPSS or SmartPLS output shapes, and a paragraph the
student can adapt straight into the thesis.

## When to use

Any request to produce or improve one DoThesis article.

**Writing many at once?** Use `dothesis-content-pipeline` first. It decides which
articles should exist, orders them by measured payback, and drives the scripted
writer that applies this skill's rules per post. Skipping it is how a batch of
near-identical pages ships.

## Workflow

### 0. Find out what the blog already covers

**Always do this first, and name what you checked.**

Read `docs/blog-index.md`. It lists every post, with slug, title, focus keyword,
word count and excerpt, plus a keyword-coverage section and any duplication
overrides. It needs no database and no credentials.

The live audit is the same check against the database:

```bash
cd api && ./run.sh python -m app.blog.cli audit-seo --locale vi
```

Read-only. It prints each visible post's focus keyword, flags pairs whose intent
overlaps, and lists thin posts and posts with no meta description.

Regenerate the committed snapshot after publishing:

```bash
cd api && ./run.sh python -m app.blog.cli export-index
```

Rules that follow:

- **A topic the audit lists as covered is a post to improve, not a topic to write
  again.** Expanding a live URL keeps its age and its links. A second post throws
  both away and competes with the first.
- **Always set `focus_keyword`.** It is the only durable record of what a post is
  for, and the duplicate guard uses it. A post with no focus keyword never blocks
  anything and never gets protected either.
- The API enforces this too. `POST /api/v1/admin/blog/upsert` refuses a post whose
  intent overlaps a published one at 0.6 or above and names the clashing slug, the
  overlap percentage, the shared keyword and the intent class. Getting past that
  refusal needs a written `duplicate_override_reason` of at least 25 characters,
  which is stored and printed in `docs/blog-index.md`. Write it for a human, or
  re-angle the post.

### 1. Ground the topic

Never pick a topic from intuition. There are two grounds and they are not
interchangeable, so check the first before reaching for the second.

**If the topic is in the bank, read the bank.** It is committed and measured
2026-09-07:

- `docs/seo/topic-bank/harvest-2026-09-07.tsv`, 752 competitor rows with volume,
  difficulty, intent, rank and URL.
- `docs/seo/topic-bank/measured-heads-2026-09-07.tsv`, the head terms and the nine
  category names with their volumes.
- `docs/seo/topic-bank/related-spss-2026-09-07.tsv` and
  `serp-head-terms-2026-09-07.tsv`, the related-query and SERP sweeps.

Record the focus keyword, its volume, and two or three secondary phrasings. The
secondaries shape the H2 list; they do not become their own pages. The volume is
worth having because it decides when the post publishes, not whether it does.

**If the topic is not in the bank, do not buy a number for it.** Open a browser,
search the query on Google in Vietnamese the way a student in Vietnam would type
it, and read the first page of results. For each of the top few, note who ranks,
what shape the page is (definition, procedure, troubleshooting, list), how deep it
goes, and what it fails to answer. That last note is the outline brief, and step 2
is written against it.

The post then carries `gate_status = unmeasured`. That changes nothing about
whether it exists and two things about how it is written: it clears the doubled
proprietary bar in `references/structure.md`, and it publishes behind the measured
pages. An unmeasured page is not a lesser page. It is a page whose only defence is
that it is good, so it has to be.

### 2. Outline against what already ranks

Open the two or three competitor URLs, from the harvest when the keyword is in it
and from the search you just ran when it is not, and take their **heading
outline**, never their text. Reading a competitor in a browser puts their
sentences in front of you, which makes this rule harder to keep and more important
to keep. You are matching the depth a reader
expects, and then going past it on the axis they are weak on: the threshold with
a source, the actual output table, the sentence to paste into the thesis.

If the SERP for the query is full of `dịch vụ chạy SPSS` service pages, the intent
is partly commercial and the article should say plainly what doing it yourself
costs in time versus paying someone, then answer the how-to anyway.

Then apply `references/structure.md`, which carries the ten archetype skeletons.

### 3. Write

Follow `references/voice.md`. The short version: write to one student who has the
data open and a deadline, show real SPSS and SmartPLS output, admit the parts that
are genuinely painful, name the honest alternatives, and never use a phrase a
Vietnamese content farm would use.

Every citation must come from `references/canonical-sources.md`, verbatim. That
file is the entire allowlist. A threshold with no source is worth less than no
threshold, and an invented source is a firing offence in a market where the reader
is going to paste your citation into a thesis that gets defended.

**DoThesis is quantitative-only.** SPSS, SmartPLS, AMOS, questionnaires, `.sav`
and `.csv` data. Never suggest the reader run interviews, focus groups, thematic
coding or any qualitative step. If a topic only makes sense qualitatively, it is
not a DoThesis topic.

### 4. Images

DoThesis has no public image hosting today, so **posts ship with no images by
default** and the hero plus Open Graph card are rendered from the title and
category by `web/app/blog/[locale]/[slug]/opengraph-image.tsx` at zero cost.
See `references/images.md` before adding any image; the `images[]` block stays in
the schema for later and is empty in every current post.

Carry the information in **tables** instead. A threshold table and a worked output
table do more for this reader than any illustration would.

### 5. Publish

Seed JSON goes to `api/data/blog-seeds/vi/posts/NNNN-{slug}.json`. Schema in
`references/seed-schema.md`. Gate it first, then insert:

```bash
python3 .claude/skills/dothesis-content-pipeline/scripts/qa_seeds.py api/data/blog-seeds/vi/posts --corpus
cd api && ./run.sh python -m app.blog.cli create --dir ../api/data/blog-seeds/vi/posts --dry-run
cd api && ./run.sh python -m app.blog.cli create --dir ../api/data/blog-seeds/vi/posts
```

`create` skips a post whose `(locale, slug)` already exists, so it never updates.
To change a live post use `update-from-seed --file ... --dry-run` first.

Seeds are gitignored working files. The database is the source of truth and
`docs/blog-index.md` is the committed snapshot.

### 6. Link it

A post nothing links to is a dead end. Every post carries at least four internal
links: its category route, two or three sibling posts in the same family, and the
single CTA to `/landing`. The category intro links back to its strongest posts.

## Hard rules

- **Real content, genuinely useful, not a duplicate.** Those three decide whether
  the post exists. A measured focus keyword decides when it publishes, never
  whether.
- **Never invent a study, a statistic or a citation.** Cite only from
  `references/canonical-sources.md`, as the exact string given there.
- **Quantitative only.** No interviews, no transcripts, no coding, no thematic
  analysis as something the reader should do.
- **Learner-facing numbers stay soft.** Do not promise the reader a Cronbach alpha
  or a p-value they will get. Thresholds from the literature and search volumes
  are concrete and belong in tables; predictions about the reader's own data do
  not exist.
- **Keep English technical terms in English.** `Cronbach's Alpha`, `p-value`,
  `bootstrapping`, `outer loading`, `AVE`, `HTMT`, `VIF`. Vietnamese students say
  these in English and search for them in English.
- **No em dash, no exclamation mark, no blacklisted phrase.** See
  `references/voice.md`. The QA gate fails the post on all three.
- **Every post carries something proprietary.** A threshold table with its source,
  a worked example table labelled `số liệu minh họa`, or a
  "cách viết vào luận văn" paragraph with a sentence the student can adapt. A post
  with none of those is a rewrite of a competitor page. **A post with no measured
  volume carries two of the three**, plus an extra table and an extra internal
  link. See `references/structure.md`.
- **One CTA.** One link to `/landing`, naming the DoThesis module that does this
  step. No second sales paragraph.
- **fillform.info for survey and data-collection posts**, when writing in
  Vietnamese. It is the owner's own product for collecting questionnaire
  responses, so it is named as ours, plainly, not presented as a neutral
  third-party recommendation.

## Files

- `references/structure.md` — target shape and the ten archetype skeletons
- `references/voice.md` — voice, the slop blacklist, the hard prose rules
- `references/canonical-sources.md` — the citation allowlist, verbatim strings
- `references/seed-schema.md` — seed JSON fields and body rules
- `references/images.md` — why posts have no images, and the rules if that changes

The worked exemplar is
`api/tests/fixtures/blog/content/passing/0001-cronbach-alpha-la-gi.json`. It is
also the QA gate's passing fixture, so it stays correct by test.

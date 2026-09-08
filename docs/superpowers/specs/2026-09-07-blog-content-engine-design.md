# DoThesis blog and content engine — design

Status: design approved for build (planned by Fable, implemented by Opus agents).
Date: 2026-09-07.

## 1. What this is

A blog for DoThesis, cloned from the method WELE uses for wele-learn.com, plus a
scripted content engine that can produce a 1,000-post Vietnamese content bank on
quantitative thesis research (SPSS, SmartPLS/PLS-SEM, statistics, questionnaire
design, surveys, thesis writing), gated on measured search demand, checked by a
mechanical QA gate, and loaded into the database on a publishing schedule.

DoThesis has no blog today: no route, no table, no sitemap, no metadata, no
public image hosting (`web/app/landing/_components/Footer.tsx:31` links "Blog"
to `#`). Everything below is new.

## 2. The WELE method, and what changes here

WELE's blog system (`~/project/wele`) is two skills plus tooling:

| WELE piece | What it does | DoThesis equivalent |
|---|---|---|
| `wele-blog-content` skill | one article: keyword grounding, structure, voice, images, seed JSON, publish | `.claude/skills/dothesis-blog-content` |
| `wele-content-pipeline` skill | batches: harvest competitor topics, expand along an axis, demand gate, dedupe, write in parallel, QA, publish in tranches | `.claude/skills/dothesis-content-pipeline` |
| `qa_seeds.py` | mechanical gate over seed JSON | `api/app/blog/content/qa.py` + a skill shim |
| `create.blog` sysfix | insert seeds, skip existing, schedule go-live | `python -m app.blog.cli create` |
| `audit.blog.seo`, `export.blog.index`, `update.blog.from.seed`, `audit.blog.links` | coverage audit, committed index snapshot, live-post update, link audit | same commands under `app.blog.cli` |
| duplicate guard on `admin.create/update` | refuses a post whose `focus_keyword` overlaps a published one at the same intent | `api/app/blog/guard.py`, enforced in `create` and the admin upsert route |
| blog routes, `sitemap.ts`, JSON-LD, contents box | rendering | `web/app/blog/**`, `web/app/sitemap.ts`, `web/app/robots.ts` |
| `docs/seo/topic-bank/*.tsv`, `backlog.tsv`, gate TSVs, batch logs | reproducible topic supply | `docs/seo/topic-bank/` (harvest already committed) |

Three deliberate departures, each with a reason:

1. **A scripted writer instead of Claude subagents.** WELE's batches are written
   by one Claude subagent per article, about 20 articles per session. A
   thousand posts would take roughly fifty sessions. The DoThesis engine writes
   with `gpt-5.6-luna` through the OpenAI SDK, which is the model the draft
   agents already moved to on 2026-09-07 for cost ($0.20 in / $1.20 out per
   million tokens). Estimated cost for 1,000 posts of about 2,000 Vietnamese
   words with one repair pass on a fifth of them: $12 to $20. The skill files
   remain the source of truth for structure and voice; the writer's prompt is
   built from them.
2. **Markdown from day one, no HTML migration.** WELE is mid-migration from
   Quill HTML to markdown. DoThesis is greenfield, so `body` is markdown only
   and there is no `body_format` column. `react-markdown`, `remark-gfm` and
   `mermaid` are already installed in `web/`.
3. **No paid images by default.** WELE generates hero art with `gpt-image-2`
   and hosts it on S3/CloudFront. DoThesis has no public image hosting, so the
   hero and Open Graph image are rendered by Next's `opengraph-image`
   convention from the post title and category, at zero cost. The WELE
   `images[]` seed block is kept in the schema for later, and AI art is a
   documented optional step, not part of the run.

Everything else in the WELE method is kept: measured volume or no page,
expand by unit never by audience, take the question never the answer, dedupe
before every batch, every article carries something proprietary, publish in
tranches, and the QA gate exits non-zero.

## 3. The market, measured

All numbers Vietnam, `vi`, DataForSEO via OpenSEO, 2026-09-07, saved under
`docs/seo/topic-bank/`.

Four sites own this space: phamlocblog.com (229 ranking keywords in the
dataset), xulysolieu.info (426), phantichspss.com (229), xulydinhluong.com
(123). Their top 100 rows each were harvested: 752 rows, 407 distinct keywords,
278 distinct pages. 142 keywords clear 1,000 a month and 264 sit between 100
and 999. Keyword difficulty is 0 to 4 almost everywhere.

Head terms: `spss` 14,800, `thống kê` 14,800, `khảo sát` 6,600,
`nghiên cứu khoa học` 6,600, `khóa luận tốt nghiệp` 2,900, `smartpls` 2,400,
`thang đo likert` 1,600, `phân tích dữ liệu` 1,600, `cronbach alpha` 1,300,
`phương pháp nghiên cứu` 1,300, `hồi quy tuyến tính` 1,000,
`luận văn thạc sĩ` 1,000, `mô hình nghiên cứu` 720, `pls-sem` 720.

Page archetypes that rank (from the harvest and the SERP sweep of ten head
terms):

- `{thuật ngữ} là gì` (139 of 407 keywords): độ lệch chuẩn, outlier,
  moderator, mediator, AVE, p-value, PLS, SEM, EFA, eigenvalue, communality.
- `cách chạy {phân tích} trong SPSS` and `kiểm định {test} SPSS`.
- SmartPLS procedures: đo lường, cấu trúc, bootstrapping, biến điều tiết,
  trung gian.
- Thesis writing and topic pages: khóa luận, luận văn, abstract, đề tài.
- Survey pages: `phiếu khảo sát online` 14,800, `biểu mẫu khảo sát` 9,900,
  `form khảo sát` 6,600 (xulysolieu ranks these with one Google Forms page).
  This is fillform.info's territory, DoThesis's sibling product.
- Troubleshooting: `ma trận xoay` (lộn xộn, không hội tụ) 6,600.

Off-topic rows in the harvest to exclude: TOEIC answer keys, school algebra
(`bậc của đa thức`), programming (`cú pháp khai báo biến`), brand noise
(`loc`, `locs`), software download and crack pages.

## 4. Expansion axes for DoThesis

WELE's proven axes are linguistic units. The equivalent here is a
**methodological unit**: each unit has its own query, its own content, and
cannot be produced by swapping a noun in a sibling page.

| Axis | Population | Phrasing templates | Evidence |
|---|---:|---|---|
| Statistical term | ~200 | `{term} là gì`, `{term} trong spss`, `{term} bao nhiêu là tốt` | 139 harvested `là gì` keywords |
| SPSS procedure | ~60 | `cách chạy {x} trong spss`, `kiểm định {x} spss`, `phân tích {x} spss` | `cách chạy spss` 480, `t-test` 1,000, `anova` 2,400 |
| SmartPLS procedure | ~40 | `{x} trong smartpls`, `cách chạy {x} smartpls 4` | `moderator` 5,400 via a SmartPLS 4 page |
| Theory or model | ~60 | `mô hình {x}`, `lý thuyết {x}`, `{x} là gì` | `mô hình nghiên cứu` 720 |
| Construct and scale | ~120 | `thang đo {x}`, `{x} là gì` (business constructs) | `thang đo likert` 1,600, `scale là gì` 4,880 |
| Thesis section | ~40 | `cách viết {x} luận văn`, `{x} trong luận văn là gì` | `abstract` 8,100 |
| Survey and data collection | ~30 | `{x} khảo sát`, `cỡ mẫu {x}` | `cỡ mẫu là gì` 4,400 |
| Troubleshooting | ~40 | `{symptom} phải làm sao`, `lỗi {x} spss` | `ma trận xoay` 6,600 |
| Topic list by field | ~30 | `đề tài luận văn {ngành}`, `đề tài nghiên cứu khoa học {ngành}` | `khóa luận tốt nghiệp` 2,900 |

Rejected axes: audience segmentation (per university, per year of study),
software version pages (`spss 20`, `spss 27` differ by nothing), and
download/crack pages (off-brand and legally risky).

The depth budget from WELE applies: a dimension multiplies once. `cách chạy
hồi quy trong spss` is a page; `cách chạy hồi quy trong spss cho sinh viên
marketing` is not.

## 5. Content gates, and what measured volume is still for

Rewritten 2026-09-08 for the rule change recorded in §20. The rule:

> **A page exists when three things hold: it has real content, it is genuinely
> useful to a student standing at this step, and it does not duplicate anything
> already in the corpus. Measured search volume sets the order pages publish in.
> It has no veto.**

The trade is worth stating rather than glossing. Volume was a cheap mechanical
proxy for "somebody wants this", and its virtue was that a script could check it
without an argument. Three judgements now stand where one number stood. The risk
that number was defending against has not moved: a bank of a thousand pages that
say nothing is what Google's spam policy calls scaled content abuse, the policy
covers human-written pages as well as generated ones, and the penalty is
domain-wide. So the distinctness judgement carries what the volume gate carried,
and it carries double where the evidence is thinner. **For a page with no measured
volume the distinctness bar is twice as heavy**, because for that page the article
itself is the entire case for its existence.

Measured volume still decides order, for payback rather than for safety: a page
whose query carries a number has known demand before it is written, so it earns
impressions on a schedule instead of on a hope. Publishing those first means the
bank returns value soonest and the judgement calls ride behind traffic that
already exists.

`gate` therefore measures and never cuts. It attaches a monthly volume to every
candidate it can price and stamps every candidate it cannot as
`gate_status = unmeasured`. `family-inferred` survives on the read side only: the
loader maps it to `unmeasured` so pre-2026-09-08 seeds still load, and
`--fill-unmeasured` is now a no-op that prints a deprecation line. The summary prints measured
against unmeasured, because that split is the size of the batch standing on
judgement. Measurement is optional and worth doing, from two sources:

1. **DataForSEO direct.** `DATAFORSEO_LOGIN` and `DATAFORSEO_PASSWORD` are set
   in the repo `.env`. `gate` calls the Google Ads search volume endpoint (up to
   1,000 keywords per request) and records the `cost` field from every response.
   The first call is a 5-keyword probe that must print its cost before any bulk
   call.
2. **OpenSEO** (MCP), about 1.7 credits per keyword: the fallback for short
   lists, not the bulk tool.

Neither is spent on competitor research any more (§20).

What became of the cut rules:

- **No volume returned, or under 10 a month.** Neither drops. Both are stamped
  `unmeasured` and ordered behind every measured row by `plan`.
- **Difficulty above 40, defer.** Kept. It is a statement about how long a page
  takes to earn anything, not about whether anyone wants it. Google Ads volume
  carries no difficulty, so it applies only to OpenSEO-measured rows.
- **The load-bearing check moved into `qa.py`** (§14): a corpus pass comparing
  every seed body against every other on word-5-gram shingles, at a stricter
  threshold when either page is unmeasured, plus a per-post rule that an
  unmeasured page carries two of the three proprietary elements, one more
  internal link and one more table than a measured one. The calibrated
  thresholds live in `qa.py` and are deliberately not restated here.

Expected yield: about 250 on-topic pages from the harvest after clustering, plus
400 to 700 phrasings from the axes. **The ceiling is now the candidate set the
axes and the harvest supply, about 1,000 pages, not the count of rows that came
back with a price.** The run still does not pad: a candidate that cannot be made
genuinely distinct is not a page, and the QA corpus check is where that is
settled.

## 6. Categories

A category exists only if its name has measured volume, has a real route, an
intro, and at least ten posts. Nine categories, measured 2026-09-07:

| Slug | Display name | Target query | Volume |
|---|---|---|---:|
| `spss` | SPSS | spss | 14,800 |
| `thong-ke` | Thống kê | thống kê | 14,800 |
| `khao-sat` | Khảo sát | khảo sát | 6,600 |
| `nghien-cuu-khoa-hoc` | Nghiên cứu khoa học | nghiên cứu khoa học | 6,600 |
| `khoa-luan-tot-nghiep` | Khóa luận tốt nghiệp | khóa luận tốt nghiệp | 2,900 |
| `smartpls` | SmartPLS | smartpls | 2,400 |
| `phan-tich-du-lieu` | Phân tích dữ liệu | phân tích dữ liệu | 1,600 |
| `luan-van-thac-si` | Luận văn thạc sĩ | luận văn thạc sĩ | 1,000 |
| `mo-hinh-nghien-cuu` | Mô hình nghiên cứu | mô hình nghiên cứu | 720 |

Route: `/blog/{locale}/chu-de/{slug}`. Each category page has an H1 near the
target query, 300 to 500 words of intro (hand-written in `categories.json`),
the post list as server-rendered anchors, sibling category links, a
self-canonical, and a sitemap entry.

## 7. Data model (api)

Two tables, hand-written Alembic migration `20260908_blog.py` with
`down_revision = "20260907_searchcache01"`. Models go in `api/app/models.py`
(the single models file `migrations/env.py` star-imports).

`blog_categories`: `id` uuid pk, `slug` String(64) unique, `name`
String(120), `display_name` String(120), `intro_md` Text, `sort_order`
Integer default 0, `created_at` timestamptz server default now.

`blog_posts`: `id` uuid pk, `locale` String(8) default `vi`, `slug`
String(200), `title` String(300), `body` Text (markdown), `excerpt` Text,
`image_url` Text nullable, `category_id` uuid FK nullable, `tags` JSONB
default `[]`, `status` SmallInteger (0 draft, 1 published, 2 scheduled),
`published_at` timestamptz nullable, `scheduled_at` timestamptz nullable,
`meta_title` String(200), `meta_description` String(400), `focus_keyword`
String(200) nullable, `secondary_keywords` JSONB default `[]`,
`focus_keyword_volume` Integer nullable, `canonical_url` Text nullable,
`duplicate_override_reason` Text nullable, `reading_time` Integer,
`archetype` String(40) nullable, `source_batch` String(64) nullable,
`views` Integer default 0, `created_at`, `updated_at`. Unique
`(locale, slug)`; index `(status, published_at)`; index `category_id`.

A post is visible when `status = 1`, or `status = 2` and `scheduled_at <=
now()` (WELE's `isPublished()`). One query helper, `visible_filter()`, owns
that rule.

## 8. API (POST-only, per CLAUDE.md)

Public, plain `BaseModel` bodies, no `current_user` (the pattern
`routers/auth.py` uses):

- `POST /api/v1/blog/list` `{locale, page=1, page_size<=50, category?, q?}` →
  `{posts: [compact], total, page, page_size}`. Compact = `id, locale, slug,
  title, excerpt, image_url, tags, category {slug, name, display_name,
  intro_md, sort_order} | null, published_at, updated_at, reading_time,
  views`; no body.
- `POST /api/v1/blog/get` `{locale, slug}` → the full post as one flat object
  (compact fields plus `body, meta_title, meta_description, focus_keyword,
  secondary_keywords, canonical_url, archetype`) with `related` (up to 5
  compact posts, same category then shared tags) nested inside it. Increments
  `views` best-effort. 404 for both missing and not-yet-visible posts.
- `POST /api/v1/blog/categories` `{locale}` → `{categories: [{...category,
  post_count}]}`.
- `POST /api/v1/blog/sitemap` `{locale?}` → a bare array
  `[{locale, slug, updated_at}]` of visible posts, capped at 5,000.

(As built. The web fetchers in `web/app/blog/_lib/api.ts` accept both this
flat `get` shape and a `{post, related}` envelope, and both a bare array and
`{posts}` for `sitemap`, so either side can change later without a
coordinated deploy.)

Admin (router dependency `require_admin` from `api/app/auth_admin.py`):

- `POST /api/v1/admin/blog/list` all statuses, paginated.
- `POST /api/v1/admin/blog/upsert` full seed-shaped body; runs the duplicate
  guard; refuses with `{"error": {"code": "duplicate_intent", ...}}` naming
  the clashing slug, overlap percentage, shared keyword and intent, unless
  `duplicate_override_reason` has 25+ characters.
- `POST /api/v1/admin/blog/delete` `{id}`.

Errors follow the repo shape `{"detail": {"error": {"code", "message"}}}`.

## 9. Blog service package: `api/app/blog/`

- `similarity.py`: port of WELE's `tokens()`, `classify()` (intent buckets
  comparison | tool | how-to | definition | troubleshooting | informational,
  regexes for Vietnamese and English), `overlap()`, `find_clashes()` at
  threshold 0.6 within a locale and intent class.
- `guard.py`: `assert_no_duplicate(session, seed, exclude_id=None)`; candidates
  are visible posts with a non-empty `focus_keyword` (WELE's calibration
  finding: title fallback produces false clashes on template-title families).
- `markdown.py`: `plain_text()`, `word_count()`, `reading_time()` at 200
  words per minute, `headings()` returning `(level, text, id)` with the same
  slugger the web uses (GitHub-style: lowercase, strip diacritics, hyphenate,
  numeric suffix on repeats), `faq()` extracting `### ` questions under the
  FAQ H2, `internal_links()`.
- `seeds.py`: `load_seed(path)` validating against the seed schema (§12),
  `load_dir(dir)` sorted by filename, `upsert_from_seed()`, `create_from_seed()`
  that skips an existing `(locale, slug)`.
- `schedule.py`: WELE's formula. `go_live_at(index, start, per_week)` =
  `start + week*7d + floor(slot*7d/per_week)`; past dates insert as published,
  future as scheduled.
- `index.py`: writes `docs/blog-index.md` (generated-file banner, per-locale
  post list with slug, title, keyword, words, excerpt, URL; keyword coverage
  sorted; duplication overrides section).
- `audit.py`: coverage audit over visible posts (overlap pairs, thin posts
  under a threshold, missing meta description, missing focus keyword) and a
  link audit (internal links that resolve to no visible slug, category or
  allow-listed route).
- `cli.py`: `python -m app.blog.cli <command>`, run through `api/run.sh`.
  Commands: `create --dir|--file [--schedule-start YYYY-MM-DD] [--per-week N]
  [--dry-run]`, `update-from-seed --file|--dir [--dry-run]`, `audit-seo
  [--locale vi] [--thin 1500]`, `audit-links`, `export-index`. Each prints a
  per-file line and a summary, exits 1 on any failure.

## 10. Web (Next 16 app router)

Routes, all outside the auth route groups:

- `web/app/blog/page.tsx` redirects to `/blog/vi`.
- `web/app/blog/[locale]/page.tsx` listing: hero strip, category chips,
  paginated cards (`?page=`), server-rendered.
- `web/app/blog/[locale]/chu-de/[category]/page.tsx` category page (§6).
- `web/app/blog/[locale]/[slug]/page.tsx` detail: title, meta line
  (category, date, reading time), auto-generated contents box from H2s,
  markdown body, FAQ rendered from body, related posts, one CTA block, JSON-LD
  `BlogPosting` and `FAQPage` when a FAQ section exists.
- `web/app/blog/[locale]/[slug]/opengraph-image.tsx`: `ImageResponse`,
  1200×630, title plus category, palette keyed by category. The listing card
  uses the same URL as its thumbnail.
- `web/app/sitemap.ts`: `/landing`, `/blog/vi`, every category, every
  visible post (`lastModified` from `updated_at`). `web/app/robots.ts`:
  allow `/blog`, `/landing`; disallow `/chat`, `/admin`, `/api`.

Shared pieces in `web/app/blog/_components/`: `BlogShell` (reuses the landing
`Nav` and `Footer` and the `.lp-root` scoped stylesheet so the marketing
surface stays one design), `PostCard`, `ContentsBox`, `Markdown`
(react-markdown + remark-gfm + rehype-slug + rehype-raw; tables wrapped in an
`overflow-x:auto` container; external links `rel="noopener"`), `JsonLd`,
`Pagination`, `CtaBlock`. Markdown helpers in `web/app/blog/_lib/markdown.ts`
(headings, FAQ extraction, slugger) must produce the same ids as
`api/app/blog/markdown.py`; both sides carry the same fixture test.

Metadata: `generateMetadata` on listing, category and detail pages with
title, description, canonical, `openGraph` (type article, published and
modified time), Twitter card. `metadataBase` from `NEXT_PUBLIC_SITE_ORIGIN`
(new, default `http://localhost:3006`), also used by the sitemap and JSON-LD.

Plumbing: `web/proxy.js` `PUBLIC_PATHS` gains `/blog`. Footer "Blog" links to
`/blog/vi`; landing Nav gains "Blog". Data fetches use `apiFetch(path, {auth:
false})` from `web/app/lib/api.js` on the server with `cache: "no-store"`.

## 11. Content engine: `api/app/blog/content/`

Pure Python, stdlib plus `openai` and `httpx` (both already in the venv). No
import of `engine` or `agent`: the API layer imports neither today, and a
40-line OpenAI wrapper is cheaper than a new cross-layer dependency.

Commands under `python -m app.blog.content.cli`:

1. `expand` reads `docs/seo/topic-bank/axes/*.tsv` (one file per axis:
   `unit`, `display`, `templates` (semicolon-separated), `category`,
   `archetype`, `family`) and writes `candidates.tsv` (`keyword`, `axis`,
   `unit`, `family`, `category`, `archetype`).
2. `gate` measures `candidates.tsv` through DataForSEO (`--source dataforseo`)
   or consumes a TSV of measured rows (`--source tsv --file`), applies the
   cut rules, writes `gate-{axis}.tsv` (`keyword`, `search_volume`, `verdict`,
   `reason`) and prints the API cost.
3. `plan` merges the harvest (`harvest-2026-09-07.tsv` minus exclusion
   regexes) with gate survivors, clusters phrasings into one page per intent
   (same slug stem, or identical volume and shared head token as WELE's
   morphological merge), picks the highest-volume phrasing as
   `focus_keyword` and keeps the rest as `secondary_keywords`, assigns
   category and archetype, computes 3 to 5 `sibling_slugs` per row (same
   family, then same category by volume), orders rows category round-robin by
   volume, and writes `backlog.tsv` with `priority`, `slug`, `focus_keyword`,
   `search_volume`, `secondary_keywords`, `category`, `archetype`, `family`,
   `sibling_slugs`, `competitor_urls`, `gate_status`.
4. `write --backlog backlog.tsv --out api/data/blog-seeds/vi/posts
   [--limit N] [--workers 6] [--model gpt-5.6-luna] [--budget-usd 40]
   [--dry-run]`. For each row without an existing seed file: build the
   prompt (§13), call the model in JSON mode, validate, run QA in-process; on
   QA failure run one repair call carrying the failure list; on second failure
   write the seed to `rejected/` and continue. Writes `write-log.tsv` (`slug`,
   `status`, `attempts`, `prompt_tokens`, `output_tokens`, `usd`, `seconds`,
   `failures`) and stops when the cumulative spend crosses the budget or on
   `--limit`. Resumable by re-running. Retries transport errors with
   exponential backoff; honours 429 `Retry-After`.
5. `qa <seed-dir>` runs the gate (§14) over a directory, exit 1 on any FAIL.
6. `report` prints axis and category counts, volume totals, cost, and the
   shortfall against 1,000.

The DataForSEO client (`dataforseo.py`): basic-auth POST to
`/v3/keywords_data/google_ads/search_volume/live`, batches of 1,000,
`location_code 2704`, `language_code vi`, returns `{keyword: volume}`,
raises on a non-20000 status, logs `cost`.

## 12. Seed JSON schema (`dothesis-blog-seed/1`)

One file per post at `api/data/blog-seeds/{locale}/posts/NNNN-{slug}.json`
(gitignored, like WELE's `data/`). `categories.json` beside `posts/` carries
the nine categories with `intro_md`.

```json
{
  "schema": "dothesis-blog-seed/1",
  "title": "Cronbach's Alpha là gì và bao nhiêu là đạt",
  "slug": "cronbach-alpha-la-gi",
  "locale": "vi",
  "meta_title": "Cronbach's Alpha là gì, bao nhiêu là đạt | DoThesis",
  "meta_description": "120 đến 160 ký tự, mô tả cái người đọc nhận được.",
  "focus_keyword": "cronbach alpha",
  "secondary_keywords": ["cronbach's alpha là gì", "hệ số cronbach alpha"],
  "focus_keyword_volume": 1300,
  "excerpt": "Một dòng cho trang danh sách.",
  "category": "spss",
  "tags": ["cronbach alpha", "độ tin cậy thang đo", "spss"],
  "archetype": "term-la-gi",
  "family": "reliability",
  "source_batch": "harvest-2026-09-07",
  "gate_status": "measured",
  "sibling_slugs": ["do-tin-cay-thang-do", "phan-tich-efa-trong-spss"],
  "images": [],
  "body": "markdown"
}
```

Required: `schema`, `title`, `slug`, `locale`, `meta_title`,
`meta_description`, `focus_keyword`, `excerpt`, `category`, `archetype`,
`body`. `slug` is ASCII lowercase hyphenated (đ → d, diacritics stripped),
max 120 characters. `category` must be one of the nine slugs.

Body rules: H2 sections with no manual ids (the renderer slugs them), a
`## Câu hỏi thường gặp` section with `### ` questions and one to three
paragraph answers each, GFM tables, `[text](/blog/vi/slug)` internal links,
no raw HTML, no images unless `images[]` is populated.

## 13. Writer prompt

One JSON-mode call per post. The preamble is generated from the skill files
so the skill stays the source of truth: `references/structure.md` (the
archetype skeletons), `references/voice.md` (voice, slop blacklist, hard
rules), `references/canonical-sources.md` (the only citations allowed, as
exact strings), and a product block (what DoThesis is, the CTA routes, the
fillform.info rule for survey posts). The per-post brief carries the backlog
row: focus keyword and volume, secondary keywords, category, archetype
skeleton, sibling slugs with titles (so internal links resolve), competitor
URL slugs as *question* hints only, and the word target (1,800 to 2,400).

Archetype skeletons (H2 spine, each with its own section list so pages do not
mail-merge): `term-la-gi`, `spss-howto`, `smartpls-howto`, `test`,
`model-theory`, `scale`, `thesis-writing`, `survey`, `topic-list`,
`troubleshoot`. Every skeleton ends with common mistakes, FAQ, and a one
paragraph close with a single CTA link.

The proprietary element, required in every post, is at least one of: a
threshold or decision table with its canonical source; a worked example table
labelled `số liệu minh họa`; a "cách viết vào luận văn" paragraph with a
sample sentence the student can adapt. The CTA names the DoThesis module that
does this step (M3 thang đo và bảng hỏi, M4 phân tích, M5 viết chương) and
links to `/landing`.

Hard rules in the prompt, mirrored by QA: never invent a study, statistic or
citation; cite only from the allowlist; keep learner-facing numbers soft;
never offer qualitative methods; keep English technical terms in English;
no em dash, no exclamation mark, no blacklisted phrase; no "Kết luận"
motivational close.

`reasoning_effort` defaults to `low` (`BLOG_REASONING_EFFORT`), model
`gpt-5.6-luna` (`BLOG_LLM_MODEL`), max output 16,000 tokens.

## 14. QA gate (`qa.py`, stdlib only)

FAIL on: JSON does not parse; missing required field; `schema` mismatch;
unknown category; `slug` not normalized; `meta_title` over 70; `meta_description`
outside 110 to 170; body under 1,500 words; fewer than 5 H2; no FAQ section or
fewer than 4 questions; no table; em dash anywhere; exclamation mark in prose;
blacklisted phrase; a citation pattern (`(Tên và cộng sự, 2015)`, `et al.`,
`(Author, 1981)`) not in the allowlist; fewer than 4 distinct internal links;
an internal link that resolves to nothing known (backlog slugs, category
routes, `/landing`, `/signup`, `/login`, `/blog/vi`); raw HTML tags; an
`{{img:x}}` reference with no `images[]` entry; body mentions
`phỏng vấn sâu` or `mã hóa định tính` as a step the reader should do.

WARN on: word count over 3,000; a paragraph over 120 words; a `%` claim
outside a table; `nghiên cứu cho thấy` without a citation; more than one CTA
link; duplicate H2 text within the post.

Output mirrors WELE's: one line per file with words, H2s, tables, links,
status; a detail block; a final count; exit code 1 if anything fails.

## 15. Publishing schedule and staging

`create` defaults to `--schedule-start` tomorrow and `--per-week 40`, so a
1,000-post bank goes live over about 25 weeks. Rows are inserted in backlog
priority order, so the highest-volume page of every category is in the first
tranche. The nine category pages and the first tranche are live on day one.

Staging gates (WELE's, unchanged): check indexation two to three weeks after
each tranche through Search Console; if sampled indexation is under 70%, stop
publishing and fix crawlability; if Search Console reports a manual action,
stop everything. Rescheduling is `create --reschedule --per-week N` over
posts still in status 2.

Publishing to production is the owner's step, exactly as at WELE: run
`create` against the production `DATABASE_URL` after deploying the branch. The
run in this project targets the local Docker Postgres on port 5499 only.

## 16. Skills

`.claude/skills/dothesis-blog-content/` (SKILL.md, `references/structure.md`,
`voice.md`, `seed-schema.md`, `images.md`, `canonical-sources.md`) and
`.claude/skills/dothesis-content-pipeline/` (SKILL.md,
`references/category-taxonomy.md`, `expansion-axes.md`,
`scripts/qa_seeds.py` shim). Both cloned from WELE's structure and rewritten
for this market with the measurements in §3 to §6. The pipeline skill's
workflow is the engine's command sequence plus the manual steps (harvest via
OpenSEO, dedupe, publish, measure).

## 17. Testing

API (pytest, testcontainers Postgres): similarity and guard unit tests
including WELE's refusal-message cases; seeds load, validation errors, create
skips existing, schedule formula, dry-run writes nothing; migration applies
and downgrades; public routes list/get/categories/sitemap and the visibility
rule (scheduled future post hidden, scheduled past post visible); admin upsert
refuses a duplicate and accepts an override; CLI commands via `main([...])`.

Content engine: expand from a two-line axis fixture; gate with a stubbed
DataForSEO client, including the family aggregate rule; plan clustering and
sibling assignment; qa fixtures (one passing seed, one seed per failure
class); writer with a stubbed model returning a fixture that passes QA, a
repair path, the budget stop, and resume skipping existing files. Nothing in
the test suite touches the network.

Web (vitest): markdown helpers (heading ids match the API fixture, FAQ
extraction, contents box), JSON-LD builders, sitemap builder from a mocked
API, listing and detail pages rendered against MSW.

Verification of the run itself: `qa` exit 0 over the whole seed directory,
`create --dry-run` clean, `export-index` regenerated, `audit-seo` reporting
no clashes, `report` showing counts and spend.

## 18. Out of scope

AI-generated hero art and S3 public hosting; an admin UI for the blog (the
admin API exists, the editor does not); an RSS feed; English-locale content;
Search Console automation; comments; per-post analytics beyond `views`.

## 19. Outcome of the first run (2026-09-08)

Measured, not planned. Everything below is reproducible from
`docs/seo/topic-bank/` and `docs/blog-index.md`.

| Step | Result |
|---|---|
| Harvest | 1,152 competitor rows from 7 domains; 449 dropped by exclusions and the vocabulary whitelist |
| Axis expansion | 638 units, 1,579 candidate phrasings |
| Gate | DataForSEO unusable (HTTP 402, no balance). OpenSEO measured 259 phrasings: template phrasings (`cách chạy X trong spss`, `thang đo X`, `cách viết X luận văn`) return no data almost everywhere; bare terms and `X là gì` carry the demand |
| Backlog | 421 pages, 7 categories (two folded), 272 measured at 386,330 searches a month, 149 family-inferred |
| Writer | 421 of 421 seeds pass QA; gpt-5.6-luna, $4.20, about 2 hours with 6 workers; 88 needed one repair |
| Load | 185 scheduled or live, 115 drafts, 121 refused by the duplicate guard as same-intent overlaps after calibration (§9 `similarity.py`) |

The 421 ceiling below was measured under the demand rule superseded on
2026-09-08 (§20); it records what the gate could price that day, not a limit that
still binds.

**The 1,000 target is not supported by measured demand** in this market with
this method, exactly as WELE's expansion-axes note predicts: the ceiling the
gate returned is 421, and the honest way to raise it is to measure more units
(a DataForSEO top-up makes bulk measurement cost about $0.05 per thousand
keywords), not to pad. The 121 refused seeds are consolidation candidates: fold
each into the page it clashes with as secondary keywords, or re-angle it, then
load again.

Publishing to production remains the owner's step: deploy the branch, then run
`create --dir api/data/blog-seeds/vi --schedule-start <date> --per-week 40`
against the production `DATABASE_URL`.

## 20. The demand rule changes (2026-09-08)

Decided by the product owner on 2026-09-08, matching a change made in the WELE
project the same day.

**The veto goes.** "No page without measured search volume for its own primary
query" is replaced. Measured volume now orders the backlog and vetoes nothing.
Three gates decide whether an article exists at all: it has real content, it is
genuinely useful to the reader, and it does not duplicate the corpus. In
exchange, the "genuinely distinct" bar is **twice as heavy for an article with no
measured volume**, because for such an article quality is the only thing that
stops the bank reading as scaled content abuse to Google.

**Stop paying to measure competitors' SEO.** Competitor research is a browser:
search the query on Google in Vietnamese and read what ranks on page one,
recording per result who ranks, what shape the page is (definition, procedure,
troubleshooting, list), how deep it goes, and what it fails to answer.
`get_ranked_keywords` and `get_keyword_metrics` are no longer the required path.
The harvest committed under `docs/seo/topic-bank/` stays as historical evidence:
a snapshot of 2026-09-07 and 2026-09-08, still the best ordering input in the
repo because its volumes are real readings, and no longer a gate.

**What it unlocks.** The 421-page ceiling in §19 was the gate's answer under the
old rule, which is to say a measurement of what DataForSEO and OpenSEO could
price on the day the DataForSEO balance ran out. The new ceiling is the candidate
set the axes and the harvest supply, about 1,000 pages.

**What it supersedes in this document:**

- §5, rewritten in place.
- §12 and §15: `gate_status = family-inferred` no longer inserts as DRAFT, and no
  seed is held out of the schedule for want of a volume. `plan` orders measured
  rows ahead of unmeasured ones, then category round-robin by volume inside each
  band.
- §14: the QA gate gains corpus near-duplicate detection over word-5-gram body
  shingles across the whole seed directory, and the doubled per-post bar for
  unmeasured pages.
- §16: the pipeline skill's manual harvest step is browser research rather than
  an OpenSEO ranked-keywords pull.
- §19 stands as history. Its 421 is a measurement taken under the superseded
  rule.

**What does not change:** the dedupe audit before every batch, the QA gate's
existing rule list, the voice rules, the citation allowlist and the rule against
inventing a source, a study or a statistic.

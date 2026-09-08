# Seed JSON schema

Schema id: `dothesis-blog-seed/1`.

One file per post at `api/data/blog-seeds/{locale}/posts/NNNN-{slug}.json`. The
`NNNN-` prefix controls insert order, since `create --dir` sorts by filename and
the publishing schedule follows that order. `categories.json` sits beside `posts/`
and carries the nine categories with their `intro_md`.

`api/data/` is gitignored. Seeds are working input for the CLI; the database is the
source of truth and `docs/blog-index.md` is the committed snapshot.

```json
{
  "schema": "dothesis-blog-seed/1",
  "title": "Cronbach's Alpha là gì và bao nhiêu là đạt",
  "slug": "cronbach-alpha-la-gi",
  "locale": "vi",
  "meta_title": "Cronbach's Alpha là gì, bao nhiêu là đạt | DoThesis",
  "meta_description": "110 đến 170 ký tự, nói rõ người đọc nhận được gì.",
  "focus_keyword": "cronbach alpha",
  "secondary_keywords": ["cronbach's alpha là gì", "hệ số cronbach alpha"],
  "focus_keyword_volume": 1300,
  "excerpt": "Một câu cho trang danh sách.",
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

## Fields

| Field | Required | Notes |
|---|---|---|
| `schema` | yes | Exactly `dothesis-blog-seed/1`. QA fails on anything else |
| `title` | yes | The `<h1>`. No brand suffix, the page does not append one |
| `slug` | yes | ASCII lowercase hyphenated, `đ` becomes `d`, diacritics stripped, 120 chars max. Set it deliberately, it is the URL forever |
| `locale` | yes | `vi` |
| `meta_title` | yes | Used verbatim in `<title>`. May carry ` \| DoThesis`. 70 chars max |
| `meta_description` | yes | 110 to 170 characters. Unique across the corpus |
| `focus_keyword` | yes | The query this page targets, measured or not. The duplicate guard reads it |
| `secondary_keywords` | no | Other phrasings of the same intent, clustered into this page by `plan`. They shape H2s, they do not become pages |
| `focus_keyword_volume` | no | Monthly volume from the gate, absent when the keyword was never measured. Sets publishing order and lets the corpus be audited against demand later |
| `excerpt` | yes | One sentence for the listing card. Not a copy of the meta description |
| `category` | yes | One of the nine slugs: `spss`, `thong-ke`, `khao-sat`, `nghien-cuu-khoa-hoc`, `khoa-luan-tot-nghiep`, `smartpls`, `phan-tich-du-lieu`, `luan-van-thac-si`, `mo-hinh-nghien-cuu`. Any other value fails QA |
| `tags` | no | Strings. Used for related-post fallback when the category has nothing closer |
| `archetype` | yes | One of the ten in `structure.md`. Recorded so the corpus can be audited per skeleton |
| `family` | no | The unit family from the axis file (`reliability`, `efa`, `mediation`, ...). Drives sibling selection |
| `source_batch` | no | Which run produced this post, for example `harvest-2026-09-07` or `axis-spss-procedure` |
| `gate_status` | no | `measured` when the focus keyword has its own volume reading, `unmeasured` when it does not (`family-inferred` is a deprecated alias for `unmeasured`). Both schedule normally. An `unmeasured` post is ordered behind the measured ones and must clear the doubled proprietary bar in `structure.md` |
| `sibling_slugs` | no | 3 to 5 slugs this post links to. `plan` fills them from the same family, then the same category by volume |
| `images` | no | Always `[]` today. See `images.md` |
| `body` | yes | Markdown. See below |

## Body rules

Markdown, not HTML. The renderer is `react-markdown` with `remark-gfm` and
`rehype-slug`.

- **H2 sections with no manual ids.** The renderer slugs them and builds the
  contents box from them. Writing `<h2 id="...">` yourself fails QA as raw HTML.
- **No `# ` H1 in the body.** The page renders `title` as the H1.
- **`## Câu hỏi thường gặp`** with 4 to 6 `### ` questions. The FAQ JSON-LD is
  extracted from that section by heading text, so the exact H2 wording matters.
- **GFM tables** with a header row and a separator row. At least one per post.
- **Internal links** as `[text](/blog/vi/slug)` for posts,
  `[text](/blog/vi/chu-de/{category})` for a category, `/landing` for the CTA. At
  least four distinct internal links. Every target must resolve: a slug in the
  backlog, one of the nine category routes, or one of `/landing`, `/signup`,
  `/login`, `/blog/vi`.
- **No raw HTML.** No `<div>`, no `<br>`, no `<table>`. QA fails on any tag.
- **No images** unless `images[]` is populated, and it is not. An `{{img:x}}`
  reference with no matching entry fails QA.
- **No em dash, no exclamation mark, no blacklisted phrase**, per `voice.md`.
- **Citations only from `canonical-sources.md`**, in the exact in-text form.
- Word count 1,800 to 2,400. QA fails under 1,500 and warns above 3,000.

## What the writer fills in versus what the pipeline fills in

`plan` produces the backlog row and therefore owns `slug`, `focus_keyword`,
`focus_keyword_volume`, `secondary_keywords`, `category`, `archetype`, `family`,
`sibling_slugs`, `source_batch` and `gate_status`. The model writes `title`,
`meta_title`, `meta_description`, `excerpt`, `tags` and `body`, and echoes the
pipeline fields back unchanged. `writer.py` overwrites the pipeline fields from the
row after the call, so a model that drifts on them cannot corrupt the corpus.

## Publishing

```bash
python3 .claude/skills/dothesis-content-pipeline/scripts/qa_seeds.py api/data/blog-seeds/vi/posts
cd api && ./run.sh python -m app.blog.cli create --dir ../api/data/blog-seeds/vi/posts \
  --schedule-start 2026-09-09 --per-week 40 --dry-run
```

Drop `--dry-run` to insert. Rows whose scheduled date is in the past insert as
published, future ones as scheduled. `create` never updates an existing
`(locale, slug)`; use `update-from-seed` for that.

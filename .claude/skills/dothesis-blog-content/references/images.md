# Images

A DoThesis post carries **one hero and nothing else**. The hero comes out of a
shared library of about 35 illustrations, and the informative visual in the body
is a table.

## Source order

1. **The shared library.** `"source": "library:<key>"` in the seed's `images[]`,
   resolved by `python -m app.blog.content.cli images`. This is the default and
   almost always the answer.
2. **A screenshot of DoThesis, SPSS or SmartPLS**, when a step genuinely needs
   the reader to match their screen to yours. Take it yourself, from your own
   licensed copy, on your own data or on a seeded demo account — never a real
   student's project, and never lifted from a competitor's page, where the
   capture is their copyrighted asset and the numbers in it are theirs.
3. **Generating a one-off illustration** for a single post. Almost never right:
   if a scene is worth a picture it is worth a library key, because the next
   forty posts in that archetype want the same one.

## Why a library, and what it saves

WELE measured this first and the number is the whole argument: 489 image slots
across their corpus resolved to **64 distinct scenes**, so generating per article
cost roughly twenty-five times what generating per scene did.

Our version of the same arithmetic is starker, because our pages are more
uniform. Every post belongs to one of seven categories and one of the ten
archetypes in `structure.md`, so the bank needs about three dozen pictures no
matter how many posts it grows to:

| | Images | At $0.039 each |
|---|---:|---:|
| One hero generated per post, at the 854 seeds on disk 2026-09-08 | 854 | **$33.31** |
| The library, once, ever | 37 | **$1.44** |

Twenty-three times cheaper today, and the gap widens with every post written —
the library cost is fixed, the per-post cost is not. That comparison is printed
at the end of every `images` run, so it stays a measured claim.

`docs/blog-image-library.json` is the library: `{"<key>": {"prompt": "...",
"url": "..."}}`, with the `url` absent until the key has been generated. A key
with a url is handed straight back; an empty key is generated once, written to
`web/public/img/blog/<key>.webp`, and its url written back into the JSON. **No
key is ever billed twice.**

## Hosting: the repo, not a bucket

Generated files are committed to `web/public/img/blog/` and referenced as
`/img/blog/<key>.webp`.

DoThesis has no public image host — the S3 client only mints 300-second
presigned urls, and there is no CDN in front of anything the public may read.
Committing the files works here for three reasons that would not hold for a
per-post scheme: the library is ~35 files rather than one per post, so the repo
cost is bounded and does not grow with the corpus; Next serves and optimises
`public/` directly, so it needs no bucket, no distribution and no `next.config`
`remotePatterns` entry; and version control is what makes "paid for once"
actually true, since a lost file means paying for it again.

**Not `web/public/blog/...`** — that path collides with the
`/blog/[locale]/[slug]` route.

`image_url` on the post is stored **root-relative**. An absolute origin in the
database bakes the environment into the row. The two places that need an
absolute url, the BlogPosting `image` and the og:image, put it through
`absoluteUrl()` in `web/app/blog/_lib/site.ts`.

## The keys

Seven category keys, one per live slug in `docs/seo/categories.json`:
`spss`, `thong-ke`, `khao-sat`, `nghien-cuu-khoa-hoc`, `khoa-luan-tot-nghiep`,
`smartpls`, `mo-hinh-nghien-cuu`.

Thirty archetype keys, `<archetype>-1`, `-2`, `-3` for each of the ten
archetypes. A seed takes `<archetype>-<n>` where `n` comes from a stable hash of
the slug, so the same post gets the same picture on every run. Where two seeds
adjacent in backlog priority order would land on one key, the second steps to
the next variant: two neighbouring cards in a listing showing one illustration
reads as a broken page. An archetype with no variants falls back to its category
key.

## Prompt rules

Every prompt shares one style prefix, so 37 separately generated pictures read
as one publication rather than 37 commissions. The palette is the landing page's:
indigo and ink on warm off-white. Flat vector, subtle grain, calm and
uncluttered, generous negative space.

**Every prompt ends with `no text, no letters, no numbers, no charts with
labels, no UI, no logos`.** This is not optional and it is not decoration:

- Generated type is always wrong, and wrong Vietnamese type is worse than none.
- A statistics illustration covered in fabricated numbers is worse than no
  picture at all. This bank's whole claim is that its thresholds are sourced; a
  hero full of invented figures undercuts it on sight.
- "No UI" keeps the model from inventing a fake SPSS window that misrepresents
  software the reader is about to open.

Scenes stay **concrete and calm** — a student at a desk with a laptop and
printed tables, a supervisor and a student across a table, a lecture hall, a
questionnaire on a clipboard. The three variants of an archetype are genuinely
different scenes, not one scene recoloured.

## Running it

```bash
cd api

# what is missing and what it would cost. Calls nothing, writes nothing.
./run.sh python -m app.blog.content.cli images --assign --generate --dry-run

# assign a hero to every seed, then fill only the keys with no picture yet
./run.sh python -m app.blog.content.cli images --assign --generate
```

`--dir` picks a different seed directory, `--force` regenerates a key that
already has an image (once per run, not once per post), and `--openai` swaps
gemini-2.5-flash-image for gpt-image-2, which is several times dearer per image.
`GEMINI_API_KEY` and `OPENAI_API_KEY` live in the repo `.env`. Never print them.

**Commit the `.webp` files.** A generated file that is not in version control is
a bill waiting to be paid a second time.

## Alt text

`assign` writes a Vietnamese description of the scene into the seed's
`images[0].alt`. The rendered hero itself uses an empty alt, which is the
correct choice for decorative art: it is not carrying information, and the H1
one line below says what the page is about. Should an informational image ever
ship — a real SPSS output capture — it needs real Vietnamese alt text
describing what the screen shows, and empty alt would then be a bug.

## What actually carries the information

Tables, still. See the proprietary-element rule in `structure.md`: a `số liệu
minh họa` table beats any illustration a competitor put at the top of the same
article, because the reader is trying to match their own output to yours. The
hero is there so the page and the listing card do not look unfinished; it is not
doing the work.

Mermaid blocks are available for a conceptual model or a decision flow —
`mermaid` is installed in `web/` and the renderer handles ```mermaid fences. Use
one only where the shape genuinely is a graph. Never for decoration.

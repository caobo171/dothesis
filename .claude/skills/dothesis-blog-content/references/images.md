# Images

**DoThesis blog posts ship with no images, on purpose.** `images` is `[]` in every
seed and the body contains no `![alt](src)` and no `{{img:id}}`.

## Why

DoThesis has no public image host. There is an S3 bucket for user uploads and
exports, private and signed, and no CDN in front of anything the public may read.
Adding one for decorative blog art would mean a new bucket, a new distribution, a
new cache policy and a per-image generation cost, on a corpus heading for a
thousand posts.

The visual slot is filled instead by
`web/app/blog/[locale]/[slug]/opengraph-image.tsx`, Next's `ImageResponse`
convention. It renders 1200x630 from the post title and category, with a palette
keyed by category, at request time and zero marginal cost. That image is the Open
Graph card, the Twitter card and the listing-card thumbnail, so a post looks
finished on a shared link and on the listing without a single hosted file.

## What carries the information instead

Tables. This reader wants a threshold with a source and an output block that looks
like the one on their screen, not an illustration of a person at a laptop. See the
proprietary-element rule in `structure.md`. A `số liệu minh họa` table beats any
stock image a competitor put at the top of the same article.

Mermaid blocks are available for a conceptual model or a decision flow, since
`mermaid` is already installed in `web/` and the renderer handles ```mermaid
fences. Use one only where the shape genuinely is a graph, for example a model with
mediator and moderator paths. Never for decoration.

## If images are turned on later

The `images[]` block is kept in the schema for that day and works like WELE's:

```json
{ "id": "hero", "prompt": "...", "alt": "" }
```

`id` is referenced from the body as `{{img:<id>}}`, and `hero` is special because
the detail page renders it above the article rather than in the flow. The rules
that would apply on the day:

- **Screenshots of DoThesis itself before generated art.** A capture of M4 running
  a reliability analysis on a real uploaded file proves the product works, which no
  illustration does. Never screenshot a real student's project; use a seeded demo
  account.
- **Screenshots of SPSS and SmartPLS output are the most useful images in this
  market**, because the reader is trying to match their own screen to yours. Take
  them yourself from your own licensed copy on your own data. Never lift an output
  screenshot from a competitor's page: it is their copyrighted asset regardless of
  attribution, and the numbers in it are theirs.
- **Alt text in Vietnamese**, describing what the table or screen shows, on every
  informational image. Decorative art is the only correct empty alt.
- **No hotlinking**, ever. Upload through whatever pipeline exists, so the post
  does not break when someone else redesigns.
- Say **"no text, no letters"** in any generation prompt. Generated Vietnamese type
  is always wrong, and wrong Vietnamese in an image is worse than no image.

Until that infrastructure exists, adding an image URL to a seed just produces a
broken image in production, so QA fails a body that references one.

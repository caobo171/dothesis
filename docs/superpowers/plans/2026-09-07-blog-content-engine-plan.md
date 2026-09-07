# DoThesis blog and content engine — implementation plan

Spec: `docs/superpowers/specs/2026-09-07-blog-content-engine-design.md`.
Read the spec first; this plan only says who builds what, in which order,
and how each piece is verified. Section numbers below refer to the spec.

Branch: `claude/wele-blog-build-check-f6ce37` (worktree at
`/Users/caonguyenvan/project/dothesis/.claude/worktrees/wele-blog-build-check-f6ce37`).
Never `cd` to the main checkout. Commit on this branch only.

## Environment facts the implementers rely on

- `api/.venv` is set up in the worktree. Run every Python command through the
  arch wrapper: `cd api && ./run.sh pytest ...`, `./run.sh alembic ...`,
  `./run.sh python -m app.blog.cli ...`. The repo root is on `sys.path` via a
  `.pth` file, so `orchestrator`, `agent`, `quality`, `engine` import.
- `web/node_modules` is installed. Use `arch -arm64 npx vitest run <file>` and
  `arch -arm64 npx tsc --noEmit -p web` (from `web/`). Do not run `next build`
  while a dev server is up.
- `.env` in the worktree root is a copy of the owner's env: `DATABASE_URL`
  points at the local Docker Postgres on port 5499 (`dothesis`/`dothesis`),
  and `OPENAI_API_KEY`, `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD` are set. Never
  print their values.
- API tests use testcontainers Postgres (Docker is running). Migration head is
  `20260907_searchcache01`.
- Existing conventions: POST-only routers (`CLAUDE.md`), error shape
  `{"detail": {"error": {"code", "message"}}}`, `require_admin` in
  `api/app/auth_admin.py`, `db_session` in `api/app/db.py`, `_uuid_pk()` in
  `api/app/models.py`, hand-written migrations named `YYYYMMDD_slug.py`.
- Comment the reasoning behind non-obvious decisions in code (owner
  preference). Comments explain why, not what.
- The topic bank is already harvested and committed under
  `docs/seo/topic-bank/` (`harvest-2026-09-07.tsv`, one TSV per competitor,
  `serp-head-terms-2026-09-07.tsv`, `related-spss-2026-09-07.tsv`,
  `measured-heads-2026-09-07.tsv`).

## Work packages

Three packages run in parallel, each owned by one implementer. File
ownership is exclusive; the shared contracts are the seed schema (§12), the
category slugs (§6), the backlog TSV columns (§11 step 3), and the heading id
algorithm (§9 `markdown.py` and §10 `_lib/markdown.ts`). A fourth package
(the run) starts when A and C are green.

### Package A — API, data model, CLI (owner: agent A)

Files: `api/app/models.py` (append two models), `api/migrations/versions/
20260908_blog.py`, `api/app/blog/__init__.py`, `similarity.py`, `guard.py`,
`markdown.py`, `seeds.py`, `schedule.py`, `index.py`, `audit.py`, `cli.py`,
`api/app/routers/blog.py`, `api/app/routers/admin_blog.py`, `api/app/main.py`
(two `include_router` lines), `api/tests/test_blog_*.py`, `.gitignore`
(add `api/data/`).

Tasks, in order, each with its test written first:

1. Models and migration (§7). Test: `alembic upgrade head` in the test
   container creates both tables with the unique and indexes; `downgrade -1`
   drops them.
2. `markdown.py` (§9). Test fixture `api/tests/fixtures/blog/headings.md`
   with expected ids in `headings.json`; the same fixture is copied by agent B
   for the web side. Cover diacritics (`Phân tích EFA` → `phan-tich-efa`),
   `đ` → `d`, repeated headings (`-1`, `-2`), FAQ extraction, word count that
   ignores table pipes and link URLs.
3. `similarity.py` and `guard.py` (§9). Port WELE's `tokens`, `classify`,
   `overlap`, `find_clashes` and the refusal message that names slug, overlap
   percentage, shared keyword and intent. Tests mirror WELE's
   `blog.duplicate.guard` and `blog.similarity` cases; a post with no
   `focus_keyword` never blocks.
4. `seeds.py` and `schedule.py` (§9, §12, §15). Tests: a valid seed loads;
   each missing required field fails with the field name; unknown category
   fails; slug normalization; `create_from_seed` skips an existing
   `(locale, slug)`; the schedule formula for `per_week=40` puts row 0 on
   `start`, row 39 inside week 0, row 40 at `start + 7d`; past dates insert
   status 1, future status 2.
5. Routers (§8). Tests: list pagination and the visibility rule (draft
   hidden; scheduled future hidden; scheduled past visible; published
   visible), `get` returns `related` and increments `views`, `categories`
   returns counts, `sitemap` returns visible slugs only, admin routes 401
   without a token and 403 for a non-admin, upsert refuses a duplicate with
   `code = duplicate_intent` and accepts a 25+ character override.
6. `index.py`, `audit.py`, `cli.py` (§9). Tests call `cli.main([...])`:
   `create --dry-run` writes nothing and prints the plan; `create` inserts and
   reports skips on a second run; `export-index` writes the file with the
   generated banner; `audit-seo` reports a planted overlap; `audit-links`
   reports a link to a missing slug.

Verification: `cd api && ./run.sh pytest tests/test_blog_*.py -q` green;
`./run.sh alembic upgrade head` against the local Docker DB succeeds;
`./run.sh python -m app.blog.cli create --dir ../docs/seo/fixtures/seeds
--dry-run` (agent A adds two fixture seeds and a `categories.json` there)
prints a plan.

### Package B — Web (owner: agent B)

Files: `web/app/blog/**`, `web/app/sitemap.ts`, `web/app/robots.ts`,
`web/proxy.js` (one line), `web/app/landing/_components/Footer.tsx` (Blog
href), `web/app/landing/_components/Nav.tsx` (Blog link),
`web/package.json` (add `rehype-slug`, `rehype-raw`, `github-slugger`),
`web/.env.example` or the repo `.env.example` (`NEXT_PUBLIC_SITE_ORIGIN`),
`web/app/blog/**/*.test.tsx`, `web/app/blog/_lib/*.test.ts`.

Tasks:

1. `_lib/markdown.ts` (§10): headings with ids, contents box model, FAQ
   extraction, plain-text excerpt. Test against the shared fixture
   `api/tests/fixtures/blog/headings.md` + `headings.json` (copy it to
   `web/app/blog/_lib/__fixtures__/`); ids must match byte for byte.
2. `_lib/api.ts`: typed server-side fetchers over `apiFetch(path, {auth:
   false})` for list, get, categories, sitemap; `_lib/site.ts` exporting
   `SITE_ORIGIN`. Test with MSW.
3. `_components/`: `BlogShell` (landing `Nav` + `Footer`, `.lp-root`),
   `Markdown` (react-markdown + remark-gfm + rehype-slug + rehype-raw;
   tables inside an `overflow-x:auto` wrapper; external links get
   `rel="noopener"`), `ContentsBox`, `PostCard`, `Pagination`, `CtaBlock`,
   `JsonLd` with `blogPostingJsonLd()` and `faqJsonLd()` builders (tested).
4. Routes (§10): `/blog` redirect, listing with `?page=`, category page,
   detail page with `generateMetadata`, `opengraph-image.tsx`. Render tests
   for listing and detail against MSW with one fixture post; assert the
   contents box links equal the H2 ids and the FAQ JSON-LD contains the
   questions.
5. `sitemap.ts` and `robots.ts` (§10); test the sitemap builder function
   with a mocked fetch.
6. Plumbing: `proxy.js` `PUBLIC_PATHS` gains `/blog`; Footer and Nav links.

Verification: `cd web && arch -arm64 npx vitest run app/blog` green;
`arch -arm64 npx tsc --noEmit` clean for the touched files (baseline any
pre-existing errors first with `git stash`-free means: run tsc before and
after and diff); a manual check with the dev server is optional and must not
use `next build`.

### Package C — Content engine and skills (owner: agent C)

Files: `.claude/skills/dothesis-blog-content/**`,
`.claude/skills/dothesis-content-pipeline/**`,
`docs/seo/topic-bank/axes/*.tsv`, `docs/seo/topic-bank/exclusions.txt`,
`docs/seo/README.md`, `api/app/blog/content/__init__.py`, `llm.py`,
`dataforseo.py`, `expand.py`, `gate.py`, `plan.py`, `prompts.py`,
`writer.py`, `qa.py`, `report.py`, `cli.py`,
`api/tests/test_blog_content_*.py`, `api/tests/fixtures/blog/content/*`.

Agent C imports nothing from `app.blog` except `markdown.py` helpers once
agent A has landed them; until then it vendors a private copy in `qa.py`
(stdlib only, because the skill shim runs without the venv) and the final
integration test asserts both produce the same ids on the shared fixture.

Tasks:

1. Skills (§16). Clone WELE's two skills' structure from
   `~/project/wele/.claude/skills/wele-blog-content` and
   `wele-content-pipeline` (read them; do not copy prose that is WELE
   specific). Rewrite for this market using §3 to §6: structure with the ten
   archetype skeletons, voice for Vietnamese students writing a quantitative
   thesis, slop blacklist, hard rules, `canonical-sources.md` with 20 to 30
   methodology references as exact citation strings (Hair et al. on PLS-SEM
   and multivariate analysis, Fornell and Larcker 1981, Henseler et al. 2015
   on HTMT, Nunnally 1978, Kaiser 1974, Bagozzi and Yi 1988, Podsakoff et al.
   2003, Baron and Kenny 1986, Preacher and Hayes 2008, Davis 1989 TAM,
   Ajzen 1991 TPB, Venkatesh et al. 2003 UTAUT, Parasuraman et al. 1988
   SERVQUAL, Hair et al. 2010, Cohen 1988, Bollen 1989, Anderson and
   Gerbing 1988, Tabachnick and Fidell, Field 2013, Nguyễn Đình Thọ 2011
   and Hoàng Trọng and Chu Nguyễn Mộng Ngọc 2008 for the Vietnamese
   textbooks). Every entry must be a real, well-known publication; when
   unsure of a year or title, leave it out. `category-taxonomy.md` carries
   the nine categories with their measured volumes. `expansion-axes.md`
   carries §4.
2. Axis unit lists `docs/seo/topic-bank/axes/*.tsv` (§4, §11 step 1): one
   file per axis with columns `unit`, `display`, `templates`, `category`,
   `archetype`, `family`. Populate from domain knowledge: about 200
   statistical terms, 60 SPSS procedures, 40 SmartPLS procedures, 60
   theories and models, 120 constructs, 40 thesis sections, 30 survey
   topics, 40 troubleshooting symptoms, 30 fields for topic lists. Each unit
   is a real thing students search for; no invented terms.
3. `expand.py`, `dataforseo.py`, `gate.py`, `plan.py` with tests (§11,
   §17). The DataForSEO client is exercised only through a stub in tests.
   `plan` applies `exclusions.txt` regexes to the harvest, clusters
   phrasings, assigns siblings, and writes `backlog.tsv`.
4. `qa.py` (§14) with one fixture per failure class and one passing seed
   of at least 1,600 words (write it by hand for `cronbach-alpha-la-gi`; it
   doubles as the exemplar the skill points to). The skill shim
   `scripts/qa_seeds.py` adds `api/` to `sys.path` and calls
   `app.blog.content.qa.main()`; verify it runs with plain `python3`.
5. `prompts.py` and `writer.py` (§13, §11 step 4) with tests using a stub
   model: a passing fixture, a repair path, the budget stop, resume that
   skips existing files, the rejected path, and the write log columns. The
   real model call lives in `llm.py` (`OpenAI` client, JSON mode, usage and
   cost from `BLOG_LLM_PRICE_IN`/`_OUT` defaults 0.20 and 1.20 per million,
   `reasoning_effort` low, 429 backoff honouring `Retry-After`).
6. `report.py` and `cli.py`.

Verification: `cd api && ./run.sh pytest tests/test_blog_content_*.py -q`
green; `python3 .claude/skills/dothesis-content-pipeline/scripts/qa_seeds.py
api/tests/fixtures/blog/content/passing` exits 0; `./run.sh python -m
app.blog.content.cli expand` writes `candidates.tsv` with the axis counts
printed; `./run.sh python -m app.blog.content.cli gate --source dataforseo
--probe` measures five known keywords (`spss`, `cronbach alpha`, `thang đo
likert`, `hồi quy tuyến tính`, `mô hình nghiên cứu`) and prints the API
cost; the volumes must be within a factor of two of the OpenSEO readings
in `measured-heads-2026-09-07.tsv` or the source is flagged unusable.

### Package D — The run (owner: Fable, after A and C are green)

1. `gate --source dataforseo` over all candidates; commit `gate-*.tsv`.
2. `plan`; commit `backlog.tsv`; review the top 30 rows and the category
   spread by hand.
3. `write --limit 5`; read the five seeds end to end; fix prompt or
   skeletons; re-run those five with `--force`.
4. `write --limit 50`; `qa`; spot-read 5; then `write` for the rest with
   `--budget-usd 40` in the background, logging to the scratchpad.
5. `qa` over the whole directory; `create --schedule-start <tomorrow>
   --per-week 40` against the local DB; `export-index`; `audit-seo`;
   `report`. Commit `docs/blog-index.md`, `write-log.tsv`, the batch log.
6. Web check: listing, one category, one post, sitemap, robots, OG image
   route, with the dev server.
7. Code review of the branch, fix findings, final test run, report.

## Order and gates

- A, B and C start together. B does not block on A because the API shape is
  fixed by the spec; B's MSW fixtures use the §8 response shapes.
- C's `writer` may not be run against the real model by agent C. Only the
  five-keyword DataForSEO probe touches the network in C.
- D starts when A's and C's suites are green and A's migration has been
  applied to the local DB.
- Nothing merges to `master` in this session; the branch is left verified
  with a summary of what is done and the merge command.

## Commit discipline

One commit per task, message in the imperative naming the behaviour, trailer
`Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Do not commit
`api/data/`, `.env`, or anything under the scratchpad. Do commit
`docs/seo/topic-bank/*.tsv`, `docs/blog-index.md`, and the skills.

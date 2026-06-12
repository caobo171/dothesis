# research_scout playbook — when and how to scope searches

`research_scout` is expensive (multi-API deep search + citation validation, 30–90s).
Scope every call; never fire it speculatively.

## When to call

| Situation | Call? | Scope |
|---|---|---|
| Slice has 0 sources and user asks you to find papers | yes | M1 title + all RQs |
| User asks for papers on one construct/angle (*"more on parasocial interaction"*) | yes | that construct + the RQ it serves; pass existing source ids as `seed_refs` |
| A proposed gap has <2 supporting papers | yes | the gap statement itself as topic |
| User uploaded PDFs and wants them analyzed | **no** — `parse_reference` per file |
| User pastes a DOI / reference list | **no** — `parse_reference` per entry |
| You "remember" a relevant paper | **never trust it** — scout to verify or drop it |

## How to scope

- `topic`: one sentence, the narrower the better. Include population + platform +
  context when the project has them (e.g. "Gen Z impulsive buying on TikTok Live in
  Vietnam"), not the bare construct.
- `research_questions`: pass the M1 RQs verbatim — the planner uses them to generate
  query families.
- `seed_refs`: pass slice sources already confirmed relevant; the planner expands
  from their citation graphs instead of starting cold.
- One scout call per user request. If results are thin, show what came back and ask
  how to widen — don't auto-retry with broader terms.

## Handling results

- Results arrive with `verified` flags and dedup against `seed_refs`. Present a
  numbered table (id · authors · year · title · venue · cites when present).
- Let the user cull before you commit anything to `literature_sources` — the slice
  is *their* curated library, not the raw search dump.
- Keep at most ~10 new sources per round; more is noise at gap-analysis time.

# DoThesis — The Method (M1–M5)

DoThesis turns a blank topic into a finished thesis through **five modules**. The same five modules run two ways: **guided chat** (the student drives, turn by turn) and **Auto approve** (the whole pipeline runs unattended). Both write the same project `context_store` (see [`ARCHITECTURE.md`](ARCHITECTURE.md)).

```
TOPIC ──► M1 Topic ──► M2 Literature ──► M3 Design ──► M4 Analysis ──► M5 Writing ──► DOCX + PDF
          discovery     review            (model +       (real stats     (6 chapters
          (title, RQs)   (sources, gaps)   methodology)   on your data)   + references)
```

Dependency DAG (a change upstream flags downstream modules `needs_review`):
`M1 → M2,M3,M4,M5` · `M2 → M3,M4,M5` · `M3 → M4,M5` · `M4 → M5`.

---

## The five modules

| Module | Goal | Produces | Key guardrails |
|--------|------|----------|----------------|
| **M1 — Topic Discovery** | Pin down the research title + questions. | `research_title`, `research_questions` (and field, paradigm, scope, sample) | `research_type` normalized to `quantitative`/`qualitative`/`mixed`. |
| **M2 — Literature Review** | Gather verified sources, derive the gaps the thesis fills. | `literature_sources`, `research_gaps` (with supporting papers) | Sources only via `research_scout`/`parse_reference` (CrossRef/OpenAlex/Semantic Scholar/arXiv) — never invented. |
| **M3 — Research Design** | Pick paradigm, conceptual model + hypotheses, methodology, instrument. | `conceptual_model`, `hypotheses`, `methodology`, `instrument` | Interactive offers PLS-SEM/regression/etc.; **auto mode forces plain multiple linear regression** for analysability. |
| **M4 — Data Analysis** | Run real statistics on the student's data. | `analysis_outline`, `analysis_results` (measurement model, correlations, path/regression tables) | Numbers come **only** from the whitelisted `run_stats` tool on an uploaded dataset. No data → no results. |
| **M5 — Writing** | Compose the chapters, compile citations, export. | `final_sections` / `chapters` → DOCX + PDF | Numbers in Results match `analysis_results`; metrics stay consistent with the chosen tool (no PLS-SEM + CB-SEM fit-index mixing). |

Module skills live in `skills/dothesis-m{1..5}-*`; the routing/state skill is `skills/dothesis`; the entry wizard is `skills/dothesis-bootstrap`.

---

## Entry: the bootstrap wizard

A new project opens the new-project modal, which collects whatever the student already has (topic, references, gaps, model, instrument, data, draft) and sends one structured `/bootstrap …` first message. The `dothesis-bootstrap` skill imports each declared item into the right module's slice, reconciles dependency holes, computes the entry focus (first module needing attention), commits, and hands off to normal routing. If the student has nothing, it just opens M1.

---

## Guided chat turn

1. Browser POSTs to `/api/v1/threads/{id}/messages`; the API returns an SSE stream.
2. The agent reads the `dothesis` routing skill, then the relevant module skill, and works the turn. It calls tools as needed:
   - `read_slice` / `commit_slice` — read/write project state (commit is the only write path).
   - `research_scout` — literature search (engine cascade); `parse_reference` — DOI/PDF → validated metadata.
   - `run_stats` — whitelisted statistics on an uploaded dataset.
   - `export_docx` — render the current draft to DOCX + PDF.
3. SSE events the UI renders: `token` (assistant text), `progress` (tool activity as plain-language beats — "Reading the guide for this step…", "Searching for relevant research…", "Saving your topic…"), `tool_calls` (interactive cards / editable models), `done`.
4. Decisions persist via `commit_slice`; downstream modules get flagged `needs_review`. The assistant message is saved and the turn is metered (credits) by an idempotent finalizer that also runs if the student disconnects mid-turn (partial reply saved, agent stopped).

---

## Auto-approve run

The "Auto approve" button (or a "write the whole thesis" request) starts an unattended run:

1. `POST /api/v1/projects/{id}/runs` → a detached `python -m orchestrator --auto-draft` subprocess.
2. The LangGraph graph walks M1→M5; each module agent auto-fills its slice (auto-fill gets a generous wall-clock cap since it generates a whole schema at once). M3 is constrained to a simple linear-regression design; M5 (`_auto_compose_chapters`) composes the six chapters and renders DOCX + PDF to S3.
3. Progress streams to the drawer via `POST /api/v1/runs/{id}/events` — coarse node beats *and* agent-internal beats (M2 scout searching, M5 per-chapter writing) so the feed never looks stuck.
4. Controls: **pause/resume** (resume re-enters at the last LangGraph checkpoint — a run that died in M3 resumes at M3 with M1/M2 intact), **cancel**, and **retry** (failed/canceled).

---

## Export

Chapters → a single Markdown document → DOCX + PDF via the engine's renderer (`engine/utils/export_professional.py`, pandoc/LibreOffice when available). Citations are compiled from `literature_sources` into a clickable bibliography. Artifacts are uploaded to S3 and surfaced as download links in the Context store panel and chat header. Composition guards refuse to ship placeholder/stub chapters or fabricated statistics.

---

## The engine behind the tools

`research_scout`, `parse_reference`, and document export are backed by `engine/` — the standalone 19-agent research/draft pipeline (literature APIs, citation cascade, draft compose, DOCX/PDF). It can also run on its own as a CLI; see [`../engine/README.md`](../engine/README.md).

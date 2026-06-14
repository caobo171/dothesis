# DoThesis Engine (19-agent draft generator)

The Python AI engine — the original 19-agent thesis draft generator. It is a **standalone, one-shot draft pipeline** that also serves as the **research + writing muscle** behind the DoThesis chat product's tools.

> Working on the chat product (the deep agent, 5 modules M1–M5, streaming chat, `context_store`)? Start at [`../AGENTS.md`](../AGENTS.md), [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md), and [`../docs/PIPELINE.md`](../docs/PIPELINE.md) — the chat runtime is `agent/` + `api/`, and unattended auto-runs are `orchestrator/`.

Two reasons the engine lives here: (1) it ships as its own MIT-licensed product, and (2) the chat agent reuses it — `research_scout` and `parse_reference` call its citation-API clients (`utils/api_citations/`, `utils/deep_research.py`), and document export goes through its renderer (`utils/export_professional.py`). The 19-agent pipeline below is independent of the M1–M5 chat architecture, but the auto-approve path's M5 composer renders through the same export utilities.

## Structure

```
engine/
├── draft_generator.py      # Main 19-stage pipeline orchestrator
├── config.py               # Model settings, API keys, rate limits
├── utils/
│   ├── agent_runner.py     # Agent execution engine
│   ├── api_citations/      # Citation APIs (CrossRef, Semantic Scholar)
│   ├── citation_*.py       # Citation management & validation
│   ├── export_professional.py  # PDF/DOCX export
│   ├── pdf_engines/        # Pandoc, WeasyPrint engines
│   └── deep_research.py    # Research phase utilities
├── prompts/
│   ├── 00_WORKFLOW.md      # Complete agent workflow
│   ├── 01_research/        # Deep Research, Scout, Scribe, Signal
│   ├── 02_structure/       # Architect, Citation Manager, Formatter
│   ├── 03_compose/         # Crafter, Thread, Narrator
│   ├── 04_validate/        # Skeptic, Verifier, Referee
│   ├── 05_refine/          # Citation Verifier, Voice, Entropy, Polish
│   └── 06_enhance/         # Abstract Generator, Enhancer
└── dothesis/              # CLI tools
```

## Usage

### Run Pipeline Directly

```bash
cd engine
python draft_generator.py --topic "Your research topic" --level master
```

### Academic Levels

| Level | Words | Chapters | Time |
|-------|-------|----------|------|
| research_paper | 3-5k | 3-4 | 5-10 min |
| bachelor | 10-15k | 5-7 | 8-15 min |
| master | 20-30k | 7-10 | 10-25 min |
| phd | 50-80k | 10-15 | 20-40 min |

## Environment Variables

Required in `.env` (project root):

```bash
GEMINI_API_KEY=your-key      # Required
PROXY_LIST=...               # Optional: for faster research
SCOUT_PARALLEL_WORKERS=32    # Optional: parallelism
```

## Dependencies

```bash
pip install -r requirements.txt
```

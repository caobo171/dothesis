> **📜 Historical record — superseded.** This document captured a plan / spec / design at a point in time and is kept for history. It does **not** describe the current system. For the live DoThesis method and architecture see `README.md`, `AGENTS.md`, `docs/ARCHITECTURE.md`, and `docs/PIPELINE.md`.

# Orchestration Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land a LangGraph-based chat orchestrator with 5 module agents that runs both as an in-process FastAPI service (interactive chat) and as a subprocess (auto-draft), preserves the existing `engine/` pipeline by wrapping it as tools, and persists per-project shared context across multiple per-project threads.

**Architecture:** Supervisor-routed LangGraph. Five agent-per-module nodes share a `ModuleAgent` base class implementing a Pydantic-schema-driven clarification loop. Interactive turns run in-process inside `api/` and stream tokens via SSE. Auto-mode runs as `python -m orchestrator --auto-draft`, reusing today's `events.jsonl` + `job_runner.py` pattern. All five module agents call LangChain `@tool`s that thin-wrap existing `engine/utils/*` and `engine/phases/*` functions. PostgreSQL stores `projects`, `threads`, `messages`, `context_store`, plus LangGraph's own checkpoint tables. Existing wizard + `python -m engine` path is untouched.

**Tech Stack:** Python 3.10+, LangGraph 0.2+, LangChain core 0.3+, `langchain-google-genai`, `langgraph-checkpoint-postgres`, FastAPI, SQLAlchemy 2.0, Alembic, pytest + testcontainers, PostgreSQL 16, Pydantic v2.

**Spec:** `docs/superpowers/specs/2026-05-25-orchestration-foundation-design.md`

---

## File map

### New files
```
orchestrator/
├── __init__.py
├── __main__.py                       # subprocess entrypoint (auto-mode + resume)
├── pyproject.toml
├── state.py                          # OrchestratorState TypedDict + ContextStore Pydantic
├── concurrency.py                    # first-write-wins context_store commit
├── graph.py                          # build_graph, get_interactive_graph, get_auto_graph
├── schemas/
│   ├── __init__.py
│   ├── common.py                     # shared enums (AcademicField, ResearchType, …)
│   ├── m1.py                         # M1Output
│   ├── m2.py                         # M2Output + CitedGap
│   ├── m3.py                         # M3Output
│   ├── m4.py                         # M4Output
│   └── m5.py                         # M5Output
├── agents/
│   ├── __init__.py
│   ├── base.py                       # ModuleAgent base + clarification loop
│   ├── supervisor.py                 # supervisor node + RouteDecision
│   ├── m1_topic.py
│   ├── m2_literature.py
│   ├── m3_design.py
│   ├── m4_analysis.py
│   └── m5_writing.py
├── tools/
│   ├── __init__.py
│   ├── m1_topic.py                   # suggest_topics, refine_title
│   ├── m2_literature.py              # scout_citations, summarize_paper, find_research_gaps, …
│   ├── m3_design.py                  # recommend_methodology, build_conceptual_model, …
│   ├── m4_analysis.py                # detect_data_type, generate_analysis_outline, …
│   └── m5_writing.py                 # compose_section, validate_draft, compile_pdf, export_docx, …
├── prompts/
│   ├── supervisor.md
│   ├── m1.md … m5.md
└── tests/
    ├── __init__.py
    ├── conftest.py                   # pytest fixtures (fake LLM, in-memory checkpointer, test DB)
    ├── test_state.py
    ├── test_schemas.py
    ├── test_concurrency.py
    ├── test_tools_m1.py … test_tools_m5.py
    ├── test_agent_base.py
    ├── test_supervisor.py
    ├── test_agents_m1.py … test_agents_m5.py
    ├── test_graph.py
    ├── test_subprocess.py
    ├── integration/
    │   ├── test_single_module.py
    │   ├── test_full_interactive.py
    │   ├── test_full_auto.py
    │   ├── test_concurrency_e2e.py
    │   └── test_stop_resume.py
    └── test_migration.py

api/app/routers/
├── chat.py                            # NEW: project + thread + message endpoints
└── runs.py                            # NEW: auto-draft start, pause, resume, status

api/migrations/versions/
└── 20260526_add_orchestrator_tables.py
```

### Modified files
```
requirements.txt                        # +langgraph, langchain-google-genai, langgraph-checkpoint-postgres
api/pyproject.toml                      # +langgraph deps
api/app/main.py                         # mount chat + runs routers if ORCHESTRATOR_ENABLED, startup hook
api/app/settings.py                     # add ORCHESTRATOR_ENABLED, LANGSMITH_API_KEY
api/app/models.py                       # add Project, Thread, Message, ContextStore models; extend Job
api/app/job_runner.py                   # spawn `python -m orchestrator` when run.mode == "auto"
.env.example                            # ORCHESTRATOR_ENABLED, LANGSMITH_API_KEY
```

---

## Task index (32 tasks)

| Phase | Tasks |
|---|---|
| 0 Setup | 1. Deps + skeleton · 2. Alembic migration |
| 1 Models & schemas | 3. SQLAlchemy models · 4. OrchestratorState + ContextStore · 5. M1–M5 schemas · 6. Concurrency helper |
| 2 Tools (one task per module) | 7. M1 tools · 8. M2 tools · 9. M3 tools · 10. M4 tools · 11. M5 tools |
| 3 Agents | 12. ModuleAgent base · 13–17. M1–M5 agents · 18. Supervisor |
| 4 Graph | 19. Graph builder |
| 5 Subprocess | 20. `orchestrator/__main__.py` |
| 6 HTTP API | 21. Chat router CRUD · 22. Message SSE · 23. Runs router · 24. `job_runner.py` · 25. Feature flag · 26. App startup |
| 7 Integration | 27–31. Integration tests · 32. Migration test |

Tasks have dependencies between phases but tasks within a phase are mostly independent (e.g., M1–M5 tool tasks can be done in parallel).

---

Continuing the rest of this plan in companion files since each task carries its own non-trivial code block and we want each task's full TDD cycle visible inline. See:

- `2026-05-26-orchestration-foundation-plan-phase-0-2.md` (Tasks 1–11: setup, models, schemas, tools)
- `2026-05-26-orchestration-foundation-plan-phase-3-4.md` (Tasks 12–19: agents + graph)
- `2026-05-26-orchestration-foundation-plan-phase-5-6.md` (Tasks 20–26: subprocess + HTTP API)
- `2026-05-26-orchestration-foundation-plan-phase-7.md` (Tasks 27–32: integration tests + migration test)

Execute the four files in order. Each task's "Commit" step ships a working slice that can be reviewed independently before moving to the next.

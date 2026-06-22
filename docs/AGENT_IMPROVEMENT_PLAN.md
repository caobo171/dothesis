# DoThesis — Agent Improvement Plan

> Derived from a 2026 vertical-agent best-practice review + a competitor look at SciSpace.
> DoThesis is already strong on the hard parts (single-deep-agent design, `context_store`
> state discipline, verified-citation grounding). This plan targets the operational gaps:
> **always-on grounding UX, evaluation, observability, runtime guardrails**, plus smaller wins.
> Ordered by value/effort. Each item lists concrete files and acceptance criteria.

---

## P0 — Ground every reply with citations from the first message (SciSpace parity)

**Problem.** SciSpace cites sources in *every* answer, even during early topic exploration —
before any explicit "research" step. DoThesis only surfaces verified sources at **M2**
(Literature Review); **M1 topic chat is ungrounded**, so early answers read like a generic
chatbot and lose the trust signal that is DoThesis's whole differentiator.

**Approach.**
- Give the M1 topic skill access to a lightweight grounded-search tool (reuse the existing
  `research_scout` / `engine.utils.deep_research`, capped to ~3–5 quick hits, no full M2 cascade).
- Update `skills/dothesis-m1-topic/SKILL.md` to require: when making a factual/landscape claim,
  attach 1–3 citations from the tool — never free-text claims.
- Render inline citation chips in chat (the `tool_calls`/citation widget already exists for M2;
  reuse it for M1 answers).

**Files.** `skills/dothesis-m1-topic/SKILL.md` · `agent/tools/` (expose a `quick_sources`
wrapper over `research_scout`) · `web/app/components/chat/` (reuse citation chip component).

**Acceptance.** Ask a topic question with no project context → reply contains ≥1 clickable,
real (CrossRef/OpenAlex-verified) citation; no fabricated refs (existing invariant holds).

**Effort.** ~1–2 days. **Highest user-visible payoff.**

---

## P1 — Agent evaluation harness (biggest engineering gap)

**Problem.** 461 engine unit tests exist, but there's **no agent-level eval** scoring output
quality/faithfulness per release. Quality work (the `humanizer-*` branches) is ad-hoc.

**Approach.**
- Build a small gold set: 10–20 (topic → expected modules/sections) fixtures + a few full runs.
- LLM-judge scorers for: **citation faithfulness** (does each cite support its claim?),
  **no-fabrication** (numbers trace to `run_stats`/uploads), **task completion** (modules filled),
  **tool-calling accuracy**. Align the judge to a handful of human-labeled samples.
- Wire into CI as a non-blocking report first, then a regression gate on faithfulness.

**Files.** new `evals/` package (datasets + runner) · reuse `agent/runtime.py:stream_turn`
headless · CI job in `.github/workflows/`.

**Acceptance.** `python -m evals run` prints per-metric scores; CI posts them on PRs; a seeded
fabrication regression is caught.

**Effort.** ~3–5 days.

---

## P1 — Always-on observability + tracing

**Problem.** LangSmith is **optional/off without a key**; only token metering + progress events
exist. Agents "fail across steps" (bad tool output shape, dropped state, early loop exit,
semantically-close-but-wrong retrieval) — you need step-level traces to catch these.

**Approach.**
- Enable LangSmith tracing by default in prod (sampling in high traffic); it's already wired in
  `dev.sh`/settings — just make it on-by-default when a key is present and add the key to prod env.
- Emit per-step spans: tool name, latency, token cost, success/error, retrieval hit-rate.
- Add alerts on tool-error rate, loop/early-termination, p95 latency, cost per turn.

**Files.** `api/app/main.py` (lifespan tracing init) · `agent/runtime.py` (span annotations on
`tool_start`/`tool_end`) · `orchestrator/token_meter.py` (already a sink — extend).

**Acceptance.** Every chat turn produces a full trace; a dashboard shows tool-error rate + cost/turn;
an alert fires on synthetic tool-failure.

**Effort.** ~2–3 days.

---

## P1 — Runtime guardrails layer (esp. uploads)

**Problem.** Anti-fabrication is enforced structurally (excellent), but there's **no general
guardrail layer**. The sharp risk for a commercial product: **prompt-injection inside uploaded
PDFs** (M2/M4 ingest user files), plus PII/toxicity on outputs.

**Approach.**
- Input guardrail on uploaded docs: strip/flag instruction-like content before it reaches the
  agent context (prompt-injection scan); size/type validation.
- Output guardrail pass before the reply is delivered: PII redaction + toxicity check.
- Keep it a thin, fast pass (regex + a small classifier or a cheap LLM check).

**Files.** `api/app/routers/chat_v3.py` (output pass in `_finalize`) · upload path in
`api/app/` + `agent/multimodal.py` (input scan) · new `agent/guardrails.py`.

**Acceptance.** A PDF containing "ignore previous instructions…" does not alter agent behavior;
an output with injected PII is redacted/blocked.

**Effort.** ~2–4 days.

---

## P2 — Smaller wins

- **Model routing + prompt caching.** Use cheap `gemini-2.5-flash` for simple modules, a stronger
  model for M3/M4 reasoning; cache the large skill/system prompts. Files: `agent/runtime.py`,
  `orchestrator/agents/base.py`. ~1–2 days. Cuts cost.
- **HITL autonomy gates for Auto-approve.** Optional human-approval checkpoints between modules
  (EU AI Act Art. 14 flavor) + an academic-integrity disclosure. Files: `orchestrator/__main__.py`,
  `api/app/routers/runs.py`, drawer UI. ~2 days.
- **User-level memory (personalization).** Persist writing-style/preferences across projects
  (separate from per-project `context_store`). ~2–3 days. Product lever, not correctness.

---

## Suggested sequence
1. **P0 grounded M1** (fastest visible win, competitor parity).
2. **Observability** (you can't improve what you can't see).
3. **Eval harness** (locks in quality, prevents regressions).
4. **Guardrails** (commercial/safety hardening).
5. P2 wins as capacity allows.

## What NOT to change
- Don't go multi-agent. 2026 evidence: single-agent matches/beats it on ~64% of tasks at a
  fraction of the cost/tokens; 40% of multi-agent pilots fail in 6 months. The single-deep-agent
  + skills design is correct — keep it.
- Don't loosen `commit_slice` as the sole write path or the `run_stats` whitelist. Those
  invariants are the product's integrity backbone.

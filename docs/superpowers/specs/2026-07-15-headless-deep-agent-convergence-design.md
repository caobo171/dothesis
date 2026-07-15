# Headless deep-agent convergence — design (sub-projects A+B)

Date: 2026-07-15
Status: design approved, spec pending review
Scope: **A** (headless run core) + **B** (partner API rebuilt as a headless client)

## Problem

DoThesis has three generation surfaces running on two-and-a-half engines. They
share almost nothing, so output quality is inconsistent by construction.

| | Chat | Auto-mode | Partner API |
|---|---|---|---|
| Engine | `create_deep_agent` (`agent/runtime.py:540`) | LangGraph supervisor (`orchestrator/graph.py:340`) | no agent — straight-line function (`api/app/partner_report_service.py:594`) |
| Prompts | `SYSTEM_PROMPT` (`agent/runtime.py:187`) + `skills/` | `orchestrator/prompts/*.md` | inline ad-hoc strings |
| Skills | 8 skills | none | none |
| Tools | ~20 | ~12 across 5 agents | 0 |
| Model default | `claude-sonnet-4-6` (`agent/model_factory.py:42`) | `gemini-2.5-flash` (`orchestrator/llm.py:47`) | same as auto |
| State | `DbProjectStateStore` | raw checkpoint sync (`api/app/job_runner.py:189`) | none (ephemeral dict) |

The divergence is not symmetric drift. **Chat has everything; the headless
surfaces have nothing.** Every capability built for chat — mock committee,
questionnaire doctor, threshold checks, SmartPLS parsing, preflight, the advisor
feedback loop — is invisible to two of three surfaces. They converge only at the
bottom, in `run_export` (`orchestrator/tools/m5_writing.py:1481`).

This inverts the intended invariant. The stated constraint is "chat features must
not gate/break the headless ones"; in practice every chat feature is simply
absent from headless.

### Verified defects found during design

All confirmed by reading code, not inferred:

1. **`agent/multimodal.py:225`** — `detect_provider()` ignores `DOTHESIS_MODEL_ROUTE`.
   It checks only `ANTHROPIC_API_KEY`, else returns `"gemini"`. On `route=ofox` +
   `qwen-plus` it emits Gemini-native `{type:"media"}` blocks into an
   OpenAI-compatible endpoint — a malformed request. Breaks **every** attachment
   (PDF/CSV too), not just images. Pre-ship: Ofox is not live yet.
2. **`api/app/partner_report_service.py:40`** — `_NODE_BIN` hardcodes
   `/Users/kaoguyen/.nvm/versions/node/v24.18.0/bin`. The failure is swallowed at
   `:436`, so every partner report silently ships without its research-model
   diagram.
3. **Billing/model mismatch** — `api/app/job_runner.py:373` computes the credit
   multiplier for `gemini-3.5-flash` while `orchestrator/llm.py:47` runs
   `gemini-2.5-flash`. Per the comment at `job_runner.py:369` that is ~4x, so with
   `ORCHESTRATOR_LLM_MODEL` unset students are **overcharged ~4x** on auto runs.
4. **Three sources of truth for "what model am I on"**: `model_factory.spec_from_env()`,
   `orchestrator/llm.get_vision_llm()`, `multimodal.detect_provider()`. They already
   disagree — `detect_provider` does not know the ofox route exists.
5. **Three `CHAPTER_ORDER` definitions**: `orchestrator/tools/m5_writing.py:983`,
   `orchestrator/agents/m5_writing.py:24`, `api/app/partner_report_service.py:50`.
6. **`DOTHESIS_AGENT_V3` is dead documentation** — described as the switch in
   `README.md:100`, `AGENTS.md:23`, `docs/ARCHITECTURE.md:15`, `api/README.md:15`,
   but no production code reads it. `api/app/routers/chat.py:550` delegates
   unconditionally. Only a test sets it.
7. **Auto-mode never gates** — `assess_export_readiness` is called by chat
   (`agent/tools/writing.py:197`) and partner (`partner_report_service.py:681`) but
   has no auto-mode caller. An auto run with empty M2/M3 composes from stubs and
   reports `job_done` successfully.

## Prior art: opencode

opencode (`/Volumes/SSDportable/projects/opencode`) has more surfaces than
DoThesis — TUI, CLI, headless run, SDK, GitHub bot, Slack, desktop, ACP — and
zero forks. Three decisions do the work:

1. **The loop takes an ID, not a context object.** `SessionPrompt.runLoop(sessionID)`
   (`packages/opencode/src/session/prompt.ts:1081`) re-reads state from the DB every
   iteration. Exactly one `streamText()` call exists in the product
   (`session/llm.ts:280`), enforced by convention in their `AGENTS.md:157`.
2. **Mode differences are data.** Headless is not a pipeline — it is
   `session.create({ permission: [{question:"deny"}, …] })` (`cli/cmd/run.ts:430-446`).
   "Plan mode" is likewise a ruleset diff (`agent/agent.ts:156-181`), not a branch.
3. **Headless is a client that answers.** The core publishes `permission.asked` and
   blocks on a Deferred (`permission/index.ts:96-105`); it never knows whether a
   human exists. The TUI renders a dialog; the headless runner auto-replies
   (`cli/cmd/run.ts:798-816`), defaulting to *reject* without `--auto`.

**Where DoThesis is already aligned.** `_state_header()` (`agent/runtime.py:575`)
calls `store.load()` every turn and conversation lives in the checkpointer keyed
by thread id. The cached `agent` in `chat_v3._agents` is a cache of
model+tools+prompt, not conversation context. Durable state is already
ID-addressed. This is why the migration is tractable.

**Where DoThesis differs, and it matters.** In opencode, asking is a *tool call*
mid-turn, so `question:"deny"` is enforced by the permission evaluator — the model
physically cannot ask. In DoThesis, asking is a *turn boundary*: a skill emits an
`[OPTIONS]` marker in prose, the turn ends, the student's reply is the next turn
(parsed at `agent/runtime.py:768-773`). That makes the headless runner cheap to
build, but "auto-decide" is **emergent behaviour, not an enforced boundary**. See
Risks.

**Where we deliberately do not follow opencode.** Their fake-hostname loopback
`fetch` (`cli/cmd/run.ts:948-960`) exists because their surfaces are separate
processes. DoThesis routers already cross their own HTTP boundary before reaching
`runtime`, so an in-process round-trip would be ceremony. We settle for
service-layer consistency — which is what opencode's own GitHub handler does
(`cli/cmd/github.handler.ts:382`). Carry their warning: that handler is their
least-consistent surface and holds a latent hang bug, precisely because it skipped
the client discipline.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| One brain | Deep agent (`agent/runtime.py`); LangGraph supervisor retired | Skills + all ~20 tools reach every surface; matches the v3 deepagents pivot |
| Headless asks | Auto-decide and record the choice | Auto-mode stays fire-and-forget; decisions auditable and overridable |
| Vision on text-only brain | Pre-transcribe via vision model, inject as text | Vision becomes a runtime capability, not a model property; generalizes the existing `_vision_read` pattern; identical headless |
| Partner runs | Create a real project row; run as an ordinary Job | Reuses events.jsonl → JobEvent → SSE, crash isolation, resumability — and makes C a swap rather than a rewrite |
| Model | Ofox + `qwen-plus` (text), `gemini-2.5-flash` (vision) | Cost/quality lever. **Premise unverified — see Risks** |

## Design

### 1. The run spine

New module `agent/headless.py`. The headless runner plays the student's part:

```
run_headless(store, profile):
    loop until roadmap.next_action() == done, or budget exhausted:
        before  = store.load()
        events  = stream_turn(agent, next_prompt, ...)
        after   = store.load()

        progress = (after != before) or (turn emitted [OPTIONS])
        if not progress:
            stalls += 1;  if stalls >= profile.max_stalls: FAIL
            continue
        stalls = 0

        if turn emitted [OPTIONS]:
            choice = pick(options, store)
            record_decision(store, options, choice, rationale)   # see §4
            next_prompt = choice
        else:
            next_prompt = "continue"
```

Reuses `build_agent` (`agent/runtime.py:467`), `stream_turn` (`agent/runtime.py:608`),
the existing `[OPTIONS]` parser (`agent/runtime.py:768-773`), `agent/roadmap.py:next_action`
as the termination condition, and `commit_slice` as the only write path. **No new
prompts, no new tools, no new state protocol.**

`RunProfile(interactive: bool, max_turns: int, wall_clock_s: int, max_stalls: int = 3,
on_options: "ask" | "auto")` is **data**. Neither `stream_turn` nor `build_agent`
inspects it — only the runner does. That is what preserves the headless invariant:
chat features cannot gate headless, because headless runs the same code with a
different caller.

**Stall detection.** Detecting "is the agent asking?" depends on the model marking
up `[OPTIONS]` correctly; if a skill asks in plain prose the runner replies
"continue" and the agent guesses or hangs. Detecting "did anything change?" is
deterministic — read `store.load()` before and after. It catches the failure
regardless of cause: missing marker, model off-script, unresolvable blocker, or a
tool failing silently. It does not make auto-decide an enforced boundary; it
converts a silent failure (spend with no output, or a hollow thesis) into a loud,
bounded one.

**All three budgets fail the run.** `max_turns`, `wall_clock_s`, `max_stalls` —
exhaustion is a **failed run with partial state preserved**, never a silent
success. (Auto-mode's `bounded_invoke` at `orchestrator/agents/base.py:31` is the
existing precedent for wall-clock discipline.)

### 2. Model capability routing

`ModelSpec` (`agent/model_factory.py:23-29`) gains:

```python
vision_model: str = ""         # resolved per route; "" = same as `model`
supports_vision: bool = False  # derived from `model`, FAIL-CLOSED
```

`supports_vision` is a lookup on the model id — the same technique opencode uses
for prompt selection (`session/system.ts:27-42`). It is a known maintenance point.

**Fail-closed: unknown model ⇒ assume no vision.** Worst case we transcribe an
image that did not need it (minor fidelity loss, fractions of a cent). The other
default ships Gemini blocks into an OpenAI-compat endpoint and hard-fails.

`detect_provider(spec)` takes the spec and derives provider from `route` + `model`
instead of sniffing env. **This is defect 1's fix** and collapses the third
model-truth source.

`build_user_message` becomes capability-driven rather than provider-driven:

| Attachment | Vision-capable brain | Text-only brain (qwen-plus) |
|---|---|---|
| image | native media block (today's path) | vision model transcribe → text |
| PDF | native media block | `extract_pdf_text()` → text |
| CSV / txt | text | text |

Nothing raises `NotImplementedError`; the stub at `agent/multimodal.py:200-209`
stops being a landmine.

**Module moves (both are re-export shims, not rewrites):**

- `api/app/pdf_extract.py` → `agent/pdf_extract.py`, leaving a re-export at the old
  path so `api/app/routers/uploads.py:25` and `partner_report_service.py:28` are
  untouched. Required because `agent/` importing `api.app.*` is an **agent→app
  import** — a known recurring defect class in this repo.
- `orchestrator/llm.get_vision_llm` (`orchestrator/llm.py:101`) → implementation
  moves to `agent/model_factory.make_vision_model(spec)`, with a thin delegate left
  behind so `agent/tools/output_parse.py:126` and auto-mode keep working. Takes the
  model-truth sources from three to one and clears the path for D.

Note `agent → orchestrator` is the existing direction (`output_parse.py:126` already
does it), so no new cycle. `orchestrator/llm.py:12-15` documents the reverse
(`orchestrator → agent`) as the cycle to avoid.

### 3. Partner as the proof of the spine

```
POST /partner/report    (contract unchanged: multipart, shared secret, POST-only)
  → create project row (system-owned) + Job
  → seed store from payload (m1/m3 JSON, uploaded PDF → M4)
  → run_headless(store, RunProfile(interactive=False, …))     [subprocess, as auto-mode]
  → export_docx → run_export        (already the shared renderer)
  → presign → return
```

Partner is unshipped, so the contract is free to change; keeping it stable is a
convenience, not a constraint.

**Deleted:** inline prompts `_infer_topic` (`:155`), `_infer_model` (`:342`),
`_search_query_en` (`:205`); `_CHAPTER_ORDER` copy (`:50`); `_NODE_BIN` (`:40`);
`build_partner_context_store` (`:499`); the private compose loop; the in-memory
`_PROGRESS` dict (`:58`) and its single-process constraint; the private S3 presign
client (`:83`) if the shared path suffices.

**Gained the day it lands:** all ~20 tools, all 8 skills, threshold checks,
questionnaire audit, rubric review, preflight — everything partner currently lacks.

**Promoted rather than deleted** (these are good and should not die with partner):

- `_render_model_diagram` (`:391`) → a tool in `agent/tools/`, with node discovery
  via `shutil.which`. Turns a swallowed prod bug into a feature **all three**
  surfaces get; chat students want a research-model diagram too.
- `_budgeted_scout` (`:278`) — the wall-clock cap + Crossref fallback moves behind
  `research_scout`. It is exactly the discipline headless needs.
- Discussion+Conclusion merge (`:641`) — a presentation choice, so it becomes an
  export argument, not a pipeline fork.

**Why Job, not threadpool.** Reusing the Job infrastructure means C
(auto-mode migration) becomes a *swap* — point the existing Job at the headless
entrypoint instead of `python -m orchestrator --auto-draft`
(`api/app/job_runner.py:416`) — rather than a rewrite. It also removes the
single-process progress limit and gives partner crash isolation for a multi-minute
run.

### 4. State, and the persistence gap

Partner on a real project row means partner uses `DbProjectStateStore`
(`api/app/agent_state.py:39`). That store **only round-trips keys in
`SLICE_OWNERSHIP`** — both `load` (`:127`) and `_save` (`:183`) iterate
`SLICE_OWNERSHIP[module]` and nothing else.

The runner's auditability story is recording auto-decisions. A new top-level
`context_store` key would round-trip in tests against the file-backed
`ProjectStateStore` and **vanish in prod**. This is a known CRITICAL failure mode
in this repo, not a hypothetical.

**Decision: record decisions inside the owned slice** — `m1_topic["decisions"] = [...]`,
written through `commit_slice`. Rides existing ownership, no store changes, no new
failure surface. Decisions are naturally per-module.

This is worse data modelling — decisions are not really *part of* the M1 content —
and considerably safer. Stating the trade-off explicitly rather than pretending it
is clean.

**A Db round-trip test is non-negotiable.** It is the check that catches this class
of bug.

**Note for C:** `job_runner._sync_context_store_from_checkpoint`
(`api/app/job_runner.py:189-201`) writes the five slice columns raw, bypassing
`DbProjectStateStore` and `SLICE_OWNERSHIP`. Once auto-mode runs the deep agent
that sync should be **deleted, not maintained** — the agent writes through the
store itself.

### 5. Testing

`DOTHESIS_E2E_MOCK=1` → `FakeChatModel.from_fixtures_dir` (`agent/runtime.py:564-566`)
is one guard at the model boundary; everything downstream stays real. The loop,
stall detection, budget exhaustion, and decision recording are all deterministically
testable with scripted fixtures — no API spend, no flake.

- **Budget tests assert failure, not completion.** Fixture that never commits →
  stall-fails at 3. Fixture that loops → turn-cap fails. Slow fixture → wall-clock
  fails. Budget bugs only surface as tests that assert the run *stops*.
- **Db round-trip test** for decisions (§4).
- **Capability routing table test**: `(route, model)` → provider, with the
  fail-closed case (unknown model ⇒ no vision) asserted explicitly. This is the
  test that would have caught defect 1.
- **Partner E2E** under mock: seed → `run_headless` → artifacts.

Constraints: api tests run via **`./run.sh`**, not `.venv/bin` directly (the venv is
arm64, the shell is x86_64). No web surface in A+B, so the vitest breakage does not
apply.

## Risks

1. **Auto-decide is emergent, not enforced.** Unlike opencode's permission
   evaluator, nothing prevents a skill from asking in prose without an `[OPTIONS]`
   marker. Stall detection bounds the damage but does not create the boundary. If
   stalls prove common in practice, the follow-up is to make asking a real tool
   (which LangGraph `interrupt()` + the existing checkpointer would support) — out
   of scope for A+B.
2. **The qwen-plus cost premise is unverified.** `agent/model_factory.py:128-138`
   already documents that Ofox's OpenAI-compat endpoint likely loses the ~90%
   input-cache discount, and waves it off with "DoThesis cost is output-dominated
   (uncacheable anyway)". That is an untested assumption. The system prompt is ~280
   lines (`agent/runtime.py:187-464`) plus a skills index, re-sent every turn, and
   chat is many-turn. If the prefix is not cached, qwen-plus-via-Ofox could land
   **more expensive** than gemini-2.5-flash-via-native despite a better per-token
   rate. **Measure with the existing benchmark harness (`a070354`) before
   committing** — this is the entire premise of the qwen choice.
3. **`extract_pdf_text` has no OCR.** A scanned PDF returns empty and the agent
   silently gets nothing. Handling: if extraction yields near-empty on a PDF, fall
   back to the vision path rather than proceeding with a hollow message. Partner
   has a related sniff already (`pdf_looks_like_analysis`, `:484`).
4. **`supports_vision` lookup will drift** as model ids change. Fail-closed keeps
   drift cheap.
5. **chat_v3 accumulating behaviour** is the DoThesis version of opencode's
   GitHub-handler bug. `runtime.stream_turn` must stay the whole spine and both
   callers stay thin. The moment logic chat needs lands in `chat_v3` rather than
   `runtime`, we are back to two pipelines wearing one brain's clothes.

## Non-goals

- **Quality equivalence is not proven by this work.** Same brain + same skills makes
  the surfaces consistent *by construction*, which is far stronger than today. But
  "the qwen-plus headless partner report is as good as the Claude chat thesis" is a
  claim only an eval can settle, and quality-evals do not exist yet. A+B must not
  imply otherwise.
- **C (auto-mode migration)** — deliberately after A+B, because B proves the
  headless path at zero customer risk. Auto-mode is production.
- **D (retire duplicates)** — `orchestrator/prompts/{m1..m5,supervisor,router}.md`,
  the second model factory, the `CHAPTER_ORDER` copies, the dead `DOTHESIS_AGENT_V3`
  docs. Only safe once C removes the last reader; earlier means maintaining two
  prompt sets during the migration, which is the drift we are escaping.
- **E (hygiene)** — the billing/model mismatch (defect 3) is independent and should
  land now, ahead of A+B.

## Sequencing

**E (now, trivial) → A+B (this spec) → C → D.**

C is where the value lands (auto-mode is production and gets zero skills today) and
also where a shipping feature can break; B buys a proven headless path first, at
zero customer risk. D is pure deletion, safe only once C removes the last reader.

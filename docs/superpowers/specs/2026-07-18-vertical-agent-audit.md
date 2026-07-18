# DoThesis Vertical-Agent Audit — judged against opencode and grok-build

**Date:** 2026-07-18
**Status:** Audit — no code changes
**Question:** Is DoThesis the best-in-class VERTICAL AI agent, judged on agent-engineering excellence against two reference horizontal coding agents?
**Reference repos:**
- `opencode` — `/Volumes/SSDportable/projects/opencode` (TypeScript/Bun, horizontal coding agent)
- `grok-build` — `/Volumes/SSDportable/projects/grok-build` (Rust, horizontal build/coding agent; kernel sandbox previously identified as its standout)
- `dothesis` — `/Users/caonguyenvan/project/dothesis` (LangChain deepagents, M1–M5 + defense)

Framing rule applied throughout: the three solve different problems, so nothing here scores feature parity. Each dimension asks one question — *does DoThesis meet or beat the engineering bar the two coding agents set on this transferable quality?*

---

## Executive summary

**Verdict: yes on the vertical claim, with one categorical weakness.** DoThesis clears the "best vertical agent for quantitative theses" bar: its verified-numbers chain (whitelisted compute → deterministic self-validation → hard commit gates → provenance ledger → renderer-over-state → coherence gate → honest certificate) is a domain-semantic verification loop that neither coding agent has an analogue of, and its state/trust discipline ("the model can't author its own audit trail") is *stronger* than either reference. On generic agent engineering it is **ahead** on determinism/verification and state/trust, **at par** on adoption-wiring and prompt/skill architecture, and **behind** on execution isolation: grok-build enforces its boundary in the kernel; DoThesis enforces its boundary in one Python function, in-process, with an unconfined file-path parameter.

**Top 3 gaps (ranked):**
1. **`run_stats`/parser file paths are not workspace-confined and ops run in-process** — the model can pass any absolute path the server can read, and the promised "network-less sandbox service" is not the current wiring (`agent/tools/stats.py:5-7,21-32`; `agent/tools/output_parse.py:46-51`). grok-build shows the bar: kernel-enforced deny paths that fail closed (`xai-grok-sandbox/src/lib.rs:8-18`, `src/deny/mod.rs:75-96`).
2. **Validator crashes fail open at the fabrication boundary** — a crashed M4 stats validator lets the commit proceed "marked unverified" (`agent/tools/state_tools.py:113-127`). grok-build refuses to run rather than silently downgrade when its enforcement layer can't apply (`xai-grok-shell/src/config/mod.rs:1283-1311`). For B2B/headless, where "the gate is the product," this should be fail-closed.
3. **Skill adherence is instructed, not enforced** — nothing mechanically requires the module skill to have been read before that module's first commit; opencode enforces read-before-edit in the tool itself (`packages/opencode/src/tool/edit.txt:1-6`), grok-build enforces read-only by *omitting* tools from the toolset (`xai-grok-agent/src/config.rs:355-379`).

---

## Dimension 1 — Tool/capability boundary & sandbox

### opencode
A permission engine, not an OS sandbox. Every tool call is evaluated against wildcard rulesets whose **default is `ask`** — `evaluate()` returns `{action: "ask", permission, pattern: "*"}` when no rule matches (`packages/opencode/src/permission/index.ts:28-38`). Agent-level defaults are fail-closed-by-approval: `"*": "ask"`, `doom_loop: "ask"`, `external_directory: {"*": "ask"}`, and `.env` files get their own `"*.env": "ask"` rule (`packages/opencode/src/agent/agent.ts:113-133`). Capability is also cut structurally per agent: the `plan` agent is described as "Plan mode. Disallows all edit tools" (`packages/opencode/src/agent/agent.ts:156-158`). Isolation is process-level (user approval), not kernel-level.

### grok-build
The strongest boundary of the three — kernel-enforced, layered, and fail-closed:
- Dedicated crate `xai-grok-sandbox` on Landlock (Linux) / Seatbelt (macOS), applied once, irreversibly, at process startup; child-process network blocked per-subprocess via a hand-built seccomp filter (`crates/codegen/xai-grok-sandbox/src/lib.rs:8-18`, `src/child_net.rs:44-102`).
- Seatbelt deny rules are written per concrete write sub-action because a broad `(deny file-write*)` demonstrably loses to a later `(allow file-write* (subpath <ws>))` by last-match — the comment documents the actual `mv x y && cat y` bypass they closed (`src/deny/mod.rs:75-96`), plus `/private` firmlink alias denies (`src/deny/mod.rs:39-53`), and a **hard error if a deny path can't be expressed** rather than a silently unprotected path (`src/deny/mod.rs:144-151`).
- On Linux, read-deny that Landlock can't express is enforced by re-exec inside `bwrap` with mode-000 bind-overs (`src/lib.rs:240-335`).
- Above the kernel: a tree-sitter bash splitter that only accepts word-only command sequences (`xai-grok-workspace/src/permission/bash_command_splitting.rs:32-48`), a fail-closed heuristic classifier (`classify_bash` returns `Block` for anything it can't decompose — `permission/auto_mode.rs:379-392`), an LLM classifier with a strict JSON schema (`auto_mode.rs:953-987`), and a policy engine with deny > ask > allow precedence that recurses into chained bash and fails closed to `Ask` (`permission/policy.rs:64-108`). Project config can only *add* profiles, never hollow out a trusted one (`src/profiles.rs:119-173`).

### dothesis
A **semantic** boundary instead of an OS one: there is no bash/exec tool at all. The model picks ops and parameters; "The whitelist IS the security boundary — every op is a vetted function here" (`agent/tools/stats.py:1-8`), `OPS` is a closed dict — "An op not in this dict does not run, full stop" (`agent/tools/stats.py:376-397`) — and the tool docstring tells the model "Free-form code is NOT an op — if an analysis you need is missing, say so instead of improvising" (`agent/tools/stats.py:506-507`). File tools are confined: the deepagents `FilesystemBackend(root_dir=project_dir, virtual_mode=True)` refuses absolute-path/`..` escapes, and the state file is deliberately not exposed as writable (`agent/runtime.py:490-499`). Uploaded-document text passes a prompt-injection neutralizer that delimits it as data (`agent/guardrails.py:24-62`) — a trust-boundary layer neither reference has for content.

**But the boundary has two real holes, both self-documented:**
- `run_stats`'s `file` parameter is `Path(file)` with **no workspace confinement** (`agent/tools/stats.py:21-32`), and the parsers say so explicitly: "`run_stats`/`_load_df`... does `Path(file)` directly — there is NO separate workspace resolver" (`agent/tools/output_parse.py:46-51`). A prompt-injected model can read any server-readable file (`detect` returns per-column `example` values — `stats.py:35-48`), and `screening` with `params.apply` **writes** `<stem>_screened.csv` next to any path (`stats.py:338-342`).
- The ops run **in-process in the API server**: "In production these run inside the network-less sandbox service; the spike runs them in-process" (`stats.py:5-7`) — but the thesis-stats ops are explicitly "run IN-PROCESS (no network, no subprocess)" (`stats.py:119-123`), and the M4 skill's claim that "The sandbox has no network and no filesystem beyond the workspace" (`skills/dothesis-m4-analysis/SKILL.md:275-279`) is not what the code enforces today.

**Verdict: BEHIND grok-build; mixed vs opencode.** The whitelist is a genuinely principled design — it eliminates the entire arbitrary-code class rather than approving it case-by-case, which for this domain is the right shape and in that one respect exceeds both references. But it is one path-handling bug (or one pandas/pyreadstat CVE) away from the server's whole filesystem, with no kernel backstop and no approval layer behind it. grok-build's defense-in-depth (kernel + parser + classifier + policy + toolset) is categorically stronger containment.

---

## Dimension 2 — Determinism & verification loops

### opencode
Verifies *process*, mechanically: the edit tool enforces exact-string matching and Read-before-Edit ("This tool will error if you attempt an edit without reading the file", "The edit will FAIL if `oldString` is not found" — `packages/opencode/src/tool/edit.txt:1-6`), and after every successful edit the LSP is touched and diagnostics are appended to the tool output — "LSP errors detected in this file, please fix:" (`packages/opencode/src/tool/edit.ts:195-200`). The correctness judgment itself stays with the model/user.

### grok-build
Same shape, deeper: the codex `apply_patch` engine tries exact match first and degrades through rstrip → trim → Unicode normalization, with typed failures ("A context line or old-lines block could not be located" — `xai-grok-tools/src/implementations/codex/apply_patch/seek_sequence.rs:26-53`, `apply_patch/errors.rs:16-35`); `search_replace` requires uniqueness and builds Unicode-confusable diagnostics on mismatch (`grok_build/search_replace/mod.rs:59-63,104-116`). Turn-level, an adversarial verifier panel judges goal completion with a stall cap (`xai-grok-shell/src/session/goal_tracker.rs:181-190`, templates `goal_verifier_prompt.md` et al.). Still: the verifier is an LLM panel — the *outcome* check is generative, not deterministic.

### dothesis
Verifies the **answer**, deterministically, at multiple choke points:
- Every `run_stats` result gets deterministic verification arithmetic attached — impossible values, AVE↔loadings inconsistency, t↔p impossibility, CI-not-containing-estimate, PLS/CB-SEM family mixing (`agent/tools/stats.py:527-537`; claim extraction in `agent/stats_validation.py:55-99`).
- Hard findings **block the M4 commit** with a `stats_validation_failed` error — "a wrong number never becomes product state" (`agent/tools/state_tools.py:98-127`); prose that contradicts persisted numbers **blocks the M5 commit** with `coherence_failed` (`state_tools.py:142-162`; number tolerance = display precision, `agent/coherence.py:367-409`).
- A safety net re-runs the same checks over persisted state for results that entered by other paths (auto-draft, editor, legacy): `stats_validity_dimension` and `coherence_dimension` in the rubric (`quality/rubric.py:260-291,433-455`), rolled into a deterministic, offline, never-raising certificate (`quality/certificate.py:248-325`).
- The compute engine itself has **independent-reference test discipline**: "Accuracy tests for the ported PLS engine — independent reference" implementations of HTMT/Fornell-Larcker/f² plus golden-parity captures (`libs/thesis-stats/tests/test_pls_accuracy.py:1-3,28-109`, `tests/capture_golden.py`), and gate behavior is unit-proven (`agent/tests/test_state_tools.py:160` `test_gate_blocks_impossible_and_store_unchanged`; `agent/tests/test_stats_validation.py` covers t↔p, family mix, Heywood cases, CI containment).

Honest caveats: the coherence prose extractor is regex-based and *admits* its blind spots — markdown-table numbers and "56% of variance" R² renderings are "deferred to a future LLM-judge" (`agent/coherence.py:8-10`), so a formatting choice can dodge the M5 hard gate (partially mitigated by the renderer making the tables authoritative bytes — see Dimension 5). And the rubric's LLM-judge dims fail to a *neutral 0.6* on error (`quality/rubric.py:211-216`) — a silent score, though flagged with a "review manually" finding.

**Verdict: AHEAD.** Both coding agents verify that edits applied and diagnostics are clean; neither can verify that the *content* of the output is correct. DoThesis's domain lets it make output correctness a pure function, and it actually did — at the tool boundary, at the commit gate, at review, and at export, with independently-referenced tests underneath. This is the strongest verification story of the three.

---

## Dimension 3 — State management & trust discipline

### opencode
Sessions/messages persist through a storage layer (`packages/opencode/src/session/` — `session.ts`, `message-v2.ts`, `revert.ts`); file-state safety comes from an out-of-band git snapshot: a separate `--git-dir` under the global data dir keyed by project+worktree hash, so snapshots/reverts live outside the model-writable worktree (`packages/opencode/src/snapshot/index.ts:71-84`, revert flow in `session/revert.ts`). Solid, conventional; the model can't corrupt the snapshot store, but there is no notion of the model being forbidden to author parts of its own record.

### grok-build
JSONL rollouts per session with a versioned chat format (`CHAT_FORMAT_VERSION = 1`, documented v0→v1 — `xai-grok-shell/src/session/persistence.rs:24-28`), every prompt a rewind checkpoint with file snapshots (`session/acp_session_impl/rewind.rs:24-30`), and two genuine trust-discipline moves: the applied sandbox profile is recorded into session metadata (`session/storage/jsonl/mod.rs:900`), and sandbox state lives in `OnceLock`/`AtomicBool` statics set at startup with **no tool that can mutate them** (`xai-grok-sandbox/src/lib.rs:47-85`) — model output cannot relax the sandbox mid-session.

### dothesis
The most explicit trust model of the three, enforced at a single choke point:
- `commit_slice` is "The ONLY write path" — ownership validation, pre-write version snapshot, focus shift, deterministic downstream `needs_review` propagation (`agent/state.py:254-346`); writes outside the module's slice raise `SliceOwnershipError` surfaced to the model as a correctable error (`agent/tools/state_tools.py:190-193`).
- **The model cannot author its own audit trail**: `NON_CONTENT_KEYS` (`decisions`, `analysis_provenance`) are stripped at the model-facing edge before the ownership check even sees them — "An audit trail is only worth something if the audited party can't write it" (`agent/tools/state_tools.py:73-82`; key definition and reasoning at `agent/state.py:96,57-69`); `read_slice` never returns them either (`agent/state.py:205-215`). `decisions` is written only by deterministic `record_decision`, which snapshots every module status so an audit append can't mutate the state machine it audits (`agent/headless.py:19-56`). Provenance is **injected by deterministic code after the hard gate**, "so a forged analysis_provenance is already gone... The model can never author it; the matcher only upgrades tiers" (`state_tools.py:163-183`; anti-laundering rationale at `agent/provenance.py:10-15`).
- `done` must be earned, not narrated: the strict done-gate rejects marking a module done on an empty slice, and `NON_EARNING_KEYS` stop caller-supplied inputs (locale, steering notes) from cashing in for a `done` (`agent/state.py:276-297,99-107`).
- All of it is test-pinned: `test_model_cannot_write_the_decision_audit_trail` and `test_model_read_slice_never_carries_the_audit_trail` (`agent/tests/test_state_tools.py:53,79`).
- Minor weakness: the file-backed store's `load()` has no corrupt-JSON handling (`agent/state.py:160-163` raises), though writes are atomic tmp+replace (`state.py:165-171`) and production uses the Postgres-backed store (`AGENTS.md:45`).

**Verdict: AHEAD.** grok-build's set-once sandbox state is the same instinct applied to one subsystem; DoThesis generalizes it — the audit trail, the provenance summary, the done status, and the steering inputs are all structurally outside the model's reach, with tests that prove it. Neither coding agent has an equivalent of "the audited party can't write the audit."

---

## Dimension 4 — Fail-open vs fail-closed posture, and error handling

### opencode
Fail-closed by approval: unmatched permissions default to `ask` (`permission/index.ts:28-38`), risky categories (`external_directory`, `*.env`, `doom_loop`) are explicitly `ask` at the agent defaults (`agent/agent.ts:113-133`), and edits hard-fail on non-matching `oldString` rather than fuzzy-applying (`tool/edit.txt:6`).

### grok-build
The most consistent fail-closed posture audited, with named exceptions: startup **refuses to run** if a profile requires read-deny and bwrap is missing — "Refusing to start with denied paths unprotected" + `exit(1)` (`xai-grok-shell/src/config/mod.rs:1283-1311`); `requires_read_deny` is computed from intrinsic config, not the resolved deny set, precisely because the resolved set "returns empty on failure," which would "silently downgrade to fail-open" (`xai-grok-sandbox/src/lib.rs:349-370`); undecomposable or over-nested scripts return `Ask`/`Block` (`permission/policy.rs:76-84`, `auto_mode.rs:379-392`); inexpressible Seatbelt deny paths hard-error (`deny/mod.rs:144-151`). Deliberate fail-open is confined to non-security niceties (hooks dispatcher, summarizer).

### dothesis
A **deliberately inverted, two-tier posture**, stated as principle: "Advisory, not blocking... only the two fabrication boundaries are hard" (`docs/superpowers/specs/2026-07-17-dothesis-vertical-agent-vision.md:240-244`). The hard tier fails closed (whitelist miss returns an error listing available ops — `stats.py:514-519`; hard stats findings and prose-number mismatches block commits — `state_tools.py:115-122,150-157`). Everything else — validators, coherence, provenance capture, ledger I/O — is wrapped in try/except and **fails open by design**: "a validator bug must never block a legitimate thesis" (`agent/stats_validation.py:6-8`), "A validator crash fails open (commit proceeds, marked unverified)" (`state_tools.py:102-104`), fail-open pinned by `test_gate_fail_open_on_validator_crash` (`agent/tests/test_state_tools.py:187`). Garbage-state robustness is exceptional at the review/export layer: `build_certificate` "never raises... a garbage store or a crashed rubric yields a degraded-but-valid certificate" whose degraded form asserts *no* readiness (`quality/certificate.py:9-15,248-344`), `generate_viva` "never raises — junk state degrades to the four staples" (`agent/viva.py:12-14`), and honesty is schema, not tone: `not_checked` is a real status and mandatory limitation strings ship in every certificate (`certificate.py:29-42`).

**Verdict: BEHIND grok-build at the boundary, ahead of both on honest degradation.** The advisory-first stance is a defensible product choice for a student-facing coach (the vision even reserves the right for B2B to flip gates to blocking — vision §5.4). But there is one place the reasoning breaks: when the *validator itself* crashes, the fabrication boundary — the product's core guarantee — silently degrades to "unverified," relying on the rubric/certificate net to catch it later. grok-build's rule for exactly this situation is the better one: if the enforcement layer can't run, don't proceed as if it did — at minimum in headless/B2B mode. The degraded-certificate / honest-`not_checked` machinery, on the other hand, is a posture neither coding agent has and is worth naming as best-in-class.

---

## Dimension 5 — Adoption/wiring: do the capabilities actually fire?

### opencode
Wiring by tool contract and per-tool instruction files: fifteen `tool/*.txt` model-facing descriptions (`packages/opencode/src/tool/` — `edit.txt`, `read.txt`, `skill.txt`, `task.txt`…), with the critical behaviors enforced mechanically rather than requested (Read-before-Edit errors, exact-match errors — `tool/edit.txt:1-6`). LSP feedback fires automatically on every edit rather than waiting to be invoked (`tool/edit.ts:195-200`).

### grok-build
Wiring by construction: the base prompt steers tools over bash ("Use specialized tools instead of bash commands... Reserve bash tools exclusively for actual system commands" — `xai-grok-agent/templates/prompt.md:18-20`), toolsets are model-family-specific (`codex_toolset()` vs default vs Hashline — `xai-grok-agent/src/config.rs:307-354`), and capability limits are enforced by *omission*: "the read-only guarantee is enforced by the toolset, not merely by the prompt" (`config.rs:355-379`).

### dothesis
Three distinct wiring mechanisms, one of them just shipped:
- **Gates fire without being called.** Self-validation, coherence, provenance capture and injection are wrapped *around* `run_stats` and `commit_slice` (`stats.py:527-556`; `state_tools.py:98-183`) — the model cannot forget to verify because verification is not a tool it chooses. The M4 skill says so: "Self-validation runs automatically (you don't call it)" (`skills/dothesis-m4-analysis/SKILL.md:226-227`). This is the strongest form of adoption and matches grok-build's by-construction philosophy.
- **An explicit adoption audit closed present-but-unused gaps.** Commit `df738a1` ("fix(skills): trigger the shipped design-time ops in the default flow") found power/method_advice/screening/ipma/mga "AVAILABLE-ONLY — the tools existed and were whitelisted, but no skill step told the agent to run them," and wired them into the M3/M4 default flow: screening as pipeline step 1b "run FIRST... do NOT wait to be asked" (`skills/dothesis-m4-analysis/SKILL.md:93-98,118-126,143-150`), computed a-priori N replacing the guessed rule of thumb (`skills/dothesis-m3-design/SKILL.md`, per the commit diff). Skill↔code drift is pinned by contract tests (`api/tests/test_skill_content.py:11-29`).
- **Every-turn injection for the things models drop.** The state header and `[NEXT]` line are injected fresh each turn because "The model routinely confabulates module status" (`agent/runtime.py:586-608`), UI conventions ride the system prompt every turn because "models routinely ignore instructions they only see after a skill-read" (`runtime.py:183-188`), and source-surfacing is a hard rule ("fetching sources but not displaying them is a failure" — `runtime.py:332-338`).

Weak spot: skill *reading itself* is discretionary. The root skill demands "Do not act on a module without having read its skill this session" (`skills/dothesis/SKILL.md:317`), but unlike opencode's Read-before-Edit or grok-build's toolset omission, nothing mechanical enforces it — a model that skips the M4 skill still holds `commit_slice` (the gates then catch the worst outcomes, but the workflow guidance is lost).

**Verdict: AT PAR, ahead on the gate pattern.** Wiring verification into the only write path is better adoption engineering than either reference's equivalent (opencode's LSP-on-edit is the same idea, narrower). The recency of the `df738a1` pass cuts both ways: it shows the discipline exists and is tested, but also that adoption drift happened and was caught by audit rather than prevented by design.

---

## Dimension 6 — Prompt/skill architecture

### opencode
Per-model-family prompt files — `anthropic.txt`, `gemini.txt`, `gpt.txt`, `codex.txt`, `beast.txt`, `plan.txt` and eight more under `packages/opencode/src/session/prompt/`; layered instruction loading of global + project `AGENTS.md`/`CLAUDE.md` with ancestor dedup ("The first project-level match wins so we don't stack AGENTS.md/CLAUDE.md from every ancestor" — `packages/opencode/src/session/instruction.ts:61-66,122`); agents as first-class config (build/plan — `agent/agent.ts:141-158`).

### grok-build
Templated `.md` prompts with conditionals and tool-name interpolation so one base prompt renders correctly per registered toolset (`xai-grok-agent/templates/prompt.md:1,41`; `config.rs:109-114`); a 604-line `AGENTS.md` module that also feeds the permission classifier (`xai-grok-agent/src/prompt/agents_md.rs`; `auto_mode.rs:89-95`); a 2,688-line skills subsystem plus canonical slash commands shared across front-ends (`xai-grok-agent/src/prompt/skills.rs`; `xai-grok-tools-api/src/slash_commands.rs:1-45`); per-role subagent prompts (`config.rs:1526-1554`).

### dothesis
Eight skills with progressive disclosure and an enforced contract — "skill name == directory name, description ≤1024 chars, body <500 lines; heavy detail → `references/`", and the binding rule that module behavior changes land in the skill *before* code (`AGENTS.md:56`; vision §5.7 "keeping domain judgment inspectable and versionable"). The root skill is a genuine protocol document: state protocol, routing semantics, the "Promise = tool call. Always." rule with banned phrases ("anything you said you'd do that wasn't a tool call did not happen" — `skills/dothesis/SKILL.md:59-77`), worked behavioral examples (`SKILL.md:206-220`), and the two-register pedagogy rule with a worked α example (`SKILL.md:288-313`). The system prompt is deliberately short — identity + protocol pointer + the frontend-contract conventions that must survive every turn (`agent/runtime.py:183-197`).

Where it trails: there is **one** system prompt regardless of model — the model factory swaps Gemini/Claude (`runtime.py:562-583`) but nothing adapts prompt or toolset per family the way both references do; and skills are consumed via discretionary `read_file` rather than a loader with structural guarantees (grok-build's skills subsystem and opencode's skill tool are more engineered surfaces).

**Verdict: AT PAR.** As *domain-behavior encoding*, the skill set is the best artifact of the three — the banned-phrases promise rule and worked examples are prompt engineering the references don't attempt. As *prompt infrastructure*, it is simpler than both: no per-model adaptation, no templating, single-product scope. For a vertical with one deployment that trade is mostly right; the per-model gap is real but low-severity.

---

## Scorecard

| # | Dimension | opencode | grok-build | dothesis | Verdict for dothesis |
|---|---|---|---|---|---|
| 1 | Boundary & sandbox | Permission engine, default-`ask` (`permission/index.ts:28-38`) | Kernel sandbox + 5 layers, fail-closed (`xai-grok-sandbox/src/lib.rs:8-18`) | Whitelist-of-ops, no exec tool (`agent/tools/stats.py:376-397`) but unconfined file paths, in-process (`stats.py:21-32`) | **Behind** (grok-build); principled design, one bug wide |
| 2 | Determinism & verification | LSP-after-edit, exact-match (`tool/edit.ts:195-200`) | Typed patch engine + LLM verifier panel (`seek_sequence.rs:26-53`, `goal_tracker.rs:181-190`) | Deterministic output-correctness gates + independent-reference tests (`state_tools.py:98-162`, `libs/thesis-stats/tests/test_pls_accuracy.py:1-3`) | **Ahead** |
| 3 | State & trust discipline | Out-of-band git snapshots (`snapshot/index.ts:71-84`) | Versioned rollouts, set-once sandbox state (`persistence.rs:24-28`, `lib.rs:47-85`) | Single write path; model structurally cannot author audit trail/provenance/done (`state_tools.py:73-82`, `state.py:96,286-297`) | **Ahead** |
| 4 | Fail-open/closed & errors | Default-ask everywhere (`agent/agent.ts:113-133`) | Refuses to start unprotected (`config/mod.rs:1283-1311`) | Hard fabrication boundary, advisory everything else; validators fail open (`state_tools.py:102-127`); best-in-class honest degradation (`certificate.py:9-15`) | **Behind** at the boundary, ahead on degradation honesty |
| 5 | Adoption/wiring | Mechanical tool contracts (`tool/edit.txt:1-6`) | Capability by toolset omission (`config.rs:355-379`) | Gates auto-fire on the write path (`stats.py:527-556`); adoption audit shipped (`df738a1`); skill reads discretionary | **At par** (ahead on the gate pattern) |
| 6 | Prompt/skill architecture | Per-model prompts, AGENTS.md layering (`session/prompt/`, `instruction.ts:61-66`) | Templated prompts, skills subsystem (`templates/prompt.md`, `prompt/skills.rs`) | Skill-first domain encoding, promise-rule, two-register (`skills/dothesis/SKILL.md:59-77`); no per-model adaptation (`runtime.py:562-583`) | **At par** |

---

## The verdict, precisely

**"Best VERTICAL agent for quantitative theses" — yes, credibly.** The claim rests on the verified-numbers and verified-sources chains, and the audit confirms those chains exist end-to-end in code, are deterministic at every link, are wired so the model can't skip or forge them, and are tested against independent references. No horizontal agent has a reason to build this, and neither reference has anything comparable in kind.

**"Best-in-class agent engineering across the board" — not yet.** Two findings prevent the unqualified claim:
1. The execution boundary is the product's most-cited guarantee ("sandboxed whitelist" — vision §1) and it is currently a semantic boundary without OS enforcement, with a documented unconfined path parameter. grok-build demonstrates what the finished version of this looks like.
2. The "no incorrect statistics" guarantee fails open under validator fault — acceptable for a coached student, wrong for the unattended B2B path whose selling point *is* the gate.

Both are bounded, addressable gaps rather than architectural flaws; neither undermines the vertical verdict, both keep it honest.

---

## Ranked gap list

| # | Gap | Reference bar (file:line) | Effort | Impact |
|---|---|---|---|---|
| 1 | **Confine `run_stats`/parser file paths to the project workspace, then move ops out-of-process.** Today `_load_df` is `Path(file)` raw (`agent/tools/stats.py:21-32`; `output_parse.py:46-51`), and ops run in the API process (`stats.py:119-123`) despite the sandbox-service claim (`stats.py:5-7`, `skills/dothesis-m4-analysis/SKILL.md:275-279`). | grok-build: kernel deny-paths, fail-closed on inexpressible paths (`xai-grok-sandbox/src/deny/mod.rs:75-151`); network-less child via seccomp (`src/child_net.rs:44-102`) | S for path confinement (resolve against workspace root, reject escapes — the FilesystemBackend already models this, `runtime.py:490-499`); M–L for out-of-process sandboxing | Highest. Closes arbitrary file read/write from a prompt-injected turn; makes the skill's security section true |
| 2 | **Fail-closed validator option for headless/B2B.** A crashed validator commits "unverified" (`state_tools.py:113-127`, `test_state_tools.py:187`); the rubric net catches it later but nothing forces re-verification before export. | grok-build: refuse to proceed when enforcement can't apply (`xai-grok-shell/src/config/mod.rs:1283-1311`; `xai-grok-sandbox/src/lib.rs:349-370`) | S (a `RunProfile`-style flag — mode differences already ride as data, `agent/headless.py:59-79`) | High for B2B trust; the certificate can then attest "all gates ran," not just "no gate failed" |
| 3 | **Mechanical skill-adherence enforcement.** "Do not act on a module without having read its skill" is instruction-only (`skills/dothesis/SKILL.md:317`). | opencode: Read-before-Edit enforced in-tool (`tool/edit.txt:1-6`); grok-build: capability by toolset omission (`config.rs:355-379`) | M (track skill reads per session; gate first `commit_slice(module)` or auto-inject the skill on focus shift) | Medium-high. Removes a whole class of "model skipped the workflow" failures the gates only partially catch |
| 4 | **Coherence extraction blind spots.** Markdown-table numbers and % renderings are unchecked by the M5 hard gate — self-admitted (`agent/coherence.py:8-10`). | (Internal gap; the references have no equivalent check at all) | M (extend `_NUM`/add a table-cell extractor; renderer sentinels already exclude authoritative blocks, `results_render.py:27-31`) | Medium. Hardens the flagship guarantee against formatting dodges |
| 5 | **Workspace file snapshots / undo.** `versionHistory` covers the context_store (cap 50 — `state.py:109-111,301-308`) but uploads and derived files (`_screened.csv`) have no snapshot/revert. | opencode: out-of-band git snapshot + revert (`snapshot/index.ts:71-84`, `session/revert.ts`); grok-build: per-prompt checkpoints (`rewind.rs:24-30`) | M | Medium. Recoverability for the data files the whole chain hangs off |
| 6 | **Per-model prompt/toolset adaptation.** One `SYSTEM_PROMPT` for Gemini and Claude alike (`runtime.py:189,562-583`). | opencode: `session/prompt/{anthropic,gemini,gpt,…}.txt`; grok-build: per-family toolsets (`config.rs:307-354`) | S–M | Low-medium today (single product), rises with every provider added to `model_factory` |
| 7 | **Corrupt-state read robustness in the file store.** `load()` raises on malformed JSON (`state.py:160-163`). | grok-build: versioned formats with documented migration (`persistence.rs:24-28`) | S | Low (prod is Postgres-backed; CLI/spike only) |

---

## What DoThesis does that neither coding agent does

1. **Deterministic output-correctness verification.** Both references verify that changes applied and diagnostics are clean; DoThesis proves the *content* right — impossible-value/consistency arithmetic at the tool boundary and the commit gate (`agent/stats_validation.py`, `state_tools.py:98-127`), with the "no incorrect statistics" guarantee as the third hard boundary (`AGENTS.md:50`).
2. **An audit trail the audited party can't write.** `NON_CONTENT_KEYS` stripping at the model edge, deterministic-only `decisions`, post-gate provenance injection, earned-not-narrated `done` (`state_tools.py:73-82,163-183`; `state.py:57-69,96-107,286-297`) — test-pinned (`test_state_tools.py:53,79`).
3. **A provenance ledger that classifies every reported number** as computed / validated / unchecked, pinned to a dataset SHA-256, designed so tampering can only *overstate* the compute share, never launder a wrong number (`agent/provenance.py:10-15,36-54,237-312`).
4. **A machine-checkable honesty artifact.** The committee-readiness certificate encodes what it did *not* check as schema (`not_checked`, mandatory limitation strings, tamper-evident hash, degraded-but-valid fallback — `quality/certificate.py:9-42,248-344`) and projects a <2 KB B2B gate summary (`certificate.py:369-387`).
5. **Renderer-over-verified-state.** Chapter tables are byte-projections of persisted, gate-passed results, sentinel-marked so coherence/similarity checkers treat them as authoritative instead of re-litigating them; the LLM writes only connective prose around `[[DT:kind]]` tokens (`orchestrator/tools/results_render.py:1-31`; `agent/coherence.py:286-298`; `skills/dothesis-m5-writing/SKILL.md:136-146`).
6. **Weakness-grounded defense simulation.** Viva questions are generated deterministically from the thesis's actual rubric findings, with grading criteria per question and zero LLM calls in generation (`agent/viva.py:1-60`).
7. **A prompt-injection neutralizer for untrusted document content** — detect + delimit-as-data on every extracted upload (`agent/guardrails.py:24-62`).
8. **Pedagogy as a hard rule**: the two-register (plain Vietnamese analogy + citable formal sentence) requirement, contract-tested (`skills/dothesis/SKILL.md:288-313`; `api/tests/test_skill_content.py:20-22`).

These are the moat. Every one of them reads domain judgment that a horizontal agent has no reason to encode — and, per the vision's own argument (`2026-07-17-dothesis-vertical-agent-vision.md:213-215`), encoded domain judgment compounds only for the vertical.

---

## Method note

All dothesis evidence was read first-hand. opencode and grok-build evidence was gathered by directed exploration of both repos; every opencode citation used in a verdict was independently re-verified against the source (`permission/index.ts`, `tool/edit.ts`, `agent/agent.ts`, `snapshot/index.ts`, `session/instruction.ts`, `session/prompt/`, `tool/*.txt`), and grok-build's core sandbox citations were spot-verified (`xai-grok-sandbox/src/lib.rs:8-18`, `src/deny/mod.rs:75-96`, `permission/auto_mode.rs:379-392`). Where a comparison would have been apples-to-oranges (e.g. scoring the coding agents on statistical verification, or dothesis on multi-model support breadth), the report says so rather than forcing a score.

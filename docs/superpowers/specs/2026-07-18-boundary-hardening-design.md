# Boundary Hardening — Design Spec

**Date:** 2026-07-18
**Status:** Design — approved input for the implementation plan (`2026-07-18-boundary-hardening-plan.md`)
**Source:** `docs/superpowers/specs/2026-07-18-vertical-agent-audit.md` — the ranked gap list (7 gaps). The audit's verdict: DoThesis clears "best vertical agent for quantitative theses" but is **behind** grok-build/opencode on execution isolation and boundary fault posture. This spec closes that categorical weakness without breaking the shipped fail-open-for-legitimate-work posture.
**Repos referenced:**
- dothesis — `/Users/caonguyenvan/project/dothesis`
- grok-build — `/Volumes/SSDportable/projects/grok-build`
- opencode — `/Volumes/SSDportable/projects/opencode`

---

## 1. The governing principle

DoThesis's shipped philosophy is *advisory, not blocking*: "a validator bug must never block a legitimate thesis" (`agent/stats_validation.py:6-8`), pinned by `test_gate_fail_open_on_validator_crash` (`agent/tests/test_state_tools.py:187-195`). The audit shows that the same posture, applied at the wrong layer, is the product's one categorical weakness: an unconfined `Path(file)` and a silently-degrading fabrication gate.

The resolution, stated once and applied per gap:

> **Fail-OPEN for legitimate-but-imperfect work. Fail-CLOSED at the security and fabrication boundary.**
>
> A validator hiccup on a real student's real thesis must not block the thesis (interactive). A path that escapes the project workspace, or an unrunnable gate in an unattended B2B run whose selling point *is* the gate, must refuse — because proceeding is not "imperfect work", it is an unenforced boundary reporting itself as enforced. grok-build's rule for exactly this: "Refusing to start with denied paths unprotected" (`crates/codegen/xai-grok-shell/src/config/mod.rs:1283-1311`) and hard-erroring on any deny path it cannot express rather than leaving it silently unprotected (`crates/codegen/xai-grok-sandbox/src/deny/mod.rs:144-151`).

Which side each gap lands on:

| Gap | Situation | Posture | Why |
|---|---|---|---|
| 1a | `run_stats`/parser `file` resolves outside the project workspace | **Fail-closed** (op refused, correctable JSON error) | A path escape is never legitimate thesis work. There is no user whose real flow needs `/etc/passwd`. |
| 1a | File missing / unreadable *inside* the workspace | Fail-open shape unchanged (existing error JSON) | Legitimate-but-imperfect: wrong filename, not an attack. |
| 2 | M4 stats validator or M5 coherence gate **crashes**, interactive chat | **Fail-open** (unchanged — commit proceeds "unverified") | A coached student with a human in the loop; the rubric/certificate net catches it downstream. |
| 2 | Same crash, headless/B2B strict mode | **Fail-closed** (commit refused) | Unattended; "the gate is the product". The certificate must be able to attest "all gates ran", not just "no gate failed". |
| 3 | Module skill not read before that module's first commit | **Advisory-plus** (one deterministic, correctable nudge; never a hard block) | Skipping workflow guidance is imperfect-but-legitimate work, not fabrication. The hard gates behind commit_slice still catch the worst outcomes. |
| 4 | Prose markdown-table / % rendering contradicts persisted numbers | **Fail-closed** (existing M5 hard-block bar, extended coverage) | Same fabrication boundary as today's `coherence_failed`; only provably-wrong blocks — ambiguous extractions stay soft or unchecked. |

Everything else stays as shipped: soft findings warn, the certificate degrades honestly (`quality/certificate.py:9-15`), garbage state never crashes review/export.

Two hard constraints on every fix:

1. **Deterministic and test-first.** No LLM in any gate. Every new behavior lands as a failing test first.
2. **No regression** of the 900+ green tests (`agent/tests/`, `api/tests/`, `orchestrator/tests/` — `AGENTS.md:77`) or of the shipped gates (M4 stats gate, M5 coherence gate, provenance injection, NON_CONTENT_KEYS stripping).

---

## 2. Gap 1a — Workspace path confinement (effort S, highest impact)

### Today

- `_load_df` is raw `Path(file)` — no confinement (`agent/tools/stats.py:21-32`). `detect` returns per-column `example` values (`stats.py:35-48`), so a prompt-injected turn can read any server-readable file. `screening` with `params.apply` **writes** `<stem>_screened.csv` next to any path (`stats.py:339-342`).
- The parsers say so explicitly: "`run_stats`/`_load_df` ... does `Path(file)` directly — there is NO separate workspace resolver" (`agent/tools/output_parse.py:46-51`); `parse_smartpls_export` and the vision path `parse_output_table` share `_load_bytes` / raw paths (`output_parse.py:82-103,118+`).
- The provenance wrapper re-loads the file a second time for fingerprinting (`stats.py:548-553`) — same raw path.
- Meanwhile the deepagents file tools are *already* confined: `FilesystemBackend(root_dir=project_dir, virtual_mode=True)` refuses absolute-path/`..` escapes (`agent/runtime.py:490-499`). The stats tools simply never went through it.
- The workspace root is well-defined and shared by every surface: `workspace_dir(project_id)` (`api/app/workspace.py:18-21`), with uploads mirrored to `<workspace>/uploads/<name>` (`api/app/routers/uploads.py:166-183`) and the model told about `uploads/...` relative paths in the system prompt (`agent/runtime.py:229-235`).

### Reference bar

grok-build enforces path denial in the kernel, per-alias (`/private` firmlinks), per write sub-action, and **fails closed when a deny path can't be expressed** (`crates/codegen/xai-grok-sandbox/src/deny/mod.rs:39-73,75-96,144-151`). We are not porting Seatbelt; we are porting the two transferable properties: (a) resolve to canonical form *before* checking (their alias lesson = our symlink/`..` lesson), and (b) an inexpressible/unresolvable path is an error, never a silent pass-through.

### Design

**New module `agent/tools/workspace_paths.py`** — pure, stdlib-only (pathlib), no tool imports, fully unit-testable:

```python
class WorkspaceEscapeError(ValueError):
    """The supplied path resolves outside the project workspace."""

def resolve_data_path(file: str, root: Path, *, must_exist: bool = False) -> Path:
    """Resolve `file` against the workspace root; raise WorkspaceEscapeError on escape."""
```

Semantics (each is a test case):

1. Empty/None `file` → `ValueError` (callers with an optional file — `_op_power` `stats.py:298-313`, `_op_method_advice` `stats.py:348-373` — skip resolution on falsy input, preserving the data-free path).
2. Relative input (`"uploads/data.csv"`) → joined under `root`. This *fixes* today's ambiguity where a relative path resolved against the API process CWD.
3. Absolute input → accepted **only if** it resolves inside `root`.
4. Both `root` and the candidate go through `Path.resolve()` (realpath): `..` traversal, and symlinks inside the workspace pointing outside, both resolve to their true target and are then rejected by the containment check (`resolved.is_relative_to(resolved_root)`). This is the grok-build alias lesson applied with Python's tools.
5. Containment failure → `WorkspaceEscapeError` — the fail-closed branch. Resolution *errors* (e.g. a path so malformed `resolve()` raises) are also `WorkspaceEscapeError`: an unresolvable path is never silently allowed (deny/mod.rs:144-151's rule).
6. `must_exist` stays `False` at the resolver — existence is checked where it is today (`_load_df` `stats.py:24-25`), so the missing-file error message shape doesn't change.

**Wiring — one choke point per tool family, ops untouched:**

- `run_stats` becomes a **factory**: `make_stats_tools(project_dir)` in `agent/tools/stats.py`, mirroring the established store-closing factory pattern (`make_state_tools(store)` — `agent/tools/state_tools.py:34`; same pattern noted at `agent/preflight.py:70`). The tool resolves `file` **once at entry** (`stats.py:514` dispatch site) and passes the resolved absolute path into the op functions, which stay byte-identical. The provenance re-load (`stats.py:548`) uses the same resolved path.
  - Why a factory and not a ContextVar: `agent/run_context.py:18-22` documents that its ContextVar "does NOT survive the executor threads LangGraph runs sync tool nodes in" and falls back to a **process-global env var** — safe for one-report-per-subprocess headless, but the chat API serves many projects in one process, so an ambient carrier could cross-contaminate workspace roots. A security boundary must be explicit, not ambient. `build_agent` already has `project_dir` in hand (`agent/runtime.py:484-509`).
- `_op_screening`'s derived file: `<stem>_screened.csv` is derived from the **resolved** source path (`stats.py:339-342`), so it lands inside the workspace by construction; the write path re-asserts containment via the resolver anyway (cheap, and it turns a future refactor bug into a loud error). The legitimate `_screened.csv` flow — screening an in-workspace upload, then running `pls_sem` on the derived file — must keep working; it is a named regression test.
- The parsers become `make_parse_tools(project_dir)` in `agent/tools/output_parse.py`: `_load_bytes` (`output_parse.py:46-51`) takes an already-resolved path; `parse_smartpls_export` and `parse_output_table` resolve at entry. The stale design-note comments at `output_parse.py:4-7,47-49` ("there is NO separate workspace resolver") are updated — they were honest documentation of the gap and must not outlive it.
- `agent/runtime.py` swaps the module-level imports (`runtime.py:171,174`) and tool-list entries (`runtime.py:509,515-516`) for the factory outputs. Tool **names, signatures, and model-facing docstrings stay identical** (`file: Path to the uploaded data file` — `stats.py:511`), plus one added sentence: paths are workspace-relative.
- `check_thresholds` takes no file and stays module-level (`stats.py:416-427`).

**Model-facing failure shape** (consistent with existing tool-error style, `stats.py:514-519`):

```json
{"error": "path_outside_workspace — data files must live in the project workspace",
 "hint": "use the workspace-relative path from [ATTACHED], e.g. uploads/data.csv"}
```

Fail-closed at tool-call granularity: the op does not run, the store is untouched, the turn continues, the model can correct. (An exception raise would abort the whole turn — same reasoning as `state_tools.py:190-193`.)

**Truth repair:** M4 skill's security section claims "The sandbox has no network and no filesystem beyond the workspace" (`skills/dothesis-m4-analysis/SKILL.md:275-279`). After 1a the *filesystem* half is true at the tool boundary; the section is reworded to exactly what is enforced (workspace-confined paths, whitelisted ops, in-process execution pending 1b). Per the repo rule, the skill edit lands **before** the code in the same phase (`AGENTS.md:56`). The `stats.py:5-7` docstring's "in production these run inside the network-less sandbox service" claim is likewise corrected to describe reality + the 1b plan.

### Explicit non-goals for 1a

- No OS sandbox, no subprocess (that is 1b).
- No change to `FilesystemBackend` routing (`runtime.py:496-499`) — already correct.
- No confinement of `research_scout`/network tools — out of audit scope.

---

## 3. Gap 1b — Out-of-process op execution (effort M–L, **design only, deferred**)

Today the ops run "IN-PROCESS (no network, no subprocess)" in the API server (`stats.py:119-125`). One pandas/pyreadstat CVE away from the server process. The reference bar is grok-build's per-subprocess network cut: a seccomp filter installed in `pre_exec` that EPERMs `connect/bind/sendto/...` (`crates/codegen/xai-grok-sandbox/src/child_net.rs:44-102`).

Sketch (to be turned into its own spec when scheduled):

- `agent/stats_worker.py`: a `python -m agent.stats_worker` subprocess per `run_stats` invocation. Protocol: one JSON job `{op, resolved_file, params}` on stdin, one JSON result on stdout, hard rlimits (CPU seconds, address space), `cwd=workspace`, scrubbed env, output size cap. The 1a resolver runs in the **parent** (the boundary stays outside the sandboxed party).
- Network cut per platform: Linux — run under `unshare -n`/`bwrap --unshare-net` when available; macOS — `sandbox-exec` profile denying network; both unavailable → **strict mode refuses to run the op, advisory mode runs in-process and *records* the degradation** (the grok-build `requires_read_deny`-style rule: compute "does this deployment require isolation" from intrinsic config, never from the resolved capability, so failure can't silently downgrade — `crates/codegen/xai-grok-sandbox/src/lib.rs:349-370` per audit).
- The whitelist dict (`stats.py:376-397`) stays the single op registry; the worker imports the same module, so there is exactly one vetted-ops surface.
- Interaction with gap 2: the same `strict_gates` flag governs "isolation unavailable" (see §4) — one policy, two enforcement points.

Not planned in this cycle beyond the sketch; the plan file carries it in the deferred section.

---

## 4. Gap 2 — Fail-closed gate option for headless/B2B (effort S)

### Today

A crashed M4 validator commits "unverified": `_v.get("crashed")` and the wrapping `except Exception` both set `_stats_warnings = "unavailable"` and fall through to the commit (`agent/tools/state_tools.py:113-114,125-127`); the M5 coherence gate has the identical shape (`state_tools.py:147-148,160-162`). Pinned by `test_gate_fail_open_on_validator_crash` (`agent/tests/test_state_tools.py:187-195`). Mode differences already ride as caller-held DATA (`RunProfile`, `agent/headless.py:59-79`), and the headless entrypoint builds the agent itself (`api/app/headless_entry.py:160-161,196`).

### Design

**Policy as an explicit constructor argument, default preserving today's behavior:**

- `make_state_tools(store, *, strict_gates: bool = False)` (`state_tools.py:34`).
- `build_agent(project_dir, ..., strict_gates: bool = False)` threads it through (`runtime.py:471-505`).
- `api/app/headless_entry.py` passes `strict_gates=True` at its `build_agent` call (`headless_entry.py:196`), overridable by job params (`params.get("strict_gates", True)` — partner/B2B default is strict, matching "the gate is the product"). Interactive chat (`api/app/routers/chat_v3.py`) passes nothing and stays fail-open.
- This **preserves the headless invariant** (`agent/headless.py:1-8`): `stream_turn`/`run_headless` still never inspect a profile; the flag is caller-held data set at agent construction, exactly like `RunProfile` is caller-held data at run time. Chat features still cannot gate headless — this is the caller *choosing* strictness, not the spine forking.

**Strict-mode behavior** — in `commit_slice`, at the two crash sites only:

- M4: when `strict_gates` and (`_v.get("crashed")` or the `except Exception` branch fires), return a correctable error instead of falling through:

```json
{"error": "stats_gate_unavailable — the deterministic stats validator could not run; refusing to commit unverified analysis_results (strict gate policy)",
 "hint": "retry the commit; if this persists the run must fail rather than ship unverified numbers"}
```

- M5 coherence crash: same shape, `coherence_gate_unavailable`.
- Store untouched (same guarantee as `test_gate_blocks_impossible_and_store_unchanged`, `test_state_tools.py:160-167`).
- Hard-finding blocks and soft-warning passthroughs are **unchanged in both modes** — strictness only changes what happens when the gate *cannot run*.
- A persistent validator crash in a headless run surfaces as repeated commit errors → no state change → the existing stall machinery bounds it (`agent/headless.py:198-227` stall path, `max_stalls`), and the run fails loudly instead of shipping "unverified". That is the intended behavior; no new budget machinery.

**Attestation — "all gates ran", not just "no gate failed":**

- The deterministic provenance injection (`state_tools.py:163-183`) — which the model structurally cannot author (`NON_CONTENT_KEYS`, `agent/state.py:96`; stripped at `state_tools.py:73-82`) — gains a `gate` field written by the same code path:
  `{"gate": {"stats_validation": "ran" | "unavailable", "policy": "strict" | "advisory"}}` inside the injected `analysis_provenance` summary.
- `quality/certificate.py` reads it: when every persisted gate record says `ran`, the relevant checklist item can attest "all gates ran"; an `unavailable` record downgrades to the existing honest `warn`/`not_checked` vocabulary (`certificate.py:42`). No schema break — additive field, `SCHEMA_VERSION` stays 1 (`certificate.py:26`) since absent fields already degrade.

---

## 5. Gap 4 — Coherence extraction blind spots (effort M)

### Today

The M5 hard gate's extractor is regex-over-sentences and self-admits its blind spots: "Deferred to a future LLM-judge: semantic coherence, markdown-table numbers, '56% of variance' R² renderings" (`agent/coherence.py:8-10`). `_NUM` only matches inline `metric op value` runs (`coherence.py:116-118`); the M5 loop feeds sentence-level claims into `_number_checks`, which hard-blocks only within display-precision tolerance (`coherence.py:257-283,367-401`; `_eps` at 367-369). Renderer sentinels already exclude authoritative rendered tables from checking (`orchestrator/tools/results_render.py:27-31`; stripped via `_strip_rendered`, `coherence.py:286-298`) — so the gap is exactly **hand-typed** markdown tables and percent-rendered R² in un-rendered prose.

### Design — no LLM judge; extend the deterministic extractor

Two additive extractors in `agent/coherence.py`, both feeding the **existing** check/tolerance machinery so the hard-block bar ("only provably-wrong blocks") is inherited, not re-derived:

**(a) Markdown table-cell extractor `extract_table_claims(prose)`**

- Operates on prose *after* `_strip_rendered` (so rendered tables stay exempt — that exemption is the whole point of the sentinels).
- Detects markdown table blocks (`|`-delimited rows with a `---` separator row).
- Maps header cells → metrics using the same vocabulary `_NUM`/`_metric_of` already own (β/beta/hệ số → beta; t; p; f²; R² — `coherence.py:121-133`); parses cells with the existing `_parse_num` (`coherence.py:136-147`), so EU-comma and unicode-minus handling is shared, not duplicated.
- Anchors a row to a hypothesis when a cell contains a unique H-id (`normalize_hypothesis_id`, `coherence.py:29-45`); anchored claims get `attribution: "strong"` → **hard** on mismatch, exactly like sentence claims. A row with no unambiguous anchor, or a header that maps to no known metric, produces **no claim** (unchecked beats guessed — the `output_parse.py:10` "never a fabricated 0" instinct).
- Emitted claims are the same dict shape as `extract_number_claims` (`coherence.py:150-164`) so `_number_checks` (`coherence.py:371-401`) consumes them unchanged.

**(b) Percent-rendered R² extractor**

- New pattern: a number followed by `%` within a sentence that carries a variance-explained cue (en: "of the variance", "variance explained"; vi: "phương sai", "giải thích ... % "), yielding an R² claim with `value/100` and decimals shifted by 2 (so "56%" → 0.56 with tolerance `_eps(2)` on the percent scale ⇒ ±0.005 on the R² scale — display-precision semantics preserved).
- Compared against the construct-level `r2_by_con` the registry already builds from `structural_model.r2` (`coherence.py:250-255`). **Hard** only when the sentence unambiguously names exactly one construct with a stored R²; a sentence naming zero or several matching constructs yields a **soft** finding at most. This keeps the shipped bar: natural-language ambiguity is never a hard block (`coherence.py:5-8`).
- The module docstring's deferred-list (`coherence.py:8-10`) is updated to remove the two now-covered items — same truth-repair rule as the M4 skill.

Certificate/rubric pick these up for free: the safety-net dimensions re-run the same coherence functions over persisted state (`quality/rubric.py:433-455` per audit), so auto-draft/editor/legacy paths inherit the coverage.

---

## 6. Gap 3 — Mechanical skill-adherence enforcement (effort M)

### Today

"Do not act on a module without having read its skill this session" is instruction-only (`skills/dothesis/SKILL.md:317`). The references enforce equivalents mechanically: opencode's edit tool contract errors on edit-without-read and hard-fails on non-matching `oldString` (`packages/opencode/src/tool/edit.txt:1-6`; the code-level refusal shape at `packages/opencode/src/tool/edit.ts:711`); grok-build enforces read-only by *omitting* tools from the toolset (`crates/codegen/xai-grok-agent/src/config.rs:355-379` per audit). Neither shape fits directly: we cannot omit `commit_slice` (it is the only write path), and a permanent hard block on an advisory workflow rule would violate §1.

### Decision on enforcement strength

**Advisory-plus: a deterministic, once-per-module, correctable refusal — never a hard block.** The first `commit_slice(module)` in a session without a recorded read of that module's skill returns a correctable error naming the exact skill path; the nudge is recorded, so a repeated commit proceeds even if the model still refuses to read (no deadlock, no headless run wedged on a stubborn model — the stall budget stays the backstop, `agent/headless.py:69`). Rationale: this converts "instruction the model may drop" into "state machine the model must pass through once", which is the transferable core of opencode's read-before-edit, while keeping the fail-open promise for legitimate flow. Auto-injection of the full skill on focus shift was considered and rejected as the primary mechanism: it burns tokens every shift, defeats progressive disclosure (`AGENTS.md:56` — body <500 lines, heavy detail in `references/`), and *reading* is not *following* anyway; the nudge at the commit point is where the model demonstrably acts on the module.

### Design

- **`agent/skill_tracker.py`** (new, pure): a process-local registry `{project_key: {"read": set[module], "nudged": set[module]}}` plus the module↔skill map `{"M1": "dothesis-m1-topic", ..., "M5": "dothesis-m5-writing"}` (dirs verified under `skills/`). Process-local is deliberate: worst case after an API restart is one extra nudge — benign, deterministic, no store schema change.
- **Read recording**: build_agent wraps the `/skills/` route backend (`runtime.py:496-499`) in a thin `RecordingBackend` decorator around `FilesystemBackend` whose read hook calls `skill_tracker.note_read(project_key, path)` — path→module via the map; non-module skills (root, bootstrap, defense) are ignored. The decorator changes no read semantics (same bytes, same virtual-path refusals).
- **Gate**: in `commit_slice` (`state_tools.py:49+`), before the existing gates: if `module` unread and un-nudged for this project key → record the nudge and return:

```json
{"error": "module_skill_not_read — read the module's skill before its first commit",
 "hint": "read_file('/skills/dothesis-m4-analysis/SKILL.md') then re-run this commit"}
```

- `record_decision` calls `store.commit_slice` directly (`agent/headless.py:50-55`), not the tool wrapper — unaffected, as with every other tool-edge guard (`state_tools.py:79-80`).
- The root skill line 317 gains a sentence documenting that the rule is now mechanically nudged (skill-first edit rule, `AGENTS.md:56`).

---

## 7. Gaps 5–7 — sketches only (deferred)

| # | Gap | Sketch | Effort | Impact |
|---|---|---|---|---|
| 5 | **Workspace file snapshots/undo.** `versionHistory` covers the context_store only (cap 50 — `agent/state.py:109-111`); uploads and `_screened.csv` have no revert. | opencode's shape: an out-of-band snapshot store the model can't write (`packages/opencode/src/snapshot/index.ts:71-84` — separate `--git-dir` keyed by project). For us: `<workspace>/.dt_snapshots/<ts>/` copies taken by deterministic code before the two mutation events (upload overwrite in `uploads.py:166-183`; `apply_screening` write in `stats.py:338-342`), capped count, plus a restore helper. Not exposed as a model tool. | M | Medium — recoverability for the files the whole verified-numbers chain hangs off |
| 6 | **Per-model prompt/toolset adaptation.** One `SYSTEM_PROMPT` regardless of family (`agent/runtime.py:562-583`). | opencode ships per-family prompt files (`packages/opencode/src/session/prompt/`); grok-build per-family toolsets (`config.rs:307-354`). For us: `make_model()` returns a family tag; `build_agent` assembles `SYSTEM_PROMPT + overlays[family]` from small overlay strings (Gemini needs the anti-confabulation reinforcement; Claude needs less). No toolset forking yet — single product. | S–M | Low-medium today; rises with each provider in `model_factory` |
| 7 | **Corrupt-state read robustness (file store).** `load()` raises on malformed JSON (`agent/state.py:160-163`); writes are already atomic tmp+replace (`state.py:165-171`). | Catch `JSONDecodeError` in `load()`: rename the corrupt file to `context_store.json.corrupt-<ts>` (never destroy evidence), attempt the `.json.tmp` sibling, else raise a typed `StateCorruptError` the CLI surfaces with recovery guidance. Prod is Postgres-backed (`AGENTS.md:44`), so CLI/spike only. | S | Low |

---

## 8. Invariants preserved (checklist for review)

- `commit_slice` remains the only write path; no new write paths introduced (`AGENTS.md:45-46`).
- `NON_CONTENT_KEYS` stripping and deterministic-only provenance/decisions authorship untouched; gap 2's `gate` field is written *by* the deterministic injector, extending the "audited party can't write the audit" property, not weakening it (`state_tools.py:73-82,163-183`).
- Interactive fail-open behavior byte-identical: `test_gate_fail_open_on_validator_crash` stays green *as written* (`test_state_tools.py:187-195`).
- Renderer-over-state exemption intact: rendered blocks stay authoritative and unchecked (`results_render.py:27-31`).
- Headless invariant intact: `stream_turn`/`run_headless` never inspect a mode flag (`agent/headless.py:1-8`); strictness is caller-held construction data.
- The `_screened.csv` derived-file flow keeps working end-to-end (named regression test in the plan).

## 9. Risks, ranked

1. **Gap 1a breaks a legitimate path someone relies on.** The CLI spike may pass arbitrary local CSVs; tests pass `tmp_path` absolutes (`agent/tests/test_stats_tool.py:23-29`). Mitigation: the factory takes whatever `project_dir` the caller uses as root (CLI: its own project dir; tests: `tmp_path`), so in-root absolutes keep working; the plan's first wiring task migrates every test fixture and greps all `run_stats` call sites (verified: only `agent/runtime.py` + tests import it).
2. **Gap 2 strict mode wedges a headless run on a persistently-broken validator.** Accepted by design — a loud failed run beats a silent unverified certificate; bounded by `max_stalls`/`max_turns`.
3. **Gap 4 hard-blocks a legitimate table.** Mitigated by inheriting the display-precision tolerance and the "no unambiguous anchor → no claim" rule; the failure mode of a too-timid extractor is a missed check (today's status quo), not a false block.
4. **Gap 3 nudge annoys a correct flow.** Bounded to once per module per process lifetime; measured cost is one extra tool round-trip.

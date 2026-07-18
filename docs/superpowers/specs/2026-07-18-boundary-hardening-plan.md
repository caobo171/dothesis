# Boundary Hardening — Implementation Plan (TDD)

**Date:** 2026-07-18
**Design:** `docs/superpowers/specs/2026-07-18-boundary-hardening-design.md` (read it first — every decision below is justified there)
**Audit source:** `docs/superpowers/specs/2026-07-18-vertical-agent-audit.md` (ranked gap list)
**Executor:** Opus agent, strict TDD — every task writes the failing test FIRST, watches it fail for the right reason, then implements to green. Never weaken an existing test to pass; the fail-open interactive tests are contract, not scaffolding.

**Repo:** `/Users/caonguyenvan/project/dothesis` (branch off current main/dev per repo convention).

**Global verify** (run at the end of every phase, must stay green):

```bash
cd /Users/caonguyenvan/project/dothesis
python -m pytest agent/tests -q
python -m pytest api/tests -q
python -m pytest orchestrator/tests -q
```

**Repo rule that binds every phase:** module-behavior changes edit the relevant `skills/*/SKILL.md` *before* the code (`AGENTS.md:56`).

**Ordering:** Gap 1a (Phases 1–3) → Gap 2 (Phase 4) → Gap 4 (Phase 5) → Gap 3 (Phase 6) → deferred sketches (Phase 7, no code).

---

## Phase 1 — Gap 1a: the pure path resolver

### Task 1.1 — `agent/tools/workspace_paths.py` + `agent/tests/test_workspace_paths.py`

**Files**
- Create `agent/tests/test_workspace_paths.py` (failing first)
- Create `agent/tools/workspace_paths.py`

**Failing tests first** (all pure, `tmp_path`-based, no tool imports):
1. `test_relative_path_resolves_under_root` — `resolve_data_path("uploads/data.csv", root)` → `root/uploads/data.csv` (absolute, resolved).
2. `test_absolute_path_inside_root_accepted` — `resolve_data_path(str(root/"uploads/d.csv"), root)` works.
3. `test_absolute_path_outside_root_rejected` — `/etc/passwd` → `WorkspaceEscapeError`.
4. `test_dotdot_traversal_rejected` — `"uploads/../../secrets.txt"` → `WorkspaceEscapeError`.
5. `test_symlink_escape_rejected` — create `root/uploads/link.csv` symlinking to a file outside root; resolver rejects (realpath containment — the grok-build alias lesson, `crates/codegen/xai-grok-sandbox/src/deny/mod.rs:139-151`).
6. `test_symlink_inside_root_accepted` — an in-root symlink to an in-root target resolves fine.
7. `test_empty_or_none_rejected` — `""`/`None` → `ValueError`.
8. `test_root_itself_and_nested_dirs_ok` — files at root depth and several levels deep both pass.
9. `test_missing_file_inside_root_still_resolves` — resolver does NOT require existence (`must_exist=False` default; existence errors keep their current shape at `_load_df`, `agent/tools/stats.py:24-25`).

**Implementation**: per design §2 — `WorkspaceEscapeError(ValueError)`, `resolve_data_path(file, root, *, must_exist=False)`; `Path.resolve()` on both sides; `is_relative_to` containment; any resolution exception → `WorkspaceEscapeError` (unresolvable is never allowed). Stdlib only.

**Verify**: `python -m pytest agent/tests/test_workspace_paths.py -q`

**Done when**: all 9+ tests green; module imports nothing beyond stdlib.

---

## Phase 2 — Gap 1a: wire `run_stats` (factory) + screening write + provenance

### Task 2.1 — skill/docstring truth first

**Files**
- Edit `skills/dothesis-m4-analysis/SKILL.md:275-279` — reword the Security section to what is enforced after this phase: whitelisted ops only; data paths confined to the project workspace (escapes refused); execution currently in-process, out-of-process isolation planned (design §3).
- Edit the `agent/tools/stats.py:5-7` module docstring the same way (remove the untrue "in production these run inside the network-less sandbox service" present tense).
- Check `api/tests/test_skill_content.py` contract tests still pass (they pin skill↔code drift).

**Verify**: `python -m pytest api/tests/test_skill_content.py -q`

### Task 2.2 — `make_stats_tools(project_dir)` with entry-point confinement

**Files**
- Edit `agent/tests/test_stats_tool.py` (failing tests first, plus fixture migration)
- Edit `agent/tools/stats.py`
- Edit `agent/runtime.py:174,509`

**Failing tests first** (in `test_stats_tool.py`; build tools via the new factory rooted at `tmp_path`):
1. `test_run_stats_rejects_path_outside_workspace` — `run_stats("detect", "/etc/passwd")` → JSON `{"error": "path_outside_workspace ..."}`, hint mentions `uploads/`; no exception raised (turn survives — same rationale as `agent/tools/state_tools.py:190-193`).
2. `test_run_stats_rejects_dotdot_escape` — `"uploads/../../x.csv"` → same error.
3. `test_run_stats_relative_path_resolves_against_workspace` — write `tmp_path/uploads/data.csv`, call with `"uploads/data.csv"`, `detect` returns the schema (this is new capability — today a relative path resolved against process CWD).
4. `test_screening_apply_writes_inside_workspace_only` — the `_screened.csv` derived file lands next to the resolved in-workspace source (`stats.py:339-342`) and a follow-up `run_stats("detect", "uploads/data_screened.csv")` works — the named `_screened.csv` regression test from design §8.
5. `test_power_apriori_without_file_still_works` — `file=""` data-free path untouched (`stats.py:298-313`); same for `method_advice` without file (`stats.py:348-373`).
6. Existing tests migrated: `_run()` helper builds the tool from `make_stats_tools(tmp_path)`; the `csv` fixture already writes under `tmp_path` so in-root absolutes keep passing (design risk #1).

**Implementation**
- `make_stats_tools(project_dir) -> list` in `stats.py`, mirroring `make_state_tools` (`agent/tools/state_tools.py:34`). The `@tool run_stats` moves inside, closing over the resolved root. Tool name/signature/docstring unchanged except one added sentence ("paths are workspace-relative").
- At entry (current dispatch site `stats.py:514-521`): falsy `file` → skip resolution (power/method_advice); else `resolve_data_path(file, root)`; `WorkspaceEscapeError` → the error JSON above; on success pass the **resolved absolute path** into the op (`fn(str(resolved), ...)`) — op bodies stay byte-identical.
- Provenance capture (`stats.py:542-555`) uses the same resolved path for `_load_df`/`dataset_fingerprint`/`append_ledger_row` — the ledger sidecar (`agent/provenance.py:28,165`) is thereby workspace-anchored too.
- `_op_screening`'s write (`stats.py:339-342`): derive from the resolved source, then re-assert containment via `resolve_data_path(str(out_path), root)` before writing (loud-error future-proofing, design §2).
- `agent/runtime.py`: replace the `run_stats` import/entry (`runtime.py:174,509`) with `*make_stats_tools(project_dir)` inside `build_agent`.
- Grep check (already verified once, re-verify at implementation): `run_stats` is imported only by `agent/runtime.py` and tests.

**Verify**: `python -m pytest agent/tests/test_stats_tool.py agent/tests/test_stats_validation.py -q` then the global verify (provenance + validation wrappers must not regress: `stats.py:527-556` behavior unchanged for in-workspace files).

**Done when**: escapes are refused with the correctable JSON error; every pre-existing stats test green after fixture migration; `_screened.csv` flow proven end-to-end.

---

## Phase 3 — Gap 1a: wire the parsers

### Task 3.1 — `make_parse_tools(project_dir)`

**Files**
- Edit `agent/tests/test_output_parse_vision.py` (+ any other parser tests found under `agent/tests/`) — failing first
- Edit `agent/tools/output_parse.py`
- Edit `agent/runtime.py:171,515-516`

**Failing tests first**
1. `test_parse_smartpls_export_rejects_outside_workspace` — absolute path outside root → fail-soft JSON error (the tool already fail-softs on parse errors, `output_parse.py:99-103`; escape must produce the same *shape* but the distinct `path_outside_workspace` message — never a raise).
2. `test_parse_output_table_rejects_outside_workspace` — same for the vision path (`output_parse.py:118+`); the `_vision_read` stub must NOT be reached (assert the stub is not called — proves rejection happens before any model/network hop).
3. `test_parse_smartpls_export_relative_path_resolves` — a real minimal `.xlsx`/HTML under `tmp_path/uploads/` parses via `"uploads/export.xlsx"`.
4. Existing stub-based tests migrated to the factory (they stub `_load_bytes`/`_vision_read` and never touch disk — keep that property; resolution happens before the stubbed seam, so stubs receive resolved paths).

**Implementation**
- `make_parse_tools(project_dir) -> list` returning `parse_smartpls_export`, `parse_output_table`; resolve at each tool entry; `_load_bytes` (`output_parse.py:46-51`) now documented as taking an already-resolved path.
- Update the stale design-note comments (`output_parse.py:4-7,47-49`) that say "there is NO separate workspace resolver" — there is now; the comment must not outlive the gap (design §2).
- `agent/runtime.py`: swap imports/entries (`runtime.py:171,515-516`) for `*make_parse_tools(project_dir)`.

**Verify**: `python -m pytest agent/tests/test_output_parse_vision.py -q` then global verify.

**Done when**: both parsers refuse escapes fail-soft, accept workspace-relative paths, and all migrated tests are green. **Gap 1a is now closed at every op/parser entry.**

---

## Phase 4 — Gap 2: strict gate policy for headless/B2B

### Task 4.1 — `strict_gates` through `make_state_tools`

**Files**
- Edit `agent/tests/test_state_tools.py` — failing first
- Edit `agent/tools/state_tools.py`

**Failing tests first**
1. `test_strict_gate_refuses_commit_on_validator_crash` — build tools with `make_state_tools(store, strict_gates=True)`; monkeypatch `validate_analysis_results` to raise (exact pattern of the existing fail-open test, `test_state_tools.py:187-195`); commit returns `{"error": "stats_gate_unavailable ..."}` and `store.load()["contextStore"].get("analysis_results") is None` (store untouched — mirror of `test_state_tools.py:160-167`).
2. `test_strict_gate_refuses_on_crashed_flag` — monkeypatch to return `{"crashed": True, ...}` (the `_v.get("crashed")` branch, `state_tools.py:113-114`) → same refusal.
3. `test_strict_gate_refuses_m5_commit_on_coherence_crash` — same shape for the M5 gate crash branches (`state_tools.py:147-148,160-162`) → `coherence_gate_unavailable`.
4. `test_strict_gate_clean_and_hard_paths_unchanged` — with `strict_gates=True`, a clean commit succeeds and a hard finding still returns `stats_validation_failed` (strictness only changes the cannot-run branch).
5. **Unmodified**: `test_gate_fail_open_on_validator_crash` (`test_state_tools.py:187-195`) must stay green *as written* — default remains fail-open.

**Implementation**: `make_state_tools(store, *, strict_gates: bool = False)` (`state_tools.py:34`); in the M4 crash branches (`state_tools.py:113-114` and the `except` at `125-127`) and M5 crash branches (`147-148`, `160-162`): if strict → return the refusal JSON (design §4 wording) before any `store.commit_slice`; else current behavior byte-identical.

**Verify**: `python -m pytest agent/tests/test_state_tools.py -q`

### Task 4.2 — thread the flag: `build_agent` → headless entry

**Files
**- Edit `agent/tests/test_runtime_state_header.py` or a new `agent/tests/test_build_agent_gates.py` — failing first
- Edit `agent/runtime.py:471-505`
- Edit `api/app/headless_entry.py:196`
- (Optionally) `api/tests/` — a headless-entry unit asserting the param default

**Failing tests first**
1. `test_build_agent_passes_strict_gates` — `build_agent(tmp_path, strict_gates=True, model=<fake>)` produces a `commit_slice` tool that refuses on a crashed validator (reuse the Task 4.1 monkeypatch through the built agent's tool set, or assert via `make_state_tools` call spy).
2. `test_headless_entry_defaults_strict` — the headless entry computes `strict_gates=True` unless `params["strict_gates"]` is explicitly false (test the small pure helper you extract for this, same style as `_build_profile`, `api/app/headless_entry.py:48-73`).

**Implementation**: `build_agent(project_dir, ..., strict_gates=False)` forwards to `make_state_tools(store, strict_gates=strict_gates)` (`runtime.py:505`); `headless_entry` passes `strict_gates=params.get("strict_gates", True)` at `headless_entry.py:196`. `chat_v3` untouched (fail-open default). Headless invariant intact: `run_headless`/`stream_turn` never read the flag (design §4).

**Verify**: `python -m pytest agent/tests -q && python -m pytest api/tests -q`

### Task 4.3 — attest "all gates ran" in provenance + certificate

**Files**
- Edit `agent/tests/test_state_tools.py`, `quality/tests/` (locate the certificate tests; audit cites `quality/certificate.py:248-344`) — failing first
- Edit `agent/tools/state_tools.py:163-183` (provenance injection)
- Edit `quality/certificate.py`

**Failing tests first**
1. `test_provenance_records_gate_ran` — after a clean M4 commit, injected `analysis_provenance["gate"] == {"stats_validation": "ran", "policy": "advisory"}` (and `"strict"` when strict); model-supplied `analysis_provenance` still stripped (`NON_CONTENT_KEYS`, `state_tools.py:73-82` — extend the existing strip test's assertions, do not weaken).
2. `test_certificate_attests_all_gates_ran` — certificate built over state whose gate records all say `ran` includes the attestation; an `unavailable` record degrades to existing `warn`/`not_checked` vocabulary (`certificate.py:42`), never `pass`.
3. `test_certificate_degrades_without_gate_field` — legacy state with no `gate` field yields today's exact output (additive-only, schema stays v1 — `certificate.py:26`).

**Implementation**: per design §4 — the deterministic injector writes `gate`; certificate reads it in the relevant checklist item. Written only by the code path the model cannot author.

**Verify**: `python -m pytest agent/tests/test_state_tools.py -q` plus the certificate test file; then global verify.

**Done when**: strict runs refuse unverified commits; interactive is byte-identical; the certificate can truthfully distinguish "all gates ran" from "no gate failed".

---

## Phase 5 — Gap 4: coherence table + percent extraction

### Task 5.1 — markdown table-cell extractor

**Files**
- Edit `agent/tests/test_coherence.py` — failing first
- Edit `agent/coherence.py`

**Failing tests first**
1. `test_table_claim_mismatch_hard_blocks` — M5 prose containing a hand-typed markdown table (`| H | β | t | p |` header, row `| H1 | 0.45 | ... |`) where persisted beta is 0.3391 (fixture shape from `test_state_tools.py:213-214`) → hard `coherence.number_mismatch`; through the tool, the commit is refused with `coherence_failed` (`state_tools.py:149-157`).
2. `test_table_claim_within_tolerance_passes` — table value 0.34 vs stored 0.3391 → no finding (display-precision `_eps`, `coherence.py:367-369`).
3. `test_rendered_table_still_exempt` — the same mismatching table wrapped in renderer sentinels (`orchestrator/tools/results_render.py:27-31`) produces NO finding (`_strip_rendered` runs first, `coherence.py:286-298`) — the exemption is a contract, pin it.
4. `test_table_without_anchor_produces_no_claim` — a row with no H-id (or ambiguous ids) yields no hard finding (unchecked beats guessed).
5. `test_table_eu_commas_and_unicode_minus` — `0,45` / `−0,45` cells parse via the shared `_parse_num` (`coherence.py:136-147`).
6. `test_vietnamese_header_maps_to_metric` — `| GT | Hệ số | t | p |` header maps `Hệ số` → beta (vocabulary from `_metric_of`, `coherence.py:121-133`).

**Implementation**: `extract_table_claims(prose)` per design §5(a); emitted claims identical in shape to `extract_number_claims` output (`coherence.py:150-164`) and appended into the same per-hypothesis `m5.claims` list the registry builds (`coherence.py:257-283`) so `_number_checks` (`coherence.py:371-401`) needs zero changes.

### Task 5.2 — percent-rendered R²

**Failing tests first** (same files)
1. `test_percent_variance_mismatch` — prose "The model explains 56% of the variance in PI" with stored `structural_model.r2 = {"PI": 0.31}` → finding; **hard** only because exactly one construct matches (`r2_by_con`, `coherence.py:250-255`).
2. `test_percent_variance_match_passes` — 56% vs stored 0.5612 → no finding (tolerance on the percent scale: `_eps(decimals+2)` semantics, design §5(b)).
3. `test_percent_ambiguous_construct_soft_or_skipped` — sentence naming two stored constructs → at most a soft finding, never hard (the shipped "only provably-wrong blocks" bar, `coherence.py:5-8`).
4. `test_vietnamese_variance_phrasing` — "giải thích 56% phương sai của PI" is recognized.

**Implementation**: per design §5(b). Update the module docstring's deferred-list (`coherence.py:8-10`) to drop the two now-covered items.

**Verify**: `python -m pytest agent/tests/test_coherence.py agent/tests/test_state_tools.py -q`; then global verify (rubric safety-net dimensions re-run these functions — `quality/rubric.py` tests must stay green).

**Done when**: a hand-typed table or percent rendering can no longer dodge the M5 hard gate; rendered blocks remain exempt; no new false-block class (tolerance + anchor rules proven).

---

## Phase 6 — Gap 3: mechanical skill-read nudge

### Task 6.1 — skill first, then tracker + gate

**Files**
- Edit `skills/dothesis/SKILL.md` (line 317 area) — note the rule is now mechanically nudged (skill-before-code, `AGENTS.md:56`)
- Create `agent/tests/test_skill_tracker.py` — failing first
- Create `agent/skill_tracker.py`
- Edit `agent/tools/state_tools.py` (gate) and `agent/runtime.py:496-499` (RecordingBackend wrap)
- Edit `agent/tests/test_state_tools.py` (gate-level tests)

**Failing tests first**
1. `test_note_read_maps_skill_path_to_module` — `/skills/dothesis-m4-analysis/SKILL.md` → M4 recorded; root/bootstrap/defense skill paths ignored (dirs verified: `skills/dothesis-m{1..5}-*`).
2. `test_first_commit_without_skill_read_is_nudged_once` — `commit_slice("M4", ...)` with no recorded read → `{"error": "module_skill_not_read ...", "hint": "read_file('/skills/dothesis-m4-analysis/SKILL.md') ..."}`, store untouched; the SAME commit repeated → proceeds (nudge recorded — never a deadlock, design §6).
3. `test_commit_after_skill_read_passes_first_time` — `note_read` then commit → no nudge.
4. `test_record_decision_is_never_nudged` — `record_decision` (`agent/headless.py:19-56`) writes through `store.commit_slice` directly and is unaffected.
5. `test_recording_backend_preserves_read_semantics` — the wrapped `/skills/` backend returns identical bytes and still refuses escapes (decorator adds observation only).
6. `test_tracker_isolated_per_project` — two stores/projects don't share nudge state.

**Implementation**: per design §6 — process-local registry keyed per project; `RecordingBackend` decorator around the `/skills/` route's `FilesystemBackend` (`runtime.py:496-499`) feeding `note_read`; gate check in `commit_slice` before the existing gates. Enforcement strength is fixed by the design: once-per-module correctable nudge, never a hard block — do not "improve" it into a hard gate.

**Verify**: `python -m pytest agent/tests/test_skill_tracker.py agent/tests/test_state_tools.py agent/tests/test_headless_runner.py -q`; then global verify (headless runner must not gain stalls from the nudge — the nudge+read+commit cycle changes state, so the stall detector sees progress, `agent/headless.py:198-207`).

**Done when**: the first module commit in a session mechanically requires (one round-trip of) the skill read; no flow can deadlock on it; headless tests green.

---

## Phase 7 — Deferred, sketched (NO code this cycle)

Recorded here so the backlog carries real citations; each needs its own mini-design before implementation.

| # | Item | Sketch (see design §3, §7) | Effort | Impact |
|---|---|---|---|---|
| 1b | **Out-of-process op execution** | `agent/stats_worker.py` subprocess per op: JSON over stdin/stdout, rlimits, cwd=workspace, scrubbed env; network cut via `bwrap --unshare-net` (Linux) / `sandbox-exec` (macOS); strict mode refuses when isolation is unavailable, advisory mode records the degradation (grok-build's intrinsic-requirement rule, `crates/codegen/xai-grok-sandbox/src/lib.rs:349-370`; network-cut reference `src/child_net.rs:44-102`). Resolver stays in the parent. | M–L | High — closes the pandas/pyreadstat-CVE-to-server-process hop; makes the M4 skill's sandbox sentence fully true |
| 5 | **Workspace file snapshots/undo** | Deterministic pre-mutation copies to `<workspace>/.dt_snapshots/<ts>/` before upload overwrite (`api/app/routers/uploads.py:166-183`) and screening apply (`agent/tools/stats.py:338-342`); capped; restore helper; not a model tool. Reference: opencode's out-of-band snapshot store (`packages/opencode/src/snapshot/index.ts:71-84`). | M | Medium |
| 6 | **Per-model prompt/toolset adaptation** | `make_model()` returns a family tag; `build_agent` appends small per-family overlay strings to `SYSTEM_PROMPT` (`agent/runtime.py:562-583`). Reference: `packages/opencode/src/session/prompt/`, grok-build per-family toolsets. | S–M | Low-medium |
| 7 | **Corrupt-state read robustness (file store)** | `load()` (`agent/state.py:160-163`): catch `JSONDecodeError` → rename to `.corrupt-<ts>`, try the `.json.tmp` sibling, else raise typed `StateCorruptError`. Prod is Postgres (`AGENTS.md:44`) — CLI/spike only. | S | Low |

---

## Completion checklist (whole plan)

- [ ] Phases 1–6 landed in order, each with failing-test-first commits.
- [ ] Global verify green: `agent/tests`, `api/tests`, `orchestrator/tests` — zero pre-existing tests weakened or deleted; `test_gate_fail_open_on_validator_crash` (`agent/tests/test_state_tools.py:187`) unchanged.
- [ ] `_screened.csv` end-to-end regression test exists and passes (Phase 2, test 4).
- [ ] Skill files updated *before* code in Phases 2 and 6; `api/tests/test_skill_content.py` green.
- [ ] The two stale "there is NO workspace resolver" comments (`agent/tools/output_parse.py:4-7,47-49`) and the untrue sandbox-service docstring (`agent/tools/stats.py:5-7`) are gone.
- [ ] Certificate distinguishes "all gates ran" from "no gate failed" (Phase 4.3), additively.

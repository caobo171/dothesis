# DoThesis skills (v3 deep-agent runtime)

Promoted from `dothesis_v2/skills/` (the Claude.ai bundle validated in the 2026-06-10 PDF
session) and adapted for the in-app deepagents runtime per
`docs/architecture/2026-06-10-deepagent-skills-architecture.md`.

Deltas from the v2 bundle:

- `SKILL.md` (uppercase) per the deepagents layout; `dothesis-router` is retired — the
  agent's own skill-matching does the dispatch, and the read/mutate semantics live in the
  root `dothesis` skill while enforcement lives in the `commit_slice` tool.
- State is server-side: `/project/context_store.json` is read through `read_slice` and
  written ONLY through `commit_slice` (which versions, shifts focus, and flags downstream
  `needs_review` deterministically). No "download the artifact" step.
- M2 calls the engine research stack through the `research_scout` / `parse_reference`
  tools instead of relying on model memory or native-only PDF reading.
- M5 generates and exports through the engine writing pipeline (`write_pipeline`,
  `export_docx`) instead of ad-hoc python-docx scripting.

One source tree, two targets: the Claude.ai bundle in `dothesis_v2` remains the
zero-infra distribution; behavioral edits should land here first and be back-ported.

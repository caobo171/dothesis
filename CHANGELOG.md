# Changelog

All notable changes are documented in this file.

## Unreleased

### Added
- Hosted SaaS MVP. New `api/` FastAPI service with email/password auth, papers/jobs CRUD, live progress over SSE, and AWS S3 artifact storage. Wires the existing `web/` Next.js template to the existing engine pipeline via a per-job subprocess (`python -m engine`) that streams events through a JSONL file.
- `engine/__main__.py` subprocess entrypoint with JSONL event writer and S3 uploader.
- `dev.sh` brings up the full stack (API + web).
- Spec and implementation plan under `docs/superpowers/`.

### Excluded (deferred to future specs)
- Billing, credits, paid plans, affiliate program (Sidebar entries removed).
- Rich-text draft editing — MVP viewer is read-only.
- Admin / quota UI; quotas hard-coded in `api/app/quotas.py`.

## 2026-02-16

### Added
- CI quality gate workflow: `.github/workflows/quality.yml`
- Maintainer push/auth runbook: `docs/MAINTAINER_PUSH_RUNBOOK.md`
- Automated push preflight checker: `scripts/push-preflight.sh`

### Changed
- Migrated Gemini runtime usage from legacy SDK to `google-genai` wrappers across engine modules.
- Replaced deprecated `google-generativeai` dependency pins with `google-genai>=1.0.0`.
- Stabilized pytest harness with strict markers and integration test separation.

### Fixed
- Output cleaning regression that could strip real references sections.
- Live factcheck integration tests now skip safely in offline/restricted environments.

### Verification
- `python3 -W error::SyntaxWarning -m compileall -q engine tests` passed.
- `python3 -m pytest tests -q` passed (`286 passed, 4 deselected`).
- Push preflight passed with clean sync and correct maintainer account.

### Follow-up
- Aligned CLI/npm requirement consistency (`6e74e75`).
- Hardened live script execution paths (`python tests/test_live_crafter.py`, `python tests/audit_output.py`) with prerequisite-aware skip behavior.
- Expanded CI quality workflow to execute `python -m pytest tests -q`.
- Added secret-gated live-validation workflow (`.github/workflows/live-validation.yml`) for weekly/manual execution of API-backed checks.
- Fixed live audit model selection to use `GEMINI_MODEL` override with `gemini-2.0-flash` fallback (`f8b8a6c`).
- Verified live-validation workflow success on GitHub Actions (`run 22061717973`).
- Fixed quality CI pytest collection error by removing stale `genai.GenerativeModel` annotation from `engine/utils/citation_compiler.py`.

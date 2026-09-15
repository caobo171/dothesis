# Recovery Doctor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every turn, reconcile what a project HAS (uploads on disk, prose already written) against what its state SAYS, and repair the difference.

**Architecture:** A pure-function diagnosis module (`orchestrator/doctor.py`) that makes no model call and touches no I/O, plus an adapter (`api/app/doctor_adapter.py`) that gathers its input from Postgres and the workspace mirror, applies deterministic repairs through `DbProjectStateStore`, and renders a directive for repairs that need the agent. `chat_v3` calls the adapter once per turn.

**Tech Stack:** Python 3.13, SQLAlchemy 2 (`Session`, `select`), Alembic, Pydantic v2, pytest. Run tests with `api/.venv/bin/python -m pytest` (the venv is arm64; do not invoke `.venv/bin/pytest` directly).

**Spec:** `docs/superpowers/specs/2026-09-15-recovery-doctor-design.md`

## Global Constraints

- **Diagnosis makes no model call.** Every check in `orchestrator/doctor.py` is a function of its arguments. Where a repair needs a model it uses the configured default (`gpt-5.6-luna` via `get_orchestrator_llm`); no new cheap-model route.
- **Chapter 4 does not require raw data.** An uploaded SmartPLS/SPSS results export is sufficient on its own.
- **`agent/` must never import `app/`.** `orchestrator/doctor.py` imports neither.
- **Every new endpoint is `@router.post`.** No task here adds one, but if you do, POST only.
- **`DbProjectStateStore` only round-trips `SLICE_OWNERSHIP` keys.** A new `context_store` column needs explicit `load`/`_save` support plus a round-trip test, or it is dead in production.
- **`analysis_results` / `results` is ONE dict keyed by table**, never a list.
- Verified symbols, use these exact paths: `orchestrator.state.dod_for_module` (NOT `orchestrator.artifacts`), `orchestrator.backfill.reconstructable_modules(context_store)`, `orchestrator.tools.m5_writing.chapter_prose(m5_slice)`, `orchestrator.tools.m5_writing._is_stub_prose(prose)`, `ProjectStateStore.commit_slice(module, writes, reason, confirm_done=False, status_overrides=None)`.
- Current Alembic head: `20260915_m5canon01`. New migrations set `down_revision = "20260915_m5canon01"`.

---

### Task 1: Doctor types and the three pure checks that need no parsing

**Files:**
- Create: `orchestrator/doctor.py`
- Test: `orchestrator/tests/test_doctor.py`

**Interfaces:**
- Consumes: `orchestrator.state.dod_for_module`, `orchestrator.backfill.reconstructable_modules`, `orchestrator.tools.m5_writing._is_stub_prose`
- Produces: `UploadRecord`, `DoctorInput`, `Finding` dataclasses; `diagnose(inp: DoctorInput) -> list[Finding]`. Finding codes: `UNREAD_UPLOAD`, `RESULTS_NOT_IN_STATE`, `FALSE_DONE`, `REFUSAL_CHAPTER`, `BACKFILL_AVAILABLE`. `Finding.repair` is one of `"deterministic" | "directive" | "ask_student"`.

- [ ] **Step 1: Write the failing test**

```python
"""The doctor's diagnosis is a pure function — no DB, no model, no disk."""
from orchestrator.doctor import DoctorInput, UploadRecord, diagnose


def _codes(findings):
    return {f.code for f in findings}


def test_an_upload_with_text_that_never_rode_a_turn_is_unread():
    inp = DoctorInput(
        context_store={},
        uploads=[UploadRecord(upload_id="u1", filename="_Result.docx",
                              sidecar_text="| ATT_1 | 0.854 |", ever_attached=False)],
        chapter_prose={},
    )
    assert "UNREAD_UPLOAD" in _codes(diagnose(inp))


def test_an_attached_upload_is_not_flagged_unread():
    inp = DoctorInput(
        context_store={},
        uploads=[UploadRecord(upload_id="u1", filename="a.docx",
                              sidecar_text="text", ever_attached=True)],
        chapter_prose={},
    )
    assert "UNREAD_UPLOAD" not in _codes(diagnose(inp))


def test_a_confirmed_module_failing_its_dod_is_false_done():
    # M4 confirmed with results {} — exactly project 500319a8 on 2026-09-15.
    inp = DoctorInput(
        context_store={"m4_analysis": {
            "analysis_outline": {"research_design": "Định lượng"},
            "results": {},
            "confirmed_at": "2026-09-15T05:33:22+00:00"}},
        uploads=[], chapter_prose={},
    )
    findings = [f for f in diagnose(inp) if f.code == "FALSE_DONE"]
    assert findings, "M4 confirmed with empty results must be FALSE_DONE"
    assert findings[0].repair == "deterministic"


def test_a_refusal_chapter_is_flagged_as_a_directive_repair():
    inp = DoctorInput(
        context_store={}, uploads=[],
        chapter_prose={"methodology": (
            "Chưa thể biên soạn Chương 3 theo các yêu cầu đã nêu vì các trường "
            "đầu vào quyết định cấu trúc và nội dung phương pháp hiện chưa có "
            "giá trị cụ thể. Để tạo chương hoàn chỉnh, cần cung cấp paradigm, "
            "research design, analysis tool và sampling strategy.")},
    )
    findings = [f for f in diagnose(inp) if f.code == "REFUSAL_CHAPTER"]
    assert findings
    assert "methodology" in findings[0].detail
    assert findings[0].repair == "directive"


def test_a_healthy_project_produces_no_findings():
    assert diagnose(DoctorInput(context_store={}, uploads=[], chapter_prose={})) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `api/.venv/bin/python -m pytest orchestrator/tests/test_doctor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'orchestrator.doctor'`

- [ ] **Step 3: Write minimal implementation**

```python
"""Reconcile what a project HAS against what its state SAYS. No I/O, no model.

Diagnosis is a pure function so it can run on every turn for free and be
tested with literals. The adapter (api/app/doctor_adapter.py) does all the
gathering and all the repairing; this module only decides what is wrong.

Why this exists: on the dev database 12 of 21 uploads had never ridden a turn,
and project 500319a8 held 102 rows of real SmartPLS coefficients in
`uploads/_Result.docx.txt` while `m4_analysis.results` was `{}`. Nothing
noticed either, so the project looked healthy while being empty.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class UploadRecord:
    upload_id: str
    filename: str
    sidecar_text: str | None
    ever_attached: bool


@dataclass(frozen=True)
class DoctorInput:
    # PER-MODULE slices, as load_full_context_store() returns them. Not
    # flattened: every slice has its own `confirmed_at`, so a flat dict cannot
    # say WHICH module is falsely done, and reconstructable_modules wants this
    # shape anyway.
    context_store: dict
    uploads: list[UploadRecord]
    chapter_prose: dict[str, str]


@dataclass(frozen=True)
class Finding:
    code: str
    detail: str
    repair: str
    payload: dict = field(default_factory=dict)


# Module id -> its slice key in the context store. Mirrors
# orchestrator.state._MODULE_TO_FIELD; kept local so doctor.py stays a pure
# module with no import-time dependency on the state package.
_MODULE_FIELD = {
    "M1": "m1_topic",
    "M2": "m2_literature",
    "M3": "m3_design",
    "M4": "m4_analysis",
}


def _unread_uploads(inp: DoctorInput) -> list[Finding]:
    out = []
    for u in inp.uploads:
        if u.ever_attached or not (u.sidecar_text or "").strip():
            continue
        out.append(Finding(
            code="UNREAD_UPLOAD",
            detail=f"{u.filename} đã tải lên nhưng chưa từng được đọc.",
            repair="deterministic",
            payload={"upload_id": u.upload_id, "filename": u.filename},
        ))
    return out


def _false_done(inp: DoctorInput) -> list[Finding]:
    """A module wearing `confirmed_at` while its own DoD says it is not done.

    Per-slice, not flat: `confirmed_at` exists on every module, so a flattened
    store would report whichever one happened to land last.
    """
    from orchestrator.state import dod_for_module  # noqa: PLC0415

    cs = inp.context_store or {}
    out = []
    for module, field_name in _MODULE_FIELD.items():
        slice_ = cs.get(field_name) or {}
        if not isinstance(slice_, dict) or not slice_.get("confirmed_at"):
            continue
        dod = dod_for_module(module)
        if dod is None:
            continue
        result = dod(slice_)
        if not result.done:
            out.append(Finding(
                code="FALSE_DONE",
                detail=f"{module} đang được đánh dấu xong nhưng còn thiếu: "
                       f"{', '.join(result.gaps)}.",
                repair="deterministic",
                payload={"module": module, "gaps": list(result.gaps)},
            ))
    return out


def _refusal_chapters(inp: DoctorInput) -> list[Finding]:
    from orchestrator.tools.m5_writing import _is_stub_prose  # noqa: PLC0415

    out = []
    for name, prose in (inp.chapter_prose or {}).items():
        if _is_stub_prose(prose or ""):
            out.append(Finding(
                code="REFUSAL_CHAPTER",
                detail=f"Chương `{name}` hiện không có nội dung thật.",
                repair="directive",
                payload={"chapter": name},
            ))
    return out


def diagnose(inp: DoctorInput) -> list[Finding]:
    """Every problem this project has that the doctor knows how to name."""
    return _unread_uploads(inp) + _false_done(inp) + _refusal_chapters(inp)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `api/.venv/bin/python -m pytest orchestrator/tests/test_doctor.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add orchestrator/doctor.py orchestrator/tests/test_doctor.py
git commit -m "feat(doctor): pure diagnosis for unread uploads, false done, refusal chapters"
```

---

### Task 2: The results parser — turn an extracted sidecar into a results dict

**Files:**
- Modify: `orchestrator/doctor.py`
- Create: `orchestrator/tests/fixtures/result_docx_sidecar.txt` (copy of the real file, see Step 1)
- Test: `orchestrator/tests/test_doctor_results_parser.py`

**Interfaces:**
- Consumes: Task 1's `Finding`, `DoctorInput`
- Produces: `parse_results_tables(sidecar_text: str) -> dict[str, list[dict]]` — ONE dict keyed by canonical table name; `{}` when nothing qualifies. Adds the `RESULTS_NOT_IN_STATE` finding to `diagnose`, whose `payload["results"]` carries that dict.

- [ ] **Step 1: Create the fixture from the real file**

```bash
mkdir -p orchestrator/tests/fixtures
cp "var/jobs/agent_projects/500319a8-5a06-47bf-bfd8-3ef921b36184/uploads/_Result.docx.txt" \
   orchestrator/tests/fixtures/result_docx_sidecar.txt
```

This is the actual student file that exposed the bug: 13,634 bytes, 125 pipe rows, 102 of them carrying coefficients. Parsing anything else proves nothing.

- [ ] **Step 2: Write the failing test**

```python
"""The parser runs against the REAL sidecar that exposed the bug."""
from pathlib import Path

import pytest

from orchestrator.doctor import parse_results_tables

FIXTURE = Path(__file__).parent / "fixtures" / "result_docx_sidecar.txt"


@pytest.fixture
def sidecar() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_returns_one_dict_keyed_by_table(sidecar):
    out = parse_results_tables(sidecar)
    assert isinstance(out, dict), "results is ONE dict keyed by table, never a list"
    assert out, "the real file has 102 coefficient rows — parsing none is a bug"


def test_outer_loadings_carry_the_real_numbers(sidecar):
    out = parse_results_tables(sidecar)
    flat = [row for rows in out.values() for row in rows]
    att1 = [r for r in flat if r.get("label") == "ATT_1"]
    assert att1, f"ATT_1 missing; tables found: {list(out)}"
    assert 0.854 in att1[0]["values"]


def test_a_sidecar_with_no_coefficient_table_yields_nothing(sidecar):
    # A partial parse is worse than none: it reads as a finished analysis.
    assert parse_results_tables("Chương 1\n\nKhông có bảng số liệu nào ở đây.") == {}
    assert parse_results_tables("") == {}


def test_an_unrecognised_heading_keeps_its_own_text_as_the_key():
    raw = ("Bảng lạ không ai biết\n"
           "| X_1 | 0.911 |\n"
           "| X_2 | 0.902 |\n")
    out = parse_results_tables(raw)
    assert out, "an unknown heading must not drop the table"
    assert any("lạ" in k for k in out), f"heading text not preserved: {list(out)}"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `api/.venv/bin/python -m pytest orchestrator/tests/test_doctor_results_parser.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_results_tables'`

- [ ] **Step 4: Write the implementation**

Append to `orchestrator/doctor.py`:

```python
import re

# A coefficient is a decimal with at least two places: 0.854, 12.30. Integers
# are excluded because item counts and sample sizes are not results.
_COEF_RE = re.compile(r"-?\d+\.\d{2,}")
# Heading -> canonical table. Checked in order, first hit wins, so the more
# specific patterns (HTMT, VIF) come before the broader reliability keywords.
_TABLE_KEYWORDS = (
    ("discriminant_validity", ("htmt", "heterotrait", "fornell", "larcker")),
    ("collinearity", ("vif", "đa cộng tuyến", "collinearity")),
    ("explained_variance", ("r²", "r2", "r square", "q²", "q2", "f²", "f2")),
    ("reliability", ("cronbach", "composite reliability", " cr ", "ave",
                     "độ tin cậy")),
    ("path_coefficients", ("path", "đường dẫn", "hệ số tác động",
                           "structural", "giả thuyết")),
    ("outer_loadings", ("outer loading", "hệ số tải", "factor loading",
                        "loading")),
)


def _canonical_table(heading: str) -> str:
    h = f" {heading.strip().lower()} "
    for name, keywords in _TABLE_KEYWORDS:
        if any(k in h for k in keywords):
            return name
    # Unknown heading keeps its own text rather than being guessed at or
    # dropped — a mis-keyed table puts HTMT numbers under reliability.
    return heading.strip()[:80] or "untitled"


def _parse_row(line: str) -> dict | None:
    """`| ATT_1 | 0.854 | | |` -> {"label": "ATT_1", "values": [0.854]}."""
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    values = [float(m) for c in cells for m in _COEF_RE.findall(c)]
    if not values:
        return None
    label = next((c for c in cells if c and not _COEF_RE.fullmatch(c)), "")
    return {"label": label, "values": values}


def parse_results_tables(sidecar_text: str) -> dict[str, list[dict]]:
    """Extracted sidecar text -> ONE dict keyed by table. `{}` when unsure.

    Deterministic on purpose: the numbers were already turned into text when
    the file was uploaded, and paying a model to read them a second time buys
    nothing. The hard part is not reading a number, it is knowing which table
    it belongs to — 102 rows spread over outer loadings, CR/AVE, HTMT, VIF and
    R², separated only by the heading above each block.
    """
    if not (sidecar_text or "").strip():
        return {}
    out: dict[str, list[dict]] = {}
    heading = ""
    block: list[dict] = []

    def _flush():
        if block:
            out.setdefault(_canonical_table(heading), []).extend(block)

    for line in sidecar_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            row = _parse_row(stripped)
            if row:
                block.append(row)
            continue
        # A non-table, non-empty line ends the current block and becomes the
        # heading for the next one.
        if stripped:
            _flush()
            block = []
            heading = stripped
    _flush()
    return out
```

Then add the check and wire it into `diagnose`:

```python
def _results_not_in_state(inp: DoctorInput) -> list[Finding]:
    """Numbers on disk that never reached `m4_analysis.results`.

    The highest-value check and the cheapest. Chapter 4 does not need raw
    data — an uploaded SmartPLS/SPSS export IS the analysis — so a project
    holding a parseable results table while `results` is empty is repairable
    with no model call at all.
    """
    if ((inp.context_store or {}).get("m4_analysis") or {}).get("results"):
        return []
    for u in inp.uploads:
        tables = parse_results_tables(u.sidecar_text or "")
        if not tables:
            continue
        n = sum(len(rows) for rows in tables.values())
        return [Finding(
            code="RESULTS_NOT_IN_STATE",
            detail=f"Đã đọc {n} dòng kết quả từ {u.filename} và lưu vào Chương 4.",
            repair="deterministic",
            payload={"results": tables, "filename": u.filename},
        )]
    return []
```

Change `diagnose` to:

```python
def diagnose(inp: DoctorInput) -> list[Finding]:
    """Every problem this project has that the doctor knows how to name."""
    return (_results_not_in_state(inp) + _unread_uploads(inp)
            + _false_done(inp) + _refusal_chapters(inp))
```

- [ ] **Step 5: Run both doctor test files**

Run: `api/.venv/bin/python -m pytest orchestrator/tests/test_doctor.py orchestrator/tests/test_doctor_results_parser.py -v`
Expected: PASS (9 tests)

- [ ] **Step 6: Commit**

```bash
git add orchestrator/doctor.py orchestrator/tests/test_doctor_results_parser.py orchestrator/tests/fixtures/result_docx_sidecar.txt
git commit -m "feat(doctor): parse an extracted results sidecar into a table-keyed dict"
```

---

### Task 3: `BACKFILL_AVAILABLE` finding, replacing the standalone directive

**Files:**
- Modify: `orchestrator/doctor.py`
- Modify: `orchestrator/tests/test_doctor.py`

**Interfaces:**
- Consumes: `orchestrator.backfill.reconstructable_modules`, `orchestrator.state.ContextStore`
- Produces: a `BACKFILL_AVAILABLE` finding with `payload["modules"]` — the list `chat_v3._new_context_backfill_directive` currently computes inline.

- [ ] **Step 1: Write the failing test**

Append to `orchestrator/tests/test_doctor.py`:

```python
def test_reconstructable_modules_become_a_backfill_finding():
    # Project 500319a8: M2 absent, M3 questionnaire-only, M4 thin.
    inp = DoctorInput(
        context_store={
            "m1_topic": {"research_title": "Tác động của tiếp thị người ảnh hưởng",
                         "research_type": "quantitative"},
            "m3_design": {"instrument": {"items": ["q1"]}},
            "m4_analysis": {"analysis_outline": {"research_design": "Định lượng"}},
        },
        uploads=[], chapter_prose={},
    )
    found = [f for f in diagnose(inp) if f.code == "BACKFILL_AVAILABLE"]
    assert found
    assert {"M2", "M3"} <= set(found[0].payload["modules"])
    assert found[0].repair == "directive"


def test_no_backfill_finding_when_nothing_is_reconstructable():
    inp = DoctorInput(context_store={}, uploads=[], chapter_prose={})
    assert not [f for f in diagnose(inp) if f.code == "BACKFILL_AVAILABLE"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `api/.venv/bin/python -m pytest orchestrator/tests/test_doctor.py::test_reconstructable_modules_become_a_backfill_finding -v`
Expected: FAIL — no `BACKFILL_AVAILABLE` finding produced

- [ ] **Step 3: Write the implementation**

Add to `orchestrator/doctor.py` and include it in `diagnose`'s return:

```python
def _backfill_available(inp: DoctorInput) -> list[Finding]:
    """Modules that have evidence to infer from and are not COMPLETE.

    `reconstructable_modules` takes a ContextStore, not the flat dict, so the
    flat store is projected back onto the per-module fields it reads.
    """
    from orchestrator.backfill import reconstructable_modules  # noqa: PLC0415
    from orchestrator.state import ContextStore  # noqa: PLC0415

    cs = inp.context_store or {}
    try:
        store = ContextStore(**{f: cs[f] for f in _MODULE_FIELD.values()
                                if isinstance(cs.get(f), dict)})
        modules = reconstructable_modules(store)
    except Exception:  # noqa: BLE001 — diagnosis must never fail a turn
        return []
    if not modules:
        return []
    return [Finding(
        code="BACKFILL_AVAILABLE",
        detail=f"Có thể dựng lại từ dữ liệu sẵn có: {', '.join(modules)}.",
        repair="directive",
        payload={"modules": modules},
    )]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `api/.venv/bin/python -m pytest orchestrator/tests/test_doctor.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add orchestrator/doctor.py orchestrator/tests/test_doctor.py
git commit -m "feat(doctor): surface reconstructable modules as a finding"
```

---

### Task 4: The `doctor` column and its round-trip

**Files:**
- Create: `api/migrations/versions/20260915_doctor_log.py`
- Modify: `api/app/models.py:464-503` (the `ContextStore` model — add the column beside `coaching`)
- Modify: `api/app/agent_state.py` (`DbProjectStateStore.load` at :285, `load_full_context_store` at :369, `_save` at :385)
- Test: `api/tests/test_doctor_log_roundtrip.py`

**Interfaces:**
- Consumes: nothing from earlier tasks
- Produces: `DbProjectStateStore.load_doctor_log() -> dict` and `save_doctor_log(log: dict) -> None`

- [ ] **Step 1: Write the failing test**

```python
"""The doctor log must survive a round-trip, or it is dead in production.

DbProjectStateStore only round-trips SLICE_OWNERSHIP keys. A new column needs
explicit load/_save support; this has already shipped broken once.
"""
import uuid

from app.agent_state import DbProjectStateStore


def test_doctor_log_round_trips(db_session, tmp_path):
    engine = db_session.bind
    pid = uuid.uuid4()
    _seed_project(db_session, pid)          # see conftest helpers
    store = DbProjectStateStore(engine, pid, tmp_path)

    assert store.load_doctor_log() == {}

    store.save_doctor_log({"RESULTS_NOT_IN_STATE": {
        "gaps_before": ["results is empty"], "gaps_after": [], "exhausted": False}})

    fresh = DbProjectStateStore(engine, pid, tmp_path)
    log = fresh.load_doctor_log()
    assert log["RESULTS_NOT_IN_STATE"]["gaps_before"] == ["results is empty"]
    assert log["RESULTS_NOT_IN_STATE"]["exhausted"] is False


def test_saving_the_log_does_not_disturb_module_slices(db_session, tmp_path):
    engine = db_session.bind
    pid = uuid.uuid4()
    _seed_project(db_session, pid)
    store = DbProjectStateStore(engine, pid, tmp_path)
    store.commit_slice("M1", {"research_title": "T"}, reason="test")

    store.save_doctor_log({"FALSE_DONE": {"exhausted": True}})

    assert DbProjectStateStore(engine, pid, tmp_path) \
        .load_full_context_store()["m1_topic"]["research_title"] == "T"
```

Reuse the existing project-seeding helper from `api/tests/conftest.py`; if none is exported, add `_seed_project` locally by inserting a `Project` row with `owner_id` set to a user created the same way `api/tests/test_chat_v3.py` does it.

- [ ] **Step 2: Run test to verify it fails**

Run: `api/.venv/bin/python -m pytest api/tests/test_doctor_log_roundtrip.py -v`
Expected: FAIL — `AttributeError: 'DbProjectStateStore' object has no attribute 'load_doctor_log'`

- [ ] **Step 3: Write the migration**

```python
"""add doctor repair log to context_store

Revision ID: 20260915_doctorlog01
Revises: 20260915_m5canon01
Create Date: 2026-09-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260915_doctorlog01"
down_revision = "20260915_m5canon01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A sibling of `coaching`, NOT a module slice: slices are the student's
    # work and a diagnostic ledger does not belong inside one.
    op.add_column(
        "context_store",
        sa.Column("doctor", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("context_store", "doctor")
```

- [ ] **Step 4: Add the column to the model**

In `api/app/models.py`, in `class ContextStore`, directly after the `coaching` column:

```python
    # Doctor's repair ledger: {finding_code: {gaps_before, gaps_after, exhausted}}.
    # Beside `coaching` rather than inside a slice — a diagnostic record is not
    # the student's work, and slices are round-tripped by SLICE_OWNERSHIP.
    doctor: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
```

- [ ] **Step 5: Add explicit load/save to the store**

In `api/app/agent_state.py`, on `DbProjectStateStore`:

```python
    def load_doctor_log(self) -> dict:
        """The doctor's repair ledger, or {} when unset.

        Explicit rather than riding the slice round-trip: `_save` only writes
        SLICE_OWNERSHIP keys, so a column left out of these two methods is
        silently dropped on the next commit.
        """
        with Session(self.engine) as s:
            row = s.get(ContextStoreModel, self.project_id)
            return dict(row.doctor or {}) if row is not None else {}

    def save_doctor_log(self, log: dict) -> None:
        with Session(self.engine) as s:
            row = s.get(ContextStoreModel, self.project_id)
            if row is None:
                row = ContextStoreModel(project_id=self.project_id)
                s.add(row)
            row.doctor = dict(log or {})
            s.commit()
```

Match the import name `agent_state.py` already uses for the model (it imports the SQLAlchemy `ContextStore` under an alias to avoid colliding with the Pydantic one — reuse that alias, do not introduce a second).

- [ ] **Step 6: Run the migration and the test**

```bash
cd api && ../api/.venv/bin/alembic upgrade head
cd .. && api/.venv/bin/python -m pytest api/tests/test_doctor_log_roundtrip.py -v
```
Expected: PASS (2 tests)

- [ ] **Step 7: Commit**

```bash
git add api/migrations/versions/20260915_doctor_log.py api/app/models.py api/app/agent_state.py api/tests/test_doctor_log_roundtrip.py
git commit -m "feat(doctor): persist the repair ledger with an explicit round-trip"
```

---

### Task 5: The adapter — gather, repair, guard against loops

**Files:**
- Create: `api/app/doctor_adapter.py`
- Test: `api/tests/test_doctor_adapter.py`

**Interfaces:**
- Consumes: Task 1–3 (`diagnose`, `DoctorInput`, `UploadRecord`), Task 4 (`load_doctor_log`, `save_doctor_log`)
- Produces: `run_doctor(db, project_id, store, workspace) -> DoctorResult` where `DoctorResult` has `.repaired: list[str]` (student-facing one-liners) and `.directive: str | None`

- [ ] **Step 1: Write the failing test**

```python
"""Repairs apply once; a repair that changes nothing is not retried."""
from app.doctor_adapter import apply_findings
from orchestrator.doctor import Finding


class _Store:
    def __init__(self, log=None):
        self.log = dict(log or {})
        self.commits = []

    def load_doctor_log(self):
        return dict(self.log)

    def save_doctor_log(self, log):
        self.log = dict(log)

    def commit_slice(self, module, writes, reason, **kw):
        self.commits.append((module, writes, reason))
        return {"ok": True}


def test_a_deterministic_finding_is_committed_and_reported():
    store = _Store()
    res = apply_findings(store, [Finding(
        code="RESULTS_NOT_IN_STATE",
        detail="Đã đọc 102 dòng kết quả từ _Result.docx và lưu vào Chương 4.",
        repair="deterministic",
        payload={"results": {"outer_loadings": [{"label": "ATT_1", "values": [0.854]}]},
                 "filename": "_Result.docx"},
    )])
    assert store.commits, "results must be committed to M4"
    module, writes, _ = store.commits[0]
    assert module == "M4"
    assert writes["results"]["outer_loadings"][0]["label"] == "ATT_1"
    assert any("102 dòng" in line for line in res.repaired)


def test_a_repair_that_changed_nothing_is_marked_exhausted():
    store = _Store()
    f = Finding(code="FALSE_DONE", detail="M4 thiếu kết quả.",
                repair="deterministic",
                payload={"module": "M4", "gaps": ["results is empty"]})
    apply_findings(store, [f], gaps_after={"M4": ["results is empty"]})
    assert store.log["FALSE_DONE"]["exhausted"] is True


def test_an_exhausted_finding_is_not_retried_and_asks_the_student():
    store = _Store({"FALSE_DONE": {"exhausted": True,
                                   "gaps_before": ["results is empty"]}})
    res = apply_findings(store, [Finding(
        code="FALSE_DONE", detail="M4 thiếu kết quả.", repair="deterministic",
        payload={"module": "M4", "gaps": ["results is empty"]})])
    assert not store.commits, "an exhausted repair must not run again"
    assert res.directive and "results is empty" in res.directive


def test_new_evidence_clears_exhaustion():
    store = _Store({"FALSE_DONE": {"exhausted": True,
                                   "gaps_before": ["results is empty"]}})
    apply_findings(store, [Finding(
        code="FALSE_DONE", detail="M4 thiếu kết quả.", repair="deterministic",
        payload={"module": "M4", "gaps": ["results is empty"]})],
        new_evidence=True)
    assert store.commits, "new evidence must re-open an exhausted repair"


def test_directive_findings_are_never_committed():
    store = _Store()
    res = apply_findings(store, [Finding(
        code="BACKFILL_AVAILABLE", detail="Có thể dựng lại: M2, M3.",
        repair="directive", payload={"modules": ["M2", "M3"]})])
    assert not store.commits
    assert "backfill_upstream_modules" in res.directive
```

- [ ] **Step 2: Run test to verify it fails**

Run: `api/.venv/bin/python -m pytest api/tests/test_doctor_adapter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.doctor_adapter'`

- [ ] **Step 3: Write the implementation**

```python
"""Gather the doctor's input, apply its repairs, render its directive.

The only half that touches I/O. `orchestrator/doctor.py` decides what is
wrong; this decides what to do about it and keeps the ledger that stops a
repair from running forever.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from orchestrator.doctor import DoctorInput, Finding, UploadRecord, diagnose

logger = logging.getLogger(__name__)


@dataclass
class DoctorResult:
    repaired: list[str] = field(default_factory=list)
    directive: str | None = None


# Which module each deterministic repair writes to.
_REPAIR_TARGET = {"RESULTS_NOT_IN_STATE": "M4"}


def apply_findings(store, findings: list[Finding], *,
                   gaps_after: dict[str, list[str]] | None = None,
                   new_evidence: bool = False) -> DoctorResult:
    """Run every repair that is still worth running, and record what happened.

    A repair that runs, changes nothing, and runs again next turn bills
    forever. After each one the ledger records gaps before and after; when
    they match, that code is exhausted and converts to a message for the
    student instead of another attempt. New evidence clears exhaustion —
    the same "new context" signal the backfill directive keys on.
    """
    res = DoctorResult()
    try:
        log = store.load_doctor_log()
    except Exception:  # noqa: BLE001 — the doctor must never fail a turn
        logger.exception("doctor: log unreadable")
        log = {}
    if new_evidence:
        log = {}

    asks: list[str] = []
    directives: list[str] = []

    for f in findings:
        entry = log.get(f.code) or {}
        if entry.get("exhausted"):
            asks.append(f.detail)
            continue
        if f.repair == "directive":
            directives.append(_render_directive(f))
            continue
        if f.repair != "deterministic":
            asks.append(f.detail)
            continue
        try:
            _commit(store, f)
        except Exception:  # noqa: BLE001
            logger.exception("doctor: repair %s failed", f.code)
            continue
        res.repaired.append(f.detail)
        before = list(f.payload.get("gaps") or [])
        after = list((gaps_after or {}).get(f.payload.get("module") or "", before)) \
            if gaps_after is not None else []
        log[f.code] = {"gaps_before": before, "gaps_after": after,
                       "exhausted": bool(before) and before == after}

    try:
        store.save_doctor_log(log)
    except Exception:  # noqa: BLE001
        logger.exception("doctor: log unwritable")

    if asks:
        directives.append(
            "[DOCTOR] Những việc này không tự sửa được, hãy nói thẳng với sinh "
            "viên cần gửi gì: " + " ".join(asks))
    res.directive = "\n".join(directives) or None
    return res


def _commit(store, f: Finding) -> None:
    module = _REPAIR_TARGET.get(f.code) or f.payload.get("module")
    if f.code == "RESULTS_NOT_IN_STATE":
        store.commit_slice(module, {"results": f.payload["results"]},
                           reason=f"doctor: kết quả đọc từ {f.payload['filename']}")
        return
    if f.code == "FALSE_DONE":
        # Clearing the flag is a status change, not a content write.
        store.commit_slice(module, {}, reason="doctor: chưa đủ điều kiện hoàn thành",
                           status_overrides={module: "in_progress"})
        return
    if f.code == "UNREAD_UPLOAD":
        # Nothing to commit — the adapter's caller attaches it to the turn.
        return


def _render_directive(f: Finding) -> str:
    if f.code == "BACKFILL_AVAILABLE":
        mods = ", ".join(f.payload["modules"])
        return (
            f"[BACKFILL AVAILABLE] These modules are incomplete and CAN be "
            f"reconstructed right now from evidence already in this project: "
            f"{mods}.\nA `locked` status on the [PROJECT STATE] line above does "
            f"NOT mean these are off limits.\nCall `backfill_upstream_modules` "
            f"THIS TURN before you write, recompose or export any chapter. Do "
            f"not narrow it to the module the student happens to be asking "
            f"about.\nAfterwards tell them in one line what was filled in."
        )
    if f.code == "REFUSAL_CHAPTER":
        return (
            f"[EMPTY CHAPTER] {f.detail} Recompose it this turn. If it still "
            f"cannot be written, say which chapter and what is missing — never "
            f"write the refusal into the chapter itself."
        )
    return f"[DOCTOR] {f.detail}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `api/.venv/bin/python -m pytest api/tests/test_doctor_adapter.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add api/app/doctor_adapter.py api/tests/test_doctor_adapter.py
git commit -m "feat(doctor): apply repairs with a loop guard and an exhaustion ledger"
```

---

### Task 6: Gather from the database, and wire into the turn

**Files:**
- Modify: `api/app/doctor_adapter.py` (add `gather` and `run_doctor`)
- Modify: `api/app/routers/chat_v3.py` — delete `_new_context_backfill_directive` (added 2026-09-15, now subsumed) and call `run_doctor` at its call site near `:640`
- Modify: `api/tests/test_chat_v3_new_context_backfill.py` → rename to `api/tests/test_doctor_backfill_finding.py`, retargeted at `run_doctor`
- Test: `api/tests/test_doctor_gather.py`

**Interfaces:**
- Consumes: Task 5's `apply_findings`, `DoctorResult`
- Produces: `gather(db, project_id, store, workspace) -> DoctorInput`; `run_doctor(db, project_id, store, workspace, *, new_evidence=False) -> DoctorResult`

- [ ] **Step 1: Write the failing test**

```python
"""`gather` reads uploads, sidecars and chapter prose — no model, no guessing."""
from app.doctor_adapter import gather


def test_gather_marks_an_upload_unattached_when_no_message_references_it(
        db_session, tmp_path, seeded_project):
    pid = seeded_project.id
    (tmp_path / "uploads").mkdir(parents=True, exist_ok=True)
    (tmp_path / "uploads" / "_Result.docx.txt").write_text(
        "Outer loadings\n| ATT_1 | 0.854 |\n", encoding="utf-8")
    _insert_upload(db_session, pid, "_Result.docx")   # no message references it

    inp = gather(db_session, pid, _store_for(pid, tmp_path), tmp_path)

    assert len(inp.uploads) == 1
    assert inp.uploads[0].ever_attached is False
    assert "ATT_1" in inp.uploads[0].sidecar_text


def test_gather_survives_a_missing_sidecar(db_session, tmp_path, seeded_project):
    pid = seeded_project.id
    _insert_upload(db_session, pid, "no_sidecar.pdf")
    inp = gather(db_session, pid, _store_for(pid, tmp_path), tmp_path)
    assert inp.uploads[0].sidecar_text is None
```

Write `_insert_upload` and `_store_for` as local helpers: insert a `PaperUpload` row (`project_id`, `filename`, `s3_uri=""`, `size_bytes=1`, `mime_type="application/octet-stream"`) and build a `DbProjectStateStore(db_session.bind, pid, tmp_path)`. Reuse `seeded_project` if `api/tests/conftest.py` provides it; otherwise create the project the way `api/tests/test_chat_v3.py` does.

- [ ] **Step 2: Run test to verify it fails**

Run: `api/.venv/bin/python -m pytest api/tests/test_doctor_gather.py -v`
Expected: FAIL — `ImportError: cannot import name 'gather'`

- [ ] **Step 3: Implement `gather` and `run_doctor`**

Append to `api/app/doctor_adapter.py`:

```python
def gather(db, project_id, store, workspace) -> DoctorInput:
    """Assemble the doctor's input from Postgres and the workspace mirror."""
    from sqlalchemy import select  # noqa: PLC0415

    from .models import Message, PaperUpload, Thread  # noqa: PLC0415

    attached: set[str] = set()
    for (tcj,) in db.execute(
        select(Message.tool_calls_json)
        .join(Thread, Thread.id == Message.thread_id)
        .where(Thread.project_id == project_id)
    ).all():
        for chip in ((tcj or {}).get("attachments") or []):
            if chip.get("upload_id"):
                attached.add(str(chip["upload_id"]))

    uploads: list[UploadRecord] = []
    for row in db.execute(
        select(PaperUpload).where(PaperUpload.project_id == project_id)
    ).scalars().all():
        sidecar = workspace / "uploads" / f"{row.filename}.txt"
        text = None
        try:
            if sidecar.exists():
                text = sidecar.read_text(encoding="utf-8") or None
        except Exception:  # noqa: BLE001 — an unreadable sidecar is not an error
            logger.warning("doctor: unreadable sidecar %s", sidecar)
        uploads.append(UploadRecord(
            upload_id=str(row.id), filename=row.filename,
            sidecar_text=text, ever_attached=str(row.id) in attached))

    try:
        cs = store.load_full_context_store() or {}
    except Exception:  # noqa: BLE001
        logger.exception("doctor: context store unreadable")
        cs = {}

    from orchestrator.tools.m5_writing import chapter_prose  # noqa: PLC0415
    prose = chapter_prose(cs.get("m5_writing") or {})

    # Per-module slices pass through unflattened — that is the shape the checks
    # want (see DoctorInput).
    return DoctorInput(context_store=cs, uploads=uploads, chapter_prose=prose)


def run_doctor(db, project_id, store, workspace, *,
               new_evidence: bool = False) -> DoctorResult:
    """One diagnosis + repair pass. Never raises."""
    try:
        findings = diagnose(gather(db, project_id, store, workspace))
    except Exception:  # noqa: BLE001 — a doctor that breaks turns is worse than none
        logger.exception("doctor: diagnosis failed")
        return DoctorResult()
    if not findings:
        return DoctorResult()
    return apply_findings(store, findings, new_evidence=new_evidence)
```

- [ ] **Step 4: Wire it into the turn**

In `api/app/routers/chat_v3.py`, delete `_new_context_backfill_directive` entirely and replace its call site inside `_pump_agent` with:

```python
                # One doctor pass per turn: reconcile what this project HAS
                # against what its state SAYS, repair what is deterministic,
                # and hand the agent a directive for what is not. Replaces the
                # standalone backfill directive, which only answered one of the
                # five ways a project goes quietly empty.
                from ..doctor_adapter import run_doctor
                _doc = run_doctor(db, project_id, turn_store,
                                  _workspace_dir(project_id),
                                  new_evidence=bool(attachments))
                _runtime_text = "\n".join(part for part in (
                    EXECUTE_NOW_MARKER if execute_now else None,
                    _doc.directive,
                    chapter_directive,
                    save_directive,
                    text,
                ) if part)
```

`db` is not in scope inside `gen()` — it is the request-scoped session and the generator outlives it. Open a short-lived one instead: `with Session(engine) as _db:` around the `run_doctor` call, matching how `DbProjectStateStore` opens its own sessions.

Surface `_doc.repaired` to the student by prepending each line to the assistant reply in `_finalize`, so a silent repair is still reported.

- [ ] **Step 5: Retarget the superseded test file**

```bash
git mv api/tests/test_chat_v3_new_context_backfill.py api/tests/test_doctor_backfill_finding.py
```

Rewrite its five tests against `orchestrator.doctor.diagnose` + `doctor_adapter._render_directive` rather than the deleted function, keeping every assertion: no-attachment still produces the finding, the directive names M2 and M3, it contradicts `locked`, an unreadable store yields nothing, and a complete project yields nothing.

- [ ] **Step 6: Run the full affected surface**

```bash
api/.venv/bin/python -m pytest orchestrator/tests/test_doctor.py \
  orchestrator/tests/test_doctor_results_parser.py \
  api/tests/test_doctor_adapter.py api/tests/test_doctor_gather.py \
  api/tests/test_doctor_log_roundtrip.py api/tests/test_doctor_backfill_finding.py -v
api/.venv/bin/python -m pytest api/tests -q -k "chat or stream or upload"
```
Expected: all doctor tests PASS; the chat/upload selection stays at its baseline (112 passed as of 2026-09-15).

- [ ] **Step 7: Commit**

```bash
git add api/app/doctor_adapter.py api/app/routers/chat_v3.py api/tests/
git commit -m "feat(doctor): run one diagnosis and repair pass per turn"
```

---

### Task 7: Correct the stale `dod_analysis` comment and pin the no-raw-data rule

**Files:**
- Modify: `orchestrator/artifacts.py:252-305` (`dod_analysis` docstring)
- Test: `orchestrator/tests/test_dod_analysis_results_only.py`

**Interfaces:**
- Consumes: nothing
- Produces: nothing new — a comment fix plus a regression test

- [ ] **Step 1: Write the failing test**

```python
"""Chapter 4 does not require raw data — a results export is enough.

The owner's rule: if the student uploads SmartPLS/SPSS output, there is nothing
to collect and nothing to compute. Results ARE the definition of done.
"""
from orchestrator.artifacts import dod_analysis


def test_results_parsed_from_an_upload_satisfy_the_dod_without_raw_data():
    got = dod_analysis({
        "data_type_detected": "SmartPLS",
        "analysis_outline": {"research_design": "Định lượng, PLS-SEM"},
        # Doctor's parse of uploads/_Result.docx.txt — no raw dataset anywhere.
        "results": {"outer_loadings": [{"label": "ATT_1", "values": [0.854]}],
                    "discriminant_validity": [{"label": "ATT", "values": [0.81]}]},
    })
    assert got.done is True, got.gaps


def test_an_empty_results_dict_is_still_not_done():
    got = dod_analysis({"data_type_detected": "SmartPLS",
                        "analysis_outline": {"research_design": "Định lượng"},
                        "results": {}})
    assert got.done is False
    assert "results is empty" in got.gaps
```

- [ ] **Step 2: Run test to verify the current behaviour**

Run: `api/.venv/bin/python -m pytest orchestrator/tests/test_dod_analysis_results_only.py -v`
Expected: both PASS already — the gate does not require raw data today. If either fails, the gate has a raw-data precondition that must be removed before continuing.

- [ ] **Step 3: Correct the stale ownership claim**

In `orchestrator/artifacts.py`, the `dod_analysis` docstring states that
`data_type_detected` and `results` "are not M4-owned (agent/state.py)". Both
ARE in `SLICE_OWNERSHIP["M4"]` as of 2026-09-15 — verified with
`python -c "from agent.state import SLICE_OWNERSHIP; print(SLICE_OWNERSHIP['M4'])"`.
Replace that clause with the current fact, and note that the doctor writes
`results` through `commit_slice` precisely because it round-trips.

- [ ] **Step 4: Re-run the orchestrator suite**

Run: `api/.venv/bin/python -m pytest orchestrator/tests -q`
Expected: no new failures against the 2026-09-15 baseline (2 known: `test_dod_analysis_still_strict_for_a_mid_flight_engine_run`, `test_dod_analysis_rejects_a_structured_block_with_no_results`; plus `test_module_chapters.py::test_a_merged_closing_chapter_cannot_keep_either_halfs_heading`).

- [ ] **Step 5: Commit**

```bash
git add orchestrator/artifacts.py orchestrator/tests/test_dod_analysis_results_only.py
git commit -m "docs(dod): results IS M4-owned; pin that a results export needs no raw data"
```

---

## Verification against the live project

After Task 6, `500319a8-5a06-47bf-bfd8-3ef921b36184` is the acceptance test. Before:

```
m4_analysis.results = {}     confirmed_at = 2026-09-15T05:33:22
uploads/_Result.docx.txt     102 coefficient rows, on disk since 06:07
```

Send any message on thread `c10f6d13` and expect `m4_analysis.results` to become non-empty with tables keyed by name, one reported line naming `_Result.docx`, and the backfill directive naming M2 and M3.

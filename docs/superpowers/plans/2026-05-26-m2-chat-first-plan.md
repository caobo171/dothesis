> **📜 Historical record — superseded.** This document captured a plan / spec / design at a point in time and is kept for history. It does **not** describe the current system. For the live DoThesis method and architecture see `README.md`, `AGENTS.md`, `docs/ARCHITECTURE.md`, and `docs/PIPELINE.md`.

# M2 Literature Review chat-first Implementation Plan (sub-project 2 of 7)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace M2's generic ModuleAgent clarification loop with a compiled LangGraph sub-graph that walks the 5-phase chat-first conversation from PRD §6.2.3 (Familiarize → Research_State → Gap_Analysis → Reference_Confirm → Output_Gen), plus a project-scoped PDF upload subsystem (DB table + multipart endpoint + sync text extraction).

**Architecture:** Outer graph from sub-project 1 stays unchanged — it still sees one `M2` node. The wrapper invokes a new sub-graph compiled separately, with its own `M2SubGraphState` TypedDict and own `thread_id` namespace (`{outer}::m2`). Each phase is a node that self-loops on user "refine" requests until confirm (capped at 5 iterations). PDF uploads land in a new `paper_uploads` table; pdfminer extracts text synchronously on upload; M2 phases read URIs via the wrapper's `_seed_from_outer`.

**Tech Stack:** Python 3.10+, LangGraph 1.2+, LangChain 1.3+, FastAPI multipart, SQLAlchemy 2.0, Alembic, pdfminer.six, boto3 (existing S3 client), moto[s3] for tests, pytest.

**Spec:** `docs/superpowers/specs/2026-05-26-m2-chat-first-design.md`
**Roadmap entry:** `docs/superpowers/2026-05-26-platform-pivot-roadmap.md` (sub-project 2)
**Depends on:** Sub-project 1 (orchestration foundation) — shipped at master `5e598a4`.

---

## File map

### NEW files

```
api/
├── migrations/versions/
│   └── 20260527_add_paper_uploads.py
├── app/routers/
│   └── uploads.py                                    # POST/GET/DELETE endpoints
└── tests/
    └── test_uploads_router.py

orchestrator/
├── agents/m2/                                        # NEW package; replaces m2_literature.py
│   ├── __init__.py                                   # re-exports M2Agent
│   ├── agent.py                                      # M2Agent wrapper (ModuleAgent subclass)
│   ├── graph.py                                      # build_m2_subgraph(), get_m2_graph()
│   ├── state.py                                      # M2SubGraphState
│   ├── intent.py                                     # shared classifier (extracted)
│   └── phases/
│       ├── __init__.py
│       ├── phase1_familiarize.py
│       ├── phase2_research_state.py                  # heaviest — regen loop
│       ├── phase3_gap_analysis.py
│       ├── phase4_reference_confirm.py               # cursor walk + auto-verify
│       └── phase5_output_gen.py
├── prompts/m2/                                       # NEW directory; replaces m2.md
│   ├── _style.md                                     # shared tone/voice guide
│   ├── 1_familiarize.md
│   ├── 2_research_state.md
│   ├── 3_gap_analysis.md
│   ├── 4_reference_confirm.md
│   └── 5_output_gen.md
└── tests/
    ├── agents/m2/
    │   ├── __init__.py
    │   ├── test_intent_classifier.py
    │   ├── test_state_translation.py
    │   ├── test_phase1_familiarize.py
    │   ├── test_phase2_research_state.py
    │   ├── test_phase3_gap_analysis.py
    │   ├── test_phase4_reference_confirm.py
    │   ├── test_phase5_output_gen.py
    │   ├── test_m2_subgraph.py                       # full sub-graph e2e
    │   └── test_m2_agent_wrapper.py
    ├── test_seed_with_paper_uris.py                  # wrapper queries paper_uploads
    └── integration/
        ├── test_m2_e2e_upload.py                     # upload → M2 auto-mode → ch2 draft
        └── test_m2_bilingual.py                      # language=vi smoke
```

### DELETED files

- `orchestrator/agents/m2_literature.py`               (responsibility moves to `orchestrator/agents/m2/agent.py`)
- `orchestrator/prompts/m2.md`                         (replaced by `orchestrator/prompts/m2/`)
- `orchestrator/tests/test_agents_m2.py`               (deleted; replaced by `orchestrator/tests/agents/m2/test_m2_agent_wrapper.py`. The old file's single test is reproduced in the new file's wrapper test.)

### MODIFIED files

- `api/app/models.py`                                  add `PaperUpload`
- `api/app/main.py`                                    mount `uploads_router` (same flag as chat router)
- `api/pyproject.toml`                                 add `pdfminer.six>=20231228` if not already present
- `orchestrator/pyproject.toml`                        add `"orchestrator.agents.m2"`, `"orchestrator.agents.m2.phases"` to `packages` list
- `orchestrator/graph.py`                              change import `from orchestrator.agents.m2_literature import M2Agent` → `from orchestrator.agents.m2 import M2Agent`

---

## Task index (24 tasks)

| Phase | Tasks |
|---|---|
| A. Upload subsystem | 1. Migration · 2. Model · 3. PDF extraction helper · 4. Uploads router · 5. Mount + wire |
| B. Sub-graph foundation | 6. M2SubGraphState · 7. Intent classifier extraction · 8. State translation · 9. Sub-graph scaffold |
| C. Phase nodes | 10. Phase 1 (Familiarize) · 11. Phase 2 (Research_State) · 12. Phase 3 (Gap_Analysis) · 13. Phase 4 (Reference_Confirm) · 14. Phase 5 (Output_Gen) |
| D. Wire-up + sub-graph | 15. Sub-graph edges + conditional routing · 16. M2Agent wrapper · 17. orchestrator/graph.py import swap + delete old files |
| E. Integration tests | 18. Sub-graph auto e2e · 19. Sub-graph interactive with regen · 20. Regen cap · 21. Navigate back · 22. Upload + M2 e2e · 23. Bilingual smoke · 24. Regression: sub-project 1 tests still pass |

Tasks within a phase can be ordered freely except where noted. Each task is a single TDD cycle (failing test → impl → passing test → commit).

---

## Phase A — PDF upload subsystem

### Task 1: Alembic migration for paper_uploads

**Files:**
- Create: `api/migrations/versions/20260527_add_paper_uploads.py`
- Test: `orchestrator/tests/test_paper_uploads_migration.py`

- [ ] **Step 1: Get the current alembic head**

Run: `cd api && source .venv/bin/activate && alembic heads`
Expected: `20260526_orch01 (head)` (from sub-project 1). Note this id.

- [ ] **Step 2: Write the migration test**

Create `orchestrator/tests/test_paper_uploads_migration.py`:

```python
"""Verifies the paper_uploads migration creates the right table."""
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def alembic_env(pg_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    monkeypatch.chdir(REPO_ROOT / "api")
    return pg_url


def _alembic(args):
    subprocess.run(["alembic", *args], check=True)


def test_paper_uploads_migration_up_down_up(alembic_env):
    _alembic(["downgrade", "base"])
    _alembic(["upgrade", "head"])
    eng = create_engine(alembic_env)
    insp = inspect(eng)
    assert "paper_uploads" in insp.get_table_names()
    cols = {c["name"] for c in insp.get_columns("paper_uploads")}
    for c in ("id", "project_id", "filename", "s3_uri", "size_bytes",
              "mime_type", "text_extracted_at", "text_extract_uri",
              "page_count", "uploaded_at"):
        assert c in cols, f"missing column {c}"

    _alembic(["downgrade", "-1"])
    insp = inspect(eng)
    assert "paper_uploads" not in insp.get_table_names()

    _alembic(["upgrade", "head"])
```

- [ ] **Step 3: Run — should fail (migration doesn't exist)**

Run: `cd /Users/caonguyenvan/project/dothesis && source api/.venv/bin/activate && python -m pytest orchestrator/tests/test_paper_uploads_migration.py -v`
Expected: FAIL — alembic error about unknown revision.

- [ ] **Step 4: Write the migration**

Create `api/migrations/versions/20260527_add_paper_uploads.py`:

```python
"""add paper_uploads table

Revision ID: 20260527_uploads01
Revises: 20260526_orch01
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "20260527_uploads01"
down_revision = "20260526_orch01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "paper_uploads",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("filename", sa.Text, nullable=False),
        sa.Column("s3_uri", sa.Text, nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("mime_type", sa.String(64), nullable=False),
        sa.Column("text_extracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("text_extract_uri", sa.Text, nullable=True),
        sa.Column("page_count", sa.Integer, nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("paper_uploads")
```

- [ ] **Step 5: Run test — should pass**

Run: `cd /Users/caonguyenvan/project/dothesis && source api/.venv/bin/activate && python -m pytest orchestrator/tests/test_paper_uploads_migration.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/caonguyenvan/project/dothesis
git add api/migrations/versions/20260527_add_paper_uploads.py \
        orchestrator/tests/test_paper_uploads_migration.py
git commit -m "feat(api): alembic migration for paper_uploads table"
```

---

### Task 2: PaperUpload SQLAlchemy model

**Files:**
- Modify: `api/app/models.py`
- Test: `api/tests/test_models.py` (append)

- [ ] **Step 1: Append the test**

Append to `api/tests/test_models.py`:

```python
def test_paper_upload_roundtrip():
    from app.models import PaperUpload
    with OrmSession(get_engine()) as db:
        u = _make_user(db)
        p = Project(user_id=u.id, name="X", language="en", citation_style="apa")
        db.add(p); db.flush()
        up = PaperUpload(
            project_id=p.id, filename="paper.pdf",
            s3_uri="s3://bucket/key.pdf",
            size_bytes=12345, mime_type="application/pdf",
        )
        db.add(up); db.commit()

        got = db.scalar(select(PaperUpload).where(PaperUpload.project_id == p.id))
        assert got.filename == "paper.pdf"
        assert got.text_extracted_at is None  # null until extraction succeeds
        assert got.uploaded_at is not None
```

- [ ] **Step 2: Run — should fail (PaperUpload not imported)**

Run: `cd /Users/caonguyenvan/project/dothesis/api && source .venv/bin/activate && python -m pytest tests/test_models.py::test_paper_upload_roundtrip -v`
Expected: FAIL — ImportError.

- [ ] **Step 3: Add the model**

Append to `api/app/models.py`:

```python
class PaperUpload(Base):
    __tablename__ = "paper_uploads"

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    s3_uri: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    text_extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    text_extract_uri: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 4: Run — should pass**

Run: `cd /Users/caonguyenvan/project/dothesis/api && source .venv/bin/activate && python -m pytest tests/test_models.py::test_paper_upload_roundtrip -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/app/models.py api/tests/test_models.py
git commit -m "feat(api): PaperUpload SQLAlchemy model"
```

---

### Task 3: PDF text extraction helper

**Files:**
- Create: `api/app/pdf_extract.py`
- Create: `api/tests/test_pdf_extract.py`
- Create: `api/tests/fixtures/sample.pdf` (small 1-page PDF with extractable text)
- Modify: `api/pyproject.toml` (add `pdfminer.six` if not present)

- [ ] **Step 1: Confirm pdfminer.six availability**

Run: `cd /Users/caonguyenvan/project/dothesis && source api/.venv/bin/activate && python -c "import pdfminer.high_level; print(pdfminer.__version__)"`

If it errors with ImportError, add `pdfminer.six>=20231228` to `api/pyproject.toml`'s `dependencies` list and run `pip install -e api[dev]`.
Expected: prints a version string.

- [ ] **Step 2: Generate a tiny PDF fixture**

Run from repo root:
```bash
source api/.venv/bin/activate
python -c "
from reportlab.pdfgen import canvas
c = canvas.Canvas('api/tests/fixtures/sample.pdf')
c.drawString(100, 750, 'Smith and Doe (2024) studied transformational leadership.')
c.drawString(100, 720, 'See page 42 for the key finding.')
c.showPage()
c.save()
print('wrote sample.pdf')
"
```
If `reportlab` isn't installed, install it first: `pip install reportlab`.
Expected: writes a small PDF (~1KB).

- [ ] **Step 3: Write the test**

Create `api/tests/test_pdf_extract.py`:

```python
"""Tests for PDF text extraction."""
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "sample.pdf"


def test_extract_pdf_text_returns_known_string():
    from app.pdf_extract import extract_pdf_text
    text, page_count = extract_pdf_text(FIXTURE.read_bytes())
    assert "transformational leadership" in text.lower()
    assert page_count == 1


def test_extract_pdf_text_empty_bytes_returns_empty():
    from app.pdf_extract import extract_pdf_text
    text, page_count = extract_pdf_text(b"")
    assert text == ""
    assert page_count == 0


def test_extract_pdf_text_invalid_bytes_returns_empty():
    from app.pdf_extract import extract_pdf_text
    text, page_count = extract_pdf_text(b"not a pdf")
    assert text == ""
    assert page_count == 0
```

- [ ] **Step 4: Run — should fail (module missing)**

Run: `cd /Users/caonguyenvan/project/dothesis/api && source .venv/bin/activate && python -m pytest tests/test_pdf_extract.py -v`
Expected: FAIL — ImportError.

- [ ] **Step 5: Implement extractor**

Create `api/app/pdf_extract.py`:

```python
"""PDF text extraction — sync, no OCR.

Used by the uploads router on POST to cache extracted text alongside the
binary in S3, and by M2 Phase 4 to verify page-reference claims.
"""
from __future__ import annotations

import io
import logging
from typing import Tuple

logger = logging.getLogger(__name__)


def extract_pdf_text(pdf_bytes: bytes) -> Tuple[str, int]:
    """Extract plain text and page count from a PDF byte string.

    Returns ('', 0) for empty input, invalid PDFs, or extraction failure
    (e.g., image-only scans). Callers should treat both empty results as
    "no usable text" and surface a warning rather than treating it as an
    error — image-only PDFs are valid input but yield no text.
    """
    if not pdf_bytes:
        return ("", 0)
    try:
        from pdfminer.high_level import extract_text
        from pdfminer.pdfpage import PDFPage
    except ImportError:
        logger.exception("pdfminer.six not installed")
        return ("", 0)

    try:
        text = extract_text(io.BytesIO(pdf_bytes))
        # PDFPage.get_pages is the lightest way to count pages without re-extraction.
        page_count = sum(1 for _ in PDFPage.get_pages(io.BytesIO(pdf_bytes)))
        return (text or "", page_count)
    except Exception as e:
        logger.warning("pdfminer extract failed: %s", e)
        return ("", 0)
```

- [ ] **Step 6: Run — should pass**

Run: `cd /Users/caonguyenvan/project/dothesis/api && source .venv/bin/activate && python -m pytest tests/test_pdf_extract.py -v`
Expected: 3 PASS.

- [ ] **Step 7: Commit**

```bash
cd /Users/caonguyenvan/project/dothesis
git add api/app/pdf_extract.py api/tests/test_pdf_extract.py api/tests/fixtures/sample.pdf
# Only add api/pyproject.toml if you actually modified it in Step 1
git diff --quiet api/pyproject.toml || git add api/pyproject.toml
git commit -m "feat(api): sync PDF text extraction helper (pdfminer.six)"
```

---

### Task 4: Uploads router (POST/GET/DELETE + GET text)

**Files:**
- Create: `api/app/routers/uploads.py`
- Create: `api/tests/test_uploads_router.py`

- [ ] **Step 1: Write tests**

Create `api/tests/test_uploads_router.py`:

```python
"""Tests for /api/v1/projects/{pid}/uploads + /api/v1/uploads/{id}."""
import io
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import PaperUpload, Project, User
from app.security import create_session

FIXTURE = Path(__file__).parent / "fixtures" / "sample.pdf"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "true")
    return TestClient(create_app())


def _login(client) -> uuid.UUID:
    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"u{uuid.uuid4().hex[:6]}@x",
                 username=f"u{uuid.uuid4().hex[:6]}",
                 password_hash="x", email_verified=True)
        db.add(u); db.commit()
        client.cookies.set("dothesis_session", create_session(db, u))
        return u.id


def _project(client) -> uuid.UUID:
    return uuid.UUID(client.post("/api/v1/projects", json={"name": "T"}).json()["id"])


def test_upload_pdf_returns_id_and_extracted_text(client, monkeypatch):
    # Mock the S3 client so tests stay offline.
    fake_s3 = MagicMock()
    monkeypatch.setattr("app.routers.uploads.s3_from_env", lambda: fake_s3)

    _login(client)
    pid = _project(client)

    with FIXTURE.open("rb") as f:
        r = client.post(
            f"/api/v1/projects/{pid}/uploads",
            files={"file": ("sample.pdf", f, "application/pdf")},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "upload_id" in body
    assert body["filename"] == "sample.pdf"
    assert body["size_bytes"] > 0
    assert body["page_count"] == 1

    # S3 was called twice — once for original, once for extracted text
    assert fake_s3.put_object.call_count == 2

    # DB row exists with text_extracted_at set
    sf = get_session_factory()
    with sf() as db:
        row = db.query(PaperUpload).filter_by(project_id=pid).one()
        assert row.text_extracted_at is not None
        assert row.page_count == 1


def test_upload_rejects_oversized_file(client, monkeypatch):
    monkeypatch.setattr("app.routers.uploads.s3_from_env", lambda: MagicMock())
    monkeypatch.setenv("M2_UPLOAD_MAX_BYTES", "100")  # 100 bytes cap

    _login(client)
    pid = _project(client)

    # 200-byte payload
    payload = b"x" * 200
    r = client.post(
        f"/api/v1/projects/{pid}/uploads",
        files={"file": ("big.pdf", io.BytesIO(payload), "application/pdf")},
    )
    assert r.status_code == 413


def test_upload_rejects_disallowed_mime_type(client, monkeypatch):
    monkeypatch.setattr("app.routers.uploads.s3_from_env", lambda: MagicMock())

    _login(client)
    pid = _project(client)

    r = client.post(
        f"/api/v1/projects/{pid}/uploads",
        files={"file": ("data.bin", io.BytesIO(b"x"), "application/octet-stream")},
    )
    assert r.status_code == 415


def test_list_uploads_returns_project_scoped(client, monkeypatch):
    monkeypatch.setattr("app.routers.uploads.s3_from_env", lambda: MagicMock())
    _login(client)
    pid = _project(client)
    with FIXTURE.open("rb") as f:
        client.post(f"/api/v1/projects/{pid}/uploads",
                    files={"file": ("a.pdf", f, "application/pdf")})

    r = client.get(f"/api/v1/projects/{pid}/uploads")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["filename"] == "a.pdf"


def test_delete_upload_removes_row(client, monkeypatch):
    monkeypatch.setattr("app.routers.uploads.s3_from_env", lambda: MagicMock())
    _login(client)
    pid = _project(client)
    with FIXTURE.open("rb") as f:
        upload_id = client.post(
            f"/api/v1/projects/{pid}/uploads",
            files={"file": ("a.pdf", f, "application/pdf")},
        ).json()["upload_id"]

    r = client.delete(f"/api/v1/uploads/{upload_id}")
    assert r.status_code == 204

    sf = get_session_factory()
    with sf() as db:
        assert db.query(PaperUpload).filter_by(id=uuid.UUID(upload_id)).count() == 0


def test_get_upload_text_returns_extracted_body(client, monkeypatch):
    fake_s3 = MagicMock()
    fake_s3.get_object.return_value = {"Body": io.BytesIO(b"extracted text body")}
    monkeypatch.setattr("app.routers.uploads.s3_from_env", lambda: fake_s3)
    _login(client)
    pid = _project(client)
    with FIXTURE.open("rb") as f:
        upload_id = client.post(
            f"/api/v1/projects/{pid}/uploads",
            files={"file": ("a.pdf", f, "application/pdf")},
        ).json()["upload_id"]

    r = client.get(f"/api/v1/uploads/{upload_id}/text")
    assert r.status_code == 200
    assert "extracted" in r.text


def test_upload_with_no_extractable_text_leaves_text_extracted_at_null(client, monkeypatch):
    monkeypatch.setattr("app.routers.uploads.s3_from_env", lambda: MagicMock())
    monkeypatch.setattr("app.routers.uploads.extract_pdf_text", lambda b: ("", 0))

    _login(client)
    pid = _project(client)
    with FIXTURE.open("rb") as f:
        r = client.post(
            f"/api/v1/projects/{pid}/uploads",
            files={"file": ("a.pdf", f, "application/pdf")},
        )
    assert r.status_code == 200

    sf = get_session_factory()
    with sf() as db:
        row = db.query(PaperUpload).filter_by(project_id=pid).one()
        assert row.text_extracted_at is None
        assert row.text_extract_uri is None
```

- [ ] **Step 2: Run — should fail (router not yet mounted, plus module missing)**

Run: `cd /Users/caonguyenvan/project/dothesis/api && source .venv/bin/activate && python -m pytest tests/test_uploads_router.py -v`
Expected: FAIL — ImportError or 404.

- [ ] **Step 3: Implement the router**

Create `api/app/routers/uploads.py`:

```python
"""PDF/text upload endpoints for M2 Literature Review (sub-project 2).

Uploads are project-scoped (shared across all threads of a project). On POST,
the file is stored in S3 and text is synchronously extracted via pdfminer.six
and cached to a sibling S3 object. M2 sub-graph's Phase 1 reads the list via
the orchestrator wrapper.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import db_session
from ..deps import current_user
from ..models import PaperUpload, Project, User
from ..pdf_extract import extract_pdf_text

router = APIRouter(tags=["uploads"])

_ALLOWED_MIME = {"application/pdf", "text/plain"}
_DEFAULT_MAX_BYTES = 50 * 1024 * 1024  # 50 MB


def _max_bytes() -> int:
    return int(os.getenv("M2_UPLOAD_MAX_BYTES", str(_DEFAULT_MAX_BYTES)))


def s3_from_env():
    """Indirection so tests can monkeypatch easily."""
    from engine.s3_for_jobs import s3_from_env as _real
    return _real()


def _owned_project(db: Session, user: User, project_id: uuid.UUID) -> Project:
    p = db.get(Project, project_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status_code=404,
                            detail={"error": {"code": "not_found", "message": "project not found"}})
    return p


def _owned_upload(db: Session, user: User, upload_id: uuid.UUID) -> PaperUpload:
    up = db.get(PaperUpload, upload_id)
    if not up:
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    _owned_project(db, user, up.project_id)
    return up


class UploadOut(BaseModel):
    upload_id: uuid.UUID
    filename: str
    size_bytes: int
    mime_type: str
    page_count: int | None
    uploaded_at: Any


class UploadListItem(BaseModel):
    id: uuid.UUID
    filename: str
    size_bytes: int
    mime_type: str
    page_count: int | None
    uploaded_at: Any


@router.post("/projects/{project_id}/uploads", response_model=UploadOut)
async def upload_paper(project_id: uuid.UUID,
                       file: UploadFile = File(...),
                       user: User = Depends(current_user),
                       db: Session = Depends(db_session)):
    """Accept a PDF or text file, store in S3, extract text synchronously."""
    p = _owned_project(db, user, project_id)

    # Validate mime type
    mime = file.content_type or "application/octet-stream"
    if mime not in _ALLOWED_MIME:
        raise HTTPException(status_code=415,
                            detail={"error": {"code": "bad_mime",
                                              "message": f"unsupported content type: {mime}"}})

    # Read body, validate size
    body = await file.read()
    if len(body) > _max_bytes():
        raise HTTPException(status_code=413,
                            detail={"error": {"code": "too_large",
                                              "message": f"file exceeds {_max_bytes()} bytes"}})

    upload_id = uuid.uuid4()
    bucket = os.environ.get("S3_BUCKET")
    s3_uri = f"s3://{bucket}/users/{p.user_id}/projects/{project_id}/uploads/{upload_id}/{file.filename}"

    s3 = s3_from_env()
    # Upload original
    s3.put_object(
        Bucket=bucket,
        Key=f"users/{p.user_id}/projects/{project_id}/uploads/{upload_id}/{file.filename}",
        Body=body,
        ContentType=mime,
    )

    # Synchronous extraction
    text = ""
    page_count = 0
    text_uri = None
    text_extracted_at = None
    if mime == "application/pdf":
        text, page_count = extract_pdf_text(body)
    else:  # text/plain
        try:
            text = body.decode("utf-8", errors="ignore")
            page_count = 1
        except Exception:
            text = ""

    if text:
        # Cache extracted text alongside
        text_key = f"users/{p.user_id}/projects/{project_id}/uploads/{upload_id}/extracted.txt"
        s3.put_object(Bucket=bucket, Key=text_key, Body=text.encode("utf-8"),
                      ContentType="text/plain")
        text_uri = f"s3://{bucket}/{text_key}"
        text_extracted_at = datetime.now(timezone.utc)

    row = PaperUpload(
        id=upload_id,
        project_id=project_id,
        filename=file.filename or "untitled",
        s3_uri=s3_uri,
        size_bytes=len(body),
        mime_type=mime,
        text_extracted_at=text_extracted_at,
        text_extract_uri=text_uri,
        page_count=page_count or None,
    )
    db.add(row); db.commit(); db.refresh(row)

    return UploadOut(
        upload_id=row.id, filename=row.filename, size_bytes=row.size_bytes,
        mime_type=row.mime_type, page_count=row.page_count,
        uploaded_at=row.uploaded_at,
    )


@router.get("/projects/{project_id}/uploads", response_model=list[UploadListItem])
def list_uploads(project_id: uuid.UUID,
                 user: User = Depends(current_user),
                 db: Session = Depends(db_session)):
    _owned_project(db, user, project_id)
    return db.query(PaperUpload).filter_by(project_id=project_id) \
             .order_by(PaperUpload.uploaded_at.desc()).all()


@router.delete("/uploads/{upload_id}", status_code=204)
def delete_upload(upload_id: uuid.UUID,
                  user: User = Depends(current_user),
                  db: Session = Depends(db_session)):
    up = _owned_upload(db, user, upload_id)
    db.delete(up); db.commit()
    return None


@router.get("/uploads/{upload_id}/text", response_class=PlainTextResponse)
def get_upload_text(upload_id: uuid.UUID,
                    user: User = Depends(current_user),
                    db: Session = Depends(db_session)):
    """Returns the cached extracted text. Mostly for debugging."""
    up = _owned_upload(db, user, upload_id)
    if not up.text_extract_uri:
        raise HTTPException(404, detail={"error": {"code": "no_text",
                                                    "message": "no extracted text for this upload"}})
    bucket = os.environ.get("S3_BUCKET")
    key = up.text_extract_uri.replace(f"s3://{bucket}/", "")
    s3 = s3_from_env()
    obj = s3.get_object(Bucket=bucket, Key=key)
    return obj["Body"].read().decode("utf-8", errors="ignore")
```

- [ ] **Step 4: Tests still fail until Task 5 mounts the router. Verify the file imports cleanly:**

Run: `python -c "from api.app.routers import uploads; print('ok')"`
Expected: `ok`.

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/uploads.py api/tests/test_uploads_router.py
git commit -m "feat(api): uploads router with sync PDF extraction (mounting in Task 5)"
```

---

### Task 5: Mount uploads router + wire feature flag

**Files:**
- Modify: `api/app/main.py`

- [ ] **Step 1: Run the uploads tests — they should fail (router not mounted)**

Run: `cd /Users/caonguyenvan/project/dothesis/api && source .venv/bin/activate && python -m pytest tests/test_uploads_router.py -v 2>&1 | tail -3`
Expected: most tests fail with 404 status.

- [ ] **Step 2: Mount the router**

Edit `api/app/main.py` — find the existing `if settings.orchestrator_enabled:` block and add the uploads router:

```python
    if settings.orchestrator_enabled:
        from .routers import chat as chat_router
        from .routers import runs as runs_router
        from .routers import uploads as uploads_router
        app.include_router(chat_router.router, prefix="/api/v1")
        app.include_router(runs_router.router, prefix="/api/v1")
        app.include_router(uploads_router.router, prefix="/api/v1")
```

- [ ] **Step 3: Run the uploads tests — should pass**

Run: `cd /Users/caonguyenvan/project/dothesis/api && source .venv/bin/activate && python -m pytest tests/test_uploads_router.py -v`
Expected: 7 PASS.

- [ ] **Step 4: Commit**

```bash
cd /Users/caonguyenvan/project/dothesis
git add api/app/main.py
git commit -m "feat(api): mount uploads router under ORCHESTRATOR_ENABLED flag"
```

---

## Phase B — Sub-graph foundation

### Task 6: M2SubGraphState

**Files:**
- Create: `orchestrator/agents/m2/__init__.py`
- Create: `orchestrator/agents/m2/state.py`
- Create: `orchestrator/tests/agents/__init__.py`
- Create: `orchestrator/tests/agents/m2/__init__.py`
- Create: `orchestrator/tests/agents/m2/test_state.py`

- [ ] **Step 1: Write the test**

Create `orchestrator/tests/agents/m2/test_state.py`:

```python
"""Tests for M2SubGraphState shape and helpers."""
from langchain_core.messages import HumanMessage
from orchestrator.agents.m2.state import M2SubGraphState, fresh_state


def test_fresh_state_has_defaults():
    s = fresh_state(
        project_id="00000000-0000-0000-0000-000000000001",
        thread_id="00000000-0000-0000-0000-000000000002",
        research_title="X",
        research_type="quantitative",
        language="en",
        paper_uris=["s3://b/k.pdf"],
        mode="interactive",
    )
    assert s["current_phase"] == "familiarize"
    assert s["regeneration_count"] == {}
    assert s["paper_uris"] == ["s3://b/k.pdf"]
    assert s["has_uploaded_papers"] is None
    assert s["research_state_confirmed"] is False
    assert s["page_check_cursor"] == 0


def test_fresh_state_empty_paper_uris():
    s = fresh_state(
        project_id="x", thread_id="y", research_title="T",
        research_type="qualitative", language="vi",
        paper_uris=[], mode="auto",
    )
    assert s["paper_uris"] == []
    assert s["language"] == "vi"
```

- [ ] **Step 2: Run — should fail**

Run: `cd /Users/caonguyenvan/project/dothesis && source api/.venv/bin/activate && python -m pytest orchestrator/tests/agents/m2/test_state.py -v`
Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 3: Implement state**

Create `orchestrator/agents/m2/__init__.py`:

```python
"""M2 Literature Review chat-first sub-graph."""
```

Create `orchestrator/agents/m2/state.py`:

```python
"""M2 sub-graph state — kept separate from outer OrchestratorState.

Sub-graph reads outer state on entry via _seed_from_outer (in agent.py) and
writes back to context_store.m2_literature on exit via _flatten_to_m2_output.
The state below is in-memory only; LangGraph PostgresSaver checkpoints it
under thread_id "{outer}::m2".
"""
from __future__ import annotations

from typing import Annotated, Literal, TypedDict
from uuid import UUID

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


PhaseKey = Literal[
    "familiarize", "research_state", "gap_analysis",
    "reference_confirm", "output_gen", "DONE",
]


class M2SubGraphState(TypedDict, total=False):
    # --- Inputs from outer state (set on entry) ---
    project_id: UUID | str
    thread_id: UUID | str
    research_title: str
    research_type: Literal["quantitative", "qualitative", "mixed"]
    language: Literal["vi", "en", "bilingual"]
    paper_uris: list[str]
    messages: Annotated[list[BaseMessage], add_messages]
    mode: Literal["interactive", "auto"]

    # --- Phase pointer ---
    current_phase: PhaseKey
    regeneration_count: dict[str, int]

    # --- Phase 1: Familiarize ---
    has_uploaded_papers: bool | None

    # --- Phase 2: Research_State ---
    research_state_draft: str | None
    research_state_refinements: list[str]
    research_state_confirmed: bool
    research_state_citations: list[dict]

    # --- Phase 3: Gap_Analysis ---
    candidate_gaps: list[dict] | None
    gap_refinements: list[str]
    selected_gap_ids: list[str] | None

    # --- Phase 4: Reference_Confirm ---
    pending_page_checks: list[dict]
    verified_refs: list[dict]
    page_check_cursor: int

    # --- Phase 5: Output_Gen ---
    ch2_draft: str | None
    citation_list: list[dict]


def fresh_state(
    *,
    project_id, thread_id, research_title: str, research_type: str,
    language: str, paper_uris: list[str], mode: str,
) -> M2SubGraphState:
    """Seed a brand-new sub-graph state for an entry into M2."""
    return {
        "project_id": project_id, "thread_id": thread_id,
        "research_title": research_title, "research_type": research_type,
        "language": language, "paper_uris": list(paper_uris),
        "messages": [], "mode": mode,
        "current_phase": "familiarize",
        "regeneration_count": {},
        "has_uploaded_papers": None,
        "research_state_draft": None,
        "research_state_refinements": [],
        "research_state_confirmed": False,
        "research_state_citations": [],
        "candidate_gaps": None,
        "gap_refinements": [],
        "selected_gap_ids": None,
        "pending_page_checks": [],
        "verified_refs": [],
        "page_check_cursor": 0,
        "ch2_draft": None,
        "citation_list": [],
    }
```

Also create empty `__init__.py` files: `orchestrator/tests/agents/__init__.py`, `orchestrator/tests/agents/m2/__init__.py`.

- [ ] **Step 4: Run — should pass**

Run: `cd /Users/caonguyenvan/project/dothesis && source api/.venv/bin/activate && python -m pytest orchestrator/tests/agents/m2/test_state.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/agents/m2/__init__.py orchestrator/agents/m2/state.py \
        orchestrator/tests/agents/__init__.py \
        orchestrator/tests/agents/m2/__init__.py \
        orchestrator/tests/agents/m2/test_state.py
git commit -m "feat(orchestrator): M2SubGraphState + fresh_state seeder"
```

---

### Task 7: Intent classifier extraction

**Files:**
- Create: `orchestrator/agents/m2/intent.py`
- Create: `orchestrator/tests/agents/m2/test_intent_classifier.py`

The classifier is M2-specific (it knows about phases like "research_state", "gap_analysis"). Future M3-M5 sub-projects will reuse the *shape* (Pydantic schema + structured-output LLM) but the labels/keywords are M2's. We don't try to make it fully generic.

- [ ] **Step 1: Write tests**

Create `orchestrator/tests/agents/m2/test_intent_classifier.py`:

```python
"""Tests for M2's per-phase intent classifier."""
from unittest.mock import MagicMock

import pytest
from orchestrator.agents.m2.intent import (
    PhaseIntent, classify_phase_intent,
)


def test_classify_confirm_via_rule(monkeypatch):
    intent = classify_phase_intent(
        last_user_message="ok looks good",
        current_phase="research_state",
        mode="interactive",
    )
    assert intent.action == "confirm"


def test_classify_refine_via_rule(monkeypatch):
    intent = classify_phase_intent(
        last_user_message="redo focusing on Self-Determination Theory",
        current_phase="research_state",
        mode="interactive",
    )
    assert intent.action == "refine"
    assert "Self-Determination" in intent.refinement_text


def test_classify_navigate_back(monkeypatch):
    intent = classify_phase_intent(
        last_user_message="go back to research state",
        current_phase="gap_analysis",
        mode="interactive",
    )
    assert intent.action == "navigate"
    assert intent.target_phase == "research_state"


def test_classify_auto_mode_always_advances():
    """Auto mode never asks the classifier — always returns confirm."""
    intent = classify_phase_intent(
        last_user_message="anything",
        current_phase="research_state",
        mode="auto",
    )
    assert intent.action == "confirm"


def test_classify_ambiguous_falls_back_to_llm(monkeypatch):
    """When rules don't fire, falls back to LLM. Stub the LLM to return refine."""
    fake = MagicMock()
    fake.with_structured_output.return_value.invoke.return_value = PhaseIntent(
        action="refine", refinement_text="add SDT", target_phase=None,
    )
    monkeypatch.setattr("orchestrator.agents.m2.intent._intent_llm", lambda: fake)
    intent = classify_phase_intent(
        last_user_message="hmm something about motivation",
        current_phase="research_state",
        mode="interactive",
    )
    assert intent.action == "refine"


def test_select_gaps_in_phase_3():
    intent = classify_phase_intent(
        last_user_message="use gap 1 and gap 3",
        current_phase="gap_analysis",
        mode="interactive",
    )
    assert intent.action == "select"
    assert intent.selected_ids == ["1", "3"]
```

- [ ] **Step 2: Run — should fail**

Run: `cd /Users/caonguyenvan/project/dothesis && source api/.venv/bin/activate && python -m pytest orchestrator/tests/agents/m2/test_intent_classifier.py -v`
Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 3: Implement classifier**

Create `orchestrator/agents/m2/intent.py`:

```python
"""M2 per-phase intent classifier.

Hybrid rules-first / LLM-fallback. In auto mode, always returns confirm.
"""
from __future__ import annotations

import os
import re
from typing import Literal

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field


PhaseKey = Literal[
    "familiarize", "research_state", "gap_analysis",
    "reference_confirm", "output_gen",
]


class PhaseIntent(BaseModel):
    action: Literal[
        "confirm",           # accept current output, advance to next phase
        "refine",            # regenerate with new constraint (self-loop)
        "navigate",          # jump to a different phase
        "select",            # Phase 3: pick gap ids
        "skip",              # Phase 4: skip this page reference
        "skip_all",          # Phase 4: skip all remaining
        "correct_page",      # Phase 4: provide a corrected page number
        "add_custom_gap",    # Phase 3: user supplies their own gap
    ] = "confirm"
    refinement_text: str = ""
    target_phase: PhaseKey | None = None
    selected_ids: list[str] = Field(default_factory=list)
    corrected_page: int | None = None
    custom_gap_text: str = ""


_CONFIRM_WORDS = {
    "yes", "y", "ok", "okay", "looks good", "confirm", "go", "continue",
    "đồng ý", "ok rồi", "tiếp tục", "tốt rồi",
}
_REFINE_KEYWORDS = ("redo", "regenerate", "change", "focus on", "instead",
                    "làm lại", "đổi", "tập trung vào")
_NAV_KEYWORDS_TO_PHASE: dict[str, PhaseKey] = {
    "back to research state": "research_state",
    "back to research": "research_state",
    "back to gap": "gap_analysis",
    "back to references": "reference_confirm",
    "redo familiarize": "familiarize",
    "go to research state": "research_state",
    "go to gap": "gap_analysis",
    "quay lại nghiên cứu": "research_state",
    "quay lại gap": "gap_analysis",
}
_SKIP_ALL_WORDS = {"skip all", "skip the rest", "bỏ qua tất cả"}
_SKIP_WORDS = {"skip", "next", "bỏ qua"}


def _intent_llm():
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.0-flash-001"),
        temperature=0.0,
    )


def classify_phase_intent(
    *,
    last_user_message: str,
    current_phase: PhaseKey,
    mode: Literal["interactive", "auto"],
) -> PhaseIntent:
    """Classify the user's reply within the active M2 phase."""
    if mode == "auto":
        return PhaseIntent(action="confirm")

    text = (last_user_message or "").strip().lower()

    # 1. Navigation has highest priority (overrides phase-local actions).
    for kw, target in _NAV_KEYWORDS_TO_PHASE.items():
        if kw in text:
            return PhaseIntent(action="navigate", target_phase=target)

    # 2. Phase-3 selection: "use gap 1 and gap 3" / "gap 2"
    if current_phase == "gap_analysis":
        ids = re.findall(r"\bgap\s*(\d+)\b", text)
        if ids:
            return PhaseIntent(action="select", selected_ids=ids)
        if "custom gap" in text or "add gap" in text:
            return PhaseIntent(action="add_custom_gap",
                                custom_gap_text=last_user_message)

    # 3. Phase-4 specific
    if current_phase == "reference_confirm":
        if any(kw in text for kw in _SKIP_ALL_WORDS):
            return PhaseIntent(action="skip_all")
        page_match = re.search(r"page\s+(\d+)", text)
        if page_match and ("correct" in text or "actually" in text):
            return PhaseIntent(action="correct_page",
                                corrected_page=int(page_match.group(1)))
        if any(kw in text for kw in _SKIP_WORDS):
            return PhaseIntent(action="skip")

    # 4. Refine — explicit keyword
    if any(kw in text for kw in _REFINE_KEYWORDS):
        return PhaseIntent(action="refine", refinement_text=last_user_message)

    # 5. Confirm — exact / phrase match
    if any(text == w or text.startswith(w + " ") for w in _CONFIRM_WORDS):
        return PhaseIntent(action="confirm")

    # 6. Ambiguous — defer to LLM with structured output
    try:
        llm = _intent_llm().with_structured_output(PhaseIntent)
        prompt = (
            f"Classify the user's intent in M2 Literature Review phase '{current_phase}'.\n"
            f"User message: {last_user_message}\n"
            "If unclear, default to 'refine' with the message as refinement_text."
        )
        return llm.invoke(prompt)
    except Exception:
        # Last-resort: treat as refine (preserves the user's intent of pushing back).
        return PhaseIntent(action="refine", refinement_text=last_user_message)
```

- [ ] **Step 4: Run — should pass**

Run: `cd /Users/caonguyenvan/project/dothesis && source api/.venv/bin/activate && python -m pytest orchestrator/tests/agents/m2/test_intent_classifier.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/agents/m2/intent.py \
        orchestrator/tests/agents/m2/test_intent_classifier.py
git commit -m "feat(orchestrator): M2 per-phase intent classifier (rules + LLM fallback)"
```

---

### Task 8: State translation (_seed_from_outer / _flatten_to_m2_output)

**Files:**
- Create: `orchestrator/agents/m2/translation.py`
- Create: `orchestrator/tests/agents/m2/test_state_translation.py`

- [ ] **Step 1: Tests**

Create `orchestrator/tests/agents/m2/test_state_translation.py`:

```python
"""Tests for the outer-state ↔ sub-graph-state translation layer."""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage
from sqlalchemy.orm import Session

from app.db import get_engine, get_session_factory
from app.models import PaperUpload, Project, User
from orchestrator.agents.m2.translation import (
    _flatten_to_m2_output, _seed_from_outer,
)
from orchestrator.state import ContextStore


def _make_user_project(db: Session) -> Project:
    u = User(email=f"u{uuid.uuid4().hex[:6]}@x",
             username=f"u{uuid.uuid4().hex[:6]}", password_hash="x")
    db.add(u); db.flush()
    p = Project(user_id=u.id, name="T", language="en", citation_style="apa")
    db.add(p); db.flush()
    return p


def test_seed_from_outer_reads_m1_topic():
    with Session(get_engine()) as db:
        p = _make_user_project(db); db.commit()
        outer_state = {
            "project_id": p.id, "thread_id": uuid.uuid4(),
            "messages": [HumanMessage("hi")],
            "current_module": "M2",
            "context_store": ContextStore(
                m1_topic={
                    "research_title": "TL→EE",
                    "research_type": "quantitative",
                    "language": "vi",
                    "confirmed_at": "2026-05-26T00:00:00",
                },
            ),
            "mode": "interactive",
        }
        sub = _seed_from_outer(outer_state, db)
        assert sub["research_title"] == "TL→EE"
        assert sub["research_type"] == "quantitative"
        assert sub["language"] == "vi"
        assert sub["paper_uris"] == []
        assert sub["current_phase"] == "familiarize"


def test_seed_from_outer_populates_paper_uris_from_uploads():
    with Session(get_engine()) as db:
        p = _make_user_project(db)
        for fn, uri in [("a.pdf", "s3://b/a.pdf"), ("b.pdf", "s3://b/b.pdf")]:
            db.add(PaperUpload(
                project_id=p.id, filename=fn, s3_uri=uri,
                size_bytes=100, mime_type="application/pdf",
            ))
        db.commit()
        outer_state = {
            "project_id": p.id, "thread_id": uuid.uuid4(),
            "messages": [], "current_module": "M2",
            "context_store": ContextStore(
                m1_topic={"research_title": "X", "research_type": "qualitative",
                          "language": "en", "confirmed_at": "2026-05-26"},
            ),
            "mode": "auto",
        }
        sub = _seed_from_outer(outer_state, db)
        assert sorted(sub["paper_uris"]) == ["s3://b/a.pdf", "s3://b/b.pdf"]


def test_seed_restores_partial_work_from_context_store():
    with Session(get_engine()) as db:
        p = _make_user_project(db); db.commit()
        outer_state = {
            "project_id": p.id, "thread_id": uuid.uuid4(),
            "messages": [],
            "context_store": ContextStore(
                m1_topic={"research_title": "X", "research_type": "qualitative",
                          "language": "en", "confirmed_at": "2026-05-26"},
                m2_literature={
                    "research_state_summary": "draft so far...",
                    "research_gaps": [{"description": "g1"}],
                    "theoretical_framework": "F",
                    "literature_review_doc": "",
                    "citation_list": [],
                },
            ),
            "mode": "interactive",
        }
        sub = _seed_from_outer(outer_state, db)
        assert sub["research_state_draft"] == "draft so far..."


def test_flatten_complete_state_emits_full_m2_output():
    sub_state = {
        "current_phase": "DONE",
        "research_state_draft": "synthesis",
        "candidate_gaps": [{"description": "g1", "supporting_papers": [],
                            "relevance": "High", "confirmed": True}],
        "selected_gap_ids": ["0"],
        "verified_refs": [],
        "ch2_draft": "Chapter 2 draft",
        "citation_list": [{"author": "A", "year": 2024, "title": "T"}],
        "research_type": "quantitative",
    }
    out = _flatten_to_m2_output(sub_state)
    assert out["research_state_summary"] == "synthesis"
    assert out["literature_review_doc"] == "Chapter 2 draft"
    assert out["hypotheses"] == []   # populated from research_type in a later phase
    assert out["citation_list"][0]["author"] == "A"
    assert "confirmed_at" in out  # DONE → set timestamp


def test_flatten_partial_state_omits_confirmed_at():
    sub_state = {
        "current_phase": "gap_analysis",
        "research_state_draft": "partial",
        "candidate_gaps": [],
        "verified_refs": [],
        "ch2_draft": None,
        "citation_list": [],
        "research_type": "qualitative",
    }
    out = _flatten_to_m2_output(sub_state)
    assert out.get("confirmed_at") is None
```

- [ ] **Step 2: Run — should fail**

Run: `cd /Users/caonguyenvan/project/dothesis && source api/.venv/bin/activate && python -m pytest orchestrator/tests/agents/m2/test_state_translation.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement translation**

Create `orchestrator/agents/m2/translation.py`:

```python
"""Translation between outer OrchestratorState and M2SubGraphState.

These are the only two functions that touch both shapes. Everywhere else
in the M2 code talks to one or the other but never both.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import PaperUpload
from orchestrator.agents.m2.state import M2SubGraphState, fresh_state


def _seed_from_outer(outer_state: dict, db: Session) -> M2SubGraphState:
    """Build a fresh M2SubGraphState from the outer state + DB-resolved paper_uris.

    Restores any partial work in context_store.m2_literature so the user can
    resume mid-conversation across sessions.
    """
    cs = outer_state["context_store"]
    m1 = cs.m1_topic or {}
    m2 = cs.m2_literature or {}

    # Resolve paper URIs from paper_uploads table.
    project_id = outer_state.get("project_id")
    paper_uris: list[str] = []
    if project_id is not None:
        rows = db.query(PaperUpload).filter_by(project_id=project_id).all()
        paper_uris = [r.s3_uri for r in rows]

    sub = fresh_state(
        project_id=project_id,
        thread_id=outer_state.get("thread_id"),
        research_title=m1.get("research_title", "Untitled"),
        research_type=m1.get("research_type", "quantitative"),
        language=m1.get("language", "en"),
        paper_uris=paper_uris,
        mode=outer_state.get("mode", "interactive"),
    )

    # Restore partial work from context_store.m2_literature (if any).
    if m2.get("research_state_summary"):
        sub["research_state_draft"] = m2["research_state_summary"]
    if m2.get("research_gaps"):
        sub["candidate_gaps"] = m2["research_gaps"]
        sub["selected_gap_ids"] = [str(i) for i in range(len(m2["research_gaps"]))]
    if m2.get("citation_list"):
        sub["citation_list"] = m2["citation_list"]
    return sub


def _flatten_to_m2_output(sub_state: M2SubGraphState) -> dict[str, Any]:
    """Pack the sub-graph's final state into a M2Output-shape dict.

    Only sets confirmed_at when the sub-graph reached its DONE phase.
    """
    research_type = sub_state.get("research_type", "quantitative")
    research_gaps = sub_state.get("candidate_gaps") or []
    # If selection happened, narrow to selected only
    if sub_state.get("selected_gap_ids"):
        try:
            sel = set(int(i) for i in sub_state["selected_gap_ids"])
            research_gaps = [g for i, g in enumerate(research_gaps) if i in sel]
        except (ValueError, TypeError):
            pass

    out: dict[str, Any] = {
        "research_state_summary": sub_state.get("research_state_draft") or "",
        "research_gaps": research_gaps,
        "theoretical_framework": sub_state.get("theoretical_framework", ""),
        "hypotheses": [] if research_type == "qualitative"
                       else sub_state.get("hypotheses", []),
        "propositions": [] if research_type == "quantitative"
                         else sub_state.get("propositions", []),
        "literature_review_doc": sub_state.get("ch2_draft") or "",
        "citation_list": sub_state.get("citation_list", []),
    }
    if sub_state.get("current_phase") == "DONE":
        out["confirmed_at"] = datetime.now(timezone.utc).isoformat()
    return out
```

- [ ] **Step 4: Run — should pass**

Run: `cd /Users/caonguyenvan/project/dothesis && source api/.venv/bin/activate && python -m pytest orchestrator/tests/agents/m2/test_state_translation.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/agents/m2/translation.py \
        orchestrator/tests/agents/m2/test_state_translation.py
git commit -m "feat(orchestrator): M2 outer↔sub-graph state translation"
```

---

### Task 9: Empty sub-graph scaffold

**Files:**
- Create: `orchestrator/agents/m2/graph.py`
- Create: `orchestrator/agents/m2/phases/__init__.py`

This task ships the graph builder with all 5 phase nodes as STUB pass-through functions that just advance the phase pointer. Real phase logic lands in Tasks 10-14.

- [ ] **Step 1: Write a stub test**

Append a test to `orchestrator/tests/agents/m2/test_state.py`:

```python
def test_build_m2_subgraph_compiles_with_stubs():
    from langgraph.checkpoint.memory import MemorySaver
    from orchestrator.agents.m2.graph import build_m2_subgraph
    g = build_m2_subgraph(interactive=False, checkpointer=MemorySaver())
    assert g is not None


def test_m2_subgraph_auto_mode_walks_to_done():
    from langchain_core.messages import HumanMessage
    from langgraph.checkpoint.memory import MemorySaver
    from orchestrator.agents.m2.graph import build_m2_subgraph
    from orchestrator.agents.m2.state import fresh_state

    g = build_m2_subgraph(interactive=False, checkpointer=MemorySaver())
    s = fresh_state(
        project_id="00000000-0000-0000-0000-000000000001",
        thread_id="00000000-0000-0000-0000-000000000002",
        research_title="X", research_type="quantitative",
        language="en", paper_uris=[], mode="auto",
    )
    final = g.invoke(s, config={"configurable": {"thread_id": "t1::m2"}})
    assert final["current_phase"] == "DONE"
```

- [ ] **Step 2: Run — should fail**

Run: `python -m pytest orchestrator/tests/agents/m2/test_state.py -v`
Expected: FAIL (the two new tests).

- [ ] **Step 3: Implement scaffold**

Create `orchestrator/agents/m2/phases/__init__.py`:

```python
"""M2 phase node implementations."""
```

Create `orchestrator/agents/m2/graph.py`:

```python
"""M2 sub-graph builder — supervisor in the middle, 5 phase nodes on the spokes."""
from __future__ import annotations

import os
from functools import lru_cache

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from orchestrator.agents.m2.state import M2SubGraphState, PhaseKey


# Stubs — Tasks 10-14 replace these with real phase logic.
def _stub_phase(next_phase: PhaseKey):
    def _node(state: M2SubGraphState) -> dict:
        return {"current_phase": next_phase}
    return _node


_PHASE_TO_NODE_NAME = {
    "familiarize": "m2_familiarize",
    "research_state": "m2_research_state",
    "gap_analysis": "m2_gap_analysis",
    "reference_confirm": "m2_reference_confirm",
    "output_gen": "m2_output_gen",
}


def _route_from_start(state: M2SubGraphState) -> str:
    """Pick the entry node based on current_phase (allows resuming mid-graph)."""
    phase = state.get("current_phase", "familiarize")
    if phase == "DONE":
        return "END"
    return _PHASE_TO_NODE_NAME.get(phase, "m2_familiarize")


def build_m2_subgraph(*, interactive: bool, checkpointer: BaseCheckpointSaver):
    """Compile the M2 sub-graph.

    Tasks 10-14 replace the stub phase functions with real ones.
    Task 15 sets up the conditional self-loop edges.
    """
    # Late imports — phases get filled in across Tasks 10-14.
    from orchestrator.agents.m2.phases import (
        phase1_familiarize, phase2_research_state, phase3_gap_analysis,
        phase4_reference_confirm, phase5_output_gen,
    )

    builder = StateGraph(M2SubGraphState)
    builder.add_node("m2_familiarize", getattr(phase1_familiarize, "run", _stub_phase("research_state")))
    builder.add_node("m2_research_state", getattr(phase2_research_state, "run", _stub_phase("gap_analysis")))
    builder.add_node("m2_gap_analysis", getattr(phase3_gap_analysis, "run", _stub_phase("reference_confirm")))
    builder.add_node("m2_reference_confirm", getattr(phase4_reference_confirm, "run", _stub_phase("output_gen")))
    builder.add_node("m2_output_gen", getattr(phase5_output_gen, "run", _stub_phase("DONE")))

    # Linear edges (Task 15 replaces with conditional self-loops)
    builder.add_conditional_edges(START, _route_from_start, {
        "m2_familiarize": "m2_familiarize", "m2_research_state": "m2_research_state",
        "m2_gap_analysis": "m2_gap_analysis", "m2_reference_confirm": "m2_reference_confirm",
        "m2_output_gen": "m2_output_gen", "END": END,
    })
    builder.add_edge("m2_familiarize", "m2_research_state")
    builder.add_edge("m2_research_state", "m2_gap_analysis")
    builder.add_edge("m2_gap_analysis", "m2_reference_confirm")
    builder.add_edge("m2_reference_confirm", "m2_output_gen")
    builder.add_edge("m2_output_gen", END)

    interrupt_before = [] if not interactive else [
        "m2_familiarize", "m2_research_state", "m2_gap_analysis",
        "m2_reference_confirm", "m2_output_gen",
    ]
    return builder.compile(checkpointer=checkpointer, interrupt_before=interrupt_before)


@lru_cache(maxsize=2)
def get_m2_graph(interactive: bool = True):
    """Cached singleton — uses the same PostgresSaver as the outer graph."""
    from orchestrator.graph import _get_pool
    from langgraph.checkpoint.postgres import PostgresSaver
    saver = PostgresSaver(_get_pool())
    saver.setup()  # idempotent
    return build_m2_subgraph(interactive=interactive, checkpointer=saver)
```

Create empty placeholders for the 5 phase files so the `getattr(..., "run", _stub_phase(...))` falls back cleanly:

```bash
touch orchestrator/agents/m2/phases/phase1_familiarize.py
touch orchestrator/agents/m2/phases/phase2_research_state.py
touch orchestrator/agents/m2/phases/phase3_gap_analysis.py
touch orchestrator/agents/m2/phases/phase4_reference_confirm.py
touch orchestrator/agents/m2/phases/phase5_output_gen.py
```

- [ ] **Step 4: Run — should pass**

Run: `python -m pytest orchestrator/tests/agents/m2/test_state.py -v`
Expected: 4 PASS (the original 2 + the 2 new ones).

- [ ] **Step 5: Update orchestrator/pyproject.toml**

Add the new packages so `pip install -e orchestrator` picks them up. Edit `orchestrator/pyproject.toml`:

```diff
 packages = [
     "orchestrator",
     "orchestrator.agents",
+    "orchestrator.agents.m2",
+    "orchestrator.agents.m2.phases",
     "orchestrator.schemas",
     "orchestrator.tools",
 ]
```

Reinstall:
```bash
cd /Users/caonguyenvan/project/dothesis && source api/.venv/bin/activate && pip install -e orchestrator --quiet
```

- [ ] **Step 6: Commit**

```bash
git add orchestrator/agents/m2/graph.py orchestrator/agents/m2/phases/ \
        orchestrator/pyproject.toml \
        orchestrator/tests/agents/m2/test_state.py
git commit -m "feat(orchestrator): M2 sub-graph scaffold (stub phases, linear edges)"
```

---

## Phase C — 5 phase node implementations

Each phase node file has the same shape: a `run(state) -> dict` function that returns a state patch.

### Task 10: Phase 1 — Familiarize

**Files:**
- Create: `orchestrator/prompts/m2/_style.md`
- Create: `orchestrator/prompts/m2/1_familiarize.md`
- Modify: `orchestrator/agents/m2/phases/phase1_familiarize.py`
- Create: `orchestrator/tests/agents/m2/test_phase1_familiarize.py`

- [ ] **Step 1: Write prompts**

Create `orchestrator/prompts/m2/_style.md`:

```markdown
# M2 phase prompts — shared style guide

Voice and tone (apply across all 5 phase prompts):

- **Plain conversational tone.** This is a chat, not a form. Avoid bullet lists when prose works.
- **One question per turn** in interactive mode. Don't ask the user multiple things at once.
- **Cite specifically.** When referencing literature, name the author, year, and page when known. Mark unknown pages as `[page?]`.
- **Mirror the user's language.** If the user types in Vietnamese, respond in Vietnamese. Default to English when the user's language is ambiguous.
- **Don't repeat the schema at the user.** They don't need to see field names like `research_state_draft` — talk in plain terms.
- **Don't invent.** Never fabricate citations or page numbers.
```

Create `orchestrator/prompts/m2/1_familiarize.md`:

```markdown
# Phase 1 — Familiarize

You're at the start of the M2 literature-review conversation. Greet briefly and ask whether the user has academic papers to upload.

Behavior:
- If `paper_uris` already non-empty: acknowledge them by filename, ask whether to use them as the primary source.
- If `paper_uris` empty: ask whether the user wants to upload some, OR proceed with AI-driven citation search instead.

Keep it to 1-2 short sentences. Don't list the schema fields you're trying to fill — that's internal to you. Just have the conversation.
```

- [ ] **Step 2: Write tests**

Create `orchestrator/tests/agents/m2/test_phase1_familiarize.py`:

```python
"""Tests for Phase 1 — Familiarize."""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage

from orchestrator.agents.m2.state import fresh_state


def _state(mode="interactive", paper_uris=None, user_msg="start"):
    s = fresh_state(
        project_id="p", thread_id="t", research_title="X",
        research_type="quantitative", language="en",
        paper_uris=paper_uris or [], mode=mode,
    )
    s["messages"] = [HumanMessage(content=user_msg)]
    return s


def test_phase1_first_call_with_no_uploads_asks_question(monkeypatch):
    from orchestrator.agents.m2.phases import phase1_familiarize
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "Do you have papers to upload?"
    monkeypatch.setattr(phase1_familiarize, "_get_llm", lambda: fake_llm)

    patch = phase1_familiarize.run(_state())
    # Phase 1 doesn't advance — sets has_uploaded_papers to None and emits a question
    assert patch.get("has_uploaded_papers") is None
    msgs = patch.get("messages", [])
    assert len(msgs) == 1
    assert "papers" in msgs[0].content.lower()


def test_phase1_with_uploads_lists_filenames(monkeypatch):
    from orchestrator.agents.m2.phases import phase1_familiarize
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "I see 2 papers — use them?"
    monkeypatch.setattr(phase1_familiarize, "_get_llm", lambda: fake_llm)

    patch = phase1_familiarize.run(_state(paper_uris=["s3://b/a.pdf", "s3://b/b.pdf"]))
    msgs = patch.get("messages", [])
    assert any("2" in m.content or "papers" in m.content.lower() for m in msgs)


def test_phase1_resume_after_confirm_advances(monkeypatch):
    """When user says yes/upload, has_uploaded_papers becomes True and phase advances."""
    from orchestrator.agents.m2.phases import phase1_familiarize
    s = _state(paper_uris=["s3://b/a.pdf"], user_msg="yes use them")
    # Simulate resume: the agent has previously asked the question
    s["has_uploaded_papers"] = None
    monkeypatch.setattr(phase1_familiarize, "_get_llm", lambda: MagicMock())

    patch = phase1_familiarize.run(s)
    assert patch.get("has_uploaded_papers") is True
    assert patch.get("current_phase") == "research_state"


def test_phase1_auto_mode_advances_immediately():
    from orchestrator.agents.m2.phases import phase1_familiarize
    patch = phase1_familiarize.run(_state(mode="auto", paper_uris=["s3://b/a.pdf"]))
    assert patch.get("has_uploaded_papers") is True
    assert patch.get("current_phase") == "research_state"


def test_phase1_auto_mode_no_papers_also_advances():
    from orchestrator.agents.m2.phases import phase1_familiarize
    patch = phase1_familiarize.run(_state(mode="auto", paper_uris=[]))
    assert patch.get("has_uploaded_papers") is False
    assert patch.get("current_phase") == "research_state"
```

- [ ] **Step 3: Run — should fail**

Run: `python -m pytest orchestrator/tests/agents/m2/test_phase1_familiarize.py -v`
Expected: FAIL (run() doesn't exist).

- [ ] **Step 4: Implement Phase 1**

Replace `orchestrator/agents/m2/phases/phase1_familiarize.py`:

```python
"""Phase 1 — Familiarize.

First call (interactive): asks whether to use uploaded papers or proceed with
AI-search. Does NOT advance — leaves has_uploaded_papers = None.
Resume (interactive): inspects user reply, sets has_uploaded_papers, advances.
Auto mode: assumes True if uploads exist, False otherwise. Always advances.
"""
from __future__ import annotations

import os
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from orchestrator.agents.m2.intent import classify_phase_intent
from orchestrator.agents.m2.state import M2SubGraphState

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "prompts" / "m2"
_PROMPT = (_PROMPT_DIR / "1_familiarize.md").read_text()
_STYLE = (_PROMPT_DIR / "_style.md").read_text()


def _get_llm():
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.0-flash-001"),
        temperature=0.4,
    )


def run(state: M2SubGraphState) -> dict:
    mode = state.get("mode", "interactive")
    paper_uris = state.get("paper_uris", [])

    if mode == "auto":
        return {
            "has_uploaded_papers": bool(paper_uris),
            "current_phase": "research_state",
        }

    # Interactive — decide if first-call or resume.
    if state.get("has_uploaded_papers") is None:
        # First call OR resume after a no-decision message.
        last_user = next(
            (m.content for m in reversed(state.get("messages") or [])
             if isinstance(m, HumanMessage)),
            "",
        )
        # If there's a user message that looks like a confirm/skip, resume-advance.
        if last_user.strip():
            intent = classify_phase_intent(
                last_user_message=last_user,
                current_phase="familiarize",
                mode="interactive",
            )
            if intent.action in {"confirm", "skip"}:
                return {
                    "has_uploaded_papers": (intent.action == "confirm") or bool(paper_uris),
                    "current_phase": "research_state",
                }

        # First call — generate the question.
        if paper_uris:
            user_prompt = (
                f"{_STYLE}\n\n{_PROMPT}\n\n"
                f"The project has {len(paper_uris)} uploaded paper(s). "
                f"Ask whether to use them as primary citation sources, or fall back to AI search."
            )
        else:
            user_prompt = (
                f"{_STYLE}\n\n{_PROMPT}\n\n"
                f"The project has no uploaded papers. "
                f"Ask whether the user wants to upload some, or proceed with AI search."
            )
        msg = _get_llm().invoke(user_prompt).content
        return {
            "messages": [AIMessage(content=msg)],
            "has_uploaded_papers": None,  # still waiting
        }

    # Already has a value — already resolved, just advance.
    return {"current_phase": "research_state"}
```

- [ ] **Step 5: Run — should pass**

Run: `python -m pytest orchestrator/tests/agents/m2/test_phase1_familiarize.py -v`
Expected: 5 PASS.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/prompts/m2/_style.md orchestrator/prompts/m2/1_familiarize.md \
        orchestrator/agents/m2/phases/phase1_familiarize.py \
        orchestrator/tests/agents/m2/test_phase1_familiarize.py
git commit -m "feat(orchestrator): M2 Phase 1 — Familiarize"
```

---

### Task 11: Phase 2 — Research_State (heaviest, regen loop)

**Files:**
- Create: `orchestrator/prompts/m2/2_research_state.md`
- Modify: `orchestrator/agents/m2/phases/phase2_research_state.py`
- Create: `orchestrator/tests/agents/m2/test_phase2_research_state.py`

- [ ] **Step 1: Write the prompt**

Create `orchestrator/prompts/m2/2_research_state.md`:

```markdown
# Phase 2 — Research_State

Synthesize the current state of research on the project's topic. Output should:

- Be a single prose passage (~250-400 words for a thesis-level synthesis)
- Cite specific authors and years; include page numbers when sourced from uploaded PDFs
- Use a neutral academic tone
- Cover: theoretical foundations, key empirical findings, contested questions

If the user has supplied refinements (e.g., "focus on Self-Determination Theory"), re-synthesize honoring them.

If you've scouted citations, use them. Don't invent citations.

When you're done, your output goes back to the user verbatim in the next chat message.
```

- [ ] **Step 2: Write tests**

Create `orchestrator/tests/agents/m2/test_phase2_research_state.py`:

```python
"""Tests for Phase 2 — Research_State.

Covers: first call (scout + synthesize), regen loop, 5-cap, navigate.
"""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage

from orchestrator.agents.m2.state import fresh_state


def _state(mode="interactive", user_msg="continue", **overrides):
    s = fresh_state(
        project_id="p", thread_id="t", research_title="TL → EE",
        research_type="quantitative", language="en",
        paper_uris=[], mode=mode,
    )
    s["messages"] = [HumanMessage(content=user_msg)]
    s.update(overrides)
    return s


def test_phase2_first_call_scouts_and_synthesizes(monkeypatch):
    from orchestrator.agents.m2.phases import phase2_research_state

    fake_scout = MagicMock(return_value=[
        {"title": "P1", "authors": "Bass", "year": 1985,
         "source": "Journal", "url": None, "doi": None},
    ])
    monkeypatch.setattr(phase2_research_state, "_scout", fake_scout)

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "Synthesis with (Bass, 1985)."
    monkeypatch.setattr(phase2_research_state, "_get_llm", lambda: fake_llm)

    patch = phase2_research_state.run(_state())
    assert "Bass" in patch["research_state_draft"]
    assert patch["research_state_citations"] == [
        {"title": "P1", "authors": "Bass", "year": 1985,
         "source": "Journal", "url": None, "doi": None},
    ]
    assert patch.get("research_state_confirmed") is False
    msgs = patch.get("messages", [])
    assert len(msgs) == 1


def test_phase2_refine_appends_and_regenerates_with_cached_citations(monkeypatch):
    """Second call with 'redo' should NOT call scout again — reuses cached citations."""
    from orchestrator.agents.m2.phases import phase2_research_state

    scout_calls = {"n": 0}
    def fake_scout(*a, **kw):
        scout_calls["n"] += 1
        return []
    monkeypatch.setattr(phase2_research_state, "_scout", fake_scout)

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "Refined synthesis focusing on SDT."
    monkeypatch.setattr(phase2_research_state, "_get_llm", lambda: fake_llm)

    s = _state(user_msg="redo focusing on Self-Determination Theory")
    s["research_state_draft"] = "old synthesis"
    s["research_state_citations"] = [{"title": "P1"}]
    patch = phase2_research_state.run(s)
    assert scout_calls["n"] == 0  # didn't re-scout
    assert "SDT" in patch["research_state_draft"]
    assert patch.get("research_state_refinements") == ["redo focusing on Self-Determination Theory"]
    assert patch["regeneration_count"]["research_state"] == 1


def test_phase2_confirm_advances_to_gap_analysis(monkeypatch):
    from orchestrator.agents.m2.phases import phase2_research_state
    monkeypatch.setattr(phase2_research_state, "_get_llm", lambda: MagicMock())

    s = _state(user_msg="looks good, continue")
    s["research_state_draft"] = "synthesis"
    patch = phase2_research_state.run(s)
    assert patch.get("research_state_confirmed") is True
    assert patch.get("current_phase") == "gap_analysis"


def test_phase2_regen_cap_blocks_6th_iteration(monkeypatch):
    from orchestrator.agents.m2.phases import phase2_research_state
    fake_llm = MagicMock()
    monkeypatch.setattr(phase2_research_state, "_get_llm", lambda: fake_llm)

    s = _state(user_msg="redo with a different lens")
    s["research_state_draft"] = "synthesis"
    s["regeneration_count"] = {"research_state": 5}
    patch = phase2_research_state.run(s)
    # No regeneration happened — draft unchanged, no LLM call
    assert patch.get("research_state_draft") == "synthesis"
    fake_llm.invoke.assert_not_called()
    msgs = patch.get("messages", [])
    assert any("lock" in m.content.lower() or "5" in m.content for m in msgs)


def test_phase2_navigate_back_to_familiarize(monkeypatch):
    from orchestrator.agents.m2.phases import phase2_research_state
    monkeypatch.setattr(phase2_research_state, "_get_llm", lambda: MagicMock())

    s = _state(user_msg="redo familiarize")
    s["research_state_draft"] = "synthesis"
    patch = phase2_research_state.run(s)
    assert patch.get("current_phase") == "familiarize"


def test_phase2_auto_mode_one_shot(monkeypatch):
    from orchestrator.agents.m2.phases import phase2_research_state
    monkeypatch.setattr(phase2_research_state, "_scout", lambda *a, **kw: [])
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "Auto synthesis."
    monkeypatch.setattr(phase2_research_state, "_get_llm", lambda: fake_llm)

    patch = phase2_research_state.run(_state(mode="auto"))
    assert patch.get("research_state_confirmed") is True
    assert patch.get("current_phase") == "gap_analysis"
```

- [ ] **Step 3: Run — should fail**

Run: `python -m pytest orchestrator/tests/agents/m2/test_phase2_research_state.py -v`
Expected: FAIL.

- [ ] **Step 4: Implement Phase 2**

Replace `orchestrator/agents/m2/phases/phase2_research_state.py`:

```python
"""Phase 2 — Research_State.

Generates a literature synthesis. Self-loops on user "refine" requests,
capped at 5 iterations (`M2_REGEN_CAP` env). Reuses scouted citations
across regens — only the first call invokes scout_citations.
"""
from __future__ import annotations

import os
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from orchestrator.agents.m2.intent import classify_phase_intent
from orchestrator.agents.m2.state import M2SubGraphState
from orchestrator.tools.m2_literature import scout_citations

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "prompts" / "m2"
_PROMPT = (_PROMPT_DIR / "2_research_state.md").read_text()
_STYLE = (_PROMPT_DIR / "_style.md").read_text()

_PHASE_KEY = "research_state"


def _regen_cap() -> int:
    return int(os.getenv("M2_REGEN_CAP", "5"))


def _get_llm():
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.0-flash-001"),
        temperature=0.5,
    )


def _scout(topic: str, min_n: int = 20) -> list[dict]:
    """Indirection so tests can monkeypatch easily."""
    return scout_citations.invoke({"topic": topic, "min_n": min_n})


def _synthesize(state: M2SubGraphState, refinements: list[str]) -> str:
    citations = state.get("research_state_citations", [])
    citations_block = "\n".join(
        f"- {c.get('authors', '?')} ({c.get('year', '?')}). {c.get('title', '?')}."
        for c in citations[:30]
    )
    refinement_block = ""
    if refinements:
        refinement_block = "User refinements:\n" + "\n".join(f"- {r}" for r in refinements)
    user_prompt = (
        f"{_STYLE}\n\n{_PROMPT}\n\n"
        f"Topic: {state.get('research_title')}\n"
        f"Research type: {state.get('research_type')}\n"
        f"Language: {state.get('language')}\n\n"
        f"Citations available:\n{citations_block}\n\n"
        f"{refinement_block}"
    )
    return _get_llm().invoke(user_prompt).content


def run(state: M2SubGraphState) -> dict:
    mode = state.get("mode", "interactive")

    # AUTO MODE — one-shot
    if mode == "auto":
        citations = state.get("research_state_citations") or _scout(state.get("research_title", ""))
        new_state = dict(state)
        new_state["research_state_citations"] = citations
        draft = _synthesize(new_state, refinements=[])
        return {
            "research_state_citations": citations,
            "research_state_draft": draft,
            "research_state_confirmed": True,
            "current_phase": "gap_analysis",
        }

    # INTERACTIVE MODE — first call vs. resume
    last_user = next(
        (m.content for m in reversed(state.get("messages") or [])
         if isinstance(m, HumanMessage)),
        "",
    )

    # First call: no draft yet OR no prior user reply to react to
    if not state.get("research_state_draft"):
        citations = _scout(state.get("research_title", ""))
        new_state = dict(state)
        new_state["research_state_citations"] = citations
        draft = _synthesize(new_state, refinements=state.get("research_state_refinements", []))
        return {
            "research_state_citations": citations,
            "research_state_draft": draft,
            "messages": [AIMessage(content=draft)],
        }

    # Resume — classify user intent
    intent = classify_phase_intent(
        last_user_message=last_user,
        current_phase=_PHASE_KEY,
        mode="interactive",
    )

    if intent.action == "navigate":
        return {"current_phase": intent.target_phase or "familiarize"}

    if intent.action == "confirm":
        return {
            "research_state_confirmed": True,
            "current_phase": "gap_analysis",
        }

    if intent.action == "refine":
        counts = dict(state.get("regeneration_count") or {})
        current_count = counts.get(_PHASE_KEY, 0)
        if current_count >= _regen_cap():
            return {
                "messages": [AIMessage(content=(
                    f"We've regenerated {_regen_cap()} times — let's lock this in "
                    "or move on. Reply 'confirm' to advance, or 'force-continue' "
                    "to bypass the cap once."
                ))],
            }
        counts[_PHASE_KEY] = current_count + 1
        refinements = list(state.get("research_state_refinements") or []) + [intent.refinement_text or last_user]
        new_state = dict(state); new_state["research_state_refinements"] = refinements
        draft = _synthesize(new_state, refinements=refinements)
        return {
            "research_state_refinements": refinements,
            "regeneration_count": counts,
            "research_state_draft": draft,
            "messages": [AIMessage(content=draft)],
        }

    # Fallback — treat as refine if unclear
    return {
        "messages": [AIMessage(content=(
            "I'm not sure what you'd like. Reply 'confirm' to advance, "
            "or describe how you'd like the synthesis changed."
        ))],
    }
```

- [ ] **Step 5: Run — should pass**

Run: `python -m pytest orchestrator/tests/agents/m2/test_phase2_research_state.py -v`
Expected: 6 PASS.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/prompts/m2/2_research_state.md \
        orchestrator/agents/m2/phases/phase2_research_state.py \
        orchestrator/tests/agents/m2/test_phase2_research_state.py
git commit -m "feat(orchestrator): M2 Phase 2 — Research_State with capped regen loop"
```

---

### Task 12: Phase 3 — Gap_Analysis

**Files:**
- Create: `orchestrator/prompts/m2/3_gap_analysis.md`
- Modify: `orchestrator/agents/m2/phases/phase3_gap_analysis.py`
- Create: `orchestrator/tests/agents/m2/test_phase3_gap_analysis.py`

- [ ] **Step 1: Prompt**

Create `orchestrator/prompts/m2/3_gap_analysis.md`:

```markdown
# Phase 3 — Gap_Analysis

Given the synthesis from Phase 2, identify 3-4 specific research gaps. Each gap must:

- Have a clear statement of what's missing or contested
- Cite 1-3 supporting papers (author, year, page when known)
- Be ranked by relevance to the project's research title

Respond with ONLY a JSON array, no prose, no markdown. Schema:
```json
[
  {"id": "1", "description": "...", "relevance": "High",
   "supporting_papers": [{"author": "X", "year": 2020, "page": 12}]}
]
```

If the user has refinements (e.g., "make them methodological"), honor them.
```

- [ ] **Step 2: Tests**

Create `orchestrator/tests/agents/m2/test_phase3_gap_analysis.py`:

```python
"""Tests for Phase 3 — Gap_Analysis."""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage

from orchestrator.agents.m2.state import fresh_state


_GAP_JSON = (
    '[{"id":"1","description":"No SME context",'
    '"relevance":"High","supporting_papers":[]},'
    '{"id":"2","description":"Mediator untested",'
    '"relevance":"Medium","supporting_papers":[]}]'
)


def _state(mode="interactive", user_msg="start"):
    s = fresh_state(
        project_id="p", thread_id="t", research_title="X",
        research_type="quantitative", language="en",
        paper_uris=[], mode=mode,
    )
    s["messages"] = [HumanMessage(content=user_msg)]
    s["research_state_draft"] = "synthesis from phase 2"
    s["research_state_citations"] = [{"title": "P1"}]
    return s


def test_phase3_first_call_proposes_gaps(monkeypatch):
    from orchestrator.agents.m2.phases import phase3_gap_analysis
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = _GAP_JSON
    monkeypatch.setattr(phase3_gap_analysis, "_get_llm", lambda: fake_llm)

    patch = phase3_gap_analysis.run(_state())
    gaps = patch["candidate_gaps"]
    assert len(gaps) == 2
    assert gaps[0]["description"] == "No SME context"


def test_phase3_select_advances_to_reference_confirm(monkeypatch):
    from orchestrator.agents.m2.phases import phase3_gap_analysis
    monkeypatch.setattr(phase3_gap_analysis, "_get_llm", lambda: MagicMock())

    s = _state(user_msg="use gap 1 and gap 2")
    s["candidate_gaps"] = [
        {"id": "1", "description": "g1"},
        {"id": "2", "description": "g2"},
    ]
    patch = phase3_gap_analysis.run(s)
    assert patch.get("selected_gap_ids") == ["1", "2"]
    assert patch.get("current_phase") == "reference_confirm"


def test_phase3_refine_regenerates(monkeypatch):
    from orchestrator.agents.m2.phases import phase3_gap_analysis
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = _GAP_JSON
    monkeypatch.setattr(phase3_gap_analysis, "_get_llm", lambda: fake_llm)

    s = _state(user_msg="redo, focus on methodological gaps")
    s["candidate_gaps"] = [{"id": "1", "description": "old gap"}]
    patch = phase3_gap_analysis.run(s)
    assert patch["candidate_gaps"][0]["description"] == "No SME context"
    assert patch["gap_refinements"] == ["redo, focus on methodological gaps"]


def test_phase3_regen_cap_blocks_6th(monkeypatch):
    from orchestrator.agents.m2.phases import phase3_gap_analysis
    fake_llm = MagicMock()
    monkeypatch.setattr(phase3_gap_analysis, "_get_llm", lambda: fake_llm)

    s = _state(user_msg="redo")
    s["candidate_gaps"] = [{"id": "1"}]
    s["regeneration_count"] = {"gap_analysis": 5}
    patch = phase3_gap_analysis.run(s)
    fake_llm.invoke.assert_not_called()


def test_phase3_auto_selects_all(monkeypatch):
    from orchestrator.agents.m2.phases import phase3_gap_analysis
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = _GAP_JSON
    monkeypatch.setattr(phase3_gap_analysis, "_get_llm", lambda: fake_llm)

    patch = phase3_gap_analysis.run(_state(mode="auto"))
    assert patch.get("selected_gap_ids") == ["1", "2"]
    assert patch.get("current_phase") == "reference_confirm"
```

- [ ] **Step 3: Run — should fail**

Run: `python -m pytest orchestrator/tests/agents/m2/test_phase3_gap_analysis.py -v`
Expected: FAIL.

- [ ] **Step 4: Implement Phase 3**

Replace `orchestrator/agents/m2/phases/phase3_gap_analysis.py`:

```python
"""Phase 3 — Gap_Analysis.

Identifies research gaps from Phase 2's synthesis. Self-loops on refinements
(5-cap). Advances when user selects gap ids.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from orchestrator.agents.m2.intent import classify_phase_intent
from orchestrator.agents.m2.state import M2SubGraphState

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "prompts" / "m2"
_PROMPT = (_PROMPT_DIR / "3_gap_analysis.md").read_text()
_STYLE = (_PROMPT_DIR / "_style.md").read_text()

_PHASE_KEY = "gap_analysis"


def _regen_cap() -> int:
    return int(os.getenv("M2_REGEN_CAP", "5"))


def _get_llm():
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.0-flash-001"),
        temperature=0.3,
    )


def _generate_gaps(state: M2SubGraphState, refinements: list[str]) -> list[dict]:
    refinement_block = ""
    if refinements:
        refinement_block = "\nUser constraints:\n" + "\n".join(f"- {r}" for r in refinements)
    user_prompt = (
        f"{_STYLE}\n\n{_PROMPT}\n\n"
        f"Synthesis from Phase 2:\n{state.get('research_state_draft', '')}\n"
        f"{refinement_block}"
    )
    resp = _get_llm().invoke(user_prompt).content
    try:
        gaps = json.loads(_strip_fence(resp))
        if isinstance(gaps, list):
            return [dict(g) for g in gaps]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _strip_fence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


def run(state: M2SubGraphState) -> dict:
    mode = state.get("mode", "interactive")

    # AUTO MODE — generate + auto-select all
    if mode == "auto":
        gaps = _generate_gaps(state, refinements=[])
        return {
            "candidate_gaps": gaps,
            "selected_gap_ids": [g.get("id", str(i)) for i, g in enumerate(gaps)],
            "current_phase": "reference_confirm",
        }

    # First call — no candidate_gaps yet
    if not state.get("candidate_gaps"):
        gaps = _generate_gaps(state, refinements=state.get("gap_refinements", []))
        text = "Here are the gaps I found:\n" + "\n".join(
            f"  {g.get('id', i+1)}. {g.get('description', '?')} ({g.get('relevance', 'Medium')})"
            for i, g in enumerate(gaps)
        ) + "\n\nWhich would you like to use? (e.g. 'use gap 1 and gap 3')"
        return {
            "candidate_gaps": gaps,
            "messages": [AIMessage(content=text)],
        }

    # Resume — classify
    last_user = next(
        (m.content for m in reversed(state.get("messages") or [])
         if isinstance(m, HumanMessage)),
        "",
    )
    intent = classify_phase_intent(
        last_user_message=last_user,
        current_phase=_PHASE_KEY,
        mode="interactive",
    )

    if intent.action == "navigate":
        return {"current_phase": intent.target_phase or "research_state"}

    if intent.action == "select":
        return {
            "selected_gap_ids": intent.selected_ids,
            "current_phase": "reference_confirm",
        }

    if intent.action == "add_custom_gap":
        existing = list(state.get("candidate_gaps") or [])
        new_id = str(len(existing) + 1)
        existing.append({
            "id": new_id,
            "description": intent.custom_gap_text or last_user,
            "relevance": "Medium",
            "supporting_papers": [],
            "confirmed": True,
        })
        return {
            "candidate_gaps": existing,
            "messages": [AIMessage(content=f"Added gap {new_id}. Want me to re-list?")],
        }

    if intent.action == "refine":
        counts = dict(state.get("regeneration_count") or {})
        current_count = counts.get(_PHASE_KEY, 0)
        if current_count >= _regen_cap():
            return {
                "messages": [AIMessage(content=(
                    f"We've regenerated {_regen_cap()} times. "
                    "Pick from the current list or 'force-continue' to bypass."
                ))],
            }
        counts[_PHASE_KEY] = current_count + 1
        refinements = list(state.get("gap_refinements") or []) + [intent.refinement_text or last_user]
        gaps = _generate_gaps(state, refinements=refinements)
        text = "Here's a revised list:\n" + "\n".join(
            f"  {g.get('id', i+1)}. {g.get('description', '?')}"
            for i, g in enumerate(gaps)
        )
        return {
            "candidate_gaps": gaps,
            "gap_refinements": refinements,
            "regeneration_count": counts,
            "messages": [AIMessage(content=text)],
        }

    return {
        "messages": [AIMessage(content=(
            "I'm not sure — say 'use gap N' to pick, or describe how to refine the list."
        ))],
    }
```

- [ ] **Step 5: Run — should pass**

Run: `python -m pytest orchestrator/tests/agents/m2/test_phase3_gap_analysis.py -v`
Expected: 5 PASS.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/prompts/m2/3_gap_analysis.md \
        orchestrator/agents/m2/phases/phase3_gap_analysis.py \
        orchestrator/tests/agents/m2/test_phase3_gap_analysis.py
git commit -m "feat(orchestrator): M2 Phase 3 — Gap_Analysis with selection + refinement"
```

---

### Task 13: Phase 4 — Reference_Confirm (cursor walk + auto-verify)

**Files:**
- Create: `orchestrator/prompts/m2/4_reference_confirm.md`
- Modify: `orchestrator/agents/m2/phases/phase4_reference_confirm.py`
- Create: `orchestrator/tests/agents/m2/test_phase4_reference_confirm.py`

- [ ] **Step 1: Prompt**

Create `orchestrator/prompts/m2/4_reference_confirm.md`:

```markdown
# Phase 4 — Reference_Confirm

For each citation that includes a page number, ask the user to verify it. If you have the source PDF available via `verify_page_numbers`, try auto-verifying first — only fall back to asking when inconclusive.

Be concise. One reference at a time. Offer 'skip', 'correct page <n>', or 'skip all' as escape hatches.
```

- [ ] **Step 2: Tests**

Create `orchestrator/tests/agents/m2/test_phase4_reference_confirm.py`:

```python
"""Tests for Phase 4 — Reference_Confirm."""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage

from orchestrator.agents.m2.state import fresh_state


def _state(mode="interactive", user_msg="continue"):
    s = fresh_state(
        project_id="p", thread_id="t", research_title="X",
        research_type="quantitative", language="en",
        paper_uris=[], mode=mode,
    )
    s["messages"] = [HumanMessage(content=user_msg)]
    s["candidate_gaps"] = [
        {"id": "1", "description": "g1",
         "supporting_papers": [
             {"author": "Wang", "year": 2011, "page": 118},
             {"author": "Bass", "year": 1985, "page": 31},
         ]},
    ]
    s["selected_gap_ids"] = ["1"]
    return s


def test_phase4_first_call_populates_queue_and_asks_first(monkeypatch):
    from orchestrator.agents.m2.phases import phase4_reference_confirm
    monkeypatch.setattr(phase4_reference_confirm, "_auto_verify",
                        lambda paper_uris, refs: refs)  # nothing auto-verifies
    monkeypatch.setattr(phase4_reference_confirm, "_get_llm", lambda: MagicMock())

    patch = phase4_reference_confirm.run(_state())
    assert len(patch["pending_page_checks"]) == 2
    assert patch.get("page_check_cursor") == 0
    msgs = patch.get("messages", [])
    assert "Wang" in msgs[0].content


def test_phase4_confirm_advances_cursor(monkeypatch):
    from orchestrator.agents.m2.phases import phase4_reference_confirm
    monkeypatch.setattr(phase4_reference_confirm, "_auto_verify",
                        lambda paper_uris, refs: refs)
    monkeypatch.setattr(phase4_reference_confirm, "_get_llm", lambda: MagicMock())

    s = _state(user_msg="yes")
    s["pending_page_checks"] = [
        {"author": "Wang", "year": 2011, "page": 118, "verified": False},
        {"author": "Bass", "year": 1985, "page": 31, "verified": False},
    ]
    s["page_check_cursor"] = 0
    patch = phase4_reference_confirm.run(s)
    assert patch.get("page_check_cursor") == 1
    # First reference marked verified
    new_verified = patch.get("verified_refs", [])
    assert len(new_verified) == 1
    assert new_verified[0]["verified"] is True


def test_phase4_correct_page_updates_and_advances(monkeypatch):
    from orchestrator.agents.m2.phases import phase4_reference_confirm
    monkeypatch.setattr(phase4_reference_confirm, "_auto_verify",
                        lambda paper_uris, refs: refs)
    monkeypatch.setattr(phase4_reference_confirm, "_get_llm", lambda: MagicMock())

    s = _state(user_msg="correct page 120")
    s["pending_page_checks"] = [
        {"author": "Wang", "year": 2011, "page": 118, "verified": False},
        {"author": "Bass", "year": 1985, "page": 31, "verified": False},
    ]
    s["page_check_cursor"] = 0
    patch = phase4_reference_confirm.run(s)
    assert patch["verified_refs"][0]["page"] == 120
    assert patch["verified_refs"][0]["verified"] is True
    assert patch["page_check_cursor"] == 1


def test_phase4_skip_all_marks_remaining_unverified(monkeypatch):
    from orchestrator.agents.m2.phases import phase4_reference_confirm
    monkeypatch.setattr(phase4_reference_confirm, "_auto_verify",
                        lambda paper_uris, refs: refs)
    monkeypatch.setattr(phase4_reference_confirm, "_get_llm", lambda: MagicMock())

    s = _state(user_msg="skip all")
    s["pending_page_checks"] = [
        {"author": "Wang", "year": 2011, "page": 118, "verified": False},
        {"author": "Bass", "year": 1985, "page": 31, "verified": False},
    ]
    s["page_check_cursor"] = 0
    patch = phase4_reference_confirm.run(s)
    assert patch.get("current_phase") == "output_gen"
    assert len(patch.get("verified_refs", [])) == 2
    assert all(r["verified"] is False for r in patch["verified_refs"])


def test_phase4_auto_mode_skips_all_user_prompts(monkeypatch):
    from orchestrator.agents.m2.phases import phase4_reference_confirm
    monkeypatch.setattr(phase4_reference_confirm, "_auto_verify",
                        lambda paper_uris, refs: refs)
    monkeypatch.setattr(phase4_reference_confirm, "_get_llm", lambda: MagicMock())

    patch = phase4_reference_confirm.run(_state(mode="auto"))
    assert patch.get("current_phase") == "output_gen"


def test_phase4_auto_verify_marks_matched_references(monkeypatch):
    """When auto-verify finds a match in uploaded PDFs, skips user prompting."""
    from orchestrator.agents.m2.phases import phase4_reference_confirm

    def fake_auto_verify(paper_uris, refs):
        # Pretend Wang's reference auto-verifies
        return [
            {**r, "verified": True} if r["author"] == "Wang" else r
            for r in refs
        ]
    monkeypatch.setattr(phase4_reference_confirm, "_auto_verify", fake_auto_verify)
    monkeypatch.setattr(phase4_reference_confirm, "_get_llm", lambda: MagicMock())

    s = _state()
    s["paper_uris"] = ["s3://b/wang2011.pdf"]
    patch = phase4_reference_confirm.run(s)
    # Wang is pre-verified; cursor should start at Bass (index 1)
    pending = patch["pending_page_checks"]
    assert pending[0]["author"] == "Wang"
    assert pending[0]["verified"] is True
    msgs = patch.get("messages", [])
    assert msgs and "Bass" in msgs[0].content  # asking about Bass, not Wang
```

- [ ] **Step 3: Run — should fail**

Run: `python -m pytest orchestrator/tests/agents/m2/test_phase4_reference_confirm.py -v`
Expected: FAIL.

- [ ] **Step 4: Implement Phase 4**

Replace `orchestrator/agents/m2/phases/phase4_reference_confirm.py`:

```python
"""Phase 4 — Reference_Confirm.

Walks every page reference in selected gaps one at a time. Auto-verifies
against uploaded PDFs first; falls back to asking user when inconclusive.
"""
from __future__ import annotations

import os
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from orchestrator.agents.m2.intent import classify_phase_intent
from orchestrator.agents.m2.state import M2SubGraphState
from orchestrator.tools.m2_literature import verify_page_numbers

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "prompts" / "m2"
_PROMPT = (_PROMPT_DIR / "4_reference_confirm.md").read_text()
_STYLE = (_PROMPT_DIR / "_style.md").read_text()

_PHASE_KEY = "reference_confirm"


def _get_llm():
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.0-flash-001"),
        temperature=0.0,
    )


def _auto_verify(paper_uris: list[str], refs: list[dict]) -> list[dict]:
    """For each reference, try to match an uploaded PDF and verify.

    Match heuristic: simple author-lastname + year substring on filename.
    Returns refs with 'verified': True where auto-verify succeeded.
    """
    if not paper_uris:
        return refs
    result = []
    for ref in refs:
        author = (ref.get("author") or "").split()[-1].lower() if ref.get("author") else ""
        year = str(ref.get("year") or "")
        matched_uri = None
        for uri in paper_uris:
            uri_lower = uri.lower()
            if author and year and author in uri_lower and year in uri_lower:
                matched_uri = uri
                break
        if matched_uri:
            try:
                outcome = verify_page_numbers.invoke({"claim": {**ref, "pdf_path": matched_uri}})
                if outcome.get("status") == "verified":
                    result.append({**ref, "verified": True})
                    continue
            except Exception:
                pass
        result.append(ref)
    return result


def _gather_pending(state: M2SubGraphState) -> list[dict]:
    """Pull every PaperReference from selected gaps into a flat queue."""
    gaps = state.get("candidate_gaps") or []
    selected = set(state.get("selected_gap_ids") or [])
    pending = []
    for gap in gaps:
        if str(gap.get("id")) in selected:
            for paper in gap.get("supporting_papers", []):
                # Only verify when a page number is present
                if paper.get("page") is not None:
                    pending.append({**paper, "verified": False})
    return pending


def _ask_at_cursor(pending: list[dict], cursor: int) -> str:
    """Render the question for the reference at the cursor."""
    if cursor >= len(pending):
        return ""
    ref = pending[cursor]
    return (
        f"Citation: {ref.get('author')} ({ref.get('year')}), "
        f"page {ref.get('page')}. Can you verify? "
        "(yes / correct page <n> / skip / skip all)"
    )


def run(state: M2SubGraphState) -> dict:
    mode = state.get("mode", "interactive")

    # First call — populate queue and run auto-verify.
    if not state.get("pending_page_checks"):
        raw = _gather_pending(state)
        verified_in_advance = _auto_verify(state.get("paper_uris", []), raw)
        # Find first unverified ref to ask about
        cursor = 0
        while cursor < len(verified_in_advance) and verified_in_advance[cursor].get("verified"):
            cursor += 1

        if mode == "auto":
            # Mark anything still unverified as False (no user to ask)
            final = [r if r.get("verified") else {**r, "verified": False}
                     for r in verified_in_advance]
            return {
                "pending_page_checks": final,
                "verified_refs": final,
                "page_check_cursor": len(final),
                "current_phase": "output_gen",
            }

        if cursor >= len(verified_in_advance):
            # All auto-verified — skip phase entirely
            return {
                "pending_page_checks": verified_in_advance,
                "verified_refs": verified_in_advance,
                "page_check_cursor": cursor,
                "current_phase": "output_gen",
            }

        return {
            "pending_page_checks": verified_in_advance,
            "page_check_cursor": cursor,
            "messages": [AIMessage(content=_ask_at_cursor(verified_in_advance, cursor))],
        }

    # Resume — classify
    last_user = next(
        (m.content for m in reversed(state.get("messages") or [])
         if isinstance(m, HumanMessage)),
        "",
    )
    intent = classify_phase_intent(
        last_user_message=last_user,
        current_phase=_PHASE_KEY,
        mode="interactive",
    )

    pending = list(state.get("pending_page_checks") or [])
    cursor = state.get("page_check_cursor") or 0
    verified = list(state.get("verified_refs") or [])

    if intent.action == "navigate":
        return {"current_phase": intent.target_phase or "gap_analysis"}

    if intent.action == "skip_all":
        # Mark all remaining as unverified
        remaining = pending[cursor:]
        for r in remaining:
            verified.append({**r, "verified": False})
        # Also flush the first part of pending that was already verified by auto-verify
        for r in pending[:cursor]:
            if r not in verified:
                verified.append(r)
        return {
            "verified_refs": verified,
            "page_check_cursor": len(pending),
            "current_phase": "output_gen",
        }

    # Confirm / correct / skip — all advance the cursor by 1
    current = pending[cursor] if cursor < len(pending) else None
    if current is not None:
        if intent.action == "correct_page" and intent.corrected_page is not None:
            verified.append({**current, "page": intent.corrected_page, "verified": True})
        elif intent.action == "skip":
            verified.append({**current, "verified": False})
        else:  # confirm
            verified.append({**current, "verified": True})

    new_cursor = cursor + 1
    # Find next unverified (skip ones auto-verified already)
    while new_cursor < len(pending) and pending[new_cursor].get("verified"):
        verified.append(pending[new_cursor])
        new_cursor += 1

    if new_cursor >= len(pending):
        return {
            "verified_refs": verified,
            "page_check_cursor": new_cursor,
            "current_phase": "output_gen",
        }

    return {
        "verified_refs": verified,
        "page_check_cursor": new_cursor,
        "messages": [AIMessage(content=_ask_at_cursor(pending, new_cursor))],
    }
```

- [ ] **Step 5: Run — should pass**

Run: `python -m pytest orchestrator/tests/agents/m2/test_phase4_reference_confirm.py -v`
Expected: 6 PASS.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/prompts/m2/4_reference_confirm.md \
        orchestrator/agents/m2/phases/phase4_reference_confirm.py \
        orchestrator/tests/agents/m2/test_phase4_reference_confirm.py
git commit -m "feat(orchestrator): M2 Phase 4 — Reference_Confirm with cursor walk + auto-verify"
```

---

### Task 14: Phase 5 — Output_Gen

**Files:**
- Create: `orchestrator/prompts/m2/5_output_gen.md`
- Modify: `orchestrator/agents/m2/phases/phase5_output_gen.py`
- Create: `orchestrator/tests/agents/m2/test_phase5_output_gen.py`

- [ ] **Step 1: Prompt**

Create `orchestrator/prompts/m2/5_output_gen.md`:

```markdown
# Phase 5 — Output_Gen

Write Chapter 2 (Literature Review) for the thesis. Use:
- Phase 2's synthesis (`research_state_draft`)
- The confirmed research gaps from Phase 3
- The verified page references from Phase 4 (mark unverified pages as `[page?]`)

Structure:
- 2.1 Theoretical Foundation
- 2.2 Empirical Studies
- 2.3 Research Gaps
- 2.4 Theoretical Framework

Length: ~1500-2500 words for a thesis-level chapter. Use academic citation style. Single-shot — no regeneration loop in this phase.
```

- [ ] **Step 2: Tests**

Create `orchestrator/tests/agents/m2/test_phase5_output_gen.py`:

```python
"""Tests for Phase 5 — Output_Gen."""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage

from orchestrator.agents.m2.state import fresh_state


def _state(mode="auto"):
    s = fresh_state(
        project_id="p", thread_id="t", research_title="X",
        research_type="quantitative", language="en",
        paper_uris=[], mode=mode,
    )
    s["messages"] = [HumanMessage(content="write")]
    s["research_state_draft"] = "synthesis"
    s["candidate_gaps"] = [{"id": "1", "description": "g1",
                            "supporting_papers": []}]
    s["selected_gap_ids"] = ["1"]
    s["verified_refs"] = [{"author": "X", "year": 2024, "page": 12, "verified": True}]
    s["research_state_citations"] = [{"author": "Y", "year": 2023, "title": "T1"}]
    return s


def test_phase5_writes_ch2_and_advances_to_done(monkeypatch):
    from orchestrator.agents.m2.phases import phase5_output_gen
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = (
        "2.1 Theoretical Foundation\n...\n"
        "2.2 Empirical Studies\n...\n"
        "2.3 Research Gaps\n...\n"
        "2.4 Theoretical Framework\nTransformational Leadership Theory"
    )
    monkeypatch.setattr(phase5_output_gen, "_get_llm", lambda: fake_llm)

    patch = phase5_output_gen.run(_state())
    assert patch.get("current_phase") == "DONE"
    assert "Theoretical Foundation" in patch.get("ch2_draft", "")
    assert patch.get("citation_list") == [{"author": "Y", "year": 2023, "title": "T1"}]


def test_phase5_marks_unverified_pages(monkeypatch):
    from orchestrator.agents.m2.phases import phase5_output_gen
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "Chapter 2 mentions [page?] for unverified."
    monkeypatch.setattr(phase5_output_gen, "_get_llm", lambda: fake_llm)

    s = _state()
    s["verified_refs"] = [{"author": "X", "year": 2024, "page": 12, "verified": False}]
    patch = phase5_output_gen.run(s)
    assert "[page?]" in patch.get("ch2_draft", "")
```

- [ ] **Step 3: Run — should fail**

Run: `python -m pytest orchestrator/tests/agents/m2/test_phase5_output_gen.py -v`
Expected: FAIL.

- [ ] **Step 4: Implement Phase 5**

Replace `orchestrator/agents/m2/phases/phase5_output_gen.py`:

```python
"""Phase 5 — Output_Gen.

Single-shot. Writes Chapter 2 of the thesis. No regeneration loop.
"""
from __future__ import annotations

import os
from pathlib import Path

from langchain_core.messages import AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from orchestrator.agents.m2.state import M2SubGraphState

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "prompts" / "m2"
_PROMPT = (_PROMPT_DIR / "5_output_gen.md").read_text()
_STYLE = (_PROMPT_DIR / "_style.md").read_text()


def _get_llm():
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.0-flash-001"),
        temperature=0.4,
    )


def _format_references(refs: list[dict]) -> str:
    lines = []
    for r in refs:
        page = r.get("page")
        page_str = str(page) if r.get("verified") and page is not None else "[page?]"
        lines.append(f"- {r.get('author')} ({r.get('year')}), p. {page_str}")
    return "\n".join(lines)


def _format_gaps(gaps: list[dict], selected: list[str]) -> str:
    selected_set = set(selected or [])
    return "\n".join(
        f"- {g.get('description', '?')}"
        for g in gaps if str(g.get("id")) in selected_set
    )


def run(state: M2SubGraphState) -> dict:
    synthesis = state.get("research_state_draft", "")
    selected_gaps = _format_gaps(
        state.get("candidate_gaps") or [],
        state.get("selected_gap_ids") or [],
    )
    refs = _format_references(state.get("verified_refs") or [])

    user_prompt = (
        f"{_STYLE}\n\n{_PROMPT}\n\n"
        f"Topic: {state.get('research_title')}\n"
        f"Research type: {state.get('research_type')}\n"
        f"Language: {state.get('language')}\n\n"
        f"Phase 2 synthesis:\n{synthesis}\n\n"
        f"Confirmed research gaps:\n{selected_gaps}\n\n"
        f"Verified references:\n{refs}"
    )
    draft = _get_llm().invoke(user_prompt).content

    return {
        "ch2_draft": draft,
        "citation_list": state.get("research_state_citations") or [],
        "current_phase": "DONE",
        "messages": [AIMessage(content="Chapter 2 drafted.")],
    }
```

- [ ] **Step 5: Run — should pass**

Run: `python -m pytest orchestrator/tests/agents/m2/test_phase5_output_gen.py -v`
Expected: 2 PASS.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/prompts/m2/5_output_gen.md \
        orchestrator/agents/m2/phases/phase5_output_gen.py \
        orchestrator/tests/agents/m2/test_phase5_output_gen.py
git commit -m "feat(orchestrator): M2 Phase 5 — Output_Gen (single-shot Chapter 2 draft)"
```

---

## Phase D — Wire-up

### Task 15: Sub-graph conditional edges + self-loops

**Files:**
- Modify: `orchestrator/agents/m2/graph.py`
- Create: `orchestrator/tests/agents/m2/test_m2_subgraph_edges.py`

Phase nodes now return `current_phase` patches. The sub-graph's edges must respect those: when `phase2.run()` returns `{"current_phase": "research_state"}` it means "self-loop"; when it returns `{"current_phase": "gap_analysis"}` it means "advance".

- [ ] **Step 1: Tests**

Create `orchestrator/tests/agents/m2/test_m2_subgraph_edges.py`:

```python
"""Tests that the sub-graph respects phase transitions and self-loops."""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from orchestrator.agents.m2.graph import build_m2_subgraph
from orchestrator.agents.m2.state import fresh_state


def _stub_all_phases_to_advance(monkeypatch):
    """Make all 5 phases unconditionally advance. Used as the baseline."""
    from orchestrator.agents.m2.phases import (
        phase1_familiarize, phase2_research_state, phase3_gap_analysis,
        phase4_reference_confirm, phase5_output_gen,
    )
    monkeypatch.setattr(phase1_familiarize, "run", lambda s: {"current_phase": "research_state"})
    monkeypatch.setattr(phase2_research_state, "run", lambda s: {"current_phase": "gap_analysis"})
    monkeypatch.setattr(phase3_gap_analysis, "run", lambda s: {"current_phase": "reference_confirm"})
    monkeypatch.setattr(phase4_reference_confirm, "run", lambda s: {"current_phase": "output_gen"})
    monkeypatch.setattr(phase5_output_gen, "run", lambda s: {"current_phase": "DONE"})


def test_subgraph_walks_linearly_when_all_advance(monkeypatch):
    _stub_all_phases_to_advance(monkeypatch)
    g = build_m2_subgraph(interactive=False, checkpointer=MemorySaver())
    s = fresh_state(project_id="p", thread_id="t", research_title="X",
                    research_type="quantitative", language="en",
                    paper_uris=[], mode="auto")
    final = g.invoke(s, config={"configurable": {"thread_id": "linear"}})
    assert final["current_phase"] == "DONE"


def test_subgraph_self_loop_when_phase_returns_same_phase(monkeypatch):
    """Phase 2 returns current_phase=research_state once, then advances."""
    from orchestrator.agents.m2.phases import (
        phase1_familiarize, phase2_research_state, phase3_gap_analysis,
        phase4_reference_confirm, phase5_output_gen,
    )

    iteration = {"n": 0}
    def phase2_alternating(s):
        iteration["n"] += 1
        if iteration["n"] == 1:
            return {"current_phase": "research_state",
                    "regeneration_count": {"research_state": 1}}
        return {"current_phase": "gap_analysis"}

    monkeypatch.setattr(phase1_familiarize, "run", lambda s: {"current_phase": "research_state"})
    monkeypatch.setattr(phase2_research_state, "run", phase2_alternating)
    monkeypatch.setattr(phase3_gap_analysis, "run", lambda s: {"current_phase": "reference_confirm"})
    monkeypatch.setattr(phase4_reference_confirm, "run", lambda s: {"current_phase": "output_gen"})
    monkeypatch.setattr(phase5_output_gen, "run", lambda s: {"current_phase": "DONE"})

    g = build_m2_subgraph(interactive=False, checkpointer=MemorySaver())
    s = fresh_state(project_id="p", thread_id="t", research_title="X",
                    research_type="quantitative", language="en",
                    paper_uris=[], mode="auto")
    final = g.invoke(s, config={"configurable": {"thread_id": "selfloop"}})
    assert final["current_phase"] == "DONE"
    assert iteration["n"] == 2  # phase 2 ran twice
```

- [ ] **Step 2: Run — should fail**

Run: `python -m pytest orchestrator/tests/agents/m2/test_m2_subgraph_edges.py -v`
Expected: FAIL (current graph uses unconditional edges).

- [ ] **Step 3: Replace graph with conditional edges**

Replace `orchestrator/agents/m2/graph.py`:

```python
"""M2 sub-graph builder — conditional edges support self-loops + jump-back."""
from __future__ import annotations

import os
from functools import lru_cache

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from orchestrator.agents.m2.state import M2SubGraphState, PhaseKey


_PHASE_TO_NODE_NAME: dict[PhaseKey, str] = {
    "familiarize": "m2_familiarize",
    "research_state": "m2_research_state",
    "gap_analysis": "m2_gap_analysis",
    "reference_confirm": "m2_reference_confirm",
    "output_gen": "m2_output_gen",
    "DONE": "END",
}


def _route_to_next(state: M2SubGraphState) -> str:
    """Read current_phase, return the matching node name (or END)."""
    phase = state.get("current_phase", "familiarize")
    if phase == "DONE":
        return "END"
    return _PHASE_TO_NODE_NAME.get(phase, "m2_familiarize")


def build_m2_subgraph(*, interactive: bool, checkpointer: BaseCheckpointSaver):
    """Compile the M2 sub-graph.

    Each phase node returns a state patch including current_phase. The
    conditional edges read that and route accordingly — supporting:
    - advance (next phase)
    - self-loop (same phase)
    - jump-back (earlier phase)
    """
    from orchestrator.agents.m2.phases import (
        phase1_familiarize, phase2_research_state, phase3_gap_analysis,
        phase4_reference_confirm, phase5_output_gen,
    )

    builder = StateGraph(M2SubGraphState)
    builder.add_node("m2_familiarize", phase1_familiarize.run)
    builder.add_node("m2_research_state", phase2_research_state.run)
    builder.add_node("m2_gap_analysis", phase3_gap_analysis.run)
    builder.add_node("m2_reference_confirm", phase4_reference_confirm.run)
    builder.add_node("m2_output_gen", phase5_output_gen.run)

    # Entry: route based on the seeded current_phase (supports mid-graph resume)
    builder.add_conditional_edges(START, _route_to_next, {
        "m2_familiarize": "m2_familiarize",
        "m2_research_state": "m2_research_state",
        "m2_gap_analysis": "m2_gap_analysis",
        "m2_reference_confirm": "m2_reference_confirm",
        "m2_output_gen": "m2_output_gen",
        "END": END,
    })

    # After every phase, re-route based on the updated current_phase.
    for node in ["m2_familiarize", "m2_research_state", "m2_gap_analysis",
                 "m2_reference_confirm", "m2_output_gen"]:
        builder.add_conditional_edges(node, _route_to_next, {
            "m2_familiarize": "m2_familiarize",
            "m2_research_state": "m2_research_state",
            "m2_gap_analysis": "m2_gap_analysis",
            "m2_reference_confirm": "m2_reference_confirm",
            "m2_output_gen": "m2_output_gen",
            "END": END,
        })

    interrupt_before = [] if not interactive else [
        "m2_familiarize", "m2_research_state", "m2_gap_analysis",
        "m2_reference_confirm", "m2_output_gen",
    ]
    return builder.compile(checkpointer=checkpointer, interrupt_before=interrupt_before)


@lru_cache(maxsize=2)
def get_m2_graph(interactive: bool = True):
    """Cached singleton — uses the same PostgresSaver as the outer graph."""
    from orchestrator.graph import _get_pool
    from langgraph.checkpoint.postgres import PostgresSaver
    saver = PostgresSaver(_get_pool())
    saver.setup()
    return build_m2_subgraph(interactive=interactive, checkpointer=saver)
```

- [ ] **Step 4: Run — should pass**

Run: `python -m pytest orchestrator/tests/agents/m2/test_m2_subgraph_edges.py orchestrator/tests/agents/m2/test_state.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/agents/m2/graph.py \
        orchestrator/tests/agents/m2/test_m2_subgraph_edges.py
git commit -m "feat(orchestrator): M2 sub-graph conditional edges (self-loop + jump-back)"
```

---

### Task 16: M2Agent wrapper

**Files:**
- Create: `orchestrator/agents/m2/agent.py`
- Create: `orchestrator/tests/agents/m2/test_m2_agent_wrapper.py`

- [ ] **Step 1: Tests**

Create `orchestrator/tests/agents/m2/test_m2_agent_wrapper.py`:

```python
"""Tests for M2Agent wrapper — outer-state → sub-graph → context_store output."""
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

from orchestrator.agents.m2 import M2Agent
from orchestrator.state import ContextStore


def _outer_state(mode="auto"):
    return {
        "project_id": "00000000-0000-0000-0000-000000000001",
        "thread_id": "00000000-0000-0000-0000-000000000002",
        "messages": [HumanMessage(content="lit review please")],
        "current_module": "M2",
        "context_store": ContextStore(
            m1_topic={"research_title": "TL→EE", "research_type": "quantitative",
                      "language": "en", "confirmed_at": "2026-05-26"},
        ),
        "mode": mode,
    }


def test_m2_agent_runs_sub_graph_to_done(monkeypatch):
    """Stub the sub-graph to return a DONE final state; wrapper should flatten and transition."""
    fake_subgraph = MagicMock()
    fake_subgraph.invoke.return_value = {
        "current_phase": "DONE",
        "research_state_draft": "synthesis",
        "candidate_gaps": [{"id": "1", "description": "g1", "supporting_papers": []}],
        "selected_gap_ids": ["1"],
        "verified_refs": [],
        "ch2_draft": "Chapter 2 text",
        "citation_list": [{"author": "X", "year": 2024}],
        "research_type": "quantitative",
    }
    monkeypatch.setattr(
        "orchestrator.agents.m2.agent.get_m2_graph", lambda interactive: fake_subgraph
    )
    monkeypatch.setattr(
        "orchestrator.agents.m2.agent._open_db_session",
        lambda: _FakeDbSession(),
    )

    agent = M2Agent()
    result = agent.step(_outer_state())
    assert result.transition is True
    patch_dict = result.context_patch
    assert patch_dict["literature_review_doc"] == "Chapter 2 text"
    assert patch_dict["research_state_summary"] == "synthesis"
    assert "confirmed_at" in patch_dict


def test_m2_agent_partial_state_does_not_transition(monkeypatch):
    """Sub-graph paused at a phase interrupt — wrapper returns transition=False."""
    fake_subgraph = MagicMock()
    fake_subgraph.invoke.return_value = {
        "current_phase": "research_state",
        "research_state_draft": "partial",
        "messages": [HumanMessage(content="What's your topic?")],
    }
    monkeypatch.setattr(
        "orchestrator.agents.m2.agent.get_m2_graph", lambda interactive: fake_subgraph
    )
    monkeypatch.setattr(
        "orchestrator.agents.m2.agent._open_db_session",
        lambda: _FakeDbSession(),
    )

    agent = M2Agent()
    result = agent.step(_outer_state(mode="interactive"))
    assert result.transition is False
    assert result.needs_user_reply is True


class _FakeDbSession:
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def query(self, *a, **kw):
        m = MagicMock()
        m.filter_by.return_value.all.return_value = []
        return m
```

- [ ] **Step 2: Run — should fail**

Run: `python -m pytest orchestrator/tests/agents/m2/test_m2_agent_wrapper.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement wrapper**

Create `orchestrator/agents/m2/agent.py`:

```python
"""M2Agent — outer-graph wrapper that delegates to the M2 sub-graph."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any

from orchestrator.agents.base import ModuleAgent, ModuleStepResult
from orchestrator.agents.m2.graph import get_m2_graph
from orchestrator.agents.m2.translation import _flatten_to_m2_output, _seed_from_outer
from orchestrator.schemas.m2 import M2Output
from orchestrator.tools.m2_literature import (
    compile_citations, find_research_gaps, scout_citations,
    summarize_paper, verify_page_numbers,
)

_PROMPT = (
    "M2 Literature Review wrapper. Routes the user through a 5-phase "
    "chat-first conversation (familiarize → research state → gap analysis "
    "→ reference confirm → output generation)."
)


@contextmanager
def _open_db_session():
    """Indirection so tests can monkeypatch the DB session getter."""
    from app.db import get_session_factory
    sf = get_session_factory()
    with sf() as db:
        yield db


class M2Agent(ModuleAgent):
    schema = M2Output
    module_key = "M2"
    system_prompt = _PROMPT
    tools = [scout_citations, summarize_paper, find_research_gaps,
             compile_citations, verify_page_numbers]

    def step(self, state) -> ModuleStepResult:
        # 1. Seed sub-graph state from outer.
        with _open_db_session() as db:
            sub_state = _seed_from_outer(state, db)

        # 2. Invoke sub-graph with namespaced thread_id.
        is_interactive = state.get("mode", "interactive") == "interactive"
        sub_graph = get_m2_graph(interactive=is_interactive)
        config = {"configurable": {"thread_id": f"{state['thread_id']}::m2"}}
        final = sub_graph.invoke(sub_state, config=config)

        # 3. Sub-graph DONE → return transition.
        if final.get("current_phase") == "DONE":
            return ModuleStepResult(
                assistant_message=(
                    f"M2 complete — {len(final.get('citation_list', []))} citations, "
                    f"draft of Chapter 2 ready."
                ),
                context_patch=_flatten_to_m2_output(final),
                transition=True,
            )

        # 4. Sub-graph paused — forward the latest assistant message upstream.
        msgs = final.get("messages") or []
        latest = msgs[-1].content if msgs else ""
        return ModuleStepResult(
            assistant_message=latest,
            context_patch=_flatten_to_m2_output(final),
            transition=False,
            needs_user_reply=True,
        )
```

Update `orchestrator/agents/m2/__init__.py`:

```python
"""M2 Literature Review chat-first sub-graph."""
from orchestrator.agents.m2.agent import M2Agent

__all__ = ["M2Agent"]
```

- [ ] **Step 4: Run — should pass**

Run: `python -m pytest orchestrator/tests/agents/m2/test_m2_agent_wrapper.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/agents/m2/agent.py orchestrator/agents/m2/__init__.py \
        orchestrator/tests/agents/m2/test_m2_agent_wrapper.py
git commit -m "feat(orchestrator): M2Agent wrapper that delegates to sub-graph"
```

---

### Task 17: Outer-graph import swap + delete old files

**Files:**
- Modify: `orchestrator/graph.py`
- Delete: `orchestrator/agents/m2_literature.py`
- Delete: `orchestrator/prompts/m2.md`
- Delete: `orchestrator/tests/test_agents_m2.py`

- [ ] **Step 1: Update the import**

Edit `orchestrator/graph.py`. Change:

```diff
-from orchestrator.agents.m2_literature import M2Agent
+from orchestrator.agents.m2 import M2Agent
```

- [ ] **Step 2: Delete the old files**

```bash
cd /Users/caonguyenvan/project/dothesis
rm orchestrator/agents/m2_literature.py
rm orchestrator/prompts/m2.md
rm orchestrator/tests/test_agents_m2.py
```

- [ ] **Step 3: Re-install + run regression checks**

```bash
source api/.venv/bin/activate
pip install -e orchestrator --quiet
python -m pytest orchestrator/tests/ -m "not integration" -q --no-header 2>&1 | tail -5
```

Expected: all previously-passing tests still pass; no ImportError.

- [ ] **Step 4: Commit**

```bash
git add orchestrator/graph.py
git rm orchestrator/agents/m2_literature.py orchestrator/prompts/m2.md \
       orchestrator/tests/test_agents_m2.py
git commit -m "refactor(orchestrator): wire M2 wrapper into outer graph; delete legacy files"
```

---

## Phase E — Integration tests

### Task 18: Sub-graph full auto-mode e2e

**Files:**
- Create: `orchestrator/tests/agents/m2/test_m2_subgraph_auto_e2e.py`

- [ ] **Step 1: Test**

Create `orchestrator/tests/agents/m2/test_m2_subgraph_auto_e2e.py`:

```python
"""Sub-graph auto-mode end-to-end — all 5 phases run, produces ch2_draft + citations."""
from unittest.mock import MagicMock

import pytest
from langgraph.checkpoint.memory import MemorySaver

from orchestrator.agents.m2.graph import build_m2_subgraph
from orchestrator.agents.m2.state import fresh_state


pytestmark = pytest.mark.integration


def _stub_llms_and_tools(monkeypatch):
    """Stub every LLM call + the scout tool so the test stays offline."""
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = (
        '[{"id":"1","description":"No SME context","relevance":"High",'
        '"supporting_papers":[{"author":"Wang","year":2011,"page":118}]}]'
    )
    from orchestrator.agents.m2.phases import (
        phase2_research_state, phase3_gap_analysis, phase4_reference_confirm,
        phase5_output_gen,
    )
    monkeypatch.setattr(phase2_research_state, "_scout",
                        lambda *a, **kw: [{"title": "P1", "authors": "Wang",
                                            "year": 2011, "source": "J", "url": None}])
    monkeypatch.setattr(phase2_research_state, "_get_llm",
                        lambda: _llm_for("Synthesis with (Wang, 2011)."))
    monkeypatch.setattr(phase3_gap_analysis, "_get_llm",
                        lambda: _llm_for(
                            '[{"id":"1","description":"No SME context","relevance":"High",'
                            '"supporting_papers":[{"author":"Wang","year":2011,"page":118}]}]'
                        ))
    monkeypatch.setattr(phase4_reference_confirm, "_get_llm", lambda: MagicMock())
    monkeypatch.setattr(phase5_output_gen, "_get_llm",
                        lambda: _llm_for("Chapter 2 draft text."))


def _llm_for(content: str):
    m = MagicMock()
    m.invoke.return_value.content = content
    return m


def test_subgraph_auto_runs_to_done_with_artifacts(monkeypatch):
    _stub_llms_and_tools(monkeypatch)

    g = build_m2_subgraph(interactive=False, checkpointer=MemorySaver())
    s = fresh_state(
        project_id="p", thread_id="t",
        research_title="TL on EE", research_type="quantitative",
        language="en", paper_uris=[], mode="auto",
    )
    final = g.invoke(s, config={"configurable": {"thread_id": "auto-e2e"}})

    assert final["current_phase"] == "DONE"
    assert final["research_state_draft"] and "Wang" in final["research_state_draft"]
    assert final["selected_gap_ids"] == ["1"]
    assert final["ch2_draft"]
```

- [ ] **Step 2: Run — should pass**

Run: `cd /Users/caonguyenvan/project/dothesis && source api/.venv/bin/activate && python -m pytest orchestrator/tests/agents/m2/test_m2_subgraph_auto_e2e.py -m integration -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add orchestrator/tests/agents/m2/test_m2_subgraph_auto_e2e.py
git commit -m "test(orchestrator): M2 sub-graph auto-mode e2e integration"
```

---

### Task 19: Sub-graph interactive with regen

**Files:**
- Create: `orchestrator/tests/agents/m2/test_m2_subgraph_interactive_e2e.py`

- [ ] **Step 1: Test**

Create `orchestrator/tests/agents/m2/test_m2_subgraph_interactive_e2e.py`:

```python
"""Interactive walk through Phase 2 + Phase 3 with one regen each."""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from orchestrator.agents.m2.graph import build_m2_subgraph
from orchestrator.agents.m2.state import fresh_state


pytestmark = pytest.mark.integration


def _setup_stubs(monkeypatch):
    from orchestrator.agents.m2.phases import (
        phase2_research_state, phase3_gap_analysis, phase4_reference_confirm,
        phase5_output_gen,
    )
    monkeypatch.setattr(phase2_research_state, "_scout", lambda *a, **kw: [])

    synth_counter = {"n": 0}
    def synth_llm():
        m = MagicMock()
        def invoke(prompt):
            synth_counter["n"] += 1
            msg = MagicMock()
            msg.content = (f"Synthesis v{synth_counter['n']}")
            return msg
        m.invoke = invoke
        return m
    monkeypatch.setattr(phase2_research_state, "_get_llm", synth_llm)

    gap_counter = {"n": 0}
    def gap_llm():
        m = MagicMock()
        def invoke(prompt):
            gap_counter["n"] += 1
            msg = MagicMock()
            msg.content = '[{"id":"1","description":"gap v' + str(gap_counter["n"]) + '","relevance":"High","supporting_papers":[]}]'
            return msg
        m.invoke = invoke
        return m
    monkeypatch.setattr(phase3_gap_analysis, "_get_llm", gap_llm)

    monkeypatch.setattr(phase4_reference_confirm, "_get_llm", lambda: MagicMock())
    monkeypatch.setattr(phase4_reference_confirm, "_auto_verify",
                        lambda paper_uris, refs: refs)
    final_llm = MagicMock()
    final_llm.invoke.return_value.content = "Chapter 2 final."
    monkeypatch.setattr(phase5_output_gen, "_get_llm", lambda: final_llm)


def test_phase2_refines_once_then_confirms(monkeypatch):
    _setup_stubs(monkeypatch)
    g = build_m2_subgraph(interactive=True, checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "p2-refine"}}

    s = fresh_state(project_id="p", thread_id="t", research_title="X",
                    research_type="quantitative", language="en",
                    paper_uris=[], mode="interactive")
    s["current_phase"] = "research_state"  # jump straight to phase 2

    # 1) Initial invoke — produces draft v1, interrupts.
    g.invoke(s, config=config)
    snapshot = g.get_state(config)
    assert snapshot.values["research_state_draft"] == "Synthesis v1"

    # 2) User says "redo focus on SDT" — feed it back to the same thread.
    from langgraph.types import Command
    g.invoke(Command(update={
        "messages": [HumanMessage(content="redo focus on SDT")],
    }), config=config)
    snapshot = g.get_state(config)
    assert snapshot.values["research_state_draft"] == "Synthesis v2"
    assert snapshot.values["regeneration_count"]["research_state"] == 1

    # 3) User confirms — should advance to gap_analysis.
    g.invoke(Command(update={
        "messages": [HumanMessage(content="confirm")],
    }), config=config)
    snapshot = g.get_state(config)
    assert snapshot.values["research_state_confirmed"] is True
    assert snapshot.values["current_phase"] == "gap_analysis"
```

- [ ] **Step 2: Run**

Run: `cd /Users/caonguyenvan/project/dothesis && source api/.venv/bin/activate && python -m pytest orchestrator/tests/agents/m2/test_m2_subgraph_interactive_e2e.py -m integration -v`
Expected: PASS.

> **Note:** If `langgraph.types.Command` isn't importable in your version of LangGraph (it's the 1.x resume API), substitute with `graph.update_state(config, {"messages": [...]})` followed by another `invoke({}, config=config)`. The integration test exists to catch API drift.

- [ ] **Step 3: Commit**

```bash
git add orchestrator/tests/agents/m2/test_m2_subgraph_interactive_e2e.py
git commit -m "test(orchestrator): M2 sub-graph interactive regen integration"
```

---

### Task 20: Regen cap integration test

**Files:**
- Append: `orchestrator/tests/agents/m2/test_m2_subgraph_interactive_e2e.py`

- [ ] **Step 1: Append the test**

Append to `orchestrator/tests/agents/m2/test_m2_subgraph_interactive_e2e.py`:

```python
def test_phase2_regen_cap_blocks_6th_iteration(monkeypatch):
    _setup_stubs(monkeypatch)
    g = build_m2_subgraph(interactive=True, checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "p2-cap"}}

    s = fresh_state(project_id="p", thread_id="t", research_title="X",
                    research_type="quantitative", language="en",
                    paper_uris=[], mode="interactive")
    s["current_phase"] = "research_state"
    s["research_state_draft"] = "old synthesis"
    s["regeneration_count"] = {"research_state": 5}
    g.invoke(s, config=config)

    from langgraph.types import Command
    g.invoke(Command(update={
        "messages": [HumanMessage(content="redo one more time")],
    }), config=config)
    snapshot = g.get_state(config)
    # Draft unchanged — cap hit
    assert snapshot.values["research_state_draft"] == "old synthesis"
    # Cap message in chat
    last_msg = snapshot.values["messages"][-1]
    assert "lock" in last_msg.content.lower() or "5" in last_msg.content
```

- [ ] **Step 2: Run + commit**

```bash
python -m pytest orchestrator/tests/agents/m2/test_m2_subgraph_interactive_e2e.py::test_phase2_regen_cap_blocks_6th_iteration -m integration -v
git add orchestrator/tests/agents/m2/test_m2_subgraph_interactive_e2e.py
git commit -m "test(orchestrator): M2 Phase 2 regen cap blocks 6th iteration"
```

---

### Task 21: Navigate-back integration test

**Files:**
- Append: `orchestrator/tests/agents/m2/test_m2_subgraph_interactive_e2e.py`

- [ ] **Step 1: Append**

Append to `orchestrator/tests/agents/m2/test_m2_subgraph_interactive_e2e.py`:

```python
def test_navigate_back_from_gap_analysis_to_research_state(monkeypatch):
    _setup_stubs(monkeypatch)
    g = build_m2_subgraph(interactive=True, checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "p3-nav"}}

    s = fresh_state(project_id="p", thread_id="t", research_title="X",
                    research_type="quantitative", language="en",
                    paper_uris=[], mode="interactive")
    s["current_phase"] = "gap_analysis"
    s["research_state_draft"] = "synthesis"
    s["candidate_gaps"] = [{"id": "1", "description": "g1"}]
    g.invoke(s, config=config)

    from langgraph.types import Command
    g.invoke(Command(update={
        "messages": [HumanMessage(content="go back to research state")],
    }), config=config)
    snapshot = g.get_state(config)
    assert snapshot.values["current_phase"] == "research_state"
```

- [ ] **Step 2: Run + commit**

```bash
python -m pytest orchestrator/tests/agents/m2/test_m2_subgraph_interactive_e2e.py::test_navigate_back_from_gap_analysis_to_research_state -m integration -v
git add orchestrator/tests/agents/m2/test_m2_subgraph_interactive_e2e.py
git commit -m "test(orchestrator): M2 navigation back from gap_analysis to research_state"
```

---

### Task 22: Upload → M2 auto-mode e2e

**Files:**
- Create: `orchestrator/tests/integration/test_m2_e2e_upload.py`

- [ ] **Step 1: Test**

Create `orchestrator/tests/integration/test_m2_e2e_upload.py`:

```python
"""Upload a PDF, then run M2 auto-mode — assert the upload is surfaced and
auto-verification mentions it.
"""
import io
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import User
from app.security import create_session


pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).parent.parent.parent.parent / "api" / "tests" / "fixtures" / "sample.pdf"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "true")
    monkeypatch.setattr("app.routers.uploads.s3_from_env",
                        lambda: _FakeS3())
    return TestClient(create_app())


class _FakeS3:
    """In-memory stand-in for boto3 S3 client."""
    _store: dict = {}
    def put_object(self, Bucket, Key, Body, ContentType):
        self._store[f"{Bucket}/{Key}"] = Body if isinstance(Body, bytes) else Body.encode()
    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self._store[f"{Bucket}/{Key}"])}


def _login(client) -> uuid.UUID:
    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"u{uuid.uuid4().hex[:6]}@x",
                 username=f"u{uuid.uuid4().hex[:6]}",
                 password_hash="x", email_verified=True)
        db.add(u); db.commit()
        client.cookies.set("dothesis_session", create_session(db, u))
        return u.id


def test_upload_then_m2_seed_includes_paper_uris(client, monkeypatch):
    _login(client)
    pid = client.post("/api/v1/projects", json={"name": "T"}).json()["id"]

    with FIXTURE.open("rb") as f:
        r = client.post(
            f"/api/v1/projects/{pid}/uploads",
            files={"file": ("smith2024.pdf", f, "application/pdf")},
        )
    assert r.status_code == 200

    # Now invoke M2Agent directly to verify _seed_from_outer picks up the upload.
    from orchestrator.agents.m2.translation import _seed_from_outer
    from orchestrator.state import ContextStore

    outer_state = {
        "project_id": uuid.UUID(pid),
        "thread_id": uuid.uuid4(),
        "messages": [],
        "current_module": "M2",
        "context_store": ContextStore(
            m1_topic={"research_title": "X", "research_type": "quantitative",
                      "language": "en", "confirmed_at": "2026-05-26"},
        ),
        "mode": "auto",
    }
    sf = get_session_factory()
    with sf() as db:
        sub = _seed_from_outer(outer_state, db)
    assert len(sub["paper_uris"]) == 1
    assert sub["paper_uris"][0].endswith("smith2024.pdf")
```

- [ ] **Step 2: Run + commit**

```bash
python -m pytest orchestrator/tests/integration/test_m2_e2e_upload.py -m integration -v
git add orchestrator/tests/integration/test_m2_e2e_upload.py
git commit -m "test(orchestrator): integration — upload populates paper_uris in M2 seed"
```

---

### Task 23: Bilingual smoke

**Files:**
- Create: `orchestrator/tests/integration/test_m2_bilingual.py`

- [ ] **Step 1: Test**

Create `orchestrator/tests/integration/test_m2_bilingual.py`:

```python
"""Bilingual smoke — when language='vi', the synthesis LLM is invoked with vi context."""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage

from orchestrator.agents.m2.phases import phase2_research_state
from orchestrator.agents.m2.state import fresh_state


pytestmark = pytest.mark.integration


def test_vi_language_passed_into_phase2_prompt(monkeypatch):
    captured = {}
    def fake_llm():
        m = MagicMock()
        def invoke(prompt):
            captured["prompt"] = prompt
            msg = MagicMock()
            msg.content = "Tổng hợp tiếng Việt."
            return msg
        m.invoke = invoke
        return m
    monkeypatch.setattr(phase2_research_state, "_scout", lambda *a, **kw: [])
    monkeypatch.setattr(phase2_research_state, "_get_llm", fake_llm)

    s = fresh_state(
        project_id="p", thread_id="t", research_title="TL→EE",
        research_type="quantitative", language="vi",
        paper_uris=[], mode="auto",
    )
    s["messages"] = [HumanMessage(content="start")]
    patch = phase2_research_state.run(s)
    assert "vi" in captured["prompt"]
    assert "Tiếng Việt" in patch["research_state_draft"] or "Việt" in patch["research_state_draft"]
```

- [ ] **Step 2: Run + commit**

```bash
python -m pytest orchestrator/tests/integration/test_m2_bilingual.py -m integration -v
git add orchestrator/tests/integration/test_m2_bilingual.py
git commit -m "test(orchestrator): bilingual smoke — vi language threads into Phase 2 prompt"
```

---

### Task 24: Regression — sub-project 1 tests still pass

**Files:**
- (No new files; this is a verification task)

- [ ] **Step 1: Run full orchestrator suite**

```bash
cd /Users/caonguyenvan/project/dothesis && source api/.venv/bin/activate
python -m pytest orchestrator/tests/ -m "integration or not integration" -q --no-header 2>&1 | tail -5
```

Expected: ALL pass (sub-project 1 tests + sub-project 2 tests). Count should be roughly 68 (from sub-project 1) + ~50 new = ~118 passing.

- [ ] **Step 2: Run full api suite (excluding pre-existing baseline failures)**

```bash
cd /Users/caonguyenvan/project/dothesis/api && source .venv/bin/activate
python -m pytest tests/ -q --no-header 2>&1 | tail -3
```

Expected: At least all the new chat/runs/uploads tests pass. Pre-existing `users.username NOT NULL` baseline failures remain (53 broken from sub-project 1's `.baseline_failures_2026-05-26.txt`). No NEW failures from sub-project 2's changes.

- [ ] **Step 3: Compare counts**

```bash
diff <(cat .baseline_failures_2026-05-26.txt | sort) <(cd api && source .venv/bin/activate && python -m pytest tests/ --no-header -q 2>&1 | grep -E "^(FAILED|ERROR)" | sort) | head -20
```

Expected: empty diff or only NEW additions that you intentionally introduced (e.g. uploads tests if they hit a pre-existing fixture issue).

If new failures appear that aren't in the baseline, **STOP** and investigate. Sub-project 2 must not regress sub-project 1.

- [ ] **Step 4: Update roadmap and final commit**

Edit `docs/superpowers/2026-05-26-platform-pivot-roadmap.md`:
- Flip sub-project 2 status from ⬜ to ✅
- Append a status log entry: `| 2026-05-27 | 2 | ⬜ → ✅ | M2 chat-first redesign + PDF upload shipped on feat/m2-chat-first; X tests passing |`

```bash
cd /Users/caonguyenvan/project/dothesis
git add docs/superpowers/2026-05-26-platform-pivot-roadmap.md
git commit -m "docs(roadmap): sub-project 2 shipped (M2 chat-first + PDF uploads)"
```

---

## Done criteria checklist

- [ ] All 24 tasks committed in order
- [ ] Sub-project 1 tests (68) still passing
- [ ] New sub-project 2 tests (~50) passing
- [ ] Migration up/down/up clean on fresh DB
- [ ] Upload + extraction working end-to-end with `moto[s3]`
- [ ] M2 sub-graph compiles in both interactive and auto modes
- [ ] Phase 2 regen cap blocks at 5 iterations
- [ ] Phase 4 auto-verify against extracted PDF text works for matched references
- [ ] Navigate-back from any phase routes correctly
- [ ] Bilingual smoke (vi) passes
- [ ] No regressions in `engine/` tests
- [ ] Roadmap flipped to ✅

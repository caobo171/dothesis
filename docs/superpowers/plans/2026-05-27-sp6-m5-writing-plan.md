> **📜 Historical record — superseded.** This document captured a plan / spec / design at a point in time and is kept for history. It does **not** describe the current system. For the live DoThesis method and architecture see `README.md`, `AGENTS.md`, `docs/ARCHITECTURE.md`, and `docs/PIPELINE.md`.

# SP6 — M5 Writing & Finalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make M5 batch-compose all 6 chapters via paradigm-aware LLM prompts, emit each as its own AIMessage via SP5's `extra_messages`, handle NL keyword rewrites + auto-export on confirm. S3 upload is mandatory for both interactive and auto-mode paths; a new download endpoint resolves s3_keys to 5-minute signed URLs via 302 redirect.

**Architecture:** Single `M5Agent` extends SP3/SP4/SP5 ModuleAgent. `step()` checks `_compose_chapters_done` directly (no field walk); first turn enters compose phase, batches all chapter compositions, emits per-chapter AIMessages + bibliography + summary via `extra_messages`, sets `_awaiting_confirm=True`. Next turn either confirms (→ S3 export + transition) or rewrites (`rewrite_chapter` LLM tool → update partial.chapters[name] → emit new bubble → stay in confirm).

**Tech Stack:** Python 3.10+, Pydantic v2, FastAPI, LangChain 1.x, LangGraph 1.2+, boto3, React 19, Vitest 2.

**Spec:** `docs/superpowers/specs/2026-05-27-sp6-m5-writing-design.md`
**Depends on:** Sub-projects 1, 2, 3, 4, 5, 7 (all on master).

---

## File map

### NEW backend files

```
orchestrator/prompts/m5/intro.md
orchestrator/prompts/m5/lit_review.md
orchestrator/prompts/m5/methodology.md
orchestrator/prompts/m5/results.md
orchestrator/prompts/m5/discussion.md
orchestrator/prompts/m5/conclusion.md
orchestrator/tests/agents/test_m5_compose.py
orchestrator/tests/agents/test_m5_rewrite.py
orchestrator/tests/agents/test_m5_finalize.py
orchestrator/tests/agents/test_m5_context_slice.py
api/app/routers/exports.py
api/tests/test_exports.py
api/tests/test_m5_round_trip.py
```

### MODIFIED backend files

```
orchestrator/agents/m5_writing.py
orchestrator/schemas/m5.py
orchestrator/tools/m5_writing.py
orchestrator/prompts/m5.md
orchestrator/__main__.py
orchestrator/tests/test_schemas.py
orchestrator/tests/test_tools_m5.py
orchestrator/tests/test_agents_m5.py
orchestrator/tests/test_subprocess.py
api/app/main.py
dev.sh
```

### MODIFIED frontend files

```
(none in V1 — chapters render as markdown bubbles in existing MessageBubble)
```

### MODIFIED docs

```
docs/superpowers/2026-05-26-platform-pivot-roadmap.md
```

---

## Task index (19 tasks)

| Phase | Tasks |
|---|---|
| A. Schema | 1. `ChapterDraft` + `ExportArtifact` (s3_key + download_url) + `M5Output.@model_validator` |
| B. Tools | 2. `_upload_to_s3` helper + `s3_from_env` factory · 3. `compile_pdf` / `export_docx` S3 + project_id · 4. `validate_citations` helper · 5. `compile_bibliography` tool |
| C. Prompts | 6. 6 chapter prompt files (intro, lit_review, methodology, results, discussion, conclusion) |
| D. Compose + Rewrite tools | 7. `compose_chapter` tool · 8. `rewrite_chapter` tool |
| E. Agent | 9. `_extract_context_slice` + `_collect_references` + small helpers · 10. `_compose_all_chapters` + emission · 11. `_is_rewrite_request` + `_identify_chapter` + `_handle_rewrite` · 12. `_finalize_and_export` |
| F. Prompt + Subprocess | 13. M5 system prompt rewrite · 14. Subprocess AWS_S3_BUCKET check + dev.sh note |
| G. API | 15. `/api/v1/projects/{id}/exports/{filename}` endpoint + mount + tests |
| H. Wrap-up | 16. `test_m5_round_trip.py` contract test · 17. Update existing auto-mode test for new schema · 18. Frontend integration test (optional) · 19. Regression + roadmap flip |

---

## Phase A — Schema

### Task 1: `ChapterDraft` + `ExportArtifact` + `M5Output` validator

**Files:**
- Modify: `orchestrator/schemas/m5.py`
- Modify: `orchestrator/tests/test_schemas.py`

- [ ] **Step 1: Append the failing tests**

Append to `orchestrator/tests/test_schemas.py`:

```python
def test_chapter_draft_minimal():
    from orchestrator.schemas.m5 import ChapterDraft
    cd = ChapterDraft(name="intro", prose="# Introduction\n...")
    assert cd.name == "intro"
    assert cd.prose.startswith("# Introduction")
    assert cd.citations_used == []
    assert cd.uncited_warnings == []


def test_chapter_draft_with_citations():
    from orchestrator.schemas.m5 import ChapterDraft
    cd = ChapterDraft(
        name="lit_review", prose="...",
        citations_used=["Bass, 1990", "Avolio et al., 2009"],
        uncited_warnings=["Smith, 2023"],
    )
    blob = cd.model_dump()
    assert blob["citations_used"][0] == "Bass, 1990"
    assert blob["uncited_warnings"] == ["Smith, 2023"]


def test_export_artifact_new_shape():
    from orchestrator.schemas.m5 import ExportArtifact
    a = ExportArtifact(
        kind="docx",
        s3_key="projects/abc/exports/thesis-X.docx",
        download_url="/api/v1/projects/abc/exports/thesis-X.docx",
        size_bytes=12345,
    )
    assert a.s3_key.startswith("projects/")
    assert a.download_url.startswith("/api/v1/")
    assert a.uri == ""  # deprecated field, default empty


def test_m5_unconfirmed_partial_is_valid_minimal():
    from orchestrator.schemas.m5 import M5Output
    out = M5Output()  # all fields default
    assert out.chapters == {}
    assert out.export_artifacts == []
    assert out.confirmed_at is None


def test_m5_confirm_requires_all_six_chapters():
    from datetime import datetime, timezone
    from pydantic import ValidationError
    from orchestrator.schemas.m5 import M5Output, ExportArtifact
    with pytest.raises(ValidationError) as exc:
        M5Output(
            chapters={"intro": {"name": "intro", "prose": "x"}},
            export_artifacts=[ExportArtifact(
                kind="docx", s3_key="k", download_url="u", size_bytes=1,
            )],
            confirmed_at=datetime.now(timezone.utc),
        )
    assert "missing" in str(exc.value).lower()


def test_m5_confirm_requires_docx_artifact():
    from datetime import datetime, timezone
    from pydantic import ValidationError
    from orchestrator.schemas.m5 import M5Output
    chapters = {n: {"name": n, "prose": "x"}
                for n in ("intro", "lit_review", "methodology",
                          "results", "discussion", "conclusion")}
    with pytest.raises(ValidationError) as exc:
        M5Output(
            chapters=chapters,
            export_artifacts=[],  # no docx
            confirmed_at=datetime.now(timezone.utc),
        )
    assert "docx" in str(exc.value).lower()


def test_m5_confirm_passes_with_six_chapters_and_docx():
    from datetime import datetime, timezone
    from orchestrator.schemas.m5 import M5Output, ExportArtifact
    chapters = {n: {"name": n, "prose": "x"}
                for n in ("intro", "lit_review", "methodology",
                          "results", "discussion", "conclusion")}
    out = M5Output(
        chapters=chapters,
        export_artifacts=[ExportArtifact(
            kind="docx", s3_key="k", download_url="u", size_bytes=1,
        )],
        confirmed_at=datetime.now(timezone.utc),
    )
    assert len(out.chapters) == 6
```

- [ ] **Step 2: Run — should FAIL**

```bash
cd /Users/caonguyenvan/project/dothesis && source api/.venv/bin/activate
python -m pytest orchestrator/tests/test_schemas.py -v 2>&1 | tail -20
```

Expected: FAIL — `ChapterDraft` doesn't exist, `ExportArtifact` has only `uri` field, no `@model_validator` on M5Output.

- [ ] **Step 3: Replace `orchestrator/schemas/m5.py`**

```python
"""M5 Writing & Finalization output schema (SP6 — chapter-by-chapter compose + S3 export)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


ChapterName = Literal["intro", "lit_review", "methodology", "results", "discussion", "conclusion"]


class ChapterDraft(BaseModel):
    """One composed chapter with provenance info."""
    name: ChapterName
    prose: str
    citations_used: list[str] = Field(default_factory=list)
    uncited_warnings: list[str] = Field(default_factory=list)


class ExportArtifact(BaseModel):
    kind: Literal["docx", "pdf", "latex", "md"]
    s3_key: str = ""
    download_url: str = ""
    size_bytes: int = Field(default=0, ge=0)
    # SP1 field — DEPRECATED but kept for back-compat with auto-mode readers
    uri: str = ""


class M5Output(BaseModel):
    chapters: dict[str, dict] = Field(default_factory=dict)
    bibliography: str = ""
    export_artifacts: list[ExportArtifact] = Field(default_factory=list)
    # SP1 — preserved for back-compat with engine-fallback auto-mode
    sections: list[dict] = Field(default_factory=list)
    confirmed_at: datetime | None = None

    @model_validator(mode="after")
    def _require_artifacts_on_confirm(self):
        """When confirmed, the agent must have produced all 6 chapters + at
        least the docx export. Pre-confirm partials remain valid."""
        if self.confirmed_at is None:
            return self
        required = {"intro", "lit_review", "methodology", "results", "discussion", "conclusion"}
        present = set(self.chapters.keys())
        missing = required - present
        if missing:
            raise ValueError(f"M5 confirm requires all 6 chapters; missing: {sorted(missing)}")
        if not any(a.kind == "docx" for a in self.export_artifacts):
            raise ValueError("M5 confirm requires at least the docx export artifact")
        return self
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest orchestrator/tests/test_schemas.py -v 2>&1 | tail -15
git add orchestrator/schemas/m5.py orchestrator/tests/test_schemas.py
git commit -m "feat(orchestrator): ChapterDraft + ExportArtifact (s3_key, download_url) + M5Output validator"
```

Expected: existing schema tests + 7 new = PASS.

---

## Phase B — Tools

### Task 2: `_upload_to_s3` helper + `s3_from_env` factory

**Files:**
- Modify: `orchestrator/tools/m5_writing.py`
- Modify: `orchestrator/tests/test_tools_m5.py`

- [ ] **Step 1: Append the failing tests**

Append to `orchestrator/tests/test_tools_m5.py`:

```python
def test_s3_from_env_returns_boto3_client(monkeypatch):
    """The factory should return a boto3 S3 client built from env vars."""
    from orchestrator.tools.m5_writing import s3_from_env
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY", "fake-key")
    monkeypatch.setenv("AWS_SECRET_KEY", "fake-secret")
    client = s3_from_env()
    # boto3 client is a "S3" service client — has put_object / get_object methods
    assert hasattr(client, "put_object")
    assert hasattr(client, "generate_presigned_url")


def test_upload_to_s3_writes_correct_key_and_deletes_local(tmp_path, monkeypatch):
    """_upload_to_s3 uploads to projects/{id}/exports/{filename} and deletes local file."""
    from orchestrator.tools import m5_writing
    from unittest.mock import MagicMock

    fake_s3 = MagicMock()
    monkeypatch.setattr(m5_writing, "s3_from_env", lambda: fake_s3)
    monkeypatch.setenv("AWS_S3_BUCKET", "test-bucket")

    local = tmp_path / "thesis-abc123.docx"
    local.write_bytes(b"fake docx content")

    s3_key = m5_writing._upload_to_s3(
        str(local), project_id="proj-xyz", kind="docx", filename="thesis-abc123.docx",
    )
    # Returned key has the expected shape
    assert s3_key == "projects/proj-xyz/exports/thesis-abc123.docx"
    # boto3 put_object called with the right bucket + key + content-type
    call = fake_s3.put_object.call_args
    assert call.kwargs["Bucket"] == "test-bucket"
    assert call.kwargs["Key"] == "projects/proj-xyz/exports/thesis-abc123.docx"
    assert call.kwargs["ContentType"].startswith("application/vnd.openxmlformats")
    assert call.kwargs["Body"] == b"fake docx content"
    # Local file deleted after upload
    assert not local.exists()


def test_upload_to_s3_pdf_content_type(tmp_path, monkeypatch):
    """PDF gets the right content type."""
    from orchestrator.tools import m5_writing
    from unittest.mock import MagicMock

    fake_s3 = MagicMock()
    monkeypatch.setattr(m5_writing, "s3_from_env", lambda: fake_s3)
    monkeypatch.setenv("AWS_S3_BUCKET", "test-bucket")

    local = tmp_path / "thesis-x.pdf"
    local.write_bytes(b"%PDF-1.4")
    m5_writing._upload_to_s3(str(local), "p", "pdf", "thesis-x.pdf")
    assert fake_s3.put_object.call_args.kwargs["ContentType"] == "application/pdf"
```

- [ ] **Step 2: Run — should FAIL**

```bash
python -m pytest orchestrator/tests/test_tools_m5.py -v 2>&1 | tail -15
```

Expected: FAIL — `s3_from_env` and `_upload_to_s3` don't exist in `orchestrator/tools/m5_writing.py`.

- [ ] **Step 3: Add the helpers to `orchestrator/tools/m5_writing.py`**

Append to `orchestrator/tools/m5_writing.py` (after the existing imports and before any `@tool` definitions — find a sensible spot):

```python
# Add to existing imports at top of file:
# import boto3
# from uuid import uuid4
# (uuid4 may already be imported; boto3 likely not)
import boto3
from uuid import uuid4


def s3_from_env():
    """S3 client factory — mirrors the SP2 api/app/routers/uploads.py pattern.
    Indirection point so tests can monkeypatch easily.
    """
    return boto3.client(
        "s3",
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_KEY"),
    )


_CONTENT_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf":  "application/pdf",
}


def _upload_to_s3(local_path: str, project_id: str, kind: str, filename: str) -> str:
    """Upload a local artifact to S3 under projects/{project_id}/exports/.

    Returns the s3_key (not signed URL — keys persist; signed URLs expire).
    Deletes the local file after upload to keep the scratch dir clean.
    """
    s3 = s3_from_env()
    bucket = os.environ["AWS_S3_BUCKET"]
    s3_key = f"projects/{project_id}/exports/{filename}"
    content_type = _CONTENT_TYPES[kind]
    with open(local_path, "rb") as f:
        s3.put_object(
            Bucket=bucket, Key=s3_key, Body=f.read(),
            ContentType=content_type,
        )
    Path(local_path).unlink(missing_ok=True)
    return s3_key
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest orchestrator/tests/test_tools_m5.py -v 2>&1 | tail -15
git add orchestrator/tools/m5_writing.py orchestrator/tests/test_tools_m5.py
git commit -m "feat(orchestrator): _upload_to_s3 helper + s3_from_env factory"
```

Expected: existing + 3 new tests PASS.

---

### Task 3: `compile_pdf` + `export_docx` S3 upload + `project_id` requirement

**Files:**
- Modify: `orchestrator/tools/m5_writing.py`
- Modify: `orchestrator/tests/test_tools_m5.py`

- [ ] **Step 1: Append the failing tests**

Append to `orchestrator/tests/test_tools_m5.py`:

```python
def test_compile_pdf_uploads_to_s3_and_returns_key(monkeypatch):
    from orchestrator.tools import m5_writing
    from unittest.mock import MagicMock

    fake_s3 = MagicMock()
    monkeypatch.setattr(m5_writing, "s3_from_env", lambda: fake_s3)
    monkeypatch.setenv("AWS_S3_BUCKET", "test-bucket")

    # Stub the engine PDF render: write a dummy file at the path it was asked to.
    def fake_compile_via_engine(sections, output_path, **kw):
        Path(output_path).write_bytes(b"%PDF-1.4\nfake")
        return output_path
    monkeypatch.setattr(m5_writing, "_compile_pdf_via_engine", fake_compile_via_engine)

    s3_key = m5_writing.compile_pdf.invoke({
        "sections": [{"name": "intro", "text": "x"}],
        "project_id": "proj-xyz",
    })
    assert s3_key.startswith("projects/proj-xyz/exports/thesis-")
    assert s3_key.endswith(".pdf")
    # boto3 was called once
    assert fake_s3.put_object.call_count == 1


def test_export_docx_uploads_to_s3_and_returns_key(monkeypatch):
    from orchestrator.tools import m5_writing
    from unittest.mock import MagicMock

    fake_s3 = MagicMock()
    monkeypatch.setattr(m5_writing, "s3_from_env", lambda: fake_s3)
    monkeypatch.setenv("AWS_S3_BUCKET", "test-bucket")

    def fake_export_via_engine(sections, output_path, **kw):
        Path(output_path).write_bytes(b"PK\x03\x04 fake docx")
        return output_path
    monkeypatch.setattr(m5_writing, "_export_docx_via_engine", fake_export_via_engine)

    s3_key = m5_writing.export_docx.invoke({
        "sections": [{"name": "intro", "text": "x"}],
        "project_id": "proj-xyz",
    })
    assert s3_key.startswith("projects/proj-xyz/exports/thesis-")
    assert s3_key.endswith(".docx")


def test_compile_pdf_raises_without_project_id():
    from orchestrator.tools.m5_writing import compile_pdf
    with pytest.raises(ValueError, match="project_id"):
        compile_pdf.invoke({"sections": [], "project_id": ""})


def test_export_docx_raises_without_project_id():
    from orchestrator.tools.m5_writing import export_docx
    with pytest.raises(ValueError, match="project_id"):
        export_docx.invoke({"sections": [], "project_id": ""})
```

(Tests need `import pytest` and `from pathlib import Path` — check that the existing test file has these or add them.)

- [ ] **Step 2: Run — should FAIL**

```bash
python -m pytest orchestrator/tests/test_tools_m5.py -v 2>&1 | tail -15
```

Expected: FAIL — current `compile_pdf` / `export_docx` don't accept `project_id` and don't upload to S3.

- [ ] **Step 3: Replace the existing `compile_pdf` and `export_docx` in `orchestrator/tools/m5_writing.py`**

Find the existing `@tool def compile_pdf(...)` and `@tool def export_docx(...)` definitions. Replace with:

```python
@tool
def compile_pdf(sections: list[dict], project_id: str) -> str:
    """SP6: render sections to PDF, upload to S3, return s3_key.

    Required for both interactive and auto-mode paths — local-path fallback
    removed (Q-S3 decision).
    """
    if not project_id:
        raise ValueError("compile_pdf requires project_id")
    filename = f"thesis-{uuid4().hex[:8]}.pdf"
    local_path = _scratch_dir() / filename
    _compile_pdf_via_engine(sections, str(local_path))
    return _upload_to_s3(str(local_path), project_id, "pdf", filename)


@tool
def export_docx(sections: list[dict], project_id: str) -> str:
    """SP6: render sections to DOCX, upload to S3, return s3_key.

    Required for both interactive and auto-mode paths.
    """
    if not project_id:
        raise ValueError("export_docx requires project_id")
    filename = f"thesis-{uuid4().hex[:8]}.docx"
    local_path = _scratch_dir() / filename
    _export_docx_via_engine(sections, str(local_path))
    return _upload_to_s3(str(local_path), project_id, "docx", filename)
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest orchestrator/tests/test_tools_m5.py -v 2>&1 | tail -20
git add orchestrator/tools/m5_writing.py orchestrator/tests/test_tools_m5.py
git commit -m "feat(orchestrator): compile_pdf + export_docx upload to S3 with required project_id"
```

Expected: all existing + 4 new tests PASS.

---

### Task 4: `validate_citations` helper

**Files:**
- Modify: `orchestrator/tools/m5_writing.py`
- Modify: `orchestrator/tests/test_tools_m5.py`

- [ ] **Step 1: Append the failing tests**

```python
def test_validate_citations_matches_pool():
    from orchestrator.tools.m5_writing import validate_citations
    prose = "Bass (1990) found... Later researchers confirmed (Avolio et al., 2009) that..."
    references = [
        {"author": "Bass", "year": 1990, "title": "Leadership"},
        {"author": "Avolio et al.", "year": 2009, "title": "Trans. leadership"},
    ]
    cited, uncited = validate_citations(prose, references)
    # The regex matches "(Author, Year)" — "Bass (1990)" is NOT in the (X, Y) shape;
    # only "(Avolio et al., 2009)" matches the regex.
    assert "Avolio et al., 2009" in cited
    assert uncited == []


def test_validate_citations_flags_uncited():
    from orchestrator.tools.m5_writing import validate_citations
    prose = "Some studies (Smith, 2023) claim X. Others (Bass, 1990) agree."
    references = [
        {"author": "Bass", "year": 1990, "title": "Leadership"},
    ]
    cited, uncited = validate_citations(prose, references)
    assert cited == ["Bass, 1990"]
    assert uncited == ["Smith, 2023"]


def test_validate_citations_empty_prose():
    from orchestrator.tools.m5_writing import validate_citations
    cited, uncited = validate_citations("", [])
    assert cited == []
    assert uncited == []


def test_validate_citations_deduplicates():
    from orchestrator.tools.m5_writing import validate_citations
    prose = "(Bass, 1990) said X. Later (Bass, 1990) also said Y."
    references = [{"author": "Bass", "year": 1990}]
    cited, uncited = validate_citations(prose, references)
    assert cited == ["Bass, 1990"]  # de-duplicated
```

- [ ] **Step 2: Run — should FAIL**

```bash
python -m pytest orchestrator/tests/test_tools_m5.py::test_validate_citations_matches_pool -v
```

Expected: FAIL — `validate_citations` doesn't exist.

- [ ] **Step 3: Add the helper to `orchestrator/tools/m5_writing.py`**

```python
# Add to imports at top of file:
import re


_CITE_PATTERN = re.compile(r"\((?P<author>[A-Z][\w-]+(?: et al\.)?), (?P<year>\d{4})\)")


def validate_citations(prose: str, references: list[dict]) -> tuple[list[str], list[str]]:
    """Regex-scan prose for (Author, Year) patterns; partition into
    (cited_in_pool, uncited). Each returned list is de-duplicated and
    preserves first-occurrence order.

    Plain Python helper (not a @tool) — used by compose_chapter +
    rewrite_chapter post-validation.
    """
    pool = {(r.get("author", ""), str(r.get("year", ""))) for r in references}
    cited: list[str] = []
    uncited: list[str] = []
    seen: set[tuple[str, str]] = set()
    for m in _CITE_PATTERN.finditer(prose):
        key = (m.group("author"), m.group("year"))
        if key in seen:
            continue
        seen.add(key)
        label = f"{m.group('author')}, {m.group('year')}"
        if key in pool:
            cited.append(label)
        else:
            uncited.append(label)
    return cited, uncited
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest orchestrator/tests/test_tools_m5.py -v 2>&1 | tail -15
git add orchestrator/tools/m5_writing.py orchestrator/tests/test_tools_m5.py
git commit -m "feat(orchestrator): validate_citations regex-scan helper"
```

Expected: 4 new + existing M5-tool tests PASS.

---

### Task 5: `compile_bibliography` tool

**Files:**
- Modify: `orchestrator/tools/m5_writing.py`
- Modify: `orchestrator/tests/test_tools_m5.py`

- [ ] **Step 1: Append the failing tests**

```python
def test_compile_bibliography_formats_references():
    from orchestrator.tools.m5_writing import compile_bibliography
    refs = [
        {"author": "Bass", "year": 1990, "title": "Transformational leadership"},
        {"author": "Avolio et al.", "year": 2009, "title": "Authentic leadership"},
    ]
    out = compile_bibliography.invoke({"references": refs, "citation_style": "apa7"})
    assert "Bass" in out
    assert "1990" in out
    assert "Avolio" in out


def test_compile_bibliography_empty_references():
    from orchestrator.tools.m5_writing import compile_bibliography
    out = compile_bibliography.invoke({"references": [], "citation_style": "apa7"})
    assert "No references" in out or out == ""
```

- [ ] **Step 2: Run — should FAIL**

```bash
python -m pytest orchestrator/tests/test_tools_m5.py::test_compile_bibliography_formats_references -v
```

- [ ] **Step 3: Add the tool to `orchestrator/tools/m5_writing.py`**

```python
@tool
def compile_bibliography(references: list[dict], citation_style: str) -> str:
    """Format M2 references as a bibliography section using the existing
    CitationCompiler. Returns the formatted block as a multi-line string,
    or '(No references)' on empty input.
    """
    if not references:
        return "(No references)"
    return CitationCompiler(citation_style).compile(references)
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest orchestrator/tests/test_tools_m5.py -v 2>&1 | tail -10
git add orchestrator/tools/m5_writing.py orchestrator/tests/test_tools_m5.py
git commit -m "feat(orchestrator): compile_bibliography tool"
```

Expected: 2 new + existing tests PASS.

---

## Phase C — Chapter prompts

### Task 6: 6 chapter prompt files

**Files:**
- Create: `orchestrator/prompts/m5/intro.md`
- Create: `orchestrator/prompts/m5/lit_review.md`
- Create: `orchestrator/prompts/m5/methodology.md`
- Create: `orchestrator/prompts/m5/results.md`
- Create: `orchestrator/prompts/m5/discussion.md`
- Create: `orchestrator/prompts/m5/conclusion.md`

- [ ] **Step 1: Create the directory**

```bash
mkdir -p /Users/caonguyenvan/project/dothesis/orchestrator/prompts/m5
```

- [ ] **Step 2: Create `orchestrator/prompts/m5/intro.md`**

```markdown
# Compose Chapter 1 — Introduction

You are writing Chapter 1 (Introduction) of a master's thesis.

## Inputs (interpolated from context_store)
- Research title: {research_title}
- Field: {field}
- Paradigm: {paradigm}
- Research type: {research_type}
- Objectives: {objectives}
- Research questions: {research_questions}
- Target population: {target_population}
- Scope: {scope}
- Language: {language}
- Citation style: {citation_style}

## References available for citation
{references_list}

## Instructions
Write a 600-1000 word Chapter 1 with these sections:
- 1.1 Background and motivation
- 1.2 Problem statement
- 1.3 Research objectives (list the objectives above)
- 1.4 Research questions (list them; align with objectives)
- 1.5 Scope and significance
- 1.6 Thesis structure overview

Use academic prose. Cite inline as (Author, Year) using ONLY references above; do not invent citations. Write in {language}.

Output: Chapter 1 prose as markdown only — no preamble, no explanation.
```

- [ ] **Step 3: Create `orchestrator/prompts/m5/lit_review.md`**

```markdown
# Compose Chapter 2 — Literature Review

You are writing Chapter 2 (Literature Review) of a master's thesis.

## Inputs
- Research title: {research_title}
- Paradigm: {paradigm}
- Research questions: {research_questions}
- Existing literature draft (from M2): {literature_review_doc}
- Identified research gaps (from M2): {research_gaps}
- Language: {language}
- Citation style: {citation_style}

## References available for citation
{references_list}

## Instructions
Write a 1200-2000 word Chapter 2 with these sections:
- 2.1 Theoretical background (key constructs + their accepted definitions)
- 2.2 Empirical literature (recent studies grouped by sub-topic; cite extensively)
- 2.3 Research gaps (synthesize the gaps above; explain how this thesis addresses them)
- 2.4 Conceptual framework / Thematic framework summary

If the M2 literature_review_doc already contains rich content, incorporate and refine it — do not duplicate. Cite inline as (Author, Year). Write in {language}.

Output: Chapter 2 prose as markdown only.
```

- [ ] **Step 4: Create `orchestrator/prompts/m5/methodology.md`**

```markdown
# Compose Chapter 3 — Methodology

You are writing Chapter 3 (Methodology) of a master's thesis.

## Inputs
- Research title: {research_title}
- Paradigm: {paradigm}
- Research design: {design}
- Analysis tool: {tool}
- Conceptual model (quant): {conceptual_model}
- Themes (qual): {themes}
- Scale items (quant): {scale_items}
- Interview guide (qual): {interview_guide}
- Sampling strategy: {sampling_strategy}
- Target sample size: {target_sample_size}
- Purposive criteria (qual): {purposive_criteria}
- Mixed design type (mixed only): {mixed_design_type}
- Language: {language}
- Citation style: {citation_style}

## References available for citation
{references_list}

## Instructions
For paradigm = quantitative, write sections:
- 3.1 Research design rationale (justify quant approach + chosen design)
- 3.2 Population and sampling (sampling_strategy + target_sample_size)
- 3.3 Instrument: measurement model + scale items per construct
- 3.4 Data collection procedure
- 3.5 Data analysis approach (justify tool — SmartPLS/SPSS/AMOS/R lavaan)

For paradigm = qualitative, write sections:
- 3.1 Research approach + Braun & Clarke (2006) justification
- 3.2 Purposive sampling rationale + criteria
- 3.3 Interview guide structure with example probes
- 3.4 Data collection logistics
- 3.5 Thematic analysis 6-step procedure (familiarization → coding → themes → review → naming → writing)

For paradigm = mixed, include both above + 3.6 integration section explaining the {mixed_design_type} sequencing.

Cite inline as (Author, Year). Write in {language}. Length: 800-1500 words.

Output: Chapter 3 prose as markdown only.
```

- [ ] **Step 5: Create `orchestrator/prompts/m5/results.md`**

```markdown
# Compose Chapter 4 — Results

You are writing Chapter 4 (Results) of a master's thesis.

## Inputs
- Research title: {research_title}
- Paradigm: {paradigm}
- Mixed design type (mixed only): {mixed_design_type}
- Data type detected (M4): {data_type_detected}
- Per-step results (quant, from M4): {results}
- Qualitative codes (from M4): {qual_codes}
- Qualitative themes (from M4): {qual_themes}
- Custom ad-hoc analyses: {custom_analyses}
- Language: {language}
- Citation style: {citation_style}

## References available for citation
{references_list}

## Instructions

### If paradigm == "quantitative"
Write a 1200-2000 word Chapter 4 with these sections:
- 4.1 Sample characteristics (descriptives from results)
- 4.2 Measurement model evaluation (reliability + validity from results)
- 4.3 Hypothesis testing / structural model (path coefficients, regression coefficients, fit indices from results)
- 4.4 Summary of supported / rejected hypotheses

For each result table reference, integrate the numbers from {results} naturally into prose. Flag any threshold breaches (`⚠️` markers from M4 mean the threshold was missed).

### If paradigm == "qualitative"
Write a 1200-2500 word Chapter 4 using the Braun & Clarke (2006) thematic-analysis writeup pattern:
- 4.1 Sample characteristics + context
- 4.2 to 4.N (one section per theme in {qual_themes})
  - Theme name as section heading
  - Synthesize codes belonging to this theme from {qual_codes}
  - Embed 1-2 verbatim quotes per theme (drawn from qual_codes[*].quote)
  - Link back to literature where appropriate
- 4.{N+1} Integration of themes (how themes relate to each other and to the research questions)

### If paradigm == "mixed"
Use {mixed_design_type} to structure:
- 4.1 Sample characteristics (both phases)
- 4.2 Quantitative results (as in the quant section above)
- 4.3 Qualitative results (as in the qual section above)
- 4.4 Integration: convergence, divergence, expansion (explain how quant + qual results inform each other)

Cite inline as (Author, Year). Write in {language}.

Output: Chapter 4 prose as markdown only.
```

- [ ] **Step 6: Create `orchestrator/prompts/m5/discussion.md`**

```markdown
# Compose Chapter 5 — Discussion

You are writing Chapter 5 (Discussion) of a master's thesis.

## Inputs
- Research title: {research_title}
- Paradigm: {paradigm}
- Research questions: {research_questions}
- Research gaps (M2): {research_gaps}
- Themes / hypotheses results (from Chapter 4): {results} / {qual_themes}
- Language: {language}
- Citation style: {citation_style}

## References available for citation
{references_list}

## Instructions
Write a 1200-2000 word Chapter 5 with these sections:
- 5.1 Summary of findings (one paragraph per research question)
- 5.2 Discussion of findings (compare to prior literature; explain consistencies + surprises)
- 5.3 Theoretical contributions (how findings extend / refine the theory used)
- 5.4 Practical implications (managerial / policy recommendations)
- 5.5 Limitations
- 5.6 Suggestions for future research

Cite extensively to back up each interpretation. Write in {language}.

Output: Chapter 5 prose as markdown only.
```

- [ ] **Step 7: Create `orchestrator/prompts/m5/conclusion.md`**

```markdown
# Compose Chapter 6 — Conclusion

You are writing Chapter 6 (Conclusion) of a master's thesis.

## Inputs
- Research title: {research_title}
- Paradigm: {paradigm}
- Objectives: {objectives}
- Research questions: {research_questions}
- Key findings summary: {results} / {qual_themes}
- Language: {language}

## References available for citation
{references_list}

## Instructions
Write a 500-800 word Chapter 6 with these sections:
- 6.1 Restatement of objectives + how they were met
- 6.2 Key conclusions per research question
- 6.3 Significance of the work (concise; no new claims)
- 6.4 Closing remarks

Use academic prose. Minimal new citations — only if essential. Write in {language}.

Output: Chapter 6 prose as markdown only.
```

- [ ] **Step 8: Validate that prompts load**

```bash
cd /Users/caonguyenvan/project/dothesis
python -c "
from pathlib import Path
d = Path('orchestrator/prompts/m5')
for f in ['intro', 'lit_review', 'methodology', 'results', 'discussion', 'conclusion']:
    text = (d / f'{f}.md').read_text()
    assert len(text) > 200, f'{f}.md too short'
    assert '{research_title}' in text or '{paradigm}' in text, f'{f}.md missing placeholder'
print('All 6 prompts OK')
"
```

Expected: prints "All 6 prompts OK".

- [ ] **Step 9: Commit**

```bash
git add orchestrator/prompts/m5/*.md
git commit -m "feat(orchestrator): 6 chapter prompts for M5 (intro / lit_review / methodology / results / discussion / conclusion)"
```

---

## Phase D — Compose + Rewrite tools

### Task 7: `compose_chapter` tool

**Files:**
- Modify: `orchestrator/tools/m5_writing.py`
- Modify: `orchestrator/tests/test_tools_m5.py`

- [ ] **Step 1: Append the failing tests**

```python
def test_compose_chapter_returns_chapter_draft_shape(monkeypatch):
    """compose_chapter calls the LLM with a chapter prompt + returns ChapterDraft dict."""
    from orchestrator.tools import m5_writing
    from unittest.mock import MagicMock

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = (
        "# Introduction\n\nThis is a draft intro citing (Bass, 1990).\n"
    )
    monkeypatch.setattr(m5_writing, "_get_llm", lambda: fake_llm)

    refs = [{"author": "Bass", "year": 1990, "title": "Leadership"}]
    out = m5_writing.compose_chapter.invoke({
        "chapter_name": "intro",
        "paradigm": "quantitative",
        "context_slice": {
            "research_title": "Leadership and Engagement",
            "field": "Management", "paradigm": "quantitative",
            "research_type": "quantitative",
            "objectives": ["O1"], "research_questions": ["RQ1"],
            "target_population": "SME employees", "scope": "VN, 2026",
        },
        "references": refs,
        "citation_style": "apa7",
        "language": "en",
    })
    assert out["name"] == "intro"
    assert out["prose"].startswith("# Introduction")
    assert "Bass, 1990" in out["citations_used"]
    assert out["uncited_warnings"] == []


def test_compose_chapter_flags_uncited(monkeypatch):
    """When the LLM cites a reference NOT in the pool, it's flagged."""
    from orchestrator.tools import m5_writing
    from unittest.mock import MagicMock

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = (
        "Some studies (Smith, 2023) suggest X. Others (Bass, 1990) agree.\n"
    )
    monkeypatch.setattr(m5_writing, "_get_llm", lambda: fake_llm)

    refs = [{"author": "Bass", "year": 1990}]
    out = m5_writing.compose_chapter.invoke({
        "chapter_name": "intro",
        "paradigm": "quantitative",
        "context_slice": {"research_title": "x", "objectives": []},
        "references": refs,
        "citation_style": "apa7", "language": "en",
    })
    assert "Bass, 1990" in out["citations_used"]
    assert "Smith, 2023" in out["uncited_warnings"]
    assert "uncited" in out["prose"].lower() or "⚠️" in out["prose"]


def test_compose_chapter_falls_back_on_llm_error(monkeypatch):
    """compose_chapter survives an LLM exception with a placeholder prose."""
    from orchestrator.tools import m5_writing
    from unittest.mock import MagicMock

    fake_llm = MagicMock()
    fake_llm.invoke.side_effect = RuntimeError("API down")
    monkeypatch.setattr(m5_writing, "_get_llm", lambda: fake_llm)

    out = m5_writing.compose_chapter.invoke({
        "chapter_name": "intro",
        "paradigm": "quantitative",
        "context_slice": {"research_title": "x", "objectives": []},
        "references": [],
        "citation_style": "apa7", "language": "en",
    })
    assert out["name"] == "intro"
    assert "Composition failed" in out["prose"] or "[Composition failed" in out["prose"]
```

- [ ] **Step 2: Run — should FAIL**

```bash
python -m pytest orchestrator/tests/test_tools_m5.py::test_compose_chapter_returns_chapter_draft_shape -v
```

- [ ] **Step 3: Add helpers + the `compose_chapter` tool to `orchestrator/tools/m5_writing.py`**

```python
# Add to imports at top:
import json


_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts" / "m5"


def _format_references_for_prompt(refs: list[dict]) -> str:
    """One reference per line, numbered. Used inside chapter prompts."""
    if not refs:
        return "(no references available — write without inline citations)"
    lines = []
    for i, r in enumerate(refs, 1):
        author = r.get("author", "Anon")
        year = r.get("year", "n.d.")
        title = r.get("title", "")
        lines.append(f"[{i}] {author} ({year}). {title}".strip())
    return "\n".join(lines)


def _safe_format_kwargs(context_slice: dict) -> dict:
    """Convert dict/list values to JSON strings so str.format() doesn't break."""
    out = {}
    for k, v in context_slice.items():
        if isinstance(v, (dict, list)):
            out[k] = json.dumps(v, ensure_ascii=False, default=str)
        elif v is None:
            out[k] = ""
        else:
            out[k] = str(v)
    return out


def _annotate_uncited(prose: str, uncited: list[str]) -> str:
    """Append a notice block listing any uncited (Author, Year) flags."""
    if not uncited:
        return prose
    notice = (
        "\n\n> ⚠️ The following inline citations are not present in the "
        "M2 reference pool and may be hallucinated: "
        + ", ".join(uncited)
        + ". Verify or remove."
    )
    return prose + notice


def _get_llm():
    """LLM factory for M5 tools. Monkeypatchable in tests."""
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.0-flash-001"),
        temperature=0.4,
    )


@tool
def compose_chapter(
    chapter_name: str, paradigm: str, context_slice: dict,
    references: list[dict], citation_style: str, language: str,
) -> dict:
    """Compose one chapter via LLM, returns ChapterDraft dict.

    Loads orchestrator/prompts/m5/<chapter_name>.md as the prompt template;
    fills it with the context_slice + references; calls the LLM; runs
    validate_citations on the result; returns
    {name, prose, citations_used, uncited_warnings}.
    """
    prompt_template = (_PROMPT_DIR / f"{chapter_name}.md").read_text()
    refs_block = _format_references_for_prompt(references)
    safe_kwargs = _safe_format_kwargs(context_slice)
    safe_kwargs.setdefault("paradigm", paradigm)
    safe_kwargs.setdefault("language", language)
    safe_kwargs.setdefault("citation_style", citation_style)
    safe_kwargs["references_list"] = refs_block
    # str.format may KeyError on placeholders not in safe_kwargs — pre-extract
    # all expected keys and fall back to empty string.
    expected_keys = (
        "research_title", "field", "paradigm", "research_type",
        "objectives", "research_questions", "target_population", "scope",
        "literature_review_doc", "research_gaps",
        "design", "tool", "conceptual_model", "scale_items",
        "themes", "interview_guide", "purposive_criteria",
        "sampling_strategy", "target_sample_size", "mixed_design_type",
        "data_type_detected", "results", "qual_codes", "qual_themes",
        "custom_analyses",
        "language", "citation_style", "references_list",
    )
    for k in expected_keys:
        safe_kwargs.setdefault(k, "")

    try:
        prompt = prompt_template.format(**safe_kwargs)
        prose = _get_llm().invoke(prompt).content.strip()
    except (KeyError, Exception) as e:
        logger.warning("compose_chapter LLM call failed for %s: %s", chapter_name, e)
        prose = f"# {chapter_name.title()}\n\n[Composition failed — please retry]"

    cited_in_pool, uncited = validate_citations(prose, references)
    if uncited:
        prose = _annotate_uncited(prose, uncited)
    return {
        "name": chapter_name,
        "prose": prose,
        "citations_used": cited_in_pool,
        "uncited_warnings": uncited,
    }
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest orchestrator/tests/test_tools_m5.py -v 2>&1 | tail -15
git add orchestrator/tools/m5_writing.py orchestrator/tests/test_tools_m5.py
git commit -m "feat(orchestrator): compose_chapter LLM tool with prompt loading + citation validation"
```

Expected: 3 new + existing M5-tool tests PASS.

---

### Task 8: `rewrite_chapter` tool

**Files:**
- Modify: `orchestrator/tools/m5_writing.py`
- Modify: `orchestrator/tests/test_tools_m5.py`

- [ ] **Step 1: Append the failing tests**

```python
def test_rewrite_chapter_returns_new_draft(monkeypatch):
    from orchestrator.tools import m5_writing
    from unittest.mock import MagicMock

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "Less formal intro version here.\n"
    monkeypatch.setattr(m5_writing, "_get_llm", lambda: fake_llm)

    out = m5_writing.rewrite_chapter.invoke({
        "chapter_name": "intro",
        "current_prose": "# Introduction\n\nFormal intro.",
        "instruction": "rewrite to be less formal",
        "context_slice": {"research_title": "x", "objectives": []},
        "references": [],
        "language": "en",
    })
    assert out["name"] == "intro"
    assert "Less formal" in out["prose"]


def test_rewrite_chapter_falls_back_on_llm_error(monkeypatch):
    """If the LLM errors, return the original prose unchanged (don't lose work)."""
    from orchestrator.tools import m5_writing
    from unittest.mock import MagicMock

    fake_llm = MagicMock()
    fake_llm.invoke.side_effect = RuntimeError("API down")
    monkeypatch.setattr(m5_writing, "_get_llm", lambda: fake_llm)

    original = "# Original prose"
    out = m5_writing.rewrite_chapter.invoke({
        "chapter_name": "intro",
        "current_prose": original,
        "instruction": "any",
        "context_slice": {"research_title": "x", "objectives": []},
        "references": [], "language": "en",
    })
    assert out["prose"] == original  # unchanged on failure
```

- [ ] **Step 2: Run — should FAIL**

```bash
python -m pytest orchestrator/tests/test_tools_m5.py::test_rewrite_chapter_returns_new_draft -v
```

- [ ] **Step 3: Add the tool to `orchestrator/tools/m5_writing.py`**

```python
@tool
def rewrite_chapter(
    chapter_name: str, current_prose: str, instruction: str,
    context_slice: dict, references: list[dict], language: str,
) -> dict:
    """Rewrite one chapter per user instruction. Returns new ChapterDraft dict.

    Used when the user says e.g. "rewrite the intro to be less formal".
    Same prompt template as compose_chapter + the instruction + current prose
    as anchor. On LLM error, returns the original prose unchanged.
    """
    prompt_template = (_PROMPT_DIR / f"{chapter_name}.md").read_text()
    refs_block = _format_references_for_prompt(references)
    safe_kwargs = _safe_format_kwargs(context_slice)
    safe_kwargs.setdefault("paradigm", context_slice.get("paradigm", "quantitative"))
    safe_kwargs.setdefault("language", language)
    safe_kwargs.setdefault("citation_style", "apa7")
    safe_kwargs["references_list"] = refs_block
    expected_keys = (
        "research_title", "field", "paradigm", "research_type",
        "objectives", "research_questions", "target_population", "scope",
        "literature_review_doc", "research_gaps",
        "design", "tool", "conceptual_model", "scale_items",
        "themes", "interview_guide", "purposive_criteria",
        "sampling_strategy", "target_sample_size", "mixed_design_type",
        "data_type_detected", "results", "qual_codes", "qual_themes",
        "custom_analyses",
        "language", "citation_style", "references_list",
    )
    for k in expected_keys:
        safe_kwargs.setdefault(k, "")

    try:
        base_prompt = prompt_template.format(**safe_kwargs)
        rewrite_prompt = (
            f"{base_prompt}\n\n"
            f"## User rewrite instruction\n{instruction}\n\n"
            f"## Current chapter prose (rewrite based on the instruction; preserve good content):\n"
            f"{current_prose}\n\n"
            f"Output ONLY the rewritten chapter prose."
        )
        prose = _get_llm().invoke(rewrite_prompt).content.strip()
    except Exception as e:
        logger.warning("rewrite_chapter LLM call failed for %s: %s", chapter_name, e)
        prose = current_prose  # unchanged on failure

    cited_in_pool, uncited = validate_citations(prose, references)
    if uncited:
        prose = _annotate_uncited(prose, uncited)
    return {
        "name": chapter_name,
        "prose": prose,
        "citations_used": cited_in_pool,
        "uncited_warnings": uncited,
    }
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest orchestrator/tests/test_tools_m5.py -v 2>&1 | tail -15
git add orchestrator/tools/m5_writing.py orchestrator/tests/test_tools_m5.py
git commit -m "feat(orchestrator): rewrite_chapter LLM tool"
```

Expected: 2 new + existing M5-tool tests PASS.

---

## Phase E — M5Agent

### Task 9: `_extract_context_slice` + `_collect_references` + small helpers

**Files:**
- Modify: `orchestrator/agents/m5_writing.py`
- Create: `orchestrator/tests/agents/test_m5_context_slice.py`

- [ ] **Step 1: Write the failing tests**

Create `orchestrator/tests/agents/test_m5_context_slice.py`:

```python
"""Tests for M5Agent._extract_context_slice + _collect_references."""
from orchestrator.agents.m5_writing import M5Agent
from orchestrator.state import ContextStore


def test_extract_context_slice_returns_full_shape():
    agent = M5Agent()
    cs = ContextStore(
        m1_topic={"research_title": "TL → EE", "field": "Management",
                   "research_type": "quantitative", "language": "en",
                   "objectives": ["O1"], "research_questions": ["RQ1"],
                   "target_population": "SME emp", "scope": "VN 2026"},
        m2_literature={"literature_review_doc": "lit text",
                        "research_gaps": [{"description": "g1"}]},
        m3_design={"paradigm": "quantitative", "design": "PLS-SEM",
                    "tool": "SmartPLS", "conceptual_model": {"constructs": ["TL"]},
                    "scale_items": [{"construct": "TL", "items": ["I1"]}],
                    "sampling_strategy": "random", "target_sample_size": 200},
        m4_analysis={"data_type_detected": "SmartPLS",
                      "results": {"Outer Loadings": {"step_name": "Outer Loadings"}},
                      "qual_codes": [], "qual_themes": []},
    )
    out = agent._extract_context_slice(cs)
    assert out["research_title"] == "TL → EE"
    assert out["paradigm"] == "quantitative"
    assert out["design"] == "PLS-SEM"
    assert out["tool"] == "SmartPLS"
    assert "Outer Loadings" in out["results"]
    assert out["language"] == "en"


def test_extract_context_slice_handles_none_slices():
    """Each upstream module's slice may be None on a freshly-created project."""
    agent = M5Agent()
    cs = ContextStore()
    out = agent._extract_context_slice(cs)
    assert out["research_title"] is None
    assert out["paradigm"] is None
    assert out["objectives"] == []
    assert out["research_gaps"] == []
    assert out["results"] == {}
    assert out["language"] == "en"  # default fallback


def test_collect_references_dedupes_across_gaps():
    agent = M5Agent()
    context = {
        "research_gaps": [
            {"description": "g1", "supporting_papers": [
                {"author": "Bass", "year": 1990, "title": "Leadership"},
                {"author": "Avolio", "year": 2009, "title": "Auth"},
            ]},
            {"description": "g2", "supporting_papers": [
                {"author": "Bass", "year": 1990, "title": "Leadership"},  # dup
                {"author": "Smith", "year": 2020, "title": "S"},
            ]},
        ],
    }
    refs = agent._collect_references(context)
    keys = {(r["author"], r["year"]) for r in refs}
    assert len(refs) == 3
    assert ("Bass", 1990) in keys
    assert ("Avolio", 2009) in keys
    assert ("Smith", 2020) in keys
```

- [ ] **Step 2: Run — should FAIL**

```bash
python -m pytest orchestrator/tests/agents/test_m5_context_slice.py -v 2>&1 | tail -15
```

Expected: FAIL — `_extract_context_slice` and `_collect_references` don't exist on the current M5Agent.

- [ ] **Step 3: Replace `orchestrator/agents/m5_writing.py`**

```python
"""M5 — Writing & Export agent (SP6 chapter-by-chapter compose + auto-export)."""
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

from orchestrator.agents.base import ModuleAgent, ModuleStepResult
from orchestrator.schemas.m5 import M5Output, ExportArtifact
from orchestrator.tools.m5_writing import (
    compose_chapter, compose_section, rewrite_chapter,
    validate_draft, validate_citations,
    format_citations, compile_bibliography,
    compile_pdf, export_docx,
)


_PROMPT = (Path(__file__).resolve().parent.parent / "prompts" / "m5.md").read_text()

_CHAPTER_ORDER = ["intro", "lit_review", "methodology", "results", "discussion", "conclusion"]


class M5Agent(ModuleAgent):
    schema = M5Output
    module_key = "M5"
    system_prompt = _PROMPT
    tools = [
        compose_chapter, compose_section, rewrite_chapter,
        validate_draft, validate_citations,
        format_citations, compile_bibliography,
        compile_pdf, export_docx,
    ]

    _REWRITE_KEYWORDS = (
        "rewrite", "rephrase", "paraphrase", "less formal", "more formal",
        "more academic", "expand", "condense", "shorter", "longer",
        "more detail", "less detail",
    )
    _CHAPTER_ALIASES = {
        "intro": "intro", "introduction": "intro",
        "chapter 1": "intro", "ch1": "intro", "ch 1": "intro",
        "lit review": "lit_review", "lit_review": "lit_review", "literature": "lit_review",
        "literature review": "lit_review",
        "chapter 2": "lit_review", "ch2": "lit_review", "ch 2": "lit_review",
        "methodology": "methodology", "methods": "methodology", "method": "methodology",
        "chapter 3": "methodology", "ch3": "methodology", "ch 3": "methodology",
        "results": "results", "findings": "results", "analysis": "results",
        "chapter 4": "results", "ch4": "results", "ch 4": "results",
        "discussion": "discussion",
        "chapter 5": "discussion", "ch5": "discussion", "ch 5": "discussion",
        "conclusion": "conclusion", "concluding": "conclusion",
        "chapter 6": "conclusion", "ch6": "conclusion", "ch 6": "conclusion",
    }

    _render_context: dict | None = None

    def _extract_context_slice(self, cs) -> dict:
        """Build a clean dict for compose-chapter prompts to interpolate from.

        Reads m1_topic, m2_literature, m3_design, m4_analysis from the
        ContextStore — each may be None for a freshly-created project.
        """
        m1 = cs.m1_topic or {}
        m2 = cs.m2_literature or {}
        m3 = cs.m3_design or {}
        m4 = cs.m4_analysis or {}
        return {
            "research_title": m1.get("research_title"),
            "field": m1.get("field"),
            "paradigm": m3.get("paradigm") or m1.get("research_type"),
            "research_type": m1.get("research_type"),
            "language": m1.get("language", "en"),
            "citation_style": "apa7",
            "objectives": m1.get("objectives", []),
            "research_questions": m1.get("research_questions", []),
            "target_population": m1.get("target_population"),
            "scope": m1.get("scope"),
            "literature_review_doc": m2.get("literature_review_doc", ""),
            "research_gaps": m2.get("research_gaps", []),
            "design": m3.get("design"),
            "tool": m3.get("tool"),
            "conceptual_model": m3.get("conceptual_model"),
            "scale_items": m3.get("scale_items"),
            "themes": m3.get("themes"),
            "interview_guide": m3.get("interview_guide"),
            "purposive_criteria": m3.get("purposive_criteria"),
            "sampling_strategy": m3.get("sampling_strategy"),
            "target_sample_size": m3.get("target_sample_size"),
            "mixed_design_type": m3.get("mixed_design_type"),
            "data_type_detected": m4.get("data_type_detected"),
            "results": m4.get("results", {}),
            "qual_codes": m4.get("qual_codes", []),
            "qual_themes": m4.get("qual_themes", []),
            "custom_analyses": m4.get("custom_analyses", []),
        }

    def _collect_references(self, context: dict) -> list[dict]:
        """Dedupe supporting_papers across all M2 research_gaps. Returns a list
        of unique paper dicts preserving first-occurrence order.
        """
        seen: dict[tuple[str, str], dict] = {}
        for gap in context.get("research_gaps", []):
            for paper in gap.get("supporting_papers", []):
                key = (paper.get("author", ""), str(paper.get("year", "")))
                if key not in seen:
                    seen[key] = paper
        return list(seen.values())

    def _latest_user_message(self, messages) -> str:
        return next(
            (m.content for m in reversed(messages) if isinstance(m, HumanMessage)),
            "",
        )
```

NOTE: Tasks 10-12 will append more methods to this class (`step`, `_compose_all_chapters`, `_is_rewrite_request`, `_identify_chapter`, `_handle_rewrite`, `_finalize_and_export`, plus formatting helpers).

- [ ] **Step 4: Run + commit**

```bash
python -m pytest orchestrator/tests/agents/test_m5_context_slice.py -v 2>&1 | tail -10
# Confirm existing M5 auto-mode test still passes (the new helpers don't affect _auto_fill path)
python -m pytest orchestrator/tests/test_agents_m5.py -v 2>&1 | tail -10
git add orchestrator/agents/m5_writing.py orchestrator/tests/agents/test_m5_context_slice.py
git commit -m "feat(orchestrator): M5Agent _extract_context_slice + _collect_references helpers"
```

Expected: 3 new context-slice tests + existing auto-mode test PASS.

---

### Task 10: `_compose_all_chapters` with per-chapter emission

**Files:**
- Modify: `orchestrator/agents/m5_writing.py`
- Create: `orchestrator/tests/agents/test_m5_compose.py`

- [ ] **Step 1: Write the failing tests**

Create `orchestrator/tests/agents/test_m5_compose.py`:

```python
"""Tests for M5Agent compose phase — per-chapter AIMessage emission."""
from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage

from orchestrator.agents.m5_writing import M5Agent
from orchestrator.state import ContextStore


def test_compose_phase_emits_one_message_per_chapter_plus_bibliography(monkeypatch):
    """Compose phase emits 6 chapter messages + 1 bibliography message + 1 summary."""
    from orchestrator.agents import m5_writing as m5_mod

    fake_compose = MagicMock()
    fake_compose.invoke.side_effect = lambda kw: {
        "name": kw["chapter_name"],
        "prose": f"## Chapter — {kw['chapter_name']}\nContent",
        "citations_used": [],
        "uncited_warnings": [],
    }
    monkeypatch.setattr(m5_mod, "compose_chapter", fake_compose)

    fake_bib = MagicMock()
    fake_bib.invoke.return_value = "Bass, A. (1990). Leadership."
    monkeypatch.setattr(m5_mod, "compile_bibliography", fake_bib)

    agent = M5Agent()
    state = {
        "messages": [HumanMessage(content="ok")],
        "current_module": "M5",
        "project_id": "proj-xyz",
        "context_store": ContextStore(
            m1_topic={"research_title": "TL → EE", "language": "en"},
            m3_design={"paradigm": "quantitative", "confirmed_at": "2026-05-26"},
            m4_analysis={"data_type_detected": "SmartPLS", "results": {}, "confirmed_at": "2026-05-26"},
        ),
        "mode": "interactive",
        "user_intent": None,
        "pending_confirmations": [],
    }
    result = agent.step(state)

    # 6 chapter AIMessages + 1 bibliography = 7 in extra_messages
    assert len(result.extra_messages) == 7
    contents = [m.content for m in result.extra_messages]
    assert any("intro" in c.lower() for c in contents)
    assert any("methodology" in c.lower() for c in contents)
    assert any("bibliography" in c.lower() for c in contents)

    # State updated correctly
    assert result.context_patch.get("_compose_chapters_done") is True
    assert result.context_patch.get("_awaiting_confirm") is True
    assert "chapters" in result.context_patch
    assert set(result.context_patch["chapters"].keys()) == set(M5Agent._CHAPTER_ORDER if hasattr(M5Agent, "_CHAPTER_ORDER") else [])
    # 6 chapters in the dict
    assert len(result.context_patch["chapters"]) == 6


def test_compose_phase_passes_paradigm_to_each_chapter(monkeypatch):
    """The paradigm flows from m3_design to compose_chapter for each call."""
    from orchestrator.agents import m5_writing as m5_mod

    captured_paradigms = []
    def fake_invoke(kw):
        captured_paradigms.append(kw.get("paradigm"))
        return {"name": kw["chapter_name"], "prose": "x", "citations_used": [],
                "uncited_warnings": []}
    fake_compose = MagicMock()
    fake_compose.invoke.side_effect = fake_invoke
    monkeypatch.setattr(m5_mod, "compose_chapter", fake_compose)

    fake_bib = MagicMock()
    fake_bib.invoke.return_value = ""
    monkeypatch.setattr(m5_mod, "compile_bibliography", fake_bib)

    agent = M5Agent()
    state = {
        "messages": [HumanMessage(content="go")],
        "current_module": "M5",
        "project_id": "p",
        "context_store": ContextStore(
            m3_design={"paradigm": "qualitative", "confirmed_at": "x"},
        ),
        "mode": "interactive",
        "user_intent": None,
        "pending_confirmations": [],
    }
    agent.step(state)
    assert len(captured_paradigms) == 6
    assert all(p == "qualitative" for p in captured_paradigms)
```

- [ ] **Step 2: Run — should FAIL**

```bash
python -m pytest orchestrator/tests/agents/test_m5_compose.py -v 2>&1 | tail -15
```

Expected: FAIL — `step()` not overridden; `_compose_all_chapters` doesn't exist.

- [ ] **Step 3: Append to `M5Agent` class in `orchestrator/agents/m5_writing.py`**

Add these methods to the `M5Agent` class (after the helpers from Task 9):

```python
    def step(self, state):
        """SP6: on first turn → compose phase. Tasks 11-12 add rewrite + finalize branches."""
        from orchestrator.state import get_module_slice
        cls = type(self)
        partial = dict(get_module_slice(state["context_store"], self.module_key))
        cls._render_context = self._extract_context_slice(state["context_store"])

        # Compose phase — first M5 turn always lands here.
        if not partial.get("_compose_chapters_done"):
            return self._compose_all_chapters(state, partial)

        return super().step(state)

    def render_hint_for_field(self, field_name: str) -> dict | None:
        return None  # SP6 has no widgets; chapter prose renders as plain markdown

    def _compose_all_chapters(self, state, partial):
        """Loop chapters, compose each, emit one AIMessage per chapter +
        bibliography + summary."""
        context = self._render_context or {}
        references = self._collect_references(context)
        chapters: dict[str, dict] = {}
        extras: list[AIMessage] = []
        for name in _CHAPTER_ORDER:
            draft = compose_chapter.invoke({
                "chapter_name": name,
                "paradigm": context.get("paradigm") or "quantitative",
                "context_slice": context,
                "references": references,
                "citation_style": context.get("citation_style", "apa7"),
                "language": context.get("language", "en"),
            })
            chapters[name] = draft
            extras.append(AIMessage(content=f"## Chapter — {name}\n\n{draft.get('prose', '')}"))
        bib = compile_bibliography.invoke({
            "references": references,
            "citation_style": context.get("citation_style", "apa7"),
        })
        extras.append(AIMessage(content=f"## Bibliography\n\n{bib}"))

        partial["chapters"] = chapters
        partial["bibliography"] = bib
        partial["_compose_chapters_done"] = True
        partial["_awaiting_confirm"] = True
        partial["_summary_done"] = True  # SP5 pattern — summary IS the summary step

        summary = self._build_compose_summary(chapters, references)
        return ModuleStepResult(
            assistant_message=summary,
            context_patch=partial,
            transition=False,
            needs_user_reply=True,
            extra_messages=extras,
        )

    def _build_compose_summary(self, chapters: dict, references: list) -> str:
        n_uncited = sum(len(c.get("uncited_warnings") or []) for c in chapters.values())
        msg = [
            f"Drafted all 6 chapters + bibliography ({len(references)} unique references).",
        ]
        if n_uncited:
            msg.append(
                f"⚠️ {n_uncited} inline citations flagged as potentially missing from the reference pool."
            )
        msg.append(
            "Confirm to export to docx + pdf, or ask for a rewrite "
            "(e.g. 'rewrite chapter 3 to be less formal')."
        )
        return "\n\n".join(msg)
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest orchestrator/tests/agents/test_m5_compose.py -v 2>&1 | tail -15
# Confirm existing tests still pass
python -m pytest orchestrator/tests/agents/test_m5_context_slice.py orchestrator/tests/test_agents_m5.py -v 2>&1 | tail -10
git add orchestrator/agents/m5_writing.py orchestrator/tests/agents/test_m5_compose.py
git commit -m "feat(orchestrator): M5Agent _compose_all_chapters with per-chapter AIMessage emission"
```

Expected: 2 new compose tests + earlier tests PASS.

---

### Task 11: `_is_rewrite_request` + `_identify_chapter` + `_handle_rewrite`

**Files:**
- Modify: `orchestrator/agents/m5_writing.py`
- Create: `orchestrator/tests/agents/test_m5_rewrite.py`

- [ ] **Step 1: Write the failing tests**

Create `orchestrator/tests/agents/test_m5_rewrite.py`:

```python
"""Tests for M5Agent rewrite detection + dispatch."""
from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage

from orchestrator.agents.m5_writing import M5Agent
from orchestrator.state import ContextStore


def test_is_rewrite_request_detects_keywords():
    agent = M5Agent()
    assert agent._is_rewrite_request([HumanMessage("rewrite chapter 3")]) is True
    assert agent._is_rewrite_request([HumanMessage("make it less formal")]) is True
    assert agent._is_rewrite_request([HumanMessage("expand the methodology")]) is True
    assert agent._is_rewrite_request([HumanMessage("yes, confirm")]) is False
    assert agent._is_rewrite_request([HumanMessage("looks good")]) is False


def test_identify_chapter_maps_aliases():
    agent = M5Agent()
    assert agent._identify_chapter("rewrite chapter 3") == "methodology"
    assert agent._identify_chapter("ch3 looks weird") == "methodology"
    assert agent._identify_chapter("rephrase the methodology") == "methodology"
    assert agent._identify_chapter("rewrite the intro") == "intro"
    assert agent._identify_chapter("introduction needs work") == "intro"
    assert agent._identify_chapter("expand the lit review") == "lit_review"
    assert agent._identify_chapter("results section") == "results"
    assert agent._identify_chapter("discussion") == "discussion"
    assert agent._identify_chapter("conclusion") == "conclusion"


def test_identify_chapter_returns_none_on_ambiguous():
    agent = M5Agent()
    assert agent._identify_chapter("something something") is None
    assert agent._identify_chapter("") is None


def test_handle_rewrite_calls_rewrite_chapter_and_updates_partial(monkeypatch):
    from orchestrator.agents import m5_writing as m5_mod

    fake_rewrite = MagicMock()
    fake_rewrite.invoke.return_value = {
        "name": "methodology",
        "prose": "Less formal methodology rewrite",
        "citations_used": [],
        "uncited_warnings": [],
    }
    monkeypatch.setattr(m5_mod, "rewrite_chapter", fake_rewrite)

    agent = M5Agent()
    # Prime the class cache so _handle_rewrite has context
    M5Agent._render_context = {
        "research_title": "x", "paradigm": "quantitative",
        "language": "en", "research_gaps": [],
    }
    partial = {
        "chapters": {"methodology": {"name": "methodology", "prose": "Formal version"}},
        "_compose_chapters_done": True,
        "_awaiting_confirm": True,
    }
    state = {
        "messages": [HumanMessage("rewrite chapter 3 to be less formal")],
        "current_module": "M5", "project_id": "p",
        "context_store": ContextStore(),
        "mode": "interactive", "user_intent": None, "pending_confirmations": [],
    }
    result = agent._handle_rewrite(state, partial)

    assert result.context_patch["chapters"]["methodology"]["prose"].startswith("Less formal")
    assert result.context_patch["_awaiting_confirm"] is True
    assert len(result.extra_messages) == 1
    assert "methodology" in result.extra_messages[0].content.lower()
    assert "rewritten" in result.extra_messages[0].content.lower()


def test_handle_rewrite_asks_for_clarification_on_ambiguous(monkeypatch):
    from orchestrator.agents import m5_writing as m5_mod
    monkeypatch.setattr(m5_mod, "rewrite_chapter", MagicMock())

    agent = M5Agent()
    M5Agent._render_context = {"paradigm": "quantitative", "research_gaps": [], "language": "en"}
    partial = {"chapters": {}, "_compose_chapters_done": True, "_awaiting_confirm": True}
    state = {
        "messages": [HumanMessage("rewrite this thing please")],
        "current_module": "M5", "project_id": "p",
        "context_store": ContextStore(),
        "mode": "interactive", "user_intent": None, "pending_confirmations": [],
    }
    result = agent._handle_rewrite(state, partial)
    assert result.context_patch["_awaiting_confirm"] is True
    assert "which chapter" in result.assistant_message.lower()
    # No rewrite happened
    assert result.extra_messages == []


def test_step_routes_rewrite_request_to_handle_rewrite(monkeypatch):
    """End-to-end: step() detects rewrite + dispatches to _handle_rewrite."""
    from orchestrator.agents import m5_writing as m5_mod

    fake_rewrite = MagicMock()
    fake_rewrite.invoke.return_value = {
        "name": "intro", "prose": "New intro", "citations_used": [],
        "uncited_warnings": [],
    }
    monkeypatch.setattr(m5_mod, "rewrite_chapter", fake_rewrite)

    agent = M5Agent()
    state = {
        "messages": [HumanMessage("rewrite the intro to be shorter")],
        "current_module": "M5", "project_id": "p",
        "context_store": ContextStore(
            m1_topic={"research_title": "x", "language": "en"},
            m3_design={"paradigm": "quantitative", "confirmed_at": "x"},
            m5_writing={
                "chapters": {"intro": {"name": "intro", "prose": "old intro"}},
                "_compose_chapters_done": True,
                "_awaiting_confirm": True,
            },
        ),
        "mode": "interactive", "user_intent": None, "pending_confirmations": [],
    }
    result = agent.step(state)
    assert result.context_patch["chapters"]["intro"]["prose"] == "New intro"
    assert fake_rewrite.invoke.called
```

- [ ] **Step 2: Run — should FAIL**

```bash
python -m pytest orchestrator/tests/agents/test_m5_rewrite.py -v 2>&1 | tail -15
```

- [ ] **Step 3: Add methods to `M5Agent` + update `step()`**

Replace the `step()` method in `M5Agent` (from Task 10) with the rewrite-aware version, and add the new helpers:

```python
    def step(self, state):
        """SP6: rewrite detection (when in confirm state) → compose phase → fallback."""
        from orchestrator.state import get_module_slice
        cls = type(self)
        partial = dict(get_module_slice(state["context_store"], self.module_key))
        cls._render_context = self._extract_context_slice(state["context_store"])

        # Rewrite path — fires BEFORE compose dispatch when in confirm state.
        if partial.get("_compose_chapters_done") and partial.get("_awaiting_confirm"):
            if self._is_rewrite_request(state["messages"]):
                return self._handle_rewrite(state, partial)
            # Affirmative confirm dispatch lands in Task 12 — fall through for now.

        # Compose phase — first M5 turn.
        if not partial.get("_compose_chapters_done"):
            return self._compose_all_chapters(state, partial)

        return super().step(state)

    def _is_rewrite_request(self, messages) -> bool:
        last = self._latest_user_message(messages).lower()
        return any(kw in last for kw in self._REWRITE_KEYWORDS)

    def _identify_chapter(self, user_msg: str) -> str | None:
        """Map common chapter aliases to the canonical name. None if ambiguous."""
        if not user_msg:
            return None
        text = user_msg.lower()
        # Longest alias first so "introduction" matches before "intro"
        for alias in sorted(self._CHAPTER_ALIASES.keys(), key=len, reverse=True):
            if alias in text:
                return self._CHAPTER_ALIASES[alias]
        return None

    def _handle_rewrite(self, state, partial):
        """Route the user's rewrite request to the target chapter."""
        last_user = self._latest_user_message(state["messages"])
        target = self._identify_chapter(last_user)
        if target is None:
            partial["_awaiting_confirm"] = True
            return ModuleStepResult(
                assistant_message=(
                    "Which chapter do you want me to rewrite? "
                    "(intro / lit_review / methodology / results / discussion / conclusion)"
                ),
                context_patch=partial,
                transition=False, needs_user_reply=True,
            )
        context = self._render_context or {}
        current = (partial.get("chapters") or {}).get(target, {}).get("prose", "")
        new_draft = rewrite_chapter.invoke({
            "chapter_name": target,
            "current_prose": current,
            "instruction": last_user,
            "context_slice": context,
            "references": self._collect_references(context),
            "language": context.get("language", "en"),
        })
        chapters = dict(partial.get("chapters", {}))
        chapters[target] = new_draft
        partial["chapters"] = chapters
        partial["_awaiting_confirm"] = True
        return ModuleStepResult(
            assistant_message=f"Rewrote chapter — {target}. Review below.",
            context_patch=partial,
            transition=False, needs_user_reply=True,
            extra_messages=[AIMessage(content=f"## Chapter — {target} (rewritten)\n\n{new_draft.get('prose', '')}")],
        )
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest orchestrator/tests/agents/test_m5_rewrite.py -v 2>&1 | tail -15
# Confirm earlier tests still pass
python -m pytest orchestrator/tests/agents/test_m5_compose.py orchestrator/tests/agents/test_m5_context_slice.py -v 2>&1 | tail -10
git add orchestrator/agents/m5_writing.py orchestrator/tests/agents/test_m5_rewrite.py
git commit -m "feat(orchestrator): M5Agent rewrite detection + _handle_rewrite + _identify_chapter"
```

Expected: 6 new rewrite tests + earlier tests PASS.

---

### Task 12: `_finalize_and_export` + step() confirm branch

**Files:**
- Modify: `orchestrator/agents/m5_writing.py`
- Create: `orchestrator/tests/agents/test_m5_finalize.py`

- [ ] **Step 1: Write the failing tests**

Create `orchestrator/tests/agents/test_m5_finalize.py`:

```python
"""Tests for M5Agent _finalize_and_export — confirm + export + transition."""
from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage

from orchestrator.agents.m5_writing import M5Agent
from orchestrator.state import ContextStore


def _build_full_partial():
    """A post-compose partial with all 6 chapters drafted."""
    chapters = {n: {"name": n, "prose": f"# {n}\nContent"}
                for n in ("intro", "lit_review", "methodology",
                          "results", "discussion", "conclusion")}
    return {
        "chapters": chapters,
        "bibliography": "Bass, A. (1990). Leadership.",
        "_compose_chapters_done": True,
        "_awaiting_confirm": True,
    }


def test_finalize_calls_export_tools_and_transitions(monkeypatch):
    from orchestrator.agents import m5_writing as m5_mod

    fake_docx = MagicMock()
    fake_docx.invoke.return_value = "projects/proj-xyz/exports/thesis-abc.docx"
    monkeypatch.setattr(m5_mod, "export_docx", fake_docx)

    fake_pdf = MagicMock()
    fake_pdf.invoke.return_value = "projects/proj-xyz/exports/thesis-abc.pdf"
    monkeypatch.setattr(m5_mod, "compile_pdf", fake_pdf)

    agent = M5Agent()
    partial = _build_full_partial()
    state = {
        "messages": [HumanMessage("yes")],
        "current_module": "M5", "project_id": "proj-xyz",
        "context_store": ContextStore(
            m1_topic={"research_title": "x", "language": "en"},
            m3_design={"paradigm": "quantitative", "confirmed_at": "x"},
            m5_writing=partial,
        ),
        "mode": "interactive", "user_intent": None, "pending_confirmations": [],
    }
    result = agent.step(state)

    # Both tools called with project_id
    assert fake_docx.invoke.called
    assert fake_pdf.invoke.called
    docx_call = fake_docx.invoke.call_args.args[0]
    assert docx_call["project_id"] == "proj-xyz"

    # export_artifacts populated
    artifacts = result.context_patch["export_artifacts"]
    assert len(artifacts) == 2
    kinds = {a["kind"] for a in artifacts}
    assert kinds == {"docx", "pdf"}
    docx_artifact = next(a for a in artifacts if a["kind"] == "docx")
    assert docx_artifact["s3_key"] == "projects/proj-xyz/exports/thesis-abc.docx"
    assert "thesis-abc.docx" in docx_artifact["download_url"]

    # confirmed_at stamped + transition=True
    assert result.context_patch["confirmed_at"] is not None
    assert result.transition is True


def test_finalize_emits_markdown_links(monkeypatch):
    from orchestrator.agents import m5_writing as m5_mod
    monkeypatch.setattr(m5_mod, "export_docx", MagicMock(invoke=lambda kw: "projects/p/exports/x.docx"))
    monkeypatch.setattr(m5_mod, "compile_pdf", MagicMock(invoke=lambda kw: "projects/p/exports/x.pdf"))

    agent = M5Agent()
    partial = _build_full_partial()
    state = {
        "messages": [HumanMessage("yes")],
        "current_module": "M5", "project_id": "p",
        "context_store": ContextStore(m5_writing=partial),
        "mode": "interactive", "user_intent": None, "pending_confirmations": [],
    }
    result = agent.step(state)
    assert "Download" in result.assistant_message
    assert "/api/v1/projects/p/exports/x.docx" in result.assistant_message
    assert "/api/v1/projects/p/exports/x.pdf" in result.assistant_message


def test_finalize_raises_without_project_id():
    """No project_id in state → finalize raises with clear message."""
    agent = M5Agent()
    partial = _build_full_partial()
    state = {
        "messages": [HumanMessage("yes")],
        "current_module": "M5",
        "project_id": "",  # explicitly empty
        "context_store": ContextStore(m5_writing=partial),
        "mode": "interactive", "user_intent": None, "pending_confirmations": [],
    }
    import pytest
    with pytest.raises(RuntimeError, match="project_id"):
        agent.step(state)
```

- [ ] **Step 2: Run — should FAIL**

```bash
python -m pytest orchestrator/tests/agents/test_m5_finalize.py -v 2>&1 | tail -15
```

- [ ] **Step 3: Update `step()` + add `_finalize_and_export` + helpers**

Replace the `step()` method in `M5Agent` with the version that includes the finalize branch:

```python
    def step(self, state):
        """SP6: rewrite detection → finalize on affirmative → compose phase → fallback."""
        from orchestrator.state import get_module_slice
        cls = type(self)
        partial = dict(get_module_slice(state["context_store"], self.module_key))
        cls._render_context = self._extract_context_slice(state["context_store"])

        # Confirm-state branches: rewrite OR affirmative-finalize.
        if partial.get("_compose_chapters_done") and partial.get("_awaiting_confirm"):
            if self._is_rewrite_request(state["messages"]):
                return self._handle_rewrite(state, partial)
            if self._is_affirmative(state["messages"]):
                return self._finalize_and_export(state, partial)

        if not partial.get("_compose_chapters_done"):
            return self._compose_all_chapters(state, partial)

        return super().step(state)
```

Add the finalize method + formatting helpers to `M5Agent`:

```python
    def _finalize_and_export(self, state, partial):
        """Compile docx + pdf, upload to S3, populate export_artifacts, transition."""
        project_id = str(state.get("project_id") or "")
        if not project_id:
            raise RuntimeError("M5 finalize requires project_id in state")

        sections_for_engine = self._build_sections_for_export(partial)
        docx_key = export_docx.invoke({
            "sections": sections_for_engine, "project_id": project_id,
        })
        pdf_key = compile_pdf.invoke({
            "sections": sections_for_engine, "project_id": project_id,
        })

        artifacts = [
            ExportArtifact(
                kind="docx", s3_key=docx_key,
                download_url=f"/api/v1/projects/{project_id}/exports/{docx_key.split('/')[-1]}",
                size_bytes=0,
            ),
            ExportArtifact(
                kind="pdf", s3_key=pdf_key,
                download_url=f"/api/v1/projects/{project_id}/exports/{pdf_key.split('/')[-1]}",
                size_bytes=0,
            ),
        ]
        partial["export_artifacts"] = [a.model_dump() for a in artifacts]
        partial["confirmed_at"] = datetime.now(timezone.utc).isoformat()
        return ModuleStepResult(
            assistant_message=self._format_export_artifacts_markdown(artifacts),
            context_patch=partial,
            transition=True,
            needs_user_reply=False,
        )

    def _build_sections_for_export(self, partial: dict) -> list[dict]:
        """Assemble the per-chapter section list passed to compile_pdf/export_docx."""
        chapters = partial.get("chapters", {})
        sections = [
            {"name": name, "text": chapters.get(name, {}).get("prose", "")}
            for name in _CHAPTER_ORDER
        ]
        if partial.get("bibliography"):
            sections.append({"name": "bibliography", "text": partial["bibliography"]})
        return sections

    def _format_export_artifacts_markdown(self, artifacts: list) -> str:
        lines = ["**Done.**", ""]
        for a in artifacts:
            label = {"docx": "Download thesis (.docx)",
                     "pdf": "Download thesis (.pdf)"}.get(a.kind, a.kind)
            filename = a.s3_key.split("/")[-1]
            lines.append(f"- 📄 {label}: [{filename}]({a.download_url})")
        lines.append("")
        lines.append("Thesis confirmed and exported. M1-M5 complete.")
        return "\n".join(lines)
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest orchestrator/tests/agents/test_m5_finalize.py -v 2>&1 | tail -15
# Confirm earlier M5 tests still pass
python -m pytest orchestrator/tests/agents/test_m5_compose.py orchestrator/tests/agents/test_m5_rewrite.py orchestrator/tests/agents/test_m5_context_slice.py -v 2>&1 | tail -10
git add orchestrator/agents/m5_writing.py orchestrator/tests/agents/test_m5_finalize.py
git commit -m "feat(orchestrator): M5Agent _finalize_and_export — confirm path uploads + transitions"
```

Expected: 3 new finalize tests + earlier M5 tests PASS.

---

## Phase F — Prompt + Subprocess

### Task 13: M5 system prompt rewrite

**Files:**
- Modify: `orchestrator/prompts/m5.md`

- [ ] **Step 1: Replace `orchestrator/prompts/m5.md`**

```markdown
# M5 — Writing & Export agent

You assemble the final thesis. The user has already confirmed M1 (topic), M2 (literature review), M3 (research design), and M4 (analysis). Your job:

## Compose phase (automatic on first M5 turn)

The agent batch-composes all 6 chapters in one operation using paradigm-aware prompt templates:
- Chapter 1: Introduction
- Chapter 2: Literature Review
- Chapter 3: Methodology
- Chapter 4: Results (paradigm-branched — quant tests/coefficients, qual Braun & Clarke themes, mixed both + integration)
- Chapter 5: Discussion
- Chapter 6: Conclusion

Each chapter is emitted as its own assistant message in the stream. A bibliography (formatted in apa7 from M2's reference pool) follows. A summary message at the end prompts the user to confirm or request a rewrite.

## When user replies after compose phase

- **Affirmative** ("yes", "confirm", "looks good", "go", "okay"): the agent calls `compile_pdf` + `export_docx`, uploads both to S3 under `projects/{project_id}/exports/`, populates `M5Output.export_artifacts`, stamps `confirmed_at`, and transitions. The final message contains markdown download links pointing to `/api/v1/projects/{project_id}/exports/{filename}`.
- **Rewrite request** ("rewrite chapter 3 to be less formal", "rephrase the intro", "expand the methodology"): the agent identifies the target chapter via alias map (intro / introduction / chapter 1 / ch1 → intro, etc.) and calls `rewrite_chapter` with the user's instruction + the current chapter's prose. The new chapter renders as its own bubble; the agent stays in confirm state for another round.
- **Ambiguous request**: the agent asks the user to clarify which chapter.

## Citation handling

Each chapter's compose prompt instructs the LLM to cite inline as `(Author, Year)` using only the M2 reference pool. After compose, `validate_citations` regex-scans the prose for cites; any reference NOT in the pool is flagged with a `⚠️ uncited` notice block at the end of the chapter. The bibliography includes a "Potentially missing citations" subsection listing the flagged references for user awareness.

## Auto-mode

In auto-mode the agent still calls `compile_pdf` + `export_docx`. S3 upload is mandatory in both interactive and auto-mode (no local-path fallback). The subprocess refuses to start without `AWS_S3_BUCKET` set.

## Tools

`compose_chapter`, `rewrite_chapter`, `compile_bibliography`, `validate_citations`, `format_citations`, `compile_pdf`, `export_docx`, `compose_section` (legacy), `validate_draft` (legacy).
```

- [ ] **Step 2: Verify the agent still constructs OK with the new prompt**

```bash
python -c "from orchestrator.agents.m5_writing import M5Agent; M5Agent()"
```

Expected: no output, exit 0.

- [ ] **Step 3: Commit**

```bash
git add orchestrator/prompts/m5.md
git commit -m "docs(orchestrator): M5 prompt rewrite for batch-compose + rewrite + auto-export"
```

---

### Task 14: Subprocess `AWS_S3_BUCKET` check + dev.sh comment

**Files:**
- Modify: `orchestrator/__main__.py`
- Modify: `orchestrator/tests/test_subprocess.py`
- Modify: `dev.sh`

- [ ] **Step 1: Append the failing test**

Append to `orchestrator/tests/test_subprocess.py`:

```python
def test_subprocess_refuses_without_aws_s3_bucket(monkeypatch):
    """SP6: subprocess must refuse to start without AWS_S3_BUCKET set, since
    M5 export is mandatory and S3-only."""
    import subprocess
    import sys
    monkeypatch.delenv("AWS_S3_BUCKET", raising=False)
    # Run the subprocess module as if it were invoked from CLI — it should
    # SystemExit with a clear message before doing any real work.
    result = subprocess.run(
        [sys.executable, "-m", "orchestrator", "--help"],
        capture_output=True, text=True, env={**os.environ, "AWS_S3_BUCKET": ""},
    )
    # SystemExit prints to stderr; the subprocess exits non-zero.
    # We accept either pattern depending on how `python -m` reports it.
    output = (result.stdout + result.stderr).lower()
    assert ("aws_s3_bucket" in output) or (result.returncode != 0)
```

Add `import os` to the test file imports if not already present.

- [ ] **Step 2: Run — should FAIL**

```bash
python -m pytest orchestrator/tests/test_subprocess.py::test_subprocess_refuses_without_aws_s3_bucket -v 2>&1 | tail -10
```

Expected: FAIL or PASS-by-accident if `--help` exits 0 without checking env. Either way, the next step makes it deterministic.

- [ ] **Step 3: Add the env check to `orchestrator/__main__.py`**

Read the existing `orchestrator/__main__.py`. Find the entry point (typically a `main()` or top-level guard). At the very top of `main()` (or just after argparse parses `args`), add:

```python
import os

def _require_aws_s3_bucket():
    """SP6: M5 export uploads to S3; refuse to start without a configured bucket."""
    if not os.environ.get("AWS_S3_BUCKET"):
        raise SystemExit(
            "AWS_S3_BUCKET env var is required for M5 export artifacts. "
            "Set it (e.g. AWS_S3_BUCKET=dothesis-dev) and re-run."
        )
```

Call `_require_aws_s3_bucket()` at the start of `main()` (or `if __name__ == "__main__":` block) BEFORE any other initialization.

- [ ] **Step 4: Update `dev.sh`**

Add a comment near the existing env-var section. Find a sensible location in `dev.sh` (after other env-var settings) and insert:

```bash
# SP6: M5 export uploads to S3 (mandatory for both interactive + auto-mode).
# Set AWS_S3_BUCKET=dothesis-dev (plus AWS_ACCESS_KEY + AWS_SECRET_KEY)
# in your .env. For local dev without real S3, run minio (https://min.io)
# and point AWS_* at it. The orchestrator subprocess refuses to start
# without AWS_S3_BUCKET.
```

- [ ] **Step 5: Run + commit**

```bash
python -m pytest orchestrator/tests/test_subprocess.py -v 2>&1 | tail -10
git add orchestrator/__main__.py orchestrator/tests/test_subprocess.py dev.sh
git commit -m "feat(orchestrator): subprocess refuses without AWS_S3_BUCKET + dev.sh note"
```

Expected: subprocess test PASS (or skip if test framework can't intercept the subprocess return).

---

## Phase G — API

### Task 15: `/api/v1/projects/{id}/exports/{filename}` endpoint + main.py wiring + tests

**Files:**
- Create: `api/app/routers/exports.py`
- Create: `api/tests/test_exports.py`
- Modify: `api/app/main.py`

- [ ] **Step 1: Write the failing tests**

Create `api/tests/test_exports.py`:

```python
"""Tests for the SP6 M5 export download endpoint."""
import os
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import ContextStore, Project, User
from app.security import create_session


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "true")
    monkeypatch.setenv("AWS_S3_BUCKET", "test-bucket")
    return TestClient(create_app(), follow_redirects=False)


def _setup_user_and_project(client) -> tuple[uuid.UUID, User]:
    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"u{uuid.uuid4().hex[:6]}@x",
                 username=f"u{uuid.uuid4().hex[:6]}",
                 password_hash="x", email_verified=True)
        db.add(u); db.commit(); db.refresh(u)
        token = create_session(db, u)
    client.cookies.set("dothesis_session", token)
    pid = client.post("/api/v1/projects", json={"name": "T"}).json()["id"]
    return uuid.UUID(pid), u


def _add_m5_artifact(project_id: uuid.UUID, filename: str):
    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, project_id)
        cs.m5_writing = {
            "export_artifacts": [
                {"kind": "docx",
                 "s3_key": f"projects/{project_id}/exports/{filename}",
                 "download_url": f"/api/v1/projects/{project_id}/exports/{filename}",
                 "size_bytes": 0,
                 "uri": ""},
            ],
        }
        db.commit()


def test_download_redirects_to_signed_url(client, monkeypatch):
    """Happy path — 302 to a fresh signed URL."""
    pid, _ = _setup_user_and_project(client)
    _add_m5_artifact(pid, "thesis-abc.docx")

    fake_s3 = MagicMock()
    fake_s3.generate_presigned_url.return_value = (
        "https://test-bucket.s3.amazonaws.com/projects/abc/exports/thesis-abc.docx?sig=xyz"
    )
    monkeypatch.setattr("app.routers.exports.s3_from_env", lambda: fake_s3)

    resp = client.get(f"/api/v1/projects/{pid}/exports/thesis-abc.docx")
    assert resp.status_code == 302
    assert resp.headers["location"].startswith("https://test-bucket.s3.amazonaws.com")
    # Signed URL was generated for the right key
    call_kwargs = fake_s3.generate_presigned_url.call_args.kwargs
    assert call_kwargs["Params"]["Key"] == f"projects/{pid}/exports/thesis-abc.docx"
    assert call_kwargs["ExpiresIn"] == 300


def test_download_404_when_filename_unknown(client, monkeypatch):
    pid, _ = _setup_user_and_project(client)
    _add_m5_artifact(pid, "thesis-abc.docx")
    monkeypatch.setattr("app.routers.exports.s3_from_env", lambda: MagicMock())
    resp = client.get(f"/api/v1/projects/{pid}/exports/wrong-filename.docx")
    assert resp.status_code == 404


def test_download_404_when_user_does_not_own_project(client, monkeypatch):
    pid, _ = _setup_user_and_project(client)
    _add_m5_artifact(pid, "thesis-abc.docx")
    # Switch to a different user
    sf = get_session_factory()
    with sf() as db:
        u2 = User(email=f"u2{uuid.uuid4().hex[:6]}@x",
                   username=f"u2{uuid.uuid4().hex[:6]}",
                   password_hash="x", email_verified=True)
        db.add(u2); db.commit(); db.refresh(u2)
        token2 = create_session(db, u2)
    client.cookies.set("dothesis_session", token2)
    resp = client.get(f"/api/v1/projects/{pid}/exports/thesis-abc.docx")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run — should FAIL**

```bash
cd /Users/caonguyenvan/project/dothesis/api && source .venv/bin/activate
python -m pytest tests/test_exports.py -v 2>&1 | tail -15
```

Expected: FAIL — endpoint doesn't exist.

- [ ] **Step 3: Create `api/app/routers/exports.py`**

```python
"""SP6: download endpoint for M5 export artifacts.

Mounted under /api/v1 by app/main.py only when ORCHESTRATOR_ENABLED=true.
Resolves the s3_key from the project's M5Output.export_artifacts and
302-redirects the browser to a fresh 5-minute signed URL.
"""
from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..db import db_session
from ..deps import current_user
from ..models import ContextStore, Project, User
from ..routers.uploads import s3_from_env

router = APIRouter(tags=["exports"])


def _owned_project(db: Session, user: User, project_id: uuid.UUID) -> Project:
    p = db.get(Project, project_id)
    if not p or p.user_id != user.id:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found"}},
        )
    return p


@router.get("/projects/{project_id}/exports/{filename}")
def download_export(
    project_id: uuid.UUID, filename: str,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    """302-redirect to a fresh 5-minute signed URL for the requested artifact."""
    _owned_project(db, user, project_id)
    cs = db.get(ContextStore, project_id)
    m5 = (cs.m5_writing or {}) if cs else {}
    artifacts = m5.get("export_artifacts") or []
    expected_key = f"projects/{project_id}/exports/{filename}"
    if not any(a.get("s3_key") == expected_key for a in artifacts):
        raise HTTPException(
            404, detail={"error": {"code": "artifact_not_found"}},
        )
    s3 = s3_from_env()
    signed_url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": os.environ["AWS_S3_BUCKET"], "Key": expected_key},
        ExpiresIn=300,
    )
    return RedirectResponse(url=signed_url, status_code=302)
```

- [ ] **Step 4: Mount the router in `api/app/main.py`**

Find the existing block that mounts the chat router when `ORCHESTRATOR_ENABLED=true`. Add the exports router alongside it:

```python
if os.getenv("ORCHESTRATOR_ENABLED", "").lower() == "true":
    from .routers.chat import router as chat_router
    from .routers.exports import router as exports_router    # SP6
    app.include_router(chat_router, prefix="/api/v1")
    app.include_router(exports_router, prefix="/api/v1")     # SP6
```

- [ ] **Step 5: Run + commit**

```bash
cd /Users/caonguyenvan/project/dothesis/api && source .venv/bin/activate
python -m pytest tests/test_exports.py -v 2>&1 | tail -15
cd /Users/caonguyenvan/project/dothesis
git add api/app/routers/exports.py api/app/main.py api/tests/test_exports.py
git commit -m "feat(api): /api/v1/projects/{id}/exports/{filename} endpoint with S3 signed-URL 302"
```

Expected: 3 new export tests PASS.

---

## Phase H — Wrap-up

### Task 16: M5 round-trip contract test

**Files:**
- Create: `api/tests/test_m5_round_trip.py`

- [ ] **Step 1: Write the test**

Create `api/tests/test_m5_round_trip.py`:

```python
"""Contract test: M5 rewrite-keyword user messages persist correctly and the
agent's next step() can detect them. No router or graph changes required."""
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import Message, User
from app.security import create_session


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "true")
    monkeypatch.setenv("AWS_S3_BUCKET", "test-bucket")
    return TestClient(create_app())


def _async_iter(items):
    async def _it():
        for x in items:
            yield x
    return _it()


def test_rewrite_request_persists_to_message_row(client, monkeypatch):
    """User sends 'rewrite chapter 3' → the chat router persists it as a user
    Message. Next agent step() would route to _handle_rewrite. No router code
    needs to change for SP6 — this test documents the contract."""
    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"u{uuid.uuid4().hex[:6]}@x",
                 username=f"u{uuid.uuid4().hex[:6]}",
                 password_hash="x", email_verified=True)
        db.add(u); db.commit()
        client.cookies.set("dothesis_session", create_session(db, u))
    pid = client.post("/api/v1/projects", json={"name": "T"}).json()["id"]
    tid = client.get(f"/api/v1/projects/{pid}/threads").json()[0]["id"]

    # Stub the graph to return one assistant ack and terminate; we don't need
    # the agent to actually run, we just want to verify the user message
    # is persisted with the rewrite keyword.
    from langchain_core.messages import AIMessage
    ai = AIMessage(content="acknowledged")
    fake_graph = MagicMock()
    fake_graph.astream.return_value = _async_iter([
        {"M5": {"messages": [ai]}},
    ])
    monkeypatch.setattr(
        "orchestrator.graph.get_interactive_graph", lambda: fake_graph,
    )

    resp = client.post(
        f"/api/v1/threads/{tid}/messages",
        json={"text": "rewrite chapter 3 to be less formal"},
    )
    assert resp.status_code == 200

    # The user's rewrite message is persisted as role="user"
    sf = get_session_factory()
    with sf() as db:
        users_msgs = (
            db.query(Message)
              .filter_by(thread_id=tid, role="user")
              .order_by(Message.id)
              .all()
        )
        assert any("rewrite chapter 3" in m.content.lower() for m in users_msgs)
```

- [ ] **Step 2: Run + commit**

```bash
cd /Users/caonguyenvan/project/dothesis/api && source .venv/bin/activate
python -m pytest tests/test_m5_round_trip.py -v 2>&1 | tail -10
cd /Users/caonguyenvan/project/dothesis
git add api/tests/test_m5_round_trip.py
git commit -m "test(api): M5 rewrite-keyword message persistence (contract coverage)"
```

Expected: 1 test PASS.

---

### Task 17: Update existing auto-mode test for new schema

**Files:**
- Modify: `orchestrator/tests/test_agents_m5.py`

- [ ] **Step 1: Read the existing test**

```bash
cat /Users/caonguyenvan/project/dothesis/orchestrator/tests/test_agents_m5.py
```

The existing `test_m5_auto_produces_outline_and_results` stubs the LLM with a payload using the old `sections` shape. The new schema requires `chapters` dict + `export_artifacts` with docx when `confirmed_at` is set.

- [ ] **Step 2: Replace the test**

Replace the file body:

```python
"""Auto-mode roundtrip test for M5 agent — validates schema-driven auto-fill
against the SP6 chapter-based schema."""
from datetime import datetime, timezone
from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage

from orchestrator.agents.m5_writing import M5Agent
from orchestrator.state import ContextStore


def test_m5_auto_produces_chapters_and_artifacts(monkeypatch):
    """In auto mode, _auto_fill asks the LLM for the full M5Output payload.
    SP6 expects `chapters` (dict keyed by chapter name) + at least one docx
    artifact when confirmed."""
    chapters = {n: {"name": n, "prose": f"# {n}\nContent"}
                for n in ("intro", "lit_review", "methodology",
                          "results", "discussion", "conclusion")}
    fake = MagicMock()
    fake.invoke.return_value.content = (
        '{"chapters":' + str(chapters).replace("'", '"') + ','
        '"bibliography":"Bass, A. (1990).",'
        '"export_artifacts":[{"kind":"docx","s3_key":"projects/p/exports/x.docx",'
        '"download_url":"/api/v1/projects/p/exports/x.docx","size_bytes":1}],'
        '"sections":[]}'
    )
    monkeypatch.setattr(M5Agent, "_get_llm", lambda self: fake)
    state = {
        "messages": [HumanMessage(content="export")],
        "current_module": "M5",
        "project_id": "p",
        "context_store": ContextStore(),
        "mode": "auto",
        "user_intent": None,
        "pending_confirmations": [],
    }
    res = M5Agent().step(state)
    assert res.transition is True
    assert "chapters" in res.context_patch
    # All 6 chapter keys present (validator requires this on confirm)
    assert set(res.context_patch["chapters"].keys()) == {
        "intro", "lit_review", "methodology", "results", "discussion", "conclusion",
    }
```

- [ ] **Step 3: Run + commit**

```bash
python -m pytest orchestrator/tests/test_agents_m5.py -v 2>&1 | tail -10
git add orchestrator/tests/test_agents_m5.py
git commit -m "test(orchestrator): update M5 auto-mode test for SP6 chapter-based schema"
```

Expected: 1 PASS.

---

### Task 18 (optional): Frontend integration test

**Files:**
- Modify: `web/app/components/chat/ChatPane.test.tsx`

Skip this task if the regression run in Task 19 passes without it. The SP4/SP5 integration tests already cover the chat surface; SP6 introduces no new widgets or events.

If you choose to add the optional test:

- [ ] **Step 1: Append to `web/app/components/chat/ChatPane.test.tsx`**

```typescript
describe("ChatPane M5 download links", () => {
  test("renders markdown download links in final assistant bubble", async () => {
    server.use(
      http.get("/api/v1/projects/p1", () => HttpResponse.json({
        name: "Test Project",
        context_store: { m1_topic: null },
      })),
      http.get("/api/v1/threads/t1", () => HttpResponse.json({ name: "Main" })),
      http.get("/api/v1/projects/p1/runs", () => HttpResponse.json({ run: null })),
      http.get("/api/v1/threads/t1/messages", () => HttpResponse.json([
        {
          id: 1,
          role: "assistant",
          content: (
            "**Done.**\n\n"
            "- 📄 Download thesis (.docx): [thesis-abc.docx](/api/v1/projects/p1/exports/thesis-abc.docx)\n"
            "- 📄 Download thesis (.pdf):  [thesis-abc.pdf](/api/v1/projects/p1/exports/thesis-abc.pdf)\n\n"
            "Thesis confirmed and exported. M1-M5 complete."
          ),
          created_at: "2026-05-27T00:00:00Z",
        },
      ])),
    );
    renderFresh(<ChatPane projectId="p1" threadId="t1" />);
    await waitFor(() => expect(screen.getByText(/Thesis confirmed/i)).toBeTruthy());
    // The link text should be visible in the markdown
    expect(screen.getByText(/thesis-abc.docx/)).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run + commit**

```bash
cd /Users/caonguyenvan/project/dothesis/web && npm test -- ChatPane 2>&1 | tail -10
cd /Users/caonguyenvan/project/dothesis
git add web/app/components/chat/ChatPane.test.tsx
git commit -m "test(web): ChatPane M5 download-link rendering"
```

Expected: 4 existing + 1 new = 5 PASS.

---

### Task 19: Regression + roadmap flip

**Files:**
- Modify: `docs/superpowers/2026-05-26-platform-pivot-roadmap.md`

- [ ] **Step 1: Run all three regression suites**

```bash
cd /Users/caonguyenvan/project/dothesis && source api/.venv/bin/activate

echo "=== orchestrator ==="
python -m pytest orchestrator/tests/ -q --no-header --tb=no 2>&1 | tail -3

echo "=== api ==="
cd api && python -m pytest tests/ -q --no-header --tb=no 2>&1 > /tmp/sp6_api_full.txt
tail -3 /tmp/sp6_api_full.txt
cd ..

echo "=== web ==="
cd web && npm test 2>&1 | tail -3
cd ..
```

Expected:
- Orchestrator: 204 (SP5 baseline) + new SP6 tests = ~240+ pass; 0 NEW failures
- API: 52 baseline failures unchanged; 109 (SP5) + ~5 new = ~114 pass
- Web: 107 (SP5) + optional ~1 new = 107-108 pass

- [ ] **Step 2: Diff API failures vs baseline**

```bash
cd /Users/caonguyenvan/project/dothesis
grep -E "^(FAILED|ERROR)" /tmp/sp6_api_full.txt | sort -u > /tmp/sp6_current.txt
grep -E "^(FAILED|ERROR)" /Users/caonguyenvan/project/dothesis/.baseline_failures_2026-05-26.txt | sort -u > /tmp/sp6_baseline.txt
echo "NEW failures from SP6 (must be empty):"
comm -23 /tmp/sp6_current.txt /tmp/sp6_baseline.txt
```

Expected: zero new failures.

- [ ] **Step 3: Flip roadmap status**

Edit `docs/superpowers/2026-05-26-platform-pivot-roadmap.md`:

Find the ASCII sub-project map and update `6. M5 writing` to add ✅:

```
2. M2 chat✅ 3. M1 topic ✅ 4. M3 design ✅ 5. M4 analysis ✅ 6. M5 writing ✅ 7. New chat UI ✅
```

Replace the `## Sub-project 6 — M5 Writing & Finalization (auto-fill + new editor) ⬜` section header with:

```
## Sub-project 6 — M5 Writing & Finalization ✅

**Status:** Shipped 2026-05-27 (branch `feat/sp6-m5-writing`; batch chapter compose + S3 export + NL rewrite)

**Spec:** `docs/superpowers/specs/2026-05-27-sp6-m5-writing-design.md`
**Plan:** `docs/superpowers/plans/2026-05-27-sp6-m5-writing-plan.md`

**Delivers:**
- Single `M5Agent` batch-composes 6 chapters via paradigm-aware LLM prompts (`orchestrator/prompts/m5/<name>.md`); paradigm-branched Chapter 4 closes the SP5-deferred Braun & Clarke writeup
- Per-chapter `AIMessage` emission via SP5's `extra_messages`; bibliography + summary as additional bubbles
- NL keyword detection routes rewrites ("rewrite chapter 3 to be less formal") to `rewrite_chapter` LLM tool; `_identify_chapter` alias map covers en + chapter-number forms
- Auto-export on affirmative confirm: `compile_pdf` + `export_docx` upload to S3 (mandatory for both interactive and auto-mode), `ExportArtifact` stores `s3_key` + `download_url`
- New `GET /api/v1/projects/{id}/exports/{filename}` endpoint resolves s3_key → 5-min signed URL → 302 redirect
- Inline citation validation: regex-scan prose for (Author, Year) patterns, flag uncited, append notice block
- Subprocess refuses to start without `AWS_S3_BUCKET`
- No frontend changes — chapters render as markdown bubbles in existing `MessageBubble`

**Decisions worth remembering for post-pivot work:**
- Pure-LLM chapter composition via per-chapter prompts is the chat-native path; engine compose is the auto-mode fallback (now identical behavior since both paths upload to S3)
- Citation validation as a regex post-pass (not LLM judging itself) gives auditable provenance with `parser`-style provenance flag analog
- S3 keys (persistent) vs signed URLs (per-request, 5 min) — the right separation for shareable + secure artifact serving

**Out of scope (deferred):**
- WYSIWYG section editor, inline paraphrase / translate / cite tools → SP6.5
- Citation Manager UI (style switching, Zotero/Mendeley) → SP6.6 / Phase 3
- LaTeX / Google Docs export → Post-pivot
- Slash commands (`/cite`, `/translate`, `/explain`) → Post-pivot
```

Append to the Status log:

```
| 2026-05-27 | 6 | ⬜ → ✅ | M5 writing shipped — batch chapter compose + S3 export + NL rewrite; pivot COMPLETE (SP1-SP7 all ✅) |
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/2026-05-26-platform-pivot-roadmap.md
git commit -m "docs: SP6 shipped — roadmap flip to ✅ — pivot COMPLETE"
```

---

## Done criteria checklist

- [ ] All 19 tasks committed in order on branch `feat/sp6-m5-writing`
- [ ] All web tests pass (`cd web && npm test`)
- [ ] All orchestrator tests pass (`python -m pytest orchestrator/tests/ -q`)
- [ ] API tests show only baseline failures + new tests passing (diff vs `.baseline_failures_2026-05-26.txt` is empty)
- [ ] `npm run build` succeeds in `web/`
- [ ] Roadmap flipped to ✅ for SP6
- [ ] End-to-end manual smoke (optional): start `./dev.sh` with `AWS_S3_BUCKET` set, walk through M1-M4 in `/chat`, advance to M5, watch 8 chapter+bib bubbles stream in, confirm "yes", get 2 download links, click and verify the docx + pdf download

---

## What's next after SP6 ships

**Pivot complete.** All 7 sub-projects (SP1 orchestration foundation + SP2 M2 chat-first + SP3 M1 card-grid + SP4 M3 multi-method + SP5 M4 adaptive analysis + SP6 M5 writing + SP7 chat UI shell) ship on master. The chat-based research copilot is end-to-end usable for quant, qual, and mixed master's-thesis flows.

**SP6.5 — M5 editor surface.** WYSIWYG section editor with inline paraphrase / translate / cite-insert affordances. Reuses SP6's `chapters` storage shape unchanged.

**SP6.6 — Citation Manager UI.** Style switching (APA7 ↔ Vancouver ↔ Chicago), dedupe, Zotero/Mendeley import. Builds on SP6's `compile_bibliography` + existing `format_citations` tool.

**Post-pivot cleanups.** Retire engine-fallback wrappers (`_compose_section_via_engine`, etc.) once interactive M5 is validated; promote `M5Output.export_artifacts` JSONB entries to a dedicated `artifacts` DB table with audit log.

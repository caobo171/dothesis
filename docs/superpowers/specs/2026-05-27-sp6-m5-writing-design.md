# SP6 — M5 Writing & Finalization Design Spec

**Date:** 2026-05-27
**Owner:** Cao Nguyen
**Parent roadmap:** `docs/superpowers/2026-05-26-platform-pivot-roadmap.md` (Sub-project 6)
**Depends on:** SP1 (orchestration), SP2 (S3 upload infra), SP3 (widget protocol), SP4 (list_editor + paradigm-aware ModuleAgent pattern), SP5 (extra_messages + ad-hoc detection pattern)
**Status:** 🟡 (designed; awaiting plan)

---

## Goal

Make M5 produce a complete-enough end-to-end thesis (6 chapters + bibliography + S3-hosted docx/pdf) from M1-M4 inputs alone, via chat-native batch-compose + per-chapter sequential rendering. Paradigm-aware Chapter 4 closes the SP5-deferred Braun & Clarke writeup gap. NL keyword detection enables per-chapter rewrites. Auto-export on final confirm.

**Explicit non-goal for SP6:** WYSIWYG editor, inline paraphrase/translate/cite tools, Citation Manager UI, LaTeX/Google Docs export. Each lands as a follow-up sub-project (SP6.5+) once the chat-native chapter flow is proven.

---

## Locked decisions (from brainstorming)

| # | Question | Answer |
|---|---|---|
| Scope | Sub-project scope | **B.** Chapter-by-chapter approve flow + qual writeup + engine integration. Defer paraphrase/translate/editor UI to SP6.5. |
| Q1 | Per-chapter approval mechanic | **B.** Batch compose all 6 chapters + emit each as own AIMessage via SP5's `extra_messages` pattern. One confirm at the end. |
| Q2 | Per-chapter composition strategy | **A.** Pure LLM per chapter with chapter-specific prompt templates. Paradigm-aware Chapter 4. |
| Q3 | Citation handling | **A.** LLM-prompted inline citations + post-compose validation pass (regex scan, flag uncited) + bibliography compile from M2 reference pool. |
| Q4 | Rewrite + Export triggers | **A.** NL keyword detection routes to `rewrite_chapter` (mirrors SP5 ad-hoc pattern). Auto-export on affirmative confirm. |
| Q-S3 | Artifact serving | **S3 mandatory for both interactive + auto-mode.** No local-path fallback. New `GET /api/v1/projects/{id}/exports/{filename}` endpoint generates 5-minute signed URLs via 302 redirect. |

---

## Architecture

Single `M5Agent` extends the SP3/SP4/SP5 ModuleAgent pattern. M5 has no upstream user fields — everything comes from `context_store.m1_topic` / `.m2_literature` / `.m3_design` / `.m4_analysis`. The agent's `step()` checks `_compose_chapters_done` directly (no field walk); on first turn it enters compose phase, batches all chapter compositions into one call, emits each chapter (+ bibliography + summary) as its own `AIMessage` via SP5's `extra_messages` field, sets `_awaiting_confirm=True`.

The next user turn either:
- **confirms** → `_finalize_and_export` calls `compile_pdf` + `export_docx` (both upload to S3 + return s3_key), populates `M5Output.export_artifacts`, stamps `confirmed_at`, transitions to DONE
- **requests a rewrite** ("rewrite chapter 3 to be less formal") → keyword detection routes to `_handle_rewrite`, agent identifies target chapter via alias map, calls `rewrite_chapter` LLM tool, emits the new chapter bubble, stays in confirm state

Each chapter composes via one LLM call with a chapter-specific prompt template (`orchestrator/prompts/m5/<name>.md`). The agent assembles the relevant `context_store` slice + M2 reference pool + paradigm + language into the prompt. Chapter 4 (`results.md`) branches on `m3.paradigm`: quant reads `m4.results`, qual reads `m4.qual_codes + qual_themes` (Braun & Clarke writeup), mixed includes both with an integration paragraph.

Each chapter's compose-prompt instructs the LLM to cite inline as `(Author, Year)` using only the supplied M2 reference pool. After compose, a `validate_citations` regex pass extracts `(Author, Year)` patterns from the prose; any cite not present in the pool is marked `⚠️ uncited` inline. The bibliography section lists the pool refs plus a "Potentially missing citations" subsection.

`compile_pdf` and `export_docx` are mandatory S3-upload tools — both interactive and auto-mode paths upload to `s3://bucket/projects/{project_id}/exports/{filename}` (no local-path fallback). The agent stores `s3_key` + a relative `download_url` in `ExportArtifact`. A new `GET /api/v1/projects/{id}/exports/{filename}` endpoint resolves the s3_key + generates a 5-minute signed URL + 302-redirects the browser to it.

No frontend changes. Chapters render as long markdown bubbles in existing `MessageBubble`; download links render as standard markdown anchors in the final bubble.

---

## File map

### NEW backend files

```
orchestrator/prompts/m5/intro.md                       # chapter prompts (6 files)
orchestrator/prompts/m5/lit_review.md
orchestrator/prompts/m5/methodology.md
orchestrator/prompts/m5/results.md                     # paradigm-branched (quant + qual + mixed)
orchestrator/prompts/m5/discussion.md
orchestrator/prompts/m5/conclusion.md
orchestrator/tests/agents/test_m5_compose.py
orchestrator/tests/agents/test_m5_rewrite.py
orchestrator/tests/agents/test_m5_finalize.py
orchestrator/tests/agents/test_m5_context_slice.py
api/app/routers/exports.py                             # GET /projects/{id}/exports/{filename}
api/tests/test_exports.py
api/tests/test_m5_round_trip.py                        # rewrite-trigger contract test
```

### MODIFIED backend files

```
orchestrator/agents/m5_writing.py                      # full rewrite — compose + finalize + rewrite detection
orchestrator/schemas/m5.py                             # add ChapterDraft + extend M5Output + @model_validator
orchestrator/tools/m5_writing.py                       # add compose_chapter + rewrite_chapter + validate_citations + compile_bibliography + _upload_to_s3; compile_pdf/export_docx now require project_id + upload to S3
orchestrator/prompts/m5.md                             # rewrite — chapter-by-chapter + auto-export + rewrite guidance
orchestrator/tests/test_schemas.py                     # extend with M5Output validator tests
orchestrator/tests/test_tools_m5.py                    # extend with new-tool tests + S3 upload tests
orchestrator/tests/test_agents_m5.py                   # update existing auto-mode for new schema shape
orchestrator/tests/test_subprocess.py                  # extend — refuse start without AWS_S3_BUCKET
orchestrator/__main__.py                               # add AWS_S3_BUCKET env-var check at startup
api/app/main.py                                        # mount exports router when ORCHESTRATOR_ENABLED=true
dev.sh                                                 # comment near env-var section noting AWS_S3_BUCKET requirement
```

### NEW frontend files

(none)

### MODIFIED frontend files

```
web/app/components/chat/ChatPane.test.tsx              # OPTIONAL — one test for download-link rendering. Skip if low signal.
```

### MODIFIED docs

```
docs/superpowers/2026-05-26-platform-pivot-roadmap.md  # flip SP6 to ✅
```

---

## Schema — `orchestrator/schemas/m5.py`

```python
"""M5 Writing & Finalization output schema (SP6 — chapter-by-chapter compose + S3 export)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


ChapterName = Literal["intro", "lit_review", "methodology", "results", "discussion", "conclusion"]


class ChapterDraft(BaseModel):
    """One composed chapter with provenance info."""
    name: ChapterName
    prose: str                              # full chapter markdown
    citations_used: list[str] = Field(default_factory=list)        # (Author, Year) found in pool
    uncited_warnings: list[str] = Field(default_factory=list)      # (Author, Year) NOT in pool


class ExportArtifact(BaseModel):
    kind: Literal["docx", "pdf", "latex", "md"]
    s3_key: str                             # e.g. projects/abc/exports/thesis-xyz.docx
    download_url: str                       # e.g. /api/v1/projects/abc/exports/thesis-xyz.docx
    size_bytes: int = Field(..., ge=0)
    # Existing field — DEPRECATED, kept for back-compat with auto-mode readers
    uri: str = ""


class M5Output(BaseModel):
    chapters: dict[str, dict] = Field(default_factory=dict)        # chapter_name → ChapterDraft dict
    bibliography: str = ""
    export_artifacts: list[ExportArtifact] = Field(default_factory=list)
    # Existing — preserved for back-compat with engine-fallback auto-mode
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

---

## Agent — `M5Agent`

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


_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
_PROMPT = (_PROMPT_DIR / "m5.md").read_text()

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
        # intro
        "intro": "intro", "introduction": "intro", "chapter 1": "intro", "ch1": "intro", "ch 1": "intro",
        # lit_review
        "lit review": "lit_review", "lit_review": "lit_review", "literature": "lit_review",
        "literature review": "lit_review", "chapter 2": "lit_review", "ch2": "lit_review", "ch 2": "lit_review",
        # methodology
        "methodology": "methodology", "methods": "methodology", "method": "methodology",
        "chapter 3": "methodology", "ch3": "methodology", "ch 3": "methodology",
        # results
        "results": "results", "findings": "results", "analysis": "results",
        "chapter 4": "results", "ch4": "results", "ch 4": "results",
        # discussion
        "discussion": "discussion", "chapter 5": "discussion", "ch5": "discussion", "ch 5": "discussion",
        # conclusion
        "conclusion": "conclusion", "concluding": "conclusion",
        "chapter 6": "conclusion", "ch6": "conclusion", "ch 6": "conclusion",
    }

    # SP6 class-level caches
    _render_context: dict | None = None

    def step(self, state):
        from orchestrator.state import get_module_slice
        cls = type(self)
        partial = dict(get_module_slice(state["context_store"], self.module_key))
        cls._render_context = self._extract_context_slice(state["context_store"])

        # Rewrite + confirm detection — fires BEFORE compose dispatch when in confirm state.
        if partial.get("_compose_chapters_done") and partial.get("_awaiting_confirm"):
            if self._is_rewrite_request(state["messages"]):
                return self._handle_rewrite(state, partial)
            if self._is_affirmative(state["messages"]):
                return self._finalize_and_export(state, partial)

        # Compose phase — first M5 turn always lands here.
        if not partial.get("_compose_chapters_done"):
            return self._compose_all_chapters(state, partial)

        return super().step(state)

    def render_hint_for_field(self, field_name: str) -> dict | None:
        return None  # SP6 has no widgets; prose renders as plain markdown

    def _extract_context_slice(self, cs) -> dict:
        """Build a clean dict for compose-chapter prompts to interpolate from."""
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

    def _compose_all_chapters(self, state, partial):
        """Loop chapters, compose each, emit one AIMessage per chapter + bibliography + summary."""
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
        partial["_summary_done"] = True  # SP5-pattern: summary message IS the summary step
        summary = self._build_compose_summary(chapters, references)
        return ModuleStepResult(
            assistant_message=summary,
            context_patch=partial,
            transition=False, needs_user_reply=True,
            extra_messages=extras,
        )

    def _handle_rewrite(self, state, partial):
        """Route the user's rewrite request to the target chapter."""
        last_user = self._latest_user_message(state["messages"])
        target = self._identify_chapter(last_user)
        if target is None:
            # Couldn't identify; ask the user to clarify, stay in confirm.
            partial["_awaiting_confirm"] = True
            return ModuleStepResult(
                assistant_message=(
                    "Which chapter do you want me to rewrite? "
                    "(intro / lit_review / methodology / results / discussion / conclusion)"
                ),
                context_patch=partial,
                transition=False, needs_user_reply=True,
            )
        current = partial.get("chapters", {}).get(target, {}).get("prose", "")
        new_draft = rewrite_chapter.invoke({
            "chapter_name": target,
            "current_prose": current,
            "instruction": last_user,
            "context_slice": self._render_context or {},
            "references": self._collect_references(self._render_context or {}),
            "language": (self._render_context or {}).get("language", "en"),
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

    def _finalize_and_export(self, state, partial):
        """Compile artifacts, upload to S3, populate export_artifacts, transition."""
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

    # --- helpers (small) ---

    def _is_rewrite_request(self, messages) -> bool:
        last = self._latest_user_message(messages).lower()
        return any(kw in last for kw in self._REWRITE_KEYWORDS)

    def _identify_chapter(self, user_msg: str) -> str | None:
        text = user_msg.lower()
        for alias, canonical in self._CHAPTER_ALIASES.items():
            if alias in text:
                return canonical
        return None  # caller asks user to clarify

    def _latest_user_message(self, messages) -> str:
        return next(
            (m.content for m in reversed(messages) if isinstance(m, HumanMessage)),
            "",
        )

    def _collect_references(self, context: dict) -> list[dict]:
        """Dedupe supporting_papers across all M2 research_gaps."""
        seen: dict[tuple[str, str], dict] = {}
        for gap in context.get("research_gaps", []):
            for paper in gap.get("supporting_papers", []):
                key = (paper.get("author", ""), str(paper.get("year", "")))
                if key not in seen:
                    seen[key] = paper
        return list(seen.values())

    def _build_compose_summary(self, chapters: dict, references: list) -> str:
        n_uncited = sum(len(c.get("uncited_warnings") or []) for c in chapters.values())
        msg = [
            f"Drafted all 6 chapters + bibliography ({len(references)} unique references).",
        ]
        if n_uncited:
            msg.append(f"⚠️ {n_uncited} inline citations flagged as potentially missing from the reference pool.")
        msg.append("Confirm to export to docx + pdf, or ask for a rewrite (e.g. 'rewrite chapter 3 to be less formal').")
        return "\n\n".join(msg)

    def _build_sections_for_export(self, partial: dict) -> list[dict]:
        chapters = partial.get("chapters", {})
        sections = [
            {"name": name, "text": chapters.get(name, {}).get("prose", "")}
            for name in _CHAPTER_ORDER
        ]
        if partial.get("bibliography"):
            sections.append({"name": "bibliography", "text": partial["bibliography"]})
        return sections

    def _format_export_artifacts_markdown(self, artifacts: list[ExportArtifact]) -> str:
        lines = ["**Done.**", ""]
        for a in artifacts:
            label = {"docx": "Download thesis (.docx)", "pdf": "Download thesis (.pdf)"}.get(a.kind, a.kind)
            filename = a.s3_key.split("/")[-1]
            lines.append(f"- 📄 {label}: [{filename}]({a.download_url})")
        lines.append("")
        lines.append("Thesis confirmed and exported. M1-M5 complete.")
        return "\n".join(lines)
```

---

## New tools — `orchestrator/tools/m5_writing.py`

Existing tools (`compose_section`, `validate_draft`, `format_citations`) stay untouched. The file gains:

```python
import boto3   # at top, alongside existing imports
from uuid import uuid4


def s3_from_env():
    """S3 client factory — mirrors the SP2 uploads.py pattern. Indirection point for tests."""
    return boto3.client(
        "s3",
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_KEY"),
    )


def _upload_to_s3(local_path: str, project_id: str, kind: str, filename: str) -> str:
    """Upload a local artifact to S3 under projects/{project_id}/exports/.
    Returns the s3_key. Deletes the local file after upload."""
    s3 = s3_from_env()
    bucket = os.environ["AWS_S3_BUCKET"]
    s3_key = f"projects/{project_id}/exports/{filename}"
    content_type = {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pdf":  "application/pdf",
    }[kind]
    with open(local_path, "rb") as f:
        s3.put_object(Bucket=bucket, Key=s3_key, Body=f.read(), ContentType=content_type)
    Path(local_path).unlink(missing_ok=True)
    return s3_key


@tool
def compose_chapter(chapter_name: str, paradigm: str, context_slice: dict,
                     references: list[dict], citation_style: str, language: str) -> dict:
    """Compose one chapter via LLM. Returns ChapterDraft dict with prose + citations_used + uncited_warnings."""
    prompt_template = (_PROMPT_DIR / "m5" / f"{chapter_name}.md").read_text()
    refs_block = _format_references_for_prompt(references)
    prompt = prompt_template.format(
        paradigm=paradigm, language=language, citation_style=citation_style,
        references_list=refs_block,
        **{k: json.dumps(v, ensure_ascii=False, default=str) if isinstance(v, (dict, list)) else (v or "")
           for k, v in context_slice.items() if k != "language"},
    )
    try:
        prose = _get_llm().invoke(prompt).content.strip()
    except Exception as e:
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


@tool
def rewrite_chapter(chapter_name: str, current_prose: str, instruction: str,
                     context_slice: dict, references: list[dict], language: str) -> dict:
    """Rewrite a chapter per user instruction. Returns new ChapterDraft dict."""
    prompt_template = (_PROMPT_DIR / "m5" / f"{chapter_name}.md").read_text()
    refs_block = _format_references_for_prompt(references)
    prompt = (
        f"{prompt_template.format(paradigm=context_slice.get('paradigm', 'quantitative'), language=language, citation_style='apa7', references_list=refs_block, **_safe_format_kwargs(context_slice))}\n\n"
        f"## User rewrite instruction\n{instruction}\n\n"
        f"## Current chapter prose (rewrite based on the instruction; preserve good content):\n{current_prose}\n\n"
        f"Output ONLY the rewritten chapter prose."
    )
    try:
        prose = _get_llm().invoke(prompt).content.strip()
    except Exception as e:
        logger.warning("rewrite_chapter LLM call failed for %s: %s", chapter_name, e)
        prose = current_prose  # unchanged on failure
    cited_in_pool, uncited = validate_citations(prose, references)
    if uncited:
        prose = _annotate_uncited(prose, uncited)
    return {
        "name": chapter_name, "prose": prose,
        "citations_used": cited_in_pool, "uncited_warnings": uncited,
    }


def validate_citations(prose: str, references: list[dict]) -> tuple[list[str], list[str]]:
    """Regex-scan prose for (Author, Year) patterns. Return (cited_in_pool, uncited)."""
    pattern = re.compile(r"\((?P<author>[A-Z][\w-]+(?: et al\.)?), (?P<year>\d{4})\)")
    pool = {(r.get("author", ""), str(r.get("year", ""))) for r in references}
    cited_in_pool: list[str] = []
    uncited: list[str] = []
    for m in pattern.finditer(prose):
        key = (m.group("author"), m.group("year"))
        label = f"{m.group('author')}, {m.group('year')}"
        if key in pool:
            if label not in cited_in_pool:
                cited_in_pool.append(label)
        else:
            if label not in uncited:
                uncited.append(label)
    return cited_in_pool, uncited


@tool
def compile_bibliography(references: list[dict], citation_style: str) -> str:
    """Format M2 references as a bibliography section. Uses existing CitationCompiler."""
    formatted = CitationCompiler(citation_style).compile(references)
    return formatted or "(No references)"


@tool
def compile_pdf(sections: list[dict], project_id: str) -> str:
    """Render sections to PDF, upload to S3, return s3_key."""
    if not project_id:
        raise ValueError("compile_pdf requires project_id")
    local_path = _scratch_dir() / f"thesis-{uuid4().hex[:8]}.pdf"
    _compile_pdf_via_engine(sections, str(local_path))
    return _upload_to_s3(str(local_path), project_id, "pdf", local_path.name)


@tool
def export_docx(sections: list[dict], project_id: str) -> str:
    """Render sections to DOCX, upload to S3, return s3_key."""
    if not project_id:
        raise ValueError("export_docx requires project_id")
    local_path = _scratch_dir() / f"thesis-{uuid4().hex[:8]}.docx"
    _export_docx_via_engine(sections, str(local_path))
    return _upload_to_s3(str(local_path), project_id, "docx", local_path.name)
```

---

## Chapter prompts — `orchestrator/prompts/m5/`

Each prompt file is 30-80 lines. Structure (using `methodology.md` as example):

```markdown
# Compose Chapter 3 — Methodology

You are writing Chapter 3 (Methodology) of a master's thesis.

## Inputs (interpolated from context_store)
- Research title: {research_title}
- Paradigm: {paradigm}
- Research design: {design}
- Analysis tool: {tool}
- Conceptual model (quant): {conceptual_model}
- Themes (qual): {themes}
- Scale items (quant): {scale_items}
- Interview guide structure (qual): {interview_guide}
- Sampling: {sampling_strategy}, N={target_sample_size}, criteria={purposive_criteria}
- Mixed design type (mixed only): {mixed_design_type}
- Language: {language}
- Citation style: {citation_style}

## References available for citation
{references_list}

## Instructions
- For quantitative: write sections 3.1 (research design rationale), 3.2 (population + sampling), 3.3 (instrument + measurement model), 3.4 (data collection procedure), 3.5 (data analysis approach with tool justification).
- For qualitative: 3.1 (research approach + Braun & Clarke justification), 3.2 (purposive sampling rationale + criteria), 3.3 (interview guide structure with example probes), 3.4 (data collection logistics), 3.5 (thematic analysis 6-step procedure).
- For mixed: include both sub-flows above + a 3.6 integration section explaining sequencing.
- Cite inline as (Author, Year) using ONLY the references above. Do not invent citations.
- Write in {language}. Academic prose. 800-1500 words total.

Output: Chapter 3 prose as markdown only — no preamble, no explanation.
```

`results.md` similarly has explicit paradigm branches; for qual it prescribes the Braun & Clarke writeup pattern (theme-by-theme prose with verbatim quotes from `qual_codes`).

---

## API endpoint — `api/app/routers/exports.py`

```python
"""SP6: download endpoint for M5 export artifacts.

Mounted under /api/v1 by api/app/main.py only when ORCHESTRATOR_ENABLED=true.
The endpoint resolves the s3_key from the project's M5Output.export_artifacts
and 302-redirects the browser to a fresh 5-minute signed URL.
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
        raise HTTPException(status_code=404,
                            detail={"error": {"code": "not_found"}})
    return p


@router.get("/projects/{project_id}/exports/{filename}")
def download_export(project_id: uuid.UUID, filename: str,
                    user: User = Depends(current_user),
                    db: Session = Depends(db_session)):
    """302-redirect to a fresh 5-minute signed URL for the requested artifact."""
    _owned_project(db, user, project_id)
    cs = db.get(ContextStore, project_id)
    m5 = (cs.m5_writing or {}) if cs else {}
    expected_key = f"projects/{project_id}/exports/{filename}"
    artifacts = m5.get("export_artifacts") or []
    if not any(a.get("s3_key") == expected_key for a in artifacts):
        raise HTTPException(404, detail={"error": {"code": "artifact_not_found"}})
    s3 = s3_from_env()
    signed_url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": os.environ["AWS_S3_BUCKET"], "Key": expected_key},
        ExpiresIn=300,
    )
    return RedirectResponse(url=signed_url, status_code=302)
```

Wired in `api/app/main.py` adjacent to where the chat router is mounted:

```python
if os.getenv("ORCHESTRATOR_ENABLED", "").lower() == "true":
    from .routers.chat import router as chat_router
    from .routers.exports import router as exports_router          # SP6
    app.include_router(chat_router, prefix="/api/v1")
    app.include_router(exports_router, prefix="/api/v1")
```

---

## Subprocess + dev env

```python
# orchestrator/__main__.py — at the top of main()
if not os.environ.get("AWS_S3_BUCKET"):
    raise SystemExit("AWS_S3_BUCKET env var is required for M5 export artifacts.")
```

`dev.sh` gets a comment near the env-var section:

```bash
# SP6: M5 exports require an S3 bucket. Set AWS_S3_BUCKET=dothesis-dev in your
# .env or shell, plus AWS_ACCESS_KEY + AWS_SECRET_KEY. For local dev without
# real S3, run minio (https://min.io) and point AWS_* at it.
```

---

## Data flow

### Quantitative happy path

```
supervisor → M5 (after M4 confirmed)
M5Agent.step()
  _render_context populated from m1-m4 slices
  _compose_chapters_done is False → _compose_all_chapters(state, partial)
    references = dedupe(m2.research_gaps[*].supporting_papers)
    for name in [intro, lit_review, methodology, results, discussion, conclusion]:
        draft = compose_chapter.invoke(...)
        chapters[name] = draft
        extras.append(AIMessage("## Chapter — {name}\n\n{prose}"))
    bib = compile_bibliography.invoke(...)
    extras.append(AIMessage("## Bibliography\n\n{bib}"))
    partial["chapters"], ["bibliography"], ["_compose_chapters_done"]=True, ["_awaiting_confirm"]=True
    return ModuleStepResult(assistant_message=summary, extra_messages=extras, ...)
graph node forwards primary + 7 extras → chat router SSE → user sees 8 bubbles stream in
user: "looks good, export it"
M5Agent.step()
  _compose_chapters_done + _awaiting_confirm + _is_affirmative → _finalize_and_export(state, partial)
    docx_key = export_docx.invoke({sections, project_id})   → S3 upload → "projects/{id}/exports/thesis-X.docx"
    pdf_key  = compile_pdf.invoke({sections, project_id})   → S3 upload → "projects/{id}/exports/thesis-X.pdf"
    export_artifacts = [ExportArtifact(docx,...), ExportArtifact(pdf,...)]
    confirmed_at = utc_now()
  → ModuleStepResult(transition=True, ...) → supervisor routes to END
final AIMessage:
  **Done.**
  - 📄 Download thesis (.docx): [thesis-X.docx](/api/v1/projects/{id}/exports/thesis-X.docx)
  - 📄 Download thesis (.pdf):  [thesis-X.pdf](/api/v1/projects/{id}/exports/thesis-X.pdf)
  Thesis confirmed and exported. M1-M5 complete.
user clicks link → GET /api/v1/projects/{id}/exports/thesis-X.docx
                 → endpoint validates ownership, looks up s3_key in m5_writing.export_artifacts,
                   generates 5-min signed URL, returns 302 redirect → browser downloads
```

### Qualitative happy path

Same shape; `paradigm="qualitative"` flows into the `results.md` prompt, which reads `m4.qual_codes` + `m4.qual_themes` and writes Braun & Clarke prose (theme-by-theme sections with verbatim quotes).

### Mixed happy path

Same shape; `results.md` produces a per-phase section + integration paragraph.

### Rewrite flow

```
state: chapters drafted, _awaiting_confirm=True, _compose_chapters_done=True
user: "rewrite chapter 3 to be less formal"
M5Agent.step()
  _is_rewrite_request → True (keyword "rewrite")
  _handle_rewrite(state, partial):
    target = _identify_chapter(user_msg) → "methodology"  (alias: "chapter 3")
    current = partial.chapters["methodology"].prose
    new_draft = rewrite_chapter.invoke({chapter_name, current_prose, instruction, ...})
    chapters["methodology"] = new_draft
    _awaiting_confirm stays True
    return ModuleStepResult with one extra AIMessage("## Chapter — methodology (rewritten)\n\n{new_prose}")
user: "yes" → _finalize_and_export → export → transition
```

If `_identify_chapter` returns None (no alias match), the agent emits a clarification message asking which chapter, stays in confirm.

---

## Testing strategy

### Backend unit tests

| File | What it covers |
|---|---|
| `orchestrator/tests/test_schemas.py` (extend) | `ChapterDraft` round-trip; `M5Output.@model_validator` enforces 6 chapters + docx artifact on confirm; in-progress partials valid; back-compat `sections` + `uri` fields still serializable |
| `orchestrator/tests/test_tools_m5.py` (extend) | `compose_chapter` stubbed-LLM per paradigm (quant + qual + mixed branches in `results.md`); `validate_citations` regex behavior + threshold + uncited; `compile_bibliography` formatting; `rewrite_chapter` stubbed-LLM; `compile_pdf` + `export_docx` raise on missing `project_id`; both upload to S3 via mocked `s3_from_env` + delete local file |
| `orchestrator/tests/agents/test_m5_compose.py` (NEW) | M5Agent at compose stage emits 6 chapter + bibliography + summary AIMessages via `extra_messages`; calls compose_chapter with correct paradigm + context slice; sets `_compose_chapters_done` + `_awaiting_confirm`; does not transition |
| `orchestrator/tests/agents/test_m5_rewrite.py` (NEW) | When `_compose_chapters_done` + `_awaiting_confirm` + rewrite keyword → routes to `_handle_rewrite`; `_identify_chapter` maps "chapter 3" / "ch3" / "methodology" / "methods" → "methodology"; ambiguous request emits clarification AIMessage |
| `orchestrator/tests/agents/test_m5_finalize.py` (NEW) | Affirmative user msg + _awaiting_confirm → calls `compile_pdf` + `export_docx` with `project_id`; populates `export_artifacts` (both kinds); sets `confirmed_at`; `transition=True`; raises if `project_id` missing |
| `orchestrator/tests/agents/test_m5_context_slice.py` (NEW) | `_extract_context_slice` returns expected dict shape; falls back gracefully when an upstream module slice is None |
| `orchestrator/tests/test_agents_m5.py` (update existing) | Auto-mode test updated for new schema (chapters + bibliography); compile_pdf/export_docx S3 mocking; passes against `@model_validator` |
| `orchestrator/tests/test_subprocess.py` (extend) | Subprocess raises `SystemExit` without `AWS_S3_BUCKET`; starts normally when set |

### Backend integration tests

| File | What it covers |
|---|---|
| `api/tests/test_exports.py` (NEW) | 200 + 302 redirect happy path (mocked S3 client returns a signed URL); 404 when filename not in M5Output.export_artifacts; 403 when user doesn't own project; behaves correctly when ORCHESTRATOR_ENABLED=false (router not mounted) |
| `api/tests/test_m5_round_trip.py` (NEW) | Contract test: a rewrite-keyword user message persists correctly and the agent's next step() would route to `_handle_rewrite`. No router changes required. |

### Frontend tests

| File | What it covers |
|---|---|
| `web/app/components/chat/ChatPane.test.tsx` (extend, optional) | Hydrate thread with final-bubble containing markdown download links; assert links render with `/api/v1/projects/.../exports/...` href. Skip if no signal beyond SP5. |

### Mocking strategy

- LLM: `monkeypatch.setattr(M5Agent, "_get_llm", ...)` for agent tests; `monkeypatch.setattr("orchestrator.tools.m5_writing._get_llm", ...)` for tool tests
- S3: `monkeypatch.setattr("orchestrator.tools.m5_writing.s3_from_env", ...)` returning a `MagicMock` that records `put_object` and `generate_presigned_url` calls
- Engine wrappers (`_compile_pdf_via_engine`, `_export_docx_via_engine`): stubbed to write placeholder file so `_upload_to_s3` has something to read
- No real Gemini or S3 calls in CI

### Regression gates

SP6 ships green iff:
- All new tests pass
- `orchestrator/tests/` baseline holds (currently 204 after SP5) + new SP6 tests
- `web/` baseline holds (currently 107 after SP5) + optional ChatPane addition
- `api/tests/` shows 52 baseline failures unchanged vs `.baseline_failures_2026-05-26.txt`; 0 new
- `npm run build` succeeds in `web/`
- Auto-mode test (`test_m5_auto_*`) passes against new schema + S3-upload contract

---

## Non-goals (explicit)

| Non-goal | Why deferred | Lands in |
|---|---|---|
| WYSIWYG section editor (TipTap / Lexical) | Major frontend lift; PRD §6.5.3 calls for inline paraphrase/translate/cite-insert needing a rich editor | SP6.5 |
| Inline paraphrase tool | Whole-chapter `rewrite_chapter` covers the common case | SP6.5 |
| Translate tool | LLM composition already supports `language` parameter; per-passage needs editor selection | SP6.5 |
| Inline `/cite` command | Compose pipeline cites inline via LLM (Q3=A) | SP6.5 |
| Citation Manager UI (style switching, dedupe, Zotero/Mendeley) | V1 uses single style from `project.citation_style` (apa7) | SP6.6 / Phase 3 |
| LaTeX export | engine has weasyprint (PDF) + python-docx — no LaTeX path | Post-pivot |
| Google Docs export | Requires Google Drive API + OAuth flow | Post-pivot |
| Slash commands (`/addstep`, `/rerun`, `/cite`, `/translate`, `/explain`) | NL detection covers the rewrite path | Post-pivot |
| Persistent artifact storage with metadata DB table | V1 stores `export_artifacts` inside `M5Output` (JSONB) | Post-pivot |
| Re-export without re-compose | V1 always re-composes if user re-enters M5 | Post-pivot |
| Version history of chapter drafts | Each rewrite overwrites the previous draft | Post-pivot |

---

## Risks & mitigations

1. **LLM hallucinates citations.** Q3=A accepts the risk; `validate_citations` flags uncited; bibliography includes "Potentially missing citations" subsection. Tests cover both clean and hallucinated payloads.

2. **Six LLM calls per thesis (~60-80K tokens at compose time).** Within Gemini Flash budget; re-runs are user-triggered via rewrite, not automatic.

3. **`rewrite_chapter` may introduce new hallucinated citations.** Same `validate_citations` post-pass runs on rewrite output.

4. **Chapter identification fragile when user says "the data analysis section".** `_CHAPTER_ALIASES` covers synonyms; clarification message is the fallback.

5. **S3 credentials missing in dev.** Both subprocess + interactive paths fail fast with clear error. `dev.sh` gets a comment. Tests use mocked `s3_from_env()`.

6. **`ExportArtifact.uri` deprecated, replaced with `s3_key` + `download_url`.** `uri` kept as empty string for back-compat. Auto-mode tests + readers continue to work.

7. **`download_url` is relative (`/api/v1/...`).** Fine for dev domain. For absolute URLs (e.g. email notifications), generate with project's base URL — one-line change to `_format_export_artifacts_markdown`.

8. **Engine fallback wrappers become unused in interactive M5.** Still wired for `compose_section` + `validate_draft`. Leaving them in place reduces unrelated breakage risk. Cleanup is a separate PR.

9. **`compile_pdf` / `export_docx` signature change (added `project_id`) breaks any external caller relying on old signature.** Grep verification: no other callers in the orchestrator package. Auto-mode path goes through M5Agent which provides the project_id.

10. **7-8 long markdown bubbles streaming in is a lot.** Same UX as SP5's per-step execution — works fine; user sees progress per chapter.

---

## Success criteria

- A quantitative user walks M1→M5 → enters M5 → sees 6 chapters + bibliography + summary streaming in (~30-60s) → confirms → docx + pdf land in S3 → markdown download links in chat → click downloads via 302 redirect to fresh signed URL
- A qualitative user walks M1→M5 (with SP5's qual_codes + qual_themes) → Chapter 4 prose includes Braun & Clarke theme-by-theme writeup
- A mixed user walks both M4 sub-flows → Chapter 4 includes quant + qual + integration paragraph
- A rewrite request ("rewrite the methodology to be less formal") updates `partial.chapters["methodology"]` + emits new bubble + stays in confirm state
- All clicks/replies reuse SP3 send path; ONE new HTTP endpoint (`GET /api/v1/projects/{id}/exports/{filename}`); no new SSE event types; no new widget variants
- Auto-mode subprocess produces the same S3 artifacts via the same `compile_pdf` + `export_docx` tools (single code path)
- `web/`, `orchestrator/`, `api/` regression baselines hold
- `npm run build` succeeds in `web/`

---

## What's next after SP6 ships

**SP6.5 — M5 editor surface.** WYSIWYG section editor with inline paraphrase, translate, cite-insert affordances. Requires TipTap/Lexical pick. Reuses SP6's chapter storage shape unchanged.

**SP6.6 — Citation Manager.** Style switching (APA7 ↔ Vancouver ↔ Chicago), dedupe UI, import from Zotero/Mendeley. Builds on SP6's bibliography compile + existing `format_citations` tool.

**Post-pivot — formalized engine integration.** Today's engine fallbacks (`_compose_section_via_engine`, etc.) are dead code in interactive M5. Cleanup PR retires them once auto-mode subprocess is itself retired or formalized.

**Post-pivot — formal artifact DB table.** Promote `M5Output.export_artifacts` JSONB entries to a dedicated `artifacts` table with audit log + regeneration tracking. Adds a `/api/v1/projects/{id}/artifacts` list endpoint.

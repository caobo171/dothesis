"""M5 — Writing & Export agent (SP6 chapter-by-chapter compose + auto-export)."""
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage

from orchestrator.agents.base import ModuleAgent, ModuleStepResult
from orchestrator.agents.shapes import WizardAgent
from orchestrator.message_utils import text_of
from orchestrator.schemas.m5 import M5Output, ExportArtifact
from orchestrator.schemas.m5_editor import PendingEdit
from orchestrator.tools.m5_writing import (
    compose_chapter, compose_section, rewrite_chapter,
    validate_draft, validate_citations,
    format_citations, compile_bibliography,
    compile_pdf, export_docx,
    _chapter_titles, _references_title,
)


_PROMPT = (Path(__file__).resolve().parent.parent / "prompts" / "m5.md").read_text()

_CHAPTER_ORDER = ["intro", "lit_review", "methodology", "results", "discussion", "conclusion"]


def _scale_items_from_conceptual_model(cm: dict | None) -> list[dict]:
    """Derive the legacy `scale_items` list from the merged conceptual_model
    flow_chart shape ({nodes: [{label, questions}], edges: [...]}). The M3
    schema dropped the standalone scale_items field in the 2026-06 merge, but
    the M5 chapter prompts still read {scale_items} in their methodology
    template — this keeps that prompt populated without the prompt template
    having to know the new shape.

    Returns [{construct, items}, ...] preserving node insertion order. Nodes
    with no questions are skipped to mirror the old "only include constructs
    with measured items" behaviour.
    """
    if not isinstance(cm, dict):
        return []
    out: list[dict] = []
    for node in cm.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        questions = [q for q in (node.get("questions") or []) if q]
        if not questions:
            continue
        out.append({"construct": node.get("label", ""), "items": questions})
    return out


class M5Agent(WizardAgent, ModuleAgent):
    # PR #5 — Wizard shape per brief §3 (wizard refactor follows in #5b).
    schema = M5Output
    module_key = "M5"
    slice_field = "m5_writing"  # brief §6 — ModuleHandler contract
    system_prompt = _PROMPT
    tools = [
        compose_chapter, compose_section, rewrite_chapter,
        validate_draft, validate_citations,
        format_citations, compile_bibliography,
        compile_pdf, export_docx,
    ]

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

    # Populated by _compose_all_chapters / _handle_rewrite — shared across step() calls
    # within a single agent instance so that the compose phase can cache render data.
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
            "citation_list": m2.get("citation_list", []),
            "design": m3.get("design"),
            "tool": m3.get("tool"),
            "conceptual_model": m3.get("conceptual_model"),
            # Design merge (2026-06): the standalone `scale_items` schema field
            # is gone. Per-construct Likert items live on conceptual_model
            # nodes (`conceptual_model.nodes[].questions`). For prompt-template
            # back-compat, derive a flat scale_items list on the fly so the
            # M5 chapter prompts that still reference {scale_items} keep
            # rendering populated instead of "Scale items (quant): None".
            "scale_items": _scale_items_from_conceptual_model(
                m3.get("conceptual_model")
            ),
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
                # Skip gap papers with no title: find_research_gaps often returns
                # only {author, year}, which render as blank bibliography lines
                # ("Author (Year). ."). They can still be cited inline via the
                # titled citation_list entries collected below.
                if not (paper.get("title") or "").strip():
                    continue
                key = (paper.get("author", ""), str(paper.get("year", "")))
                if key != ("", "") and key not in seen:
                    seen[key] = paper
        # Fall back to the M2 citation_list (the scout's finds) so chapters still
        # cite when the gaps carry no attached papers — common in auto mode, where
        # gaps are generated without page-level supporting papers.
        for c in context.get("citation_list", []):
            # Scout shape (engine/prompts/01_research/scout.md): authors is a
            # list[str]. Older/hand-written entries may use a plain string under
            # either "author" or "authors". Coerce to a single string here so
            # (a) the dedupe key stays hashable (a list-element tuple isn't),
            # and (b) downstream citation rendering doesn't have to branch.
            raw_author = c.get("author") or c.get("authors") or ""
            if isinstance(raw_author, list):
                author = ", ".join(str(a) for a in raw_author if a)
            else:
                author = str(raw_author)
            key = (author, str(c.get("year", "")))
            if author and key not in seen:
                seen[key] = {"author": author, "year": c.get("year"),
                             "title": c.get("title"), "source": c.get("source")}
        return list(seen.values())

    def _latest_user_message(self, messages) -> str:
        return next(
            (text_of(m) for m in reversed(messages) if isinstance(m, HumanMessage)),
            "",
        )

    def step(self, state):
        """SP6: auto-mode + interactive both produce S3 artifacts via the same
        compile_pdf/export_docx tools (Q-S3 decision: single code path)."""
        from orchestrator.state import get_module_slice
        cls = type(self)
        partial = dict(get_module_slice(state["context_store"], self.module_key))
        cls._render_context = self._extract_context_slice(state["context_store"])

        # Auto-mode: let base class _auto_fill produce the chapters, then
        # replace any LLM-hallucinated export_artifacts with REAL S3 uploads.
        if state.get("mode") == "auto":
            # Per-chapter composition (not the monolithic _auto_fill, which 504'd).
            base_result = self._auto_compose_chapters(state)
            # Defensive: normalize to the schema's name-keyed dict.
            if base_result.context_patch.get("chapters"):
                base_result.context_patch["chapters"] = self._normalize_chapters(
                    base_result.context_patch["chapters"])
            if base_result.transition and base_result.context_patch.get("chapters"):
                project_id = str(state.get("project_id") or "")
                if project_id:
                    sections = self._build_sections_for_export(base_result.context_patch)
                    docx_result = export_docx.invoke({
                        "sections": sections, "project_id": project_id,
                    })
                    pdf_result = compile_pdf.invoke({
                        "sections": sections, "project_id": project_id,
                    })
                    artifacts = [
                        ExportArtifact(
                            kind="docx",
                            s3_key=docx_result["s3_key"],
                            download_url=f"/api/v1/projects/{project_id}/exports/{docx_result['s3_key'].split('/')[-1]}",
                            size_bytes=docx_result["size_bytes"],
                        ),
                        ExportArtifact(
                            kind="pdf",
                            s3_key=pdf_result["s3_key"],
                            download_url=f"/api/v1/projects/{project_id}/exports/{pdf_result['s3_key'].split('/')[-1]}",
                            size_bytes=pdf_result["size_bytes"],
                        ),
                    ]
                    base_result.context_patch["export_artifacts"] = [a.model_dump() for a in artifacts]
            return base_result

        # Interactive: rewrite + finalize + compose phase (existing logic).
        if partial.get("_compose_chapters_done") and partial.get("_awaiting_confirm"):
            if self._is_rewrite_request(state["messages"]):
                return self._handle_rewrite(state, partial)
            if self._is_affirmative(state["messages"]):
                return self._finalize_and_export(state, partial)

        if not partial.get("_compose_chapters_done"):
            return self._compose_all_chapters(state, partial)

        return super().step(state)

    def _is_rewrite_request(self, messages) -> bool:
        """LLM check: is the user asking us to rewrite an existing chapter?

        Replaces a keyword list ("rewrite" / "rephrase" / "shorter" / etc.)
        that missed phrasings like "tighten the intro" or "make chapter 4
        sound more academic". Falls back to False on LLM failure so the
        normal compose flow continues.
        """
        import json
        last = self._latest_user_message(messages)
        if not last:
            return False
        prompt = (
            f"The user is in the writing phase of their research project. "
            f"Their reply is below.\n"
            f"User reply: {last}\n\n"
            f"Are they asking the agent to REWRITE or modify an existing "
            f"chapter (e.g. 'rewrite the intro', 'make chapter 4 shorter', "
            f"'tighten the methods section', 'rephrase more formally')?\n\n"
            f'Respond with ONLY: {{"rewrite": true|false}}'
        )
        try:
            from orchestrator.agents.base import _strip_code_fence
            raw = self._get_llm().invoke(prompt).content
            data = json.loads(_strip_code_fence(raw))
            return bool(data.get("rewrite"))
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception("M5 rewrite classification failed")
        return False

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
        """SP6.5: chat NL-rewrite now lands as a PendingEdit (whole-chapter
        range) instead of overwriting prose directly. The user reviews and
        accepts or rejects it in the editor — same accept/reject flow as
        paraphrase/translate/cite. This keeps prose immutable in chat and
        gives the user a clean diff view before any text is committed."""
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
                # SP6.5: no extra_messages when we can't identify the chapter
                extra_messages=[],
            )
        context = self._render_context or {}
        chapters = dict(partial.get("chapters", {}))
        # SP6.5: read old prose from the chapter dict (prose key preserved, not overwritten)
        old_prose = chapters.get(target, {}).get("prose", "")
        new_text = rewrite_chapter.invoke({
            "chapter_name": target,
            "current_prose": old_prose,
            "instruction": last_user,
            "context_slice": context,
            "references": self._collect_references(context),
            "language": context.get("language", "en"),
        })
        # SP6.5: new_text may be a plain string (from mock/LLM); normalise to str
        if isinstance(new_text, dict):
            new_text = new_text.get("prose", "")
        # SP6.5: build a PendingEdit covering the whole chapter (from_offset=0,
        # to_offset=len(old_prose)) so the editor accept path slices [0:len] = new_text
        pe = PendingEdit(
            id=uuid4().hex,
            chapter_name=target,
            from_offset=0,
            to_offset=len(old_prose),
            old_text=old_prose,
            new_text=new_text,
            source="chat_rewrite",
            pending_at=datetime.now(timezone.utc),
        )
        chapter_data = dict(chapters.get(target, {"name": target, "prose": old_prose}))
        existing_edits = list(chapter_data.get("pending_edits") or [])
        chapter_data["pending_edits"] = existing_edits + [pe.model_dump(mode="json")]
        chapters[target] = chapter_data
        partial["chapters"] = chapters
        partial["_awaiting_confirm"] = True
        # SP6.5: bubble points user to the editor so they can accept/reject the diff
        project_id = state.get("project_id") or ""
        link = f"/chat/projects/{project_id}/editor" if project_id else "/editor"
        bubble = AIMessage(content=(
            f"Rewrite of **{target}** is ready — review it in the editor "
            f"and click ✓ to accept or ✗ to reject. [Open in editor]({link})"
        ))
        return ModuleStepResult(
            assistant_message=f"Rewrite of {target} queued as a pending edit. Open the editor to review.",
            context_patch=partial,
            transition=False, needs_user_reply=True,
            extra_messages=[bubble],
        )

    def _finalize_and_export(self, state, partial):
        """Compile docx + pdf, upload to S3, populate export_artifacts, transition.

        Uses dict-shape return from compile_pdf/export_docx to propagate real
        size_bytes into ExportArtifact instead of hardcoding 0.
        """
        project_id = str(state.get("project_id") or "")
        if not project_id:
            raise RuntimeError("M5 finalize requires project_id in state")

        sections_for_engine = self._build_sections_for_export(partial)
        docx_result = export_docx.invoke({
            "sections": sections_for_engine, "project_id": project_id,
        })
        pdf_result = compile_pdf.invoke({
            "sections": sections_for_engine, "project_id": project_id,
        })

        artifacts = [
            ExportArtifact(
                kind="docx",
                s3_key=docx_result["s3_key"],
                download_url=f"/api/v1/projects/{project_id}/exports/{docx_result['s3_key'].split('/')[-1]}",
                size_bytes=docx_result["size_bytes"],
            ),
            ExportArtifact(
                kind="pdf",
                s3_key=pdf_result["s3_key"],
                download_url=f"/api/v1/projects/{project_id}/exports/{pdf_result['s3_key'].split('/')[-1]}",
                size_bytes=pdf_result["size_bytes"],
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

    def _strip_uncited_warnings(self, prose: str) -> str:
        """Remove the ⚠️ uncited-warnings notice block before exporting.

        The block is appended by _annotate_uncited in compose_chapter /
        rewrite_chapter and is fine to show in chat, but it shouldn't end up
        in the final thesis docx/pdf.
        """
        marker = "\n\n> ⚠️ The following inline citations are not present"
        idx = prose.find(marker)
        if idx == -1:
            return prose
        return prose[:idx]

    @staticmethod
    def _normalize_chapters(chapters) -> dict:
        """Coerce auto-fill's chapters into the schema's {name: {prose}} dict.

        Regression guard: the auto-fill LLM sometimes returns `chapters` as a
        LIST of chapter dicts (e.g. {"title": "Chapter 1: Introduction", ...})
        instead of the name-keyed dict, which crashed downstream `.get` calls.
        Map list items onto _CHAPTER_ORDER by name/title match, falling back to
        positional order.
        """
        if isinstance(chapters, dict):
            return chapters
        if not isinstance(chapters, list):
            return {}
        out: dict = {}
        for i, ch in enumerate(chapters):
            if not isinstance(ch, dict):
                continue
            raw = str(ch.get("name") or ch.get("title") or "").lower()
            name = next(
                (c for c in _CHAPTER_ORDER if c in raw or c.replace("_", " ") in raw),
                None,
            )
            if name is None and i < len(_CHAPTER_ORDER):
                name = _CHAPTER_ORDER[i]
            if name:
                out[name] = ch
        return out

    def _build_sections_for_export(self, partial: dict) -> list[dict]:
        """Assemble the per-chapter section list passed to compile_pdf/export_docx.

        Strips uncited-warning blockquotes so editorial notices don't appear in
        the exported thesis docx/pdf (they remain visible in chat bubbles).
        """
        chapters = self._normalize_chapters(partial.get("chapters", {}))
        language = (type(self)._render_context or {}).get("language", "en")
        titles = _chapter_titles(language)
        # Emit the {title, prose} shape the renderer (_sections_to_markdown)
        # documents and compose_all_sections already uses — with localized
        # chapter headings. The old {name, text} shape silently produced a blank
        # export because the renderer reads title/prose.
        sections = [
            {"title": titles.get(name, name.replace("_", " ").title()),
             "prose": self._strip_uncited_warnings(
                 chapters.get(name, {}).get("prose", "")
             )}
            for name in _CHAPTER_ORDER
        ]
        if partial.get("bibliography"):
            sections.append({"title": _references_title(language),
                             "prose": partial["bibliography"]})
        return sections

    def _format_export_artifacts_markdown(self, artifacts: list) -> str:
        lines = ["**Done.**", ""]
        for a in artifacts:
            label = {"docx": "Download thesis (.docx)",
                     "pdf": "Download thesis (.pdf)"}.get(a.kind, a.kind)
            filename = a.s3_key.split("/")[-1]
            lines.append(f"- \U0001f4c4 {label}: [{filename}]({a.download_url})")
        lines.append("")
        lines.append("Thesis confirmed and exported. M1-M5 complete.")
        return "\n".join(lines)

    def render_hint_for_field(self, field_name: str, partial: dict | None = None) -> dict | None:
        # SP6 has no widgets; chapter prose renders as plain markdown
        return None

    def _auto_compose_chapters(self, state) -> ModuleStepResult:
        """Auto-mode chapter composition — one LLM call PER chapter (like the
        interactive path), NOT a single monolithic _auto_fill request.

        The base _auto_fill generated all 6 chapters in one giant call, which hit
        Gemini 504 DEADLINE_EXCEEDED and killed M5 in auto runs. Composing chapter
        by chapter keeps each request small and reliable. Stamps confirmed_at and
        transitions (auto mode has no user confirm step).
        """
        context = self._render_context or {}
        references = self._collect_references(context)
        # Stream a beat per chapter so the auto-run activity feed shows M5 making
        # progress ("Writing Chapter 4 — Results…") instead of one long silent
        # gap. emit() is a no-op when no emitter is bound (e.g. tests), and the
        # auto subprocess binds one (orchestrator/__main__.py).
        from engine.utils import progress as _progress

        _CHAPTER_BEAT = {
            "intro": "Writing Chapter 1 — Introduction…",
            "lit_review": "Writing Chapter 2 — Literature Review…",
            "methodology": "Writing Chapter 3 — Methodology…",
            "results": "Writing Chapter 4 — Results…",
            "discussion": "Writing Chapter 5 — Discussion…",
            "conclusion": "Writing Chapter 6 — Conclusion…",
        }
        chapters: dict[str, dict] = {}
        for name in _CHAPTER_ORDER:
            _progress.emit("m5_compose", _CHAPTER_BEAT.get(name, f"Writing {name}…"))
            chapters[name] = compose_chapter.invoke({
                "chapter_name": name,
                "paradigm": context.get("paradigm") or "quantitative",
                "context_slice": context,
                "references": references,
                "citation_style": context.get("citation_style", "apa7"),
                "language": context.get("language", "en"),
            })
        _progress.emit("m5_compose", "Compiling references…")
        bib = compile_bibliography.invoke({
            "references": references,
            "citation_style": context.get("citation_style", "apa7"),
        })
        return ModuleStepResult(
            assistant_message="[auto] Composed 6 chapters + bibliography.",
            context_patch={
                "chapters": chapters,
                "bibliography": bib,
                "confirmed_at": datetime.now(timezone.utc).isoformat(),
            },
            transition=True,
        )

    def _compose_all_chapters(self, state, partial):
        """Loop all 6 chapters, compose each, emit one AIMessage per chapter +
        bibliography + summary. Sets _awaiting_confirm=True on the context patch."""
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
        """Return the summary message shown after all chapters are composed."""
        n_uncited = sum(len(c.get("uncited_warnings") or []) for c in chapters.values())
        msg = [
            f"Drafted all 6 chapters + bibliography ({len(references)} unique references).",
        ]
        if n_uncited:
            msg.append(
                f"⚠️ {n_uncited} inline citations flagged as potentially missing "
                "from the reference pool."
            )
        msg.append(
            "Confirm to export to docx + pdf, or ask for a rewrite "
            "(e.g. 'rewrite chapter 3 to be less formal')."
        )
        return "\n\n".join(msg)

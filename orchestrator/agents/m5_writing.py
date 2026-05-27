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

    def render_hint_for_field(self, field_name: str) -> dict | None:
        # SP6 has no widgets; chapter prose renders as plain markdown
        return None

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

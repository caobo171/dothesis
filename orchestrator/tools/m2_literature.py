"""M2 — Literature Review tools.

Thin wrappers around engine/utils/* + small LLM helpers. The heavy lifting
(citation discovery, deep research, citation formatting) stays in engine/.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path

from langchain_core.tools import tool
from orchestrator.llm import get_orchestrator_llm

# Make engine package importable as a sibling.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logger = logging.getLogger(__name__)


def _get_llm():
    # Delegates to the engine-wide factory (ORCHESTRATOR_LLM_ROUTE); temperature
    # 0.3 is this tool's original per-site setting.
    return get_orchestrator_llm(temperature=0.3)


def _engine_model():
    """Native engine-shaped model for the citation pipeline.

    The engine's DeepResearchPlanner + CitationResearcher call
    `model.generate_content(prompt, generation_config=...)` (raw google-genai
    interface). LangChain's ChatGoogleGenerativeAI doesn't expose that
    method, so passing it crashed the planner and the engine silently fell
    back to 'standard mode with basic queries' — quality regression.

    GeminiModelWrapper IS the engine's native type. Constructing it directly
    here keeps the planner happy without changing engine internals.
    Resolves the API key via the same dual-name fallback the rest of the
    engine uses (B5 fix).
    """
    # DO NOT "consolidate" this onto get_orchestrator_llm(). That was tried and
    # reverted (B5): LangChain's ChatGoogleGenerativeAI has no generate_content(),
    # so the planner crashed and the engine SILENTLY degraded to "standard mode
    # with basic queries" — a quality regression with no error to notice.
    #
    # The constraint is the INTERFACE (generate_content -> .text/.candidates), not
    # the provider — engine/utils/groq_adapter.py already puts a non-Gemini model
    # in this slot. So CITATION_PLANNER_MODEL selects the client: a gpt-* id gets
    # the OpenAI adapter, anything else the Gemini one. ONE knob, and reverting to
    # Gemini is an env change with no code edit.
    #
    # Default moved 2026-08-02: gemini-2.5-flash -> gemini-3-flash-preview ->
    # gpt-5.6-luna. luna is ~2.5x cheaper than the Gemini flash tier (0.529x vs
    # 1.324x), has 1.05M context vs 400k/1M, is already priced in
    # quality/model_prices.py, and is the same model the brain and orchestrator
    # run — so "what model is DoThesis on?" now has ONE answer.
    model_name = os.getenv("CITATION_PLANNER_MODEL", "gpt-5.6-luna")

    if model_name.startswith("gpt-"):
        key = os.getenv("OPENAI_API_KEY", "")
        if not key:
            raise RuntimeError(
                "CITATION_PLANNER_MODEL is an OpenAI id but OPENAI_API_KEY is unset "
                "(set it, or pin CITATION_PLANNER_MODEL to a Gemini id)"
            )
        client: Any = _OpenAIPlannerClient(model_name, key)
    else:
        from engine.utils.gemini_client import create_gemini_client
        # create_gemini_client routes through Ofox's Gemini-native endpoint when
        # the deployment is on Ofox, else Google direct.
        client = create_gemini_client(model_name=model_name, temperature=0.3)
    return _MeteredGeminiClient(client)


_GEMINI_FINISH_STOP = 1
_GEMINI_FINISH_SAFETY = 2  # deep_research.SAFETY_BLOCKED compares against this


class _PlannerCandidate:
    """Stands in for a google-genai candidate. Only finish_reason is read."""

    def __init__(self, finish_reason: int) -> None:
        self.finish_reason = finish_reason


class _PlannerUsage:
    """google-genai usage field names, so the meter needs no special-casing."""

    def __init__(self, prompt_token_count: int, candidates_token_count: int) -> None:
        self.prompt_token_count = prompt_token_count
        self.candidates_token_count = candidates_token_count


class _PlannerResponse:
    def __init__(self, text: str, finish: str, usage: Any) -> None:
        self.text = text
        # `candidates` empty == "blocked" to the engine (deep_research.py:43 and
        # api_citations/orchestrator.py:1008 both branch on falsiness first).
        # OpenAI's content_filter is the same condition, so map it to an EMPTY
        # list rather than a candidate with a safety finish_reason — that way the
        # engine's existing block handling fires on its first check.
        if finish == "content_filter":
            self.candidates: list[Any] = []
        else:
            self.candidates = [_PlannerCandidate(
                _GEMINI_FINISH_SAFETY if finish == "content_filter" else _GEMINI_FINISH_STOP
            )]
        self.usage_metadata = usage


class _OpenAIPlannerClient:
    """Exposes Gemini's generate_content() over OpenAI chat completions.

    Why this exists: the citation planner is pinned to a Gemini client only
    because it calls the raw `generate_content(prompt, generation_config=...)`
    interface — NOT because it needs Google. The same slot already takes a
    non-Gemini model in engine/utils/groq_adapter.py ("Mimics Gemini's
    generate_content interface"), so this follows an established pattern.

    Moving the planner onto gpt-5.6-luna makes it ~2.5x cheaper than
    gemini-3-flash-preview (0.529x vs 1.324x), on a model with 1.05M context
    instead of Google's flash tier, and unifies the stack: brain, orchestrator
    and planner all run one model with one price row.

    The engine's contract, satisfied exactly:
      response.text                      -> str
      response.candidates                -> [] when blocked, else 1 candidate
      response.candidates[0].finish_reason
      response.usage_metadata            -> google-genai field names

    ⚠ temperature is DROPPED. deep_research sets 0.3 "for systematic planning",
    but gpt-5.6-* only accepts the default (400 otherwise). JSON mode still pins
    the output shape, which is what the planner actually depends on. If that
    determinism turns out to matter, gpt-5.4-nano costs 0.544x (vs 0.529x) and
    DOES honour temperature — it is the fallback, at a weaker model tier.
    """

    def __init__(self, model_name: str, api_key: str) -> None:
        self.model_name = model_name
        from openai import OpenAI  # noqa: PLC0415 — planner-only, lazy
        self._client = OpenAI(api_key=api_key)

    @staticmethod
    def _cfg_get(cfg: Any, key: str) -> Any:
        # generation_config arrives as a dict from every engine call site, but
        # GeminiModelWrapper also accepted attribute-style objects — match both.
        if cfg is None:
            return None
        if isinstance(cfg, dict):
            return cfg.get(key)
        return getattr(cfg, key, None)

    def generate_content(self, prompt: Any, generation_config: Any = None,
                         safety_settings: Any = None) -> _PlannerResponse:
        _ = safety_settings  # provider-side on OpenAI, same as GeminiModelWrapper
        # api_citations/orchestrator.py passes a LIST ([scout_prompt, user_input]);
        # deep_research passes a str. Join exactly like GeminiModelWrapper does.
        if isinstance(prompt, list):
            contents = "\n".join(str(p) for p in prompt)
        else:
            contents = str(prompt)

        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": contents}],
        }
        max_out = self._cfg_get(generation_config, "max_output_tokens")
        if max_out:
            # NOT max_tokens — gpt-5.6-* rejects it outright.
            kwargs["max_completion_tokens"] = int(max_out)
        if self._cfg_get(generation_config, "response_mime_type") == "application/json":
            kwargs["response_format"] = {"type": "json_object"}

        resp = self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        u = getattr(resp, "usage", None)
        usage = _PlannerUsage(
            int(getattr(u, "prompt_tokens", 0) or 0),
            int(getattr(u, "completion_tokens", 0) or 0),
        )
        return _PlannerResponse(choice.message.content or "",
                                choice.finish_reason or "stop", usage)


class _MeteredGeminiClient:
    """Records citation-planner token usage into the same ledger everything else bills from.

    The planner is the one LLM caller that LangChain callbacks cannot reach — it
    is a raw google-genai client (see _engine_model), so orchestrator/llm.py's
    LedgerCallback never sees it. Its tokens were therefore invisible to
    _charge_auto_run and the planner ran free.

    Delegation is via __getattr__ so the engine's DeepResearchPlanner keeps
    seeing the GeminiModelWrapper interface it expects — only generate_content is
    intercepted, and the response object is passed through untouched.

    The model is read AFTER the call, not before: GeminiModelWrapper walks a
    fallback chain on overload and MUTATES self.model_name, so a run that starts
    on gemini-3-flash-preview can finish on something cheaper. Billing the
    configured model rather than the served one would overcharge exactly when the
    student already got the degraded model.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def generate_content(self, *args: Any, **kwargs: Any) -> Any:
        import time  # noqa: PLC0415
        from orchestrator.token_meter import (  # noqa: PLC0415 — cycle-avoiding
            LedgerEntry, get_sink, project_id_from_env,
        )
        t0 = time.monotonic()
        prompt_tok = completion_tok = 0
        try:
            resp = self._inner.generate_content(*args, **kwargs)
            um = getattr(resp, "usage_metadata", None)
            if um is not None:
                prompt_tok = int(getattr(um, "prompt_token_count", 0) or 0)
                completion_tok = int(getattr(um, "candidates_token_count", 0) or 0)
            return resp
        finally:
            try:
                get_sink()(LedgerEntry(
                    project_id=project_id_from_env(),
                    action_kind="m2_citation_planner",
                    model=str(getattr(self._inner, "model_name", "unknown")),
                    prompt_tokens=prompt_tok,
                    completion_tokens=completion_tok,
                    reserved=0,
                    duration_ms=int((time.monotonic() - t0) * 1000),
                ))
            except Exception:  # noqa: BLE001
                # Billing telemetry must never break a student's citation run.
                logger.exception("citation planner ledger write failed")


# Re-exported here so tests can monkeypatch easily — the real import is late
# (inside the function body) to avoid import-time failures when engine/ is
# not fully available in test environments.
def research_citations_via_api(model, research_topics, output_path, target_minimum, **kw):
    from engine.utils.agent_runner import research_citations_via_api as _real
    return _real(model, research_topics, output_path, target_minimum, **kw)


def _read_paper_text(p: str) -> str:
    path = Path(p)
    if path.suffix.lower() == ".pdf":
        try:
            from pdfminer.high_level import extract_text
            return extract_text(str(path))
        except Exception:
            logger.warning("pdfminer extract failed for %s", path)
            return ""
    return path.read_text(encoding="utf-8", errors="ignore")


_DOMAIN_TITLE_RE = re.compile(r"^[\w-]+(?:\.[\w-]+)+(?:/\S*)?$")  # nih.gov, a.b.c/x


def _is_junk_citation(c: dict) -> bool:
    """True when a citation carries no usable bibliographic content.

    The scout over-fetches: grounded search returns bare domain stubs
    ("nih.gov") and some sources arrive with placeholder/empty titles. Such
    rows render as blank reference lines, so we drop them before they reach the
    citation_list / bibliography.
    """
    title = (c.get("title") or "").strip()
    if not title:
        return True
    low = title.lower()
    if low in {"title", "untitled", "n/a", "na", "none"} or low.startswith("title "):
        return True
    # A bare domain or URL masquerading as a title (no spaces, looks like a host).
    if " " not in title and (title.startswith("http") or _DOMAIN_TITLE_RE.match(title)):
        return True
    return False


def _strip_json_fence(s: str) -> str:
    s = (s or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


def _filter_relevant_citations(citations: list[dict], topic: str) -> list[dict]:
    """Drop citations that aren't topically relevant to `topic`.

    The deep-research scout pulls in off-topic papers — the
    "{topic} methodology and approaches" variant returns generic method papers
    (PRISMA, systematic-review guides) and grounded search returns unrelated
    highly-cited work (e.g. phosphorus reviews on a comedy thesis). One bounded
    LLM pass keeps only on-topic titles. Safe fallback: keep all titled
    citations on timeout/error/parse-failure — never silently empty the review.
    """
    titled = [c for c in citations if not _is_junk_citation(c)]
    if len(titled) <= 3 or not (topic or "").strip():
        return titled
    listing = "\n".join(
        f"{i}: {(c.get('title') or '')[:160]}" for i, c in enumerate(titled)
    )
    prompt = (
        "You are screening search results for a literature review.\n"
        f'Research topic: "{topic}"\n\n'
        "Below is a numbered list of paper titles. Return ONLY a JSON array of "
        "the integer indices of titles that are plausibly relevant to the topic. "
        "Be inclusive — keep anything related to the topic's field, methods, or "
        "context; drop only clearly unrelated papers.\n\n"
        f"{listing}"
    )
    try:
        from orchestrator.agents.base import bounded_invoke
        resp = bounded_invoke(_get_llm(), prompt, max_seconds=30)
        keep = {int(i) for i in json.loads(_strip_json_fence(resp.content))}
        filtered = [c for i, c in enumerate(titled) if i in keep]
        # Guard against a model that nukes everything (returns [] or a tiny
        # fraction): keep the filtered set only when it retains a believable
        # number of rows, else fall back to all titled — never ship an empty
        # or near-empty literature review off one bad classification.
        if len(filtered) >= max(1, len(titled) // 10):
            return filtered
        logger.warning("relevance filter kept too few (%d/%d) — keeping all titled",
                       len(filtered), len(titled))
        return titled
    except Exception:  # noqa: BLE001 — degrade gracefully, never drop everything
        logger.warning("relevance filter failed — keeping all titled citations")
        return titled


@tool
def scout_citations(topic: str, min_n: int = 20, deep: bool = True,
                    min_sources_deep: int = 100,
                    per_topic_timeout_s: int = 90) -> list[dict]:
    """Discover at least `min_n` academic citations for `topic`.

    Returns a list of dicts: {title, authors, year, source, url, doi}.
    Backed by engine/utils/agent_runner.research_citations_via_api.

    Internal knobs — agents should leave these alone; they exist for callers
    running behind a wall-clock deadline:

    - `deep` picks the planner. True runs the engine's DeepResearchPlanner,
      which finds materially better sources than the three hand-rolled topic
      variants below.
    - `min_sources_deep` is what actually sizes the deep plan. At the default
      100 the planner emitted 249 queries for one thesis title, batched with
      rate-limit pauses — many minutes of work.
    - `per_topic_timeout_s` caps ONE query's fan-out across the citation APIs.

    A deep plan that overruns its caller's deadline is not a slower answer, it
    is NO answer: the caller times out and every real DOI already found is
    discarded. So bound the plan rather than turning the good planner off.
    """
    # Test seam: M2_SCOUT_TOPIC_COUNT caps how many topic variants we search.
    # Production default = 3 (broad coverage). The sim sets it to 1 because
    # each topic variant fans out to multiple citation APIs + an LLM synthesis
    # call, so dropping from 3->1 cuts M2 wall-clock ~3x without changing
    # behaviour for real users.
    _TOPIC_VARIANTS = [
        "{topic} current state of research",
        "{topic} fundamentals and background",
        "{topic} methodology and approaches",
    ]
    n_topics = max(1, min(3, int(os.getenv("M2_SCOUT_TOPIC_COUNT", "3"))))
    research_topics = [t.format(topic=topic) for t in _TOPIC_VARIANTS[:n_topics]]
    tmp = Path(os.getenv("ORCHESTRATOR_SCRATCH", "/tmp/orchestrator_scratch"))
    tmp.mkdir(parents=True, exist_ok=True)
    # ENGINE-native model — see _engine_model docstring. Reverted from
    # _get_llm (LangChain) because the planner's `.generate_content()` call
    # crashed and the engine fell back to a 10-basic-query mode that
    # under-cited every scout.
    llm = _engine_model()
    try:
        # B4 use_deep_research=True: matches upstream dothesis. Enables the
        # engine's DeepResearchPlanner which expands the topic into 50+ varied
        # queries (vs our hand-rolled 3), routes them through Crossref/OpenAlex/
        # Semantic Scholar/Gemini Grounded. The hand-rolled research_topics are
        # passed too as a seed (engine uses them if planner output is thin).
        result = research_citations_via_api(
            model=llm,
            research_topics=research_topics,
            output_path=tmp / "scout_raw.md",
            target_minimum=min_n,
            use_deep_research=deep,
            topic=topic,
            scope=topic,
            min_sources_deep=min_sources_deep,
            per_topic_timeout_seconds=per_topic_timeout_s,
        )
    except ValueError:
        # The engine raises its quality gate (and discards results) when it finds
        # fewer than ~70% of target_minimum. The gate is only a threshold — it
        # doesn't change how hard the search ran — so retry with a minimal target
        # to RETURN whatever citations were found. A few real citations in the
        # lit review beat zero; the alternative was M2 silently degrading to none.
        result = research_citations_via_api(
            model=llm,
            research_topics=research_topics,
            output_path=tmp / "scout_raw.md",
            target_minimum=1,
            use_deep_research=deep,
            topic=topic,
            scope=topic,
            min_sources_deep=min_sources_deep,
            per_topic_timeout_seconds=per_topic_timeout_s,
        )
    citations = result.get("citations", [])

    def _field(c, name):
        # Citations come back as Citation OBJECTS (not dicts). Reading a falsy
        # field with `getattr(...) or c.get(...)` crashed on objects (no .get),
        # raising AttributeError that bubbled up and made the WHOLE scout return
        # nothing — the real reason M2 degraded to zero citations.
        return c.get(name) if isinstance(c, dict) else getattr(c, name, None)

    mapped = [
        {
            "title": _field(c, "title"),
            "authors": _field(c, "authors"),
            "year": _field(c, "year"),
            # The engine's Citation class exposes `.api_source` (the API the
            # citation came from — Crossref/OpenAlex/Semantic Scholar). Reading
            # `.source` always returned None and broke any downstream filter on
            # this field. Try api_source first; keep `source` as a back-compat
            # path in case anything else (or a dict ingest) uses it.
            "source": _field(c, "api_source") or _field(c, "source"),
            "url": _field(c, "url"),
            "doi": _field(c, "doi"),
        }
        for c in citations
    ]
    # Drop junk (blank/placeholder/domain-stub titles) and off-topic results
    # before they reach the citation_list / bibliography. ~40% of a real scout
    # was off-topic (phosphorus, PRISMA, frailty) on a stand-up-comedy thesis.
    return _filter_relevant_citations(mapped, topic)


@tool
def summarize_paper(pdf_path: str) -> str:
    """Read a PDF / text file and produce a concise academic summary."""
    text = _read_paper_text(pdf_path)
    if not text.strip():
        return ""
    snippet = text[:8000]
    llm = _get_llm()
    prompt = (
        "Summarize this academic paper in 3-5 sentences. Focus on: research question, "
        "method, key findings, theoretical contribution. Plain prose, no headings.\n\n"
        + snippet
    )
    return llm.invoke(prompt).content.strip()


@tool
def find_research_gaps(citations: list[dict]) -> list[dict]:
    """Identify research gaps from a list of citations.

    Returns: [{description, supporting_papers, relevance}, ...]
    Backed by an LLM call (no engine wrapping yet — pure prompt).
    """
    if not citations:
        return []
    cites_block = json.dumps(citations[:50], default=str)[:6000]
    llm = _get_llm()
    # supporting_papers carry reachability fields (doi / url / title) so
    # the frontend sidebar can render each citation as a click-to-open
    # link — without them, the M2 detail modal shows dead rows. Pull the
    # values from the citation payload that's already in `cites_block`.
    prompt = (
        "Analyze these citations and identify 2-4 specific research gaps. "
        "Respond with ONLY a JSON array, no prose. Schema: "
        '[{"description": "...", "relevance": "High|Medium|Low", '
        '"supporting_papers": [{"author": "first-author et al.", '
        '"year": 2020, "title": "...", "doi": "10.xxx/yyy", '
        '"url": "https://..."}]}]. '
        "For each supporting paper you MUST copy doi, url, and title "
        "from the matching citation in the list — do not invent values; "
        "omit a field only if it is genuinely missing from the citation.\n\n"
        f"Citations: {cites_block}"
    )
    resp = llm.invoke(prompt).content
    try:
        return list(json.loads(resp))
    except (json.JSONDecodeError, TypeError):
        logger.warning("find_research_gaps: malformed LLM response: %r", resp[:200])
        return []


class CitationCompiler:
    """Wrapper class so tests can monkeypatch at the symbol.

    The engine's CitationCompiler requires a CitationDatabase object and has a
    different method name (compile_citations). This wrapper provides the simple
    CitationCompiler(style).compile(items) interface expected by the orchestrator
    layer, delegating to a plain text formatter rather than the engine internals
    since the engine's interface is incompatible with the thin-wrapper contract.
    """

    def __init__(self, style: str):
        # Decision: store style for formatting; engine's CitationCompiler requires
        # a full CitationDatabase which we don't have at this layer. We format
        # directly here and leave deep integration for a follow-on sub-project.
        self.style = style

    def compile(self, items: list[dict]) -> str:
        """Format citation items into a reference list string."""
        lines = []
        for item in items:
            author = item.get("author") or item.get("authors") or "Unknown Author"
            year = item.get("year", "n.d.")
            title = item.get("title") or "Untitled"
            source = item.get("source") or item.get("journal") or ""
            doi = item.get("doi") or item.get("url") or ""
            if self.style.lower().startswith("apa"):
                # APA 7 format: Author, A. (Year). Title. Source. DOI
                line = f"{author} ({year}). {title}."
                if source:
                    line += f" {source}."
                if doi:
                    line += f" {doi}"
            else:
                # Generic fallback
                line = f"{author} ({year}). {title}."
            lines.append(line)
        return "\n".join(lines)


@tool
def compile_citations(items: list[dict], style: str = "apa7") -> str:
    """Format `items` into a citation list using the given style.

    Backed by CitationCompiler (wraps engine/utils/citation_compiler pattern).
    """
    return CitationCompiler(style).compile(items)


@tool
def verify_page_numbers(claim: dict) -> dict:
    """Verify a page-reference claim against the source PDF if available.

    `claim` shape: {author, year, page, quote, [pdf_path]}.
    Returns: {status: "verified" | "unverified" | "not_found", message: str}.
    Sub-project 1: returns "unverified" when no PDF path; a follow-on sub-project
    will integrate the existing PDF text-search code in engine/utils/.
    """
    pdf_path = claim.get("pdf_path")
    if not pdf_path or not Path(pdf_path).exists():
        return {"status": "unverified",
                "message": "No source PDF available — page reference marked [page?]"}
    text = _read_paper_text(pdf_path)
    quote = (claim.get("quote") or "").strip()
    if quote and quote.lower() in text.lower():
        return {"status": "verified", "message": "Quote found in source PDF"}
    return {"status": "not_found",
            "message": "Quote not found at the cited page; user should re-check"}

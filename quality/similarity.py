"""Similarity & quote-hygiene self-check — pure, local, deterministic.

A **self-check, not a Turnitin scan** (vision §7): it compares the draft against
the project's OWN sources and against itself. Two comparisons:

  (a) chapter vs each literature_source text  → similarity.source_overlap  (≥12 tokens)
  (b) chapter vs chapter (intra-thesis copy)  → similarity.intra_duplication (≥20 tokens)

Algorithm: NFC+lowercase tokenization with original-char offsets → k=7 shingles
hashed with blake2b (never builtin hash(): PYTHONHASHSEED would break
determinism) → Schleimer winnowing (w=4, rightmost-min) → seed/extend/merge with
direct token verification (so reported spans are exact and collision-proof).
Detection floor: w+k-1 = 10 tokens.

Everything is SOFT. A match is evidence, not proof — this tool is a self-check,
not an adjudicator, so nothing here ever blocks (the #1 bar: only provably-wrong
blocks). No headline percentage is reported: a handful of project sources cannot
produce a number commensurable with Turnitin's web-scale index, and printing one
invites exactly the misreading vision §7 forbids.
"""
from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from typing import Any, Optional

logger = logging.getLogger(__name__)

K = 7            # shingle size (tokens)
W = 4            # winnowing window → detection floor w+k-1 = 10 tokens
MIN_SOURCE = 12  # min reported span vs a source
MIN_INTRA = 20   # min reported span chapter-vs-chapter
MAX_SEEDS = 500
MAX_FINDINGS = 15
EXCERPT = 160

# The canonical five (m5_writing.M5_CHAPTER_ORDER). This was a sixth hand copy
# still listing `discussion`; a stale superset is harmless here but it is one
# more place the chapter list can drift from the product.
_CHAPTERS = ("intro", "lit_review", "methodology", "results", "conclusion")
# Retired key -> canonical, mirroring m5_writing.LEGACY_CHAPTER_ALIASES. Kept so
# an in-flight project's closing chapter is still scanned for overlap instead of
# being filtered out as "not a chapter".
_RETIRED_CHAPTERS = {"discussion": "conclusion"}
# Parity with orchestrator/tools/m5_writing.py's citation regex (duplicated to
# keep this module import-light; the parity test asserts they agree).
_CITATION = re.compile(r"\(([^)]{1,80}?),\s*(\d{4}|n\.d\.)\)")
_CITE_PILL = re.compile(r"\{\{cite:[^}]*\}\}")
_REFS_HEADING = re.compile(r"^\s*#*\s*(references|bibliography|tài liệu tham khảo)\s*:?\s*$", re.I | re.M)


# --- normalization / tokenization -------------------------------------------

def _strip_noise(text: str) -> str:
    """Blank out (never shorten — offsets must stay valid) the regions that
    generate false positives: grounding cite pills carry full source titles
    verbatim; inline citations repeat author+year; the reference list is a
    bibliography, not prose."""
    if not isinstance(text, str):
        return ""
    out = _CITE_PILL.sub(lambda m: " " * len(m.group(0)), text)
    out = _CITATION.sub(lambda m: " " * len(m.group(0)), out)
    m = _REFS_HEADING.search(out)
    if m:
        out = out[:m.start()] + " " * (len(out) - m.start())
    # Bibliography-shaped / low-letter-ratio lines (markdown tables, DOI lines).
    lines = out.split("\n")
    for i, ln in enumerate(lines):
        letters = sum(c.isalpha() for c in ln)
        if ln.strip() and (letters / max(len(ln), 1) < 0.5 or "doi.org" in ln.lower()
                           or ln.count("|") >= 2):
            lines[i] = " " * len(ln)
    return "\n".join(lines)


def normalize_tokens(text: str) -> list[tuple[str, int, int]]:
    """(token, start, end) with offsets into the ORIGINAL string."""
    raw = _strip_noise(text)
    if not raw:
        return []
    norm = unicodedata.normalize("NFC", raw)
    toks: list[tuple[str, int, int]] = []
    for m in re.finditer(r"[^\W_]+", norm, re.UNICODE):
        toks.append((m.group(0).lower(), m.start(), m.end()))
    return toks


def citation_spans(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _CITATION.finditer(text or "")]


# --- fingerprinting ---------------------------------------------------------

def _h(s: str) -> int:
    return int.from_bytes(hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest(), "big")


def shingle_hashes(tokens: list[str], k: int = K) -> list[int]:
    if len(tokens) < k:
        return [_h(" ".join(tokens))] if len(tokens) >= 5 else []
    return [_h(" ".join(tokens[i:i + k])) for i in range(len(tokens) - k + 1)]


def winnow(hashes: list[int], w: int = W) -> list[tuple[int, int]]:
    """Schleimer winnowing → [(hash, position)]; rightmost-min on ties."""
    if not hashes:
        return []
    if len(hashes) < w:
        mn = min(hashes)
        return [(mn, len(hashes) - 1 - hashes[::-1].index(mn))]
    out: list[tuple[int, int]] = []
    prev = -1
    for i in range(len(hashes) - w + 1):
        window = hashes[i:i + w]
        mn = min(window)
        j = i + (len(window) - 1 - window[::-1].index(mn))  # rightmost min
        if j != prev:
            out.append((hashes[j], j))
            prev = j
    return out


# --- seed → extend → merge --------------------------------------------------

def matched_spans(a_toks, b_toks, min_span: int) -> list[dict]:
    """Verbatim token runs shared by a and b. Returns bounded, exact spans."""
    a_words = [t[0] for t in a_toks]
    b_words = [t[0] for t in b_toks]
    if len(a_words) < 5 or len(b_words) < 5:
        return []
    a_fp = winnow(shingle_hashes(a_words))
    b_fp = winnow(shingle_hashes(b_words))
    b_index: dict[int, list[int]] = {}
    for hsh, pos in b_fp:
        b_index.setdefault(hsh, []).append(pos)

    seeds = []
    for hsh, apos in a_fp:
        for bpos in b_index.get(hsh, []):
            seeds.append((apos, bpos))
            if len(seeds) >= MAX_SEEDS:
                break
        if len(seeds) >= MAX_SEEDS:
            break
    truncated = len(seeds) >= MAX_SEEDS

    spans: list[tuple[int, int, int]] = []  # (a_start, b_start, length)
    for apos, bpos in seeds:
        # Verify the shingle actually matches (hash collisions must not survive).
        if a_words[apos:apos + K] != b_words[bpos:bpos + K]:
            continue
        a0, b0 = apos, bpos
        while a0 > 0 and b0 > 0 and a_words[a0 - 1] == b_words[b0 - 1]:
            a0 -= 1
            b0 -= 1
        a1, b1 = apos + K, bpos + K
        while a1 < len(a_words) and b1 < len(b_words) and a_words[a1] == b_words[b1]:
            a1 += 1
            b1 += 1
        spans.append((a0, b0, a1 - a0))

    merged: list[tuple[int, int, int]] = []
    for s in sorted(set(spans)):
        if merged:
            pa, pb, pl = merged[-1]
            if s[0] <= pa + pl + 2 and s[1] <= pb + pl + 2:  # ≤2-token gap → merge
                end = max(pa + pl, s[0] + s[2])
                merged[-1] = (pa, pb, end - pa)
                continue
        merged.append(s)

    out = []
    for a0, b0, ln in merged:
        if ln < min_span:
            continue
        out.append({"a_start": a0, "b_start": b0, "tokens": ln,
                    "a_char": (a_toks[a0][1], a_toks[min(a0 + ln, len(a_toks)) - 1][2]),
                    "b_char": (b_toks[b0][1], b_toks[min(b0 + ln, len(b_toks)) - 1][2]),
                    "truncated": truncated})
    return sorted(out, key=lambda s: (s["a_start"], s["b_start"]))


# --- corpus assembly --------------------------------------------------------

def source_texts(source) -> list[tuple[str, str]]:
    """Optional prose fields a source may carry. NOTE: abstracts are not
    persisted by today's literature_sources writers — this reads them when
    present and otherwise falls back to the title (see the design's coverage
    note; persisting abstracts is the separable follow-up)."""
    if not isinstance(source, dict):
        return []
    out = []
    for field in ("abstract", "summary"):
        v = source.get(field)
        if isinstance(v, str) and v.strip():
            out.append((field, v))
    kc = source.get("key_claims")
    if isinstance(kc, list):
        for item in kc:
            if isinstance(item, str) and item.strip():
                out.append(("key_claims", item))
            elif isinstance(item, dict):
                for k in ("quote", "claim", "text"):
                    if isinstance(item.get(k), str) and item[k].strip():
                        out.append(("key_claims", item[k]))
                        break
    if not out:
        t = source.get("title")
        if isinstance(t, str) and t.strip():
            out.append(("title", t))
    return out


def source_label(source) -> str:
    if not isinstance(source, dict):
        return "Anon"
    authors = source.get("authors") or ([source["author"]] if source.get("author") else [])
    first = authors[0] if isinstance(authors, list) and authors else None
    surname = "Anon"
    if isinstance(first, str) and first.strip():
        surname = first.split(",")[0].strip().split()[-1] if "," not in first else first.split(",")[0].strip()
    year = source.get("year")
    return f"{surname} {year}" if year else surname


def _strip_rendered(text):
    """Drop DoThesis-rendered table blocks before similarity fingerprinting — a
    rendered table is a verbatim projection of state shared across chapters (the
    same n/values appear in the cleaning section and the results tables), so it
    would otherwise read as intra-thesis 'duplication'. Lazy + fail-open."""
    if not isinstance(text, str) or "dt-rendered:begin" not in text:
        return text
    try:
        from orchestrator.tools.results_render import strip_rendered_blocks  # noqa: PLC0415
        return strip_rendered_blocks(text)
    except Exception:
        return text


def _merge_chapters(items) -> dict:
    """(chapter key, prose) pairs -> canonical chapter key -> prose.

    Delegates the retired-key rule (a legacy `discussion` block is concatenated
    ahead of the `conclusion` block, never dropped) to its one home in
    m5_writing. Lazy + fail-open: this module is deliberately import-light and a
    similarity scan must never break a run, so an import failure degrades to
    "canonical keys only" rather than raising.
    """
    pairs = [(str(k).lower(), v) for k, v in items]
    try:
        from orchestrator.tools.m5_writing import merge_chapter_prose  # noqa: PLC0415
        return merge_chapter_prose(pairs)
    except Exception:
        logger.warning("similarity: falling back to un-aliased chapter keys", exc_info=True)
        return {k: v for k, v in pairs if k in _CHAPTERS}


def _resolve_chapters(m5) -> dict:
    if isinstance(m5, dict):
        merged = _merge_chapters(
            (k, v.get("prose") if isinstance(v, dict) else v) for k, v in m5.items())
        return {k: _strip_rendered(v) for k, v in merged.items()}
    if isinstance(m5, list):
        pairs = []
        for s in m5:
            if isinstance(s, dict):
                name = str(s.get("title") or s.get("name") or "").lower().replace(" ", "_")
                # Canonical chapters only — a References section is not prose.
                # Retired names are matched too, then folded onto their canonical
                # key by _merge_chapters.
                for c in (*_CHAPTERS, *_RETIRED_CHAPTERS):
                    if c in name:
                        pairs.append((c, s.get("prose") or s.get("content")))
                        break
        return {k: _strip_rendered(v) for k, v in _merge_chapters(pairs).items()}
    return {}


def _usable(prose) -> bool:
    if not isinstance(prose, str) or len(prose.strip()) < 40:
        return False
    return not any(x in prose.lower() for x in ("todo", "placeholder", "to be filled"))


# --- quote hygiene ----------------------------------------------------------

def quote_regions(text: str) -> list[tuple[int, int]]:
    regions = []
    for pat in (r'"([^"\n]{1,1000})"', r'“([^”\n]{1,1000})”', r'«([^»\n]{1,1000})»'):
        regions += [(m.start(), m.end()) for m in re.finditer(pat, text or "")]
    for m in re.finditer(r"^>.*$", text or "", re.M):
        regions.append((m.start(), m.end()))
    return regions


def _is_quoted(char_span, regions) -> bool:
    s, e = char_span
    return any(r0 <= s and e <= r1 for r0, r1 in regions)


def _is_cited(text, char_span) -> bool:
    _s, e = char_span
    for c0, c1 in citation_spans(text):
        if c0 >= e and c0 - e <= 200:   # citation shortly after the span
            return True
        if abs(c0 - e) <= 200:          # or adjacent within the sentence window
            return True
    return False


# --- public API -------------------------------------------------------------

def _slices(context_store: dict) -> tuple:
    """Tolerate BOTH store shapes: the nested column shape the rubric reads
    (m5_writing/m2_literature/m3_design) and the FLAT contextStore that
    store.load() returns (the documented footgun — same tolerance
    agent/coherence.py applies)."""
    cs = context_store if isinstance(context_store, dict) else {}
    if any(k in cs for k in ("m5_writing", "m2_literature", "m3_design")):
        m5 = cs.get("m5_writing") or {}
        return (m5.get("final_sections") or m5.get("chapters") or {},
                (cs.get("m2_literature") or {}).get("literature_sources") or [],
                (cs.get("m3_design") or {}).get("hypotheses") or [])
    return (cs.get("final_sections") or cs.get("chapters") or {},
            cs.get("literature_sources") or [], cs.get("hypotheses") or [])


def check_similarity(context_store: dict) -> dict:
    """Raw matches: source overlaps + intra-thesis duplication. Never raises."""
    try:
        m5src, sources, hyps = _slices(context_store)
        chapters = _resolve_chapters(m5src)
        chapters = {c: p for c, p in chapters.items() if _usable(p)}
        hyp_texts = {str(h).lower() for h in hyps}

        tok_cache = {c: normalize_tokens(p) for c, p in chapters.items()}
        source_overlaps, intra = [], []
        with_text = title_only = 0

        for src in sources:
            texts = source_texts(src)
            if not texts:
                continue
            (with_text := with_text + 1) if texts[0][0] != "title" else (title_only := title_only + 1)
            label = source_label(src)
            for field, stext in texts:
                s_toks = normalize_tokens(stext)
                for chap, c_toks in tok_cache.items():
                    for sp in matched_spans(c_toks, s_toks, MIN_SOURCE):
                        excerpt = chapters[chap][sp["a_char"][0]:sp["a_char"][1]][:EXCERPT]
                        source_overlaps.append({"chapter": chap, "source": label, "field": field,
                                                "tokens": sp["tokens"], "excerpt": excerpt,
                                                "char": sp["a_char"], "truncated": sp["truncated"]})

        names = [c for c in _CHAPTERS if c in tok_cache]
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                for sp in matched_spans(tok_cache[a], tok_cache[b], MIN_INTRA):
                    excerpt = chapters[a][sp["a_char"][0]:sp["a_char"][1]][:EXCERPT]
                    # Chapters legitimately restate hypothesis statements.
                    if any(excerpt.lower().strip() in h or h in excerpt.lower() for h in hyp_texts if h):
                        continue
                    intra.append({"chapter": a, "other_chapter": b, "tokens": sp["tokens"],
                                  "excerpt": excerpt, "char": sp["a_char"], "truncated": sp["truncated"]})

        return {"source_overlaps": source_overlaps, "intra_duplication": intra,
                "sources_with_text": with_text, "sources_title_only": title_only}
    except Exception:
        logger.exception("check_similarity crashed")
        return {"source_overlaps": [], "intra_duplication": [], "sources_with_text": 0,
                "sources_title_only": 0, "crashed": True}


def similarity_findings(context_store: dict) -> list[dict]:
    """Rubric-shaped findings ({issue, fix, chapter, severity}) — all soft."""
    raw = check_similarity(context_store)
    m5src, _s, _h = _slices(context_store)
    chapters = _resolve_chapters(m5src)
    findings: list[dict] = []
    for m in raw["source_overlaps"]:
        prose = chapters.get(m["chapter"]) or ""
        quoted = _is_quoted(m["char"], quote_regions(prose))
        cited = _is_cited(prose, m["char"])
        if quoted and cited:
            continue  # clean
        n = m["tokens"]
        if quoted and not cited:
            fix = f"Cite {m['source']} with a page number."
            issue = f"This {n}-word quoted span matches {m['source']} but has no citation: “{m['excerpt']}”"
        elif cited and not quoted:
            fix = "Put it in quotation marks with a page number, or paraphrase."
            issue = (f"This {n}-word span matches {m['source']} verbatim and is cited but not quoted: "
                     f"“{m['excerpt']}”")
        else:
            fix = f"Quote it with a page number, or paraphrase."
            issue = f"This {n}-word span matches {m['source']}: “{m['excerpt']}”"
        findings.append({"issue": issue, "fix": fix, "chapter": m["chapter"], "severity": "soft"})
    for m in raw["intra_duplication"]:
        findings.append({
            "issue": f"This {m['tokens']}-word span in {m['chapter']} duplicates {m['other_chapter']} "
                     f"verbatim: “{m['excerpt']}”",
            "fix": "Consolidate or rewrite — chapters should not repeat each other.",
            "chapter": m["chapter"], "severity": "soft"})
    return findings[:MAX_FINDINGS]


def similarity_report(context_store: dict) -> dict:
    """Bounded pre-export report. `headline` is deliberately null — see module doc."""
    try:
        raw = check_similarity(context_store)
        spans = sorted(raw["source_overlaps"] + raw["intra_duplication"],
                       key=lambda s: (-s["tokens"], s["chapter"], s["char"][0]))
        per_source: dict[str, int] = {}
        for m in raw["source_overlaps"]:
            per_source[m["source"]] = per_source.get(m["source"], 0) + 1
        return {
            "headline": None,  # never a percentage — see module docstring
            "counts": {"source_overlaps": len(raw["source_overlaps"]),
                       "intra_duplication": len(raw["intra_duplication"]),
                       "words_matched": sum(s["tokens"] for s in spans)},
            "top_spans": [{k: s[k] for k in ("chapter", "tokens", "excerpt") if k in s} for s in spans[:10]],
            "per_source": dict(list(per_source.items())[:20]),
            "truncated": any(s.get("truncated") for s in spans),
            "coverage_note": (
                f"Self-check against this project's own {raw['sources_with_text']} source text(s) "
                f"({raw['sources_title_only']} title-only) and chapter-to-chapter duplication. "
                "This is NOT a Turnitin scan and cannot substitute for one."),
        }
    except Exception:
        logger.exception("similarity_report crashed")
        return {"headline": None, "counts": {}, "top_spans": [], "per_source": {},
                "truncated": False, "coverage_note": "similarity report unavailable"}

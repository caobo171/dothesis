"""Humanize pass — rewrite drafted prose so it stops reading as LLM output.

Re-implementation of the M21 "router-anchor" pipeline (v10.1), which won the
2026-04 humanizer bake-off. The original is TypeScript on the archived branch
`feat/humanizer-v8-bakeoff` (`backend/src/services/humanizer/`); none of it
survived the Python/deepagents rewrite, so this ports the *findings*, not code.

WHY THE DESIGN LOOKS LIKE THIS — the one result that drives everything:

    Style anchors must sit OUTSIDE the LLM training distribution.

Validated across a 12-text corpus and two independent detectors (Sapling,
Copyscape):

  - pre-1928 public-domain prose (Russell, Mill, James, Strunk) → works
  - a real person's own writing, idiosyncrasies and typos included → works
  - Wikipedia / modern CC-licensed web text → FAILS catastrophically (the v11
    "Tier 1" run: detector scores went UP across the board)

Modern web text is heavily *in* the training corpus, so mimicking it lands on
exactly the distribution detectors were trained to flag. Generic web-scraped
anchors are therefore permanently ruled out — see references/anchors/README.md.

Two more findings worth not re-discovering the hard way:

  - Back-translation layered AFTER anchoring is a REGRESSION, not a stack. The
    round-trip strips the anchor's fingerprint and returns the text to
    LLM-distribution phrasing (method M22: four passing texts went 0-1 → 100).
  - Stylometric scoring does not predict detector output, so the anchor is
    picked by an LLM router rather than a readability metric (this is the only
    difference between M21 and its predecessors, and it's why M21 won).

DELTA FROM THE ORIGINAL — the frozen-token gate:

The TS humanizer rewrote marketing and blog copy, where a reworded number costs
nothing. Here the input is a thesis results chapter: every β, p-value, N,
Cronbach's α, "Bảng 4.3" and (Tác giả, 2020) is a claim about real SPSS /
SmartPLS output. So every rewrite is diffed against its source, and a rewrite
that drops, invents, or alters a frozen token is REJECTED — the original prose
is kept instead. A humanized chapter that quietly turns p = 0.032 into p = 0.03
is worse than an un-humanized one, because nobody re-checks prose that reads
well.
"""
from __future__ import annotations

import json
import logging
import os
import re
from collections import Counter
from pathlib import Path

logger = logging.getLogger(__name__)

# Anchors ship as data, not code, so non-engineers can add one by dropping a
# .txt next to the manifest. Repo root is three levels up from this file
# (orchestrator/tools/humanize.py). The env var exists for tests and for
# deployments that mount the skills tree elsewhere.
_DEFAULT_ANCHOR_DIR = (
    Path(__file__).resolve().parents[2]
    / "skills" / "dothesis-humanize" / "references" / "anchors"
)


def anchor_dir() -> Path:
    """Directory holding anchor .txt files + manifest.json."""
    override = os.getenv("DOTHESIS_ANCHOR_DIR")
    return Path(override) if override else _DEFAULT_ANCHOR_DIR


# --- Deterministic AI-tell stripping -------------------------------------
#
# Cheap (pure string ops, no LLM) and runs on BOTH sides of the rewrite: on the
# input so the model isn't shown the tells it should avoid, and on the output to
# catch what it reintroduced. On its own this barely moves a detector (method
# M17 measured Δ≈0) — it earns its place only as the wrapper around an anchored
# rewrite, which is how M21 uses it.
#
# Substitutions are conservative on purpose. An over-eager list mangles
# legitimate academic phrasing, and a mangled sentence is a bigger problem than
# a surviving cliché.

_SUBS_EN: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\butilize[ds]?\b", re.I), "use"),
    (re.compile(r"\bfacilitate[ds]?\b", re.I), "help"),
    (re.compile(r"\bleverage[ds]?\b", re.I), "use"),
    (re.compile(r"\bencompass(?:e[ds])?\b", re.I), "cover"),
    (re.compile(r"\bunderscore[ds]?\b", re.I), "highlight"),
    (re.compile(r"\bdelve[ds]? into\b", re.I), "look at"),
    (re.compile(r"\bpivotal role\b", re.I), "central role"),
    (re.compile(r"\bsignificant potential\b", re.I), "real promise"),
    (re.compile(r"\bcutting[- ]edge\b", re.I), "recent"),
    (re.compile(r"\bever[- ]evolving\b", re.I), "changing"),
    (re.compile(r"(^|[.!?]\s+)It is worth noting that\s+"), r"\1"),
    (re.compile(r"(^|[.!?]\s+)It is important to note that\s+"), r"\1"),
]

# Vietnamese: the padding constructions that show up in every LLM-drafted
# chapter. "rằng" after a reporting verb and "một cách X" adverbials are the two
# highest-frequency ones; both are grammatical but sound translated.
_SUBS_VI: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bcho thấy rằng\b", re.I), "cho thấy"),
    (re.compile(r"\bchỉ ra rằng\b", re.I), "chỉ ra"),
    (re.compile(r"\bkhẳng định rằng\b", re.I), "khẳng định"),
    (re.compile(r"\bcó thể thấy rằng\b", re.I), "có thể thấy"),
    (re.compile(r"\bmột cách đáng kể\b", re.I), "đáng kể"),
    (re.compile(r"\bmột cách rõ rệt\b", re.I), "rõ rệt"),
    (re.compile(r"\bmột cách tích cực\b", re.I), "tích cực"),
    (re.compile(r"\bđóng một vai trò\b", re.I), "đóng vai trò"),
    (re.compile(r"\btrong bối cảnh hiện nay\b", re.I), "hiện nay"),
]

# Connectors are stripped ONLY when they open a sentence. The tell is the
# metronome — "Hơn nữa, X. Bên cạnh đó, Y. Đồng thời, Z." — not the words, which
# are ordinary Vietnamese mid-sentence.
_START_CONNECTORS_EN = [
    "Furthermore", "Moreover", "Additionally", "In conclusion",
    "In summary", "Notably", "Importantly",
]
_START_CONNECTORS_VI = [
    "Hơn nữa", "Bên cạnh đó", "Đồng thời", "Đáng chú ý",
    "Nhìn chung", "Không những vậy", "Có thể nói",
]


def _strip_start_connectors(text: str, connectors: list[str]) -> str:
    out = text
    for c in connectors:
        pat = re.compile(rf"(^|[.!?]\s+){re.escape(c)},\s+(\w)", re.MULTILINE)
        out = pat.sub(lambda m: m.group(1) + m.group(2).upper(), out)
    return out


def strip_ai_tells(text: str, language: str = "vi") -> str:
    """Remove the highest-signal LLM vocabulary tells. Deterministic, free."""
    if not text:
        return text
    vi = (language or "").lower().startswith("vi")
    out = text
    for pat, repl in (_SUBS_VI if vi else _SUBS_EN):
        out = pat.sub(repl, out)
    out = _strip_start_connectors(
        out, _START_CONNECTORS_VI if vi else _START_CONNECTORS_EN)
    # Em/en dashes as parenthetical punctuation are near-absent in human
    # Vietnamese academic prose and near-universal in LLM output. Only touch the
    # spaced form so ranges ("2019–2023") and hyphenated terms survive.
    if vi:
        out = re.sub(r"\s+[—–]\s+", ", ", out)
    return out


# --- Frozen tokens -------------------------------------------------------
#
# What a humanizing rewrite is NOT allowed to touch. Extracted from the source,
# handed to the model in the prompt, then re-extracted from the rewrite and
# diffed. Both directions matter: a DROPPED token means a finding vanished, an
# ADDED one means the model invented a statistic or a source.

_WS_RE = re.compile(r"\s+")
_NUM_RE = re.compile(r"\d+(?:[.,]\d+)*%?")
_REF_RE = re.compile(
    r"\b(?:Bảng|Hình|Biểu\s*đồ|Sơ\s*đồ|Phụ\s*lục|Chương|"
    r"Table|Figure|Fig\.?|Appendix|Chapter)\s*\d+(?:[.,]\d+)*",
    re.IGNORECASE,
)
_PAREN_RE = re.compile(r"\(([^()]{1,200})\)")
_YEAR_RE = re.compile(r"\b(\d{4}[a-z]?)\b")
_BARE_YEAR_PAREN_RE = re.compile(r"\((\d{4}[a-z]?)\)")
# A word starting with a letter. Capitalization is tested with str.isupper(),
# NOT a regex range: [A-ZÀ-Ỹ] looks right and is wrong, because the precomposed
# Vietnamese block interleaves cases — 'ấ' (U+1EA5) sits inside À-Ỹ, so that
# class matches lowercase syllables and reads "thấy" as a surname.
_WORD_RE = re.compile(r"[^\W\d_][\w'’\-]*")
# Words that may sit BETWEEN surnames in a narrative citation. Walking back over
# them keeps "Trần và Nguyễn (2021)" anchored on the first author, matching what
# the parenthetical form "(Trần & Nguyễn, 2021)" yields. ("&" isn't listed
# because _WORD_RE never emits punctuation — it's skipped for free.)
_NAME_JOINERS = {"và", "and", "et", "al", "cộng", "sự"}


def _capitalized_words(s: str) -> list[str]:
    return [w for w in _WORD_RE.findall(s) if w[:1].isupper()]


def _lead_surname(lead: str) -> str | None:
    """First surname of the author run immediately preceding a "(year)"."""
    words = _WORD_RE.findall(lead)
    run: list[str] = []
    for w in reversed(words):
        if w[:1].isupper():
            run.append(w)
        elif w.lower() in _NAME_JOINERS:
            continue
        else:
            break
    return run[-1] if run else None


def _cite_tokens(text: str) -> list[str]:
    """Citations as `surname|year`, normalized across both citation forms.

    "(Nguyễn, 2020)" and "Nguyễn (2020)" produce the SAME token on purpose — a
    rewrite is allowed to move a citation between parenthetical and narrative
    form (that's a normal writing choice), but not to drop or invent one.
    """
    out: list[str] = []
    for chunk in _PAREN_RE.findall(text):
        if not _YEAR_RE.search(chunk):
            continue
        for part in chunk.split(";"):
            years = _YEAR_RE.findall(part)
            names = _capitalized_words(part)
            if not names:
                # Bare "(2020)" — the narrative form, whose surname sits outside
                # the parens. Handled below, so skip it here rather than emit a
                # nameless token that would never match its counterpart.
                continue
            for y in years:
                out.append(f"{names[0].lower()}|{y}")
    for m in _BARE_YEAR_PAREN_RE.finditer(text):
        lead = text[max(0, m.start() - 60):m.start()]
        # Never walk back across an earlier citation. In "Nguyễn (2019) và Trần
        # & Lê (2021)" the joiner "và" would otherwise let the walk skip past
        # 2019's closing paren and read the 2021 citation as Nguyễn's — which
        # rejected correct rewrites of any sentence citing two works in a row.
        boundary = max(lead.rfind(")"), lead.rfind("("))
        if boundary != -1:
            lead = lead[boundary + 1:]
        surname = _lead_surname(lead)
        if surname:
            out.append(f"{surname.lower()}|{m.group(1)}")
    return out


def frozen_tokens(text: str) -> Counter:
    """Multiset of everything a rewrite must preserve verbatim."""
    c: Counter = Counter()
    for n in _NUM_RE.findall(text or ""):
        c[f"num:{n}"] += 1
    for r in _REF_RE.findall(text or ""):
        # Normalize case + inner spacing so "Bảng 4.3" and "bảng  4.3" are the
        # same token — a rewrite may legitimately move the ref mid-sentence.
        norm = _WS_RE.sub(" ", r).strip().lower()
        c[f"ref:{norm}"] += 1
    for t in _cite_tokens(text or ""):
        c[f"cite:{t}"] += 1
    return c


def verify_frozen(original: str, rewritten: str) -> dict:
    """Diff the frozen tokens of a rewrite against its source.

    Returns {"ok", "missing", "added"}. `missing` = present in the source and
    gone from the rewrite (a lost finding). `added` = present in the rewrite
    only (a fabricated number or source). Either is a rejection.
    """
    before, after = frozen_tokens(original), frozen_tokens(rewritten)
    missing = sorted((before - after).elements())
    added = sorted((after - before).elements())
    return {"ok": not missing and not added, "missing": missing, "added": added}


# --- Anchor library ------------------------------------------------------


def load_anchors(language: str | None = None) -> list[dict]:
    """Read the anchor manifest. Returns [] when none are installed.

    Manifest shape (skills/dothesis-humanize/references/anchors/manifest.json):

        {"anchors": [
          {"id": "vi_results_2019", "language": "vi",
           "file": "vi_results_2019.txt",
           "desc": "PICK FOR: quantitative results chapters reporting SPSS output…"}
        ]}

    An entry whose .txt is missing is skipped with a warning rather than raising
    — one bad file must not take out the whole pass.
    """
    d = anchor_dir()
    manifest = d / "manifest.json"
    if not manifest.is_file():
        return []
    try:
        raw = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("humanize: anchors/manifest.json is not valid JSON")
        return []
    out: list[dict] = []
    for entry in raw.get("anchors") or []:
        if language and entry.get("language") and entry["language"] != language:
            continue
        path = d / (entry.get("file") or f"{entry.get('id')}.txt")
        if not path.is_file():
            logger.warning("humanize: anchor file missing: %s", path)
            continue
        try:
            text = path.read_text(encoding="utf-8").strip()
        except Exception:
            logger.exception("humanize: could not read anchor %s", path)
            continue
        if not text:
            continue
        out.append({"id": entry.get("id") or path.stem,
                    "desc": entry.get("desc") or "",
                    "text": text})
    return out


# --- Prompts -------------------------------------------------------------

_ROUTER_PROMPT = """You are an anchor-matcher. Pick exactly one style anchor whose register best
matches the INPUT_TEXT. Match on topic/domain, voice, and stance.

ANCHORS:
{anchor_list}

Answer with the anchor id ALONE — no punctuation, no explanation."""

_REWRITE_PROMPT = """Below are paragraphs written by a real human. Study their cadence, sentence-length
variance, clause structure, and punctuation rhythm. DO NOT copy their phrases,
their subject matter, or their level of formality — mimic ONLY the rhythm and the
natural unevenness of real writing.

EXAMPLES:
{anchor}

Rewrite the user's text in {language_name}, borrowing the anchor's RHYTHM but
keeping the ORIGINAL text's own register.

NATURALNESS — write {language_name} the way a native academic writer actually
writes it. Idiomatic word choice and collocations only; never stiff, translated,
or awkward phrasing. Readability must not drop below the original — if your only
way to reword a clause is a clunkier one, leave that clause as it was. In
Vietnamese specifically, keep natural prepositions/collocations (e.g. "khảo sát
được gửi đến / thu thập từ" rather than a stilted "phát … tới"); do not swap a
natural word for a rarer stiff synonym just to look different.

REGISTER — this is critical:
- Match the formality of the ORIGINAL, not the anchor. If the original is a formal
  academic passage (a thesis results chapter, a report), the rewrite stays formal
  academic prose — impersonal, precise, third-person. You are loosening templated
  phrasing, NOT lowering the register to casual/spoken language.
- FORBIDDEN — these read as spoken/texting, never as human academic writing:
  · conversational fillers & discourse particles
    (Vietnamese: "à", "ừ", "nhỉ", "nhé", "luôn ấy", "ấy mà", "khá là", "kiểu",
     "nói chung là", "thật ra thì"; English: "well", "you know", "I mean", "sort of").
  · rhetorical questions to the reader ("đúng không nhỉ?", "right?").
  · first-person narration or asides about your own process
    ("mình vừa kiểm tra lại…", "mình thấy…", "as I checked…") — keep the
    impersonal academic voice; the writer never appears in the sentence.
  · interjections, emoji, or exclamations.

ABSOLUTE CONSTRAINTS — a rewrite that breaks any of these is discarded:
{protected_section}
- Invent NOTHING. No new numbers, no new citations, no new claims, and no new
  narrative actions. If the source does not state it, it does not go in.
- Keep every factual claim and its direction (a positive effect stays positive).
- Preserve the paragraph and heading structure, and any markdown tables verbatim.

Output the rewritten text ONLY — no preamble, no commentary, no code fences."""

_REPAIR_PROMPT = """Your previous rewrite broke the frozen-token rule. Fix it with the SMALLEST
possible edit — keep the voice and rhythm you already produced.

{problem}

Output the corrected text ONLY — no preamble, no commentary, no code fences."""


def _language_name(language: str) -> str:
    return "Vietnamese" if (language or "").lower().startswith("vi") else "English"


def _clean_output(raw: str) -> str:
    """Strip code fences / leading chatter a model may wrap the rewrite in."""
    t = (raw or "").strip()
    t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _get_llm(temperature: float):
    from orchestrator.llm import get_orchestrator_llm  # noqa: PLC0415 — import-light

    return get_orchestrator_llm(temperature=temperature)


def _invoke(llm, prompt: str) -> str:
    from orchestrator.message_utils import text_of  # noqa: PLC0415

    return text_of(llm.invoke(prompt))


def pick_anchor(text: str, anchors: list[dict], llm=None) -> dict:
    """LLM router: choose the anchor whose register fits `text`.

    A stylometric scorer was tried here first and did not predict detector
    output at all (methods M5/M7/M19); routing by an LLM read of the register is
    the change that made M21 win. With one anchor installed there is nothing to
    route, so the call is skipped.
    """
    if len(anchors) == 1:
        return anchors[0]
    listing = "\n".join(f"- {a['id']}: {a['desc']}" for a in anchors)
    try:
        llm = llm or _get_llm(0.0)
        raw = _invoke(llm, _ROUTER_PROMPT.format(anchor_list=listing)
                      + f"\n\nINPUT_TEXT:\n{text[:4000]}")
        pick = _clean_output(raw).split()[0].strip(".,\"'") if raw.strip() else ""
        for a in anchors:
            if a["id"].lower() == pick.lower():
                return a
    except Exception:
        logger.exception("humanize: anchor router failed, using first anchor")
    # Defensive default rather than an error: a wrong-register anchor still
    # humanizes; no anchor at all does nothing.
    return anchors[0]


def humanize_prose(
    text: str,
    *,
    language: str = "vi",
    user_anchor: str | None = None,
    anchor_id: str | None = None,
    llm=None,
) -> dict:
    """Run the anchored rewrite over one passage.

    `user_anchor` is ~150 words of the student's own writing. It takes priority
    over the installed library: a per-person anchor was the single strongest
    result in the bake-off, because idiosyncratic real writing is by definition
    outside the training distribution.

    Returns:
        {"ok", "text", "anchor", "changed", "frozen", "repairs", "error"}

    On rejection `ok` is False and `text` is the ORIGINAL, unmodified. The
    caller ships the original — never a rewrite that failed verification.
    """
    if not (text or "").strip():
        return {"ok": False, "error": "empty_input", "text": text, "changed": False}

    anchors = load_anchors(language)
    if user_anchor and user_anchor.strip():
        anchors = [{"id": "user_supplied", "desc": "The student's own writing.",
                    "text": user_anchor.strip()}]
    elif anchor_id:
        anchors = [a for a in anchors if a["id"] == anchor_id] or anchors

    if not anchors:
        # Refusing beats rewriting without an anchor. An unanchored "make this
        # sound human" rewrite lands right back in the LLM distribution — it
        # produces text that FEELS improved and scores the same or worse, which
        # is the worst outcome because it's invisible.
        return {
            "ok": False,
            "error": "no_anchor",
            "text": text,
            "changed": False,
            "hint": (
                "No style anchor is installed for this language. Ask the student "
                "for ~150 words they wrote themselves before using AI (an old "
                "essay, a report, anything) and pass it as user_anchor — or "
                "install a library anchor per "
                "skills/dothesis-humanize/references/anchors/README.md."
            ),
        }

    frozen = frozen_tokens(text)
    frozen_lines = [
        f"  {t.split(':', 1)[1]}" for t in sorted(frozen)
        if t.startswith(("num:", "ref:"))
    ]
    # Citations are listed in their source form so the model sees what to keep,
    # while verification stays form-insensitive (see _cite_tokens).
    cites = sorted({t.split(":", 1)[1].replace("|", ", ")
                    for t in frozen if t.startswith("cite:")})
    frozen_lines += [f"  ({c})" for c in cites]
    # Only present the "must appear verbatim" list when there ARE protected
    # tokens. Feeding a literal "(none)" under that instruction made the model
    # dutifully echo "(none)" into the prose — protect against that leak.
    if frozen_lines:
        protected_section = (
            "- Every one of these tokens must appear in your output, character "
            "for character. Do not round, reformat, translate, or spell them "
            "out:\n" + "\n".join(frozen_lines)
        )
    else:
        protected_section = (
            "- This passage contains no numbers or citations — there are no "
            "protected tokens, and you must not introduce any."
        )

    llm = llm or _get_llm(0.95)
    cleaned = strip_ai_tells(text, language)
    anchor = pick_anchor(cleaned, anchors, llm=llm)

    system = _REWRITE_PROMPT.format(
        anchor=anchor["text"],
        language_name=_language_name(language),
        protected_section=protected_section,
    )
    try:
        out = _clean_output(_invoke(llm, f"{system}\n\nTEXT TO REWRITE:\n{cleaned}"))
    except Exception as e:
        logger.exception("humanize: rewrite call failed")
        return {"ok": False, "error": "llm_failed", "detail": str(e),
                "text": text, "changed": False}
    if not out:
        return {"ok": False, "error": "empty_rewrite", "text": text, "changed": False}

    out = strip_ai_tells(out, language)
    check = verify_frozen(text, out)
    repairs = 0

    if not check["ok"]:
        # One repair attempt, with the exact diff. Two failures means the model
        # can't hold the numbers for this passage; keep the original.
        problem_lines = []
        if check["missing"]:
            problem_lines.append(
                "These tokens are in the ORIGINAL but missing from your rewrite. "
                "Put each one back, unchanged:\n"
                + "\n".join(f"  {m.split(':', 1)[1]}" for m in check["missing"]))
        if check["added"]:
            problem_lines.append(
                "These appear in your rewrite but NOT in the original — you "
                "invented them. Remove them:\n"
                + "\n".join(f"  {a.split(':', 1)[1]}" for a in check["added"]))
        try:
            repaired = _clean_output(_invoke(
                llm,
                _REPAIR_PROMPT.format(problem="\n\n".join(problem_lines))
                + f"\n\nORIGINAL:\n{text}\n\nYOUR REWRITE:\n{out}"))
            repairs = 1
            if repaired:
                repaired = strip_ai_tells(repaired, language)
                recheck = verify_frozen(text, repaired)
                if recheck["ok"]:
                    out, check = repaired, recheck
                else:
                    check = recheck
        except Exception:
            logger.exception("humanize: repair call failed")

    if not check["ok"]:
        return {"ok": False, "error": "frozen_violation", "text": text,
                "changed": False, "anchor": anchor["id"], "frozen": check,
                "repairs": repairs,
                "hint": "The rewrite altered numbers or citations, so the "
                        "original was kept. Report this — do not claim the "
                        "passage was humanized."}

    return {"ok": True, "text": out, "anchor": anchor["id"],
            "changed": out.strip() != text.strip(), "frozen": check,
            "repairs": repairs}


def humanize_sections(
    sections: list[dict],
    *,
    language: str = "vi",
    user_anchor: str | None = None,
    llm=None,
) -> tuple[list[dict], list[dict]]:
    """Humanize a composed chapter list in place-ish, section by section.

    Returns `(sections, report)`. Sections that fail verification keep their
    original prose — the export must never be blocked by this pass, and must
    never silently ship an unverified rewrite either. "References" is skipped:
    a bibliography has no voice to humanize and everything in it is frozen.
    """
    out: list[dict] = []
    report: list[dict] = []
    for s in sections or []:
        title = s.get("title") or ""
        prose = s.get("prose") or ""
        if title == "References" or not prose.strip():
            out.append(s)
            continue
        r = humanize_prose(prose, language=language, user_anchor=user_anchor, llm=llm)
        report.append({"title": title, "ok": r.get("ok", False),
                       "anchor": r.get("anchor"), "error": r.get("error"),
                       "frozen": r.get("frozen")})
        out.append({**s, "prose": r["text"]} if r.get("ok") else s)
    return out, report

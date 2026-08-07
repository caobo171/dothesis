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

from contextvars import ContextVar

import json
import logging
import os
import re
import unicodedata
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
    # "plays a crucial/vital role" is the same tell as "pivotal role" and at
    # least as frequent; it survived because only the adjective was listed.
    (re.compile(r"\b(?:crucial|vital|critical) role\b", re.I), "central role"),
    # Filler that says nothing: both are pure length, and the shorter form is
    # what a person writes.
    (re.compile(r"\bin order to\b", re.I), "to"),
    (re.compile(r"\bdue to the fact that\b", re.I), "because"),
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
    # "Ngoài ra" is the highest-frequency opener in LLM-drafted Vietnamese and
    # was missing from this list. "Đặc biệt" is the same metronome one rung up
    # in emphasis; its comma-less form "Đặc biệt là …" is in _OPENERS_VI, since
    # this list only matches connectors that take a comma.
    "Ngoài ra", "Đặc biệt",
]

# Padding that opens a sentence and can be deleted whole, unlike the
# substitutions above which swap one word for another. Separate from
# _START_CONNECTORS_* because these are phrases, not single connectors, and
# separate from _SUBS_* because deleting a sentence opener has to hand the
# capital letter to the word that becomes the new opener — which the _SUBS_
# path did not do: "The data holds. It is worth noting that results are
# stable." came out as "…holds. results are stable."
_OPENERS_EN = [
    r"It is worth noting that",
    r"It is important to note that",
    r"In today'?s [\w\s-]{0,24}?(?:world|age|era|landscape|environment),",
]
_OPENERS_VI = [
    r"Không thể phủ nhận rằng",
    r"Có thể khẳng định rằng",
    r"Đặc biệt là",
]


def _strip_openers(text: str, phrases: list[str]) -> str:
    """Delete a padding phrase that opens a sentence, capitalizing what follows."""
    out = text
    for phrase in phrases:
        pat = re.compile(rf"(^|[.!?]\s+){phrase}\s+(\w)", re.IGNORECASE | re.MULTILINE)
        out = pat.sub(lambda m: m.group(1) + m.group(2).upper(), out)
    return out


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
    out = _strip_openers(out, _OPENERS_VI if vi else _OPENERS_EN)
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


# Our own multiset key, as it would look if it escaped into prose:
# "cite:bass|1994" -> "bass|1994". Nothing a person writes looks like this.
# Groups: (full match is group 0), surname = 1, year = 2 — used by the scrubber
# that rewrites "(Bass and Avolio, bass|1994)" back to "(Bass and Avolio, 1994)".
_TOKEN_SYNTAX_RE = re.compile(r"([^\W\d_][\w'’\-]*)\|(\d{4}[a-z]?)")


def describe_token(token: str) -> str:
    """One frozen token, written the way it appears in the text.

    The repair prompt used to print the raw multiset key — `cite:bass|1994`
    sliced to `bass|1994` — under the instruction "put each one back,
    unchanged". A model followed that literally and a student's dissertation
    shipped reading "(Bass and Avolio, bass|1994)". The frozen gate could not
    catch it either, because that string re-extracts as the very token it was
    asked to restore, so the corruption satisfies the check.

    A prompt is read by something that will do what it says. It gets prose.
    """
    kind, _, rest = (token or "").partition(":")
    if kind == "cite":
        surname, _, year = rest.partition("|")
        return f"the citation {surname.capitalize()} ({year})" if year else rest
    if kind == "ref":
        # Stored lowercased for comparison; title-case the label back.
        head, _, num = rest.partition(" ")
        return f"{head.capitalize()} {num}".strip() if num else rest.capitalize()
    return rest or token


def _scrub_token_syntax(text: str, original: str) -> str:
    """Drop leaked multiset keys from prose, keeping only the year.

    Observed ship: "(Bass and Avolio, bass|1994)" — the repair path had printed
    the internal key and the model pasted it next to the already-correct author
    run. The year is what the citation needs; the `surname|` prefix is ours.

    Only forms that were NOT already in the original are touched, so a bizarre
    but intentional `code|2020` the student wrote themselves is left alone.
    """
    if not text or not _TOKEN_SYNTAX_RE.search(text):
        return text
    original = original or ""

    def repl(m: re.Match) -> str:
        full = m.group(0)
        if full in original:
            return full
        return m.group(2)  # year only

    return _TOKEN_SYNTAX_RE.sub(repl, text)


# Structural cross-refs the model likes to lowercase after a full stop
# ("…reported later. table 4.2 presents…"). Title-casing the label is always
# correct for the academic register this product rewrites; APA/thesis house
# style capitalises Table/Figure/Chapter, and Vietnamese Bảng/Hình/Chương.
_REF_LABEL_RE = re.compile(
    r"\b("
    r"[Bb]ảng|[Hh]ình|[Bb]iểu\s+[đĐ]ồ|[Ss]ơ\s+[đĐ]ồ|[Pp]hụ\s+[lL]ục|[Cc]hương|"
    r"[Tt]able|[Ff]igure|[Ff]ig\.?|[Aa]ppendix|[Cc]hapter"
    r")(\s*)(\d+(?:[.,]\d+)*)"
)


def _title_ref_label(label: str) -> str:
    """Title-case a ref label, preserving internal spacing ("Biểu đồ", "Fig.")."""
    parts = re.split(r"(\s+)", label)
    out: list[str] = []
    for p in parts:
        if not p or p.isspace():
            out.append(p)
        else:
            out.append(p[0].upper() + p[1:])
    return "".join(out)


def _normalize_ref_labels(text: str) -> str:
    """Force Table/Bảng/Chapter/… labels to title case before a number."""
    if not text:
        return text

    def repl(m: re.Match) -> str:
        return _title_ref_label(m.group(1)) + m.group(2) + m.group(3)

    return _REF_LABEL_RE.sub(repl, text)


# Single-letter stats openers a results paragraph may legitimately start a
# sentence with ("p = 0.03", "n = 218", "β = 0.45"). Capitalising them would
# be a silent corruption the frozen gate cannot see (β is not a number token
# when written as a letter, and "P = 0.03" vs "p = 0.03" is the same num).
_LOWERCASE_SENTENCE_OPENERS = frozenset({
    "p", "n", "t", "r", "f", "k", "m", "b", "d",
    "α", "β", "γ", "δ", "λ", "χ", "η", "φ", "ω",
})

# Tokens whose trailing period is an ABBREVIATION dot, not a sentence end.
# Multi-letter only: the single-letter case (an author initial in "B.M. and
# Avolio", or the tail of "e.g."/"i.e.") is handled structurally in
# _restore_sentence_case, because listing every possible initial is hopeless.
# "no" is here because citation styles write issue numbers as "No. 4"; a
# genuine sentence ending in the word "no" followed by a lowercase slip is the
# rarer event and loses only a fix-up, not correctness.
_ABBREV_BEFORE_DOT = frozenset({
    "cf", "edn", "eds", "vs", "fig", "no", "et", "al", "ca", "pp", "vol",
})
# After ". " capitalize a latin-lowercase sentence start. Group 4 is the first
# letter; we inspect the full first word before deciding.
_MID_SENTENCE_LOWER_RE = re.compile(
    r"([.!?…])([\"'”’)\]]*)(\s+)([^\W\d_])",
)


def _is_latin_letter(ch: str) -> bool:
    try:
        return unicodedata.name(ch).startswith("LATIN")
    except ValueError:
        return False


def _restore_sentence_case(text: str) -> str:
    """Capitalise a latin lowercase letter that opens a sentence mid-passage.

    `_restore_leading_case` only fixes the first character of each paragraph.
    Models also emit ". table 4.2 presents" and ". results show" inside a
    paragraph; both are orthographic errors, not voice choices. Stats symbols
    and single-letter openers are left alone — see _LOWERCASE_SENTENCE_OPENERS.
    """
    if not text:
        return text

    def repl(m: re.Match) -> str:
        first = m.group(4)
        if not first.islower() or not _is_latin_letter(first):
            return m.group(0)
        # A period is only a sentence end if the token BEFORE it could end a
        # sentence. After a single letter it is an author's initial ("Bass,
        # B.M. and Avolio" — the real reference list this manufactured "And"
        # through) or the tail of "e.g."/"i.e."; after a listed abbreviation
        # ("(eds.) Handbook", "cf. the table") it is a style dot. Conservative
        # by design: a genuine sentence that ENDS in a one-letter word skips
        # one fix-up, which is cheaper than corrupting names — the same trade
        # _LOWERCASE_SENTENCE_OPENERS already makes on the other side.
        if m.group(1) == ".":
            prev = re.search(r"([^\W\d_][\w'’\-]*)$", text[:m.start(1)])
            if prev and (len(prev.group(1)) == 1
                         or prev.group(1).lower() in _ABBREV_BEFORE_DOT):
                return m.group(0)
        # Peek at the rest of the first word for the opener allowlist.
        tail_start = m.end()
        rest = text[tail_start:tail_start + 24]
        word_m = re.match(r"[\w'’\-]*", rest)
        word = first + (word_m.group(0) if word_m else "")
        low = word.lower()
        if low in _LOWERCASE_SENTENCE_OPENERS or low.startswith("p-value"):
            return m.group(0)
        if low == "et":  # "et al." after a full stop is rare but leave it
            return m.group(0)
        return m.group(1) + m.group(2) + m.group(3) + first.upper()

    return _MID_SENTENCE_LOWER_RE.sub(repl, text)


# Content-expansion gate. A re-voice may split sentences and swap synonyms; it
# must not grow an abstract into a results summary. Measured on the run that
# shipped the leadership-hotel dissertation: the abstract went from ~154 words
# to ~250 by pasting chapter-4 findings the source abstract never stated —
# every number was real elsewhere in the thesis, so a multiset frozen check on
# a batched passage can miss the invention when the batch is the abstract alone
# the numbers are simply "added" (and should fail), but pure-prose padding and
# borderline cases need a length ceiling too.
#
# Floor: short captions/labels have noisy ratios. Extra-word floor: a 12-word
# flourish on a 200-word paragraph is a voice choice, not a new section.
_LENGTH_MIN_WORDS = 40
# Both must fire: ratio alone would reject a short caption that grew by three
# words; absolute extra alone would reject a long chapter that gained one
# carefully-split sentence. Together they catch the real failure mode — an
# abstract that swallowed a results paragraph (~+100 words, ~1.6×).
_LENGTH_MAX_RATIO = 1.25
_LENGTH_MAX_EXTRA_WORDS = 25


def verify_length(original: str, rewritten: str) -> dict:
    """Reject a rewrite that is substantially longer than its source.

    Returns {"ok", "before", "after", "ratio"}. Compression is allowed — the
    frozen-token gate already catches dropped numbers/citations, and a tight
    rewrite is often what "humanize" should produce. Expansion past the
    thresholds is the invention signal.
    """
    before = len((original or "").split())
    after = len((rewritten or "").split())
    ratio = round(after / before, 3) if before else 1.0
    if before < _LENGTH_MIN_WORDS:
        return {"ok": True, "before": before, "after": after, "ratio": ratio}
    extra = after - before
    bloated = extra > _LENGTH_MAX_EXTRA_WORDS and ratio > _LENGTH_MAX_RATIO
    return {"ok": not bloated, "before": before, "after": after, "ratio": ratio}


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


def _script_counts(text: str) -> Counter:
    """Letters per Unicode script, keyed by the first word of the char's name.

    `unicodedata` exposes no script property, but the character NAME starts with
    it — "LATIN SMALL LETTER A WITH ACUTE" -> LATIN, "DEVANAGARI LETTER TA" ->
    DEVANAGARI. Vietnamese is Latin either way: precomposed chars name as LATIN,
    and decomposed tone marks are category Mn, which the letter filter skips.
    """
    c: Counter = Counter()
    for ch in text or "":
        if not unicodedata.category(ch).startswith("L"):
            continue
        try:
            c[unicodedata.name(ch).split(" ", 1)[0]] += 1
        except ValueError:  # unnamed codepoint
            continue
    return c


def verify_script(original: str, rewritten: str, min_letters: int = 2) -> list[str]:
    """Scripts the rewrite introduced that the source never used.

    A re-voicing pass has no business changing writing system, but the model
    does it anyway: a Vietnamese passage came back with "đánh giá तथा mua sắm" —
    `तथा` is Devanagari for "and", swapped in for "và". Every existing gate
    passed it, because the frozen-token check only diffs numbers, table refs and
    citations, and a cross-script synonym touches none of those.

    `min_letters` keeps single symbols out of it: Greek letters are ordinary
    notation in a stats thesis (β, α), so one stray glyph is not evidence of a
    language slip, while a 3-letter Devanagari word is.
    """
    before = set(_script_counts(original))
    after = _script_counts(rewritten)
    return sorted(s for s, n in after.items() if s not in before and n >= min_letters)


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

{naturalness_section}

WHAT THIS LOOKS LIKE — each pair says the SAME thing; only the wording moved.
Nothing was added and nothing was dropped, which is the standard your rewrite
is held to:
- Padding, not content:
  · "Có thể thấy rằng, kết quả phân tích đã chỉ ra rằng nhân tố Chất lượng dịch
    vụ đóng một vai trò vô cùng quan trọng trong việc nâng cao Sự hài lòng."
  → "Chất lượng dịch vụ có tác động tích cực tới Sự hài lòng."
- A comma-chain, split where the meaning already breaks:
  · "Nghiên cứu tiến hành khảo sát 245 nhân viên tại 12 khách sạn ở Hà Nội,
    dữ liệu được thu thập trong ba tháng, sau đó được phân tích bằng SmartPLS
    để kiểm định các giả thuyết đã đề xuất trong mô hình."
  → "Nghiên cứu khảo sát 245 nhân viên tại 12 khách sạn ở Hà Nội, dữ liệu thu
    thập trong ba tháng. Các giả thuyết được kiểm định bằng SmartPLS."
- English, same principle:
  · "It is important to note that leadership style plays a crucial role in
    determining employee satisfaction levels."
  → "Leadership style shapes how satisfied employees are."

OVERUSED WORDING — these are the words a model reaches for and a person does
not. Prefer a plainer equivalent WHEN it carries the same meaning; keep the word
whenever it is the accurate one:
- Vietnamese: "toàn diện", "đột phá", "cách mạng", "tối ưu hóa", "nâng cao hiệu
  quả", "thúc đẩy", "tận dụng", "giải pháp toàn diện", "vô cùng quan trọng".
- English: "comprehensive", "robust", "significant potential", "optimize",
  "leverage", "foster", "landscape", "transformative".
- CAUTION: "đáng kể" / "significant" often reports STATISTICAL significance. In a
  results passage that is a technical term — leave it exactly as written.

VARY HOW CLAUSES JOIN — do not run the same connective frame twice in a
paragraph. "Không chỉ … mà còn …" in particular reads as a template; use it at
most once, and prefer restating the relation plainly.

SHAPE TELLS — these give a text away even when every word is right. None of
them licenses adding or cutting content; they are about how what is already
there gets arranged:
- Do not stack "-ing" / "việc …" gerund phrases in a row ("Analysing the data,
  measuring the effect, comparing the groups…"). Turn one into a finite verb.
- Do not pad a list to three items for symmetry, and do not cut a fourth to get
  there. Report exactly the number of items the source has.
- Avoid the "from X to Y" sweep ("from recruitment to retention") unless the
  source actually names both endpoints.
- Do not use the inline-heading shape ("Tốc độ: tốc độ được cải thiện đáng kể")
  — write it as an ordinary sentence.
- English only: an em dash as parenthetical punctuation is fine once; two or
  more in a paragraph reads as machine-written. Use a comma or a full stop
  instead. (In Vietnamese it is stripped outright — it is near-absent in real
  Vietnamese academic prose.)

SENTENCE LENGTH — a hard floor, independent of the anchor:
- Vary sentence length deliberately. A paragraph where every sentence is a
  similar length reads as machine-written no matter how good the vocabulary is.
- Break comma-chains. If a sentence runs past ~40 words by stringing clauses
  together with commas, split it into two or three sentences. Vietnamese
  academic prose does this; a 79-word single sentence is not more formal, it is
  harder to read.
- Put a short declarative next to a long one at least once per paragraph.
- This applies EVEN IF the anchor itself is one long sentence after another.
  The anchor supplies word choice and clause texture; it does not license
  reproducing a run-on.

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
{restructure_section}
ABSOLUTE CONSTRAINTS — a rewrite that breaks any of these is discarded:
{protected_section}
- Invent NOTHING. No new numbers, no new citations, no new claims, and no new
  narrative actions. If the source does not state it, it does not go in.
- Do NOT lengthen the passage by importing findings, statistics, or
  recommendations from elsewhere. Rewrite ONLY what this passage already says;
  a short abstract stays a short abstract.
- Keep every factual claim and its direction (a positive effect stays positive).
- Preserve the paragraph and heading structure, and any markdown tables verbatim.
- Structural cross-references keep a capital letter: "Table 4.2", "Bảng 4.3",
  "Chapter 5", "Figure 2.1" — never "table 4.2" after a full stop.
- Citations stay in ordinary academic form: "(Bass and Avolio, 1994)" or
  "Bass and Avolio (1994)". NEVER write "bass|1994" or any "surname|year" form.

Output the rewritten text ONLY — no preamble, no commentary, no code fences."""

_REPAIR_PROMPT = """Your previous rewrite broke the frozen-token rule. Fix it with the SMALLEST
possible edit — keep the voice and rhythm you already produced.

{problem}

Output the corrected text ONLY — no preamble, no commentary, no code fences."""

# --- Restructure ladder (v4 detector loop) -------------------------------
#
# Escalating directives, injected into the rewrite prompt on rounds where a
# detector still flags the text. Round 0 injects NOTHING — the single-pass v2
# path is byte-for-byte unchanged (only reached when no scorer is configured, or
# as the first iteration when one is). Each higher rung pushes harder on the two
# statistics detectors actually measure — perplexity and BURSTINESS (sentence-
# length/structure variance) — because synonym-swaps move neither. The ABSOLUTE
# CONSTRAINTS below the injection point still bind: frozen tokens and claim
# direction are never negotiable, however aggressive the restructure.
_RESTRUCTURE_LADDER: list[str] = [
    # Round 1 — vary rhythm.
    "\nRESTRUCTURE (the previous rewrite still reads as machine-even):\n"
    "- Vary sentence length deliberately. Mix short (6–12 word) sentences with "
    "long (25+ word) ones; do not let every sentence land at a similar length.\n"
    "- Merge two adjacent short sentences, or split one long sentence, wherever "
    "meaning allows — break the uniform cadence.\n",
    # Round 2 — vary structure and openings.
    "\nRESTRUCTURE HARDER (still too even — change structure, not just length):\n"
    "- Reorder clauses: move a subordinate clause to the front or end; lead some "
    "sentences with the finding, others with the condition.\n"
    "- Ensure no two consecutive sentences open the same way (same subject, same "
    "connector). Kill any repeating template.\n"
    "- Vary how findings are introduced — not every one needs 'Kết quả cho thấy'.\n",
    # Round 3+ — re-express syntactic frames.
    "\nRE-EXPRESS AGGRESSIVELY (prior rounds were still flagged):\n"
    "- Change syntactic frames: swap active↔passive, verb↔nominalization, and "
    "recombine clauses across sentence boundaries.\n"
    "- Where meaning is preserved, reorder the presentation of findings within "
    "the paragraph. Maximize sentence-structure variance.\n"
    "- This is the strongest rewrite: change everything about HOW it is said, and "
    "NOTHING about what it says. Frozen tokens and every claim's direction stay "
    "exactly as given.\n",
]


def _restructure_directive(round_idx: int) -> str:
    """The ladder rung for this round. Round 0 -> "" (v2 prompt unchanged)."""
    if round_idx <= 0:
        return ""
    return _RESTRUCTURE_LADDER[min(round_idx - 1, len(_RESTRUCTURE_LADDER) - 1)]


def _language_name(language: str) -> str:
    return "Vietnamese" if (language or "").lower().startswith("vi") else "English"


# NATURALNESS points in OPPOSITE directions for the two languages, which is why
# it can't be one shared paragraph with {language_name} substituted in.
#
# Vietnamese: the anchors are pre-2022 Vietnamese academic prose, genuinely off
# the training distribution, and stilted Vietnamese is a defect — a stiff
# synonym or a wrong preposition costs the student marks and buys nothing. So
# "write it the way a native academic writer does" is correct there, and this
# string is byte-for-byte what the shared block used to render for "vi".
#
# English: the same instruction is what caused the measured regression. On a UK
# business dissertation scored by Turnitin before and after the pass
# (2026-08-06/07), the 40 paragraphs the pass rewrote went from 16.4% flagged to
# 36.6%, while 226 byte-identical control paragraphs moved 0.1 points. Reading
# the diffs, the pass had taken a Vietnamese author's slightly awkward English —
# "levels of length of service", "How much of the effect" — and sanded it into
# canonical native-academic phrasing. That phrasing is the model's own default
# output register, so asking for it aims the rewrite AT the thing being
# detected. English academic prose is too heavily crawled for an anchor to be
# off-distribution on its own; register distance from the model's default is the
# only lever left, and it only works if the prompt stops pulling the other way.
#
# The floor stays in both versions: never make the text ungrammatical or harder
# to read. Keeping the author's awkwardness is not licence to manufacture new
# errors in work that gets graded.
_NATURALNESS_VI = """NATURALNESS — write Vietnamese the way a native academic writer actually
writes it. Idiomatic word choice and collocations only; never stiff, translated,
or awkward phrasing. Readability must not drop below the original — if your only
way to reword a clause is a clunkier one, leave that clause as it was. In
Vietnamese specifically, keep natural prepositions/collocations (e.g. "khảo sát
được gửi đến / thu thập từ" rather than a stilted "phát … tới"); do not swap a
natural word for a rarer stiff synonym just to look different."""

_NATURALNESS_EN = """NATURALNESS — the writer is a Vietnamese researcher writing English, and the
rewrite has to still read that way. Keep the source's own phrasing habits: a
workmanlike collocation stays workmanlike, and you do not upgrade it to the
polished native-speaker equivalent. Concretely, "the mediating role of job
satisfaction between each leadership style" must NOT become "whether job
satisfaction mediates the relationship between", and "How much of the effect is
transmitted" must NOT become "To what extent is the effect transmitted" — those
canonical collocations are the default register of a language model, not of this
writer. Slightly unidiomatic but correct professional English is the TARGET, not
a defect to repair. What the source got grammatically right stays right — never
introduce an error, and if your only way to reword a clause is an ungrammatical
or harder-to-read one, leave that clause exactly as it was."""


def _naturalness_directive(language: str) -> str:
    return (_NATURALNESS_VI if (language or "").lower().startswith("vi")
            else _NATURALNESS_EN)


# Vietnamese letters that exist in no other language this product sees, plus the
# tone marks. Every Latin letter carrying a diacritic decomposes under NFD;
# plain ASCII does not, and neither do β/α or CJK — so "letters with marks over
# letters total" separates the two languages without a word list.
_VI_ONLY_LETTERS = frozenset("ăâđêôơưĂÂĐÊÔƠƯ")
# Measured on the document that exposed this bug (286 paragraphs, both
# versions): every English prose paragraph scored 0.0000, the Vietnamese ones a
# median 0.31. Anything in between separates them, so 2% sits far from both —
# high enough that an English paragraph citing Nguyễn (2019) stays English, low
# enough that no real Vietnamese prose falls under it.
_VI_MARK_RATIO = 0.02
# Below this there isn't enough text to be sure. "Bảng 4.3" is Vietnamese and
# "Table 4.3" is English, but a caption-length fragment either way is a coin
# flip, and a wrong confident answer is worse than deferring to the caller.
_LANG_MIN_LETTERS = 24


# Below this many sentences a passage has no rhythm to measure, and a guess
# would gate real rewrites on noise. Same floor the stylometric scorer uses.
_BURST_MIN_SENTENCES = 3
_SENT_SPLIT_RE = re.compile(r"[.!?…]+\s+")


def _is_burstier(original: str, rewritten: str) -> bool:
    """May this rewrite ship, judged only on rhythm?

    True when the rewrite is at least as varied as the original, and true when
    either text is too short to measure — the frozen gate stays the only judge
    there, exactly as before this check existed.

    The rule is RELATIVE, not a fixed target, because a fixed one cannot be
    honest: a student whose own paragraph already varies well would have it
    replaced by a flatter rewrite that still cleared any absolute bar. Never
    handing back something more machine-even than what we were given is the
    weakest claim worth making, and it is the one that was being broken.
    """
    before, after = burstiness(original), burstiness(rewritten)
    if before is None or after is None:
        return True
    return after >= before


def burstiness(text: str) -> float | None:
    """Coefficient of variation of sentence length. None when unmeasurable.

    This is the statistic AI detectors actually separate on, and it is worth
    stating what that claim rests on. Measured against a Turnitin report on a
    real 10,921-word dissertation, splitting its body paragraphs by what the
    detector flagged:

        flagged paragraphs   median CV = 0.247
        clean paragraphs     median CV = 0.473

    Mean sentence LENGTH barely differed (24.0 vs 24.9 words), and neither did
    lexical diversity (TTR 0.79 vs 0.81). Uniform sentences are the tell, not
    long ones — which is why "write shorter" is the wrong instruction and "vary
    deliberately" is the right one.
    """
    sents = [s for s in _SENT_SPLIT_RE.split((text or "").strip()) if s.strip()]
    if len(sents) < _BURST_MIN_SENTENCES:
        return None
    lens = [len(s.split()) for s in sents]
    mean = sum(lens) / len(lens)
    if mean <= 0:
        return None
    var = sum((n - mean) ** 2 for n in lens) / len(lens)
    return round((var ** 0.5) / mean, 4)


def detect_language(text: str) -> str | None:
    """"vi", "en", or None when the text is too short to tell.

    Exists because the language was previously an ARGUMENT with a default of
    "vi", and the rewrite prompt says "Rewrite the user's text in
    {language_name}". An English dissertation posted to /tools/document/humanize
    therefore came back translated into Vietnamese — content preserved,
    citations preserved, numbers preserved, language gone. Nothing caught it:
    verify_frozen diffs numbers and citations, verify_script only catches a
    change of writing system, and Vietnamese and English share the Latin one.

    A rewrite pass has no business choosing a language at all, so this reads it
    off the text instead of trusting the caller.

    Known limit: Vietnamese typed without diacritics reads as "en" here. In a
    thesis that is vanishingly rare (it would be barely readable), and the
    caller's own `language` still wins when this returns None.
    """
    letters = [c for c in (text or "") if c.isalpha()]
    if len(letters) < _LANG_MIN_LETTERS:
        return None
    marked = sum(1 for c in letters
                 if c in _VI_ONLY_LETTERS or unicodedata.decomposition(c))
    return "vi" if marked / len(letters) >= _VI_MARK_RATIO else "en"


def anchor_language_conflicts(anchor: str, language: str) -> bool:
    """True when `anchor` is confidently NOT in `language`.

    Measured on a live run: an English dissertation was rewritten against the
    student's stored anchor — 566 characters of casual Vietnamese about AI at
    work. A Vietnamese anchor carries no rhythm an English rewrite can borrow,
    so the pass silently degraded into the unanchored "make this sound human"
    rewrite that load_anchors() exists to refuse. Turnitin scored the paragraphs
    it touched 16.4% -> 36.6%; the untouched control moved 0.1 points.

    The test is deliberately ONE-WAY. detect_language returns "vi" on positive
    evidence (Vietnamese diacritics above a ratio) but returns "en" merely when
    that evidence is absent — unaccented Vietnamese is indistinguishable from
    English to it, as its own docstring notes. So a "vi" verdict may veto the
    user's anchor and an "en" verdict may not; otherwise every student who types
    without diacritics loses the anchor that works best for them.
    """
    if not (anchor or "").strip():
        return False
    return detect_language(anchor) == "vi" and language != "vi"


# The chat-assistant wrapper around an answer: "Here is the rewritten text:" /
# "Bản viết lại: …" in front, "Hope this helps!" behind. The rewrite prompt
# already forbids them, but a prompt is a request and this is the only thing
# between the model's reply and the student's document.
#
# Both patterns demand a lead-in AND a word naming the REWRITE, which is what
# keeps them off ordinary prose: Vietnamese paragraphs open with "Đây là …:"
# all the time, and an English sentence may well end a clause with a colon.
# "Đây là kết quả của mô hình:" has the lead-in and no rewrite word, so it
# survives; "Đây là bản viết lại:" has both, so it goes.
_PREAMBLE_RE = re.compile(
    r"^\s*(?:sure|certainly|of course|okay|ok|chắc chắn|được thôi)?[,.!]?\s*"
    r"(?:here (?:is|are)|below is|the following is|i(?:'ve| have)|"
    r"dưới đây là|sau đây là|đây là|bản|đoạn)\b"
    r"[^\n:]{0,60}?\b(?:rewrit\w*|revis\w*|version|humaniz\w*|"
    r"viết lại|chỉnh sửa|diễn đạt lại)\b[^\n:]{0,40}:\s*",
    re.IGNORECASE,
)
_SIGNOFF_RE = re.compile(
    r"\n\s*(?:hope (?:this|that) helps|let me know if|feel free to|"
    r"hy vọng[^\n]{0,40}?(?:giúp ích|hữu ích)|nếu (?:bạn )?cần[^\n]{0,30}?"
    r"(?:cho tôi biết|hãy nói))[^\n]{0,120}\s*$",
    re.IGNORECASE,
)


def _clean_output(raw: str) -> str:
    """Strip code fences and the chat-assistant wrapper around the rewrite."""
    t = (raw or "").strip()
    t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    t = t.strip()
    # Never strip the passage down to nothing: a reply that is ONLY a preamble
    # means the rewrite failed, and returning "" turns that into a deleted
    # paragraph. Hand the raw text back and let the gates reject it instead.
    stripped = _SIGNOFF_RE.sub("", _PREAMBLE_RE.sub("", t, count=1)).strip()
    return stripped or t


def _get_llm(temperature: float):
    from orchestrator.llm import get_orchestrator_llm  # noqa: PLC0415 — import-light

    # Humanize may run on a different provider than the report writer: Gemini
    # reads far more idiomatic Vietnamese for prose polish (measured — it avoids
    # qwen's stilted "phát…tới" and splits dense sentences), while qwen stays the
    # benchmarked, cheapest, tool-reliable engine for report GENERATION. Set
    # HUMANIZE_LLM_ROUTE/HUMANIZE_LLM_MODEL to override; unset = engine default.
    return get_orchestrator_llm(
        temperature=temperature,
        route=os.getenv("HUMANIZE_LLM_ROUTE") or None,
        model=os.getenv("HUMANIZE_LLM_MODEL") or None,
    )


# Per-call token accounting. A ContextVar rather than a module global because
# the API serves humanize concurrently: two students' passages must not add
# their tokens to each other's bill. `None` (the default) means nobody is
# collecting, which is the case for every existing caller — the export path,
# evals, tests — so metering is opt-in and changes nothing for them.
_USAGE: ContextVar[list | None] = ContextVar("humanize_usage", default=None)


def _invoke(llm, prompt: str) -> str:
    """The single LLM chokepoint for the whole pass — all three call sites (the
    anchor router, the rewrite, the frozen-repair) go through here, which is why
    metering only has to be attached in one place."""
    from orchestrator.message_utils import text_of  # noqa: PLC0415

    resp = llm.invoke(prompt)
    bucket = _USAGE.get()
    if bucket is not None:
        try:
            from orchestrator.token_meter import _usage_from_response  # noqa: PLC0415
            p_tok, c_tok = _usage_from_response(resp)
            bucket.append({"model": str(getattr(llm, "model", "unknown")),
                           "prompt_tokens": p_tok, "completion_tokens": c_tok})
        except Exception:  # noqa: BLE001
            # Accounting must never cost a student their rewrite. A provider
            # that doesn't surface usage_metadata is under-billed, not failed.
            logger.exception("humanize: token accounting failed")
    return text_of(resp)


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


def _restore_leading_case(sent: str, rewritten: str) -> str:
    """Re-capitalise a paragraph the rewrite started with a lowercase letter.

    Observed in a shipped document: a chapter opener came back as "chương 4
    trình bày kết quả…". Nothing deterministic did that — strip_ai_tells and
    _clean_output both preserve (and _strip_start_connectors actively restores)
    sentence case. The model produced it, treating the paragraph as a
    continuation of the passage it was handed.

    Repaired rather than rejected: throwing away an otherwise good rewrite over
    one character would be a worse trade than fixing the character, and unlike a
    changed number this cannot alter meaning.

    Conservative on purpose — it only acts when the SOURCE paragraph started
    with an uppercase letter and the rewrite starts with a lowercase one. A
    paragraph that legitimately opens on a symbol or a lowercase variable name
    ("p-value…", "β đạt 0.42") is left alone, because the evidence comes from
    the original rather than from a guess about Vietnamese orthography.
    """
    def _is_latin_lower(ch: str) -> bool:
        """A lowercase letter in the LATIN script specifically.

        `"β".islower()` is True and `"β".upper()` is "Β", so a naive islower()
        check turns "β = 0,412 và p = 0,003" into "Β = 0,412…" — silently
        corrupting a coefficient symbol, which the frozen-token gate does not
        cover because β is neither a number nor a citation. Vietnamese (and
        English) are Latin, so requiring the script is both correct here and
        the reason this can't touch a Greek or CJK opener.
        """
        if not ch.islower():
            return False
        try:
            return unicodedata.name(ch).startswith("LATIN")
        except ValueError:  # unnamed codepoint
            return False

    def fix(src: str, out: str) -> str:
        src_s, out_s = src.lstrip(), out.lstrip()
        if not src_s or not out_s:
            return out
        if src_s[0].isupper() and _is_latin_lower(out_s[0]):
            lead = out[: len(out) - len(out_s)]  # keep any original indentation
            return lead + out_s[0].upper() + out_s[1:]
        return out

    # Batched callers (humanize_docx) send several paragraphs joined by blank
    # lines, so fix each one against its own source rather than only the first —
    # otherwise paragraphs 2..n keep the slip.
    src_parts, out_parts = sent.split("\n\n"), rewritten.split("\n\n")
    if len(src_parts) == len(out_parts) and len(src_parts) > 1:
        return "\n\n".join(fix(s, o) for s, o in zip(src_parts, out_parts))
    return fix(sent, rewritten)


def _verify(original: str, rewritten: str) -> dict:
    """Every gate a rewrite must clear, in one dict.

    Kept additive over verify_frozen's {"ok", "missing", "added"} shape — the
    result travels out as `frozen` in the tool payload and the API reads
    `frozen.ok` — so a script slip rejects the rewrite through the exact path a
    lost citation already does: one repair attempt, then keep the original.
    """
    check = verify_frozen(original, rewritten)
    check["foreign_scripts"] = verify_script(original, rewritten)
    if check["foreign_scripts"]:
        check["ok"] = False
    # Translation is the failure verify_script cannot see: vi→en keeps the Latin
    # script, keeps every number and every citation, and changes the one thing a
    # re-voicing pass must never change. Detection is deliberately allowed to be
    # unsure (None) — a fragment says nothing, and only a CONFIRMED disagreement
    # rejects the rewrite.
    src_lang, out_lang = detect_language(original), detect_language(rewritten)
    check["language_changed"] = bool(src_lang and out_lang and src_lang != out_lang)
    if check["language_changed"]:
        check["ok"] = False
    # Our own multiset key, echoed back into the prose. describe_token() stops
    # the prompt from ever showing it, _scrub_token_syntax strips the common
    # form, and this rejects whatever still remains — the frozen check alone is
    # blind: "(Bass and Avolio, bass|1994)" re-extracts as the token it corrupts.
    # findall returns (surname, year) tuples with the grouped regex; rebuild the
    # surface form for the report and the "was it in the original?" test.
    leaked = []
    for m in _TOKEN_SYNTAX_RE.finditer(rewritten or ""):
        surface = m.group(0)
        if surface not in (original or ""):
            leaked.append(surface)
    check["token_syntax"] = sorted(set(leaked))
    if leaked:
        check["ok"] = False
    length = verify_length(original, rewritten)
    check["length"] = length
    if not length["ok"]:
        check["ok"] = False
    return check


def _polish_rewrite(input_text: str, original_text: str, rewritten: str,
                    language: str) -> str:
    """Deterministic post-pass before the gates: strip tells, fix case/refs/keys.

    Order is load-bearing. AI-tell stripping can leave a lowercase sentence
    start (it recapitalises its own deletions, but not the model's). Leading-
    case runs next so a paragraph opener is fixed before mid-sentence case
    looks at the same string. Ref labels are title-cased after sentence case so
    "table" becoming "Table" is not then re-lowered. Token-syntax scrub is last
    among the orthographic fixes so a repaired "(…, 1994)" is what the gates
    see — not the leaked key.
    """
    out = strip_ai_tells(rewritten, language)
    out = _restore_leading_case(input_text, out)
    out = _restore_sentence_case(out)
    out = _normalize_ref_labels(out)
    out = _scrub_token_syntax(out, original_text)
    return out


def _rewrite_once(
    llm,
    *,
    input_text: str,
    original_text: str,
    language: str,
    anchor: dict,
    protected_section: str,
    round_idx: int = 0,
) -> dict:
    """One anchored rewrite of `input_text`, plus up to one frozen-token repair.

    Frozen tokens are always diffed against `original_text`, never against
    `input_text` — in the detector loop a later round rewrites the PREVIOUS
    round's output, but the numbers/citations it must preserve are still the
    ones from the true source. `round_idx` selects the restructure-ladder rung;
    round 0 injects nothing, so the single-pass call is byte-for-byte the v2
    prompt.

    Returns {"ok", "text", "check", "repairs", "error"}. `error` is set only for
    a provider failure ("llm_failed") or an empty generation ("empty_rewrite");
    a frozen violation is a normal `ok: False` with the diff in `check`.
    """
    system = _REWRITE_PROMPT.format(
        anchor=anchor["text"],
        language_name=_language_name(language),
        naturalness_section=_naturalness_directive(language),
        protected_section=protected_section,
        restructure_section=_restructure_directive(round_idx),
    )
    try:
        out = _clean_output(
            _invoke(llm, f"{system}\n\nTEXT TO REWRITE:\n{input_text}"))
    except Exception as e:
        logger.exception("humanize: rewrite call failed")
        return {"ok": False, "error": "llm_failed", "detail": str(e),
                "text": None, "check": None, "repairs": 0}
    if not out:
        return {"ok": False, "error": "empty_rewrite",
                "text": None, "check": None, "repairs": 0}

    # Aligned against input_text, not original_text: in the v4 loop input_text
    # is the previous round's output, and it is what the model was actually
    # handed — so its paragraph boundaries are the ones that line up.
    out = _polish_rewrite(input_text, original_text, out, language)
    check = _verify(original_text, out)
    repairs = 0

    if not check["ok"]:
        # One repair attempt, with the exact diff. A second failure means the
        # model can't hold the numbers for this passage; the caller keeps the
        # original (single-pass) or escalates to the next round (loop).
        problem_lines = []
        if check["missing"]:
            problem_lines.append(
                "These are in the ORIGINAL but missing from your rewrite. "
                "Put each one back, in the form it appears in the original "
                "text — NOT as written here:\n"
                + "\n".join(f"  {describe_token(m)}" for m in check["missing"]))
        if check["added"]:
            problem_lines.append(
                "These appear in your rewrite but NOT in the original — you "
                "invented them. Remove them:\n"
                + "\n".join(f"  {describe_token(a)}" for a in check["added"]))
        if check["foreign_scripts"]:
            problem_lines.append(
                "You wrote words in a different writing system than the "
                "original ("
                + ", ".join(check["foreign_scripts"]).lower()
                + "). Rewrite those words in the SAME language and script as "
                  "the original text.")
        if check.get("language_changed"):
            problem_lines.append(
                f"You TRANSLATED the text. Write the rewrite in "
                f"{_language_name(language)}, the same language as the original. "
                "This pass changes wording only — never the language.")
        # Decision: name the failure mode, never echo the pipe form back as a
        # token to "restore" — that is how the original bass|1994 corruption
        # was produced. Tell the model the correct surface form only.
        if check.get("token_syntax"):
            problem_lines.append(
                "You wrote an internal token form into the prose (a "
                "surname-pipe-year string such as a concatenated key). Never "
                "do that. Use ordinary academic citations only, e.g. "
                "(Bass and Avolio, 1994) or Bass and Avolio (1994). Remove "
                "every pipe character between a name and a year."
            )
        length = check.get("length") or {}
        if length and not length.get("ok", True):
            problem_lines.append(
                f"Your rewrite is substantially longer than the original "
                f"({length.get('after')} words vs {length.get('before')}). "
                "You added content this passage does not contain. Delete every "
                "claim, statistic, or sentence that is not already in the "
                "ORIGINAL — match the original's scope and length."
            )
        # Empty problem_lines can still happen if a future gate sets ok=False
        # without a message; skip the LLM call rather than send a blank repair.
        if problem_lines:
            try:
                repaired = _clean_output(_invoke(
                    llm,
                    _REPAIR_PROMPT.format(problem="\n\n".join(problem_lines))
                    + f"\n\nORIGINAL:\n{original_text}\n\nYOUR REWRITE:\n{out}"))
                repairs = 1
                if repaired:
                    repaired = _polish_rewrite(
                        input_text, original_text, repaired, language)
                    recheck = _verify(original_text, repaired)
                    if recheck["ok"]:
                        out, check = repaired, recheck
                    else:
                        check = recheck
            except Exception:
                logger.exception("humanize: repair call failed")

    return {"ok": check["ok"], "text": out, "check": check, "repairs": repairs}


def humanize_prose(
    text: str,
    *,
    language: str | None = None,
    user_anchor: str | None = None,
    anchor_id: str | None = None,
    llm=None,
    scorer=None,
) -> dict:
    """Run the anchored rewrite over one passage, reporting what it cost.

    Thin wrapper over `_humanize_prose` that collects per-call token usage and
    attaches it to whatever the pass returns, on EVERY path including failures:
    a rewrite that burned three rounds and then failed the frozen gate cost real
    money, and a caller that only bills successes would silently eat it.

    `usage` is a list of {model, prompt_tokens, completion_tokens}, one entry per
    LLM call — a list, not a total, because a pass can legitimately span models
    (the anchor router and the rewrite are separately configurable) and they are
    priced at different rates. api/app/routers/humanize.py bills each at its own
    rate, exactly as job_runner._charge_auto_run does for token_ledger rows.
    """
    bucket: list = []
    token = _USAGE.set(bucket)
    try:
        out = _humanize_prose(
            text, language=language, user_anchor=user_anchor,
            anchor_id=anchor_id, llm=llm, scorer=scorer)
    finally:
        _USAGE.reset(token)
    if isinstance(out, dict):
        out["usage"] = bucket
    return out


def _humanize_prose(
    text: str,
    *,
    language: str | None = None,
    user_anchor: str | None = None,
    anchor_id: str | None = None,
    llm=None,
    scorer=None,
) -> dict:
    """Run the anchored rewrite over one passage.

    `user_anchor` is ~150 words of the student's own writing. It takes priority
    over the installed library: a per-person anchor was the single strongest
    result in the bake-off, because idiosyncratic real writing is by definition
    outside the training distribution.

    `scorer` is the v4 detector-in-the-loop. When None (the default) it is
    resolved from HUMANIZE_SCORER; if that is unset/`none`, the pass runs
    EXACTLY as v2 — one anchored rewrite + optional frozen-repair, no scoring.
    When a Scorer is active, the rewrite is iterated adversarial-paraphrasing
    style: each round escalates the restructure directive, re-scores, keeps the
    lowest-scoring candidate that still passes the frozen gate, and stops early
    once the score drops to HUMANIZE_AI_THRESHOLD. A None score (backend down /
    unconfigured) degrades to single-pass — it never blocks the passage.

    Returns:
        {"ok", "text", "anchor", "changed", "frozen", "repairs", "error"}
        plus, when scored: {"score", "rounds", "threshold"}.

    On rejection `ok` is False and `text` is the ORIGINAL, unmodified. The
    caller ships the original — never a rewrite that failed verification.
    """
    if not (text or "").strip():
        return {"ok": False, "error": "empty_input", "text": text, "changed": False}

    # The text overrules the caller. `language` used to flow straight into
    # "Rewrite the user's text in {language_name}" from an API default of "vi",
    # so an English document was translated on request. It survives only as the
    # fallback for text too short to read, and it still picks the anchor
    # library and the AI-tell list below.
    language = detect_language(text) or language or "vi"

    anchors = load_anchors(language)
    if user_anchor and user_anchor.strip():
        # A stored anchor outlives the document it was saved for. The student
        # who saved Vietnamese prose months ago then submits an English chapter,
        # and the anchor is still attached. Falling through to the library beats
        # rewriting against a rhythm from the wrong language.
        if anchor_language_conflicts(user_anchor, language):
            logger.warning(
                "humanize: ignoring user_anchor — it reads as Vietnamese but "
                "the document is %s; falling back to the anchor library", language)
        else:
            anchors = [{"id": "user_supplied",
                        "desc": "The student's own writing.",
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
    # Decision: every protected token is rendered via describe_token so the
    # model never sees our multiset key syntax (bass|1994) or a lowercased ref
    # label that it then pastes as "table 4.2". Numbers stay as written; cites
    # become "the citation Bass (1994)"; refs become "Bảng 4.3" / "Table 4.2".
    frozen_lines = [
        f"  {describe_token(t)}" for t in sorted(frozen)
        if t.startswith(("num:", "ref:", "cite:"))
    ]
    # Only present the "must appear verbatim" list when there ARE protected
    # tokens. Feeding a literal "(none)" under that instruction made the model
    # dutifully echo "(none)" into the prose — protect against that leak.
    if frozen_lines:
        protected_section = (
            "- Every one of these must appear in your output. Keep numbers "
            "character-for-character (do not round). Keep citations in ordinary "
            "academic form — never as surname|year. Keep table/figure/chapter "
            "labels capitalised:\n" + "\n".join(frozen_lines)
        )
    else:
        protected_section = (
            "- This passage contains no numbers or citations — there are no "
            "protected tokens, and you must not introduce any."
        )

    llm = llm or _get_llm(0.95)
    cleaned = strip_ai_tells(text, language)
    anchor = pick_anchor(cleaned, anchors, llm=llm)

    _FROZEN_HINT = ("The rewrite altered numbers or citations, so the original "
                    "was kept. Report this — do not claim the passage was "
                    "humanized.")
    _FLAT_HINT = ("The rewrite read MORE machine-even than the original — its "
                  "sentences were more uniform in length, which is the "
                  "statistic detectors separate on. The original was kept. "
                  "Report this; do not claim the passage was humanized.")

    def _flatter(original: str, anchor_id: str, r: dict) -> dict:
        return {"ok": False, "error": "flatter_than_original", "text": original,
                "changed": False, "anchor": anchor_id, "frozen": r.get("check"),
                "repairs": r.get("repairs", 0), "hint": _FLAT_HINT,
                "burstiness": {"before": burstiness(original),
                               "after": burstiness(r.get("text") or "")}}

    # Resolve the detector. None (env unset/`none`) is the switch back to the
    # untouched v2 single-pass path — so an un-configured deployment, and every
    # existing test that passes no scorer, behaves exactly as before.
    if scorer is None:
        from orchestrator.tools.detector import get_scorer  # noqa: PLC0415
        scorer = get_scorer()

    rw = dict(original_text=text, language=language, anchor=anchor,
              protected_section=protected_section)

    # --- v2 single-pass: no detector, one rewrite (+optional repair) ---------
    if scorer is None:
        r = _rewrite_once(llm, input_text=cleaned, round_idx=0, **rw)
        if r.get("error") == "llm_failed":
            return {"ok": False, "error": "llm_failed", "detail": r.get("detail"),
                    "text": text, "changed": False}
        if r.get("error") == "empty_rewrite":
            return {"ok": False, "error": "empty_rewrite", "text": text,
                    "changed": False}
        if not r["ok"]:
            return {"ok": False, "error": "frozen_violation", "text": text,
                    "changed": False, "anchor": anchor["id"], "frozen": r["check"],
                    "repairs": r["repairs"], "hint": _FROZEN_HINT}
        if not _is_burstier(text, r["text"]):
            return _flatter(text, anchor["id"], r)
        return {"ok": True, "text": r["text"], "anchor": anchor["id"],
                "changed": r["text"].strip() != text.strip(),
                "frozen": r["check"], "repairs": r["repairs"],
                "burstiness": {"before": burstiness(text),
                               "after": burstiness(r["text"])}}

    # --- v4 detector loop: rewrite -> score -> escalate, keep the best -------
    from orchestrator.tools.detector import ai_threshold, max_rounds  # noqa: PLC0415
    threshold, rounds = ai_threshold(), max_rounds()
    best: dict | None = None       # lowest-scoring candidate that passed frozen
    last_flat: dict | None = None  # a verified round rejected only for rhythm
    input_text = cleaned
    for i in range(rounds):
        r = _rewrite_once(llm, input_text=input_text, round_idx=i, **rw)
        if r.get("error") == "llm_failed":
            break                  # provider down — stop and fall back below
        if not r.get("text") or not r["ok"]:
            continue               # empty or frozen-violating round: escalate
        if not _is_burstier(text, r["text"]):
            # Flatter than what the student wrote. Not a candidate at any
            # score — escalating the restructure ladder is exactly the right
            # response, and shipping it would be the regression this guard
            # exists for.
            last_flat = r
            continue
        sc = scorer.score(r["text"])
        if sc is None:
            # Backend unavailable — behave like single-pass: take the first
            # verified rewrite rather than burning rounds against no signal.
            best = {"text": r["text"], "check": r["check"],
                    "repairs": r["repairs"], "score": None, "round": i}
            break
        if best is None or sc < best["score"]:
            best = {"text": r["text"], "check": r["check"],
                    "repairs": r["repairs"], "score": sc, "round": i}
        if sc <= threshold:
            break
        # Iterate on the champion so far, escalating the restructure directive.
        input_text = best["text"]

    if best is None:
        # Nothing survived. Two different failures, and the student is owed the
        # difference: a rewrite that moved a number is a correctness problem,
        # one that only ever came back flatter is a quality ceiling on this
        # passage. Either way the original ships.
        if last_flat is not None:
            return _flatter(text, anchor["id"], last_flat)
        return {"ok": False, "error": "frozen_violation", "text": text,
                "changed": False, "anchor": anchor["id"], "hint": _FROZEN_HINT}

    # Log the score even though it also rides out in the return value. The
    # measure-only config (HUMANIZE_MAX_ROUNDS=1) exists to learn the real
    # distribution on Vietnamese academic prose before paying for iteration, and
    # the callers that could aggregate it don't: the API hands `score` to one
    # client and forgets it, the agent tool serialises it into a tool result,
    # and the export path files it in a per-section report nobody totals. One
    # greppable line per rewrite is what turns "we return a number" into data
    # you can actually pull a distribution from.
    #
    # logger, not analytics.emit: this module is engine-layer and importing the
    # app's analytics here would invert the dependency. Wire the PostHog event
    # in api/app/routers/humanize.py if per-user aggregation is wanted.
    logger.info(
        "humanize scored: score=%.4f threshold=%.2f rounds=%d chars=%d lang=%s anchor=%s",
        best["score"] if best["score"] is not None else -1.0,
        threshold, best["round"] + 1, len(text or ""), language, anchor["id"],
    )
    return {"ok": True, "text": best["text"], "anchor": anchor["id"],
            "changed": best["text"].strip() != text.strip(),
            "frozen": best["check"], "repairs": best["repairs"],
            "score": best["score"], "rounds": best["round"] + 1,
            "threshold": threshold,
            "burstiness": {"before": burstiness(text),
                           "after": burstiness(best["text"])}}


def humanize_sections(
    sections: list[dict],
    *,
    language: str | None = None,
    user_anchor: str | None = None,
    llm=None,
    scorer=None,
) -> tuple[list[dict], list[dict]]:
    """Humanize a composed chapter list in place-ish, section by section.

    Returns `(sections, report)`. Sections that fail verification keep their
    original prose — the export must never be blocked by this pass, and must
    never silently ship an unverified rewrite either. "References" is skipped:
    a bibliography has no voice to humanize and everything in it is frozen.

    `scorer` threads the v4 detector through to every section; when None it is
    resolved once per section from HUMANIZE_SCORER (default: off = v2 behavior).
    """
    out: list[dict] = []
    report: list[dict] = []
    for s in sections or []:
        title = s.get("title") or ""
        prose = s.get("prose") or ""
        if title == "References" or not prose.strip():
            out.append(s)
            continue
        r = humanize_prose(prose, language=language, user_anchor=user_anchor,
                           llm=llm, scorer=scorer)
        report.append({"title": title, "ok": r.get("ok", False),
                       "anchor": r.get("anchor"), "error": r.get("error"),
                       "frozen": r.get("frozen"), "score": r.get("score"),
                       "rounds": r.get("rounds")})
        out.append({**s, "prose": r["text"]} if r.get("ok") else s)
    return out, report

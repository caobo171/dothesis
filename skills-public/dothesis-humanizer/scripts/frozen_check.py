#!/usr/bin/env python3
"""Did the rewrite change the wording, and only the wording — and did it help?

Standard library only, no install, no network.

    python3 frozen_check.py original.txt rewritten.txt   # judge a rewrite
    python3 frozen_check.py --scan draft.txt             # find what to rewrite

TWO questions, because passing the first and failing the second is the trap.

1. Did anything that must not move, move? Four ways a rewrite goes wrong, all
   invisible to a reader who trusts prose that reads well:

       missing        a number, table reference or citation vanished
       added          one was invented that the source never had
       language       the text was TRANSLATED instead of re-voiced
       foreign_script a word came back in a different writing system

2. Did the rhythm actually improve? A rewrite can preserve every number and
   still come back MORE machine-even than what the human wrote. Measured against
   a Turnitin report on a real 10,921-word dissertation, splitting its
   paragraphs by what the detector flagged:

       flagged paragraphs   median sentence-length CV = 0.247
       clean paragraphs     median sentence-length CV = 0.473

   Mean sentence LENGTH barely differed between the two groups (24.0 vs 24.9
   words) and lexical diversity did not differ at all (TTR 0.79 vs 0.81).
   Uniform sentences are the tell, not long ones — which is why "write shorter"
   is the wrong instruction. On that same document the tool being tested made 4
   of 9 rewritten paragraphs flatter than the student's own writing, one going
   0.583 -> 0.204, because nothing was comparing them.

Exit 0 = safe to keep. Exit 1 = keep the original instead.

Ported from the gate DoThesis runs in production, where it exists because a
humanized results chapter that quietly turns p = 0.032 into p = 0.03 is worse
than an un-humanized one: nobody re-checks prose that reads well.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter

# --- what a rewrite may never touch --------------------------------------

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
_NAME_JOINERS = {"và", "and", "et", "al", "cộng", "sự"}


def _capitalized_words(s: str) -> list[str]:
    return [w for w in _WORD_RE.findall(s) if w[:1].isupper()]


def _lead_surname(lead: str) -> str | None:
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


def cite_tokens(text: str) -> list[str]:
    """Citations as `surname|year`, normalised across both citation forms.

    "(Nguyễn, 2020)" and "Nguyễn (2020)" produce the SAME token on purpose: a
    rewrite may move a citation between parenthetical and narrative form, which
    is an ordinary writing choice. It may not drop or invent one.
    """
    out: list[str] = []
    for chunk in _PAREN_RE.findall(text):
        if not _YEAR_RE.search(chunk):
            continue
        for part in chunk.split(";"):
            years = _YEAR_RE.findall(part)
            names = _capitalized_words(part)
            if not names:
                continue
            for y in years:
                out.append(f"{names[0].lower()}|{y}")
    for m in _BARE_YEAR_PAREN_RE.finditer(text):
        lead = text[max(0, m.start() - 60):m.start()]
        # Never walk back across an earlier citation: in "Nguyễn (2019) và Trần
        # (2021)" the joiner would otherwise read 2021 as Nguyễn's.
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
        c[f"ref:{_WS_RE.sub(' ', r).strip().lower()}"] += 1
    for t in cite_tokens(text or ""):
        c[f"cite:{t}"] += 1
    return c


# --- language + script ----------------------------------------------------

_VI_ONLY_LETTERS = frozenset("ăâđêôơưĂÂĐÊÔƠƯ")
_VI_MARK_RATIO = 0.02
_LANG_MIN_LETTERS = 24


def detect_language(text: str) -> str | None:
    """"vi", "en", or None when there is not enough text to tell.

    Measured on a real dissertation: English prose paragraphs score 0.0000
    diacritic density, Vietnamese ones a median of 0.31. 2% sits far from both,
    so an English paragraph citing Nguyễn (2019) stays English.
    """
    letters = [c for c in (text or "") if c.isalpha()]
    if len(letters) < _LANG_MIN_LETTERS:
        return None
    marked = sum(1 for c in letters
                 if c in _VI_ONLY_LETTERS or unicodedata.decomposition(c))
    return "vi" if marked / len(letters) >= _VI_MARK_RATIO else "en"


def _script_of(ch: str) -> str | None:
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return None
    return name.split(" ")[0] if name else None


def foreign_scripts(original: str, rewritten: str, min_letters: int = 2) -> list[str]:
    """Writing systems the rewrite introduced that the source never used.

    A re-voicing pass has no business changing writing system, but models do it:
    a Vietnamese passage came back with "đánh giá तथा mua sắm" — Devanagari for
    "and", swapped in for "và". Single symbols are ignored, because Greek
    letters are ordinary notation in a statistics chapter (β, α).
    """
    def counts(s: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for ch in s or "":
            if ch.isalpha():
                sc = _script_of(ch)
                if sc:
                    out[sc] = out.get(sc, 0) + 1
        return out

    before = set(counts(original))
    return sorted(s for s, n in counts(rewritten).items()
                  if s not in before and n >= min_letters)


# --- rhythm ---------------------------------------------------------------

_SENT_SPLIT_RE = re.compile(r"[.!?…]+\s+")
_BURST_MIN_SENTENCES = 3
# The clean-paragraph median from the measurement above: prose that varies this
# much is prose the detector left alone in that document.
#
# It is a SCREEN, not a goal. A later run rewrote that same dissertation toward
# this number and the flagged share of the rewritten text went 16.4% -> 36.6%;
# Turnitin's own docs say the model is "not explicitly programmed to evaluate
# specific signals such as 'burstiness,' 'perplexity'". Flat prose and flagged
# prose correlate, which makes this good at FINDING limp paragraphs and bad as a
# target to optimise. The gate below stays relative to the original for exactly
# this reason.
CV_TARGET = 0.47


def burstiness(text: str) -> float | None:
    """Coefficient of variation of sentence length. None if unmeasurable.

    Below three sentences there is no rhythm to measure and a guess would gate
    real rewrites on noise.
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


# --- the gate -------------------------------------------------------------

def check(original: str, rewritten: str) -> dict:
    before, after = frozen_tokens(original), frozen_tokens(rewritten)
    missing = sorted((before - after).elements())
    added = sorted((after - before).elements())
    scripts = foreign_scripts(original, rewritten)
    src_lang, out_lang = detect_language(original), detect_language(rewritten)
    translated = bool(src_lang and out_lang and src_lang != out_lang)

    # Relative, not an absolute target: a writer whose paragraph already varies
    # well would otherwise have it replaced by a flatter rewrite that still
    # cleared a fixed bar. Never handing back something more machine-even than
    # what you were given is the weakest claim worth making.
    cv_before, cv_after = burstiness(original), burstiness(rewritten)
    flatter = bool(cv_before is not None and cv_after is not None
                   and cv_after < cv_before)
    return {
        "ok": not (missing or added or scripts or translated or flatter),
        "missing": missing,
        "added": added,
        "foreign_scripts": scripts,
        "language_changed": translated,
        "language": {"original": src_lang, "rewritten": out_lang},
        "flatter_than_original": flatter,
        "rhythm": {"before": cv_before, "after": cv_after, "target": CV_TARGET},
    }


def _cv(v) -> str:
    return "—" if v is None else f"{v:.3f}"


def _human(result: dict) -> str:
    r = result["rhythm"]
    rhythm = f"rhythm {_cv(r['before'])} -> {_cv(r['after'])} (target {r['target']})"
    if result["ok"]:
        return ("PASS — every number, reference and citation survived, and the "
                f"rewrite is no flatter than the original.\n  {rhythm}")

    lines = ["FAIL — keep the original. This rewrite:"]
    if result["missing"]:
        lines.append("  lost from the original (put each back, unchanged):")
        lines += [f"    {m.split(':', 1)[1]}" for m in result["missing"]]
    if result["added"]:
        lines.append("  invented, not in the original (remove each):")
        lines += [f"    {a.split(':', 1)[1]}" for a in result["added"]]
    if result["language_changed"]:
        lines.append("  was TRANSLATED, not re-voiced. Rewrite it in "
                     f"{result['language']['original']}.")
    if result["foreign_scripts"]:
        lines.append("  used another writing system: "
                     + ", ".join(result["foreign_scripts"]).lower())
    if result["flatter_than_original"]:
        lines.append(f"  reads MORE machine-even than the original — {rhythm}.")
        lines.append("    Its sentences are closer to uniform length than the "
                     "text you were given, which is the statistic detectors")
        lines.append("    separate on. Escalate: see RESTRUCTURE in SKILL.md.")
    return "\n".join(lines)


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]


def scan(text: str) -> dict:
    """Which paragraphs read as machine-even, before anything is rewritten.

    Rewriting a whole chapter costs money and risks every paragraph it touches.
    Most drafts do not need it everywhere: on the measured dissertation, 47% of
    body paragraphs sat below CV 0.35 and the rest were already fine. This says
    where to spend the effort.
    """
    rows = []
    for i, para in enumerate(_paragraphs(text)):
        cv = burstiness(para)
        if cv is None:
            continue
        rows.append({"index": i + 1, "cv": cv,
                     "flat": cv < CV_TARGET,
                     "preview": re.sub(r"\s+", " ", para)[:70]})
    flat = [r for r in rows if r["flat"]]
    return {"measured": len(rows), "flat": len(flat), "target": CV_TARGET,
            "paragraphs": rows}


def _human_scan(result: dict) -> str:
    if not result["measured"]:
        return "Nothing long enough to measure — a paragraph needs 3+ sentences."
    lines = [f"{result['flat']} of {result['measured']} measurable paragraphs "
             f"read as machine-even (CV below {result['target']}).",
             "These read flattest — start here. But rewrite the SECTION they sit "
             "in, not the single paragraphs:",
             "a detector scores overlapping stretches of ~5-10 sentences, so the "
             "seam between a rewritten",
             "paragraph and an untouched neighbour is where a part-finished "
             "document goes wrong.",
             ""]
    for r in result["paragraphs"]:
        if r["flat"]:
            lines.append(f"  #{r['index']:<4} cv {r['cv']:.3f}  {r['preview']}…")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    flags = {a for a in argv[1:] if a.startswith("--")}
    as_json = "--json" in flags

    if "--scan" in flags:
        if not args:
            print(__doc__)
            return 2
        with open(args[0], encoding="utf-8") as f:
            result = scan(f.read())
        print(json.dumps(result, ensure_ascii=False, indent=2) if as_json
              else _human_scan(result))
        return 0

    if len(args) < 2:
        print(__doc__)
        return 2
    with open(args[0], encoding="utf-8") as f:
        original = f.read()
    with open(args[1], encoding="utf-8") as f:
        rewritten = f.read()
    result = check(original, rewritten)
    print(json.dumps(result, ensure_ascii=False, indent=2) if as_json
          else _human(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

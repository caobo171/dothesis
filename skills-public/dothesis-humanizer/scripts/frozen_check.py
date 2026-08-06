#!/usr/bin/env python3
"""Check that a rewrite changed the wording and nothing else.

Standard library only, no install, no network. Run it after every rewrite:

    python3 frozen_check.py original.txt rewritten.txt

It answers one question — did anything that must not move, move? Four ways a
rewrite can be wrong, all of them invisible to a reader who trusts prose that
reads well:

    missing        a number, table reference or citation vanished
    added          one was invented that the source never had
    language       the text was TRANSLATED instead of re-voiced
    foreign_script a word came back in a different writing system

Exit code is 0 when the rewrite is safe to keep, 1 when it must be discarded
and the original kept.

This is a port of the gate DoThesis runs in production, where it exists because
a humanized results chapter that quietly turns p = 0.032 into p = 0.03 is worse
than an un-humanized one — nobody re-checks prose that reads well.
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


# --- the gate -------------------------------------------------------------

def check(original: str, rewritten: str) -> dict:
    before, after = frozen_tokens(original), frozen_tokens(rewritten)
    missing = sorted((before - after).elements())
    added = sorted((after - before).elements())
    scripts = foreign_scripts(original, rewritten)
    src_lang, out_lang = detect_language(original), detect_language(rewritten)
    translated = bool(src_lang and out_lang and src_lang != out_lang)
    return {
        "ok": not (missing or added or scripts or translated),
        "missing": missing,
        "added": added,
        "foreign_scripts": scripts,
        "language_changed": translated,
        "language": {"original": src_lang, "rewritten": out_lang},
    }


def _human(result: dict) -> str:
    if result["ok"]:
        return "PASS — every number, reference and citation survived the rewrite."
    lines = ["FAIL — keep the original. This rewrite changed more than wording:"]
    if result["missing"]:
        lines.append("  lost from the original (put each back, unchanged):")
        lines += [f"    {m.split(':', 1)[1]}" for m in result["missing"]]
    if result["added"]:
        lines.append("  invented, not in the original (remove each):")
        lines += [f"    {a.split(':', 1)[1]}" for a in result["added"]]
    if result["language_changed"]:
        lines.append("  the text was TRANSLATED, not re-voiced. Rewrite it in "
                     f"{result['language']['original']}.")
    if result["foreign_scripts"]:
        lines.append("  words appeared in another writing system: "
                     + ", ".join(result["foreign_scripts"]).lower())
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    as_json = "--json" in argv
    paths = [a for a in argv[1:] if not a.startswith("--")]
    with open(paths[0], encoding="utf-8") as f:
        original = f.read()
    with open(paths[1], encoding="utf-8") as f:
        rewritten = f.read()
    result = check(original, rewritten)
    print(json.dumps(result, ensure_ascii=False, indent=2) if as_json
          else _human(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

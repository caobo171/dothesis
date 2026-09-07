"""Promote the compose skeleton to numbered thesis chapters.

compose writes one fixed skeleton — "# 1. Introduction", "# 2. Main Body"
(with "## 2.1 Literature Review", "## 2.2 Methodology", "## 2.3 Analysis and
Results", "## 2.4 Discussion"), "# 3. Conclusion", appendices, references. A
thesis is examined as chapters, and the engine's own outline planned five of
them before compose flattened them. This maps the skeleton onto

    Chương 1  Introduction          (1.x unchanged)
    Chương 2  Literature review     (2.1.x -> 2.x)
    Chương 3  Methodology           (2.2.x -> 3.x)
    Chương 4  Results & discussion  (2.3.x -> 4.x, 2.4 -> 4.(n+1))
    Chương 5  Conclusion            (3.x -> 5.x)
    Appendices / References         (unnumbered)

Every heading number below a part shifts with it, and in-text cross
references ("mục 2.3.4", "Section 2.2") are rewritten with the same map. The
writer sometimes omits the "## 2.1" line and goes straight to "### 2.1.1", so
membership is decided by number prefix, not by the presence of the parent.
If the skeleton isn't there, the text comes back unchanged.

Disable with DOTHESIS_THESIS_STRUCTURE=0.
"""
from __future__ import annotations
import os
import re

CHAPTER_WORD = {'vi': 'Chương', 'en': 'Chapter', 'de': 'Kapitel', 'fr': 'Chapitre',
                'es': 'Capítulo', 'it': 'Capitolo', 'pt': 'Capítulo'}
TITLES = {
    'vi': {1: 'Giới thiệu', 2: 'Cơ sở lý thuyết', 3: 'Phương pháp nghiên cứu',
           4: 'Kết quả nghiên cứu và thảo luận', 5: 'Kết luận',
           'discussion': 'Thảo luận', 'appendix': 'Phụ lục', 'references': 'Tài liệu tham khảo'},
    'en': {1: 'Introduction', 2: 'Literature Review', 3: 'Methodology',
           4: 'Results and Discussion', 5: 'Conclusion',
           'discussion': 'Discussion', 'appendix': 'Appendices', 'references': 'References'},
}
_HEAD = re.compile(r'^(#{1,6})\s+(.*?)\s*$')
_NUM = re.compile(r'^(\d+(?:\.\d+)*)\.?\s+(.*)$')
_APPENDIX = re.compile(r'^\d+\.?\s+(appendices|appendix|phụ lục|anhang|annexes?|apéndices?)\b', re.I)
_REFS = re.compile(r'^\d+\.?\s+(references|bibliography|tài liệu tham khảo|literaturverzeichnis|bibliographie|referencias)\b', re.I)
_ENGLISH_LABEL = re.compile(r'^(introduction|main body|literature review|methodology|analysis and results|'
                            r'results and analysis|results|discussion|conclusions?)$', re.I)
_XREF = re.compile(r'(?i)\b(mục|phần|section|chương|chapter|sec\.)\s+(\d+(?:\.\d+)+)\b')


def _lang(language: str | None) -> str:
    code = (language or 'en').split('-')[0].lower()
    return code if code in TITLES else 'en'


def restructure_to_thesis(text: str, language: str | None, academic_level: str | None = None) -> str:
    if os.getenv('DOTHESIS_THESIS_STRUCTURE', '1') == '0':
        return text
    lang = _lang(language)
    T, CH = TITLES[lang], CHAPTER_WORD.get(lang, 'Chapter')
    lines = text.split('\n')

    heads = []  # (line_idx, level, number or None, title)
    for i, ln in enumerate(lines):
        m = _HEAD.match(ln)
        if not m:
            continue
        lvl, body = len(m.group(1)), m.group(2)
        n = _NUM.match(body)
        heads.append((i, lvl, n.group(1) if n else None, n.group(2) if n else body))

    tops = {h[2].rstrip('.'): h for h in heads if h[1] == 1 and h[2] and h[2].count('.') == 0}
    if not ({'1', '2', '3'} <= set(tops)):
        return text  # not the compose skeleton
    n23 = sum(1 for h in heads if h[2] and re.fullmatch(r'2\.3\.\d+', h[2].rstrip('.')))
    disc = str(n23 + 1)

    def remap(num: str) -> list[str] | None:
        p = num.rstrip('.').split('.')
        if p[0] == '1':
            return p
        if p[0] == '2':
            if len(p) == 1:
                return None
            k, rest = p[1], p[2:]
            if k == '1': return ['2'] + rest
            if k == '2': return ['3'] + rest
            if k == '3': return ['4'] + rest
            if k == '4': return ['4', disc] + rest
            return None
        if p[0] == '3':
            return ['5'] + p[1:]
        return None

    seen_chapter = set()
    out = []
    for i, ln in enumerate(lines):
        m = _HEAD.match(ln)
        if not m:
            out.append(ln)
            continue
        lvl, body = len(m.group(1)), m.group(2)
        n = _NUM.match(body)
        if not n:
            out.append(ln)
            continue
        num, title = n.group(1).rstrip('.'), n.group(2).strip()

        if lvl == 1 and num.count('.') == 0:
            if _APPENDIX.match(body):
                out.append(f"# {T['appendix']}"); continue
            if _REFS.match(body):
                out.append(f"# {T['references']}"); continue
            if num == '2':
                continue  # "Main Body" container disappears; its children become chapters
            new = remap(num)
            if new is None:
                out.append(ln); continue
            ch = int(new[0])
            seen_chapter.add(ch)
            out.append(f"# {CH} {ch}. {T[ch]}")
            continue

        new = remap(num)
        if new is None:
            out.append(ln); continue

        # A chapter that only ever appeared as "## 2.k" (or never appeared, the
        # writer skipping straight to "### 2.k.1") gets its heading synthesised
        # the first time anything under it shows up.
        ch = int(new[0])
        if ch in (2, 3, 4) and ch not in seen_chapter:
            seen_chapter.add(ch)
            out.append(f"# {CH} {ch}. {T[ch]}")
            out.append("")
            if len(new) == 1:
                continue  # that line WAS the chapter heading
        if len(new) == 1:
            continue
        depth = len(new)
        keep = T['discussion'] if (num.startswith('2.4') and depth == 2 and _ENGLISH_LABEL.match(title)) else title
        if _ENGLISH_LABEL.match(keep) and lang != 'en':
            keep = T.get('discussion') if 'discussion' in keep.lower() else keep
        out.append(f"{'#' * min(depth, 6)} {'.'.join(new)}. {keep}")

    result = '\n'.join(out)

    result = number_figure_captions(result, lang)

    def fix_xref(m):
        new = remap(m.group(2))
        return f"{m.group(1)} {'.'.join(new)}" if new else m.group(0)
    return _XREF.sub(fix_xref, result)


_FIG_LINE = re.compile(r'^!\[(Hình|Figure|Abbildung|Figura)(?::|\s*[-–])\s*(.*?)\]\((.+)\)\s*$')
_CHAP_LINE = re.compile(r'^#\s+(?:Chương|Chapter|Kapitel|Chapitre|Capítulo|Capitolo)\s+(\d+)\b', re.I)


def number_figure_captions(text: str, lang: str) -> str:
    """Turn "![Hình: …](p)" into "![Hình 3.1. …](p)" using the chapter it sits in."""
    out, chapter, count = [], 0, 0
    for ln in text.split('\n'):
        m = _CHAP_LINE.match(ln)
        if m:
            chapter, count = int(m.group(1)), 0
        f = _FIG_LINE.match(ln)
        if f and chapter:
            count += 1
            ln = f"![{f.group(1)} {chapter}.{count}. {f.group(2)}]({f.group(3)})"
        out.append(ln)
    return '\n'.join(out)

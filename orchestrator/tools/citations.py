"""In-text citations: find them, resolve them, format a reference list.

The pure-text half of the citation work — no .docx, no LLM, no network beyond
CrossRef — so it can be tested directly against the strings Vietnamese theses
actually contain.

The one rule everything here obeys: a reference entry is only ever built from a
CrossRef record. A citation that cannot be resolved is carried through marked as
unresolved, never invented from the in-text mention, because a fabricated
reference that looks correct is the exact failure this product exists to catch.
"""
from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass, field

from .crossref import DOI_RE, by_doi, search

# 1800-2099. Anything outside that in a thesis is a page number or a sample size.
_YEAR = r"(?:1[89]|20)\d{2}[a-z]?"

# "(Hair và cộng sự, 2010)" / "(Fornell & Larcker, 1981)" / "(Nguyễn Văn A, 2019)"
# Multiple citations inside one bracket are split on ";" before this runs.
_PAREN_ENTRY = re.compile(rf"^(?P<authors>.+?)[,\s]+(?P<year>{_YEAR})$")

# Narrative form: "Hair và cộng sự (2010) cho rằng…". Up to five words of author
# so "Nguyễn Thị Minh Hòa và cộng sự" survives; more than that and we are
# swallowing the sentence.
_NARRATIVE = re.compile(
    rf"([^\s(),;.]+(?:\s+[^\s(),;.]+){{0,4}})\s*\(\s*({_YEAR})\s*\)")

# Author tails that mean "and others", in both conventions a Vietnamese thesis
# mixes. Kept so the resolved reference can be matched back to the in-text form.
# "công sự" is not a typo on our side: it is the misspelling of "cộng sự" that
# students and PDF exports produce constantly, and refusing to read it means the
# citation goes to CrossRef with two junk words attached and never resolves.
_ET_AL = re.compile(
    r"\b(và\s+c[ộôọ]ng\s+s[ựu]|c[ộôọ]ng\s+s[ựu]|et\s+al\.?|and\s+others)\b", re.I)

# Words that introduce a citation without being part of the name. "Theo Hair và
# cộng sự (2019)" means "According to Hair et al. (2019)" — leaving "Theo" in
# sent it to CrossRef as part of the author, so the lookup failed and the
# reference list printed "Theo Hair và cộng sự" as if that were a person.
_LEAD_WORDS = {
    "theo", "trong", "tu", "cua", "boi", "va", "nhu", "voi", "duoc", "dua",
    "tren", "nghien", "cuu", "tac", "gia", "cac", "ket", "qua", "tai",
    "according", "to", "by", "from", "see", "as", "the", "in", "of", "cf",
}

# Tokens that are grammar, not surnames — they must never be what makes an
# author match (see `_author_matches`).
_STOP_NAME_TOKENS = {"va", "and", "the", "of", "cong", "su", "et", "al"}

_TAG = re.compile(r"<[^>]+>")

# CrossRef indexes more than papers. These record types come back from a
# bibliographic search looking like matches and are not citable works.
_JUNK_TYPES = {"component", "peer-review", "grant", "journal-issue",
               "journal-volume", "book-set"}


def clean(s: str) -> str:
    """Make a CrossRef string safe to print in a Word document.

    CrossRef returns JATS: titles carry markup ("<i>N</i> = 2,175"), entity
    escapes ("&amp;") and hard newlines. Written straight into a .docx those
    render literally — the reference list shows tags and an entity where a
    supervisor expects a title, which is exactly what they notice first.

    Tags are stripped BEFORE unescaping so that an escaped "&lt;" in a real
    title ("p &lt; 0.05") survives as "<" instead of being eaten as markup.
    """
    if not s:
        return ""
    return " ".join(html.unescape(_TAG.sub(" ", s)).split())


def _fold(s: str) -> str:
    """Diacritic-free, case-free form, for comparing names across scripts."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.replace("đ", "d").replace("Đ", "d").casefold()


def _name_tokens(s: str) -> set[str]:
    return {t for t in re.split(r"[^a-z]+", _fold(s))
            if len(t) >= 2 and t not in _STOP_NAME_TOKENS}


def _families(msg: dict) -> set[str]:
    out: set[str] = set()
    for a in msg.get("author") or []:
        out |= _name_tokens(a.get("family") or a.get("name") or "")
    return out


def is_citable(msg: dict | None) -> bool:
    """Is this CrossRef record a work a thesis can put in its reference list?

    A record with no author, no year, or a type like "component" is a
    supplemental file, a figure or a peer-review report — CrossRef ranks them
    alongside papers, and accepting one produces the reference line that started
    this: "(2017). Interpreting Correlation Matrix &amp; Unrotated Factor
    Solution." No author, no work, nothing the student ever cited.
    """
    if not msg:
        return False
    if (msg.get("type") or "").strip().lower() in _JUNK_TYPES:
        return False
    if not clean((msg.get("title") or [""])[0] or ""):
        return False
    if not _families(msg):
        return False
    parts = (msg.get("issued") or {}).get("date-parts") or [[]]
    return bool(parts and parts[0] and parts[0][0])


def _strip_lead(authors: str) -> str:
    """Drop leading words that introduce the citation rather than name anyone.

    Two rules. Known lead-in words go ("Theo", "của"). So does any leading word
    that does not start with a capital, because a name does — and the narrative
    pattern grabs a fixed five words back from the year, so "Mô hình của Fornell
    & Larcker (1981)" arrives with two words of sentence attached. Without this
    the whole citation is discarded as implausible, which under-reports sources
    rather than mis-reporting them, but under-reports them badly.

    Guarded on length: something that is nothing BUT lead words is not an
    author, and we would rather keep it whole and fail the plausibility check
    than strip it down to a fragment that passes.
    """
    words = authors.split()
    while len(words) > 1 and (_fold(words[0]).strip(".,;:") in _LEAD_WORDS
                              or not words[0][:1].isupper()):
        words = words[1:]
    return " ".join(words)


@dataclass(frozen=True)
class InText:
    """One in-text citation as it appears in the document."""
    authors: str
    year: str
    raw: str
    # Character offsets in the text it was parsed from, so the citation can be
    # turned into a hyperlink pointing at its reference entry. Excluded from
    # equality: two mentions of the same source are the same citation.
    span: tuple[int, int] = field(default=(-1, -1), compare=False)

    @property
    def key(self) -> str:
        """Identity for de-duplication: same authors + year = same source."""
        base = _ET_AL.sub("", self.authors)
        base = unicodedata.normalize("NFC", base).casefold()
        base = re.sub(r"[^\w\s]", " ", base)
        return f"{' '.join(base.split())}|{self.year.rstrip('abcdefgh')}"


def _plausible_author(s: str) -> bool:
    """Reject the sentence fragments a bare regex would otherwise collect.

    An author string starts with a capital and is not a number or a lone
    connective — without this, "khoảng (2010)" and "0.5 (2010)" become sources.
    """
    s = s.strip()
    if not s or len(s) > 90:
        return False
    first = s.lstrip("“\"'(")[:1]
    if not first or not first.isalpha() or not first.isupper():
        return False
    # A pure number, or the trailing words of a sentence, are not authors.
    return not any(ch.isdigit() for ch in s.split()[0])


def parse_intext_citations(text: str) -> list[InText]:
    """Every in-text citation in a passage, in order, duplicates included.

    Handles the two forms a Vietnamese thesis mixes freely: parenthetical
    "(Hair và cộng sự, 2010)" and narrative "Hair và cộng sự (2010)". Both
    styles appear in the same chapter, and a parser that only knew one would
    silently under-report half the sources.
    """
    out: list[InText] = []
    seen_spans: set[tuple[int, int]] = set()

    for m in re.finditer(r"\(([^()]{3,300})\)", text):
        inner = m.group(1)
        base = m.start(1)
        chunks = inner.split(";")
        off = 0
        for raw_chunk in chunks:
            chunk = raw_chunk.strip()
            lead = len(raw_chunk) - len(raw_chunk.lstrip())
            # A lone citation is linked bracket and all — "(Hair, 2010)" reads
            # as one thing. Inside "(A, 2010; B, 2011)" only the chunk is, so
            # each source links to its own entry.
            if len(chunks) == 1:
                span = m.span()
            else:
                span = (base + off + lead, base + off + lead + len(chunk))
            off += len(raw_chunk) + 1
            em = _PAREN_ENTRY.match(chunk)
            if not em:
                continue
            authors = _strip_lead(em.group("authors").strip(" ,"))
            if not _plausible_author(authors):
                continue
            out.append(InText(authors=authors, year=em.group("year"),
                              raw=f"({chunk})", span=span))
        seen_spans.add(m.span())

    for m in _NARRATIVE.finditer(text):
        # Skip anything already consumed as a parenthetical — "(see Hair (2010))"
        # would otherwise be counted twice.
        if any(s <= m.start() and m.end() <= e for s, e in seen_spans):
            continue
        captured = m.group(1).strip(" ,")
        authors = _strip_lead(captured)
        if not _plausible_author(authors):
            continue
        # The link starts at the author we kept, not at the "Theo" we dropped.
        # Located by search rather than by length difference: _strip_lead also
        # collapses internal whitespace, so the two strings are not offset by a
        # simple delta.
        start = m.start(1)
        if authors != captured:
            idx = captured.find(authors.split()[0])
            start += max(idx, 0)
        out.append(InText(authors=authors, year=m.group(2), raw=m.group(0),
                          span=(start, m.end())))

    return out


def dedupe(cits: list[InText]) -> list[InText]:
    """One entry per distinct source, first appearance wins."""
    seen: set[str] = set()
    out: list[InText] = []
    for c in cits:
        if c.key in seen:
            continue
        seen.add(c.key)
        out.append(c)
    return out


# --- formatting -------------------------------------------------------------

def _surname_first(a: dict) -> str:
    family = clean(a.get("family") or "")
    given = clean(a.get("given") or "")
    if not family:
        return clean(a.get("name") or "")
    initials = " ".join(f"{p[0]}." for p in given.replace(".", " ").split() if p)
    return f"{family}, {initials}".strip().rstrip(",")


def format_reference(msg: dict) -> str:
    """APA 7 reference line from a CrossRef record.

    APA because it is what Vietnamese business/management faculties ask for and
    what the rest of this product already assumes. The in-text form adapts to
    the document (see `intext_form`); the reference list does not need to.
    """
    authors = [_surname_first(a) for a in (msg.get("author") or [])[:20]]
    authors = [a for a in authors if a]
    if len(authors) > 1:
        who = ", ".join(authors[:-1]) + ", & " + authors[-1]
    elif authors:
        who = authors[0]
    else:
        who = ""

    parts = (msg.get("issued") or {}).get("date-parts") or [[]]
    year = parts[0][0] if parts and parts[0] else None
    title = clean((msg.get("title") or [""])[0] or "")
    container = clean((msg.get("container-title") or [""])[0] or "")
    doi = msg.get("DOI")

    # Authorless records are refused upstream (`is_citable`), but if one ever
    # reaches here it gets the APA title-first form rather than a line that
    # opens with a bare "(2017)." and reads as a broken entry.
    out = (f"{who} ({year or 'n.d.'}). {title}" if who
           else f"{title} ({year or 'n.d.'})").strip()
    if not out.endswith("."):
        out += "."
    if container:
        out += f" {container}."
    if doi:
        out += f" https://doi.org/{doi}"
    return out


def intext_form(msg: dict, *, vietnamese: bool) -> str:
    """The "(Author, Year)" a citation should be inserted as.

    `vietnamese` follows the document's own convention rather than a setting: a
    thesis that writes "và cộng sự" everywhere must not suddenly read "et al."
    in the sentences this tool touched.
    """
    authors = (msg.get("author") or [])
    parts = (msg.get("issued") or {}).get("date-parts") or [[]]
    year = parts[0][0] if parts and parts[0] else "n.d."
    if not authors:
        title = clean((msg.get("title") or [""])[0] or "") or "Không rõ tác giả"
        return f"({title[:40]}, {year})"
    first = clean(authors[0].get("family") or authors[0].get("name") or "")
    if len(authors) == 1:
        return f"({first}, {year})"
    if len(authors) == 2:
        second = clean(authors[1].get("family") or "")
        joiner = " và " if vietnamese else " & "
        return f"({first}{joiner}{second}, {year})"
    tail = "và cộng sự" if vietnamese else "et al."
    return f"({first} {tail}, {year})"


def uses_vietnamese_convention(text: str) -> bool:
    """Does this document write "và cộng sự" rather than "et al."?"""
    vi = len(re.findall(r"và\s+cộng\s+sự", text, re.I))
    en = len(re.findall(r"et\s+al", text, re.I))
    return vi >= en


# --- resolution -------------------------------------------------------------

def match_reference_line(cit: InText, lines: list[str]) -> str | None:
    """The student's own reference entry for this in-text citation, if they wrote one.

    Matched on surname plus year, and preferring an entry that OPENS with the
    surname — APA puts the first author first, so "Hair, J. F., ..." is the
    entry for "(Hair và cộng sự, 2010)" while a line that merely mentions Hair
    in the middle is somebody else's paper.
    """
    want_year = cit.year.rstrip("abcdefgh")
    names = _name_tokens(_ET_AL.sub("", cit.authors))
    best: tuple[int, str] | None = None
    for line in lines:
        if want_year not in line:
            continue
        tokens = _name_tokens(line)
        if names and not (names & tokens):
            continue
        # The author segment is everything before "(year)" in APA. Checking a
        # fixed prefix instead would score "Sarstedt, M. (2019). Revisiting Hair
        # et al.'s..." as a Hair entry.
        head = line.split("(", 1)[0] if "(" in line[:120] else line[:40]
        score = 2 if names & _name_tokens(head) else 1
        if best is None or score > best[0]:
            best = (score, line)
    return best[1] if best else None


def _accept(msg: dict, want_year: str, wanted_names: set[str]) -> bool:
    """The three gates every candidate has to pass.

      citable  — not a supplemental file, a figure or an authorless stub
      year     — the student wrote a year; a record with a different one is a
                 different work
      author   — the student wrote a NAME. A record whose authors share no
                 surname with it is not what they cited, however well it ranks.

    The author gate is the one that was missing, and its absence is how a
    citation of "Hair và cộng sự (2010)" came back as a SAGE methods component
    from 2017 with no author at all. CrossRef answers every query with
    something; matching on year alone accepts whatever that something is.
    """
    if not is_citable(msg):
        return False
    parts = (msg.get("issued") or {}).get("date-parts") or [[]]
    got = parts[0][0] if parts and parts[0] else None
    if str(got) != want_year:
        return False
    return not (wanted_names and not (wanted_names & _families(msg)))


def resolve(cit: InText, reference_line: str | None = None) -> dict | None:
    """The record only. See `resolve_verbose` for how it was found."""
    return resolve_verbose(cit, reference_line)[0]


def resolve_verbose(cit: InText,
                    reference_line: str | None = None) -> tuple[dict | None, str]:
    """Find the CrossRef record an in-text citation refers to, and say how.

    The second element is the strength of the match, and it is not decoration:

      "doi"         the student gave the identifier. Certain.
      "line"        matched against the student's own reference entry, which
                    carries a title. Strong.
      "author-year" matched on a surname and a year alone, because the student
                    cited this source without ever listing it. WEAK — "Nunnally
                    1978" is both "Psychometric theory" and "1K Delay Line
                    Digitizer", and nothing here can tell which one they meant.

    A caller that flattens those three into "found" is presenting a guess as a
    verified reference, which is the failure this whole feature exists to avoid.

    `reference_line` is the entry the student already wrote for this citation,
    and it is worth far more than the citation itself. CrossRef matches on a
    BIBLIOGRAPHIC string: given "Fornell & Larcker 1981" it returns five tables
    from other people's papers that mention the Fornell-Larcker criterion, and
    given the student's full line it returns the actual 1981 paper, first hit.
    Author-and-year is all an in-text citation carries, which is why phase A
    reads the existing reference list before replacing it.

    A DOI in that line is better still — it is an exact lookup, and the only
    path here that is not a search at all.
    """
    want = cit.year.rstrip("abcdefgh")
    wanted = _name_tokens(_ET_AL.sub("", cit.authors))

    if reference_line:
        found = DOI_RE.search(reference_line)
        if found:
            try:
                msg = by_doi(found.group(1).rstrip(".,;"))
            except Exception:  # noqa: BLE001 — a dead DOI is "no answer", not a crash
                msg = None
            # No author or year gate on a DOI: the student gave us the
            # identifier, and it names the work more precisely than their
            # spelling of the name does.
            if is_citable(msg):
                return msg, "doi"
        for msg in search(reference_line, rows=5):
            if _accept(msg, want, wanted):
                return msg, "line"

    for msg in search(f"{_ET_AL.sub('', cit.authors).strip()} {cit.year}", rows=5):
        if _accept(msg, want, wanted):
            return msg, "author-year"
    return None, ""


def parse_reference_lines(lines: list[str]) -> list[str]:
    """Keep only the lines from an existing reference section worth carrying.

    A reference has a year or a DOI. Everything else in that part of a thesis is
    a heading, a page number or a stray line from the PDF export.
    """
    out = []
    for ln in lines:
        s = " ".join(ln.split())
        if len(s) < 20:
            continue
        if re.search(_YEAR, s) or DOI_RE.search(s):
            out.append(s)
    return out

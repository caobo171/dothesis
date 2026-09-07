/**
 * Markdown helpers for the blog surface.
 *
 * Everything here is a pure function over the raw markdown `body` a post
 * stores, because the two consumers need different things out of the same
 * string: the renderer turns it into HTML, while the contents box, the FAQ
 * JSON-LD and the excerpt need structure *before* React ever sees it.
 *
 * The heading-id algorithm is a CONTRACT, not an implementation detail. It is
 * duplicated in `api/app/blog/markdown.py` and both sides are pinned to the
 * fixture in `__fixtures__/headings.{md,json}`. If the two drift, every
 * contents-box link, every FAQ anchor and every `#section` deep link a writer
 * emits silently points at nothing — a failure that renders fine and is
 * invisible until someone clicks.
 */

/** One heading, with the id the rendered HTML will carry. */
export type Heading = { level: number; text: string; id: string };

/** One question/answer pair lifted out of the FAQ section. */
export type FaqItem = { question: string; answer: string };

/**
 * The FAQ section's H2. Matched on its slug rather than its literal text so a
 * stray double space or a different capitalisation still finds the section.
 */
export const FAQ_HEADING = "Câu hỏi thường gặp";

/**
 * Slug for one heading, no collision handling.
 *
 * Deliberately NOT `github-slugger` (which rehype-slug uses under the hood):
 * that keeps Vietnamese diacritics, so `## Phân tích EFA` would render
 * `id="phân-tích-efa"`. A percent-encoded, diacritic-bearing anchor is legal
 * but it is not what the Python side produces, it is not what an author types
 * into a link, and it round-trips badly through Search Console. ASCII is the
 * lowest common denominator both ends can agree on.
 *
 * Order matters: `đ` has no NFD decomposition (it is a distinct letter, not
 * `d` plus a mark), so it is replaced explicitly rather than falling out of
 * the combining-mark strip.
 */
export function slugify(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[đĐ]/g, "d")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/**
 * Stateful slugger: hands out unique ids across one document.
 *
 * Mirrors github-slugger's collision rule (first wins the bare slug, repeats
 * get `-1`, `-2`, ...) including the part people forget: the suffixed
 * candidate is itself checked, so a document with `## efa`, `## efa 1`,
 * `## efa` gives `efa`, `efa-1`, `efa-2` rather than two elements claiming
 * `efa-1`.
 */
export class HeadingSlugger {
  private occurrences = new Map<string, number>();

  slug(text: string): string {
    const base = slugify(text);
    let candidate = base;
    if (this.occurrences.has(candidate)) {
      let n = this.occurrences.get(base) ?? 0;
      do {
        n += 1;
        candidate = `${base}-${n}`;
      } while (this.occurrences.has(candidate));
      this.occurrences.set(base, n);
    }
    this.occurrences.set(candidate, 0);
    return candidate;
  }

  reset(): void {
    this.occurrences.clear();
  }
}

/**
 * Strip inline markdown so heading text matches the DOM text content the
 * renderer produces — `## Chỉ số **AVE**` is `Chỉ số AVE` to a reader, to
 * rehype, and therefore to the slugger.
 */
export function stripInline(text: string): string {
  let out = text;
  out = out.replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1"); // images -> alt
  out = out.replace(/\[([^\]]*)\]\([^)]*\)/g, "$1"); // inline links -> text
  out = out.replace(/\[([^\]]*)\]\[[^\]]*\]/g, "$1"); // reference links -> text
  out = out.replace(/`+([^`]*)`+/g, "$1"); // code spans -> content
  // Emphasis markers only where they actually wrap something, so `p_value`
  // and `t_stat` keep their underscores.
  for (let i = 0; i < 2; i += 1) {
    out = out.replace(/(\*\*\*|\*\*|\*|___|__|_|~~)(?=\S)([\s\S]*?\S)\1/g, "$2");
  }
  out = out.replace(/<[^>]+>/g, ""); // raw HTML tags
  out = out.replace(/\\(.)/g, "$1"); // markdown escapes
  return out.replace(/\s+/g, " ").trim();
}

/** True while the scanner sits inside a ``` or ~~~ fence. */
function scanLines(markdown: string, visit: (line: string, inFence: boolean) => void): void {
  let fence: string | null = null;
  for (const line of markdown.split(/\r?\n/)) {
    const open = /^ {0,3}(`{3,}|~{3,})/.exec(line);
    if (fence) {
      // A fence closes on a run of the same character at least as long as the
      // opener; anything else inside it is content, headings included.
      if (open && open[1][0] === fence[0] && open[1].length >= fence.length) {
        fence = null;
        continue;
      }
      visit(line, true);
      continue;
    }
    if (open) {
      fence = open[1];
      continue;
    }
    visit(line, false);
  }
}

/**
 * Every ATX heading in the document, in order, with its rendered id.
 *
 * All six levels are walked even when the caller only wants H2s: the slugger's
 * collision counter is document-wide, so skipping an H3 named the same as an
 * H2 would shift every later suffix away from what the DOM actually carries.
 *
 * Setext headings (`Title` underlined with `===`) are not recognised. The
 * writer emits ATX only and the QA gate enforces it; supporting `---` here
 * would make every thematic break ambiguous.
 */
export function extractHeadings(markdown: string, levels?: number[]): Heading[] {
  const slugger = new HeadingSlugger();
  const all: Heading[] = [];
  scanLines(markdown, (line, inFence) => {
    if (inFence) return;
    const m = /^ {0,3}(#{1,6})(?:\s+(.*))?$/.exec(line);
    if (!m) return;
    const raw = (m[2] ?? "").replace(/\s+#+\s*$/, ""); // closing hashes
    const text = stripInline(raw);
    all.push({ level: m[1].length, text, id: slugger.slug(text) });
  });
  if (!levels) return all;
  const wanted = new Set(levels);
  return all.filter((h) => wanted.has(h.level));
}

/** The contents box model: H2s only, per spec §10. */
export function tableOfContents(markdown: string): Heading[] {
  return extractHeadings(markdown, [2]);
}

/**
 * The FAQ section's questions and answers, for `FAQPage` JSON-LD.
 *
 * The body already renders the section, so this exists only to feed the
 * structured data. Answers come back as plain text because that is what
 * `acceptedAnswer.text` wants — markdown syntax in there is scraped verbatim
 * into the search result.
 */
export function extractFaq(markdown: string, headingText = FAQ_HEADING): FaqItem[] {
  const target = slugify(headingText);
  const items: FaqItem[] = [];
  let inSection = false;
  let question: string | null = null;
  let buffer: string[] = [];

  const flush = () => {
    if (question !== null) items.push({ question, answer: plainTextParagraphs(buffer) });
    question = null;
    buffer = [];
  };

  scanLines(markdown, (line, inFence) => {
    if (inFence) {
      if (inSection && question !== null) buffer.push(line);
      return;
    }
    const h = /^ {0,3}(#{1,6})(?:\s+(.*))?$/.exec(line);
    if (h) {
      const level = h[1].length;
      const text = stripInline((h[2] ?? "").replace(/\s+#+\s*$/, ""));
      if (level <= 2) {
        flush();
        inSection = slugify(text) === target;
        return;
      }
      if (inSection && level === 3) {
        flush();
        question = text;
        return;
      }
    }
    if (inSection && question !== null) buffer.push(line);
  });
  flush();
  return items;
}

/** Join an answer's lines, keeping the paragraph breaks and dropping syntax. */
function plainTextParagraphs(lines: string[]): string {
  return lines
    .join("\n")
    .split(/\n\s*\n/)
    .map((p) => plainText(p))
    .filter(Boolean)
    .join("\n\n");
}

/**
 * Readable text with the markdown syntax removed.
 *
 * Table pipes become spaces rather than disappearing, so `| 0.7 | đạt |` is
 * three words and not one nonsense token — the word count that drives reading
 * time reads through this function.
 */
export function plainText(markdown: string): string {
  const kept: string[] = [];
  scanLines(markdown, (line, inFence) => {
    if (inFence) return; // code is not prose
    let s = line;
    if (/^ {0,3}\|?[\s:|-]+\|[\s:|-]*$/.test(s)) return; // table separator row
    if (/^ {0,3}([-*_])(\s*\1){2,}\s*$/.test(s)) return; // thematic break
    s = s.replace(/^ {0,3}#{1,6}\s*/, "");
    s = s.replace(/^ {0,3}>+\s?/, "");
    s = s.replace(/^ {0,3}(?:[-*+]|\d+[.)])\s+/, "");
    s = s.replace(/\|/g, " ");
    kept.push(stripInline(s));
  });
  return kept.join(" ").replace(/\s+/g, " ").trim();
}

/** Words of prose, ignoring code blocks, table pipes and link URLs. */
export function wordCount(markdown: string): number {
  const text = plainText(markdown);
  return text ? text.split(/\s+/).length : 0;
}

/** Minutes, at the 200 wpm the API uses. Always at least 1. */
export function readingTime(markdown: string): number {
  return Math.max(1, Math.ceil(wordCount(markdown) / 200));
}

/** First `max` characters of prose, cut on a word boundary, for a fallback excerpt. */
export function excerpt(markdown: string, max = 180): string {
  const text = plainText(markdown);
  if (text.length <= max) return text;
  const cut = text.slice(0, max);
  const space = cut.lastIndexOf(" ");
  return `${(space > 40 ? cut.slice(0, space) : cut).trimEnd()}…`;
}

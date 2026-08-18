import {
  Children,
  cloneElement,
  Fragment,
  isValidElement,
  ReactNode,
  useEffect,
  useState,
} from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import { Check, Copy, Expand, FileText, Loader2, X } from "lucide-react";
import { Mermaid } from "./Mermaid";
import { CitationChip } from "./CitationChip";
import { triggerExportDownload } from "@/app/lib/api";
import { WidgetRenderer } from "./widgets/WidgetRenderer";
import { AttachmentPreview } from "./AttachmentPreview";
import { useArtifactDownload } from "./hooks/useArtifactDownload";
import type {
  AttachmentChipMeta,
  WidgetHint,
  WidgetSelectHandler,
} from "./widgets/types";


// Compact chip rendered under a user bubble when the message had files
// attached. Read-only display — no remove / re-upload affordance here
// (that lives in the composer chip row).
function UserAttachmentChip({ meta }: { meta: AttachmentChipMeta }) {
  const [open, setOpen] = useState(false);
  const size =
    typeof meta.size_bytes === "number"
      ? _formatBytes(meta.size_bytes)
      : null;
  return (
    <>
      {/* Clickable: the chip names a file the student can no longer see. Opening
          it shows the EXTRACTED text — what the agent actually read — so "did my
          result tables survive?" is answerable here instead of by downloading
          the file and opening Word. */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 max-w-[260px] rounded-lg border border-ink-200 bg-white px-2 py-1 text-[11.5px] text-ink-700 hover:border-ink-300 hover:bg-ink-50 transition-colors"
        title={`${meta.filename} — bấm để xem nội dung`}
      >
        <FileText className="w-3.5 h-3.5 text-ink-500 shrink-0" aria-hidden />
        <span className="truncate">{meta.filename}</span>
        {size && <span className="text-ink-400 shrink-0">· {size}</span>}
      </button>
      {open && <AttachmentPreview meta={meta} onClose={() => setOpen(false)} />}
    </>
  );
}

function _formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}


function MarkdownTable({ children }: { children?: ReactNode }) {
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!expanded) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setExpanded(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [expanded]);

  const table = (extraClass = "") => (
    <table className={`w-full min-w-[960px] table-fixed border-collapse text-[13.5px] ${extraClass}`}>
      {children}
    </table>
  );

  return (
    <>
      <div className="group/table relative my-3.5 max-w-full min-w-0 rounded-lg border border-ink-200 bg-white">
        <div className="markdown-table-preview max-w-full overflow-x-auto overscroll-x-contain rounded-lg">
          {table()}
        </div>
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="absolute right-2 top-2 inline-flex items-center gap-1.5 rounded-md border border-ink-200 bg-white/95 px-2 py-1 text-[11.5px] font-medium text-ink-600 shadow-sm backdrop-blur hover:bg-ink-50 hover:text-ink-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
          aria-label="View full table"
        >
          <Expand className="h-3.5 w-3.5" aria-hidden />
          <span className="hidden sm:inline">View full</span>
        </button>
      </div>

      {expanded && (
        <div
          className="fixed inset-0 z-[70] flex flex-col bg-white"
          role="dialog"
          aria-modal="true"
          aria-label="Full table view"
        >
          <header className="flex h-14 shrink-0 items-center border-b border-ink-200 px-4 sm:px-6">
            <span className="text-sm font-semibold text-ink-900">Full table</span>
            <span className="flex-1" />
            <button
              type="button"
              onClick={() => setExpanded(false)}
              className="inline-flex h-8 items-center gap-1.5 rounded-md px-2 text-[12.5px] font-medium text-ink-600 hover:bg-ink-100 hover:text-ink-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
              aria-label="Close full table"
            >
              <X className="h-4 w-4" aria-hidden />
              Close
            </button>
          </header>
          <div className="min-h-0 flex-1 overflow-auto p-4 sm:p-6">
            {table("text-[14px]")}
          </div>
        </div>
      )}
    </>
  );
}


function _renderLiteralBreaks(children: ReactNode): ReactNode {
  // ReactMarkdown intentionally treats raw HTML as text. Models nevertheless
  // commonly put <br> inside GFM cells, where converting it to a Markdown
  // newline would split the table row. Convert only the literal break token in
  // the already-parsed cell tree, preserving all other HTML as inert text.
  return Children.map(children, (child) => {
    if (typeof child === "string") {
      const parts = child.split(/<br\s*\/?>/gi);
      if (parts.length === 1) return child;
      return parts.map((part, index) => (
        <Fragment key={index}>
          {index > 0 && <br />}
          {part}
        </Fragment>
      ));
    }
    if (isValidElement<{ children?: ReactNode }>(child) && child.props.children != null) {
      return cloneElement(child, undefined, _renderLiteralBreaks(child.props.children));
    }
    return child;
  });
}


/**
 * Copy-to-clipboard button for assistant messages.
 *
 * - Strips agent markers (`[OPTIONS]`, `[PAPERS]…[/PAPERS]`) from the
 *   copied text — those are wire-format artifacts the user shouldn't
 *   paste into anything outside this app.
 * - Shows a brief "Copied" check state after a successful copy, then
 *   reverts after 1.5s.
 * - Renders as a small pill below the message, so the affordance is
 *   discoverable without crowding the bubble itself.
 */
// Per-response cost + latency, shown next to the Copy button. Hidden until the
// backend has recorded a duration (legacy / user / in-flight rows have 0).
function ResponseMeta({
  costCredits,
  durationMs,
}: {
  costCredits?: number;
  durationMs?: number;
}) {
  if (!durationMs && !costCredits) return null;
  const seconds = durationMs ? (durationMs / 1000).toFixed(1) : null;
  return (
    <span className="inline-flex items-center gap-2 text-[11.5px] text-ink-400">
      {typeof costCredits === "number" && costCredits > 0 && (
        <span title="Credits spent on this response">
          {costCredits} {costCredits === 1 ? "credit" : "credits"}
        </span>
      )}
      {seconds && (
        <>
          <span aria-hidden className="text-ink-300">·</span>
          <span title="Response time">{seconds}s</span>
        </>
      )}
    </span>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      // navigator.clipboard is gated behind a secure context — fall back
      // to the legacy execCommand path so the button still works on http.
      const clean = _stripMarkers(text);
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(clean);
      } else {
        const ta = document.createElement("textarea");
        ta.value = clean;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand("copy"); } finally { ta.remove(); }
      }
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* swallow — failure is silent; the button just doesn't flip state */
    }
  };

  // Width-stable: a fixed-width row + fixed-width text span so the button
  // doesn't visibly jump from "Copy" (4 chars) to "Copied" (6 chars) when
  // the state flips. The icon column also stays the same size regardless
  // of which glyph is shown.
  return (
    <button
      type="button"
      onClick={handleCopy}
      title="Copy message"
      className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-[11.5px] text-ink-500 hover:bg-ink-100 hover:text-ink-700 transition-colors w-[78px] justify-start"
    >
      <span className="w-3 h-3 inline-flex items-center justify-center shrink-0">
        {copied
          ? <Check className="w-3 h-3 text-emerald-600" />
          : <Copy className="w-3 h-3" />}
      </span>
      <span
        className={`font-medium ${copied ? "text-emerald-700" : ""}`}
      >
        {copied ? "Copied" : "Copy"}
      </span>
    </button>
  );
}

/**
 * Render agent messages with full markdown — bold, italic, lists (ordered +
 * unordered), tables, code blocks, blockquotes, headings, links.
 *
 * History: this used to be a hand-rolled link parser with `whitespace-pre-wrap`,
 * which meant the agent's `**bold**` and `* list` markers came through as raw
 * asterisks. The M3 methodology proposal (Vietnamese Likert items, nested
 * bullets) rendered as a wall of text the user couldn't scan. react-markdown
 * + remark-gfm handles all of that and is React-safe (no
 * dangerouslySetInnerHTML, no XSS risk from agent content).
 *
 * Tailwind classes on each rendered tag keep the visual style consistent with
 * the design system — keep them sober (no big headings inside chat bubbles).
 */
// Inline grounding pills. The agent emits `{{cite: label | title | url}}` next
// to grounded claims (curly braces so Markdown's `[...]` link parser leaves them
// intact). We split those out of the rendered text and swap in <CitationChip>.
const _CITE_RE = /\{\{cite:\s*([^{}]+?)\}\}/g;

// remark-gfm autolinks bare `https://…` URLs — inside a `{{cite}}` marker that
// splits the marker across a text node + an <a>, so the regex below would miss
// it (and gfm even swallows the trailing `}}` into the href). Neutralize the
// autolink triggers (`://`, `www.`) INSIDE markers with private-use sentinels
// before markdown runs; _splitCites restores them when building the chip URL.
const _SENTINEL_SCHEME = "\uE000";
const _SENTINEL_WWW = "\uE001";

function _protectCiteUrls(md: string): string {
  return md.replace(/\{\{cite:\s*[^{}]+?\}\}/g, marker =>
    marker.replace(/:\/\//g, _SENTINEL_SCHEME).replace(/\bwww\./g, _SENTINEL_WWW),
  );
}

function _restoreUrl(u: string): string {
  return u.replace(new RegExp(_SENTINEL_SCHEME, "g"), "://")
          .replace(new RegExp(_SENTINEL_WWW, "g"), "www.");
}

// KaTeX errors on a raw `&`, `%`, or `#` inside `\text{}` — the model sometimes
// writes `\text{Hypotheses & Model (M3)}`, which then shows as broken source
// instead of rendering. Escape those chars inside `\text{}` (its content is
// always literal text). Alignment `&` in matrices / aligned environments lives
// OUTSIDE `\text{}`, so it's left intact.
function _fixMathText(md: string): string {
  return md.replace(/\\text\{([^{}]*)\}/g, (_full, inner: string) => {
    const fixed = inner
      .replace(/(?<!\\)&/g, "\\&")
      .replace(/(?<!\\)%/g, "\\%")
      .replace(/(?<!\\)#/g, "\\#");
    return `\\text{${fixed}}`;
  });
}

function _normalizeLatexDelimiters(md: string): string {
  // remark-math accepts $/$$ delimiters, while research-writing models often
  // emit the equally standard \(...\) and \[...\] forms. Markdown consumes the
  // latter backslashes as escapes before KaTeX sees them. Normalize prose
  // segments only; fenced examples must remain byte-for-byte source code.
  return md
    .split(/(```[\s\S]*?```|~~~[\s\S]*?~~~)/g)
    .map((segment) => {
      if (segment.startsWith("```") || segment.startsWith("~~~")) return segment;
      return segment
        .replace(/\\\[([\s\S]*?)\\\]/g, (_whole, body: string) =>
          `\n$$\n${body.trim()}\n$$\n`)
        .replace(/\\\((.*?)\\\)/g, (_whole, body: string) => `$${body.trim()}$`);
    })
    .join("");
}

function _splitCites(text: string, keyBase: string): ReactNode {
  if (!text.includes("{{cite:")) return text;
  const out: ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  _CITE_RE.lastIndex = 0;
  while ((m = _CITE_RE.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const parts = m[1].split("|").map(s => s.trim());
    const label = parts[0] ?? "";
    const title = parts[1] || parts[0] || "";
    const url = _restoreUrl(parts[2] || "");
    // Need at least a label + url to make a useful pill; else leave raw.
    out.push(
      url
        ? <CitationChip key={`${keyBase}-${i++}`} label={label} title={title} url={url} />
        : m[0],
    );
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

// Walk a renderer's children; rewrite plain-string parts, pass elements
// (bold/links/etc.) through untouched. Markers live in prose, so string-level
// handling covers the real cases without recursing into nested nodes.
function _withCitations(children: ReactNode): ReactNode {
  if (typeof children === "string") return _splitCites(children, "c");
  if (Array.isArray(children)) {
    return children.map((c, i) =>
      typeof c === "string"
        ? <Fragment key={i}>{_splitCites(c, `c${i}`)}</Fragment>
        : c,
    );
  }
  return children;
}

// An export link inside assistant prose ("Tải bản .docx tại đây"). A plain <a>
// navigation hits the GET-auth'd /exports route WITHOUT the ?st= token and the
// download never starts, so the click mints a scoped token first. That mint is
// a round trip, which is why this needs state at all: previously the promise
// was discarded, so a slow mint looked like a dead link and a failed one was
// invisible.
function ExportLink({ href, children }: { href: string; children?: ReactNode }) {
  const { busy, error, start } = useArtifactDownload();
  return (
    <>
      <a
        href={href}
        aria-busy={busy}
        onClick={(e) => {
          e.preventDefault();
          void start(() => triggerExportDownload(href));
        }}
        className="underline text-primary-600 hover:text-primary-700"
      >
        {children}
      </a>
      {busy && (
        <Loader2 className="inline-block w-3 h-3 ml-1 align-baseline animate-spin text-primary-600" aria-hidden />
      )}
      {error && (
        <span className="ml-1 text-[11px] text-[#8E6B2A]" role="alert">({error})</span>
      )}
    </>
  );
}


const _markdownComponents = {
  // Lists — tight spacing so multi-level bullets stay legible inside a bubble.
  ul: ({ children, className }: { children?: ReactNode; className?: string }) => {
    // remark-gfm marks task lists with `contains-task-list`. Render those
    // without bullets + with tighter rows so each option pills cleanly.
    const isTaskList = (className || "").includes("contains-task-list");
    return (
      <ul
        className={
          isTaskList
            ? "list-none pl-0 my-2.5 space-y-1.5"
            : "list-disc pl-5 my-2.5 space-y-1"
        }
      >
        {children}
      </ul>
    );
  },
  ol: ({ children }: { children?: ReactNode }) => (
    <ol className="list-decimal pl-5 my-2.5 space-y-1">{children}</ol>
  ),
  li: ({ children, className }: { children?: ReactNode; className?: string }) => {
    // Task-list items get a button-like card row: a custom check box on
    // the left + the option text on the right, all wrapped so the whole
    // row is the click target. The underlying input stays present + is
    // styled to invisibility (we render our own check icon) so the
    // markdown semantics (`- [x]` is "checked", `- [ ]` is "unchecked")
    // still carry through to copy-paste exports.
    const isTask = (className || "").includes("task-list-item");
    if (isTask) {
      return (
        <li className="flex items-start gap-2.5 px-2.5 py-1.5 rounded-lg border border-ink-200 bg-white leading-snug">
          {children}
        </li>
      );
    }
    return <li className="leading-relaxed">{_withCitations(children)}</li>;
  },
  input: ({ type, checked }: { type?: string; checked?: boolean }) => {
    // Custom-render checkbox inputs (always from markdown task lists in
    // our world) as a clean 16×16 box. `disabled` is implicit — markdown
    // task lists are not interactive in chat; the user fills them in the
    // exported DOCX. Hide the visual default and ship our own.
    if (type !== "checkbox") return null;
    return (
      <span
        aria-hidden
        className={`inline-flex w-4 h-4 mt-[3px] shrink-0 rounded border-[1.5px] items-center justify-center transition-colors ${
          checked
            ? "bg-primary-600 border-primary-600 text-white"
            : "bg-white border-ink-300"
        }`}
      >
        {checked && <Check className="w-2.5 h-2.5" />}
      </span>
    );
  },
  // Inline emphasis.
  strong: ({ children }: { children?: ReactNode }) => (
    <strong className="font-semibold text-ink-900">{children}</strong>
  ),
  em: ({ children }: { children?: ReactNode }) => (
    <em className="italic">{children}</em>
  ),
  // Paragraph spacing — relaxed leading so stacked Vietnamese tone marks
  // (dấu) don't visually collide line-to-line, and a real gap between blocks.
  p: ({ children }: { children?: ReactNode }) => (
    <p className="my-2.5 leading-relaxed first:mt-0 last:mb-0">{_withCitations(children)}</p>
  ),
  // Headings inside a bubble look weird at h1/h2 sizes; downsize. Extra top
  // margin sets each section apart from the block above (the "between blocks"
  // cramping); first:mt-0 avoids a leading gap at the top of the bubble.
  h1: ({ children }: { children?: ReactNode }) => (
    <div className="font-semibold text-[15px] mt-5 mb-2 first:mt-0">{children}</div>
  ),
  h2: ({ children }: { children?: ReactNode }) => (
    <div className="font-semibold text-[14.5px] mt-5 mb-2 first:mt-0">{children}</div>
  ),
  h3: ({ children }: { children?: ReactNode }) => (
    <div className="font-semibold text-[14px] mt-4 mb-1.5 first:mt-0">{children}</div>
  ),
  // Code — inline, plain block, or rendered diagram. A ```mermaid``` fenced
  // block becomes an SVG via the Mermaid component; everything else stays
  // a monospace block. The lang detection is on the className prefix
  // remark sets (`language-mermaid`, `language-python`, ...).
  code: ({ children, className }: { children?: ReactNode; className?: string }) => {
    const lang = (className || "").replace(/^language-/, "");
    if (lang === "mermaid") {
      const src = typeof children === "string" ? children : Array.isArray(children) ? children.join("") : "";
      return <Mermaid source={src.trim()} />;
    }
    const isBlock = (className || "").startsWith("language-");
    return isBlock ? (
      <code className="block rounded bg-ink-50 px-2 py-1 text-[13px] font-mono whitespace-pre-wrap">
        {children}
      </code>
    ) : (
      <code className="rounded bg-ink-50 px-1 py-0.5 text-[13px] font-mono">{children}</code>
    );
  },
  pre: ({ children }: { children?: ReactNode }) => (
    <pre className="my-2.5 rounded bg-ink-50 p-2 text-[13px] overflow-x-auto">{children}</pre>
  ),
  // Links — same blue underline as before. Export-artifact links (the agent's
  // "Tải bản .docx/.pdf tại đây") point at /projects/<id>/exports/<file>, which
  // is GET-auth'd via a short-lived ?st= token — a plain <a> navigation hits it
  // WITHOUT the token and fails (the download never starts). Intercept those and
  // route through triggerExportDownload, which mints the token + triggers the
  // download. All other links keep the normal new-tab behavior.
  a: ({ href, children }: { href?: string; children?: ReactNode }) => {
    const isExport = !!href && /\/projects\/[^/]+\/exports\//.test(href);
    // Export links go through a component rather than an inline handler because
    // the download needs hook state (in-flight + error), and hooks can't live
    // in a branch of this renderer.
    if (isExport) return <ExportLink href={href!}>{children}</ExportLink>;
    return (
      <a
        href={href}
        className="underline text-primary-600 hover:text-primary-700"
        target="_blank"
        rel="noreferrer noopener"
      >
        {children}
      </a>
    );
  },
  // Tables (GFM) stay inside the message with their own horizontal scroll;
  // readers can promote dense tables to a viewport-sized inspection surface.
  table: MarkdownTable,
  th: ({ children }: { children?: ReactNode }) => (
    // Reserve the final header's right edge for the overlayed expand control.
    <th className="border border-ink-200 bg-ink-50 px-4 py-3 text-left font-semibold last:pr-32">
      {_renderLiteralBreaks(children)}
    </th>
  ),
  td: ({ children }: { children?: ReactNode }) => (
    <td className="border border-ink-200 px-4 py-3.5 text-left align-top leading-relaxed">
      <div className="markdown-table-cell">{_renderLiteralBreaks(children)}</div>
    </td>
  ),
  // Blockquote — soft left rail.
  blockquote: ({ children }: { children?: ReactNode }) => (
    <blockquote className="my-2.5 border-l-2 border-ink-200 pl-3 text-ink-600">{children}</blockquote>
  ),
  // Suppress `<hr>` entirely. The agent occasionally emits `___` or `---`
  // lines (Gemini uses them as visual separators or thinks they're
  // fill-in-the-blank markers in questionnaires) — markdown then converts
  // them to horizontal rules that look broken inside a chat bubble. The
  // agent never has a real semantic reason to render an HR; killing the
  // element entirely is cheaper than per-case formatting fights. The
  // system prompt also instructs the agent not to emit `___`/`---` lines
  // for new messages, but this swallows the existing persisted ones.
  hr: () => null,
};

/**
 * Strip a trailing `[OPTIONS] …` line from the message body before
 * markdown rendering. Backend already extracted this into tool_calls_json
 * so the cards render below; without this strip the user would see both
 * the literal marker text AND the cards, which looks broken.
 *
 * Matches the same shape `_parse_options_marker` in agent/runtime.py
 * recognizes — keep them in sync.
 */
const _OPTIONS_LINE = /^\s*\[OPTIONS(?:\s*:\s*\w+)?(?:\s+multi)?\]\s*.+$/m;
// The same marker trailing the END of a sentence rather than owning its line —
// "…rồi mới đánh dấu M5 done. [OPTIONS] A | B | C". The server parser accepts
// that shape (agent/runtime.py), so the client has to strip it, or the student
// reads the raw marker as prose under the buttons it produced.
const _OPTIONS_INLINE = /\[OPTIONS(?:\s*:\s*\w+)?(?:\s+multi)?\]\s*.+$/;
// `[PAPERS] {json} [/PAPERS]` — the JSON payload is parsed server-side and
// surfaces as a PapersPanel widget below the bubble. We strip the marker
// from the rendered text so the user doesn't see the raw block.
const _PAPERS_BLOCK = /\[PAPERS\][\s\S]*?\[\/PAPERS\]/g;
// `[ATTACHED] uploads/foo.pdf | uploads/data.csv` — a leading line the
// composer injects when the user attached files. The agent reads it raw;
// the UI strips it from the user's bubble so the visible message reads
// like prose (the chip row above the composer is the user-facing signal).
const _ATTACHED_LINE = /^\s*\[ATTACHED\][^\n]*\n?/;

function _stripOptionsMarker(text: string): string {
  // Only strip the marker if it appears as the LAST non-empty line.
  const lines = text.split("\n");
  for (let i = lines.length - 1; i >= 0; i--) {
    if (!lines[i].trim()) continue;
    if (_OPTIONS_LINE.test(lines[i])) {
      lines.splice(i, 1);
      return lines.join("\n").trimEnd();
    }
    if (_OPTIONS_INLINE.test(lines[i])) {
      // Keep the sentence, drop the marker that was glued to its tail.
      lines[i] = lines[i].replace(_OPTIONS_INLINE, "").trimEnd();
      if (!lines[i].trim()) lines.splice(i, 1);
      return lines.join("\n").trimEnd();
    }
    // First non-empty line from the bottom isn't a marker → leave text alone.
    break;
  }
  return text;
}

function _stripMarkers(text: string): string {
  return _stripOptionsMarker(
    text.replace(_PAPERS_BLOCK, "").replace(_ATTACHED_LINE, ""),
  ).trim();
}

const _STATE_LABELS: Record<string, { vi: string; en: string }> = {
  methodology: { vi: "Phương pháp nghiên cứu", en: "Research methodology" },
  design: { vi: "Thiết kế nghiên cứu", en: "Research design" },
  target_sample_size: { vi: "Cỡ mẫu dự kiến", en: "Target sample size" },
  sampling_strategy: { vi: "Chiến lược chọn mẫu", en: "Sampling strategy" },
  mixed_design_type: { vi: "Loại thiết kế", en: "Design type" },
  conceptual_model: { vi: "Mô hình khái niệm", en: "Conceptual model" },
  themes: { vi: "Các chủ đề chính", en: "Key themes" },
  instrument: { vi: "Bảng hỏi nghiên cứu", en: "Research questionnaire" },
  theoretical_foundation: { vi: "Cơ sở lý thuyết", en: "Theoretical foundation" },
  interview_guide: { vi: "Hướng dẫn phỏng vấn", en: "Interview guide" },
  purposive_criteria: { vi: "Tiêu chí chọn mẫu", en: "Sampling criteria" },
  done: { vi: "hoàn tất", en: "complete" },
  needs_review: { vi: "cần xem lại", en: "needs review" },
  in_progress: { vi: "đang thực hiện", en: "in progress" },
  locked: { vi: "chưa bắt đầu", en: "not started" },
};

export function humanizeTechnicalCopy(text: string): string {
  if (!/[À-ỹĐđ]/.test(text)) return text;
  return text
    .replace(/^.*\[PROJECT STATE\].*$/gim, "Trạng thái dự án đã được cập nhật.")
    .replace(/`?focus=M([1-5])\s*\|\s*M\1:in_progress`?/gi, "đang thực hiện M$1")
    .replace(/`?M3\/build_model`?/gi, "bước xây dựng mô hình nghiên cứu")
    .replace(/`?quick_sources`?/gi, "tìm nguồn học thuật")
    .replace(/\bslice\s+M([1-5])\b/gi, "phần M$1")
    .replace(/\bcommit(?:ted|ting)?\b/gi, "lưu")
    .replace(/`(done|needs_review|in_progress|locked)`/gi, (_whole, status: string) =>
      _STATE_LABELS[status]?.vi ?? status)
    .replace(/`([a-z][a-z0-9_]+)`/g, (whole, key: string) => {
      const label = _STATE_LABELS[key]?.vi;
      return label ? `**${label}**` : whole;
    });
}

function _humanizeVisibleStateKeys(text: string): string {
  const locale = /[À-ỹĐđ]/.test(text) ? "vi" : "en";
  return text.replace(/`([a-z][a-z0-9_]+)`/g, (whole, key: string) => {
    const label = _STATE_LABELS[key]?.[locale];
    return label ? `**${label}**` : whole;
  });
}

// The drop-first onboarding sends a `/bootstrap …` message so the agent's
// bootstrap skill fires + knows what to do — but that text is an instruction
// for the AGENT, not the human. Shown raw it reads as a technical command. For
// display, hide the marker + boilerplate and surface the user's own note (the
// part they actually typed); if there's no note, a short friendly line. The
// attached-file chips render below the bubble, so the upload is still obvious.
function _displayUserText(content: string): string {
  if (!content.trimStart().startsWith("/bootstrap")) return content;
  const m = content.match(/My own notes:\s*([\s\S]+)$/i);
  const note = m?.[1]?.trim();
  return note || "Analyze my uploaded materials and tell me where my thesis stands.";
}

function _renderMarkdown(text: string) {
  // remark-math parses `$…$` / `$$…$$`; rehype-katex renders them to HTML.
  // The agent emits regression equations + stats (e.g. `$$\text{YD} = …$$`,
  // `$p < 0.05$`, `$\beta = 0.369$`) — without these they showed as raw LaTeX.
  // KaTeX CSS is loaded globally in app/layout.tsx.
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      // strict:false + a muted errorColor so the occasional bad LaTeX the model
      // emits (e.g. plain text wrapped in \text{} with a raw `&`) degrades to
      // gray source instead of alarming red. The prompt steers the model away
      // from LaTeX-ifying plain prose in the first place.
      rehypePlugins={[[rehypeKatex, { strict: false, throwOnError: false, errorColor: "#9ca3af" }]]}
      components={_markdownComponents}
    >
      {_fixMathText(_normalizeLatexDelimiters(
        _protectCiteUrls(_humanizeVisibleStateKeys(humanizeTechnicalCopy(_stripMarkers(text)))),
      ))}
    </ReactMarkdown>
  );
}


// 2026-06-10 — DoThesis.html design: assistant turns are an avatar + a name
// row ("DoThesis" + serif module chip) above a white card with an asymmetric
// 4/18 radius. Exported as a frame so Streaming/Thinking/Error/Progress
// bubbles share the exact same silhouette and the thinking → streaming →
// final transition doesn't jump.
export function AssistantFrame({
  moduleTag,
  footer,
  children,
  ...rest
}: {
  moduleTag?: string | null;
  /** Slot rendered BELOW the bubble (outside the white card) — used for
   *  the Copy button and any future micro-actions (Regenerate, Pin, etc.). */
  footer?: ReactNode;
  children: ReactNode;
  [key: string]: unknown;
}) {
  return (
    // Claude.ai shape: the assistant does not speak from inside a card. The
    // reply IS the page — no avatar, no border, no shadow, full measure — so
    // long analytical answers read as a document rather than as a chat log of
    // boxed quotes. The only chrome is a quiet label row carrying the module
    // tag, which is real information the reference design has no equivalent of.
    <div data-role="assistant" className="flex flex-col" {...rest}>
      {moduleTag && (
        <div className="flex items-center gap-2 mb-2">
          <span className="px-[7px] py-[2px] rounded-md bg-ink-100 text-ink-600 font-serif font-extrabold text-[11px] tracking-[0.03em]">
            {moduleTag}
          </span>
        </div>
      )}
      {/* Serif body, like the reference: it is what makes multi-paragraph
          reasoning readable at length, and it distinguishes the assistant's
          prose from the UI's sans-serif chrome without needing a container. */}
      <div className="min-w-0 font-serif text-[16.5px] leading-[1.72] text-ink-800">
        {children}
      </div>
      {footer && <div className="block">{footer}</div>}
    </div>
  );
}


/**
 * Parse a trailing `[OPTIONS] …` marker into a card_grid hint, client-side.
 *
 * The server does this too (agent/runtime.py) and persists the result on the
 * message. This is the fallback for every message where it did NOT — most
 * obviously the ones already in the database from before the parser accepted a
 * marker glued to the end of a sentence.
 *
 * Without it, stripping the marker from the text made those turns strictly
 * worse: the raw marker stopped being readable AND no cards appeared, so the
 * options vanished completely. Parsing here means the buttons come back for
 * old messages too, and the client stops depending on when a message happened
 * to be written.
 *
 * Mirrors _parse_options_marker exactly: last non-empty line only, so a marker
 * buried mid-reply is still ignored.
 */
function _optionsHintFrom(content: string): WidgetHint | null {
  const lines = (content || "").trimEnd().split("\n");
  for (let i = lines.length - 1; i >= 0; i--) {
    const line = lines[i].trim();
    if (!line) continue;
    const m = line.match(
      /\[OPTIONS(?:\s*:\s*(\w+))?(\s+multi)?\]\s*(.+)$/,
    );
    if (!m) return null;
    const labels = m[3].split("|").map(s => s.trim()).filter(Boolean);
    if (!labels.length) return null;
    return {
      widget_type: "card_grid",
      field_name: m[1] || "user_choice",
      title: "",
      options: labels.map(l => ({ value: l, label: l })),
      multi_select: Boolean(m[2]),
    } as WidgetHint;
  }
  return null;
}

export type MessageBubbleProps = {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  moduleTag?: string | null;
  // SP3: widget bubble support — when both fields present, render the widget
  // inside the assistant bubble. widgetDisabled prevents clicks once a newer
  // user message has arrived (a "spent" widget shouldn't refire).
  toolCallsJson?: WidgetHint | null;
  onWidgetSelect?: WidgetSelectHandler;
  widgetDisabled?: boolean;
  // Project scope for widgets that call project-scoped endpoints directly
  // (e.g. reconstructed_modules → /mid-journey-import/confirm).
  projectId?: string;
  // Per-response cost + latency, shown in the assistant footer next to Copy.
  costCredits?: number;
  durationMs?: number;
  children?: ReactNode;
};


export function MessageBubble({
  role,
  content,
  moduleTag,
  toolCallsJson,
  onWidgetSelect,
  widgetDisabled,
  projectId,
  costCredits,
  durationMs,
  children,
}: MessageBubbleProps) {
  const isUser = role === "user";
  const isSystem = role === "system";

  if (isUser) {
    // tool_calls_json on user rows is reused as the attachments payload
    // (chat_v3.send_message_v3). Detect the shape and render chips so the
    // bubble shows which files were linked to this message after reload.
    const attachments =
      toolCallsJson && "attachments" in toolCallsJson
        ? toolCallsJson.attachments
        : null;
    return (
      <div data-role={role} className="flex justify-end">
        <div className="max-w-[70%] flex flex-col items-end gap-1.5">
          {/* Muted, not saturated. A solid primary-600 block is the loudest
              thing on the screen, and it is the one message whose content the
              reader already knows — they wrote it. Grey keeps it findable as a
              turn boundary without competing with the answer below it. */}
          <div className="rounded-[18px] bg-ink-100 text-ink-900 px-4 py-[11px] text-[15px] leading-normal">
            <div className="prose-tight text-[15px]">{_renderMarkdown(_displayUserText(content))}</div>
            {children}
          </div>
          {attachments && attachments.length > 0 && (
            <div className="flex flex-wrap justify-end gap-1.5">
              {attachments.map(a => (
                <UserAttachmentChip key={a.upload_id} meta={a} />
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  if (isSystem) {
    return (
      <div data-role={role} className="flex justify-start">
        <div className="max-w-[70%] rounded-lg bg-ink-100 text-ink-500 px-3 py-1 text-sm italic">
          <div className="prose-tight text-[14.5px]">{_renderMarkdown(content)}</div>
          {children}
        </div>
      </div>
    );
  }

  return (
    <AssistantFrame
      moduleTag={moduleTag}
      footer={
        // mt-1.5 lives on the row (not on CopyButton) so Copy and the
        // credits/duration meta share one baseline — a top margin on only
        // one child pushed it out of vertical alignment with the other.
        <div className="mt-1.5 flex items-center gap-3">
          <CopyButton text={content} />
          <ResponseMeta costCredits={costCredits} durationMs={durationMs} />
        </div>
      }
    >
      {/* No size override — inherit the frame's serif measure. */}
      <div className="prose-tight">{_renderMarkdown(content)}</div>
      {/* Fall back to parsing the marker out of the text when the message
          carries no widget — see _optionsHintFrom. */}
      {(toolCallsJson ?? _optionsHintFrom(content)) && onWidgetSelect && (
        <WidgetRenderer
          hint={(toolCallsJson ?? _optionsHintFrom(content))!}
          onSelect={onWidgetSelect}
          disabled={widgetDisabled}
          projectId={projectId}
        />
      )}
      {children}
    </AssistantFrame>
  );
}

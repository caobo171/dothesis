import { ReactNode, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy, FileText } from "lucide-react";
import { Mermaid } from "./Mermaid";
import { WidgetRenderer } from "./widgets/WidgetRenderer";
import type {
  AttachmentChipMeta,
  WidgetHint,
  WidgetSelectHandler,
} from "./widgets/types";


// Compact chip rendered under a user bubble when the message had files
// attached. Read-only display — no remove / re-upload affordance here
// (that lives in the composer chip row).
function UserAttachmentChip({ meta }: { meta: AttachmentChipMeta }) {
  const size =
    typeof meta.size_bytes === "number"
      ? _formatBytes(meta.size_bytes)
      : null;
  return (
    <span
      className="inline-flex items-center gap-1.5 max-w-[260px] rounded-lg border border-ink-200 bg-white px-2 py-1 text-[11.5px] text-ink-700 shadow-[0_1px_0_rgba(11,13,26,.04)]"
      title={meta.filename}
    >
      <FileText className="w-3.5 h-3.5 text-ink-500 shrink-0" aria-hidden />
      <span className="truncate">{meta.filename}</span>
      {size && <span className="text-ink-400 shrink-0">· {size}</span>}
    </span>
  );
}

function _formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
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
      className="mt-1.5 inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-[11.5px] text-ink-500 hover:bg-ink-100 hover:text-ink-700 transition-colors w-[78px] justify-start"
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
            ? "list-none pl-0 my-2 space-y-1.5"
            : "list-disc pl-5 my-1 space-y-0.5"
        }
      >
        {children}
      </ul>
    );
  },
  ol: ({ children }: { children?: ReactNode }) => (
    <ol className="list-decimal pl-5 my-1 space-y-0.5">{children}</ol>
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
    return <li className="leading-snug">{children}</li>;
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
  // Paragraph spacing — defaults are too generous inside a bubble.
  p: ({ children }: { children?: ReactNode }) => (
    <p className="my-1 leading-snug">{children}</p>
  ),
  // Headings inside a bubble look weird at h1/h2 sizes; downsize.
  h1: ({ children }: { children?: ReactNode }) => (
    <div className="font-semibold text-[15px] my-1.5">{children}</div>
  ),
  h2: ({ children }: { children?: ReactNode }) => (
    <div className="font-semibold text-[14.5px] my-1.5">{children}</div>
  ),
  h3: ({ children }: { children?: ReactNode }) => (
    <div className="font-semibold text-[14px] my-1">{children}</div>
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
    <pre className="my-1 rounded bg-ink-50 p-2 text-[13px] overflow-x-auto">{children}</pre>
  ),
  // Links — same blue underline as before.
  a: ({ href, children }: { href?: string; children?: ReactNode }) => (
    <a
      href={href}
      className="underline text-primary-600 hover:text-primary-700"
      target="_blank"
      rel="noreferrer noopener"
    >
      {children}
    </a>
  ),
  // Tables (GFM) — basic styling.
  table: ({ children }: { children?: ReactNode }) => (
    <table className="my-1.5 border-collapse text-[13.5px]">{children}</table>
  ),
  th: ({ children }: { children?: ReactNode }) => (
    // Header cells get whitespace-nowrap because they're typically labels
    // like "Phát biểu" / "1" / "2" / … that should never wrap.
    <th className="border border-ink-200 px-2 py-1 text-left bg-ink-50 font-semibold whitespace-nowrap">{children}</th>
  ),
  td: ({ children }: { children?: ReactNode }) => (
    // Don't break `[ ]`, `[x]`, or single tokens across lines — they're
    // common in Likert-scale tables the agent emits and break cell layout.
    // Statement cells (the leftmost column) wrap normally because they
    // hold long prose; the `[&:not(:first-child)]:whitespace-nowrap`
    // selector keeps that column wrappable while clamping the rating
    // columns.
    <td className="border border-ink-200 px-2 py-1 align-top [&:not(:first-child)]:whitespace-nowrap [&:not(:first-child)]:text-center">{children}</td>
  ),
  // Blockquote — soft left rail.
  blockquote: ({ children }: { children?: ReactNode }) => (
    <blockquote className="my-1 border-l-2 border-ink-200 pl-2 text-ink-600">{children}</blockquote>
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

function _renderMarkdown(text: string) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={_markdownComponents}>
      {_stripMarkers(text)}
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
    <div data-role="assistant" className="flex items-start gap-3" {...rest}>
      <span
        aria-hidden
        className="w-[34px] h-[34px] min-w-[34px] rounded-[10px] inline-flex items-center justify-center text-white font-extrabold font-serif text-[15px] mt-[22px] shadow-[0_4px_12px_rgba(28,46,255,.22)]"
        style={{ background: "linear-gradient(135deg, #1c2eff 0%, #5b3aa8 100%)" }}
      >
        D
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="text-[13px] font-bold text-ink-900">DoThesis</span>
          {moduleTag && (
            <span className="px-[7px] py-[2px] rounded-md bg-primary-50 text-primary-700 font-serif font-extrabold text-[11px] tracking-[0.03em]">
              {moduleTag}
            </span>
          )}
          <span className="text-[11.5px] text-ink-400 ml-auto">just now</span>
        </div>
        <div className="max-w-[92%] inline-block min-w-0 overflow-hidden bg-white border border-ink-200 rounded-[18px] rounded-tl-[4px] px-[18px] py-3.5 text-[14.5px] leading-relaxed text-ink-800 shadow-[0_1px_3px_rgba(11,16,32,.04),0_2px_8px_rgba(11,16,32,.04)]">
          {children}
        </div>
        {footer && (
          // Block wrapper forces footer onto a new line — otherwise a small
          // bubble (`inline-block`) leaves the Copy button sitting next to
          // it on the same row instead of below.
          <div className="block">{footer}</div>
        )}
      </div>
    </div>
  );
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
          <div className="rounded-[18px] rounded-br-[4px] bg-primary-600 text-white px-4 py-[11px] text-[14.5px] leading-normal shadow-[0_1px_0_rgba(11,13,26,.04)]">
            <div className="prose-tight text-[14.5px]">{_renderMarkdown(content)}</div>
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
        <div className="flex items-center gap-3">
          <CopyButton text={content} />
          <ResponseMeta costCredits={costCredits} durationMs={durationMs} />
        </div>
      }
    >
      <div className="prose-tight text-[14.5px]">{_renderMarkdown(content)}</div>
      {toolCallsJson && onWidgetSelect && (
        <WidgetRenderer
          hint={toolCallsJson}
          onSelect={onWidgetSelect}
          disabled={widgetDisabled}
        />
      )}
      {children}
    </AssistantFrame>
  );
}

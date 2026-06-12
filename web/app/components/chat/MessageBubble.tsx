import { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Mermaid } from "./Mermaid";
import { WidgetRenderer } from "./widgets/WidgetRenderer";
import type { WidgetHint, WidgetSelectHandler } from "./widgets/types";

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
  ul: ({ children }: { children?: ReactNode }) => (
    <ul className="list-disc pl-5 my-1 space-y-0.5">{children}</ul>
  ),
  ol: ({ children }: { children?: ReactNode }) => (
    <ol className="list-decimal pl-5 my-1 space-y-0.5">{children}</ol>
  ),
  li: ({ children }: { children?: ReactNode }) => (
    <li className="leading-snug">{children}</li>
  ),
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
  return _stripOptionsMarker(text.replace(_PAPERS_BLOCK, "")).trim();
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
  children,
  ...rest
}: {
  moduleTag?: string | null;
  children: ReactNode;
  [key: string]: unknown;
}) {
  return (
    <div data-role="assistant" className="flex items-start gap-3 py-3" {...rest}>
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
        </div>
        <div className="max-w-[85%] inline-block min-w-0 overflow-hidden bg-white border border-ink-200 rounded-[18px] rounded-tl-[4px] px-[18px] py-3.5 text-[14.5px] leading-relaxed text-ink-800 shadow-[var(--shadow-card)]">
          {children}
        </div>
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
  children?: ReactNode;
};


export function MessageBubble({
  role,
  content,
  moduleTag,
  toolCallsJson,
  onWidgetSelect,
  widgetDisabled,
  children,
}: MessageBubbleProps) {
  const isUser = role === "user";
  const isSystem = role === "system";

  if (isUser) {
    return (
      <div data-role={role} className="flex justify-end py-3">
        <div className="max-w-[70%] rounded-[18px] rounded-br-[4px] bg-primary-600 text-white px-4 py-[11px] text-[14.5px] leading-normal shadow-[0_1px_0_rgba(11,13,26,.04)]">
          <div className="prose-tight text-[14.5px]">{_renderMarkdown(content)}</div>
          {children}
        </div>
      </div>
    );
  }

  if (isSystem) {
    return (
      <div data-role={role} className="flex justify-start py-1.5">
        <div className="max-w-[70%] rounded-lg bg-ink-100 text-ink-500 px-3 py-1 text-sm italic">
          <div className="prose-tight text-[14.5px]">{_renderMarkdown(content)}</div>
          {children}
        </div>
      </div>
    );
  }

  return (
    <AssistantFrame moduleTag={moduleTag}>
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

"use client";

import { Table, TableCell, TableHeader, TableRow } from "@tiptap/extension-table";
import { EditorContent, useEditor, type Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useEffect, useRef, useState } from "react";
import { Markdown } from "tiptap-markdown";

/**
 * The post body: a WYSIWYG canvas and the markdown source, over ONE string.
 *
 * `value` and `onChange` speak markdown in both modes, so the tabs are
 * interchangeable and the form above does not know which one is open. The
 * stack is the one ChapterEditor already uses and the repo already tests —
 * StarterKit + tiptap-markdown with `html: false`, plus the table nodes, which
 * serialize to GFM pipe tables (see __tests__/markdown-roundtrip.test.ts).
 * Nothing new was added to package.json for this.
 *
 * `html: false` is the reason RAW HTML IS A TRAP here. The public renderer runs
 * rehypeRaw, so a body legitimately MAY contain HTML — and a round trip through
 * the rich canvas would silently drop it. So a body with raw HTML in it opens
 * in Source and says why, rather than offering a canvas that quietly eats part
 * of the post. Same call WELE's LegacyHtmlNotice makes.
 */

/** Tags we would lose. Deliberately not a general HTML parse: `<` appears in
 *  prose ("p < 0.05", "<br>" inside a code fence), and a false positive here
 *  only costs the author the rich tab, while a false negative costs content. */
const HTML_TAG = /<(?:div|span|table|tr|td|th|img|iframe|figure|figcaption|section|details|summary|br|a|p|ul|ol|li|strong|em|h[1-6])\b[^>]*>/i;

export function bodyHasRawHtml(markdown: string): boolean {
  // Fenced and indented code blocks are rendered as code, not parsed as HTML,
  // so tags inside them are not at risk and must not lock the author out.
  const withoutFences = markdown.replace(/```[\s\S]*?```/g, "").replace(/`[^`\n]*`/g, "");
  return HTML_TAG.test(withoutFences);
}

const EXTENSIONS = [
  StarterKit,
  Markdown.configure({ html: false }),
  Table.configure({ resizable: true }),
  TableRow,
  TableHeader,
  TableCell,
];

export function BodyEditor({
  value,
  onChange,
}: {
  value: string;
  onChange: (markdown: string) => void;
}) {
  const hasHtml = bodyHasRawHtml(value);
  const [mode, setMode] = useState<"rich" | "source">("rich");
  // What WE last handed upward. The parent echoes it straight back as `value`,
  // and re-seeding the canvas from our own echo would reset the caret on every
  // keystroke.
  const lastEmitted = useRef(value);

  const editor = useEditor({
    extensions: EXTENSIONS,
    content: value,
    immediatelyRender: false,
    editorProps: {
      attributes: { class: "editor-prose max-w-none min-h-[420px] focus:outline-none" },
    },
    onUpdate({ editor }) {
      const md = editor.storage.markdown.getMarkdown();
      lastEmitted.current = md;
      onChange(md);
    },
  });

  // Seed the canvas when the value arrives from somewhere else — the post
  // loading, or an edit made in the Source tab. `emitUpdate: false` so
  // re-seeding is not itself reported as an author edit, which would mark the
  // post dirty (and reformat it) just for being opened.
  useEffect(() => {
    if (!editor || mode !== "rich") return;
    if (value === lastEmitted.current) return;
    editor.commands.setContent(value, { emitUpdate: false });
    lastEmitted.current = value;
  }, [editor, value, mode]);

  // An author who opens a post with HTML in it should land where nothing is
  // lost. Checked against the loaded value rather than once at mount, because
  // the body arrives after the first render on the edit route.
  useEffect(() => {
    if (hasHtml) setMode("source");
  }, [hasHtml]);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[12px] font-semibold uppercase tracking-wide text-ink-500">
          Body
        </span>
        <div className="flex rounded-lg border border-ink-200 p-0.5">
          {(["rich", "source"] as const).map((m) => (
            <button
              key={m}
              type="button"
              disabled={m === "rich" && hasHtml}
              onClick={() => setMode(m)}
              title={m === "rich" && hasHtml
                ? "This post contains raw HTML, which the rich editor would drop."
                : undefined}
              className={`rounded-md px-3 py-1 text-sm font-semibold capitalize ${
                mode === m ? "bg-ink-900 text-white" : "text-ink-600 hover:bg-ink-50"
              } disabled:cursor-not-allowed disabled:opacity-40`}
            >
              {m === "rich" ? "Rich text" : "Markdown"}
            </button>
          ))}
        </div>
      </div>

      {hasHtml && (
        <p className="rounded-lg border border-[#E6D8BC] bg-[#FBF3E3] px-3 py-2 text-[12.5px] text-[#8E6B2A]">
          This post contains raw HTML. The rich editor stores clean markdown and
          would drop it, so it is editable as markdown only. Remove the HTML to
          unlock the rich editor.
        </p>
      )}

      {mode === "rich" && editor ? (
        <div className="rounded-lg border border-ink-200">
          <Toolbar editor={editor} />
          <div className="px-3 py-2">
            <EditorContent editor={editor} />
          </div>
        </div>
      ) : (
        <textarea
          className="w-full rounded-lg border border-ink-200 px-3 py-2 font-mono text-[13px] leading-relaxed text-ink-900 focus:border-primary-400 focus:outline-none"
          rows={28}
          value={value}
          onChange={(e) => {
            lastEmitted.current = e.target.value;
            onChange(e.target.value);
          }}
        />
      )}
    </div>
  );
}

/** Only what a blog body is actually made of. Anything markdown cannot express
 *  is deliberately absent — a button that writes a mark the serializer drops on
 *  save is a button that loses the author's work. */
function Toolbar({ editor }: { editor: Editor }) {
  const btn = (active: boolean) =>
    `rounded px-2 py-1 text-[12.5px] font-semibold ${
      active ? "bg-ink-900 text-white" : "text-ink-600 hover:bg-ink-100"
    }`;

  return (
    <div className="flex flex-wrap items-center gap-1 border-b border-ink-200 px-2 py-1.5">
      {[2, 3, 4].map((level) => (
        <button key={level} type="button"
                className={btn(editor.isActive("heading", { level }))}
                onClick={() => editor.chain().focus()
                  .toggleHeading({ level: level as 2 | 3 | 4 }).run()}>
          H{level}
        </button>
      ))}
      <Divider />
      <button type="button" className={btn(editor.isActive("bold"))}
              onClick={() => editor.chain().focus().toggleBold().run()}>
        <strong>B</strong>
      </button>
      <button type="button" className={btn(editor.isActive("italic"))}
              onClick={() => editor.chain().focus().toggleItalic().run()}>
        <em>I</em>
      </button>
      <button type="button" className={btn(editor.isActive("code"))}
              onClick={() => editor.chain().focus().toggleCode().run()}>
        {"</>"}
      </button>
      <Divider />
      <button type="button" className={btn(editor.isActive("bulletList"))}
              onClick={() => editor.chain().focus().toggleBulletList().run()}>
        • List
      </button>
      <button type="button" className={btn(editor.isActive("orderedList"))}
              onClick={() => editor.chain().focus().toggleOrderedList().run()}>
        1. List
      </button>
      <button type="button" className={btn(editor.isActive("blockquote"))}
              onClick={() => editor.chain().focus().toggleBlockquote().run()}>
        Quote
      </button>
      <Divider />
      <button type="button" className={btn(editor.isActive("link"))}
              onClick={() => {
                const previous = editor.getAttributes("link").href as string | undefined;
                const href = window.prompt("Link URL", previous ?? "");
                if (href === null) return;
                if (href === "") {
                  editor.chain().focus().unsetLink().run();
                  return;
                }
                editor.chain().focus().extendMarkRange("link")
                  .setLink({ href }).run();
              }}>
        Link
      </button>
      <button type="button" className={btn(false)}
              onClick={() => editor.chain().focus()
                .insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()}>
        Table
      </button>
      <button type="button" className={btn(false)}
              onClick={() => editor.chain().focus().setHorizontalRule().run()}>
        ―
      </button>
    </div>
  );
}

function Divider() {
  return <span className="mx-1 h-4 w-px bg-ink-200" aria-hidden />;
}

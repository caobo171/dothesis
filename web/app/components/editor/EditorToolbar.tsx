"use client";

import { useEditorState, type Editor } from "@tiptap/react";
import {
  Undo2, Redo2, Bold, Italic, Strikethrough,
  List, ListOrdered, Quote, Minus, Plus, Table as TableIcon, Workflow,
} from "lucide-react";


// Fonts a Vietnamese thesis is actually submitted in — Times New Roman is the
// faculty default, the rest cover the common house styles. Kept as a display
// setting (see ChapterEditor) rather than an inline mark: the chapter is stored
// as clean markdown (html:false) so a per-range font mark would be dropped on
// the very next autosave. A whole-document font matches how a thesis is styled
// anyway, so we apply it to the editor container instead.
export const FONT_FAMILIES = [
  { label: "Times New Roman", value: '"Times New Roman", Times, serif' },
  { label: "Arial", value: "Arial, Helvetica, sans-serif" },
  { label: "Cambria", value: "Cambria, Georgia, serif" },
  { label: "Georgia", value: "Georgia, serif" },
  { label: "Calibri", value: "Calibri, Candara, sans-serif" },
];

const MIN_SIZE = 8;
const MAX_SIZE = 72;

// The "Văn bản" (text-style) dropdown. Only headings the markdown serializer
// round-trips (# / ## / ###) plus the default paragraph — nothing here can be
// silently lost on save.
const TEXT_STYLES = [
  { label: "Văn bản", value: "paragraph" },
  { label: "Tiêu đề 1", value: "h1" },
  { label: "Tiêu đề 2", value: "h2" },
  { label: "Tiêu đề 3", value: "h3" },
] as const;


type Props = {
  editor: Editor;
  fontFamily: string;
  fontSize: number;
  onFontFamily: (v: string) => void;
  onFontSize: (n: number) => void;
};


// Persistent formatting bar above the chapter body — the Word-like surface the
// design calls for. Every control here maps to an editor command or a display
// setting that survives autosave; nothing renders a control it can't back up
// (no underline/align/table, which the markdown store would drop). See
// [[feedback_tool_naming_competitor_parity]] — don't show a button that lies.
export function EditorToolbar({ editor, fontFamily, fontSize, onFontFamily, onFontSize }: Props) {
  // Subscribe to just the flags the toolbar paints, so a keystroke that flips
  // bold on/off re-renders the bar without re-rendering the whole editor.
  const state = useEditorState({
    editor,
    selector: ({ editor }) => ({
      bold: editor.isActive("bold"),
      italic: editor.isActive("italic"),
      strike: editor.isActive("strike"),
      bulletList: editor.isActive("bulletList"),
      orderedList: editor.isActive("orderedList"),
      blockquote: editor.isActive("blockquote"),
      canUndo: editor.can().undo(),
      canRedo: editor.can().redo(),
      textStyle: editor.isActive("heading", { level: 1 })
        ? "h1"
        : editor.isActive("heading", { level: 2 })
          ? "h2"
          : editor.isActive("heading", { level: 3 })
            ? "h3"
            : "paragraph",
      // getText() joins block text with "\n"; splitting on whitespace gives a
      // good-enough word count for the header readout (matches the mock's "N từ").
      words: editor.getText().trim().split(/\s+/).filter(Boolean).length,
    }),
  });

  const applyTextStyle = (value: string) => {
    const chain = editor.chain().focus();
    if (value === "paragraph") {
      chain.setParagraph().run();
    } else {
      const level = Number(value.slice(1)) as 1 | 2 | 3;
      chain.toggleHeading({ level }).run();
    }
  };

  const clampSize = (n: number) => Math.max(MIN_SIZE, Math.min(MAX_SIZE, n));

  return (
    <div
      role="toolbar"
      aria-label="Định dạng"
      className="flex flex-wrap items-center gap-1 border-b border-ink-200 bg-white px-3 py-1.5"
    >
      {/* Undo / redo */}
      <ToolbarButton
        label="Hoàn tác"
        disabled={!state?.canUndo}
        onClick={() => editor.chain().focus().undo().run()}
      >
        <Undo2 className="w-4 h-4" />
      </ToolbarButton>
      <ToolbarButton
        label="Làm lại"
        disabled={!state?.canRedo}
        onClick={() => editor.chain().focus().redo().run()}
      >
        <Redo2 className="w-4 h-4" />
      </ToolbarButton>

      <Divider />

      {/* Font family (document display setting) */}
      <select
        aria-label="Phông chữ"
        value={fontFamily}
        onChange={e => onFontFamily(e.target.value)}
        className="h-8 rounded-md border border-ink-200 bg-white px-2 text-sm text-ink-800 hover:bg-ink-50 focus:outline-none focus:ring-1 focus:ring-primary-500"
      >
        {FONT_FAMILIES.map(f => (
          <option key={f.value} value={f.value} style={{ fontFamily: f.value }}>
            {f.label}
          </option>
        ))}
      </select>

      <Divider />

      {/* Font size stepper (document display setting) */}
      <ToolbarButton label="Giảm cỡ chữ" onClick={() => onFontSize(clampSize(fontSize - 1))}>
        <Minus className="w-4 h-4" />
      </ToolbarButton>
      <input
        aria-label="Cỡ chữ"
        type="number"
        min={MIN_SIZE}
        max={MAX_SIZE}
        value={fontSize}
        onChange={e => {
          const n = Number(e.target.value);
          if (Number.isFinite(n)) onFontSize(clampSize(n));
        }}
        className="h-8 w-12 rounded-md border border-ink-200 bg-white px-1 text-center text-sm text-ink-800 focus:outline-none focus:ring-1 focus:ring-primary-500 tabular-nums"
      />
      <ToolbarButton label="Tăng cỡ chữ" onClick={() => onFontSize(clampSize(fontSize + 1))}>
        <Plus className="w-4 h-4" />
      </ToolbarButton>

      <Divider />

      {/* Text style */}
      <select
        aria-label="Kiểu văn bản"
        value={state?.textStyle ?? "paragraph"}
        onChange={e => applyTextStyle(e.target.value)}
        className="h-8 rounded-md border border-ink-200 bg-white px-2 text-sm text-ink-800 hover:bg-ink-50 focus:outline-none focus:ring-1 focus:ring-primary-500"
      >
        {TEXT_STYLES.map(s => (
          <option key={s.value} value={s.value}>{s.label}</option>
        ))}
      </select>

      <Divider />

      {/* Inline marks — only the three the markdown store round-trips. */}
      <ToolbarButton label="Đậm" active={state?.bold} onClick={() => editor.chain().focus().toggleBold().run()}>
        <Bold className="w-4 h-4" />
      </ToolbarButton>
      <ToolbarButton label="Nghiêng" active={state?.italic} onClick={() => editor.chain().focus().toggleItalic().run()}>
        <Italic className="w-4 h-4" />
      </ToolbarButton>
      <ToolbarButton label="Gạch ngang" active={state?.strike} onClick={() => editor.chain().focus().toggleStrike().run()}>
        <Strikethrough className="w-4 h-4" />
      </ToolbarButton>

      <Divider />

      {/* Lists + quote */}
      <ToolbarButton label="Danh sách" active={state?.bulletList} onClick={() => editor.chain().focus().toggleBulletList().run()}>
        <List className="w-4 h-4" />
      </ToolbarButton>
      <ToolbarButton label="Danh sách đánh số" active={state?.orderedList} onClick={() => editor.chain().focus().toggleOrderedList().run()}>
        <ListOrdered className="w-4 h-4" />
      </ToolbarButton>
      <ToolbarButton label="Trích dẫn" active={state?.blockquote} onClick={() => editor.chain().focus().toggleBlockquote().run()}>
        <Quote className="w-4 h-4" />
      </ToolbarButton>

      <Divider />

      {/* Insert a 3×3 GFM table (header row + 2 body rows). Round-trips to
          markdown and renders in the export. */}
      <ToolbarButton
        label="Chèn bảng"
        onClick={() => editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()}
      >
        <TableIcon className="w-4 h-4" />
      </ToolbarButton>

      {/* Insert a mermaid diagram — a ```mermaid fenced block with a starter
          graph, rendered live below its source. */}
      <ToolbarButton
        label="Chèn sơ đồ"
        onClick={() =>
          editor.chain().focus().insertContent({
            type: "codeBlock",
            attrs: { language: "mermaid" },
            content: [{ type: "text", text: "graph TD;\n  A[Bắt đầu] --> B[Kết thúc];" }],
          }).run()
        }
      >
        <Workflow className="w-4 h-4" />
      </ToolbarButton>

      {/* Word count — pushed to the far right like the mock's "N từ". */}
      <span className="ml-auto text-xs text-ink-400 tabular-nums" aria-label="Số từ">
        {state?.words ?? 0} từ
      </span>
    </div>
  );
}


function Divider() {
  return <span className="mx-1 h-5 w-px bg-ink-200" aria-hidden="true" />;
}


function ToolbarButton({
  children, label, onClick, active, disabled,
}: {
  children: React.ReactNode;
  label: string;
  onClick: () => void;
  active?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={active}
      disabled={disabled}
      onClick={onClick}
      className={
        "inline-flex h-8 w-8 items-center justify-center rounded-md transition-colors " +
        (disabled
          ? "text-ink-300 cursor-not-allowed"
          : active
            ? "bg-primary-100 text-primary-700"
            : "text-ink-600 hover:bg-ink-100")
      }
    >
      {children}
    </button>
  );
}

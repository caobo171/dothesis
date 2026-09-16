"use client";

import { useEditorState, type Editor } from "@tiptap/react";
import { Listbox, ListboxButton, ListboxOption, ListboxOptions } from "@headlessui/react";
import {
  Undo2, Redo2, Bold, Italic, Strikethrough,
  List, ListOrdered, Quote, Minus, Plus, Table as TableIcon, Workflow,
  Check, ChevronDown, Code2, Heading1, Heading2, Heading3, Heading4, Pilcrow,
} from "lucide-react";
import { Select } from "@/app/components/ui/select";


// Fonts a Vietnamese thesis is actually submitted in — Times New Roman is the
// faculty default, the rest cover the common house styles. Kept as a display
// setting (see ChapterEditor) rather than an inline mark: the chapter is stored
// as clean markdown (html:false) so a per-range font mark would be dropped on
// the very next save. A whole-document font matches how a thesis is styled
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

const BLOCK_TYPES = [
  { label: "Văn bản", value: "paragraph", Icon: Pilcrow },
  { label: "Tiêu đề 1", value: "h1", Icon: Heading1 },
  { label: "Tiêu đề 2", value: "h2", Icon: Heading2 },
  { label: "Tiêu đề 3", value: "h3", Icon: Heading3 },
  { label: "Tiêu đề 4", value: "h4", Icon: Heading4 },
  { label: "Danh sách đánh số", value: "orderedList", Icon: ListOrdered },
  { label: "Danh sách dấu đầu dòng", value: "bulletList", Icon: List },
  { label: "Khối mã", value: "codeBlock", Icon: Code2 },
  { label: "Bảng", value: "table", Icon: TableIcon },
  { label: "Trích dẫn khối", value: "blockquote", Icon: Quote },
] as const;


// Line height + paragraph gap, as named presets. 1.5 and double are what a
// Vietnamese thesis template asks for; "Thoáng" is the middle ground most
// students were reaching for when they pressed Enter twice.
export const SPACING = [
  { label: "Gọn", lineHeight: 1.5, paraGap: 10 },
  { label: "Vừa", lineHeight: 1.75, paraGap: 14 },
  { label: "Rất thoáng", lineHeight: 2.4, paraGap: 32 },
];


type Props = {
  editor: Editor;
  fontFamily: string;
  fontSize: number;
  onFontFamily: (v: string) => void;
  onFontSize: (n: number) => void;
  /** Line height and the gap between paragraphs, as ONE choice. Spacing has to
   *  live here rather than in the document: markdown cannot store a blank line,
   *  so pressing Enter for air between paragraphs serialised to nothing and
   *  could never be saved. */
  lineHeight: number;
  paraGap: number;
  onSpacing: (lineHeight: number, paraGap: number) => void;
};


// Persistent formatting bar above the chapter body — the Word-like surface the
// design calls for. Every control here maps to an editor command or a display
// setting that survives a save; nothing renders a control it can't back up
// (no underline/align/table, which the markdown store would drop). See
// [[feedback_tool_naming_competitor_parity]] — don't show a button that lies.
export function EditorToolbar({
  editor, fontFamily, fontSize, onFontFamily, onFontSize,
  lineHeight, paraGap, onSpacing,
}: Props) {
  // Subscribe to just the flags the toolbar paints, so a keystroke that flips
  // bold on/off re-renders the bar without re-rendering the whole editor.
  const state = useEditorState({
    editor,
    selector: ({ editor }) => {
      // A chapter TipTap instance can be replaced during SWR refresh/HMR. The
      // toolbar subscription briefly receives a null/destroyed editor in that
      // hand-off; treating it as an idle toolbar prevents editor mode itself
      // from crashing while the next active chapter registers.
      if (!editor || editor.isDestroyed) return {
        bold: false, italic: false, strike: false, bulletList: false,
        orderedList: false, blockquote: false, canUndo: false, canRedo: false,
        textStyle: "paragraph", words: 0,
      };
      return ({
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
            : editor.isActive("heading", { level: 4 })
              ? "h4"
              : editor.isActive("orderedList")
                ? "orderedList"
                : editor.isActive("bulletList")
                  ? "bulletList"
                  : editor.isActive("codeBlock")
                    ? "codeBlock"
                    : editor.isActive("table")
                      ? "table"
                      : editor.isActive("blockquote")
                        ? "blockquote"
                        : "paragraph",
      // getText() joins block text with "\n"; splitting on whitespace gives a
      // good-enough word count for the header readout (matches the mock's "N từ").
      words: editor.getText().trim().split(/\s+/).filter(Boolean).length,
      });
    },
  });

  const applyTextStyle = (value: string) => {
    const chain = editor.chain().focus();
    if (value === "paragraph") chain.setParagraph().run();
    else if (/^h[1-4]$/.test(value)) {
      chain.toggleHeading({ level: Number(value.slice(1)) as 1 | 2 | 3 | 4 }).run();
    } else if (value === "orderedList") chain.toggleOrderedList().run();
    else if (value === "bulletList") chain.toggleBulletList().run();
    else if (value === "codeBlock") chain.toggleCodeBlock().run();
    else if (value === "blockquote") chain.toggleBlockquote().run();
    else if (value === "table") chain.insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run();
  };

  const clampSize = (n: number) => Math.max(MIN_SIZE, Math.min(MAX_SIZE, n));

  return (
    <div
      role="toolbar"
      aria-label="Định dạng"
      className="z-10 flex min-h-[48px] flex-wrap items-center gap-1 border-b border-ink-100 bg-white/95 px-4 py-2 shadow-[0_1px_0_rgba(24,31,50,0.03)] backdrop-blur"
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
      <Select
        ariaLabel="Phông chữ"
        value={fontFamily}
        onValueChange={onFontFamily}
        options={FONT_FAMILIES}
        size="sm"
        className="w-44 [&_button]:h-8 [&_button]:border-ink-200 [&_button]:shadow-none"
      />

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
        className="h-8 w-12 rounded-lg border border-ink-200 bg-white px-1 text-center text-sm text-ink-800 focus:outline-none focus:ring-2 focus:ring-primary-100 tabular-nums"
      />
      <ToolbarButton label="Tăng cỡ chữ" onClick={() => onFontSize(clampSize(fontSize + 1))}>
        <Plus className="w-4 h-4" />
      </ToolbarButton>

      {/* Spacing presets rather than two number boxes: the choice a student is
          making is "tighter" or "airier", and a thesis template usually names
          exactly these. */}
      <Select
        ariaLabel="Giãn dòng"
        value={String(SPACING.findIndex(o => o.lineHeight === lineHeight && o.paraGap === paraGap))}
        onValueChange={value => {
          const o = SPACING[Number(value)];
          if (o) onSpacing(o.lineHeight, o.paraGap);
        }}
        options={SPACING.map((option, index) => ({ value: String(index), label: option.label }))}
        size="sm"
        className="w-32 [&_button]:h-8 [&_button]:border-ink-200 [&_button]:shadow-none"
      />

      <Divider />

      {/* Text style */}
      <BlockTypeMenu value={state?.textStyle ?? "paragraph"} onChange={applyTextStyle} />

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

function BlockTypeMenu({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const current = BLOCK_TYPES.find(type => type.value === value) ?? BLOCK_TYPES[0];
  const CurrentIcon = current.Icon;
  return (
    <Listbox value={value} onChange={onChange}>
      <div className="relative w-40">
        <ListboxButton aria-label="Kiểu văn bản"
          className="flex h-8 w-full items-center gap-2 rounded-lg border border-ink-200 bg-white px-2.5 text-left text-sm text-ink-800 transition hover:bg-ink-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-100">
          <CurrentIcon className="h-4 w-4 shrink-0 text-ink-500" aria-hidden />
          <span className="min-w-0 flex-1 truncate">{current.label}</span>
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-ink-400" aria-hidden />
        </ListboxButton>
        <ListboxOptions anchor="bottom start" transition
          className="z-50 mt-1 w-64 origin-top overflow-hidden rounded-xl border border-ink-100 bg-white p-1.5 shadow-[0_18px_48px_rgba(24,31,50,0.18)] transition duration-150 ease-out data-[closed]:-translate-y-1 data-[closed]:scale-[0.98] data-[closed]:opacity-0">
          {BLOCK_TYPES.map(type => {
            const Icon = type.Icon;
            return (
              <ListboxOption key={type.value} value={type.value}
                className="group flex cursor-default select-none items-center gap-3 rounded-lg px-2.5 py-2 text-sm text-ink-800 transition-colors data-[focus]:bg-primary-50 data-[selected]:font-semibold data-[selected]:text-primary-700">
                <Icon className="h-4 w-4 shrink-0 text-ink-500 group-data-[selected]:text-primary-600" aria-hidden />
                <span className="flex-1">{type.label}</span>
                <Check className="h-4 w-4 text-primary-600 opacity-0 group-data-[selected]:opacity-100" aria-hidden />
              </ListboxOption>
            );
          })}
        </ListboxOptions>
      </div>
    </Listbox>
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
        "inline-flex h-8 w-8 items-center justify-center rounded-lg transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-200 " +
        (disabled
          ? "text-ink-300 cursor-not-allowed"
          : active
            ? "bg-primary-100 text-primary-700"
            : "text-ink-600 hover:bg-ink-100 hover:text-ink-900 active:scale-95")
      }
    >
      {children}
    </button>
  );
}

import { Extension, type Editor, type Range } from "@tiptap/core";
import Suggestion, { type SuggestionProps } from "@tiptap/suggestion";
import { ReactRenderer } from "@tiptap/react";
import { computePosition, flip, offset, shift } from "@floating-ui/dom";

import { SlashCommandList, type SlashCommandListHandle } from "../SlashCommandList";


export type SlashItem = {
  title: string;
  subtitle: string;
  icon: string;
  // Free-text search terms beyond the title (e.g. "h1" for Heading 1).
  aliases?: string[];
  command: (opts: { editor: Editor; range: Range }) => void;
};


// The block menu. Each command first deletes the typed "/query" range, then
// applies a block transform. Kept to StarterKit-provided nodes so nothing here
// can produce a block the markdown serializer / exporter doesn't understand.
const ITEMS: SlashItem[] = [
  {
    title: "Text", subtitle: "Plain paragraph", icon: "¶", aliases: ["paragraph", "p", "body"],
    command: ({ editor, range }) => editor.chain().focus().deleteRange(range).setParagraph().run(),
  },
  {
    title: "Heading 1", subtitle: "Large section title", icon: "H1", aliases: ["h1", "title"],
    command: ({ editor, range }) => editor.chain().focus().deleteRange(range).setNode("heading", { level: 1 }).run(),
  },
  {
    title: "Heading 2", subtitle: "Medium section title", icon: "H2", aliases: ["h2", "subtitle"],
    command: ({ editor, range }) => editor.chain().focus().deleteRange(range).setNode("heading", { level: 2 }).run(),
  },
  {
    title: "Heading 3", subtitle: "Small section title", icon: "H3", aliases: ["h3"],
    command: ({ editor, range }) => editor.chain().focus().deleteRange(range).setNode("heading", { level: 3 }).run(),
  },
  {
    title: "Bullet list", subtitle: "Unordered list", icon: "•", aliases: ["ul", "unordered", "bullets"],
    command: ({ editor, range }) => editor.chain().focus().deleteRange(range).toggleBulletList().run(),
  },
  {
    title: "Numbered list", subtitle: "Ordered list", icon: "1.", aliases: ["ol", "ordered", "numbers"],
    command: ({ editor, range }) => editor.chain().focus().deleteRange(range).toggleOrderedList().run(),
  },
  {
    title: "Quote", subtitle: "Block quotation", icon: "❝", aliases: ["blockquote", "citation"],
    command: ({ editor, range }) => editor.chain().focus().deleteRange(range).toggleBlockquote().run(),
  },
  {
    title: "Code block", subtitle: "Monospaced code", icon: "</>", aliases: ["code", "pre", "snippet"],
    command: ({ editor, range }) => editor.chain().focus().deleteRange(range).toggleCodeBlock().run(),
  },
  {
    title: "Divider", subtitle: "Horizontal rule", icon: "—", aliases: ["hr", "rule", "separator"],
    command: ({ editor, range }) => editor.chain().focus().deleteRange(range).setHorizontalRule().run(),
  },
];


// Exported for unit testing: case-insensitive match on title + aliases. Empty
// query returns the full palette.
export function getSlashItems(query: string): SlashItem[] {
  const q = query.trim().toLowerCase();
  if (!q) return ITEMS;
  return ITEMS.filter(
    item =>
      item.title.toLowerCase().includes(q) ||
      item.aliases?.some(a => a.includes(q)),
  );
}


// Mounts SlashCommandList into a body-level popup and keeps it positioned at the
// caret via floating-ui. One renderer per suggestion session; idempotent cleanup
// guards against the Esc-then-exit double-teardown.
function makeRenderer() {
  let component: ReactRenderer<SlashCommandListHandle> | null = null;
  let popup: HTMLDivElement | null = null;
  let done = false;

  const reposition = (props: SuggestionProps) => {
    const rect = props.clientRect?.();
    if (!rect || !popup) return;
    const virtual = { getBoundingClientRect: () => rect } as Element;
    void computePosition(virtual, popup, {
      placement: "bottom-start",
      middleware: [offset(6), flip(), shift({ padding: 8 })],
    }).then(({ x, y }) => {
      if (!popup) return;
      popup.style.left = `${x}px`;
      popup.style.top = `${y}px`;
    });
  };

  const teardown = () => {
    if (done) return;
    done = true;
    popup?.remove();
    popup = null;
    component?.destroy();
    component = null;
  };

  return {
    onStart: (props: SuggestionProps) => {
      component = new ReactRenderer(SlashCommandList, { props, editor: props.editor });
      popup = document.createElement("div");
      popup.style.position = "absolute";
      popup.style.top = "0";
      popup.style.left = "0";
      popup.style.zIndex = "50";
      popup.appendChild(component.element);
      document.body.appendChild(popup);
      reposition(props);
    },
    onUpdate: (props: SuggestionProps) => {
      if (done) return;
      component?.updateProps(props);
      reposition(props);
    },
    onKeyDown: (props: { event: KeyboardEvent }) => {
      if (props.event.key === "Escape") {
        teardown();
        return true;
      }
      return component?.ref?.onKeyDown(props) ?? false;
    },
    onExit: teardown,
  };
}


export const SlashCommand = Extension.create({
  name: "slashCommand",

  addProseMirrorPlugins() {
    return [
      Suggestion<SlashItem>({
        editor: this.editor,
        char: "/",
        // Only trigger at the start of an empty-ish block or after whitespace,
        // so "/" inside a word (URLs, fractions) doesn't pop the menu.
        allowSpaces: false,
        startOfLine: false,
        items: ({ query }) => getSlashItems(query),
        // suggestion calls this with the chosen item as `props`.
        command: ({ editor, range, props }) => props.command({ editor, range }),
        render: makeRenderer,
      }),
    ];
  },
});

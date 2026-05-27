import { Mark, mergeAttributes } from "@tiptap/core";

export interface AiPendingAttrs {
  pendingId: string;
  source: "paraphrase" | "translate" | "cite" | "chat_rewrite";
  oldText: string;
  newText: string;
}

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    aiPending: {
      setAiPending: (attrs: AiPendingAttrs) => ReturnType;
      unsetAiPending: () => ReturnType;
    };
  }
}

// Visual layer for the unified PendingEdit machinery. One mark serves
// paraphrase, translate, cite, and chat_rewrite — distinguished by `source`
// so CSS / portals can branch on the kind if needed.
export const AiPending = Mark.create({
  name: "aiPending",

  addAttributes() {
    return {
      pendingId: {
        default: null,
        parseHTML: (el) => el.getAttribute("data-pending-id"),
        renderHTML: (a) => ({ "data-pending-id": a.pendingId }),
      },
      source: {
        default: "paraphrase",
        parseHTML: (el) => el.getAttribute("data-source"),
        renderHTML: (a) => ({ "data-source": a.source }),
      },
      oldText: {
        default: "",
        parseHTML: (el) => el.getAttribute("data-old-text") ?? "",
        renderHTML: (a) => ({ "data-old-text": a.oldText }),
      },
      newText: {
        default: "",
        parseHTML: (el) => el.getAttribute("data-new-text") ?? "",
        renderHTML: (a) => ({ "data-new-text": a.newText }),
      },
    };
  },

  parseHTML() {
    return [{ tag: "span[data-pending-id]" }];
  },

  renderHTML({ HTMLAttributes }) {
    return ["span", mergeAttributes(HTMLAttributes, { class: "ai-pending" }), 0];
  },

  addCommands() {
    return {
      setAiPending:
        (attrs) =>
        ({ commands }) =>
          commands.setMark(this.name, attrs),
      unsetAiPending:
        () =>
        ({ commands }) =>
          commands.unsetMark(this.name),
    };
  },
});

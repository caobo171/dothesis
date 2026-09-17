import { Mark, mergeAttributes } from "@tiptap/core";


// Transient visual state for the exact selection currently sent to an inline
// AI action. Its empty Markdown wrappers guarantee the highlight never enters
// saved prose or exported files.
export const AiProcessing = Mark.create({
  name: "aiProcessing",

  parseHTML() {
    return [{ tag: "span[data-ai-processing]" }];
  },

  renderHTML({ HTMLAttributes }) {
    return ["span", mergeAttributes(HTMLAttributes, {
      "data-ai-processing": "true",
      "aria-busy": "true",
      class: "ai-processing",
    }), 0];
  },

  addStorage() {
    return {
      markdown: {
        serialize: { open: "", close: "", mixable: true, expelEnclosingWhitespace: true },
        parse: {},
      },
    };
  },
});

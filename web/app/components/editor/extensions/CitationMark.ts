import { Mark, mergeAttributes } from "@tiptap/core";


// Represents an inserted (Author, Year) — wraps the citation text and
// stores the back-link to the M2 reference id. Hover/click handlers live
// in the component layer; the mark just persists the linkage.
export const CitationMark = Mark.create({
  name: "citation",

  addAttributes() {
    return {
      referenceId: {
        default: null,
        parseHTML: el => el.getAttribute("data-ref"),
        renderHTML: a => ({ "data-ref": a.referenceId }),
      },
    };
  },

  parseHTML() {
    return [{ tag: "span[data-ref]" }];
  },

  renderHTML({ HTMLAttributes }) {
    return ["span", mergeAttributes(HTMLAttributes, { class: "citation" }), 0];
  },
});

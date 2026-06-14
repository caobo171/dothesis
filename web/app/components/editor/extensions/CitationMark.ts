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

  // Markdown serialization (tiptap-markdown): the citation is editor-only chrome
  // — the visible "(Author, Year)" text already lives in the document, and the
  // referenceId back-link is not part of the stored prose (it never was under
  // the old getText path). Emit no wrapping syntax so the mark serializes to its
  // bare text, keeping stored markdown / the export identical to before.
  addStorage() {
    return {
      markdown: {
        serialize: { open: "", close: "", mixable: true, expelEnclosingWhitespace: true },
        parse: {},
      },
    };
  },
});

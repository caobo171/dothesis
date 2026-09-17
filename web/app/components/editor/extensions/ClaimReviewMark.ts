import { Mark, mergeAttributes } from "@tiptap/core";

/** Transient claim-review annotation. It serializes to plain text, so review
 * UI can never leak into the saved thesis or an export. */
export const ClaimReviewMark = Mark.create({
  name: "claimReview",
  addAttributes() {
    return {
      suggestionId: {
        default: null,
        parseHTML: element => element.getAttribute("data-claim-suggestion-id"),
        renderHTML: attributes => ({ "data-claim-suggestion-id": attributes.suggestionId }),
      },
      actionable: {
        default: false,
        parseHTML: element => element.getAttribute("data-actionable") === "true",
        renderHTML: attributes => ({ "data-actionable": String(Boolean(attributes.actionable)) }),
      },
    };
  },
  parseHTML() { return [{ tag: "span[data-claim-suggestion-id]" }]; },
  renderHTML({ HTMLAttributes }) {
    return ["span", mergeAttributes(HTMLAttributes, { class: "claim-review-mark", role: "button", tabindex: "0", "aria-label": "Mở đề xuất citation" }), 0];
  },
  addStorage() {
    return { markdown: { serialize: { open: "", close: "", mixable: true, expelEnclosingWhitespace: true }, parse: {} } };
  },
});

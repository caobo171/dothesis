import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// The named text styles in globals.css (text-heading-1, text-body-main, …) are
// sizes, not colours. Without this, tailwind-merge reads them as text colours
// and drops the text-ink-* that sits beside them.
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [
        {
          text: [
            "body-main",
            "body-para",
            "heading-1",
            "heading-2",
            "heading-3",
            "label",
            "label-small",
            "button",
            "button-small",
          ],
        },
      ],
    },
  },
});

/** shadcn class merge helper: clsx for conditionals + tailwind-merge to dedupe. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

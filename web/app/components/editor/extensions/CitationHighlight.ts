import { Extension } from "@tiptap/core";
import { Plugin } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";


// Highlights in-text academic citations that live in the prose as plain text —
// the ones the M5 writer produces, e.g. "(Liem et al., 2024)" or the narrative
// "Cham et al. (2024)". These carry no CitationMark (only Cite-action insertions
// do), so without this they'd read as ordinary text. Purely presentational: a
// ProseMirror decoration, never a mark, so the stored markdown / export are
// untouched (see [[project_editor_markdown_storage]]).

// A parenthetical containing a 4-digit year: "(Liem et al., 2024)",
// "(H.A et al., 2019; Cham et al., 2024)", "(WHO, 2021a)".
const PARENTHETICAL = /\([^()\n]*(?:19|20)\d{2}[a-z]?[^()\n]*\)/g;
// Narrative form: an author (optionally "et al." / "&") immediately before a
// "(2024)" year — "Liem et al. (2024)", "Attardo & Raskin (1991)".
const NARRATIVE = /[A-Z][\w.'’-]+(?:\s+(?:et\s+al\.|&|and)[\w.'’\s-]*?)?\s\((?:19|20)\d{2}[a-z]?\)/g;


// A "(2024)" year-only parenthetical shouldn't be highlighted on its own (it's
// usually part of a narrative citation the NARRATIVE pass already covers, or a
// bare year in prose). Require at least one letter alongside the year, OR a
// separator (; or ,) signalling a real citation list.
function looksLikeCitation(match: string): boolean {
  const inner = match.slice(1, -1); // strip the outer parens
  return /[A-Za-z]/.test(inner) || /[;,]/.test(inner);
}


export const CitationHighlight = Extension.create({
  name: "citationHighlight",

  addProseMirrorPlugins() {
    return [
      new Plugin({
        props: {
          decorations(state) {
            const decos: Decoration[] = [];
            state.doc.descendants((node, pos) => {
              if (!node.isText || !node.text) return true;
              const text = node.text;
              for (const [re, guard] of [[PARENTHETICAL, looksLikeCitation], [NARRATIVE, null]] as const) {
                re.lastIndex = 0;
                let m: RegExpExecArray | null;
                while ((m = re.exec(text)) !== null) {
                  if (guard && !guard(m[0])) continue;
                  decos.push(
                    Decoration.inline(pos + m.index, pos + m.index + m[0].length, {
                      class: "citation-auto",
                    }),
                  );
                }
              }
              return true;
            });
            return DecorationSet.create(state.doc, decos);
          },
        },
      }),
    ];
  },
});

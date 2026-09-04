import { Extension } from "@tiptap/core";
import { Plugin } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";


// Friendly labels for the `[[DT:kind]]` placement tokens the M5 writer emits.
// These mirror the captions in orchestrator/tools/results_render.py (_CAPTIONS,
// vi) — the export weaves the real computed block in at each token; the editor
// only stores the token, so without this it shows raw "[[DT:data_cleaning]]"
// which reads like broken syntax. Vietnamese-first (product's primary market);
// unknown kinds fall back to a humanized slug.
const DT_LABELS: Record<string, string> = {
  data_cleaning: "Tóm tắt sàng lọc dữ liệu",
  descriptives: "Thống kê mô tả mẫu",
  measurement_model: "Mô hình đo lường: độ tin cậy và giá trị hội tụ",
  scale_reliability: "Độ tin cậy thang đo",
  discriminant_validity: "Giá trị phân biệt",
  model_fit: "Các chỉ số độ phù hợp mô hình",
  structural_paths: "Mô hình cấu trúc: kiểm định giả thuyết",
  r2_q2: "Năng lực giải thích và dự báo (R² / Q²)",
};

// A whole-paragraph token: "[[DT:kind]]" alone on its line.
const DT_TOKEN_RE = /^\s*\[\[DT:([a-z0-9_]+)\]\]\s*$/;

export function dtLabel(kind: string): string {
  return DT_LABELS[kind] || kind.replace(/_/g, " ");
}


// tiptap-markdown escapes `[` as `\[` on serialize (it's link syntax), so an
// edited chapter autosaves `[[DT:kind]]` as `\[\[DT:kind\]\]` — which the
// export's token matcher (bare `[[…]]`) would miss, silently dropping the woven
// block. Normalize DT tokens back to their bare form before persisting. Matches
// the token whether or not each bracket got escaped.
export function preserveDtTokens(md: string): string {
  return md.replace(/\\?\[\\?\[DT:([a-z0-9_]+)\\?\]\\?\]/g, "[[DT:$1]]");
}


// Decorates paragraphs that are just a `[[DT:kind]]` token so they render as a
// labeled "generated at export" card. Purely presentational — the token text is
// untouched in the document, so it still round-trips to markdown and the export
// weave finds it exactly as before (see [[project_export_pipeline]]).
export const DtPlaceholder = Extension.create({
  name: "dtPlaceholder",

  addProseMirrorPlugins() {
    return [
      new Plugin({
        props: {
          decorations(state) {
            const decos: Decoration[] = [];
            state.doc.descendants((node, pos) => {
              if (!node.isTextblock) return true;
              const m = DT_TOKEN_RE.exec(node.textContent);
              if (m) {
                decos.push(
                  Decoration.node(pos, pos + node.nodeSize, {
                    class: "dt-token",
                    "data-dt-label": dtLabel(m[1]),
                  }),
                );
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

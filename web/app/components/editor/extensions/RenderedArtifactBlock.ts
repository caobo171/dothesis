import { Extension } from "@tiptap/core";
import { Plugin } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";


const MARKER_RE = /<!--dt-rendered:(begin) kind=([a-z0-9_]+) sha=[0-9a-f]+-->|<!--dt-rendered:(end) kind=([a-z0-9_]+)-->/g;

const LABELS: Record<string, string> = {
  measurement_model: "Mô hình đo lường",
  scale_reliability: "Độ tin cậy thang đo",
  discriminant_validity: "Giá trị phân biệt",
  model_fit: "Độ phù hợp mô hình",
  structural_paths: "Kiểm định giả thuyết",
  descriptives: "Thống kê mô tả",
  r2_q2: "Năng lực giải thích và dự báo",
  data_cleaning: "Sàng lọc dữ liệu",
  limitations: "Hạn chế nghiên cứu",
};


/**
 * Presents verified `dt-rendered` regions as generated-result blocks.
 *
 * The begin/end comments are integrity sentinels used by coherence checks and
 * renderer idempotency, so deleting them on load would make a later save
 * unsafe. Decorations hide only their visual spans and label the host blocks;
 * the exact marker bytes remain in the ProseMirror document and serialized
 * Markdown.
 */
export const RenderedArtifactBlock = Extension.create({
  name: "renderedArtifactBlock",

  addProseMirrorPlugins() {
    return [
      new Plugin({
        props: {
          decorations(state) {
            const decorations: Decoration[] = [];
            state.doc.descendants((node, pos) => {
              if (!node.isText) return true;
              const text = node.text ?? "";
              MARKER_RE.lastIndex = 0;
              let match: RegExpExecArray | null;
              while ((match = MARKER_RE.exec(text))) {
                const phase = match[1] || match[3];
                const kind = match[2] || match[4] || "result";
                decorations.push(Decoration.inline(
                  pos + match.index,
                  pos + match.index + match[0].length,
                  { class: "dt-rendered-marker", "aria-hidden": "true" },
                ));

                // The marker normally shares its paragraph with the caption or
                // source line. Decorate that parent as the visible edge of the
                // generated block while leaving the useful text editable.
                const $pos = state.doc.resolve(pos);
                if ($pos.depth > 0) {
                  const parentStart = $pos.before($pos.depth);
                  const parent = $pos.node($pos.depth);
                  decorations.push(Decoration.node(
                    parentStart,
                    parentStart + parent.nodeSize,
                    phase === "begin"
                      ? {
                          class: "dt-rendered-boundary dt-rendered-start",
                          "data-dt-kind": kind,
                          "data-dt-label": LABELS[kind] || kind.replace(/_/g, " "),
                        }
                      : { class: "dt-rendered-boundary dt-rendered-end", "data-dt-kind": kind },
                  ));
                }
              }
              return true;
            });
            return DecorationSet.create(state.doc, decorations);
          },
        },
      }),
    ];
  },
});

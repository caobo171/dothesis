"use client";

import Image from "@tiptap/extension-image";
import { NodeViewWrapper, ReactNodeViewRenderer, type ReactNodeViewProps } from "@tiptap/react";
import { ImageIcon, Link2, Trash2 } from "lucide-react";


/**
 * A semantic editor surface for Markdown images.
 *
 * Decision: extend TipTap's existing `image` node instead of introducing a
 * new schema name. `tiptap-markdown` already knows how to parse and serialize
 * `![alt](src "title")`; retaining that node name makes the visual block
 * lossless for Save and Pandoc export while giving figures first-class editor
 * controls. The caption is the Markdown alt text, so it travels with the image
 * rather than living in browser-only component state.
 */
export const FigureBlock = Image.extend({
  addNodeView() {
    return ReactNodeViewRenderer(FigureView);
  },
});


function sourceLabel(source: string): string {
  if (!source) return "Project artifact";
  try {
    const parsed = new URL(source, window.location.origin);
    return parsed.origin === window.location.origin ? "Project artifact" : parsed.hostname;
  } catch {
    return "Project artifact";
  }
}


function FigureView({ node, updateAttributes, deleteNode, selected }: ReactNodeViewProps) {
  const src = String(node.attrs.src ?? "");
  const caption = String(node.attrs.alt ?? "");
  const title = String(node.attrs.title ?? "");

  return (
    <NodeViewWrapper
      className={`figure-block ${selected ? "figure-block-selected" : ""}`}
      data-testid="figure-block"
      contentEditable={false}
    >
      <div className="figure-block-toolbar">
        <span className="figure-block-kind"><ImageIcon className="h-3.5 w-3.5" /> Figure</span>
        <span className="figure-block-source" title={src}>
          <Link2 className="h-3 w-3" /> {sourceLabel(src)}
        </span>
        <button type="button" onClick={deleteNode} aria-label="Delete figure" title="Delete figure"
          className="figure-block-delete">
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="figure-block-preview">
        {/* eslint-disable-next-line @next/next/no-img-element -- source may be a signed project artifact URL. */}
        <img src={src} alt={caption || title || "Thesis figure"} draggable={false} />
      </div>
      <div className="figure-block-caption-row">
        <span className="figure-block-caption-label">Caption</span>
        <input
          value={caption}
          onChange={event => updateAttributes({ alt: event.target.value })}
          placeholder="Add a figure caption…"
          aria-label="Figure caption"
          className="figure-block-caption-input"
        />
      </div>
    </NodeViewWrapper>
  );
}

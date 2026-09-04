"use client";

import CodeBlock from "@tiptap/extension-code-block";
import {
  ReactNodeViewRenderer,
  NodeViewWrapper,
  NodeViewContent,
  type ReactNodeViewProps,
} from "@tiptap/react";
import { useEffect, useRef, useState } from "react";


// A ```mermaid fenced block that renders a live diagram preview beneath its
// source. It's a thin extension of StarterKit's CodeBlock, so the stored value
// is still a plain fenced code block — tiptap-markdown serializes it to
// ```mermaid …``` and it round-trips into the export untouched (see
// [[project_editor_markdown_storage]]). Non-mermaid code blocks keep the
// default plain rendering.
//
// Why extend CodeBlock rather than a new node: fenced code is what the markdown
// stores and what the parser produces, so reusing the codeBlock node keeps the
// load→edit→serialize cycle lossless. Only the *view* changes.
export const MermaidBlock = CodeBlock.extend({
  addNodeView() {
    return ReactNodeViewRenderer(MermaidView);
  },
});


let _mermaidReady = false;

// Lazy-load + one-time init. mermaid touches the DOM, so it must stay client
// only and load after mount — never at module eval (breaks SSR/tests).
async function renderMermaid(id: string, source: string): Promise<string> {
  const mod = await import("mermaid");
  const mermaid = mod.default;
  if (!_mermaidReady) {
    mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: "neutral" });
    _mermaidReady = true;
  }
  const { svg } = await mermaid.render(id, source);
  return svg;
}


function MermaidView({ node }: ReactNodeViewProps) {
  const language = node.attrs.language as string | null;
  const isMermaid = language === "mermaid";
  const source = node.textContent;
  const [svg, setSvg] = useState<string>("");
  const [error, setError] = useState<string>("");
  const idRef = useRef(`mermaid-${Math.random().toString(36).slice(2)}`);

  useEffect(() => {
    if (!isMermaid) return;
    const code = source.trim();
    if (!code) { setSvg(""); setError(""); return; }
    let cancelled = false;
    // Debounce so we don't re-render the diagram on every keystroke.
    const t = setTimeout(() => {
      renderMermaid(idRef.current, code)
        .then(out => { if (!cancelled) { setSvg(out); setError(""); } })
        .catch(e => { if (!cancelled) setError(String(e?.message || e)); });
    }, 300);
    return () => { cancelled = true; clearTimeout(t); };
  }, [isMermaid, source]);

  // Non-mermaid code blocks: default plain rendering.
  if (!isMermaid) {
    return (
      <NodeViewWrapper as="pre">
        <NodeViewContent<"code"> as="code" />
      </NodeViewWrapper>
    );
  }

  return (
    <NodeViewWrapper className="mermaid-block" data-testid="mermaid-block">
      {/* Editable source */}
      <pre className="mermaid-source">
        <NodeViewContent<"code"> as="code" />
      </pre>
      {/* Rendered preview (or the parse error mermaid reports) */}
      <div className="mermaid-preview" contentEditable={false}>
        {error ? (
          <div className="mermaid-error" role="alert">Sơ đồ lỗi: {error}</div>
        ) : svg ? (
          <div aria-label="Sơ đồ mermaid" dangerouslySetInnerHTML={{ __html: svg }} />
        ) : (
          <div className="mermaid-empty">Nhập cú pháp mermaid để xem sơ đồ…</div>
        )}
      </div>
    </NodeViewWrapper>
  );
}

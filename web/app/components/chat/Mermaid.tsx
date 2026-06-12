"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Lazy-loaded Mermaid renderer.
 *
 * Why dynamic import: the `mermaid` library is ~600KB minified — too big to
 * ship to the initial chat bundle when most messages won't include a
 * diagram. Importing it inside the effect means the bundle only loads when
 * a `[language-mermaid]` code block first appears in a message.
 *
 * Per-instance render: each Mermaid block gets a unique id so we can call
 * `mermaid.render(id, source)` and inject the resulting SVG into the
 * container. `mermaid.initialize` is called once per session — `securityLevel
 * = strict` blocks click handlers in diagrams so the agent can't smuggle
 * arbitrary JS into the chat surface.
 *
 * Error handling: a bad diagram renders the raw source in a faded block
 * with a "diagram error" caption rather than crashing the bubble — the
 * agent can recover by re-emitting; the user still sees what was attempted.
 */
let _mermaidPromise: Promise<typeof import("mermaid").default> | null = null;
let _idCounter = 0;

function loadMermaid() {
  if (!_mermaidPromise) {
    _mermaidPromise = import("mermaid").then((mod) => {
      mod.default.initialize({
        startOnLoad: false,
        securityLevel: "strict",
        theme: "default",
        flowchart: { htmlLabels: true, curve: "basis" },
      });
      return mod.default;
    });
  }
  return _mermaidPromise;
}

export function Mermaid({ source }: { source: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const id = `mermaid-${++_idCounter}`;
    loadMermaid()
      .then((mermaid) => mermaid.render(id, source))
      .then(({ svg, bindFunctions }) => {
        if (cancelled || !ref.current) return;
        ref.current.innerHTML = svg;
        // bindFunctions wires up click handlers when securityLevel allows;
        // we use `strict` so this is effectively a no-op, but kept here
        // to match Mermaid's documented contract.
        bindFunctions?.(ref.current);
        setError(null);
      })
      .catch((e: Error) => {
        if (cancelled) return;
        setError(e.message || "could not render diagram");
      });
    return () => { cancelled = true; };
  }, [source]);

  if (error) {
    return (
      <div className="my-2 rounded border border-amber-200 bg-amber-50 p-2 text-xs">
        <div className="font-semibold text-amber-800 mb-1">⚠ Diagram error</div>
        <div className="text-amber-700 mb-1">{error}</div>
        <pre className="font-mono text-[12px] text-ink-700 whitespace-pre-wrap">{source}</pre>
      </div>
    );
  }

  return (
    <div
      ref={ref}
      className="my-2 flex justify-center [&_svg]:max-w-full [&_svg]:h-auto"
      data-testid="mermaid-diagram"
    />
  );
}

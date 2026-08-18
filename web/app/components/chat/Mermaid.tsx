"use client";

import { useEffect, useRef, useState } from "react";
import { Maximize2, Minus, Plus, RotateCcw, X } from "lucide-react";

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

export function normalizeMermaidSource(source: string): string {
  const lines = source.replace(/<br\s*>/gi, "<br/>").split("\n");
  const nodeIds = new Set<string>();

  for (const line of lines) {
    if (/^\s*subgraph\b/.test(line)) continue;
    for (const match of line.matchAll(/\b([A-Za-z][\w-]*)\s*\[/g)) {
      nodeIds.add(match[1]);
    }
  }

  return lines
    .map((line) => line.replace(
      /^(\s*subgraph\s+)([A-Za-z][\w-]*)(?=\s*\[|\s|$)/,
      (match, prefix: string, id: string) =>
        nodeIds.has(id) ? `${prefix}cluster_${id}` : match,
    ).replace(
      /\b([A-Za-z][\w-]*)\[([^\]\n]+)\]/g,
      (match, id: string, label: string) => {
        // Already-quoted labels need no intervention. Generated prose labels
        // frequently contain parentheses, ampersands, or punctuation Mermaid
        // otherwise mistakes for node-shape syntax.
        if (/^\s*["']/.test(label)) return match;
        const escaped = label.replace(/\\/g, "\\\\").replace(/"/g, "&quot;");
        return `${id}["${escaped}"]`;
      },
    ))
    .join("\n");
}

export function Mermaid({ source }: { source: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [svgMarkup, setSvgMarkup] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [zoom, setZoom] = useState(1);

  useEffect(() => {
    let cancelled = false;
    const id = `mermaid-${++_idCounter}`;
    const normalizedSource = normalizeMermaidSource(source);
    loadMermaid()
      .then((mermaid) => mermaid.render(id, normalizedSource))
      .then(({ svg, bindFunctions }) => {
        if (cancelled || !ref.current) return;
        ref.current.innerHTML = svg;
        // bindFunctions wires up click handlers when securityLevel allows;
        // we use `strict` so this is effectively a no-op, but kept here
        // to match Mermaid's documented contract.
        bindFunctions?.(ref.current);
        setSvgMarkup(svg);
        setError(null);
      })
      .catch((e: Error) => {
        if (cancelled) return;
        setError(e.message || "could not render diagram");
      });
    return () => { cancelled = true; };
  }, [source]);

  useEffect(() => {
    if (!expanded) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setExpanded(false);
      if ((event.metaKey || event.ctrlKey) && event.key === "+") {
        event.preventDefault();
        setZoom((value) => Math.min(3, value + 0.25));
      }
      if ((event.metaKey || event.ctrlKey) && event.key === "-") {
        event.preventDefault();
        setZoom((value) => Math.max(0.5, value - 0.25));
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [expanded]);

  const openExpanded = () => {
    setZoom(1);
    setExpanded(true);
  };

  const handleCanvasWheel = (event: React.WheelEvent<HTMLDivElement>) => {
    // macOS trackpad pinch arrives as a wheel event with ctrlKey=true.
    // Leave ordinary two-finger wheel events alone so they continue to pan
    // around a zoomed diagram.
    if (!event.ctrlKey) return;
    event.preventDefault();
    const factor = Math.exp(-event.deltaY * 0.008);
    setZoom((value) => Math.min(3, Math.max(0.5, value * factor)));
  };

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
    <>
      <div
        className="group/diagram relative my-3 overflow-hidden rounded-xl border border-ink-100 bg-ink-50/70 p-3"
        onDoubleClick={svgMarkup ? openExpanded : undefined}
        title={svgMarkup ? "Double-click to view the full model" : undefined}
      >
        <div
          ref={ref}
          className="flex min-h-24 justify-center [&_svg]:h-auto [&_svg]:max-w-full"
          data-testid="mermaid-diagram"
        />
        {svgMarkup && (
          <button
            type="button"
            onClick={openExpanded}
            className="absolute right-3 top-3 inline-flex items-center gap-1.5 rounded-lg border border-ink-200 bg-white/95 px-2.5 py-1.5 text-[11.5px] font-semibold text-ink-700 shadow-sm backdrop-blur transition-colors hover:bg-ink-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
            aria-label="Expand model diagram"
          >
            <Maximize2 className="h-3.5 w-3.5" aria-hidden />
            View full
          </button>
        )}
      </div>

      {expanded && svgMarkup && (
        <div
          className="fixed inset-0 z-[80] flex flex-col bg-[#eef1f5]"
          role="dialog"
          aria-modal="true"
          aria-label="Full model diagram"
        >
          <header className="flex min-h-16 shrink-0 items-center gap-3 border-b border-ink-200 bg-white px-4 sm:px-6">
            <div>
              <div className="text-sm font-semibold text-ink-900">Model diagram</div>
              <div className="text-[11px] text-ink-400">Scroll to move around the canvas</div>
            </div>
            <span className="flex-1" />
            <div className="flex items-center rounded-lg border border-ink-200 bg-white p-1 shadow-sm">
              <button
                type="button"
                onClick={() => setZoom((value) => Math.max(0.5, value - 0.25))}
                className="inline-flex h-8 w-8 items-center justify-center rounded-md text-ink-600 hover:bg-ink-100 disabled:opacity-35"
                aria-label="Zoom out"
                disabled={zoom <= 0.5}
              >
                <Minus className="h-4 w-4" aria-hidden />
              </button>
              <span className="w-14 text-center text-[12px] font-medium tabular-nums text-ink-700">
                {Math.round(zoom * 100)}%
              </span>
              <button
                type="button"
                onClick={() => setZoom((value) => Math.min(3, value + 0.25))}
                className="inline-flex h-8 w-8 items-center justify-center rounded-md text-ink-600 hover:bg-ink-100 disabled:opacity-35"
                aria-label="Zoom in"
                disabled={zoom >= 3}
              >
                <Plus className="h-4 w-4" aria-hidden />
              </button>
              <span className="mx-1 h-5 w-px bg-ink-200" aria-hidden />
              <button
                type="button"
                onClick={() => setZoom(1)}
                className="inline-flex h-8 items-center gap-1.5 rounded-md px-2 text-[12px] font-medium text-ink-600 hover:bg-ink-100"
                aria-label="Fit diagram"
              >
                <RotateCcw className="h-3.5 w-3.5" aria-hidden />
                Fit
              </button>
            </div>
            <button
              type="button"
              onClick={() => setExpanded(false)}
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-ink-600 hover:bg-ink-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
              aria-label="Close full model"
            >
              <X className="h-5 w-5" aria-hidden />
            </button>
          </header>

          <div
            className="min-h-0 flex-1 overflow-auto p-5 sm:p-8"
            onWheel={handleCanvasWheel}
            aria-label="Zoomable model canvas"
          >
            <div
              className="mx-auto min-h-full rounded-xl border border-ink-200 bg-white p-6 shadow-[0_12px_40px_rgba(40,50,65,0.10)] [&_svg]:h-auto [&_svg]:w-full"
              style={{ width: `${zoom * 100}%`, minWidth: `${zoom * 900}px` }}
              dangerouslySetInnerHTML={{ __html: svgMarkup }}
            />
          </div>
        </div>
      )}
    </>
  );
}

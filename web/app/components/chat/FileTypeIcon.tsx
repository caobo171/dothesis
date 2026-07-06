// A recognizable file-type icon (document + folded corner + a colored label
// band) — PDF in red, DOC/DOCX in blue. Replaces the generic lucide FileText,
// which looked the same for every format and read as cheap. Dependency-free SVG
// so it stays crisp at any size and tints by type.
export function FileTypeIcon({ kind, className = "w-5 h-6" }: { kind?: string; className?: string }) {
  const k = (kind || "").toLowerCase();
  const isPdf = k === "pdf";
  const isDoc = k === "docx" || k === "doc";
  const color = isPdf ? "#E5252A" : isDoc ? "#2B579A" : "#5B6472";
  const label = isPdf ? "PDF" : isDoc ? "DOC" : (kind || "FILE").slice(0, 3).toUpperCase();
  return (
    <svg viewBox="0 0 24 28" className={className} fill="none" aria-hidden="true">
      {/* page */}
      <path
        d="M3 1.5h11l6.5 6.5V25a1.5 1.5 0 0 1-1.5 1.5H3A1.5 1.5 0 0 1 1.5 25V3A1.5 1.5 0 0 1 3 1.5Z"
        fill="#fff"
        stroke="#D7DBE6"
        strokeWidth="1.3"
      />
      {/* folded corner */}
      <path
        d="M14 1.5V7a1 1 0 0 0 1 1h5.5"
        fill="#EEF1F7"
        stroke="#D7DBE6"
        strokeWidth="1.3"
        strokeLinejoin="round"
      />
      {/* colored format band */}
      <rect x="0.5" y="14" width="17" height="9" rx="1.6" fill={color} />
      <text
        x="9"
        y="20.7"
        textAnchor="middle"
        fontSize="6.2"
        fontWeight="700"
        fill="#fff"
        fontFamily="ui-sans-serif, system-ui, sans-serif"
        letterSpacing="0.3"
      >
        {label}
      </text>
    </svg>
  );
}

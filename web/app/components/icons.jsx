// Outline-style icons (18-20px, stroke-based) — matches Survify's calm icon vocabulary.

export const Icon = ({ name, size = 18, stroke = 1.75, className = "", style }) => {
  const props = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: stroke,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    className,
    style,
  };
  switch (name) {
    case "home":
      return <svg {...props}><path d="M3 11.5 12 4l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1Z"/></svg>;
    case "book":
      return <svg {...props}><path d="M4 4h6a2 2 0 0 1 2 2v14a2 2 0 0 0-2-2H4Z"/><path d="M20 4h-6a2 2 0 0 0-2 2v14a2 2 0 0 1 2-2h6Z"/></svg>;
    case "wand":
      return <svg {...props}><path d="m4 20 12-12"/><path d="M18 4v4M16 6h4"/><path d="M14 2v3M12.5 3.5h3"/><path d="M20 14v3M18.5 15.5h3"/></svg>;
    case "pipeline":
      return <svg {...props}><circle cx="5" cy="6" r="2"/><circle cx="5" cy="18" r="2"/><circle cx="19" cy="12" r="2"/><path d="M7 6h4a3 3 0 0 1 3 3v0a3 3 0 0 0 3 3"/><path d="M7 18h4a3 3 0 0 0 3-3v0a3 3 0 0 1 3-3"/></svg>;
    case "edit":
      return <svg {...props}><path d="M4 20h4l10-10-4-4L4 16Z"/><path d="m14 6 4 4"/></svg>;
    case "quote":
      return <svg {...props}><path d="M7 7H4v6h6V7l-3 6"/><path d="M17 7h-3v6h6V7l-3 6"/></svg>;
    case "export":
      return <svg {...props}><path d="M12 3v12"/><path d="m7 8 5-5 5 5"/><path d="M5 21h14"/></svg>;
    case "wallet":
      return <svg {...props}><rect x="3" y="6" width="18" height="14" rx="2"/><path d="M16 12h3"/><path d="M3 9V5a1 1 0 0 1 1-1h13"/></svg>;
    case "affiliate":
      return <svg {...props}><circle cx="12" cy="8" r="4"/><path d="m8.5 11-2.5 4 3 .5L9 19l3-4"/><path d="m15.5 11 2.5 4-3 .5.5 3.5-3-4"/></svg>;
    case "bell":
      return <svg {...props}><path d="M6 9a6 6 0 1 1 12 0c0 5 2 6 2 6H4s2-1 2-6Z"/><path d="M10 19a2 2 0 0 0 4 0"/></svg>;
    case "logout":
      return <svg {...props}><path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3"/><path d="M11 16l-4-4 4-4"/><path d="M15 12H7"/></svg>;
    case "plus":
      return <svg {...props}><path d="M12 5v14M5 12h14"/></svg>;
    case "search":
      return <svg {...props}><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>;
    case "filter":
      return <svg {...props}><path d="M3 5h18l-7 9v6l-4-2v-4Z"/></svg>;
    case "play":
      return <svg {...props}><path d="m7 4 13 8-13 8Z" fill="currentColor"/></svg>;
    case "pause":
      return <svg {...props}><rect x="7" y="5" width="3.5" height="14" rx="1" fill="currentColor"/><rect x="13.5" y="5" width="3.5" height="14" rx="1" fill="currentColor"/></svg>;
    case "stop":
      return <svg {...props}><rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/></svg>;
    case "eye":
      return <svg {...props}><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>;
    case "check":
      return <svg {...props}><path d="m5 12 5 5 9-11"/></svg>;
    case "checkcircle":
      return <svg {...props}><circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/></svg>;
    case "arrow-right":
      return <svg {...props}><path d="M5 12h14"/><path d="m13 6 6 6-6 6"/></svg>;
    case "arrow-left":
      return <svg {...props}><path d="M19 12H5"/><path d="m11 6-6 6 6 6"/></svg>;
    case "chevron-right":
      return <svg {...props}><path d="m9 6 6 6-6 6"/></svg>;
    case "chevron-down":
      return <svg {...props}><path d="m6 9 6 6 6-6"/></svg>;
    case "sparkle":
      return <svg {...props}><path d="M12 3v4M12 17v4M3 12h4M17 12h4"/><path d="m6 6 2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18"/></svg>;
    case "feather":
      return <svg {...props}><path d="M20 4c-7 0-13 6-13 13v3h3c7 0 13-6 13-13V4Z"/><path d="M16 8 4 20"/><path d="M14 14H8"/></svg>;
    case "doc":
      return <svg {...props}><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z"/><path d="M14 3v6h6"/></svg>;
    case "doc-pdf":
      return <svg {...props}><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z"/><path d="M14 3v6h6"/><text x="7" y="18" fontSize="6" fontFamily="Manrope, sans-serif" fontWeight="700" fill="currentColor" stroke="none">PDF</text></svg>;
    case "doc-word":
      return <svg {...props}><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z"/><path d="M14 3v6h6"/><text x="7" y="18" fontSize="6" fontFamily="Manrope, sans-serif" fontWeight="700" fill="currentColor" stroke="none">DOC</text></svg>;
    case "doc-tex":
      return <svg {...props}><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z"/><path d="M14 3v6h6"/><text x="7" y="18" fontSize="6" fontFamily="Manrope, sans-serif" fontWeight="700" fill="currentColor" stroke="none">TEX</text></svg>;
    case "globe":
      return <svg {...props}><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>;
    case "graduation":
      return <svg {...props}><path d="m3 9 9-5 9 5-9 5Z"/><path d="M7 11v5a5 5 0 0 0 10 0v-5"/></svg>;
    case "spark":
      return <svg {...props}><path d="M12 2 14 9l7 2-7 2-2 7-2-7-7-2 7-2Z"/></svg>;
    case "link":
      return <svg {...props}><path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1"/><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"/></svg>;
    case "warning":
      return <svg {...props}><path d="M12 4 2 20h20Z"/><path d="M12 10v4M12 17v.5"/></svg>;
    case "trend":
      return <svg {...props}><path d="m3 17 6-6 4 4 8-8"/><path d="M14 7h7v7"/></svg>;
    case "copy":
      return <svg {...props}><rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></svg>;
    case "settings":
      return <svg {...props}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/></svg>;
    case "swap":
      return <svg {...props}><path d="m7 4-3 3 3 3"/><path d="M4 7h16"/><path d="m17 14 3 3-3 3"/><path d="M20 17H4"/></svg>;
    case "library":
      return <svg {...props}><rect x="3" y="3" width="4" height="18" rx="1"/><rect x="9" y="3" width="4" height="18" rx="1"/><rect x="15" y="6" width="4" height="15" rx="1"/></svg>;
    case "shield":
      return <svg {...props}><path d="M12 3 4 6v6c0 5 4 8 8 9 4-1 8-4 8-9V6Z"/><path d="m9 12 2 2 4-4"/></svg>;
    case "hourglass":
      return <svg {...props}><path d="M6 3h12M6 21h12"/><path d="M7 3v4l5 5-5 5v4M17 3v4l-5 5 5 5v4"/></svg>;
    default:
      return <svg {...props}><circle cx="12" cy="12" r="9"/></svg>;
  }
};

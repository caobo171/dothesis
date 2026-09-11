// File-type icons in the shape people already recognise from their desktop: a
// white sheet with a folded corner, and a saturated rounded badge carrying the
// format's letter — blue W for Word, green X for Excel, red for PDF.
//
// Drawn here rather than shipped as vendor artwork. The Office and Acrobat
// icons are trademarks and their brand guidelines don't cover redistribution
// inside another product, so this is an original drawing in the same visual
// language: instantly readable as "Word file" without embedding Microsoft's
// asset. It also stays dependency-free SVG, so it's crisp at every size the app
// uses (18px in the context panel up to 42px in the papers grid) and tints by
// type without a sprite sheet or a network request.

type Family = "word" | "excel" | "pdf" | "data" | "web" | "text";

const _FAMILY: Record<Family, { badge: string; label: string }> = {
  // Word blue and Excel green are the colours the formats are known by; the
  // point of the icon is recognition, so matching them is the whole job.
  word: { badge: "#185ABD", label: "W" },
  excel: { badge: "#107C41", label: "X" },
  pdf: { badge: "#D93025", label: "PDF" },
  // .sav has no consumer-recognisable mark (SPSS is IBM's), so it gets a
  // neutral data colour and its own extension as the label.
  data: { badge: "#6E4BB5", label: "SAV" },
  web: { badge: "#E44D26", label: "<>" },
  text: { badge: "#5B6472", label: "TXT" },
};

function _familyOf(kind?: string): { family: Family; label: string } {
  const k = (kind || "").toLowerCase().replace(/^\./, "").trim();
  if (k === "doc" || k === "docx") return { family: "word", label: "W" };
  if (k === "xls" || k === "xlsx") return { family: "excel", label: "X" };
  // A .csv is a spreadsheet to everyone who owns one, and it opens in Excel.
  if (k === "csv") return { family: "excel", label: "CSV" };
  if (k === "pdf") return { family: "pdf", label: "PDF" };
  if (k === "sav") return { family: "data", label: "SAV" };
  if (k === "htm" || k === "html") return { family: "web", label: "<>" };
  if (!k) return { family: "text", label: "FILE" };
  return { family: "text", label: k.slice(0, 4).toUpperCase() };
}

/**
 * Which badge a file should carry, named by its extension.
 *
 * The filename wins over the mime type on purpose: mime is whatever the
 * browser guessed at upload time, and .docx routinely arrives as
 * `application/octet-stream` (or an empty string, from a mobile share sheet).
 * Callers that branched on mime alone therefore put every Word file on the
 * grey "FILE" sheet — the extension the student typed is the more reliable
 * signal, with mime kept as the fallback for extensionless names.
 */
export function fileKindOf(filename?: string | null, mimeType?: string | null): string {
  const name = (filename || "").trim();
  const ext = name.includes(".") ? name.slice(name.lastIndexOf(".") + 1) : "";
  if (/^[a-z0-9]{1,5}$/i.test(ext)) return ext.toLowerCase();

  const mime = (mimeType || "").toLowerCase();
  if (mime.includes("pdf")) return "pdf";
  if (mime.includes("wordprocessingml") || mime.includes("msword")) return "docx";
  if (mime.includes("spreadsheetml") || mime.includes("ms-excel")) return "xlsx";
  if (mime.includes("csv")) return "csv";
  // Empty, not "file": _familyOf() reads that as "unknown format" and draws the
  // neutral sheet, whereas "file" would print FILE as if it were an extension.
  return "";
}

export function FileTypeIcon({ kind, className = "w-5 h-6" }: { kind?: string; className?: string }) {
  const { family, label } = _familyOf(kind);
  const { badge } = _FAMILY[family];
  // One glyph gets to be big; longer labels shrink so "CSV"/"FILE" still fit
  // the badge instead of spilling past its corners.
  const fontSize = label.length <= 1 ? 8.4 : label.length <= 3 ? 5.6 : 4.4;

  return (
    <svg viewBox="0 0 24 28" className={className} fill="none" aria-hidden="true">
      {/* sheet */}
      <path
        d="M3.2 1.4h10.4l7 7V25a1.6 1.6 0 0 1-1.6 1.6H3.2A1.6 1.6 0 0 1 1.6 25V3A1.6 1.6 0 0 1 3.2 1.4Z"
        fill="#fff"
        stroke="#D7DBE6"
        strokeWidth="1.25"
      />
      {/* folded corner */}
      <path
        d="M13.6 1.4V7.2a1.2 1.2 0 0 0 1.2 1.2h5.8"
        fill="#EEF1F7"
        stroke="#D7DBE6"
        strokeWidth="1.25"
        strokeLinejoin="round"
      />
      {/* a couple of faint text lines, so the sheet reads as a document even
          when the badge is too small to parse */}
      <path d="M5.4 12.4h7M5.4 15.2h5" stroke="#E3E7EF" strokeWidth="1.3" strokeLinecap="round" />
      {/* format badge, overlapping the lower-left corner like the desktop icons */}
      <rect x="0.9" y="16.4" width="15.6" height="10.2" rx="2.4" fill={badge} />
      <text
        x="8.7"
        y={21.5 + fontSize / 2.9}
        textAnchor="middle"
        fontSize={fontSize}
        fontWeight="700"
        fill="#fff"
        fontFamily="ui-sans-serif, system-ui, -apple-system, sans-serif"
        letterSpacing={label.length > 1 ? "0.2" : "0"}
      >
        {label}
      </text>
    </svg>
  );
}

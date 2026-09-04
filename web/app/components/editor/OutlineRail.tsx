"use client";


export type ChapterName = "intro" | "lit_review" | "methodology" | "results" | "conclusion";


// FIVE chapters, not six: the discussion of findings lives INSIDE Chapter 5
// rather than as a chapter of its own, matching the backend's collapsed
// M5_CHAPTER_ORDER / M5_CHAPTER_TITLES (orchestrator/tools/m5_writing.py).
const _ORDER: { name: ChapterName; label: string }[] = [
  { name: "intro",        label: "Ch 1 — Introduction" },
  { name: "lit_review",   label: "Ch 2 — Literature Review" },
  { name: "methodology",  label: "Ch 3 — Methodology" },
  { name: "results",      label: "Ch 4 — Results" },
  { name: "conclusion",   label: "Ch 5 — Conclusions and Recommendations" },
];


type Props = {
  present: ChapterName[];
  active: ChapterName;
  onSelect: (name: ChapterName) => void;
};


// Left rail. Pure presentation — autosave-flush-before-switch logic lives in
// the parent so the rail stays unit-testable without server coupling.
export function OutlineRail({ present, active, onSelect }: Props) {
  return (
    <nav aria-label="Chapters" className="w-48 shrink-0 border-r border-gray-200 py-4 px-2 space-y-1">
      <div className="text-xs uppercase tracking-wider text-gray-400 px-2 mb-2">Outline</div>
      {_ORDER.map(({ name, label }) => {
        const isPresent = present.includes(name);
        const isActive = name === active;
        return (
          <button
            key={name}
            disabled={!isPresent}
            aria-current={isActive ? "true" : undefined}
            onClick={() => onSelect(name)}
            className={
              "w-full text-left text-sm px-3 py-2 rounded-md transition-colors " +
              (isActive
                ? "bg-primary-100 text-primary-700 font-medium"
                : isPresent
                ? "text-gray-700 hover:bg-gray-100"
                : "text-gray-400 cursor-not-allowed")
            }
          >
            {label}
          </button>
        );
      })}
    </nav>
  );
}

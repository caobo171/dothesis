"use client";

import { useEffect, useRef } from "react";
import useSWR from "swr";

import { apiFetch } from "@/app/lib/api";
import {
  SKILLS_ENDPOINT,
  groupSkills,
  type Skill,
} from "@/app/lib/skills";

/** Square initial-avatar, matching the module chips elsewhere in chat. */
export function SkillAvatar({ name, size = 34 }: { name: string; size?: number }) {
  return (
    <span
      aria-hidden="true"
      style={{ width: size, height: size }}
      className="rounded-lg bg-primary-600 text-white font-extrabold inline-flex items-center justify-center text-[15px] shrink-0"
    >
      {name.slice(0, 1).toUpperCase()}
    </span>
  );
}

/**
 * Picker for the agent's real skills.
 *
 * The list comes from POST /skills/list, which reads the skills directory —
 * deliberately not a constant in the frontend. A hardcoded copy is how the logo
 * mark ended up stale on one surface out of four: the second list is always the
 * one nobody remembers to update.
 *
 * Module skills (m1-m5) are filtered out server-side. The agent already selects
 * those from `focus` and the left rail already navigates them, so listing them
 * here would make the picker read as a duplicate of the sidebar rather than as
 * "things I can ask for that I couldn't otherwise".
 */
export function SkillPicker({
  focusModule,
  selectedId,
  onSelect,
  onClose,
}: {
  focusModule?: string;
  selectedId?: string | null;
  onSelect: (skill: Skill | null) => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  const { data, isLoading } = useSWR<{ skills: Skill[] }>(
    SKILLS_ENDPOINT,
    (url: string) => apiFetch(url, { method: "POST" }),
  );
  const skills = data?.skills ?? [];
  const { suggested, rest } = groupSkills(skills, focusModule);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [onClose]);

  const Row = ({ s }: { s: Skill }) => (
    <button
      type="button"
      onClick={() => {
        onSelect(s);
        onClose();
      }}
      className={`w-full text-left flex items-start gap-3 px-4 py-2.5 hover:bg-ink-50 transition-colors ${
        s.id === selectedId ? "bg-primary-50" : ""
      }`}
    >
      <SkillAvatar name={s.name} />
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <span className="font-semibold text-[14px] text-ink-900">{s.name}</span>
          {s.suggested_for.map((m) => (
            <span
              key={m}
              className="text-[10.5px] font-semibold text-ink-500 bg-ink-100 rounded px-1.5 py-px"
            >
              {m}
            </span>
          ))}
        </span>
        {/* The SKILL.md description IS the "when to use this" — it was written
            to match how a student actually phrases the problem, so it is more
            useful to show verbatim than a marketing tagline would be. */}
        <span className="block text-[12.5px] text-ink-500 mt-0.5 line-clamp-2">
          {s.description}
        </span>
      </span>
    </button>
  );

  return (
    <div
      ref={ref}
      role="dialog"
      aria-label="Pick a skill"
      className="absolute bottom-full mb-2 left-0 w-[420px] max-w-[92vw] rounded-2xl border border-ink-200 bg-white shadow-xl overflow-hidden z-30"
    >
      <div className="px-4 pt-3.5 pb-2.5 border-b border-ink-100">
        <div className="font-bold text-[14.5px] text-ink-900">Pick a skill</div>
        <div className="text-[12.5px] text-ink-500 mt-0.5">
          Run one of DoThesis&apos;s specialised passes — still one thread.
        </div>
      </div>

      <div className="max-h-[46vh] overflow-y-auto py-1">
        {isLoading && (
          <div className="px-4 py-4 text-[12.5px] text-ink-500">Loading skills…</div>
        )}
        {!isLoading && skills.length === 0 && (
          <div className="px-4 py-4 text-[12.5px] text-ink-500">
            No extra skills available right now.
          </div>
        )}

        {suggested.length > 0 && (
          <>
            <div className="px-4 pt-2 pb-1 text-[10.5px] uppercase tracking-[0.08em] text-ink-400 font-semibold">
              Suggested for {focusModule}
            </div>
            {suggested.map((s) => (
              <Row key={s.id} s={s} />
            ))}
          </>
        )}

        {rest.length > 0 && (
          <>
            <div className="px-4 pt-2 pb-1 text-[10.5px] uppercase tracking-[0.08em] text-ink-400 font-semibold">
              {suggested.length > 0 ? "All skills" : "Skills"}
            </div>
            {rest.map((s) => (
              <Row key={s.id} s={s} />
            ))}
          </>
        )}
      </div>

      <button
        type="button"
        onClick={() => {
          onSelect(null);
          onClose();
        }}
        className="w-full text-left px-4 py-2.5 border-t border-ink-100 text-[13px] font-semibold text-ink-600 hover:bg-ink-50"
      >
        ← Use base DoThesis
      </button>
    </div>
  );
}

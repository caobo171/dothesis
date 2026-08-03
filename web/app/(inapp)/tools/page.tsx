"use client";

import { useState } from "react";
import { Feather, Ruler, BookCheck } from "lucide-react";

import { HumanizeTool } from "./_components/HumanizeTool";
import { RhythmTool } from "./_components/RhythmTool";
import { CitationTool } from "./_components/CitationTool";

/**
 * Standalone tools — text in, answer out. No project, no thread, no agent turn.
 *
 * The agent stays the product: it knows the citation style, the language, which
 * chapter, and what's already committed, so "fix my M2 and re-export" is agent
 * work. But a scoped job like "is this reference real" doesn't need any of that
 * context, and routing it through a turn charges the student for the whole
 * system prompt, every tool definition and the state header to answer a
 * question with one right answer.
 *
 * Nothing here is a second implementation. Each panel posts to an endpoint that
 * already existed and that the MCP connector already calls — the web app was
 * simply the only surface without a door onto them.
 */

const TOOLS = [
  { id: "humanize", name: "Humanize", icon: Feather,
    tagline: "Make drafted prose read as human-written" },
  { id: "rhythm", name: "Writing rhythm", icon: Ruler,
    tagline: "Measure how mechanical your sentences are" },
  { id: "citation", name: "Citation check", icon: BookCheck,
    tagline: "Does this source actually exist?" },
] as const;

type ToolId = (typeof TOOLS)[number]["id"];

export default function ToolsPage() {
  const [active, setActive] = useState<ToolId>("humanize");

  return (
    <div className="max-w-6xl mx-auto">
      <header className="mb-6">
        <h1 className="m-0 text-[26px] font-extrabold tracking-tight font-serif text-ink-900">
          Tools
        </h1>
        <p className="mt-1.5 mb-0 text-[13.5px] text-ink-500 max-w-2xl leading-relaxed">
          One job, one answer — no thesis project needed. For anything that needs
          to know your research, work in a thesis thread instead.
        </p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-[220px_1fr] gap-5 items-start">
        {/* Tool rail. Horizontally scrollable on mobile rather than stacked,
            so the panel stays above the fold on a phone. */}
        <nav className="flex md:flex-col gap-1.5 overflow-x-auto md:overflow-visible pb-1 md:pb-0">
          {TOOLS.map((t) => {
            const on = t.id === active;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setActive(t.id)}
                aria-current={on ? "page" : undefined}
                className={`flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-left transition-colors shrink-0 md:w-full ${
                  on
                    ? "bg-primary-50 text-primary-700 border border-primary-100"
                    : "text-ink-700 border border-transparent hover:bg-ink-100"
                }`}
              >
                <t.icon className="w-4 h-4 shrink-0" aria-hidden />
                <span className="min-w-0">
                  <span className="block text-[13.5px] font-semibold whitespace-nowrap">
                    {t.name}
                  </span>
                  <span className="hidden md:block text-[11px] text-ink-500 leading-snug mt-px">
                    {t.tagline}
                  </span>
                </span>
              </button>
            );
          })}
        </nav>

        <div className="min-w-0">
          {active === "humanize" && <HumanizeTool />}
          {active === "rhythm" && <RhythmTool />}
          {active === "citation" && <CitationTool />}
        </div>
      </div>
    </div>
  );
}

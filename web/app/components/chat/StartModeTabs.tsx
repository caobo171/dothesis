"use client";

import { useT } from "../../lib/i18n/LocaleProvider";
import type { MessageKey } from "../../lib/i18n/messages/en";
import type { StartMode } from "./ThesisComposer";

/**
 * Guided vs Auto Thesis, chosen before the student types anything.
 *
 * Lives outside ThesisComposer even though it started inside it. The composer
 * is the input; this is page chrome, and it renders at the TOP of the hero
 * block — above the heading, not just above the tagline.
 *
 * That order is load-bearing rather than decorative. Both the heading and the
 * tagline are per-mode text ("Analyze your thesis" vs "One topic, six
 * chapters."), so anything above these tabs describes a choice the student has
 * not been offered yet. Picking the mode is the first move on this screen;
 * everything below reacts to it.
 */
export function StartModeTabs({
  mode,
  onChange,
  busy = false,
}: {
  mode: StartMode;
  onChange: (mode: StartMode) => void;
  /** Mirrors the composer: nothing is switchable once a run is being started. */
  busy?: boolean;
}) {
  const t = useT();
  const modes: { id: StartMode; labelKey: MessageKey; hintKey: MessageKey }[] = [
    { id: "guided", labelKey: "new.mode.guided", hintKey: "new.mode.guided.hint" },
    { id: "auto_thesis", labelKey: "new.mode.auto", hintKey: "new.mode.auto.hint" },
  ];

  return (
    <div
      role="tablist"
      aria-label={t("new.mode.aria")}
      className="inline-flex rounded-full bg-ink-100 p-1"
    >
      {modes.map((m) => {
        const selected = mode === m.id;
        return (
          <button
            key={m.id}
            role="tab"
            type="button"
            aria-selected={selected}
            title={t(m.hintKey)}
            disabled={busy}
            onClick={() => onChange(m.id)}
            className={
              "rounded-full px-4 py-1.5 text-[13px] font-medium transition-colors disabled:opacity-50 " +
              (selected
                ? "bg-white text-ink-900 shadow-sm"
                : "text-ink-500 hover:text-ink-800")
            }
          >
            {t(m.labelKey)}
          </button>
        );
      })}
    </div>
  );
}

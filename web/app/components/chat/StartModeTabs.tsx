"use client";

import { useT } from "../../lib/i18n/LocaleProvider";
import type { MessageKey } from "../../lib/i18n/messages/en";
import type { StartMode } from "./ThesisComposer";

/**
 * Guided vs Auto Thesis, chosen before the student types anything.
 *
 * Lives outside ThesisComposer even though it started inside it. The composer
 * is the input; this is page chrome that sits in the hero block between the
 * heading and the mode's tagline. That order is load-bearing: the tagline
 * describes the SELECTED mode, so it has to come after the control that picks
 * it — with the tagline above, the page explained a choice the student had not
 * been offered yet.
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

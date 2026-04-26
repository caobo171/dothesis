'use client';

import { useSelector } from 'react-redux';
import { RootState } from '@/store/rootReducer';
import { AiMeter } from '@/components/ui/AiMeter';

export function OutputPane() {
  const { outputText, changes, aiScoreIn, aiScoreOut, isProcessing } = useSelector(
    (s: RootState) => s.humanizer
  );

  if (isProcessing) {
    return (
      <div className="flex-1 flex flex-col bg-white rounded-xl border border-rule overflow-hidden">
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-3" />
            <p className="text-sm text-ink-muted">Humanizing your text...</p>
          </div>
        </div>
      </div>
    );
  }

  if (!outputText) {
    return (
      <div className="flex-1 flex flex-col bg-white rounded-xl border border-rule overflow-hidden">
        <div className="flex-1 flex items-center justify-center">
          <p className="text-sm text-ink-muted">Output will appear here</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col bg-white rounded-xl border border-rule overflow-hidden">
      {/* Scores bar */}
      <div className="px-4 py-3 border-b border-rule flex items-center gap-6">
        <AiMeter score={aiScoreIn} label="Before" />
        <span className="text-ink-muted">→</span>
        <AiMeter score={aiScoreOut} label="After" />
      </div>

      {/* Rewritten text with diff highlights */}
      <div className="flex-1 p-4 overflow-auto">
        <div className="text-sm text-ink leading-relaxed whitespace-pre-wrap">
          {outputText}
        </div>

        {/* Changes list */}
        {changes.length > 0 && (
          <div className="mt-4 pt-4 border-t border-rule">
            <p className="text-xs font-semibold text-ink-soft mb-2">{changes.length} changes</p>
            <div className="space-y-2">
              {changes.slice(0, 10).map((c, i) => (
                <div key={i} className="text-xs">
                  <span className="line-through text-error/70">{c.original}</span>
                  <span className="mx-1 text-ink-muted">→</span>
                  <span className="text-success font-medium">{c.replacement}</span>
                </div>
              ))}
              {changes.length > 10 && (
                <p className="text-xs text-ink-muted">+{changes.length - 10} more changes</p>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2 border-t border-rule">
        <button
          onClick={() => navigator.clipboard.writeText(outputText)}
          className="text-xs text-primary font-medium hover:underline"
        >
          Copy to clipboard
        </button>
      </div>
    </div>
  );
}

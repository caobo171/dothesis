'use client';

import { useSelector, useDispatch } from 'react-redux';
import { clsx } from 'clsx';
import { Copy } from 'lucide-react';
import { toast } from 'react-toastify';
import { RootState } from '@/store/rootReducer';
import { setViewMode } from '@/store/slices/humanizerSlice';
import { AiMeter } from '@/components/ui/AiMeter';
import { PipelineSteps } from './PipelineSteps';
import { InlineDiffView } from './InlineDiffView';

export function OutputPane() {
  const dispatch = useDispatch();
  const {
    inputText,
    outputText,
    changes,
    aiScoreIn,
    aiScoreOut,
    isProcessing,
    maxStepReached,
    viewMode,
  } = useSelector((s: RootState) => s.humanizer);

  // Processing state: progress steps panel.
  if (isProcessing) {
    return (
      <div className="flex-1 flex flex-col bg-white rounded-xl border border-rule overflow-hidden">
        <div className="flex-1 flex items-center justify-center p-6">
          <PipelineSteps maxStepReached={maxStepReached} isProcessing={isProcessing} />
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
      {/* Score bar + view toggle */}
      <div className="px-4 py-3 border-b border-rule flex items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <AiMeter score={aiScoreIn} label="Before" />
          <span className="text-ink-muted">→</span>
          <AiMeter score={aiScoreOut} label="After" />
        </div>

        {/* Plain / Inline toggle. Inline only useful when the backend supplied
            a non-empty changes array. */}
        <div className="inline-flex items-center bg-bg-soft rounded-lg p-0.5 text-xs font-medium">
          <button
            type="button"
            onClick={() => dispatch(setViewMode('plain'))}
            className={clsx(
              'px-3 py-1 rounded-md transition',
              viewMode === 'plain' ? 'bg-white text-ink shadow-sm' : 'text-ink-muted hover:text-ink-soft'
            )}
          >
            Plain
          </button>
          <button
            type="button"
            onClick={() => dispatch(setViewMode('inline'))}
            disabled={changes.length === 0}
            className={clsx(
              'px-3 py-1 rounded-md transition',
              viewMode === 'inline'
                ? 'bg-white text-ink shadow-sm'
                : 'text-ink-muted hover:text-ink-soft',
              changes.length === 0 && 'opacity-50 cursor-not-allowed'
            )}
            title={changes.length === 0 ? 'No diff available' : 'Show inline changes'}
          >
            Inline diff
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 p-4 overflow-auto">
        {viewMode === 'inline' ? (
          <InlineDiffView inputText={inputText} changes={changes} />
        ) : (
          <div className="text-sm text-ink leading-relaxed whitespace-pre-wrap">{outputText}</div>
        )}

        {/* Compact change summary in plain mode only — keeps the inline view uncluttered */}
        {viewMode === 'plain' && changes.length > 0 && (
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
      <div className="px-4 py-2 border-t border-rule flex items-center justify-between">
        <button
          onClick={() => {
            navigator.clipboard.writeText(outputText);
            toast.success('Copied');
          }}
          className="flex items-center gap-1.5 text-xs text-primary font-medium hover:underline"
        >
          <Copy className="w-3 h-3" />
          Copy to clipboard
        </button>
      </div>
    </div>
  );
}

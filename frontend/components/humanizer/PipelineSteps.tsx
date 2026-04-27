'use client';

import { Check, Loader2 } from 'lucide-react';
import { clsx } from 'clsx';

// Three user-facing steps mapped from backend pipeline stages.
// Order matters — index is what humanizerSlice.maxStepReached compares against.
const STEPS = [
  'Analyzing draft',
  'Detecting AI patterns',
  'Rewriting in your voice',
];

type Props = {
  // Highest step reached so far. -1 if not started.
  maxStepReached: number;
  // True while the SSE stream is still open. When false, every reached step is "done".
  isProcessing: boolean;
};

export function PipelineSteps({ maxStepReached, isProcessing }: Props) {
  return (
    <ul className="space-y-3">
      {STEPS.map((label, i) => {
        // Pending = the pipeline hasn't gotten here yet.
        // Active  = we're currently on this step (highest reached AND still processing).
        // Done    = a later step has been reached, OR the pipeline finished altogether.
        const reached = i <= maxStepReached;
        const done = reached && (!isProcessing || i < maxStepReached);
        const active = reached && !done;

        return (
          <li key={label} className="flex items-center gap-3 text-base">
            <span
              className={clsx(
                'w-5 h-5 flex items-center justify-center rounded-full transition',
                done
                  ? 'bg-success/15 text-success'
                  : active
                    ? 'bg-bg-blue text-primary'
                    : 'bg-bg-soft text-ink-muted'
              )}
              aria-hidden="true"
            >
              {done ? (
                <Check className="w-3 h-3" strokeWidth={3} />
              ) : active ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <span className="w-1.5 h-1.5 rounded-full bg-current" />
              )}
            </span>
            <span
              className={clsx(
                'transition',
                done ? 'text-ink-muted' : active ? 'text-ink font-medium' : 'text-ink-muted',
              )}
            >
              {label}
              {active && <span className="ml-0.5 inline-block animate-pulse">…</span>}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export default PipelineSteps;

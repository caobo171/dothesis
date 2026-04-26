'use client';

import { clsx } from 'clsx';

interface AiMeterProps {
  score: number;
  label?: string;
}

// Decision: Flipped from "AI Score" (lower=better) to "Human Score" (higher=better).
// Users were confused seeing scores go DOWN after humanization — it looked like
// the tool was making things worse. Now 62% AI → shows as 38% human before,
// and 49% AI → shows as 51% human after. Higher = better = intuitive.
export function AiMeter({ score, label }: AiMeterProps) {
  const humanScore = 100 - score;
  const color =
    humanScore >= 70 ? 'bg-success' : humanScore >= 40 ? 'bg-warn' : 'bg-error';
  const textColor =
    humanScore >= 70 ? 'text-success' : humanScore >= 40 ? 'text-warn' : 'text-error';

  return (
    <div className="flex items-center gap-2">
      {label && <span className="text-xs text-ink-muted">{label}</span>}
      <div className="w-20 h-2 bg-rule rounded-full overflow-hidden">
        <div className={clsx('h-full rounded-full transition-all', color)} style={{ width: `${humanScore}%` }} />
      </div>
      <span className={clsx('text-xs font-mono font-semibold', textColor)}>{humanScore}%</span>
    </div>
  );
}

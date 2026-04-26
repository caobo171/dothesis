'use client';

import { clsx } from 'clsx';

interface AiMeterProps {
  score: number;
  label?: string;
}

export function AiMeter({ score, label }: AiMeterProps) {
  const color =
    score <= 30 ? 'bg-success' : score <= 60 ? 'bg-warn' : 'bg-error';
  const textColor =
    score <= 30 ? 'text-success' : score <= 60 ? 'text-warn' : 'text-error';

  return (
    <div className="flex items-center gap-2">
      {label && <span className="text-xs text-ink-muted">{label}</span>}
      <div className="w-20 h-2 bg-rule rounded-full overflow-hidden">
        <div className={clsx('h-full rounded-full transition-all', color)} style={{ width: `${score}%` }} />
      </div>
      <span className={clsx('text-xs font-mono font-semibold', textColor)}>{score}%</span>
    </div>
  );
}

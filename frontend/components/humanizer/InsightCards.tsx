'use client';

import { useSelector } from 'react-redux';
import { RootState } from '@/store/rootReducer';
import { clsx } from 'clsx';

export function InsightCards() {
  const { aiScoreIn, aiScoreOut, changes } = useSelector((s: RootState) => s.humanizer);

  const passedThreshold = aiScoreOut <= 30;
  const improvement = aiScoreIn - aiScoreOut;

  const cards = [
    {
      label: 'AI Score',
      value: `${aiScoreOut}%`,
      sub: aiScoreOut > 0 ? `was ${aiScoreIn}%` : '—',
      color: aiScoreOut <= 30 ? 'text-success' : aiScoreOut <= 60 ? 'text-warn' : 'text-error',
    },
    {
      label: 'Rewrites',
      value: `${changes.length}`,
      sub: 'phrases changed',
      color: 'text-primary',
    },
    {
      label: 'Improvement',
      value: improvement > 0 ? `−${improvement}%` : '—',
      sub: 'AI score drop',
      color: 'text-purple',
    },
    {
      label: 'Status',
      value: passedThreshold && aiScoreOut > 0 ? 'Pass' : aiScoreOut > 0 ? 'Needs work' : '—',
      sub: 'detection test',
      color: passedThreshold && aiScoreOut > 0 ? 'text-success' : 'text-warn',
    },
  ];

  return (
    <div className="grid grid-cols-4 gap-3">
      {cards.map((card) => (
        <div key={card.label} className="bg-white rounded-xl border border-rule p-4">
          <p className="text-xs text-ink-muted mb-1">{card.label}</p>
          <p className={clsx('text-2xl font-mono font-bold', card.color)}>{card.value}</p>
          <p className="text-xs text-ink-muted mt-0.5">{card.sub}</p>
        </div>
      ))}
    </div>
  );
}

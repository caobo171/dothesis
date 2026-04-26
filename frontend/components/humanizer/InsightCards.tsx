'use client';

import { useSelector } from 'react-redux';
import { RootState } from '@/store/rootReducer';
import { clsx } from 'clsx';

// Decision: Reframed all metrics as "Human Score" (higher=better) instead of "AI Score"
// (lower=better). Old UX showed "−6%" improvement which looked negative/bad.
// Now shows "+13% more human" which is clearly positive. Threshold for "Pass"
// is humanAfter >= 70 (i.e. AI score <= 30).
export function InsightCards() {
  const { aiScoreIn, aiScoreOut, changes } = useSelector((s: RootState) => s.humanizer);

  const humanBefore = 100 - aiScoreIn;
  const humanAfter = 100 - aiScoreOut;
  const improvement = humanAfter - humanBefore;
  const passed = humanAfter >= 70;

  const cards = [
    {
      label: 'Human Score',
      value: aiScoreOut > 0 ? `${humanAfter}%` : '—',
      sub: aiScoreOut > 0 ? `was ${humanBefore}%` : '—',
      color: humanAfter >= 70 ? 'text-success' : humanAfter >= 40 ? 'text-warn' : 'text-error',
    },
    {
      label: 'Rewrites',
      value: `${changes.length}`,
      sub: 'phrases changed',
      color: 'text-primary',
    },
    {
      label: 'Improvement',
      value: improvement > 0 ? `+${improvement}%` : '—',
      sub: 'more human',
      color: 'text-success',
    },
    {
      label: 'Status',
      value: passed && aiScoreOut > 0 ? 'Pass' : aiScoreOut > 0 ? 'Needs work' : '—',
      sub: 'detection test',
      color: passed && aiScoreOut > 0 ? 'text-success' : 'text-warn',
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

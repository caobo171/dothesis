'use client';

import { useSelector, useDispatch } from 'react-redux';
import { RootState } from '@/store/rootReducer';
import { setTone, setStrength, setLengthMode } from '@/store/slices/humanizerSlice';
import { clsx } from 'clsx';

const TONES = [
  { value: 'academic', label: 'Academic' },
  { value: 'casual', label: 'Casual' },
  { value: 'persuasive', label: 'Persuasive' },
];

const LENGTHS = [
  { value: 'shorter', label: 'Shorter' },
  { value: 'match', label: 'Match' },
  { value: 'longer', label: 'Longer' },
];

export function HumToolbar() {
  const dispatch = useDispatch();
  const { tone, strength, lengthMode } = useSelector((s: RootState) => s.humanizer);

  return (
    <div className="flex items-center gap-6 px-5 py-3 border-b border-rule bg-white">
      {/* Tone pills */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-ink-muted mr-1">Tone</span>
        {TONES.map((t) => (
          <button
            key={t.value}
            onClick={() => dispatch(setTone(t.value))}
            className={clsx(
              'px-3 py-1 rounded-full text-xs font-medium transition',
              tone === t.value
                ? 'bg-primary text-white'
                : 'bg-bg-soft text-ink-soft hover:bg-rule'
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Strength slider */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-ink-muted">Strength</span>
        <input
          type="range"
          min={0}
          max={100}
          value={strength}
          onChange={(e) => dispatch(setStrength(Number(e.target.value)))}
          className="w-24 accent-primary"
        />
        <span className="text-xs font-mono text-ink-soft w-8">{strength}%</span>
      </div>

      {/* Length toggle */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-ink-muted mr-1">Length</span>
        {LENGTHS.map((l) => (
          <button
            key={l.value}
            onClick={() => dispatch(setLengthMode(l.value))}
            className={clsx(
              'px-3 py-1 rounded-full text-xs font-medium transition',
              lengthMode === l.value
                ? 'bg-purple text-white'
                : 'bg-bg-soft text-ink-soft hover:bg-rule'
            )}
          >
            {l.label}
          </button>
        ))}
      </div>
    </div>
  );
}

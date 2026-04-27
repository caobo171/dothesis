'use client';

import { useState, useMemo } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { RootState } from '@/store/rootReducer';
import { setProcessing, setResult, resetOutput, setCurrentStage } from '@/store/slices/humanizerSlice';
import { HumToolbar } from './HumToolbar';
import { InputPane } from './InputPane';
import { OutputPane } from './OutputPane';
import { InsightCards } from './InsightCards';
import { HumanizeConfirmModal } from './HumanizeConfirmModal';
import { API_URL } from '@/lib/core/Constants';
import Cookie from '@/lib/core/fetch/Cookie';
import { toast } from 'react-toastify';
import { useBalance } from '@/hooks/credit';

// Frontend mirror of backend's HumanizerService.calculateCredits.
// Keep these formulas in lockstep — the user must see the exact number the
// backend will deduct, otherwise the confirm modal becomes a lie.
// Rate: 1 credit per 50 words, minimum 2 credits per run (2× the original).
function calculateCreditCost(wordCount: number): number {
  return Math.max(2, Math.ceil(wordCount / 50));
}

export function HumBoard() {
  const dispatch = useDispatch();
  const { inputText, tone, strength, lengthMode, isProcessing, outputText, currentStage } = useSelector(
    (s: RootState) => s.humanizer
  );
  const { balance, mutate: refreshBalance } = useBalance();

  const [confirmOpen, setConfirmOpen] = useState(false);

  // Live word + cost count so the confirm modal (and a future inline preview)
  // reflects what the user just typed without a server round trip.
  const wordCount = useMemo(
    () => inputText.trim().split(/\s+/).filter(Boolean).length,
    [inputText],
  );
  const creditCost = useMemo(() => calculateCreditCost(wordCount), [wordCount]);

  const runHumanize = async () => {
    dispatch(setProcessing(true));
    dispatch(resetOutput());

    try {
      const response = await fetch(`${API_URL}/api/humanize/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: inputText,
          tone,
          strength,
          lengthMode,
          access_token: Cookie.fromDocument('access_token'),
        }),
      });

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No stream reader');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(line.slice(6));

            if (data.type === 'done') {
              dispatch(
                setResult({
                  outputText: data.rewrittenText,
                  changes: data.changes || [],
                  aiScoreIn: data.aiScoreIn,
                  aiScoreOut: data.aiScoreOut,
                  jobId: data.jobId,
                })
              );
              dispatch(setCurrentStage(''));
              refreshBalance();
            } else if (data.type === 'stage') {
              const stageLabel = data.iteration
                ? `${data.stage} (pass ${data.iteration})`
                : data.stage;
              dispatch(setCurrentStage(stageLabel));
            } else if (data.type === 'score') {
              dispatch(setCurrentStage(`scoring (pass ${data.iteration}: ${data.score})`));
            } else if (data.type === 'ai_score_in') {
              dispatch(setCurrentStage('analyzing input...'));
            } else if (data.type === 'error') {
              toast.error(data.message);
              dispatch(setProcessing(false));
              dispatch(setCurrentStage(''));
            }
          } catch {
            // partial JSON, skip
          }
        }
      }
    } catch (err: any) {
      toast.error('Humanization failed');
      dispatch(setProcessing(false));
    }
  };

  const handleHumanizeClick = () => {
    if (!inputText.trim()) {
      toast.error('Please enter some text first');
      return;
    }
    // Open the confirm modal instead of running directly. The user sees the
    // exact credit cost and current/after balance before committing.
    setConfirmOpen(true);
  };

  const handleConfirm = () => {
    setConfirmOpen(false);
    runHumanize();
  };

  return (
    <div className="space-y-4">
      <HumToolbar />

      <div className="flex gap-4" style={{ minHeight: 400 }}>
        <InputPane />
        <OutputPane />
      </div>

      {/* Action button — kicks off the confirm modal, not the run itself. */}
      <div className="flex justify-center">
        <button
          onClick={handleHumanizeClick}
          disabled={isProcessing || !inputText.trim()}
          className="px-8 py-3 bg-primary text-white rounded-xl font-semibold text-sm hover:bg-primary-dark transition disabled:opacity-50 shadow-sm"
        >
          {isProcessing
            ? `Humanizing... ${currentStage}`
            : wordCount > 0
              ? `Humanize · ${creditCost} credits`
              : 'Humanize'}
        </button>
      </div>

      {outputText && <InsightCards />}

      <HumanizeConfirmModal
        open={confirmOpen}
        wordCount={wordCount}
        creditCost={creditCost}
        balance={balance}
        tone={tone}
        strength={strength}
        lengthMode={lengthMode}
        busy={isProcessing}
        onConfirm={handleConfirm}
        onClose={() => setConfirmOpen(false)}
      />
    </div>
  );
}

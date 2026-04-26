'use client';

import { useSelector, useDispatch } from 'react-redux';
import { RootState } from '@/store/rootReducer';
import { setProcessing, setResult, resetOutput } from '@/store/slices/humanizerSlice';
import { HumToolbar } from './HumToolbar';
import { InputPane } from './InputPane';
import { OutputPane } from './OutputPane';
import { InsightCards } from './InsightCards';
import { API_URL } from '@/lib/core/Constants';
import Cookie from '@/lib/core/fetch/Cookie';
import { toast } from 'react-toastify';
import { useBalance } from '@/hooks/credit';

export function HumBoard() {
  const dispatch = useDispatch();
  const { inputText, tone, strength, lengthMode, isProcessing, outputText } = useSelector(
    (s: RootState) => s.humanizer
  );
  const { mutate: refreshBalance } = useBalance();

  const handleHumanize = async () => {
    if (!inputText.trim()) {
      toast.error('Please enter some text first');
      return;
    }

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
              refreshBalance();
            } else if (data.type === 'error') {
              toast.error(data.message);
              dispatch(setProcessing(false));
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

  return (
    <div className="space-y-4">
      <HumToolbar />

      <div className="flex gap-4" style={{ minHeight: 400 }}>
        <InputPane />
        <OutputPane />
      </div>

      {/* Action button */}
      <div className="flex justify-center">
        <button
          onClick={handleHumanize}
          disabled={isProcessing || !inputText.trim()}
          className="px-8 py-3 bg-primary text-white rounded-xl font-semibold text-sm hover:bg-primary-dark transition disabled:opacity-50 shadow-sm"
        >
          {isProcessing ? 'Humanizing...' : 'Humanize'}
        </button>
      </div>

      {/* Insight cards */}
      {outputText && <InsightCards />}
    </div>
  );
}

'use client';

import { useState, useEffect, useRef } from 'react';
import { io, Socket } from 'socket.io-client';
import { toast } from 'react-toastify';
import { clsx } from 'clsx';
import Fetch from '@/lib/core/fetch/Fetch';
import { Code, SOCKET_URL } from '@/lib/core/Constants';
import { PlagiarismMatch } from '@/store/types';
import { useBalance } from '@/hooks/credit';

export function PlagiarismView() {
  const [text, setText] = useState('');
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<string>('idle');
  const [overallScore, setOverallScore] = useState(0);
  const [matches, setMatches] = useState<PlagiarismMatch[]>([]);
  const socketRef = useRef<Socket | null>(null);
  const { mutate: refreshBalance } = useBalance();

  useEffect(() => {
    const socket = io(SOCKET_URL);
    socketRef.current = socket;

    socket.on('plagiarism:progress', (data: any) => {
      if (data.status === 'done') {
        setStatus('done');
        setOverallScore(data.overallScore);
        setMatches(data.matches);
        refreshBalance();
      } else if (data.status === 'failed') {
        setStatus('failed');
        toast.error(data.error || 'Check failed');
      } else {
        setStatus(data.status);
      }
    });

    return () => {
      socket.disconnect();
    };
  }, [refreshBalance]);

  useEffect(() => {
    if (jobId && socketRef.current) {
      socketRef.current.emit('join', `plagiarism:${jobId}`);
    }
  }, [jobId]);

  const handleCheck = async () => {
    if (!text.trim()) {
      toast.error('Enter text to check');
      return;
    }
    setStatus('pending');
    setMatches([]);
    setOverallScore(0);

    const res = await Fetch.postWithAccessToken<any>('/api/plagiarism/check', { text });
    if (res.data.code === Code.Success) {
      setJobId(res.data.data.jobId);
    } else {
      toast.error(res.data.message);
      setStatus('idle');
    }
  };

  const isProcessing = ['pending', 'processing'].includes(status);

  const scoreColor = overallScore >= 80 ? 'text-error' : overallScore >= 40 ? 'text-warn' : 'text-success';
  const scoreBg = overallScore >= 80 ? 'stroke-error' : overallScore >= 40 ? 'stroke-warn' : 'stroke-success';

  return (
    <div className="space-y-4">
      {/* Input */}
      <div className="bg-white rounded-xl border border-rule overflow-hidden">
        <div className="p-4">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Paste your text to check for plagiarism..."
            className="w-full min-h-[200px] resize-none outline-none text-sm text-ink leading-relaxed"
          />
        </div>
        <div className="px-4 py-3 border-t border-rule">
          <button
            onClick={handleCheck}
            disabled={isProcessing || !text.trim()}
            className="px-6 py-2 bg-purple text-white rounded-lg text-sm font-medium hover:opacity-90 transition disabled:opacity-50"
          >
            {isProcessing ? 'Checking...' : 'Check Plagiarism (5 credits)'}
          </button>
        </div>
      </div>

      {/* Loading */}
      {isProcessing && (
        <div className="bg-white rounded-xl border border-rule p-8 text-center">
          <div className="w-8 h-8 border-2 border-purple border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-sm text-ink-soft">Checking for plagiarism...</p>
        </div>
      )}

      {/* Results */}
      {status === 'done' && (
        <div className="grid grid-cols-3 gap-4">
          {/* Score circle */}
          <div className="bg-white rounded-xl border border-rule p-6 flex flex-col items-center justify-center">
            <svg width="120" height="120" viewBox="0 0 120 120">
              <circle cx="60" cy="60" r="50" fill="none" stroke="#ECEDF3" strokeWidth="8" />
              <circle
                cx="60"
                cy="60"
                r="50"
                fill="none"
                className={scoreBg}
                strokeWidth="8"
                strokeDasharray={`${(overallScore / 100) * 314} 314`}
                strokeLinecap="round"
                transform="rotate(-90 60 60)"
              />
            </svg>
            <p className={clsx('text-3xl font-mono font-bold mt-2', scoreColor)}>{overallScore}%</p>
            <p className="text-xs text-ink-muted mt-1">similarity score</p>
          </div>

          {/* Matches list */}
          <div className="col-span-2 bg-white rounded-xl border border-rule overflow-hidden">
            <div className="px-4 py-3 border-b border-rule">
              <h3 className="text-xs font-semibold text-ink-soft">
                {matches.length} match{matches.length !== 1 ? 'es' : ''} found
              </h3>
            </div>
            <div className="divide-y divide-rule max-h-96 overflow-auto">
              {matches.length === 0 && (
                <div className="p-6 text-center text-sm text-ink-muted">No matches found</div>
              )}
              {matches.map((match, i) => (
                <div key={i} className="px-4 py-3">
                  <div className="flex items-center gap-2 mb-1">
                    <span
                      className={clsx(
                        'text-[10px] font-bold uppercase px-1.5 py-0.5 rounded',
                        match.severity === 'high'
                          ? 'bg-error/10 text-error'
                          : match.severity === 'medium'
                            ? 'bg-warn/10 text-warn'
                            : 'bg-success/10 text-success'
                      )}
                    >
                      {match.severity}
                    </span>
                    <span className="text-xs font-mono text-ink-soft">{match.similarity}%</span>
                  </div>
                  <p className="text-sm text-ink">{match.sourceTitle}</p>
                  {match.sourceUrl && (
                    <a
                      href={match.sourceUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-primary hover:underline"
                    >
                      {match.sourceUrl}
                    </a>
                  )}
                  {match.matchedText && (
                    <p className="text-xs text-ink-muted mt-1 italic">"{match.matchedText.slice(0, 150)}..."</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

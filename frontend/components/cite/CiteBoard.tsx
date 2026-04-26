'use client';

import { useSelector, useDispatch } from 'react-redux';
import { RootState } from '@/store/rootReducer';
import {
  setStyle,
  setCiteInput,
  startJob,
  updateStatus,
  setResults,
  acceptClaim,
  removeClaim,
} from '@/store/slices/autoCiteSlice';
import { ClaimPopover } from './ClaimPopover';
import { SourceList } from './SourceList';
import { clsx } from 'clsx';
import { toast } from 'react-toastify';
import { useEffect, useRef } from 'react';
import { io, Socket } from 'socket.io-client';
import Fetch from '@/lib/core/fetch/Fetch';
import { Code, SOCKET_URL } from '@/lib/core/Constants';
import { useBalance } from '@/hooks/credit';

const STYLES = ['apa', 'mla', 'chicago', 'harvard', 'ieee'];

const STATUS_LABELS: Record<string, string> = {
  pending: 'Starting...',
  extracting: 'Extracting claims...',
  searching: 'Searching databases...',
  matching: 'Matching sources...',
  formatting: 'Formatting citations...',
  done: 'Complete',
  failed: 'Failed',
};

export function CiteBoard() {
  const dispatch = useDispatch();
  const { jobId, status, style, claims, sources, inputText } = useSelector(
    (s: RootState) => s.autoCite
  );
  const { mutate: refreshBalance } = useBalance();
  const socketRef = useRef<Socket | null>(null);

  useEffect(() => {
    const socket = io(SOCKET_URL);
    socketRef.current = socket;

    socket.on('autocite:progress', (data: any) => {
      if (data.status === 'done') {
        dispatch(setResults({ claims: data.claims, sources: data.sources }));
        refreshBalance();
      } else if (data.status === 'failed') {
        dispatch(updateStatus('failed'));
        toast.error(data.error || 'Analysis failed');
      } else {
        dispatch(updateStatus(data.status));
      }
    });

    return () => {
      socket.disconnect();
    };
  }, [dispatch, refreshBalance]);

  useEffect(() => {
    if (jobId && socketRef.current) {
      socketRef.current.emit('join', `autocite:${jobId}`);
    }
  }, [jobId]);

  const handleAnalyze = async () => {
    if (!inputText.trim()) {
      toast.error('Please enter your essay text');
      return;
    }

    try {
      const res = await Fetch.postWithAccessToken<any>('/api/cite/analyze', {
        text: inputText,
        style,
      });

      if (res.data.code === Code.Success) {
        dispatch(startJob(res.data.data.jobId));
      } else {
        toast.error(res.data.message);
      }
    } catch {
      toast.error('Failed to start analysis');
    }
  };

  const handleAccept = async (claimIndex: number, sourceId: string) => {
    dispatch(acceptClaim({ claimIndex, sourceId }));
    await Fetch.postWithAccessToken('/api/cite/accept', { jobId, claimIndex, sourceId });
  };

  const handleRemove = async (claimIndex: number) => {
    dispatch(removeClaim(claimIndex));
    await Fetch.postWithAccessToken('/api/cite/remove', { jobId, claimIndex });
  };

  const isProcessing = ['pending', 'extracting', 'searching', 'matching', 'formatting'].includes(status);

  return (
    <div className="space-y-4">
      {/* Style selector + analyze button */}
      <div className="flex items-center gap-4 bg-white rounded-xl border border-rule px-5 py-3">
        <span className="text-xs font-medium text-ink-muted">Citation style</span>
        <div className="flex gap-1">
          {STYLES.map((s) => (
            <button
              key={s}
              onClick={() => dispatch(setStyle(s))}
              className={clsx(
                'px-3 py-1 rounded-full text-xs font-medium uppercase transition',
                style === s ? 'bg-primary text-white' : 'bg-bg-soft text-ink-soft hover:bg-rule'
              )}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* Input + results layout */}
      <div className="grid grid-cols-2 gap-4" style={{ minHeight: 400 }}>
        {/* Left: Input / Claims */}
        <div className="bg-white rounded-xl border border-rule overflow-hidden flex flex-col">
          {status === 'idle' ? (
            <>
              <div className="p-4 flex-1">
                <textarea
                  value={inputText}
                  onChange={(e) => dispatch(setCiteInput(e.target.value))}
                  placeholder="Paste your essay here to find citations..."
                  className="w-full h-full min-h-[300px] resize-none outline-none text-sm text-ink leading-relaxed"
                />
              </div>
              <div className="px-4 py-3 border-t border-rule">
                <button
                  onClick={handleAnalyze}
                  disabled={!inputText.trim()}
                  className="px-6 py-2 bg-primary text-white rounded-lg text-sm font-medium hover:bg-primary-dark transition disabled:opacity-50"
                >
                  Analyze & Find Citations
                </button>
              </div>
            </>
          ) : isProcessing ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                <p className="text-sm text-ink-soft font-medium">{STATUS_LABELS[status] || status}</p>
              </div>
            </div>
          ) : (
            <div className="flex-1 overflow-auto p-4 space-y-3">
              <p className="text-xs font-semibold text-ink-soft mb-2">
                {claims.length} claims found
              </p>
              {claims.map((claim, i) => (
                <div key={i} className="space-y-2">
                  <p className={clsx(
                    'text-sm leading-relaxed px-2 py-1 rounded',
                    claim.status === 'cited' ? 'bg-bg-blue' : 'bg-bg-soft'
                  )}>
                    {claim.text}
                  </p>
                  <ClaimPopover
                    claim={claim}
                    claimIndex={i}
                    sources={sources}
                    onAccept={handleAccept}
                    onRemove={handleRemove}
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right: Bibliography */}
        <div className="bg-white rounded-xl border border-rule overflow-hidden">
          <SourceList sources={sources} claims={claims} />
        </div>
      </div>
    </div>
  );
}

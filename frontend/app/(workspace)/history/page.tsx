'use client';

import { useHumanizerHistory, useHumanizerJob } from '@/hooks/humanizer';
import { AiMeter } from '@/components/ui/AiMeter';
import { useState } from 'react';
import { clsx } from 'clsx';

export default function HistoryPage() {
  const { jobs } = useHumanizerHistory();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { job: selectedJob } = useHumanizerJob(selectedId);

  return (
    <div className="flex gap-4" style={{ minHeight: 500 }}>
      {/* Job list */}
      <div className="w-80 bg-white rounded-xl border border-rule overflow-hidden">
        <div className="px-4 py-3 border-b border-rule">
          <h2 className="text-sm font-semibold text-ink">History</h2>
        </div>
        <div className="divide-y divide-rule overflow-auto" style={{ maxHeight: 'calc(100vh - 200px)' }}>
          {jobs.length === 0 && (
            <div className="p-6 text-center text-sm text-ink-muted">No humanize runs yet</div>
          )}
          {jobs.map((job: any) => (
            <button
              key={job._id}
              onClick={() => setSelectedId(job._id)}
              className={clsx(
                'w-full text-left px-4 py-3 hover:bg-bg-soft transition',
                selectedId === job._id && 'bg-bg-blue'
              )}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-ink capitalize">{job.tone}</span>
                <span className={clsx(
                  'text-xs px-1.5 py-0.5 rounded',
                  job.status === 'completed' ? 'bg-success/10 text-success' : 'bg-error/10 text-error'
                )}>
                  {job.status}
                </span>
              </div>
              <div className="flex items-center gap-3 mt-1">
                <span className="text-[10px] text-ink-muted">
                  Score: {job.aiScoreIn}% → {job.aiScoreOut}%
                </span>
                <span className="text-[10px] text-ink-muted">
                  {new Date(job.createdAt).toLocaleDateString()}
                </span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Detail panel */}
      <div className="flex-1 bg-white rounded-xl border border-rule overflow-hidden">
        {!selectedJob ? (
          <div className="h-full flex items-center justify-center text-sm text-ink-muted">
            Select a run to view details
          </div>
        ) : (
          <div className="p-6 space-y-4">
            <div className="flex items-center gap-6">
              <AiMeter score={selectedJob.aiScoreIn} label="Before" />
              <span className="text-ink-muted">→</span>
              <AiMeter score={selectedJob.aiScoreOut} label="After" />
              <span className="text-xs text-ink-muted ml-auto">
                {selectedJob.changesCount} changes | {selectedJob.creditsUsed} credits
              </span>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <h3 className="text-xs font-semibold text-ink-soft mb-2">Original</h3>
                <div className="p-3 bg-bg-soft rounded-lg text-sm text-ink leading-relaxed max-h-96 overflow-auto">
                  {selectedJob.inputText}
                </div>
              </div>
              <div>
                <h3 className="text-xs font-semibold text-ink-soft mb-2">Humanized</h3>
                <div className="p-3 bg-bg-blue rounded-lg text-sm text-ink leading-relaxed max-h-96 overflow-auto">
                  {selectedJob.outputText}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

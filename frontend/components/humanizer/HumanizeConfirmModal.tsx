'use client';

import { Fragment } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { Zap, AlertTriangle } from 'lucide-react';

// Confirm-modal shown before a humanize run. Lets the user see exactly how
// many credits the run will consume against their current balance, so they
// don't get surprised by the deduction. Calculated client-side using the same
// formula the backend uses (max(1, ceil(words/100))).

type Props = {
  open: boolean;
  // Live-calculated counts so the user sees the numbers as soon as they paste.
  wordCount: number;
  creditCost: number;
  balance: number;
  // Tone/strength/length picked in the toolbar — surfaced here so the user
  // can sanity-check the configuration without dismissing the modal.
  tone: string;
  strength: number;
  lengthMode: string;
  busy: boolean;
  onConfirm: () => void;
  onClose: () => void;
};

export function HumanizeConfirmModal({
  open,
  wordCount,
  creditCost,
  balance,
  tone,
  strength,
  lengthMode,
  busy,
  onConfirm,
  onClose,
}: Props) {
  const insufficient = balance < creditCost;
  const remainingAfter = Math.max(0, balance - creditCost);

  return (
    <Transition appear show={open} as={Fragment}>
      <Dialog as="div" className="relative z-30" onClose={busy ? () => undefined : onClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-150"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-100"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-ink/50 backdrop-blur-sm" />
        </Transition.Child>

        <div className="fixed inset-0 flex items-center justify-center p-4">
          <Transition.Child
            as={Fragment}
            enter="ease-out duration-150"
            enterFrom="opacity-0 scale-95"
            enterTo="opacity-100 scale-100"
            leave="ease-in duration-100"
            leaveFrom="opacity-100 scale-100"
            leaveTo="opacity-0 scale-95"
          >
            <Dialog.Panel className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
              {/* Headline */}
              <div className="flex items-start gap-3 mb-5">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary to-purple flex items-center justify-center text-white">
                  <Zap className="w-5 h-5 fill-current" />
                </div>
                <div>
                  <Dialog.Title className="text-lg font-semibold text-ink">Humanize draft?</Dialog.Title>
                  <p className="text-sm text-ink-muted mt-0.5">
                    Review how this run uses your credits.
                  </p>
                </div>
              </div>

              {/* Cost breakdown */}
              <div className="rounded-xl border border-rule bg-bg-soft p-4 mb-4">
                <div className="flex items-baseline justify-between mb-3">
                  <span className="text-xs uppercase tracking-wider text-ink-muted">Cost</span>
                  <div className="flex items-baseline gap-1">
                    <span className="text-2xl font-semibold text-ink font-mono">{creditCost}</span>
                    <span className="text-xs text-ink-muted">credits</span>
                  </div>
                </div>
                <div className="text-xs text-ink-muted">
                  {wordCount.toLocaleString()} word{wordCount === 1 ? '' : 's'}
                  {' · 1 credit per 50 words, minimum 2'}
                </div>
              </div>

              {/* Balance */}
              <div className="grid grid-cols-2 gap-3 mb-5">
                <Stat label="Current balance" value={balance} />
                <Stat
                  label="After this run"
                  value={remainingAfter}
                  tone={insufficient ? 'error' : remainingAfter < 10 ? 'warn' : 'default'}
                />
              </div>

              {/* Insufficient warning */}
              {insufficient && (
                <div className="flex items-start gap-2 mb-4 rounded-lg border border-error/30 bg-error/5 p-3 text-xs text-error">
                  <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                  <span>
                    Not enough credits. You need <strong>{creditCost - balance}</strong> more
                    to run this humanization. Top up from the Credits pill in the header.
                  </span>
                </div>
              )}

              {/* Settings recap */}
              <dl className="rounded-xl border border-rule p-3 mb-5 text-xs">
                <Recap k="Tone" v={tone} />
                <Recap k="Strength" v={`${strength}%`} />
                <Recap k="Length" v={lengthMode} />
              </dl>

              {/* Actions */}
              <div className="flex items-center justify-end gap-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={onClose}
                  className="px-4 py-2 rounded-lg border border-rule text-sm text-ink-soft hover:bg-bg-soft transition disabled:opacity-60"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={busy || insufficient}
                  onClick={onConfirm}
                  className="px-4 py-2 rounded-lg bg-primary text-white text-sm font-semibold hover:bg-primary-dark transition disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {busy ? 'Starting…' : `Use ${creditCost} credits`}
                </button>
              </div>
            </Dialog.Panel>
          </Transition.Child>
        </div>
      </Dialog>
    </Transition>
  );
}

function Stat({
  label,
  value,
  tone = 'default',
}: {
  label: string;
  value: number;
  tone?: 'default' | 'warn' | 'error';
}) {
  const valueClass =
    tone === 'error' ? 'text-error' : tone === 'warn' ? 'text-warn' : 'text-ink';
  return (
    <div className="rounded-xl border border-rule p-3">
      <div className="text-xs uppercase tracking-wider text-ink-muted mb-1">{label}</div>
      <div className={`text-xl font-semibold font-mono ${valueClass}`}>{value.toLocaleString()}</div>
    </div>
  );
}

function Recap({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between py-1">
      <dt className="text-ink-muted">{k}</dt>
      <dd className="font-medium text-ink capitalize">{v}</dd>
    </div>
  );
}

export default HumanizeConfirmModal;

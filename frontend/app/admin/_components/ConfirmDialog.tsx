// frontend/app/admin/_components/ConfirmDialog.tsx
//
// Generic confirm dialog for destructive admin actions. Built on @headlessui/react
// so focus trapping, escape-to-close, and accessibility are handled.

'use client';

import React, { Fragment } from 'react';
import { Dialog, Transition } from '@headlessui/react';

type Props = {
  open: boolean;
  title: string;
  description?: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  // Set to true while the action is in flight to disable buttons.
  busy?: boolean;
  // 'danger' uses red confirm button; 'primary' uses blue.
  tone?: 'danger' | 'primary';
  onConfirm: () => void;
  onClose: () => void;
};

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  busy,
  tone = 'primary',
  onConfirm,
  onClose,
}: Props) {
  const confirmClass =
    tone === 'danger'
      ? 'bg-red-600 hover:bg-red-700 disabled:bg-red-400'
      : 'bg-gray-900 hover:bg-gray-800 disabled:bg-gray-500';

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
          <div className="fixed inset-0 bg-black/40" />
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
            <Dialog.Panel className="w-full max-w-md rounded-lg bg-white p-5 shadow-xl">
              <Dialog.Title className="text-base font-semibold text-gray-900">{title}</Dialog.Title>
              {description && <div className="mt-2 text-sm text-gray-600">{description}</div>}
              <div className="mt-5 flex items-center justify-end gap-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={onClose}
                  className="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {cancelLabel}
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={onConfirm}
                  className={`rounded px-3 py-1.5 text-sm font-medium text-white disabled:cursor-not-allowed ${confirmClass}`}
                >
                  {busy ? 'Working…' : confirmLabel}
                </button>
              </div>
            </Dialog.Panel>
          </Transition.Child>
        </div>
      </Dialog>
    </Transition>
  );
}

export default ConfirmDialog;

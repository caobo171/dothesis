"use client";

import {
  Dialog,
  DialogPanel,
  DialogTitle,
  Transition,
  TransitionChild,
} from "@headlessui/react";
import { ExclamationTriangleIcon } from "@heroicons/react/24/outline";
import { Fragment, type ReactNode } from "react";

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  description: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  destructive = false,
  busy = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <Transition show={open} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={busy ? () => {} : onCancel}>
        <TransitionChild
          as={Fragment}
          enter="ease-out duration-200"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-150"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-ink-900/50 backdrop-blur-sm" />
        </TransitionChild>
        <div className="fixed inset-0 flex items-center justify-center p-4">
          <TransitionChild
            as={Fragment}
            enter="ease-out duration-200"
            enterFrom="opacity-0 scale-95"
            enterTo="opacity-100 scale-100"
            leave="ease-in duration-150"
            leaveFrom="opacity-100 scale-100"
            leaveTo="opacity-0 scale-95"
          >
            <DialogPanel className="w-full max-w-md rounded-2xl bg-white shadow-xl p-6">
              <div className="flex items-start gap-4">
                {destructive && (
                  <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-red-50">
                    <ExclamationTriangleIcon className="h-5 w-5 text-red-600" aria-hidden="true" />
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <DialogTitle as="h3" className="text-base font-bold text-ink-900">
                    {title}
                  </DialogTitle>
                  <div className="mt-2 text-sm text-ink-500 leading-relaxed">
                    {description}
                  </div>
                </div>
              </div>
              <div className="mt-6 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={onCancel}
                  disabled={busy}
                  className="rounded-xl border border-ink-200 px-4 py-2 text-sm font-medium text-ink-700 hover:bg-ink-50 disabled:opacity-50 transition-colors"
                >
                  {cancelLabel}
                </button>
                <button
                  type="button"
                  onClick={onConfirm}
                  disabled={busy}
                  className={`rounded-xl px-4 py-2 text-sm font-semibold text-white shadow-sm disabled:opacity-50 transition-colors ${
                    destructive
                      ? "bg-red-600 hover:bg-red-700"
                      : "bg-primary-600 hover:bg-primary-700"
                  }`}
                >
                  {busy ? "Working…" : confirmLabel}
                </button>
              </div>
            </DialogPanel>
          </TransitionChild>
        </div>
      </Dialog>
    </Transition>
  );
}

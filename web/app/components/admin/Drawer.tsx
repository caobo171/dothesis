"use client";

import { Dialog, DialogPanel, Transition, TransitionChild } from "@headlessui/react";
import { XMarkIcon } from "@heroicons/react/24/outline";
import { Fragment, type ReactNode } from "react";

export function Drawer({
  open, onClose, title, children,
}: {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
}) {
  return (
    <Transition show={open} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={onClose}>
        <TransitionChild
          as={Fragment}
          enter="ease-out duration-200"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-150"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-ink-900/40" />
        </TransitionChild>
        <div className="fixed inset-y-0 right-0 flex max-w-full">
          <TransitionChild
            as={Fragment}
            enter="transform transition ease-out duration-300"
            enterFrom="translate-x-full"
            enterTo="translate-x-0"
            leave="transform transition ease-in duration-200"
            leaveFrom="translate-x-0"
            leaveTo="translate-x-full"
          >
            <DialogPanel className="w-screen max-w-md bg-white shadow-xl flex flex-col">
              <div className="flex items-center justify-between border-b border-ink-100 px-5 py-4">
                <div className="text-sm font-semibold text-ink-900">{title}</div>
                <button type="button" onClick={onClose} className="text-ink-500 hover:text-ink-900">
                  <XMarkIcon className="h-5 w-5" />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-5">{children}</div>
            </DialogPanel>
          </TransitionChild>
        </div>
      </Dialog>
    </Transition>
  );
}

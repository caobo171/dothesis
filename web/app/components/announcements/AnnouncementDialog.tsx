"use client";

import { Dialog, DialogPanel, DialogTitle, Transition, TransitionChild } from "@headlessui/react";
import { XMarkIcon } from "@heroicons/react/24/outline";
import { Fragment } from "react";

export type AnnouncementShape = {
  id: string;
  kind: string;
  title: string;
  body: string;
  image_url: string | null;
  cta_label: string | null;
  cta_url: string | null;
};

export function AnnouncementDialog({
  announcement, open, onClose,
}: {
  announcement: AnnouncementShape;
  open: boolean;
  onClose: () => void;
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
          <div className="fixed inset-0 bg-ink-900/60" />
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
            <DialogPanel className="w-full max-w-md overflow-hidden rounded-2xl bg-white shadow-xl">
              {announcement.image_url && (
                <img src={announcement.image_url} alt="" className="h-40 w-full object-cover" />
              )}
              <div className="relative p-6">
                <button
                  type="button"
                  onClick={onClose}
                  className="absolute right-4 top-4 text-ink-400 hover:text-ink-700"
                  aria-label="Close"
                >
                  <XMarkIcon className="h-5 w-5" />
                </button>
                <DialogTitle as="h3" className="text-lg font-bold text-ink-900">
                  {announcement.title}
                </DialogTitle>
                <div className="mt-2 whitespace-pre-wrap text-sm text-ink-700">
                  {announcement.body}
                </div>
                {announcement.cta_label && announcement.cta_url && (
                  <a
                    href={announcement.cta_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-5 block w-full rounded-xl bg-primary-600 px-4 py-2.5 text-center text-sm font-semibold text-white shadow-sm hover:bg-primary-700"
                  >
                    {announcement.cta_label}
                  </a>
                )}
              </div>
            </DialogPanel>
          </TransitionChild>
        </div>
      </Dialog>
    </Transition>
  );
}

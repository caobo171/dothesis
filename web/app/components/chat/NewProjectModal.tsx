"use client";

import { useState, useEffect, useRef } from "react";
import { X } from "lucide-react";


type Props = {
  open: boolean;
  onClose: () => void;
  onCreated: (project: { id: string; name: string }) => void;
};


// Replaces window.prompt() — proper modal with validation, error surfacing,
// and Enter-to-submit. Keeps the project-creation UX consistent with the
// rest of the chat surface (mirrors AutoDraftModal's pattern).
export function NewProjectModal({ open, onClose, onCreated }: Props) {
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Reset state every time the modal opens so a previous error or value
  // doesn't bleed into the next "New project" click.
  useEffect(() => {
    if (open) {
      setName("");
      setError(null);
      setSubmitting(false);
      // Autofocus the input on open
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  if (!open) return null;

  const submit = async () => {
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Please enter a project name.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/v1/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: trimmed }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const code = body?.detail?.error?.code || body?.detail || res.statusText;
        throw new Error(`Could not create project: ${code}`);
      }
      const project = await res.json();
      onCreated(project);
    } catch (e: any) {
      setError(e?.message || "Could not create project.");
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        onClick={e => e.stopPropagation()}
        className="bg-white rounded-lg shadow-xl max-w-md w-full p-6"
        role="dialog"
        aria-modal="true"
        aria-labelledby="new-project-title"
      >
        <div className="flex items-start justify-between mb-4">
          <h2 id="new-project-title" className="text-lg font-semibold text-gray-900">
            Create new project
          </h2>
          <button type="button" onClick={onClose} aria-label="close">
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        <label
          htmlFor="new-project-name"
          className="block text-sm font-medium text-gray-700 mb-1"
        >
          Project name
        </label>
        <input
          id="new-project-name"
          ref={inputRef}
          type="text"
          value={name}
          onChange={e => setName(e.target.value)}
          onKeyDown={e => {
            if (e.key === "Enter") {
              e.preventDefault();
              void submit();
            }
          }}
          placeholder="e.g. EU AI Act and Democratic Accountability"
          className="w-full border border-gray-200 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary-500 mb-3"
        />

        {error && (
          <div className="text-sm text-red-600 mb-3" role="alert">
            {error}
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100 rounded-md disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void submit()}
            disabled={submitting || !name.trim()}
            className="px-3 py-1.5 text-sm bg-primary-600 text-white rounded-md hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? "Creating…" : "Create"}
          </button>
        </div>
      </div>
    </div>
  );
}

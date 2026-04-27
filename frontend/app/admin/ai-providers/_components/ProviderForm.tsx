// frontend/app/admin/ai-providers/_components/ProviderForm.tsx
//
// Modal form for create/edit. Uses @headlessui/react Dialog for accessibility.
// Saving with apiKey blank in edit mode preserves the existing encrypted key.

'use client';

import React, { Fragment, useState } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { toast } from 'react-toastify';
import AdminApi from '@/lib/admin/api';

type Initial = {
  id?: string;
  _id?: string;
  provider: 'openai' | 'anthropic' | 'gemini' | 'custom';
  name: string;
  hasKey?: boolean;
  baseUrl?: string;
  defaultModel: string;
  enabled: boolean;
  order: number;
  purpose: 'humanize' | 'plagiarism' | 'autocite' | 'general';
};

type Props = {
  mode: 'create' | 'update';
  initial: Initial;
  onClose: () => void;
  onSaved: () => void;
};

export function ProviderForm({ mode, initial, onClose, onSaved }: Props) {
  const [v, setV] = useState<Initial>(initial);
  // apiKey is held in a separate state because it's intentionally not part of
  // `v` (which mirrors the server payload) — the input must stay write-only.
  const [apiKey, setApiKey] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!v.name.trim() || !v.defaultModel.trim()) {
      toast.error('Name and default model are required');
      return;
    }
    if (mode === 'create' && !apiKey.trim()) {
      toast.error('API key is required when creating a provider');
      return;
    }
    setBusy(true);
    try {
      const url = mode === 'create' ? '/api/admin/ai-providers/create' : '/api/admin/ai-providers/update';
      const payload: Record<string, any> = {
        provider: v.provider,
        name: v.name,
        baseUrl: v.baseUrl || '',
        defaultModel: v.defaultModel,
        enabled: v.enabled,
        order: v.order,
        purpose: v.purpose,
      };
      if (apiKey.trim()) payload.apiKey = apiKey;
      if (mode === 'update') payload.id = v.id || v._id;
      const res = await AdminApi.post(url, payload);
      if (res.code !== 1) {
        toast.error(res.message || 'Save failed');
        return;
      }
      toast.success(mode === 'create' ? 'Provider created' : 'Provider updated');
      onSaved();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Transition appear show as={Fragment}>
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
            <Dialog.Panel className="w-full max-w-lg rounded-lg bg-white p-5 shadow-xl">
              <Dialog.Title className="text-base font-semibold text-gray-900">
                {mode === 'create' ? 'New AI provider' : `Edit "${initial.name}"`}
              </Dialog.Title>

              <form onSubmit={submit} className="mt-4 space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Provider">
                    <select
                      value={v.provider}
                      onChange={(e) => setV({ ...v, provider: e.target.value as any })}
                      className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
                    >
                      <option value="openai">openai</option>
                      <option value="anthropic">anthropic</option>
                      <option value="gemini">gemini</option>
                      <option value="custom">custom</option>
                    </select>
                  </Field>
                  <Field label="Purpose">
                    <select
                      value={v.purpose}
                      onChange={(e) => setV({ ...v, purpose: e.target.value as any })}
                      className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
                    >
                      <option value="general">general (fallback)</option>
                      <option value="humanize">humanize</option>
                      <option value="plagiarism">plagiarism</option>
                      <option value="autocite">autocite</option>
                    </select>
                  </Field>
                </div>
                <Field label="Display name">
                  <input
                    type="text"
                    value={v.name}
                    onChange={(e) => setV({ ...v, name: e.target.value })}
                    className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
                    placeholder="e.g. OpenAI primary"
                  />
                </Field>
                <Field label="Default model">
                  <input
                    type="text"
                    value={v.defaultModel}
                    onChange={(e) => setV({ ...v, defaultModel: e.target.value })}
                    className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm font-mono"
                    placeholder="e.g. gpt-4o"
                  />
                </Field>
                <Field label="Base URL (optional)">
                  <input
                    type="text"
                    value={v.baseUrl || ''}
                    onChange={(e) => setV({ ...v, baseUrl: e.target.value })}
                    className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
                    placeholder="Override the provider's default base URL"
                  />
                </Field>
                <Field label={mode === 'create' ? 'API key' : 'API key (leave blank to keep existing)'}>
                  <input
                    type="password"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm font-mono"
                    placeholder={mode === 'update' && v.hasKey ? '••••••••' : 'sk-…'}
                    autoComplete="off"
                  />
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Enabled">
                    <select
                      value={v.enabled ? 'true' : 'false'}
                      onChange={(e) => setV({ ...v, enabled: e.target.value === 'true' })}
                      className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
                    >
                      <option value="false">Off</option>
                      <option value="true">On</option>
                    </select>
                  </Field>
                  <Field label="Order">
                    <input
                      type="number"
                      value={v.order}
                      onChange={(e) => setV({ ...v, order: Number(e.target.value) || 0 })}
                      className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
                    />
                  </Field>
                </div>

                <div className="mt-5 flex items-center justify-end gap-2">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={onClose}
                    className="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={busy}
                    className="rounded bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-60"
                  >
                    {busy ? 'Saving…' : 'Save'}
                  </button>
                </div>
              </form>
            </Dialog.Panel>
          </Transition.Child>
        </div>
      </Dialog>
    </Transition>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-gray-600">{label}</span>
      {children}
    </label>
  );
}

export default ProviderForm;

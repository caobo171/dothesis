// frontend/app/admin/ai-providers/page.tsx
//
// AI provider configuration. Super admin only. The drag-to-reorder behavior
// uses @dnd-kit; other CRUD operations open the same form modal used by
// "New provider".
//
// API key handling: the table only ever shows hasKey: boolean. To rotate a key
// the admin pastes a new value into the form's apiKey field. Saving without
// a value leaves the existing key untouched.

'use client';

import React, { useEffect, useState } from 'react';
import { toast } from 'react-toastify';
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  arrayMove,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import AdminApi from '@/lib/admin/api';
import useAdminList from '../_components/useAdminList';
import AdminPageHeader from '../_components/AdminPageHeader';
import StatusBadge from '../_components/StatusBadge';
import ConfirmDialog from '../_components/ConfirmDialog';
import ProviderForm from './_components/ProviderForm';

type Provider = {
  id: string;
  _id: string;
  provider: 'openai' | 'anthropic' | 'gemini' | 'custom';
  name: string;
  hasKey: boolean;
  baseUrl?: string;
  defaultModel: string;
  enabled: boolean;
  order: number;
  purpose: 'humanize' | 'plagiarism' | 'autocite' | 'general';
};

export default function AdminAiProvidersPage() {
  const { items, isLoading, mutate } = useAdminList<Provider>('/api/admin/ai-providers', {});

  // Local order state — kept in sync with server-fetched items but mutated
  // optimistically during drag so the UI feels immediate.
  const [order, setOrder] = useState<Provider[]>([]);
  useEffect(() => {
    setOrder(items);
  }, [items]);

  const [editing, setEditing] = useState<Provider | 'new' | null>(null);
  const [deleting, setDeleting] = useState<Provider | null>(null);
  const [busy, setBusy] = useState(false);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));

  const onDragEnd = async (e: DragEndEvent) => {
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    const oldIdx = order.findIndex((p) => (p.id || p._id) === active.id);
    const newIdx = order.findIndex((p) => (p.id || p._id) === over.id);
    if (oldIdx < 0 || newIdx < 0) return;
    const next = arrayMove(order, oldIdx, newIdx);
    setOrder(next);
    const ids = next.map((p) => p.id || p._id);
    const res = await AdminApi.post('/api/admin/ai-providers/reorder', { ids });
    if (res.code !== 1) {
      toast.error(res.message || 'Reorder failed');
      // Refetch to revert local optimistic order on failure.
      mutate();
      return;
    }
    mutate();
  };

  const onToggle = async (p: Provider) => {
    const res = await AdminApi.post('/api/admin/ai-providers/toggle', { id: p.id, enabled: !p.enabled });
    if (res.code !== 1) {
      toast.error(res.message || 'Toggle failed');
      return;
    }
    mutate();
  };

  const onDelete = async () => {
    if (!deleting) return;
    setBusy(true);
    try {
      const res = await AdminApi.post('/api/admin/ai-providers/delete', { id: deleting.id });
      if (res.code !== 1) {
        toast.error(res.message || 'Delete failed');
        return;
      }
      toast.success('Deleted');
      setDeleting(null);
      mutate();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <AdminPageHeader
        title="AI providers"
        subtitle={`${order.length} configured · drag to reorder priority within a purpose`}
        actions={
          <button
            onClick={() => setEditing('new')}
            className="rounded bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-800"
          >
            New provider
          </button>
        }
      />

      {isLoading ? (
        <div className="rounded-lg border border-gray-200 bg-white p-6 text-center text-gray-500">Loading…</div>
      ) : order.length === 0 ? (
        <div className="rounded-lg border border-gray-200 bg-white p-6 text-center text-gray-500">
          No providers configured. Existing services fall back to OPENAI_API_KEY env var.
        </div>
      ) : (
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
          <SortableContext items={order.map((p) => p.id || p._id)} strategy={verticalListSortingStrategy}>
            <ul className="space-y-2">
              {order.map((p) => (
                <ProviderRow
                  key={p.id || p._id}
                  p={p}
                  onEdit={() => setEditing(p)}
                  onDelete={() => setDeleting(p)}
                  onToggle={() => onToggle(p)}
                />
              ))}
            </ul>
          </SortableContext>
        </DndContext>
      )}

      {editing && (
        <ProviderForm
          mode={editing === 'new' ? 'create' : 'update'}
          initial={
            editing === 'new'
              ? { provider: 'openai', name: '', defaultModel: '', enabled: false, order: order.length, purpose: 'general' }
              : { ...editing }
          }
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            mutate();
          }}
        />
      )}

      <ConfirmDialog
        open={!!deleting}
        title="Delete provider"
        description={`Permanently remove "${deleting?.name}". The encrypted key is destroyed; you'll need to re-enter it if you recreate this row.`}
        tone="danger"
        confirmLabel="Delete"
        busy={busy}
        onConfirm={onDelete}
        onClose={() => setDeleting(null)}
      />
    </div>
  );
}

function ProviderRow({
  p,
  onEdit,
  onDelete,
  onToggle,
}: {
  p: Provider;
  onEdit: () => void;
  onDelete: () => void;
  onToggle: () => void;
}) {
  const id = p.id || p._id;
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.6 : 1,
  };

  return (
    <li
      ref={setNodeRef}
      style={style}
      className="flex items-center gap-3 rounded-lg border border-gray-200 bg-white p-3"
    >
      <button
        type="button"
        {...attributes}
        {...listeners}
        aria-label="Drag to reorder"
        className="cursor-grab select-none rounded px-2 py-1 text-gray-400 hover:bg-gray-100"
        title="Drag to reorder"
      >
        ⋮⋮
      </button>
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <span className="font-medium text-gray-900">{p.name}</span>
          <StatusBadge tone="gray">{p.provider}</StatusBadge>
          <StatusBadge tone="blue">{p.purpose}</StatusBadge>
          {p.hasKey ? <StatusBadge tone="green">key set</StatusBadge> : <StatusBadge tone="yellow">no key</StatusBadge>}
        </div>
        <div className="mt-0.5 text-xs text-gray-500">
          model: <span className="font-mono">{p.defaultModel}</span>
          {p.baseUrl && <> · baseUrl: <span className="font-mono">{p.baseUrl}</span></>}
        </div>
      </div>
      <button
        type="button"
        onClick={onToggle}
        className={`inline-flex h-5 w-9 items-center rounded-full transition ${p.enabled ? 'bg-green-500' : 'bg-gray-300'}`}
        aria-pressed={p.enabled}
        aria-label={p.enabled ? 'Disable provider' : 'Enable provider'}
      >
        <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition ${p.enabled ? 'translate-x-4' : 'translate-x-0.5'}`} />
      </button>
      <button
        type="button"
        onClick={onEdit}
        className="rounded border border-gray-300 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50"
      >
        Edit
      </button>
      <button
        type="button"
        onClick={onDelete}
        className="rounded border border-red-300 px-2 py-1 text-xs text-red-700 hover:bg-red-50"
      >
        Delete
      </button>
    </li>
  );
}

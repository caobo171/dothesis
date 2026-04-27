// frontend/app/admin/page.tsx
//
// Placeholder dashboard for the foundation slice. Real stats wire up in a later
// slice (after user/job admin endpoints exist). Three cards keep the visual
// alive while we land subsequent slices.

'use client';

export default function AdminDashboardPage() {
  const cards = [
    { label: 'Total users', value: '—' },
    { label: 'Jobs (24h)', value: '—' },
    { label: 'Credits (24h, net)', value: '—' },
  ];

  return (
    <div>
      <h1 className="mb-6 text-2xl font-semibold">Dashboard</h1>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {cards.map((c) => (
          <div key={c.label} className="rounded-lg border border-gray-200 bg-white p-4">
            <div className="text-xs uppercase tracking-wider text-gray-500">{c.label}</div>
            <div className="mt-2 text-2xl font-semibold text-gray-900">{c.value}</div>
          </div>
        ))}
      </div>
      <p className="mt-6 text-sm text-gray-600">
        Foundation slice landed. User management, job sections, credits, announcements, and AI provider
        config will be added in subsequent slices.
      </p>
    </div>
  );
}

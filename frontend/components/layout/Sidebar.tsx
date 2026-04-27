'use client';

import Image from 'next/image';
import Link from 'next/link';
import { useRouter, usePathname } from 'next/navigation';
import { clsx } from 'clsx';
import {
  ChevronLeft,
  Plus,
  Search,
  Edit3,
  Quote,
  BookOpen,
  Clock,
  ShieldAlert,
  Sparkles,
  MoreHorizontal,
} from 'lucide-react';
import { useState, useEffect } from 'react';
import useSWR from 'swr';
import { useMe } from '@/hooks/user';
import { useBalance } from '@/hooks/credit';

// Subset shape we read from /document/list. The route returns more fields,
// but we only render the title and createdAt here.
type RecentDoc = { id?: string; _id: string; title: string; createdAt: string };

// Stable color picker for the recent-doc dot. Hashing the id keeps the same
// document on the same color across renders without storing per-doc state.
const DOT_COLORS = ['bg-primary', 'bg-purple', 'bg-success', 'bg-warn', 'bg-error', 'bg-ink-soft'];
function dotColor(id: string): string {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) | 0;
  return DOT_COLORS[Math.abs(h) % DOT_COLORS.length];
}

const NAV_ITEMS = [
  { href: '/humanizer', label: 'Humanizer', Icon: Edit3 },
  { href: '/auto-cite', label: 'Auto-Cite', Icon: Quote },
  { href: '/library', label: 'Library', Icon: BookOpen, badgeFromLibrary: true },
  { href: '/history', label: 'History', Icon: Clock },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { data: user } = useMe();
  const { balance } = useBalance();
  const [collapsed, setCollapsed] = useState(false);

  // Library count badge — fetched from the existing folders endpoint and
  // summed across folders so it matches what the user would see on /library.
  const { data: foldersData } = useSWR(['/api/library/folders/list', {}]);
  const libraryCount: number = (() => {
    const folders = (foldersData as any)?.code === 1 ? (foldersData as any).data : [];
    if (!Array.isArray(folders)) return 0;
    return folders.reduce((sum: number, f: any) => sum + (f.citationCount || 0), 0);
  })();

  // Recent docs — first 4 from /document/list. Skip if no token.
  const { data: docsData } = useSWR(['/api/document/list', {}]);
  const recentDocs: RecentDoc[] = ((docsData as any)?.code === 1 ? (docsData as any).data : []).slice(0, 4);

  // Cmd/Ctrl+K focuses the search input. Lightweight — full search is a
  // future feature; for now the shortcut at least focuses the field.
  const [searchValue, setSearchValue] = useState('');
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        const el = document.getElementById('sidebar-search');
        el?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  if (collapsed) {
    // Tight icon rail when collapsed. Dashboard nav only — recent docs and
    // upgrade card are hidden to keep the rail under 64px wide.
    return (
      <aside className="w-16 h-screen bg-white border-r border-rule flex flex-col fixed left-0 top-0 items-center py-3 gap-2">
        <button
          type="button"
          onClick={() => setCollapsed(false)}
          aria-label="Expand sidebar"
          className="w-10 h-10 rounded-lg flex items-center justify-center hover:bg-bg-soft"
        >
          <Image src="/logo.png" alt="DoThesis" width={24} height={24} />
        </button>
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          const Icon = item.Icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={clsx(
                'w-10 h-10 rounded-lg flex items-center justify-center transition',
                active ? 'bg-bg-blue text-primary' : 'text-ink-soft hover:bg-bg-soft'
              )}
              title={item.label}
            >
              <Icon className="w-5 h-5" />
            </Link>
          );
        })}
      </aside>
    );
  }

  return (
    <aside className="w-72 h-screen bg-white border-r border-rule flex flex-col fixed left-0 top-0">
      {/* Brand row + collapse toggle */}
      <div className="flex items-center justify-between px-5 pt-5 pb-3">
        <Link href="/humanizer" className="flex items-center gap-2">
          <Image src="/logo.png" alt="DoThesis" width={32} height={32} priority />
          <span className="font-serif text-2xl text-ink italic">DoThesis</span>
        </Link>
        <button
          type="button"
          onClick={() => setCollapsed(true)}
          aria-label="Collapse sidebar"
          className="w-8 h-8 rounded-lg flex items-center justify-center text-ink-muted hover:bg-bg-soft hover:text-ink-soft"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
      </div>

      {/* + New document — primary CTA */}
      <div className="px-4 pb-3">
        <button
          type="button"
          onClick={() => router.push('/humanizer')}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-primary text-white rounded-xl text-sm font-semibold hover:bg-primary-dark transition"
        >
          <Plus className="w-4 h-4" />
          New document
        </button>
      </div>

      {/* Search — Cmd/Ctrl+K focuses */}
      <div className="px-4 pb-2">
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted pointer-events-none" />
          <input
            id="sidebar-search"
            type="text"
            placeholder="Search…"
            value={searchValue}
            onChange={(e) => setSearchValue(e.target.value)}
            className="w-full pl-9 pr-12 py-2 rounded-xl border border-rule bg-bg-soft text-sm focus:outline-none focus:border-primary focus:bg-white transition"
          />
          <kbd className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] font-mono font-medium text-ink-muted bg-white border border-rule rounded px-1.5 py-0.5">
            ⌘K
          </kbd>
        </div>
      </div>

      {/* Scrollable middle: workspace nav + recent docs */}
      <nav className="flex-1 overflow-y-auto px-3 py-2 space-y-5">
        <div>
          <div className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-muted">
            Workspace
          </div>
          <ul className="space-y-1">
            {NAV_ITEMS.map((item) => {
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              const Icon = item.Icon;
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    className={clsx(
                      'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition',
                      active ? 'bg-primary text-white' : 'text-ink-soft hover:bg-bg-soft'
                    )}
                  >
                    <Icon className="w-4 h-4" />
                    <span className="flex-1">{item.label}</span>
                    {item.badgeFromLibrary && libraryCount > 0 && (
                      <span
                        className={clsx(
                          'text-xs font-mono',
                          active ? 'text-white/80' : 'text-ink-muted'
                        )}
                      >
                        {libraryCount}
                      </span>
                    )}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>

        {recentDocs.length > 0 && (
          <div>
            <div className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-muted">
              Recent docs
            </div>
            <ul className="space-y-1">
              {recentDocs.map((d) => {
                const id = d.id || d._id;
                return (
                  <li key={id}>
                    <Link
                      href={`/library`}
                      className="flex items-center gap-3 px-3 py-1.5 rounded-lg text-sm text-ink-soft hover:bg-bg-soft transition"
                      title={d.title}
                    >
                      <span className={clsx('w-2 h-2 rounded-sm flex-shrink-0', dotColor(id))} />
                      <span className="truncate">{d.title || '(untitled)'}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {/* Admin entry — only when user.is_admin (server-injected). Server-side
            gate at /api/admin/* is the actual enforcement. */}
        {user?.is_admin && (
          <div>
            <div className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-muted">
              Operations
            </div>
            <ul className="space-y-1">
              <li>
                <Link
                  href="/admin"
                  className={clsx(
                    'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition',
                    pathname.startsWith('/admin')
                      ? 'bg-primary text-white'
                      : 'text-ink-soft hover:bg-bg-soft'
                  )}
                >
                  <ShieldAlert className="w-4 h-4" />
                  <span className="flex-1">Admin</span>
                  {user?.is_super_admin && (
                    <span
                      className={clsx(
                        'rounded-full px-1.5 py-0.5 text-[10px] font-medium',
                        pathname.startsWith('/admin')
                          ? 'bg-white/20 text-white'
                          : 'bg-warn/20 text-warn'
                      )}
                    >
                      SUPER
                    </span>
                  )}
                </Link>
              </li>
            </ul>
          </div>
        )}
      </nav>

      {/* Plan + Upgrade card (only show for free plan) */}
      {user?.plan === 'free' && (
        <div className="px-4 pb-3">
          <div className="rounded-xl border border-rule bg-bg-soft p-3 mb-2">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-semibold text-ink">Free plan</span>
              <span className="text-xs font-mono text-ink-muted">{balance} credits</span>
            </div>
            <div className="h-1.5 rounded-full bg-rule overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-primary to-purple"
                style={{ width: `${Math.min(100, Math.max(0, (balance / 100) * 100))}%` }}
              />
            </div>
          </div>
          <button
            type="button"
            onClick={() => router.push('/humanizer')}
            className="w-full px-4 py-2.5 rounded-xl text-sm font-semibold text-white bg-gradient-to-r from-primary to-purple hover:opacity-95 transition flex items-center justify-center gap-2"
          >
            <Sparkles className="w-4 h-4" />
            Upgrade to Pro
          </button>
        </div>
      )}

      {/* User row */}
      <div className="border-t border-rule px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-ink flex items-center justify-center text-white text-xs font-bold">
            {user?.username?.charAt(0)?.toUpperCase() || '?'}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-ink truncate">{user?.username || 'Guest'}</p>
            <p className="text-xs text-ink-muted truncate">{user?.email || ''}</p>
          </div>
          <button
            type="button"
            aria-label="More"
            className="w-7 h-7 rounded-lg flex items-center justify-center text-ink-muted hover:bg-bg-soft hover:text-ink-soft"
          >
            <MoreHorizontal className="w-4 h-4" />
          </button>
        </div>
      </div>
    </aside>
  );
}

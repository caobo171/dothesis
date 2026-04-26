'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { clsx } from 'clsx';
import { useMe } from '@/hooks/user';

const NAV_ITEMS = [
  { href: '/humanizer', label: 'Humanizer', icon: 'H' },
  { href: '/auto-cite', label: 'Auto-Cite', icon: 'C' },
  { href: '/library', label: 'Library', icon: 'L' },
  { href: '/history', label: 'History', icon: 'R' },
];

export function Sidebar() {
  const pathname = usePathname();
  const { data: user } = useMe();

  return (
    <aside className="w-64 h-screen bg-white border-r border-rule flex flex-col fixed left-0 top-0">
      {/* Logo */}
      <div className="px-5 py-4 border-b border-rule">
        <Link href="/humanizer" className="font-serif text-2xl text-ink italic">
          DoThesis
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={clsx(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition',
                isActive
                  ? 'bg-bg-blue text-primary'
                  : 'text-ink-soft hover:bg-bg-soft'
              )}
            >
              <span
                className={clsx(
                  'w-7 h-7 rounded-md flex items-center justify-center text-xs font-bold',
                  isActive ? 'bg-primary text-white' : 'bg-bg-soft text-ink-muted'
                )}
              >
                {item.icon}
              </span>
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* User */}
      <div className="px-4 py-3 border-t border-rule">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-white text-xs font-bold">
            {user?.username?.charAt(0)?.toUpperCase() || '?'}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-ink truncate">{user?.username || 'Guest'}</p>
            <p className="text-xs text-ink-muted truncate">{user?.email || ''}</p>
          </div>
        </div>
      </div>
    </aside>
  );
}

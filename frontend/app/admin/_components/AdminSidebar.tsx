// frontend/app/admin/_components/AdminSidebar.tsx
//
// Static sidebar nav for the admin shell. Section links are listed for the
// full portal scope but only the dashboard link routes anywhere in this slice.
// Other links render but are visually disabled until later slices implement them.

'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  HomeIcon,
  UsersIcon,
  CurrencyDollarIcon,
  DocumentTextIcon,
  SparklesIcon,
  ShieldCheckIcon,
  MegaphoneIcon,
  CpuChipIcon,
  CommandLineIcon,
} from '@heroicons/react/24/outline';

type NavItem = {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  group: 'Operations' | 'Jobs' | 'Content' | 'Config';
  superAdminOnly?: boolean;
  enabled?: boolean;
};

const NAV: NavItem[] = [
  { label: 'Dashboard', href: '/admin', icon: HomeIcon, group: 'Operations', enabled: true },
  { label: 'Users', href: '/admin/users', icon: UsersIcon, group: 'Operations', enabled: true },
  { label: 'Credits', href: '/admin/credits', icon: CurrencyDollarIcon, group: 'Operations', enabled: true },
  { label: 'Documents', href: '/admin/documents', icon: DocumentTextIcon, group: 'Jobs' },
  { label: 'Humanize', href: '/admin/humanize', icon: SparklesIcon, group: 'Jobs' },
  { label: 'Plagiarism', href: '/admin/plagiarism', icon: ShieldCheckIcon, group: 'Jobs' },
  { label: 'AutoCite', href: '/admin/autocite', icon: CommandLineIcon, group: 'Jobs' },
  { label: 'Announcements', href: '/admin/announcements', icon: MegaphoneIcon, group: 'Content', superAdminOnly: true },
  { label: 'AI Providers', href: '/admin/ai-providers', icon: CpuChipIcon, group: 'Config', superAdminOnly: true },
];

export function AdminSidebar({ isSuperAdmin }: { isSuperAdmin: boolean }) {
  const pathname = usePathname();
  const groups: Array<NavItem['group']> = ['Operations', 'Jobs', 'Content', 'Config'];

  return (
    <aside className="fixed left-0 top-0 h-screen w-60 border-r border-gray-200 bg-white">
      <div className="px-4 py-5 text-lg font-semibold">DoThesis Admin</div>
      <nav className="px-2">
        {groups.map((group) => {
          const items = NAV.filter((n) => n.group === group && (!n.superAdminOnly || isSuperAdmin));
          if (items.length === 0) return null;
          return (
            <div key={group} className="mb-6">
              <div className="px-3 text-xs font-medium uppercase tracking-wider text-gray-500">{group}</div>
              <ul className="mt-1">
                {items.map((item) => {
                  // Match exact dashboard path; for everything else match the
                  // section prefix so detail pages also highlight the section.
                  const active =
                    item.href === '/admin'
                      ? pathname === '/admin'
                      : pathname === item.href || pathname.startsWith(`${item.href}/`);
                  const Icon = item.icon;
                  const baseClass = 'flex items-center gap-2 rounded px-3 py-2 text-sm';
                  const stateClass = item.enabled
                    ? active
                      ? 'bg-gray-900 text-white'
                      : 'text-gray-700 hover:bg-gray-100'
                    : 'cursor-not-allowed text-gray-400';
                  return (
                    <li key={item.href}>
                      {item.enabled ? (
                        <Link href={item.href} className={`${baseClass} ${stateClass}`}>
                          <Icon className="h-5 w-5" />
                          {item.label}
                        </Link>
                      ) : (
                        <span className={`${baseClass} ${stateClass}`} title="Coming in a later slice">
                          <Icon className="h-5 w-5" />
                          {item.label}
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </nav>
    </aside>
  );
}

export default AdminSidebar;

# UI Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Update the Survify frontend UI to match the new designs in `/designs/` folder while preserving all existing functionality.

**Architecture:** Component-first approach - update core Button component first, then layout/sidebar, then individual pages. All changes are CSS/styling only - no functional changes.

**Tech Stack:** Next.js 14, React 18, Tailwind CSS, Headless UI, Heroicons

---

## Task 1: Update Button Component with Design System

**Files:**
- Modify: `survify-frontend/components/common/Button.tsx`

**Step 1: Read current Button implementation**

```bash
cat survify-frontend/components/common/Button.tsx
```

**Step 2: Update Button component with new design system**

Replace the entire Button.tsx with the new implementation matching `button_design.png`:

```tsx
import clsx from 'clsx';
import React, { useMemo } from 'react';
import { twMerge } from 'tailwind-merge';

export type ButtonProps = {
  variant?: 'primary' | 'secondary' | 'minimal';
  size?: 'small' | 'medium' | 'large';
  iconPosition?: 'none' | 'left' | 'right' | 'only';
  className?: string;
  children?: React.ReactNode;
  icon?: React.ReactNode;
  onClick?: () => void;
  htmlType?: 'button' | 'reset' | 'submit';
  disabled?: boolean;
  loading?: boolean;
  title?: string;
  style?: React.CSSProperties;
  // Legacy props for backwards compatibility
  type?: 'solid' | 'outline' | 'text' | 'secondary';
  rounded?: boolean;
};

export function Button({
  variant = 'primary',
  size = 'medium',
  iconPosition = 'none',
  className,
  children,
  icon,
  onClick,
  disabled,
  loading,
  htmlType,
  title,
  style,
  type,
  rounded,
}: ButtonProps) {
  // Map legacy type prop to new variant
  const resolvedVariant = useMemo(() => {
    if (type) {
      if (type === 'solid') return 'primary';
      if (type === 'outline' || type === 'secondary') return 'secondary';
      if (type === 'text') return 'minimal';
    }
    return variant;
  }, [type, variant]);

  const baseClasses = 'inline-flex items-center justify-center gap-2 font-medium transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-offset-2';

  const variantClasses = useMemo(() => {
    switch (resolvedVariant) {
      case 'primary':
        return 'bg-primary text-white hover:bg-primary-700 active:bg-primary-800 focus:ring-primary-500 disabled:bg-primary-300';
      case 'secondary':
        return 'bg-white text-primary border border-primary hover:bg-primary-50 active:bg-primary-100 focus:ring-primary-500 disabled:text-primary-300 disabled:border-primary-300';
      case 'minimal':
        return 'bg-transparent text-primary hover:bg-primary-50 active:bg-primary-100 focus:ring-primary-500 disabled:text-primary-300';
      default:
        return '';
    }
  }, [resolvedVariant]);

  const sizeClasses = useMemo(() => {
    switch (size) {
      case 'small':
        return 'text-xs px-3 py-1.5 rounded-md';
      case 'medium':
        return 'text-sm px-4 py-2 rounded-lg';
      case 'large':
        return 'text-base px-6 py-3 rounded-lg';
      default:
        return '';
    }
  }, [size]);

  const iconOnlyClasses = useMemo(() => {
    if (iconPosition !== 'only') return '';
    switch (size) {
      case 'small':
        return '!px-1.5 !py-1.5';
      case 'medium':
        return '!px-2 !py-2';
      case 'large':
        return '!px-3 !py-3';
      default:
        return '';
    }
  }, [iconPosition, size]);

  const iconSizeClasses = useMemo(() => {
    switch (size) {
      case 'small':
        return 'w-3.5 h-3.5';
      case 'medium':
        return 'w-4 h-4';
      case 'large':
        return 'w-5 h-5';
      default:
        return 'w-4 h-4';
    }
  }, [size]);

  const renderIcon = () => {
    if (loading) {
      return (
        <svg
          className={clsx('animate-spin', iconSizeClasses)}
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          />
        </svg>
      );
    }
    if (icon) {
      return <span className={iconSizeClasses}>{icon}</span>;
    }
    return null;
  };

  return (
    <button
      className={twMerge(
        baseClasses,
        variantClasses,
        sizeClasses,
        iconOnlyClasses,
        clsx({
          'rounded-full': rounded,
          'pointer-events-none select-none': disabled || loading,
        }),
        className
      )}
      onClick={onClick}
      disabled={disabled || loading}
      type={htmlType}
      title={title}
      style={style}
    >
      {(iconPosition === 'left' || iconPosition === 'only' || loading) && renderIcon()}
      {iconPosition !== 'only' && children}
      {iconPosition === 'right' && !loading && renderIcon()}
    </button>
  );
}
```

**Step 3: Verify no TypeScript errors**

```bash
cd survify-frontend && npx tsc --noEmit --skipLibCheck 2>&1 | head -20
```

**Step 4: Commit changes**

```bash
git add survify-frontend/components/common/Button.tsx
git commit -m "feat(ui): update Button component with new design system

- Add variant prop (primary/secondary/minimal)
- Add iconPosition prop (none/left/right/only)
- Update size variants to match design specs
- Add proper focus/hover/active/disabled states
- Maintain backwards compatibility with legacy type prop"
```

---

## Task 2: Update Sidebar Logo and Branding

**Files:**
- Modify: `survify-frontend/components/layout/sidebar/sidebar-layout.tsx`

**Step 1: Update logo section to match design**

Find and replace the logo section (around line 245-257):

```tsx
<div className="flex h-16 shrink-0 items-center gap-2 border-b border-gray-100 mb-4">
  <div className="flex items-center gap-2">
    <div className="w-8 h-8 bg-gradient-to-br from-primary-400 to-primary-600 rounded-lg flex items-center justify-center">
      <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    </div>
    <div>
      <span className="text-lg font-bold text-gray-900 uppercase">Survify</span>
      <p className="text-xs text-gray-500">Save your energy</p>
    </div>
  </div>
</div>
```

Replace with:

```tsx
<div className="flex h-16 shrink-0 items-center gap-3 border-b border-gray-100 mb-4">
  <Link href="/" className="flex items-center gap-3">
    <div className="relative">
      <div className="w-9 h-9 bg-gradient-to-br from-primary-400 to-primary-600 rounded-xl flex items-center justify-center shadow-sm">
        <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 24 24">
          <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6zm-1 2l5 5h-5V4zM8 17v-1h8v1H8zm0-3v-1h8v1H8zm0-3v-1h5v1H8z"/>
        </svg>
      </div>
      <div className="absolute -bottom-0.5 -right-0.5 w-3 h-3 bg-primary-300 rounded-full border-2 border-white" />
    </div>
    <div>
      <div className="flex items-center gap-1">
        <span className="text-lg font-bold text-primary">FILL</span>
        <span className="text-lg font-bold text-gray-900">FORM</span>
      </div>
      <p className="text-[10px] text-gray-400 -mt-0.5">Save your energy</p>
    </div>
  </Link>
</div>
```

**Step 2: Commit changes**

```bash
git add survify-frontend/components/layout/sidebar/sidebar-layout.tsx
git commit -m "feat(ui): update sidebar logo to match new design

- Add FILL FORM branding with two-tone text
- Update logo icon design
- Add decorative accent dot"
```

---

## Task 3: Update Sidebar Help Center Section

**Files:**
- Modify: `survify-frontend/components/layout/sidebar/sidebar-layout.tsx`

**Step 1: Update Help Center section to dark theme**

Find the Help Center section (around line 261-280) and replace with:

```tsx
{/* Help Center Section */}
<div className="mt-auto pt-6">
  <div className="bg-gray-900 rounded-2xl p-4 text-center relative overflow-hidden">
    {/* Question mark icon */}
    <div className="absolute -top-3 left-1/2 -translate-x-1/2">
      <div className="w-12 h-12 bg-gray-700 rounded-full flex items-center justify-center border-4 border-white shadow-lg">
        <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      </div>
    </div>

    <div className="pt-6">
      <h3 className="text-sm font-semibold text-white mb-1">Help Center</h3>
      <p className="text-xs text-gray-400 mb-4">Having Trouble in Using App.<br/>We will support via Fanpage</p>
      <div className="space-y-2">
        <button className="w-full py-2.5 px-4 bg-white rounded-lg text-sm font-medium text-gray-900 hover:bg-gray-100 transition-colors">
          Find Document
        </button>
        <button className="w-full py-2.5 px-4 bg-transparent border border-gray-600 rounded-lg text-sm font-medium text-white hover:bg-gray-800 transition-colors">
          Contact Fanpage
        </button>
      </div>
    </div>
  </div>
</div>
```

**Step 2: Commit changes**

```bash
git add survify-frontend/components/layout/sidebar/sidebar-layout.tsx
git commit -m "feat(ui): update Help Center to dark theme

- Dark background (gray-900)
- Floating question mark icon
- White/outline button variants"
```

---

## Task 4: Update Sidebar Navigation Item Styling

**Files:**
- Modify: `survify-frontend/components/layout/sidebar/sidebar-layout.tsx`

**Step 1: Update navigation item classes**

In the `getSections` function, update the Link className (around line 132-137):

From:
```tsx
className={clsx(
  active
    ? 'bg-primary-50 text-primary font-medium'
    : 'text-gray-600 hover:bg-gray-50',
  'group flex gap-x-3 rounded-xl px-3 py-2.5 text-sm transition-colors'
)}
```

To:
```tsx
className={clsx(
  active
    ? 'bg-primary-50 text-primary font-medium shadow-sm'
    : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900',
  'group flex gap-x-3 rounded-xl px-3 py-2.5 text-sm transition-all duration-150'
)}
```

Also update the button className for items with subitems (around line 69-74):

From:
```tsx
className={clsx(
  active || hasActiveSubitem
    ? 'bg-primary-50 text-primary font-medium'
    : 'text-gray-600 hover:bg-gray-50',
  'group flex w-full items-center gap-x-3 rounded-xl px-3 py-2.5 text-sm transition-colors'
)}
```

To:
```tsx
className={clsx(
  active || hasActiveSubitem
    ? 'bg-primary-50 text-primary font-medium shadow-sm'
    : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900',
  'group flex w-full items-center gap-x-3 rounded-xl px-3 py-2.5 text-sm transition-all duration-150'
)}
```

**Step 2: Commit changes**

```bash
git add survify-frontend/components/layout/sidebar/sidebar-layout.tsx
git commit -m "feat(ui): improve sidebar navigation item styling

- Add shadow to active state
- Improve hover transitions
- Better text color on hover"
```

---

## Task 5: Add Custom Service Menu Item to Sidebar

**Files:**
- Modify: `survify-frontend/app/(inapp)/_components/SidebarLayoutWrapper.tsx`

**Step 1: Update menu items to match design**

Update the `defaultSections` array:

```tsx
let defaultSections = [
  {
    id: 'main',
    name: '',
    options: [
      { name: 'Dashboard', href: '/', icon: HomeIcon },
      { name: 'Fill Survey', href: '/form/create', icon: BookOpenIcon },
      { name: 'Research Model', href: '/data/builder', id: 'build_data', icon: CubeIcon },
      { name: 'Data Encoder', href: '/data/encode', icon: ChartBarSquareIcon },
      { name: 'Custom Service', href: '/custom-service', icon: ChatBubbleLeftRightIcon },
      { name: 'Credit', href: '/credit', icon: CurrencyDollarIcon },
      { name: 'Affiliate', href: '/affiliate', icon: UsersIcon },
    ],
  },
];
```

**Step 2: Commit changes**

```bash
git add survify-frontend/app/(inapp)/_components/SidebarLayoutWrapper.tsx
git commit -m "feat(ui): update sidebar menu items to match design

- Rename Data Service to Data Encoder
- Add Custom Service menu item
- Remove nested submenu structure"
```

---

## Task 6: Create Status Badge Component

**Files:**
- Create: `survify-frontend/components/common/StatusBadge.tsx`

**Step 1: Create new StatusBadge component**

```tsx
import clsx from 'clsx';

export type StatusBadgeProps = {
  status: 'running' | 'paused' | 'success' | 'stop' | 'pending';
  className?: string;
};

const statusConfig = {
  running: {
    label: 'Running',
    bgColor: 'bg-blue-50',
    textColor: 'text-blue-600',
    borderColor: 'border-blue-200',
  },
  paused: {
    label: 'Paused',
    bgColor: 'bg-orange-50',
    textColor: 'text-orange-600',
    borderColor: 'border-orange-200',
  },
  success: {
    label: 'Success',
    bgColor: 'bg-green-50',
    textColor: 'text-green-600',
    borderColor: 'border-green-200',
  },
  stop: {
    label: 'Stop',
    bgColor: 'bg-red-50',
    textColor: 'text-red-600',
    borderColor: 'border-red-200',
  },
  pending: {
    label: 'Pending',
    bgColor: 'bg-gray-50',
    textColor: 'text-gray-600',
    borderColor: 'border-gray-200',
  },
};

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const config = statusConfig[status] || statusConfig.pending;

  return (
    <span
      className={clsx(
        'inline-flex items-center px-3 py-1 rounded-full text-xs font-medium border',
        config.bgColor,
        config.textColor,
        config.borderColor,
        className
      )}
    >
      {config.label}
    </span>
  );
}
```

**Step 2: Commit changes**

```bash
git add survify-frontend/components/common/StatusBadge.tsx
git commit -m "feat(ui): add StatusBadge component

- Support running/paused/success/stop/pending statuses
- Color-coded badges matching design specs"
```

---

## Task 7: Create Pagination Component

**Files:**
- Create: `survify-frontend/components/common/Pagination.tsx`

**Step 1: Create Pagination component**

```tsx
import clsx from 'clsx';
import { ChevronLeftIcon, ChevronRightIcon } from '@heroicons/react/24/outline';

export type PaginationProps = {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  className?: string;
};

export function Pagination({
  currentPage,
  totalPages,
  onPageChange,
  className,
}: PaginationProps) {
  const pages = Array.from({ length: Math.min(totalPages, 4) }, (_, i) => i + 1);

  return (
    <div className={clsx('flex items-center justify-center gap-2', className)}>
      <button
        onClick={() => onPageChange(currentPage - 1)}
        disabled={currentPage === 1}
        className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-500 hover:text-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <ChevronLeftIcon className="w-4 h-4" />
        <span>Previous</span>
      </button>

      <div className="flex items-center gap-1">
        {pages.map((page) => (
          <button
            key={page}
            onClick={() => onPageChange(page)}
            className={clsx(
              'w-8 h-8 rounded-lg text-sm font-medium transition-colors',
              currentPage === page
                ? 'bg-primary text-white'
                : 'text-gray-600 hover:bg-gray-100'
            )}
          >
            {page}
          </button>
        ))}
      </div>

      <button
        onClick={() => onPageChange(currentPage + 1)}
        disabled={currentPage === totalPages}
        className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-500 hover:text-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <span>Next</span>
        <ChevronRightIcon className="w-4 h-4" />
      </button>
    </div>
  );
}
```

**Step 2: Commit changes**

```bash
git add survify-frontend/components/common/Pagination.tsx
git commit -m "feat(ui): add Pagination component

- Previous/Next buttons
- Numbered page buttons
- Active page highlighting"
```

---

## Task 8: Create Tab Navigation Component

**Files:**
- Create: `survify-frontend/components/common/TabNav.tsx`

**Step 1: Create TabNav component for fill survey pages**

```tsx
import clsx from 'clsx';

export type TabNavItem = {
  id: string;
  label: string;
  icon?: React.ReactNode;
};

export type TabNavProps = {
  items: TabNavItem[];
  activeTab: string;
  onTabChange: (tabId: string) => void;
  className?: string;
};

export function TabNav({ items, activeTab, onTabChange, className }: TabNavProps) {
  return (
    <div className={clsx('flex items-center gap-2', className)}>
      {items.map((item) => {
        const isActive = activeTab === item.id;
        return (
          <button
            key={item.id}
            onClick={() => onTabChange(item.id)}
            className={clsx(
              'flex items-center gap-2 px-5 py-2.5 rounded-full text-sm font-medium transition-all duration-150',
              isActive
                ? 'bg-primary text-white shadow-md'
                : 'bg-white text-gray-600 border border-gray-200 hover:border-gray-300 hover:bg-gray-50'
            )}
          >
            {item.icon && <span className="w-4 h-4">{item.icon}</span>}
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
```

**Step 2: Commit changes**

```bash
git add survify-frontend/components/common/TabNav.tsx
git commit -m "feat(ui): add TabNav component for pill-style tabs

- Active tab with primary background
- Inactive tabs with border
- Icon support"
```

---

## Task 9: Create Alert/Warning Component

**Files:**
- Create: `survify-frontend/components/common/Alert.tsx`

**Step 1: Create Alert component**

```tsx
import clsx from 'clsx';
import { ExclamationTriangleIcon, InformationCircleIcon, CheckCircleIcon, XCircleIcon } from '@heroicons/react/24/outline';

export type AlertProps = {
  type: 'info' | 'warning' | 'error' | 'success';
  title?: string;
  children: React.ReactNode;
  action?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
};

const alertConfig = {
  info: {
    bgColor: 'bg-blue-50',
    borderColor: 'border-blue-200',
    textColor: 'text-blue-800',
    iconColor: 'text-blue-500',
    Icon: InformationCircleIcon,
  },
  warning: {
    bgColor: 'bg-amber-50',
    borderColor: 'border-amber-200',
    textColor: 'text-amber-800',
    iconColor: 'text-amber-500',
    Icon: ExclamationTriangleIcon,
  },
  error: {
    bgColor: 'bg-red-50',
    borderColor: 'border-red-200',
    textColor: 'text-red-800',
    iconColor: 'text-red-500',
    Icon: XCircleIcon,
  },
  success: {
    bgColor: 'bg-green-50',
    borderColor: 'border-green-200',
    textColor: 'text-green-800',
    iconColor: 'text-green-500',
    Icon: CheckCircleIcon,
  },
};

export function Alert({ type, title, children, action, className }: AlertProps) {
  const config = alertConfig[type];
  const Icon = config.Icon;

  return (
    <div
      className={clsx(
        'flex items-start gap-3 p-4 rounded-xl border',
        config.bgColor,
        config.borderColor,
        className
      )}
    >
      <Icon className={clsx('w-5 h-5 flex-shrink-0 mt-0.5', config.iconColor)} />
      <div className="flex-1">
        {title && <p className={clsx('font-semibold mb-1', config.textColor)}>{title}</p>}
        <p className={clsx('text-sm', config.textColor)}>{children}</p>
      </div>
      {action && (
        <button
          onClick={action.onClick}
          className={clsx(
            'px-4 py-2 text-sm font-medium rounded-lg border transition-colors',
            config.borderColor,
            config.textColor,
            'hover:bg-white/50'
          )}
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
```

**Step 2: Commit changes**

```bash
git add survify-frontend/components/common/Alert.tsx
git commit -m "feat(ui): add Alert component

- Support info/warning/error/success types
- Optional title and action button
- Icon and color coding per type"
```

---

## Task 10: Create Note/Info Card Component

**Files:**
- Create: `survify-frontend/components/common/NoteCard.tsx`

**Step 1: Create NoteCard component for create order page**

```tsx
import clsx from 'clsx';
import { InformationCircleIcon } from '@heroicons/react/24/outline';

export type NoteCardProps = {
  title?: string;
  children: React.ReactNode;
  className?: string;
};

export function NoteCard({ title = 'Note', children, className }: NoteCardProps) {
  return (
    <div
      className={clsx(
        'bg-blue-50 border border-blue-100 rounded-xl p-4',
        className
      )}
    >
      <div className="flex items-start gap-3">
        <InformationCircleIcon className="w-5 h-5 text-blue-500 flex-shrink-0 mt-0.5" />
        <div>
          <p className="font-semibold text-gray-900 mb-1">{title}</p>
          <div className="text-sm text-gray-600">{children}</div>
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Commit changes**

```bash
git add survify-frontend/components/common/NoteCard.tsx
git commit -m "feat(ui): add NoteCard component

- Blue info-style card
- Icon + title + content layout"
```

---

## Task 11: Create Credit Warning Card Component

**Files:**
- Create: `survify-frontend/components/common/CreditWarning.tsx`

**Step 1: Create CreditWarning component**

```tsx
import clsx from 'clsx';
import { ExclamationTriangleIcon } from '@heroicons/react/24/outline';

export type CreditWarningProps = {
  requiredCredits: number;
  onAddCredit: () => void;
  className?: string;
};

export function CreditWarning({ requiredCredits, onAddCredit, className }: CreditWarningProps) {
  return (
    <div
      className={clsx(
        'bg-red-50 border border-red-100 rounded-xl p-4',
        className
      )}
    >
      <div className="flex items-start gap-3">
        <ExclamationTriangleIcon className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
        <div className="flex-1">
          <p className="font-semibold text-gray-900">You don't have enough credits!!</p>
          <p className="text-sm text-gray-600 mt-1">
            Need to add <span className="font-bold">{requiredCredits} Credit</span> to continue
          </p>
          <button
            onClick={onAddCredit}
            className="mt-3 w-full py-2.5 px-4 bg-white border border-red-200 rounded-lg text-sm font-medium text-red-600 hover:bg-red-50 transition-colors"
          >
            Add Credit
          </button>
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Commit changes**

```bash
git add survify-frontend/components/common/CreditWarning.tsx
git commit -m "feat(ui): add CreditWarning component

- Red warning card style
- Shows required credits
- Add Credit action button"
```

---

## Task 12: Create Toggle Switch Component

**Files:**
- Create: `survify-frontend/components/common/Toggle.tsx`

**Step 1: Create Toggle component**

```tsx
import clsx from 'clsx';

export type ToggleProps = {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
  label?: string;
  className?: string;
};

export function Toggle({ enabled, onChange, label, className }: ToggleProps) {
  return (
    <button
      type="button"
      onClick={() => onChange(!enabled)}
      className={clsx('flex items-center gap-2', className)}
    >
      <div
        className={clsx(
          'relative inline-flex h-6 w-11 items-center rounded-full transition-colors duration-200',
          enabled ? 'bg-primary' : 'bg-gray-200'
        )}
      >
        <span
          className={clsx(
            'inline-block h-4 w-4 transform rounded-full bg-white shadow-sm transition-transform duration-200',
            enabled ? 'translate-x-6' : 'translate-x-1'
          )}
        />
        {enabled && (
          <span className="absolute left-1.5 text-[10px] font-medium text-white">On</span>
        )}
      </div>
      {label && <span className="text-sm text-gray-700">{label}</span>}
    </button>
  );
}
```

**Step 2: Commit changes**

```bash
git add survify-frontend/components/common/Toggle.tsx
git commit -m "feat(ui): add Toggle switch component

- On/Off states with animation
- Optional label
- Shows 'On' text when enabled"
```

---

## Task 13: Create Day Schedule Component

**Files:**
- Create: `survify-frontend/components/common/DaySchedule.tsx`

**Step 1: Create DaySchedule component for create order page**

```tsx
import clsx from 'clsx';
import { Toggle } from './Toggle';

export type DayScheduleItem = {
  day: string;
  enabled: boolean;
  fromTime: string;
  toTime: string;
};

export type DayScheduleProps = {
  schedule: DayScheduleItem[];
  onChange: (schedule: DayScheduleItem[]) => void;
  className?: string;
};

export function DaySchedule({ schedule, onChange, className }: DayScheduleProps) {
  const updateDay = (index: number, updates: Partial<DayScheduleItem>) => {
    const newSchedule = [...schedule];
    newSchedule[index] = { ...newSchedule[index], ...updates };
    onChange(newSchedule);
  };

  return (
    <div className={clsx('space-y-3', className)}>
      {schedule.map((item, index) => (
        <div key={index} className="flex items-center gap-4">
          <span className="w-20 text-sm text-gray-700">{item.day}</span>
          <Toggle
            enabled={item.enabled}
            onChange={(enabled) => updateDay(index, { enabled })}
            label="Enable"
          />
          <span className="text-sm text-gray-500">from</span>
          <input
            type="time"
            value={item.fromTime}
            onChange={(e) => updateDay(index, { fromTime: e.target.value })}
            disabled={!item.enabled}
            className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm disabled:bg-gray-50 disabled:text-gray-400"
          />
          <span className="text-sm text-gray-500">to</span>
          <input
            type="time"
            value={item.toTime}
            onChange={(e) => updateDay(index, { toTime: e.target.value })}
            disabled={!item.enabled}
            className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm disabled:bg-gray-50 disabled:text-gray-400"
          />
        </div>
      ))}
    </div>
  );
}
```

**Step 2: Commit changes**

```bash
git add survify-frontend/components/common/DaySchedule.tsx
git commit -m "feat(ui): add DaySchedule component

- Day name + enable toggle + time range
- Disabled state styling
- Flexible schedule array"
```

---

## Task 14: Create View Live Demo Modal Component

**Files:**
- Create: `survify-frontend/components/common/DemoModal.tsx`

**Step 1: Create DemoModal component**

```tsx
import { Dialog, Transition, TransitionChild } from '@headlessui/react';
import { Fragment } from 'react';
import { Button } from './Button';

export type DemoModalProps = {
  isOpen: boolean;
  onClose: () => void;
  onStartDemo: () => void;
  title?: string;
  description?: string;
  backgroundImage?: string;
};

export function DemoModal({
  isOpen,
  onClose,
  onStartDemo,
  title = 'View Live Demo',
  description = 'Quick guide for cloning survey form data.\nYou can choose either Google form or Qualtric.',
  backgroundImage = '/images/demo-background.png',
}: DemoModalProps) {
  return (
    <Transition show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={onClose}>
        <TransitionChild
          as={Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/60" />
        </TransitionChild>

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            <TransitionChild
              as={Fragment}
              enter="ease-out duration-300"
              enterFrom="opacity-0 scale-95"
              enterTo="opacity-100 scale-100"
              leave="ease-in duration-200"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel className="relative w-full max-w-2xl overflow-hidden rounded-2xl">
                {/* Background Image */}
                <div
                  className="absolute inset-0 bg-cover bg-center"
                  style={{ backgroundImage: `url(${backgroundImage})` }}
                />
                <div className="absolute inset-0 bg-black/40" />

                {/* Content */}
                <div className="relative p-8 min-h-[400px] flex items-center justify-center">
                  <div className="bg-white rounded-2xl p-8 text-center max-w-sm">
                    <h3 className="text-xl font-bold text-gray-900 mb-3">{title}</h3>
                    <p className="text-sm text-gray-600 whitespace-pre-line mb-6">
                      {description}
                    </p>
                    <Button
                      variant="primary"
                      size="large"
                      className="w-full"
                      onClick={onStartDemo}
                    >
                      Start Demo
                    </Button>
                  </div>
                </div>
              </Dialog.Panel>
            </TransitionChild>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
}
```

**Step 2: Commit changes**

```bash
git add survify-frontend/components/common/DemoModal.tsx
git commit -m "feat(ui): add DemoModal component

- Full-screen overlay with background image
- Centered white card with title/description
- Start Demo action button"
```

---

## Task 15: Create Error Message Component

**Files:**
- Create: `survify-frontend/components/common/ErrorMessage.tsx`

**Step 1: Create ErrorMessage component**

```tsx
import clsx from 'clsx';
import { ExclamationCircleIcon } from '@heroicons/react/24/outline';

export type ErrorMessageProps = {
  title: string;
  message: string;
  className?: string;
};

export function ErrorMessage({ title, message, className }: ErrorMessageProps) {
  return (
    <div
      className={clsx(
        'flex flex-col items-center justify-center py-8 px-4 text-center',
        className
      )}
    >
      <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mb-4">
        <ExclamationCircleIcon className="w-8 h-8 text-red-500" />
      </div>
      <h3 className="text-lg font-semibold text-gray-900 mb-2">{title}</h3>
      <p className="text-sm text-gray-600 max-w-md">{message}</p>
    </div>
  );
}
```

**Step 2: Commit changes**

```bash
git add survify-frontend/components/common/ErrorMessage.tsx
git commit -m "feat(ui): add ErrorMessage component

- Centered error display with icon
- Title and message text
- Red color scheme"
```

---

## Task 16: Export All New Components from Common Index

**Files:**
- Modify: `survify-frontend/components/common/index.ts` (create if doesn't exist)

**Step 1: Check if index file exists and update exports**

```bash
ls -la survify-frontend/components/common/index.ts 2>/dev/null || echo "File does not exist"
```

**Step 2: Create or update index.ts**

```tsx
export { Button } from './Button';
export type { ButtonProps } from './Button';

export { StatusBadge } from './StatusBadge';
export type { StatusBadgeProps } from './StatusBadge';

export { Pagination } from './Pagination';
export type { PaginationProps } from './Pagination';

export { TabNav } from './TabNav';
export type { TabNavProps, TabNavItem } from './TabNav';

export { Alert } from './Alert';
export type { AlertProps } from './Alert';

export { NoteCard } from './NoteCard';
export type { NoteCardProps } from './NoteCard';

export { CreditWarning } from './CreditWarning';
export type { CreditWarningProps } from './CreditWarning';

export { Toggle } from './Toggle';
export type { ToggleProps } from './Toggle';

export { DaySchedule } from './DaySchedule';
export type { DayScheduleProps, DayScheduleItem } from './DaySchedule';

export { DemoModal } from './DemoModal';
export type { DemoModalProps } from './DemoModal';

export { ErrorMessage } from './ErrorMessage';
export type { ErrorMessageProps } from './ErrorMessage';
```

**Step 3: Commit changes**

```bash
git add survify-frontend/components/common/index.ts
git commit -m "feat(ui): export all new common components from index

- Button, StatusBadge, Pagination, TabNav
- Alert, NoteCard, CreditWarning
- Toggle, DaySchedule, DemoModal, ErrorMessage"
```

---

## Task 17: Update Home Page Tables Styling

**Files:**
- Modify: `survify-frontend/app/(inapp)/_sections/FormLists.tsx`
- Modify: `survify-frontend/app/(inapp)/_sections/OrderLists.tsx`

**Step 1: Read current FormLists implementation**

```bash
cat survify-frontend/app/(inapp)/_sections/FormLists.tsx
```

**Step 2: Update table header styling to match design**

Update the table classes to use proper spacing, add "View Detail" outline buttons, and match the design typography:

- Headers should use: `text-xs font-medium text-primary uppercase`
- Row numbers should be styled
- Add Pagination component at bottom

**Step 3: Read current OrderLists implementation**

```bash
cat survify-frontend/app/(inapp)/_sections/OrderLists.tsx
```

**Step 4: Update OrderLists with status badges and tab switcher**

- Add TabNav for "Fill Survey" / "Data Service" tabs
- Use StatusBadge component for status column
- Add action icons (pause, view, copy)
- Add Pagination at bottom

**Step 5: Commit changes**

```bash
git add survify-frontend/app/(inapp)/_sections/FormLists.tsx survify-frontend/app/(inapp)/_sections/OrderLists.tsx
git commit -m "feat(ui): update home page tables to match design

- Add proper table header styling
- Use StatusBadge for order status
- Add tab switcher for orders
- Add Pagination components
- Add View Detail buttons"
```

---

## Task 18: Update Header User Profile Section

**Files:**
- Modify: `survify-frontend/components/layout/sidebar/sidebar-layout.tsx`

**Step 1: Update the header profile section**

Find the profile section (around line 322-355) and update to show username and email:

```tsx
{/* Profile dropdown */}
<Menu as="div" className="relative">
  <MenuButton className="relative flex items-center gap-3">
    <span className="absolute -inset-1.5" />
    <span className="sr-only">Open user menu</span>
    <img
      alt=""
      src={me.data?.avatar || "https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?ixlib=rb-1.2.1&ixid=eyJhcHBfaWQiOjEyMDd9&auto=format&fit=facearea&facepad=2&w=256&h=256&q=80"}
      className="w-10 h-10 rounded-full bg-gray-50 object-cover border-2 border-gray-100"
    />
    <div className="hidden lg:block text-left">
      <p className="text-sm font-semibold text-gray-900">{me.data?.username}</p>
      <p className="text-xs text-gray-500">{me.data?.email}</p>
    </div>
    <ChevronDownIcon aria-hidden="true" className="hidden lg:block w-4 h-4 text-gray-400" />
  </MenuButton>
  {/* ... rest of menu items */}
</Menu>
```

**Step 2: Commit changes**

```bash
git add survify-frontend/components/layout/sidebar/sidebar-layout.tsx
git commit -m "feat(ui): update header profile section

- Show avatar with border
- Display username and email
- Better dropdown trigger styling"
```

---

## Task 19: Verify All Changes Compile

**Files:**
- None (verification only)

**Step 1: Run TypeScript compilation check**

```bash
cd survify-frontend && npx tsc --noEmit --skipLibCheck
```

**Step 2: Run lint check**

```bash
cd survify-frontend && npm run lint
```

**Step 3: If errors, fix them and recommit**

---

## Task 20: Test Development Server

**Files:**
- None (verification only)

**Step 1: Start the development server**

```bash
cd survify-frontend && npm run dev
```

**Step 2: Manually verify in browser**

Open http://localhost:7002 and check:
- [ ] Sidebar logo shows "FILL FORM"
- [ ] Help Center has dark background
- [ ] Navigation items have proper hover/active states
- [ ] Home page tables match design
- [ ] Buttons render correctly with new variants

**Step 3: Create summary commit**

```bash
git add -A
git commit -m "chore: complete UI redesign implementation

Summary of changes:
- Updated Button component with design system
- Updated Sidebar with new branding and Help Center
- Added StatusBadge, Pagination, TabNav components
- Added Alert, NoteCard, CreditWarning components
- Added Toggle, DaySchedule, DemoModal components
- Updated home page tables styling"
```

---

## Summary

This plan covers:

1. **Core Components** (Tasks 1-15): Button, StatusBadge, Pagination, TabNav, Alert, NoteCard, CreditWarning, Toggle, DaySchedule, DemoModal, ErrorMessage

2. **Layout Updates** (Tasks 2-5, 18): Sidebar logo, Help Center, navigation styling, header profile

3. **Page Updates** (Task 17): Home page tables

4. **Verification** (Tasks 19-20): TypeScript, lint, dev server

Total: 20 tasks with ~5 commits

"use client";

import { Menu, MenuButton, MenuItem, MenuItems } from "@headlessui/react";
import {
  CurrencyDollarIcon,
  PowerIcon,
  PuzzlePieceIcon,
  ShieldCheckIcon,
} from "@heroicons/react/24/outline";
import clsx from "clsx";
import Link from "next/link";
import type { ComponentType, ReactNode, SVGProps } from "react";

import { apiFetch } from "@/app/lib/api";
import { useT } from "@/app/lib/i18n/LocaleProvider";
import { tokenStore } from "@/app/lib/tokenStore";
import { useMe } from "@/app/lib/use-me";

async function logout() {
  // tokenStore.clear wipes both localStorage AND the marker cookie that
  // proxy.js gates routes on. Without that, the next request would still
  // see the marker cookie and stay on the protected page.
  try { await apiFetch("/auth/logout", { method: "POST", auth: false }); } catch { /* network error is fine */ }
  tokenStore.clear();
  window.location.href = "/login";
}

type Icon = ComponentType<SVGProps<SVGSVGElement>>;

const itemClass =
  "flex w-full items-center gap-3 rounded-lg p-2 text-left text-sm text-ink-900 data-[focus]:bg-ink-100";

function Item({ icon: Icon, href, onClick, children }: { icon: Icon; href?: string; onClick?: () => void; children: ReactNode }) {
  const body = (
    <>
      <Icon className="h-4 w-4 shrink-0 text-ink-500" aria-hidden="true" />
      {children}
    </>
  );
  return (
    <MenuItem>
      {href ? (
        <Link href={href} className={itemClass}>{body}</Link>
      ) : (
        <button type="button" onClick={onClick} className={itemClass}>{body}</button>
      )}
    </MenuItem>
  );
}

/**
 * The account menu at the foot of both sidebars (app shell and chat rail),
 * after Chat Crossocial's SidebarProfileMenu: the person is the trigger, and
 * the menu opens upward with a context row (credit balance) on top, a
 * hairline, then icon + label items.
 */
export function AccountMenu({ collapsed = false }: { collapsed?: boolean }) {
  const t = useT();
  const me = useMe();
  const userName = me.data?.username || me.data?.email?.split("@")[0] || "—";
  const userEmail = me.data?.email;
  const userInitial = userName.charAt(0).toUpperCase();

  return (
    <Menu as="div" className="relative min-w-0">
      <MenuButton
        className={clsx(
          "flex w-full items-center gap-2 rounded-lg p-1 text-left hover:bg-ink-100 data-[open]:bg-ink-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500",
          collapsed && "justify-center",
        )}
        aria-label={t("shell.userMenu")}
        title={collapsed ? userName : undefined}
      >
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary-100 text-[13px] font-semibold text-primary-700">
          {userInitial}
        </span>
        {!collapsed && (
          <span className="min-w-0">
            <span className="block truncate text-sm font-medium leading-4 text-ink-900">{userName}</span>
            {userEmail && <span className="block truncate text-xs text-ink-500">{userEmail}</span>}
          </span>
        )}
      </MenuButton>
      <MenuItems
        anchor={{ to: "top start", gap: 8 }}
        className="z-50 grid w-80 gap-2 rounded-xl border border-ink-200 bg-white/95 px-2 py-2 text-sm shadow-lg shadow-ink-900/10 backdrop-blur-xl focus:outline-none"
      >
        <div className="flex items-center gap-1 p-2">
          <div className="flex min-w-0 flex-grow items-center gap-3 text-ink-900">
            <CurrencyDollarIcon className="h-4 w-4 shrink-0 text-ink-500" aria-hidden="true" />
            {t("nav.credit")}
          </div>
          <MenuItem>
            <Link
              href="/credit"
              className="flex h-8 shrink-0 items-center rounded-lg bg-ink-100 px-3 text-sm text-ink-800 hover:bg-ink-200 data-[focus]:bg-ink-200"
            >
              {me.data ? t("tools.credits", { count: me.data.credit.toLocaleString() }) : "…"}
            </Link>
          </MenuItem>
        </div>

        <div className="-mx-2 h-0 border-b border-ink-200" />

        <Item icon={PuzzlePieceIcon} href="/connect">{t("nav.mcp")}</Item>
        {me.data?.is_super_admin && (
          <Item icon={ShieldCheckIcon} href="/admin">{t("nav.adminConsole")}</Item>
        )}
        <Item icon={PowerIcon} onClick={() => void logout()}>{t("shell.signOut")}</Item>
      </MenuItems>
    </Menu>
  );
}

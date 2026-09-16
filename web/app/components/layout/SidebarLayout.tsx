"use client";

import {
  Dialog,
  DialogPanel,
  Menu,
  MenuButton,
  MenuItem,
  MenuItems,
  Transition,
  TransitionChild,
} from "@headlessui/react";
import {
  Bars3Icon,
  BellIcon,
  ArrowRightStartOnRectangleIcon,
  ChevronDoubleLeftIcon,
  ChevronDoubleRightIcon,
  ChevronRightIcon,
  ChevronUpIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import clsx from "clsx";
import Link from "next/link";
import { Fragment, type PropsWithChildren, useEffect, useState } from "react";

import { LocaleSwitcher } from "@/app/components/LocaleSwitcher";
import { apiFetch } from "@/app/lib/api";
import { useT } from "@/app/lib/i18n/LocaleProvider";
import { tokenStore } from "@/app/lib/tokenStore";
import { useMe } from "@/app/lib/use-me";

import { Brand } from "./Brand";
import type { SidebarSection } from "./sections";

const COLLAPSED_KEY = "dothesis_sidebar_collapsed";

async function logout() {
  // tokenStore.clear wipes both localStorage AND the marker cookie that
  // proxy.js gates routes on. Without that, the next request would still
  // see the marker cookie and stay on the protected page.
  try { await apiFetch("/auth/logout", { method: "POST", auth: false }); } catch { /* network error is fine */ }
  tokenStore.clear();
  window.location.href = "/login";
}

// fullBleed: when true, the main slot renders edge-to-edge without the
// gradient backdrop, vertical padding, or max-width wrapper. The chat
// surface needs this because it manages its own panes (threads + chat +
// context) at full viewport height — the default shell chrome wraps it
// in a cramped column with unwanted top spacing.
export function SidebarLayout({
  sections,
  children,
  fullBleed = false,
}: PropsWithChildren<{ sections: SidebarSection[]; fullBleed?: boolean }>) {
  const [selectedHref, setSelectedHref] = useState<string>("");
  const [expandedItems, setExpandedItems] = useState<Set<string>>(new Set());
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const me = useMe();
  // Section/item labels arrive already translated from useSidebarSections; `t`
  // here is only for the chrome this component owns (collapse, sign out, and the
  // sr-only labels), so the two never translate the same string twice.
  const t = useT();

  useEffect(() => {
    setSelectedHref(window.location.pathname + window.location.search);
    const stored = window.localStorage.getItem(COLLAPSED_KEY);
    if (stored === "true") setSidebarCollapsed(true);
  }, []);

  useEffect(() => {
    window.localStorage.setItem(COLLAPSED_KEY, String(sidebarCollapsed));
  }, [sidebarCollapsed]);

  const toggleExpanded = (itemName: string) => {
    setExpandedItems((prev) => {
      const next = new Set(prev);
      if (next.has(itemName)) next.delete(itemName);
      else next.add(itemName);
      return next;
    });
  };

  function renderSections(collapsed = false) {
    return (
      <ul role="list" className="flex flex-1 flex-col gap-y-7 list-none p-0 m-0">
        {sections.map((section) => (
          <li key={section.id} className="space-y-2">
            {!collapsed && section.name && (
              <div className="text-xs font-semibold text-ink-500 uppercase tracking-wide">
                {section.name}
              </div>
            )}
            <ul role="list" className={clsx("mt-2 space-y-1 list-none p-0", collapsed ? "mx-0" : "-mx-2")}>
              {section.options.map((option) => {
                const hasSubitems = (option.subitems?.length ?? 0) > 0;
                const isExpanded = expandedItems.has(option.name);
                const active = selectedHref === option.href;
                const hasActiveSubitem =
                  hasSubitems && option.subitems!.some((s) => selectedHref === s.href);

                return (
                  <li key={option.name} className="relative group/item">
                    {hasSubitems ? (
                      <div>
                        <button
                          type="button"
                          onClick={() => {
                            if (collapsed) {
                              setSidebarCollapsed(false);
                              setExpandedItems(new Set([option.name]));
                            } else {
                              toggleExpanded(option.name);
                            }
                          }}
                          className={clsx(
                            active || hasActiveSubitem
                              ? "bg-primary-50 text-primary-600 font-medium shadow-sm"
                              : "text-ink-700 hover:bg-ink-50 hover:text-ink-900",
                            "group flex w-full items-center gap-x-3 rounded-xl px-3 py-2.5 text-sm transition-all",
                            collapsed && "justify-center px-2",
                          )}
                        >
                          {option.icon && (
                            <option.icon
                              className={clsx(
                                active || hasActiveSubitem ? "text-primary-600" : "text-ink-500",
                                "h-5 w-5 shrink-0",
                              )}
                              aria-hidden="true"
                            />
                          )}
                          {!collapsed && (
                            <>
                              <span className="flex-1 text-left">{option.name}</span>
                              <ChevronRightIcon
                                className={clsx(
                                  "h-4 w-4 transition-transform",
                                  isExpanded ? "rotate-90" : "",
                                  active || hasActiveSubitem ? "text-primary-600" : "text-ink-500",
                                )}
                                aria-hidden="true"
                              />
                            </>
                          )}
                        </button>
                        {collapsed && (
                          <div className="absolute left-full top-1/2 -translate-y-1/2 ml-2 px-2 py-1 bg-ink-900 text-white text-xs rounded opacity-0 invisible group-hover/item:opacity-100 group-hover/item:visible transition-all whitespace-nowrap z-50">
                            {option.name}
                          </div>
                        )}
                        {isExpanded && !collapsed && (
                          <ul className="mt-1 space-y-1 list-none">
                            {option.subitems!.map((subitem) => {
                              const subActive = selectedHref === subitem.href;
                              return (
                                <li key={subitem.name}>
                                  <Link
                                    href={subitem.href}
                                    onClick={() => setSelectedHref(subitem.href)}
                                    className={clsx(
                                      subActive
                                        ? "bg-primary-50 text-primary-600"
                                        : "text-ink-700 hover:bg-ink-50",
                                      "group flex gap-x-2 rounded-md py-2 pr-2 text-sm items-center",
                                      subitem.icon ? "pl-8" : "pl-10",
                                    )}
                                  >
                                    {subitem.icon && (
                                      <subitem.icon
                                        className={clsx(
                                          subActive ? "text-primary-600" : "text-ink-500",
                                          "h-4 w-4 shrink-0",
                                        )}
                                        aria-hidden="true"
                                      />
                                    )}
                                    {subitem.name}
                                  </Link>
                                </li>
                              );
                            })}
                          </ul>
                        )}
                      </div>
                    ) : (
                      <Link
                        href={option.href}
                        onClick={() => setSelectedHref(option.href)}
                        className={clsx(
                          active
                            ? "bg-primary-50 text-primary-600 font-medium shadow-sm"
                            : "text-ink-700 hover:bg-ink-50 hover:text-ink-900",
                          "group flex gap-x-3 rounded-xl px-3 py-2.5 text-sm transition-all",
                          collapsed && "justify-center px-2",
                        )}
                      >
                        {option.icon && (
                          <option.icon
                            className={clsx(
                              active ? "text-primary-600" : "text-ink-500",
                              "h-5 w-5 shrink-0",
                            )}
                            aria-hidden="true"
                          />
                        )}
                        {!collapsed && (
                          <>
                            {option.name}
                            {option.count ? (
                              <span className="ml-auto w-9 min-w-max whitespace-nowrap rounded-full bg-white px-2.5 py-0.5 text-center text-xs font-medium leading-5 text-ink-500 ring-1 ring-inset ring-ink-200">
                                {option.count}
                              </span>
                            ) : null}
                          </>
                        )}
                      </Link>
                    )}
                  </li>
                );
              })}
            </ul>
          </li>
        ))}
      </ul>
    );
  }

  const userInitial = (me.data?.username || me.data?.email || "?").charAt(0).toUpperCase();
  const userName = me.data?.username || me.data?.email?.split("@")[0] || "—";

  function renderAccountMenu(collapsed = false) {
    return (
      <Menu as="div" className="relative">
        <MenuButton
          className={clsx(
            "flex w-full items-center rounded-xl py-2 text-left transition-colors hover:bg-ink-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500",
            collapsed ? "justify-center px-2" : "gap-2.5 px-2",
          )}
          aria-label={t("shell.userMenu")}
          title={collapsed ? userName : undefined}
        >
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-ink-900 text-[11px] font-bold text-white">
            {userInitial}
          </span>
          {!collapsed && (
            <>
              <span className="min-w-0 flex-1 leading-tight">
                <span className="block truncate text-[12px] font-semibold text-ink-800">{userName}</span>
                {me.data?.email && <span className="block truncate pt-0.5 text-[10.5px] text-ink-500">{me.data.email}</span>}
              </span>
              <ChevronUpIcon className="h-3.5 w-3.5 shrink-0 text-ink-400" aria-hidden="true" />
            </>
          )}
        </MenuButton>
        <MenuItems
          anchor="top start"
          className="z-50 mb-2 w-64 origin-bottom-left rounded-xl border border-ink-200 bg-white p-1.5 shadow-lg shadow-ink-900/10 focus:outline-none"
        >
          <div className="border-b border-ink-100 px-2.5 py-2">
            <p className="m-0 truncate text-[12px] font-semibold text-ink-900">{userName}</p>
            {me.data?.email && <p className="m-0 truncate pt-0.5 text-[11px] text-ink-500">{me.data.email}</p>}
          </div>
          <MenuItem>
            <button
              type="button"
              onClick={logout}
              className="mt-1 flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[12px] font-medium text-ink-700 data-[focus]:bg-ink-50 data-[focus]:text-ink-900"
            >
              <ArrowRightStartOnRectangleIcon className="h-4 w-4" aria-hidden="true" />
              {t("shell.signOut")}
            </button>
          </MenuItem>
        </MenuItems>
      </Menu>
    );
  }

  return (
    <div>
      {/* Mobile sidebar */}
      <Transition show={sidebarOpen} as={Fragment}>
        <Dialog as="div" className="relative z-50 lg:hidden" onClose={setSidebarOpen}>
          <TransitionChild
            as={Fragment}
            enter="transition-opacity ease-linear duration-300"
            enterFrom="opacity-0"
            enterTo="opacity-100"
            leave="transition-opacity ease-linear duration-300"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <div className="fixed inset-0 bg-ink-900/80" />
          </TransitionChild>
          <div className="fixed inset-0 flex">
            <TransitionChild
              as={Fragment}
              enter="transition ease-in-out duration-300 transform"
              enterFrom="-translate-x-full"
              enterTo="translate-x-0"
              leave="transition ease-in-out duration-300 transform"
              leaveFrom="translate-x-0"
              leaveTo="-translate-x-full"
            >
              <DialogPanel className="relative mr-16 flex w-full max-w-xs flex-1">
                <TransitionChild
                  as={Fragment}
                  enter="ease-in-out duration-300"
                  enterFrom="opacity-0"
                  enterTo="opacity-100"
                  leave="ease-in-out duration-300"
                  leaveFrom="opacity-100"
                  leaveTo="opacity-0"
                >
                  <div className="absolute left-full top-0 flex w-16 justify-center pt-5">
                    <button type="button" className="-m-2.5 p-2.5" onClick={() => setSidebarOpen(false)}>
                      <span className="sr-only">{t("shell.closeSidebar")}</span>
                      <XMarkIcon className="h-6 w-6 text-white" aria-hidden="true" />
                    </button>
                  </div>
                </TransitionChild>
                <div className="flex grow flex-col gap-y-5 overflow-y-auto bg-white px-6 py-4">
                  <Brand />
                  <nav className="flex flex-1 flex-col">
                    {renderSections(false)}
                    <div className="mt-auto border-t border-ink-200 pt-2.5">{renderAccountMenu(false)}</div>
                  </nav>
                </div>
              </DialogPanel>
            </TransitionChild>
          </div>
        </Dialog>
      </Transition>

      {/* Desktop sidebar */}
      <div
        className={clsx(
          "hidden lg:fixed lg:inset-y-0 lg:z-50 lg:flex lg:flex-col transition-all duration-300",
          sidebarCollapsed ? "lg:w-20" : "lg:w-72",
        )}
      >
        <div
          className={clsx(
            "flex grow flex-col gap-y-5 overflow-y-auto border-r border-ink-100 bg-white pb-4 transition-all",
            sidebarCollapsed ? "px-3" : "px-6",
          )}
        >
          <div
            className={clsx(
              "flex h-16 shrink-0 items-center border-b border-ink-100 mb-2",
              sidebarCollapsed ? "justify-center" : "gap-3",
            )}
          >
            <Brand collapsed={sidebarCollapsed} />
          </div>

          <nav className="flex flex-1 flex-col">
            {renderSections(sidebarCollapsed)}

            <div className="mt-auto pt-4">
              <div className="mb-2 border-t border-ink-200 pt-2.5">
                {renderAccountMenu(sidebarCollapsed)}
              </div>
              <button
                type="button"
                onClick={() => setSidebarCollapsed((prev) => !prev)}
                className={clsx(
                  "flex items-center gap-2 w-full rounded-xl py-2.5 text-sm text-ink-500 hover:bg-ink-50 hover:text-ink-900 transition-all",
                  sidebarCollapsed ? "justify-center px-2" : "px-3",
                )}
              >
                {sidebarCollapsed ? (
                  <ChevronDoubleRightIcon className="h-5 w-5" />
                ) : (
                  <>
                    <ChevronDoubleLeftIcon className="h-5 w-5" />
                    <span>{t("shell.collapse")}</span>
                  </>
                )}
              </button>
            </div>
          </nav>
        </div>
      </div>

      <div className={clsx("transition-all", sidebarCollapsed ? "lg:pl-20" : "lg:pl-72")}>
        {/* Topbar */}
        <div className="sticky top-0 z-40 border-b border-ink-100 bg-white shadow-sm">
          <div className="flex h-16 items-center gap-x-4 px-4 sm:gap-x-6 sm:px-6 lg:px-8">
            <button
              type="button"
              onClick={() => setSidebarOpen(true)}
              className="-m-2.5 p-2.5 text-ink-500 hover:text-ink-900 lg:hidden"
            >
              <span className="sr-only">{t("shell.openSidebar")}</span>
              <Bars3Icon className="h-6 w-6" aria-hidden="true" />
            </button>

            <div className="h-6 w-px bg-ink-200 lg:hidden" aria-hidden="true" />

            <div className="flex flex-1 gap-x-4 self-stretch lg:gap-x-6">
              <div className="flex flex-1" />
              <div className="flex items-center gap-x-4 lg:gap-x-6">
                {/* The chat rail has had this since i18n shipped; the app shell
                    had nothing, so a student whose language was auto-detected
                    wrong on the dashboard had no way out without opening a
                    thesis first. The topbar is on every shell page, mobile
                    included. */}
                <LocaleSwitcher />

                <button
                  type="button"
                  className="-m-2.5 p-2.5 text-ink-500 hover:text-ink-900"
                  aria-label={t("shell.notifications")}
                >
                  <BellIcon className="h-6 w-6" aria-hidden="true" />
                </button>

              </div>
            </div>
          </div>
        </div>

        {fullBleed ? (
          <main className="min-h-[calc(100vh-4rem)] bg-white">{children}</main>
        ) : (
          <main className="bg-gradient-to-b from-primary-50/60 to-white min-h-[calc(100vh-4rem)] py-10">
            <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">{children}</div>
          </main>
        )}
      </div>
    </div>
  );
}

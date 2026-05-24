"use client";

import { useEffect, useState, type ReactNode } from "react";
import useSWR from "swr";

import { swrFetcher } from "@/app/lib/api";
import { useMe } from "@/app/lib/use-me";

import { AnnouncementDialog, type AnnouncementShape } from "./AnnouncementDialog";

type MeAnnouncements = {
  first_login: AnnouncementShape | null;
  login_banner: AnnouncementShape | null;
};

const FIRST_LOGIN_TTL_HOURS = 48;

export function AnnouncementProvider({ children }: { children: ReactNode }) {
  const me = useMe();
  const { data } = useSWR<MeAnnouncements>(me.data ? "/announcements/me" : null, swrFetcher);
  const [showFirstLogin, setShowFirstLogin] = useState(false);
  const [showBanner, setShowBanner] = useState(false);

  // first_login: once per user, only within 48h of signup
  useEffect(() => {
    if (!data?.first_login || !me.data) return;
    const created = me.data.created_at;
    if (created) {
      const ageMs = Date.now() - new Date(created).getTime();
      if (ageMs > FIRST_LOGIN_TTL_HOURS * 3600 * 1000) return;
    }
    const key = `opendraft_first_announcement_${me.data.id}`;
    if (window.localStorage.getItem(key)) return;
    window.localStorage.setItem(key, "1");
    setShowFirstLogin(true);
  }, [data?.first_login, me.data]);

  // login_banner: once per day per user per announcement id
  useEffect(() => {
    if (!data?.login_banner || !me.data) return;
    const key = `opendraft_login_banner_${me.data.id}_${data.login_banner.id}`;
    const stored = window.localStorage.getItem(key);
    const startOfToday = new Date().setHours(0, 0, 0, 0);
    if (stored && parseInt(stored, 10) >= startOfToday) return;
    window.localStorage.setItem(key, String(Date.now()));
    setShowBanner(true);
  }, [data?.login_banner, me.data]);

  return (
    <>
      {children}
      {data?.first_login && (
        <AnnouncementDialog
          announcement={data.first_login}
          open={showFirstLogin}
          onClose={() => setShowFirstLogin(false)}
        />
      )}
      {data?.login_banner && (
        <AnnouncementDialog
          announcement={data.login_banner}
          open={showBanner}
          onClose={() => setShowBanner(false)}
        />
      )}
    </>
  );
}

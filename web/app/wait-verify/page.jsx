"use client";
import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { AuthBrand } from "../components/layout/Brand";
import { apiFetch } from "../lib/api";

function WaitVerifyInner() {
  const params = useSearchParams();
  const email = params.get("email") || "your email";
  const [cooldown, setCooldown] = useState(0);
  const [sending, setSending] = useState(false);
  const [note, setNote] = useState(null);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  const resend = async () => {
    setSending(true);
    setNote(null);
    try {
      await apiFetch("/auth/resend-verification", { method: "POST", body: { email } });
      setNote("Sent. Check your inbox (and spam folder).");
      setCooldown(60);
    } catch (err) {
      const retry = err?.body?.detail?.error?.retry_in;
      if (retry) {
        setCooldown(retry);
        setNote(`Please wait ${retry}s before requesting another.`);
      } else {
        setNote(err.message || "Could not send.");
      }
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="w-full max-w-md bg-white rounded-2xl border border-ink-100 shadow-sm p-8 text-center space-y-4">
      <AuthBrand />
      <div className="text-4xl">📬</div>
      <h1 className="text-xl font-bold text-ink-900">Check your inbox</h1>
      <p className="text-sm text-ink-500">
        We sent a verification link to <b className="text-ink-900">{email}</b>. Click it to finish creating your account.
      </p>
      <button
        type="button" onClick={resend} disabled={sending || cooldown > 0}
        className="rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 disabled:opacity-50"
      >
        {sending ? "Sending…" : cooldown > 0 ? `Resend in ${cooldown}s` : "Resend email"}
      </button>
      {note && <div className="text-xs text-ink-500">{note}</div>}
      <div className="pt-4 text-xs text-ink-500">
        Used the wrong email? <Link href="/signup" className="text-primary-600 font-medium hover:underline">Start over</Link>
      </div>
    </div>
  );
}

export default function WaitVerifyPage() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-ink-50 px-4 py-12">
      <Suspense fallback={null}>
        <WaitVerifyInner />
      </Suspense>
    </main>
  );
}

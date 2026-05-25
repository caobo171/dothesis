"use client";
import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { apiFetch } from "../lib/api";

function ResetInner() {
  const params = useSearchParams();
  const router = useRouter();
  const token = params.get("token") || "";
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    if (pw !== pw2) {
      setError("Passwords don't match.");
      return;
    }
    if (pw.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setBusy(true);
    try {
      await apiFetch("/auth/reset-password", { method: "POST", body: { token, new_password: pw } });
      router.push("/login?reset=success");
    } catch (err) {
      const code = err?.body?.detail?.error?.code;
      const map = {
        token_expired: "This reset link has expired. Request a new one.",
        token_invalid: "This reset link is invalid.",
        token_mismatch: "This is not a password-reset link.",
      };
      setError(map[code] || err.message || "Reset failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="w-full max-w-md bg-white rounded-2xl border border-ink-100 shadow-sm p-8 space-y-5">
      <div className="text-center">
        <div className="font-extrabold text-2xl text-ink-900">Do<span className="text-primary-600">Thesis</span></div>
        <h1 className="mt-3 text-xl font-bold text-ink-900">Choose a new password</h1>
      </div>
      {!token && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          This page expects a reset token in the URL. Use the link from your email.
        </div>
      )}
      <form onSubmit={submit} className="space-y-3">
        <label className="block">
          <span className="text-xs font-medium text-ink-500">New password (8+ chars)</span>
          <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} required minLength={8} autoFocus
                 className="mt-1 w-full rounded-xl border border-ink-200 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none" />
        </label>
        <label className="block">
          <span className="text-xs font-medium text-ink-500">Confirm password</span>
          <input type="password" value={pw2} onChange={(e) => setPw2(e.target.value)} required minLength={8}
                 className="mt-1 w-full rounded-xl border border-ink-200 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none" />
        </label>
        {error && <div className="text-xs text-red-700">{error}</div>}
        <button type="submit" disabled={busy || !token}
                className="w-full rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 disabled:opacity-50">
          {busy ? "Updating…" : "Update password"}
        </button>
        <div className="text-center text-xs">
          <Link href="/login" className="text-primary-600 hover:underline">Back to sign in</Link>
        </div>
      </form>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-ink-50 px-4 py-12">
      <Suspense fallback={null}>
        <ResetInner />
      </Suspense>
    </main>
  );
}

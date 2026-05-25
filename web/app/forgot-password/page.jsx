"use client";
import { useState } from "react";
import Link from "next/link";

import { apiFetch } from "../lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await apiFetch("/auth/forgot-password", { method: "POST", body: { email } });
      setSent(true);
    } catch (err) {
      setError(err.message || "Could not send reset email.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="min-h-screen flex items-center justify-center bg-ink-50 px-4 py-12">
      <div className="w-full max-w-md bg-white rounded-2xl border border-ink-100 shadow-sm p-8 space-y-5">
        <div className="text-center">
          <div className="font-extrabold text-2xl text-ink-900">Do<span className="text-primary-600">Thesis</span></div>
          <h1 className="mt-3 text-xl font-bold text-ink-900">Forgot your password?</h1>
        </div>

        {sent ? (
          <div className="text-sm text-ink-700 text-center space-y-3">
            <div className="text-3xl">📬</div>
            <p>If that email exists in our system, we sent a reset link. Check your inbox (and spam folder).</p>
            <Link href="/login" className="inline-block text-primary-600 font-medium hover:underline">Back to sign in</Link>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-3">
            <label className="block">
              <span className="text-xs font-medium text-ink-500">Email</span>
              <input
                type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus
                className="mt-1 w-full rounded-xl border border-ink-200 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
              />
            </label>
            {error && <div className="text-xs text-red-700">{error}</div>}
            <button type="submit" disabled={busy}
                    className="w-full rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 disabled:opacity-50">
              {busy ? "Sending…" : "Send reset link"}
            </button>
            <div className="text-center text-xs">
              <Link href="/login" className="text-primary-600 hover:underline">Back to sign in</Link>
            </div>
          </form>
        )}
      </div>
    </main>
  );
}

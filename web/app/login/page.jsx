"use client";
import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { GoogleSignInButton } from "../components/auth/GoogleSignInButton";
import { apiFetch } from "../lib/api";
import { useAuth } from "../lib/auth-context";

function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") || "/";
  const resetOk = params.get("reset") === "success";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [unverifiedEmail, setUnverifiedEmail] = useState(null);
  const [busy, setBusy] = useState(false);
  const [resending, setResending] = useState(false);
  const [resendNote, setResendNote] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    setUnverifiedEmail(null);
    setBusy(true);
    try {
      await login(email, password);
      router.push(next);
    } catch (err) {
      const code = err?.body?.detail?.error?.code;
      if (code === "unverified") {
        setUnverifiedEmail(err.body.detail.error.email || email);
      } else if (code === "use_google") {
        setError("This email is linked to Google. Use the Google button above.");
      } else {
        setError(err.message || "Login failed.");
      }
    } finally {
      setBusy(false);
    }
  };

  const resend = async () => {
    if (!unverifiedEmail) return;
    setResending(true);
    setResendNote(null);
    try {
      await apiFetch("/auth/resend-verification", { method: "POST", body: { email: unverifiedEmail } });
      setResendNote("Sent. Check your inbox.");
    } catch (e) {
      setResendNote(e.message || "Could not send.");
    } finally {
      setResending(false);
    }
  };

  return (
    <div className="w-full max-w-md bg-white rounded-2xl border border-ink-100 shadow-sm p-8 space-y-5">
      <div className="text-center">
        <div className="font-extrabold text-2xl text-ink-900">Do<span className="text-primary-600">Thesis</span></div>
        <h1 className="mt-3 text-xl font-bold text-ink-900">Sign in</h1>
        <p className="mt-1 text-sm text-ink-500">Continue to your draft workspace.</p>
      </div>

      {resetOk && (
        <div className="rounded-xl border border-green-200 bg-green-50 px-3 py-2 text-xs text-green-700">
          Password updated. Sign in with your new password.
        </div>
      )}

      <GoogleSignInButton onError={setError} />

      <form onSubmit={submit} className="space-y-3">
        <label className="block">
          <span className="text-xs font-medium text-ink-500">Email</span>
          <input
            type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus
            className="mt-1 w-full rounded-xl border border-ink-200 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
          />
        </label>
        <label className="block">
          <span className="text-xs font-medium text-ink-500">Password</span>
          <input
            type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8}
            className="mt-1 w-full rounded-xl border border-ink-200 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
          />
        </label>

        {unverifiedEmail && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800 space-y-2">
            <div>
              We sent a verification link to <b>{unverifiedEmail}</b>. Click it to finish signing in.
            </div>
            <button type="button" onClick={resend} disabled={resending}
                    className="rounded-md border border-amber-300 bg-white px-2 py-1 font-semibold text-amber-800 hover:bg-amber-100">
              {resending ? "Sending…" : "Resend email"}
            </button>
            {resendNote && <div>{resendNote}</div>}
          </div>
        )}
        {error && <div className="text-xs text-red-700">{error}</div>}

        <button type="submit" disabled={busy}
                className="w-full rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 disabled:opacity-50">
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <div className="flex justify-between text-xs">
          <Link href="/forgot-password" className="text-primary-600 hover:underline">Forgot password?</Link>
          <Link href="/signup" className="text-primary-600 hover:underline">Create account</Link>
        </div>
      </form>
    </div>
  );
}

export default function LoginPage() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-ink-50 px-4 py-12">
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </main>
  );
}

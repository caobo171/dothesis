"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { GoogleSignInButton } from "../components/auth/GoogleSignInButton";
import { apiFetch } from "../lib/api";

const USERNAME_RE = /^[a-zA-Z0-9_]{3,32}$/;

export default function SignupPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    if (!USERNAME_RE.test(username)) {
      setError("Username must be 3–32 characters, letters/numbers/underscore only.");
      return;
    }
    setBusy(true);
    try {
      await apiFetch("/auth/signup", { method: "POST", body: { username, email, password } });
      router.push(`/wait-verify?email=${encodeURIComponent(email)}`);
    } catch (err) {
      const code = err?.body?.detail?.error?.code;
      const map = {
        email_taken: "That email is already registered. Try signing in instead.",
        username_taken: "That username is taken. Pick another.",
        bad_username: "Username must be 3–32 characters, letters/numbers/underscore only.",
      };
      setError(map[code] || err.message || "Signup failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="min-h-screen flex items-center justify-center bg-ink-50 px-4 py-12">
      <div className="w-full max-w-md bg-white rounded-2xl border border-ink-100 shadow-sm p-8 space-y-5">
        <div className="text-center">
          <div className="font-extrabold text-2xl text-ink-900">Do<span className="text-primary-600">Thesis</span></div>
          <h1 className="mt-3 text-xl font-bold text-ink-900">Create your account</h1>
          <p className="mt-1 text-sm text-ink-500">Sign up to start drafting verified-citation theses.</p>
        </div>

        <GoogleSignInButton onError={setError} />

        <form onSubmit={submit} className="space-y-3">
          <label className="block">
            <span className="text-xs font-medium text-ink-500">Username</span>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
              className="mt-1 w-full rounded-xl border border-ink-200 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
              placeholder="your_handle"
              pattern="[a-zA-Z0-9_]{3,32}"
            />
          </label>
          <label className="block">
            <span className="text-xs font-medium text-ink-500">Email</span>
            <input
              type="email" value={email} onChange={(e) => setEmail(e.target.value)} required
              className="mt-1 w-full rounded-xl border border-ink-200 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
            />
          </label>
          <label className="block">
            <span className="text-xs font-medium text-ink-500">Password (8+ chars)</span>
            <input
              type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8}
              className="mt-1 w-full rounded-xl border border-ink-200 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
            />
          </label>
          {error && <div className="text-xs text-red-700">{error}</div>}
          <button
            type="submit" disabled={busy}
            className="w-full rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 disabled:opacity-50"
          >
            {busy ? "Creating account…" : "Create account"}
          </button>
        </form>

        <div className="text-center text-sm text-ink-500">
          Already have an account?{" "}
          <Link href="/login" className="text-primary-600 font-medium hover:underline">Sign in</Link>
        </div>
      </div>
    </main>
  );
}

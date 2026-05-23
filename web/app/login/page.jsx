"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "../lib/auth-context";

function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") || "/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email, password);
      router.push(next);
    } catch (err) {
      setError(err.message || "Login failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="card" style={{ padding: 32, width: 360, display: "flex", flexDirection: "column", gap: 14 }}>
      <h1 className="section-title" style={{ marginBottom: 4 }}>Sign in</h1>
      <p style={{ color: "var(--ink-500)", fontSize: 13, margin: 0 }}>Use the email and password you signed up with.</p>
      <div className="field">
        <label>Email</label>
        <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required autoFocus />
      </div>
      <div className="field">
        <label>Password</label>
        <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" minLength={8} required />
      </div>
      {error && <div style={{ color: "var(--danger-fg)", fontSize: 12 }}>{error}</div>}
      <button className="btn btn-primary btn-lg btn-block" disabled={busy} type="submit">
        {busy ? "Signing in…" : "Sign in"}
      </button>
      <a href="/signup" style={{ fontSize: 13, color: "var(--blue-600)", textAlign: "center" }}>
        Create an account
      </a>
    </form>
  );
}

export default function LoginPage() {
  return (
    <div style={{ display: "grid", placeItems: "center", minHeight: "100vh", background: "var(--ink-50)" }}>
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </div>
  );
}

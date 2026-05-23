"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../lib/auth-context";

export default function SignupPage() {
  const { signup } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await signup(email, password);
      router.push("/");
    } catch (err) {
      setError(err.message || "Signup failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: "grid", placeItems: "center", minHeight: "100vh", background: "var(--ink-50)" }}>
      <form onSubmit={submit} className="card" style={{ padding: 32, width: 360, display: "flex", flexDirection: "column", gap: 14 }}>
        <h1 className="section-title" style={{ marginBottom: 4 }}>Create account</h1>
        <div className="field">
          <label>Email</label>
          <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required autoFocus />
        </div>
        <div className="field">
          <label>Password (≥ 8 chars)</label>
          <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" minLength={8} required />
        </div>
        {error && <div style={{ color: "var(--danger-fg)", fontSize: 12 }}>{error}</div>}
        <button className="btn btn-primary btn-lg btn-block" disabled={busy} type="submit">
          {busy ? "Creating…" : "Create account"}
        </button>
        <a href="/login" style={{ fontSize: 13, color: "var(--blue-600)", textAlign: "center" }}>
          Already have an account? Sign in
        </a>
      </form>
    </div>
  );
}

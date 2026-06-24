"use client";
import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { GoogleSignInButton } from "../components/auth/GoogleSignInButton";
import { apiFetch } from "../lib/api";
import { useAuth } from "../lib/auth-context";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";

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
    <Card className="w-full max-w-md">
      <CardHeader className="text-center">
        <div className="font-extrabold text-2xl text-ink-900">Do<span className="text-primary-600">Thesis</span></div>
        <CardTitle className="mt-2 text-xl">Sign in</CardTitle>
        <CardDescription>Continue to your draft workspace.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {resetOk && (
          <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-xs text-green-700">
            Password updated. Sign in with your new password.
          </div>
        )}

        <GoogleSignInButton onError={setError} />

        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password">Password</Label>
            <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} />
          </div>

          {unverifiedEmail && (
            <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800 space-y-2">
              <div>
                We sent a verification link to <b>{unverifiedEmail}</b>. Click it to finish signing in.
              </div>
              <Button type="button" variant="outline" size="sm" onClick={resend} disabled={resending}>
                {resending ? "Sending…" : "Resend email"}
              </Button>
              {resendNote && <div>{resendNote}</div>}
            </div>
          )}
          {error && <div className="text-sm text-destructive">{error}</div>}

          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </Button>
          <div className="flex justify-between text-xs">
            <Link href="/forgot-password" className="text-primary-600 hover:underline">Forgot password?</Link>
            <Link href="/signup" className="text-primary-600 hover:underline">Create account</Link>
          </div>
        </form>
      </CardContent>
    </Card>
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

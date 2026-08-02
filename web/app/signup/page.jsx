"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { GoogleSignInButton } from "../components/auth/GoogleSignInButton";
import { AuthBrand } from "../components/layout/Brand";
import { apiFetch } from "../lib/api";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { PasswordInput } from "../components/ui/password-input";
import { Label } from "../components/ui/label";

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
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <AuthBrand />
          <CardTitle className="mt-2 text-xl">Create your account</CardTitle>
          <CardDescription>Sign up to start drafting verified-citation theses.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <GoogleSignInButton onError={setError} />

          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoFocus
                placeholder="your_handle"
                pattern="[a-zA-Z0-9_]{3,32}"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" placeholder="Enter your email address" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Password (8+ chars)</Label>
              <PasswordInput id="password" placeholder="Create a password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} />
            </div>
            {error && <div className="text-sm text-destructive">{error}</div>}
            <Button type="submit" className="w-full" disabled={busy}>
              {busy ? "Creating account…" : "Create account"}
            </Button>
          </form>

          <div className="text-center text-sm text-muted-foreground">
            Already have an account?{" "}
            <Link href="/login" className="text-primary-600 font-medium hover:underline">Sign in</Link>
          </div>
        </CardContent>
      </Card>
    </main>
  );
}

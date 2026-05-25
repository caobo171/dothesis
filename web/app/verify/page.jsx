"use client";
import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { apiFetch } from "../lib/api";

function VerifyInner() {
  const params = useSearchParams();
  const router = useRouter();
  const token = params.get("token") || "";
  const [state, setState] = useState("pending");
  const [errorMsg, setErrorMsg] = useState(null);

  useEffect(() => {
    if (!token) {
      setState("error");
      setErrorMsg("This verification link is missing the token.");
      return;
    }
    apiFetch("/auth/verify", { method: "POST", body: { token } })
      .then(() => {
        setState("success");
        setTimeout(() => router.push("/"), 1800);
      })
      .catch((err) => {
        const code = err?.body?.detail?.error?.code;
        const map = {
          token_expired: "This link has expired. Request a new verification email below.",
          token_invalid: "This link is invalid.",
          token_mismatch: "This link is not a verification link.",
        };
        setErrorMsg(map[code] || err.message || "Verification failed.");
        setState("error");
      });
  }, [token, router]);

  return (
    <div className="w-full max-w-md bg-white rounded-2xl border border-ink-100 shadow-sm p-8 text-center space-y-4">
      <div className="font-extrabold text-2xl text-ink-900">Do<span className="text-primary-600">Thesis</span></div>

      {state === "pending" && (
        <>
          <div className="text-2xl">⏳</div>
          <h1 className="text-xl font-bold text-ink-900">Verifying…</h1>
        </>
      )}
      {state === "success" && (
        <>
          <div className="text-4xl">✅</div>
          <h1 className="text-xl font-bold text-ink-900">You're in!</h1>
          <p className="text-sm text-ink-500">Redirecting to your dashboard…</p>
        </>
      )}
      {state === "error" && (
        <>
          <div className="text-4xl">⚠️</div>
          <h1 className="text-xl font-bold text-ink-900">Verification failed</h1>
          <p className="text-sm text-ink-500">{errorMsg}</p>
          <Link href="/login" className="inline-block rounded-xl bg-primary-600 px-4 py-2 text-sm font-semibold text-white">
            Back to sign in
          </Link>
        </>
      )}
    </div>
  );
}

export default function VerifyPage() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-ink-50 px-4 py-12">
      <Suspense fallback={null}>
        <VerifyInner />
      </Suspense>
    </main>
  );
}

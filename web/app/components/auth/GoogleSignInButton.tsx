"use client";
import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

import { apiFetch } from "@/app/lib/api";
import { useAuth } from "@/app/lib/auth-context";

const CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "";

declare global {
  interface Window {
    google?: any;
  }
}

export function GoogleSignInButton({ onError }: { onError?: (msg: string) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const router = useRouter();
  // /auth/google now returns TokenOut — pipe it through the auth context
  // so the access_token gets persisted to tokenStore before we navigate.
  const { acceptTokenPayload } = useAuth();

  useEffect(() => {
    if (!CLIENT_ID) return;
    let script = document.querySelector<HTMLScriptElement>('script[src="https://accounts.google.com/gsi/client"]');
    let added = false;
    if (!script) {
      script = document.createElement("script");
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true;
      script.defer = true;
      document.body.appendChild(script);
      added = true;
    }
    const init = () => {
      if (!window.google?.accounts?.id || !ref.current) return;
      window.google.accounts.id.initialize({
        client_id: CLIENT_ID,
        callback: async (resp: any) => {
          try {
            const payload = await apiFetch("/auth/google", {
              method: "POST",
              body: { id_token: resp.credential },
              auth: false,
            });
            acceptTokenPayload(payload);
            router.push("/");
          } catch (e: any) {
            onError?.(e?.body?.detail?.error?.message || e?.message || "Google sign-in failed");
          }
        },
      });
      window.google.accounts.id.renderButton(ref.current, {
        theme: "outline", size: "large", width: 320, shape: "rectangular",
      });
    };
    if (window.google?.accounts?.id) {
      init();
    } else {
      script.onload = init;
    }
    return () => {
      if (added) { /* no-op: keep script for other consumers */ }
    };
  }, [router, onError]);

  if (!CLIENT_ID) {
    return (
      <button
        type="button"
        disabled
        className="w-full rounded-xl border border-ink-200 px-4 py-2.5 text-sm font-medium text-ink-400 cursor-not-allowed"
        title="OPENDRAFT_GOOGLE_CLIENT_ID is not set"
      >
        Google sign-in (not configured)
      </button>
    );
  }
  return <div ref={ref} className="flex justify-center" />;
}

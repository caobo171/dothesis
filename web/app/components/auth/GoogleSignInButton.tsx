"use client";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

import { apiFetch } from "@/app/lib/api";
import { useAuth } from "@/app/lib/auth-context";
import { goToNext } from "@/app/lib/nextPath";

const CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "";

declare global {
  interface Window {
    google?: any;
  }
}

// Renders the Google sign-in widget AND its "or with email" divider as one unit.
// On origins Google hasn't authorized (e.g. *.trycloudflare.com tunnels) GIS
// silently renders nothing — which used to leave a dead gap + a dangling
// divider. We detect that the widget never appeared and hide the whole block,
// so the form falls back cleanly to email/password. On a properly registered
// domain the widget renders and everything shows again automatically.
type Status = "off" | "pending" | "on";

export function GoogleSignInButton({ onError }: { onError?: (msg: string) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  // Honour ?next= exactly as the email form does. It used to hard-push "/",
  // which silently dropped the destination — a user who signed in with Google
  // partway through the MCP connector flow landed on the dashboard and the
  // OAuth handshake they were in the middle of just vanished.
  const params = useSearchParams();
  // /auth/google now returns TokenOut — pipe it through the auth context
  // so the access_token gets persisted to tokenStore before we navigate.
  const { acceptTokenPayload } = useAuth();
  const [status, setStatus] = useState<Status>(CLIENT_ID ? "pending" : "off");

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
    // GIS only accepts a fixed pixel width (max 400), not "100%". Measure the
    // wrapper and render the button at that width so it lines up with the
    // full-width email/password inputs instead of sitting narrow + centered.
    const renderAtContainerWidth = () => {
      if (!window.google?.accounts?.id || !ref.current) return;
      const w = Math.min(ref.current.offsetWidth || 320, 400);
      ref.current.innerHTML = "";
      window.google.accounts.id.renderButton(ref.current, {
        theme: "outline", size: "large", width: w, shape: "rectangular",
      });
    };
    // If the widget never paints (unauthorized origin / blocked script), hide
    // the block instead of leaving an empty gap.
    const verifyRendered = () => {
      // GIS inserts an iframe even on unauthorized origins, but it stays
      // collapsed (≈0 height) because the content fails to load. Require a real
      // rendered height so a broken/empty widget counts as "not available".
      const el = ref.current;
      const ok = !!el && el.childElementCount > 0 && el.offsetHeight > 20;
      setStatus(ok ? "on" : "off");
    };
    const init = () => {
      if (!window.google?.accounts?.id || !ref.current) { setStatus("off"); return; }
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
            goToNext(params.get("next"));
          } catch (e: any) {
            onError?.(e?.body?.detail?.error?.message || e?.message || "Google sign-in failed");
          }
        },
      });
      renderAtContainerWidth();
      // GIS paints asynchronously; check shortly after.
      setTimeout(verifyRendered, 1200);
    };
    if (window.google?.accounts?.id) {
      init();
    } else {
      script.onload = init;
      // Script blocked or slow → don't hang in "pending" forever.
      script.onerror = () => setStatus("off");
    }
    // Hard timeout backstop in case onload never fires.
    const backstop = setTimeout(() => {
      if (!window.google?.accounts?.id) setStatus("off");
    }, 4000);
    // Re-render on container resize so the button keeps matching the form width.
    const ro = ref.current ? new ResizeObserver(() => renderAtContainerWidth()) : null;
    if (ro && ref.current) ro.observe(ref.current);
    return () => {
      clearTimeout(backstop);
      ro?.disconnect();
      if (added) { /* no-op: keep script for other consumers */ }
    };
  }, [params, onError]);

  if (status === "off") return null;

  return (
    <>
      {/* `gis-button` is the hook for the radius override in globals.css — see
          the note there. Don't clip this wrapper with overflow-hidden: GIS
          draws the button's own 1px border at a 4px radius, and clipping at
          8px shears the corners off it. */}
      <div ref={ref} className="gis-button w-full min-h-[2.75rem]" />
      <div className="flex items-center gap-3 text-xs text-ink-400">
        <span className="flex-1 h-px bg-ink-100" />
        <span>or with email</span>
        <span className="flex-1 h-px bg-ink-100" />
      </div>
    </>
  );
}

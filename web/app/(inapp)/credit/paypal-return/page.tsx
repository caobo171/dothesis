"use client";

import { useEffect, useState } from "react";

import { apiFetch } from "@/app/lib/api";

/**
 * PayPal redirects here after approval with ?token=<paypal_order_id>. We capture
 * the order (the webhook is the backstop; whichever lands first grants credits),
 * then bounce back to /credit.
 */
export default function PayPalReturnPage() {
  const [state, setState] = useState<"capturing" | "ok" | "error">("capturing");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get("token");
    if (!token) {
      setState("error");
      setMsg("Missing PayPal order token.");
      return;
    }
    (async () => {
      try {
        await apiFetch("/credit/paypal/capture", {
          method: "POST",
          body: { paypal_order_id: token },
        });
        setState("ok");
        setTimeout(() => (window.location.href = "/credit"), 2000);
      } catch (e: any) {
        setState("error");
        setMsg(e?.message || "Could not confirm the PayPal payment.");
      }
    })();
  }, []);

  return (
    <div className="mx-auto max-w-md px-6 py-20 text-center">
      {state === "capturing" && <p className="text-ink-600">Confirming your PayPal payment…</p>}
      {state === "ok" && (
        <div className="rounded-xl bg-green-50 px-4 py-6 text-green-700">
          Payment confirmed — credits added. Redirecting…
        </div>
      )}
      {state === "error" && (
        <div className="rounded-xl bg-red-50 px-4 py-6 text-red-700">
          {msg}{" "}
          <a href="/credit" className="font-semibold underline">
            Back to credits
          </a>
        </div>
      )}
    </div>
  );
}

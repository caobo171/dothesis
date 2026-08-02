"use client";

import { useEffect, useState } from "react";
import { Check, Copy, ExternalLink } from "lucide-react";

/**
 * MCP connector setup — Claude and ChatGPT.
 *
 * Lives under ACCOUNT rather than ADMIN: adding a connector is something each
 * person does in their OWN client, not something an operator configures once.
 *
 * Content is derived from mcp/README.md + mcp/RUNBOOK.md rather than written
 * from memory, because the two clients genuinely differ (Claude takes a custom
 * connector URL; ChatGPT gates MCP behind developer mode) and a confidently
 * wrong instruction here costs a student more time than no instruction at all.
 *
 * The OAuth caveat is deliberately loud. mcp/MCP_OAUTH_PLAN.md is a PLAN — the
 * façade is not built, so there is no per-user login yet and the server still
 * authenticates with a single shared token. Shipping a "connect your account"
 * page that implies otherwise would be the dishonest version of this feature.
 */

/**
 * The MCP URL is THIS PAGE'S OWN ORIGIN + /mcp. No env var, no derivation.
 *
 * `/api/v1/*` is already a Next rewrite onto FastAPI (see web/proxy.js), so
 * from a browser the whole product is one origin. Routing `/mcp` the same way
 * makes the connector URL something the page can simply read off the address
 * bar — correct in dev, on the tunnel, and in production without anything to
 * configure.
 *
 * A first attempt derived this from NEXT_PUBLIC_API_BASE. That broke exactly
 * because of the rewrite: the base is relative (or unset), `new URL()` threw,
 * and the field rendered a bare "/mcp" with no host — a URL nobody can paste
 * into Claude.
 */
function useMcpUrl(): string {
  // Computed after mount rather than during render: window doesn't exist during
  // SSR, and rendering a different value on the server than on the first client
  // pass is a hydration mismatch. Both start empty, then this fills it in.
  const [url, setUrl] = useState("");
  useEffect(() => {
    setUrl(`${window.location.origin}/mcp`);
  }, []);
  return url;
}

function CopyRow({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11.5px] font-semibold text-ink-500">{label}</span>
      <div className="flex items-center gap-2 rounded-xl border border-ink-200 bg-ink-50 px-3 py-2">
        <code className="flex-1 text-[12.5px] text-ink-800 font-mono truncate">{value}</code>
        <button
          type="button"
          onClick={() => {
            void navigator.clipboard.writeText(value);
            setCopied(true);
            setTimeout(() => setCopied(false), 1400);
          }}
          aria-label={`Copy ${label}`}
          className="shrink-0 inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[12px] font-semibold text-ink-600 hover:bg-ink-200"
        >
          {copied ? <Check className="w-3.5 h-3.5 text-green-600" /> : <Copy className="w-3.5 h-3.5" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
    </div>
  );
}

function Step({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <li className="flex gap-3">
      <span className="shrink-0 w-6 h-6 rounded-full bg-primary-600 text-white text-[12px] font-bold inline-flex items-center justify-center">
        {n}
      </span>
      <span className="text-[13.5px] text-ink-700 leading-relaxed pt-0.5">{children}</span>
    </li>
  );
}

type Tab = "claude" | "chatgpt";

export default function McpSetupPage() {
  const [tab, setTab] = useState<Tab>("claude");
  const MCP_URL = useMcpUrl();

  return (
    <div className="max-w-3xl mx-auto py-8 px-4 flex flex-col gap-6">
      <div>
        <h1 className="m-0 text-[24px] font-extrabold font-serif tracking-tight text-ink-900">
          Connect DoThesis to your AI
        </h1>
        <p className="mt-1.5 text-[14px] text-ink-500">
          Add DoThesis as an MCP connector and use its tools directly inside
          Claude or ChatGPT — starting with <strong>humanize</strong>.
        </p>
      </div>

      {/* Status is stated up front rather than buried. The OAuth façade in
          mcp/MCP_OAUTH_PLAN.md is not built, so there is no per-user sign-in
          and the server runs on one shared token behind a dev tunnel. */}
      <div className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3">
        <div className="text-[13px] font-bold text-amber-900">Preview — not open to students yet</div>
        <p className="mt-1 text-[12.5px] text-amber-900/90 m-0 leading-relaxed">
          The connector runs on a development tunnel and authenticates with a
          single shared token, because per-user sign-in (OAuth 2.1) is still a
          plan, not a build. Until that lands, treat this as an internal setup
          guide: anyone who adds the connector shares one identity, so don&apos;t
          hand the URL to students.
        </p>
      </div>

      <div className="flex flex-col gap-3">
        <CopyRow label="Server URL" value={MCP_URL} />
        <div className="flex gap-6 text-[12.5px] text-ink-600">
          <span><strong className="text-ink-800">Transport:</strong> Streamable HTTP</span>
          <span><strong className="text-ink-800">Tools:</strong> humanize</span>
        </div>
      </div>

      <div className="flex gap-1 border-b border-ink-200">
        {(["claude", "chatgpt"] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-[13.5px] font-semibold border-b-2 -mb-px transition-colors ${
              tab === t
                ? "border-primary-600 text-primary-700"
                : "border-transparent text-ink-500 hover:text-ink-800"
            }`}
          >
            {t === "claude" ? "Claude" : "ChatGPT"}
          </button>
        ))}
      </div>

      {tab === "claude" ? (
        <ol className="flex flex-col gap-3.5 m-0 p-0 list-none">
          <Step n={1}>
            Open <strong>claude.ai</strong> → <strong>Settings</strong> →{" "}
            <strong>Connectors</strong>. (Claude Desktop has the same section
            under Settings.)
          </Step>
          <Step n={2}>
            Choose <strong>Add custom connector</strong> and paste the Server URL
            above.
          </Step>
          <Step n={3}>
            Save, then start a new chat. DoThesis appears in the tool menu and{" "}
            <code className="text-[12px] bg-ink-100 rounded px-1 py-0.5">humanize</code>{" "}
            becomes callable.
          </Step>
          <Step n={4}>
            Ask it to re-voice a passage. The first run asks for ~150 words you
            wrote yourself — that&apos;s the style anchor, and it&apos;s only
            asked once.
          </Step>
        </ol>
      ) : (
        <ol className="flex flex-col gap-3.5 m-0 p-0 list-none">
          <Step n={1}>
            MCP connectors in ChatGPT need <strong>developer mode</strong>, and
            availability depends on your plan — check{" "}
            <strong>Settings → Connectors</strong> first. If you don&apos;t see
            it, your account can&apos;t add custom MCP servers yet.
          </Step>
          <Step n={2}>
            In <strong>Settings → Connectors → Advanced</strong>, enable
            developer mode, then <strong>Create</strong> a connector.
          </Step>
          <Step n={3}>
            Paste the Server URL above and choose the{" "}
            <strong>Streamable HTTP</strong> transport. Authentication is{" "}
            <strong>none</strong> until the OAuth façade ships.
          </Step>
          <Step n={4}>
            Enable the connector in a chat&apos;s tools list, then ask it to
            humanize a passage.
          </Step>
        </ol>
      )}

      <div className="rounded-xl border border-ink-200 bg-white p-4">
        <div className="text-[13px] font-bold text-ink-900">What humanize does — and doesn&apos;t</div>
        <p className="mt-1.5 text-[12.5px] text-ink-600 m-0 leading-relaxed">
          It reduces the AI-detection &quot;smell&quot; of prose you already
          wrote, freezing every number, table reference, term and citation — a
          rewrite that moves one is discarded and the original returned. It is{" "}
          <strong>not</strong> a plagiarism or similarity tool, and it does{" "}
          <strong>not</strong> guarantee passing any specific detector.
        </p>
        <a
          href="https://modelcontextprotocol.io/docs/develop/connect-local-servers"
          target="_blank"
          rel="noreferrer"
          className="mt-3 inline-flex items-center gap-1.5 text-[12.5px] font-semibold text-primary-700 hover:underline"
        >
          MCP documentation <ExternalLink className="w-3.5 h-3.5" />
        </a>
      </div>
    </div>
  );
}

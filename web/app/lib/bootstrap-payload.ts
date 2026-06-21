// Bootstrap-payload stash — handoff from the /new bootstrap form to the
// chat surface. The form stashes what the user declared (topic + any
// optional fields) keyed by the freshly-created project id; ChatPane reads
// it on mount and sends a structured first message to the agent so the
// dothesis-bootstrap skill can commit each slice on turn 1.

// Topic now lives inside the grid as the M1 item, so it's just another
// BootstrapItemId — no special-casing on the stash helper.
export type BootstrapItemId =
  | "topic" | "references" | "gaps" | "model" | "instrument" | "data" | "draft";

export type BootstrapPayload = Partial<Record<BootstrapItemId, string>>;

const PAYLOAD_KEY_PREFIX = "dothesis_bootstrap_v1:";

export function stashBootstrapPayload(
  projectId: string,
  have: Set<BootstrapItemId>,
  payload: Partial<Record<BootstrapItemId, string>>,
): void {
  if (typeof window === "undefined") return;
  const data: BootstrapPayload = {};
  have.forEach(id => {
    const v = (payload[id] ?? "").trim();
    if (v) data[id] = v;
  });
  if (Object.keys(data).length === 0) return;
  try {
    window.sessionStorage.setItem(
      PAYLOAD_KEY_PREFIX + projectId,
      JSON.stringify(data),
    );
  } catch { /* sessionStorage may be unavailable in private modes */ }
}

/**
 * Pull (and clear) the bootstrap payload for a freshly-created project.
 *
 * Called by the chat surface on mount; returns null when there is no
 * stash so callers can branch trivially.
 */
export function readBootstrapPayload(projectId: string): BootstrapPayload | null {
  if (typeof window === "undefined") return null;
  const key = PAYLOAD_KEY_PREFIX + projectId;
  const raw = window.sessionStorage.getItem(key);
  if (!raw) return null;
  try {
    window.sessionStorage.removeItem(key);
    return JSON.parse(raw) as BootstrapPayload;
  } catch {
    return null;
  }
}

/** Compose the user-message text the chat surface sends as the first
 *  turn — matches the dothesis-bootstrap skill's expected input shape. */
export function formatBootstrapMessage(p: BootstrapPayload): string {
  const lines: string[] = ["/bootstrap", ""];
  if (p.topic) lines.push(`Topic: ${p.topic}`);
  if (p.references) lines.push(`References:\n${p.references}`);
  if (p.gaps) lines.push(`Gaps:\n${p.gaps}`);
  if (p.model) lines.push(`Model:\n${p.model}`);
  if (p.instrument) lines.push(`Instrument:\n${p.instrument}`);
  if (p.data) lines.push(`Data:\n${p.data}`);
  if (p.draft) lines.push(`Draft:\n${p.draft}`);
  return lines.join("\n\n");
}

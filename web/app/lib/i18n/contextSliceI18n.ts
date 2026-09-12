import type { MessageKey } from "./messages/en";
import type { TParams } from "./locale";

/** Stable slug for a stored methodology value → translation key suffix. */
export function contextValueSlug(raw: string): string {
  return raw.toLowerCase().trim().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
}

/** Translate a committed slice value when a catalogue entry exists; else show raw. */
export function translateContextValue(
  t: (key: MessageKey, params?: TParams) => string,
  category: string,
  raw: string,
): string {
  if (!raw) return raw;
  const key = `context.value.${category}.${contextValueSlug(raw)}` as MessageKey;
  const out = t(key);
  return out === key ? raw : out;
}

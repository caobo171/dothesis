// Runs in the main Node process BEFORE any test environment (jsdom/happy-dom) is set up.
// Captures Node's native AbortController/AbortSignal so that setup.ts can restore them
// after jsdom replaces globalThis.AbortController with its own realm-local version.
//
// Why needed: MSW's fetch interceptor creates Request objects via Node's built-in undici.
// Undici checks `signal instanceof AbortSignal` using the AbortSignal it captured at
// startup (Node's native one). jsdom installs its own AbortController/AbortSignal onto
// globalThis, so `new AbortController()` in tests produces jsdom-realm signals that fail
// undici's instanceof check → "Expected signal to be an instance of AbortSignal".
export function setup() {
  (globalThis as unknown as Record<string, unknown>).__nativeAbortController__ =
    globalThis.AbortController;
  (globalThis as unknown as Record<string, unknown>).__nativeAbortSignal__ =
    globalThis.AbortSignal;
}

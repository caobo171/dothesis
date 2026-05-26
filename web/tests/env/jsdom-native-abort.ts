/**
 * Custom Vitest environment: jsdom + native AbortController restoration.
 *
 * Problem: jsdom installs its own AbortController/AbortSignal onto globalThis.
 * MSW's fetch interceptor calls `new Request(url, { signal })` which delegates to
 * Node's built-in undici. Undici's internal webidl converter checks
 * `signal instanceof [Node-internal AbortSignal]`, but the signal produced by
 * jsdom's AbortController is a different class → "Expected signal to be an
 * instance of AbortSignal".
 *
 * Fix: wrap the jsdom environment, capture Node's native AbortController before
 * jsdom's populateGlobal replaces it, then restore it after setup so that
 * `new AbortController()` in tests produces Node-realm signals.
 */
import { builtinEnvironments, populateGlobal } from "vitest/environments";

export default {
  name: "jsdom-native-abort",
  transformMode: "web" as const,

  async setupVM(options: Record<string, unknown>) {
    return builtinEnvironments.jsdom.setupVM?.(options) ?? {};
  },

  async setup(global: typeof globalThis, options: Record<string, unknown>) {
    // Save Node's native AbortController/AbortSignal BEFORE jsdom replaces them.
    const NativeAbortController = (global as unknown as Record<string, unknown>).AbortController as typeof AbortController | undefined;
    const NativeAbortSignal = (global as unknown as Record<string, unknown>).AbortSignal as typeof AbortSignal | undefined;

    // Run the standard jsdom environment setup (installs dom globals).
    const result = await builtinEnvironments.jsdom.setup(global, options);

    // Restore Node-realm AbortController/AbortSignal so fetch() in hooks
    // produces signals that pass undici's instanceof check.
    if (NativeAbortController) {
      (global as unknown as Record<string, unknown>).AbortController = NativeAbortController;
    }
    if (NativeAbortSignal) {
      (global as unknown as Record<string, unknown>).AbortSignal = NativeAbortSignal;
    }

    return result;
  },
};

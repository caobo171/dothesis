import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  test: {
    // Custom environment wrapping jsdom:
    //   - Avoids happy-dom's non-configurable defaultPrevented getter conflict with
    //     rettime/TypedEvent (used by MSW's interceptor-source).
    //   - Restores Node's native AbortController/AbortSignal after jsdom installs its
    //     own, so MSW's fetch interceptor can create Node-undici Requests with the hook's
    //     AbortSignal without failing `instanceof AbortSignal`.
    environment: "./tests/env/jsdom-native-abort.ts",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["app/**/*.test.{ts,tsx}", "tests/**/*.test.{ts,tsx}"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./"),
    },
  },
});

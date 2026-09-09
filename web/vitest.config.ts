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
  // tsconfig sets "jsx": "react-jsx", and esbuild honours that for .ts/.tsx —
  // but not for plain .jsx, which it transforms with the classic runtime
  // instead, i.e. bare `React.createElement` against a `React` nobody imported.
  // Every test so far happened to render a .tsx component, so the first .jsx
  // page under test (app/login/page.jsx) died on "React is not defined".
  // Next builds .jsx with the automatic runtime; this says the same thing.
  esbuild: {
    jsx: "automatic",
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./"),
    },
  },
});

import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll, vi } from "vitest";
import { setupServer } from "msw/node";
import { defaultHandlers } from "./mocks/handlers";

// @testing-library/dom's waitFor fake-timer branch checks `typeof jest !== 'undefined'`
// to detect fake timers. Vitest doesn't inject `jest` as a global even with
// `globals: true`, so waitFor falls through to the real-setInterval path —
// which is faked — causing waitFor promises to hang forever.
// Aliasing jest → vi lets testing-library detect vitest fake timers correctly
// and use its synchronous polling loop instead.
// See: https://github.com/testing-library/dom-testing-library/issues/987
(globalThis as any).jest = vi;

export const server = setupServer(...defaultHandlers);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

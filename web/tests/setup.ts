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

// @xyflow/react (used by FlowChartWidget) reads node sizes via ResizeObserver
// and DOMMatrix on mount. jsdom omits both, so tests rendering the widget
// would crash on first render. A no-op polyfill is enough — the widget logic
// we test (initial render, edit panel state, Confirm payload) doesn't depend
// on actual measured sizes.
if (typeof (globalThis as any).ResizeObserver === "undefined") {
  (globalThis as any).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
if (typeof (globalThis as any).DOMMatrixReadOnly === "undefined") {
  (globalThis as any).DOMMatrixReadOnly = class {
    m22 = 1;
    constructor(_: unknown) {}
  };
}

// TipTap/ProseMirror measures caret geometry via getClientRects whenever a
// command focuses the editor (e.g. toggleBold → focus → scrollToSelection).
// jsdom omits getClientRects on Text/Range, so those commands throw an
// unhandled "getClientRects is not a function" that Vitest flags as an error
// even when assertions pass. A zero-rect stub is enough — no editor test
// asserts on caret pixel positions.
// ProseMirror's singleRect() calls target.getClientRects() and, when that's
// empty, falls through to target.getBoundingClientRect() — and `target` can be
// a Text node, which lacks BOTH in jsdom. Stub both with zero-rects.
const _zeroRect = () => ({ x: 0, y: 0, top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0, toJSON: () => ({}) });
for (const proto of [
  (globalThis as any).Text?.prototype,
  (globalThis as any).Range?.prototype,
  (globalThis as any).Element?.prototype,
]) {
  if (proto && typeof proto.getClientRects !== "function") {
    proto.getClientRects = () => Object.assign([], { item: () => null });
  }
  if (proto && typeof proto.getBoundingClientRect !== "function") {
    proto.getBoundingClientRect = _zeroRect;
  }
}

// jsdom ships neither IntersectionObserver (the editor's scrollspy) nor
// Element.scrollIntoView (outline click-to-scroll). No-op stubs are enough —
// these tests assert structure/state, not real scroll geometry.
if (typeof (globalThis as any).IntersectionObserver === "undefined") {
  (globalThis as any).IntersectionObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() { return []; }
  };
}
if (typeof (globalThis as any).Element !== "undefined" && !(globalThis as any).Element.prototype.scrollIntoView) {
  (globalThis as any).Element.prototype.scrollIntoView = () => {};
}

export const server = setupServer(...defaultHandlers);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

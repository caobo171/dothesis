import { afterEach, describe, expect, it, vi } from "vitest";

/**
 * The module reads its configuration once at import, the way Next inlines
 * NEXT_PUBLIC_* at build time. So each case sets the environment and imports a
 * fresh copy rather than mutating a live one.
 */
async function load(env: Record<string, string | undefined>) {
  vi.resetModules();
  for (const [key, value] of Object.entries(env)) {
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
  return import("./hosts");
}

const SPLIT = {
  NEXT_PUBLIC_MARKETING_HOST: "dothesis.com",
  NEXT_PUBLIC_APP_HOST: "app.dothesis.com",
  NEXT_PUBLIC_APP_ORIGIN: "https://app.dothesis.com",
  NEXT_PUBLIC_SITE_ORIGIN: "https://dothesis.com",
};

const OFF = {
  NEXT_PUBLIC_MARKETING_HOST: undefined,
  NEXT_PUBLIC_APP_HOST: undefined,
  NEXT_PUBLIC_APP_ORIGIN: undefined,
  NEXT_PUBLIC_SITE_ORIGIN: undefined,
};

afterEach(() => vi.resetModules());

describe("with no hosts configured", () => {
  it("leaves every request alone, which is how localhost:3006 has always worked", async () => {
    const { routeForHost, SPLIT_ENABLED } = await load(OFF);
    expect(SPLIT_ENABLED).toBe(false);
    for (const path of ["/", "/landing", "/blog/vi", "/chat", "/login"]) {
      expect(routeForHost("localhost", path)).toEqual({ action: "next" });
    }
  });
});

describe("marketing host", () => {
  it("serves the landing page at the bare apex", async () => {
    const { routeForHost } = await load(SPLIT);
    expect(routeForHost("dothesis.com", "/")).toEqual({ action: "rewrite", to: "/landing" });
  });

  it("keeps one URL for the landing page", async () => {
    const { routeForHost } = await load(SPLIT);
    expect(routeForHost("dothesis.com", "/landing")).toEqual({
      action: "redirect", to: "/", status: 301,
    });
  });

  it("serves the blog and the crawler files", async () => {
    const { routeForHost } = await load(SPLIT);
    for (const path of [
      "/blog",
      "/blog/vi",
      "/blog/vi/cfa",
      "/sitemap.xml",
      "/robots.txt",
      // The og:image the apex's own pages point at. Redirect it to the app
      // host and every share of dothesis.com loses its card.
      "/opengraph-image",
    ]) {
      expect(routeForHost("dothesis.com", path)).toEqual({ action: "next" });
    }
  });

  it("sends a product path to the app host, path intact", async () => {
    const { routeForHost } = await load(SPLIT);
    expect(routeForHost("dothesis.com", "/chat/abc")).toEqual({
      action: "redirect", to: "https://app.dothesis.com/chat/abc", status: 308, external: true,
    });
    // 308 rather than 302: an old bookmark or a POST must keep its method.
    expect(routeForHost("dothesis.com", "/login").status).toBe(308);
  });

  it("treats www as the same site", async () => {
    const { routeForHost, isMarketingHost } = await load(SPLIT);
    expect(isMarketingHost("www.dothesis.com")).toBe(true);
    expect(routeForHost("www.dothesis.com", "/")).toEqual({ action: "rewrite", to: "/landing" });
  });
});

describe("app host", () => {
  it("sends public content back to its one home", async () => {
    const { routeForHost } = await load(SPLIT);
    expect(routeForHost("app.dothesis.com", "/blog/vi/cfa")).toEqual({
      action: "redirect", to: "https://dothesis.com/blog/vi/cfa", status: 301, external: true,
    });
    expect(routeForHost("app.dothesis.com", "/landing")).toEqual({
      action: "redirect", to: "https://dothesis.com/", status: 301, external: true,
    });
  });

  it("leaves the product alone for the auth gate that runs after it", async () => {
    const { routeForHost } = await load(SPLIT);
    for (const path of ["/", "/chat", "/login", "/papers"]) {
      expect(routeForHost("app.dothesis.com", path)).toEqual({ action: "next" });
    }
  });
});

describe("host parsing", () => {
  it("drops the port and is case-insensitive", async () => {
    const { hostFromHeader, isMarketingHost, isAppHost } = await load(SPLIT);
    expect(hostFromHeader("DoThesis.com:443")).toBe("dothesis.com");
    expect(isMarketingHost(hostFromHeader("dothesis.com:3006"))).toBe(true);
    expect(isAppHost(hostFromHeader("app.dothesis.com"))).toBe(true);
  });

  it("does not mistake a lookalike hostname for ours", async () => {
    const { isMarketingHost, isAppHost } = await load(SPLIT);
    expect(isMarketingHost("notdothesis.com")).toBe(false);
    expect(isMarketingHost("dothesis.com.evil.test")).toBe(false);
    expect(isAppHost("app.dothesis.com.evil.test")).toBe(false);
  });
});

/**
 * The two menus are two menus.
 *
 * Worth a test rather than a glance because the failure is silent in both
 * directions: put an operator table back in the student hook and every signed-in
 * admin carries it through the product; drop the door from the student hook and
 * the console becomes unreachable without typing the URL.
 */
import { http, HttpResponse } from "msw";
import { SWRConfig } from "swr";
import { describe, expect, test } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";

import { LocaleProvider } from "../../lib/i18n/LocaleProvider";
import { useSidebarSections } from "../../components/layout/use-sections";
import { server } from "../../../tests/setup";

import { useAdminSections } from "./use-admin-sections";

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <LocaleProvider initialLocale="en" hasCookie>
      <SWRConfig value={{ dedupingInterval: 0, provider: () => new Map() }}>
        {children}
      </SWRConfig>
    </LocaleProvider>
  );
}

function signedInAs(isAdmin: boolean) {
  server.use(
    http.post("*/auth/me", () =>
      HttpResponse.json({ id: "u1", email: "a@b.c", is_super_admin: isAdmin })),
  );
}

const hrefsOf = (sections: { options: { href: string }[] }[]) =>
  sections.flatMap((s) => s.options.map((o) => o.href));

describe("the student sidebar", () => {
  test("gives an admin one door, not the console's tables", async () => {
    signedInAs(true);
    const { result } = renderHook(() => useSidebarSections(), { wrapper });

    await waitFor(() =>
      expect(hrefsOf(result.current)).toContain("/admin"));

    const hrefs = hrefsOf(result.current);
    // The seven destinations this hook used to splice in.
    for (const gone of ["/admin/users", "/admin/papers", "/admin/jobs",
                        "/admin/orders", "/admin/connectors", "/admin/tools",
                        "/admin/announcements"]) {
      expect(hrefs).not.toContain(gone);
    }
    // The student's own tool history stays — it is not an admin entry.
    expect(hrefs).toContain("/tool-runs");
  });

  test("shows a non-admin no admin section at all", async () => {
    signedInAs(false);
    const { result } = renderHook(() => useSidebarSections(), { wrapper });

    await waitFor(() => expect(hrefsOf(result.current)).toContain("/papers"));
    expect(result.current.find((s) => s.id === "admin")).toBeUndefined();
  });
});

describe("the admin sidebar", () => {
  test("leads with the blog and carries no student destinations", () => {
    const { result } = renderHook(() => useAdminSections(), { wrapper });
    const hrefs = hrefsOf(result.current);

    expect(hrefs).toContain("/admin/blog");
    expect(hrefs).toContain("/admin/blog/categories");
    expect(hrefs).toContain("/admin/users");
    // /admin/tools is the operator's view of every run; /tool-runs is the
    // student's view of their own. Only one of them belongs in this menu.
    expect(hrefs).toContain("/admin/tools");
    expect(hrefs).not.toContain("/tool-runs");
    expect(hrefs).not.toContain("/papers");
  });
});

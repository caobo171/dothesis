import { render, screen, within } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

// notFound()/redirect() abort rendering by throwing in Next. Reproduce that
// here so a route that "returns" after calling them would still fail the test.
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
  redirect: (url: string) => {
    throw new Error(`NEXT_REDIRECT:${url}`);
  },
}));

import ContactRootPage from "../contact/page";
import ContactPage, { generateMetadata as contactMetadata } from "../contact/[locale]/page";
import PrivacyRootPage from "../privacy/page";
import PrivacyPage, { generateMetadata as privacyMetadata } from "../privacy/[locale]/page";
import TermsRootPage from "../terms/page";
import TermsPage, { generateMetadata as termsMetadata } from "../terms/[locale]/page";
import { EMAIL, ENTITY, UPDATED } from "./_lib/site";

const DOCS = [
  { name: "privacy", Page: PrivacyPage, metadata: privacyMetadata, Root: PrivacyRootPage },
  { name: "terms", Page: TermsPage, metadata: termsMetadata, Root: TermsRootPage },
  { name: "contact", Page: ContactPage, metadata: contactMetadata, Root: ContactRootPage },
] as const;

const LOCALES = ["vi", "en"] as const;

async function renderDoc(Page: (p: { params: Promise<{ locale: string }> }) => Promise<React.JSX.Element>, locale: string) {
  render(await Page({ params: Promise.resolve({ locale }) }));
}

describe("legal + contact routes", () => {
  test.each(DOCS.map((d) => [d.name, d.Root] as const))(
    "/%s redirects to the default edition rather than serving a second copy",
    (name, Root) => {
      // Two URLs serving identical text is the duplicate-content problem the
      // canonical tag exists to clean up. `vi` because DEFAULT_LOCALE is vi.
      expect(() => Root()).toThrow(`NEXT_REDIRECT:/${name}/vi`);
    },
  );

  test.each(DOCS.map((d) => [d.name, d.Page] as const))(
    "/%s/<locale> 404s on a locale that does not exist",
    async (_name, Page) => {
      await expect(renderDoc(Page, "fr")).rejects.toThrow("NEXT_NOT_FOUND");
    },
  );

  for (const locale of LOCALES) {
    test(`every mailto on the ${locale} contact page goes to the one inbox`, async () => {
      await renderDoc(ContactPage, locale);
      const mailtos = Array.from(document.querySelectorAll('a[href^="mailto:"]'));
      expect(mailtos.length).toBeGreaterThan(1);
      for (const a of mailtos) {
        // The subject may vary — it is the only routing this inbox gets — but
        // the address never may. A second address is an inbox nobody reads.
        expect(a.getAttribute("href")).toMatch(
          new RegExp(`^mailto:${EMAIL.replace(".", "\\.")}(\\?|$)`),
        );
      }
    });

    test(`the ${locale} policies name the operator and carry an effective date`, async () => {
      for (const Page of [PrivacyPage, TermsPage]) {
        document.body.innerHTML = "";
        await renderDoc(Page, locale);
        expect(document.body.textContent).toContain(ENTITY);
        // The year at least: the two editions format the date differently, and
        // pinning the whole string here would just restate `formattedDate`.
        expect(document.body.textContent).toContain(UPDATED.slice(0, 4));
      }
    });

    test(`the ${locale} policies state where the thesis content goes`, async () => {
      // The one disclosure this product cannot omit: the student's own writing
      // and uploaded analysis output leave for a third-party model. A privacy
      // policy for an AI writing tool that does not say so is the wrong policy.
      document.body.innerHTML = "";
      await renderDoc(PrivacyPage, locale);
      const text = document.body.textContent ?? "";
      expect(text).toMatch(/OpenAI/);
      expect(text).toMatch(/Google/);
      expect(text).toMatch(/SePay/);
      expect(text).toMatch(/CrossRef/);
    });

    test(`the ${locale} terms keep the academic-responsibility clause`, async () => {
      // Deliberately asserted rather than left to review: a tool that drafts a
      // thesis has to tell the student the submission and its rules are theirs.
      document.body.innerHTML = "";
      await renderDoc(TermsPage, locale);
      const text = document.body.textContent ?? "";
      expect(text).toMatch(locale === "vi" ? /trách nhiệm học thuật/i : /academic responsibility/i);
      expect(text).toMatch(locale === "vi" ? /pháp luật Việt Nam/ : /laws of Vietnam/);
    });

    test(`the ${locale} pages link to the other edition`, async () => {
      const other = locale === "vi" ? "en" : "vi";
      document.body.innerHTML = "";
      await renderDoc(PrivacyPage, locale);
      const switcher = document.querySelector<HTMLAnchorElement>("a.blog-langswitch");
      expect(switcher?.getAttribute("href")).toBe(`/privacy/${other}`);
      expect(switcher?.getAttribute("hreflang")).toBe(other);
    });

    test(`the ${locale} footer links the legal set at that locale`, async () => {
      document.body.innerHTML = "";
      await renderDoc(TermsPage, locale);
      const footer = document.querySelector("footer");
      expect(footer).not.toBeNull();
      const hrefs = Array.from(footer!.querySelectorAll("a")).map((a) => a.getAttribute("href"));
      // Locale-suffixed, so a reader of the English terms who clicks Privacy
      // does not get bounced to Vietnamese by the bare-path redirect.
      expect(hrefs).toContain(`/privacy/${locale}`);
      expect(hrefs).toContain(`/terms/${locale}`);
      expect(hrefs).toContain(`/contact/${locale}`);
      // No placeholder survived in the columns we just wired up.
      const legalCol = within(footer!).getByText("Legal").parentElement!;
      expect(
        Array.from(legalCol.querySelectorAll("a")).map((a) => a.getAttribute("href")),
      ).not.toContain("#");
    });
  }

  test("each document declares both editions as alternates, and its own canonical", async () => {
    for (const { name, metadata } of DOCS) {
      for (const locale of LOCALES) {
        const meta = await metadata({ params: Promise.resolve({ locale }) });
        expect(meta.alternates?.canonical).toBe(`/${name}/${locale}`);
        const languages = meta.alternates?.languages as Record<string, string>;
        // Both editions ship in one source file, so the pair can never be
        // half-published — unlike a blog post, where hreflang has to be earned.
        expect(Object.keys(languages)).toEqual(expect.arrayContaining(["vi", "en", "x-default"]));
        expect(languages["x-default"]).toContain(`/${name}/vi`);
      }
    }
  });

  test("the rendered prose contains no unparsed inline markup", async () => {
    // `inline()` is a two-mark parser, not markdown. A stray `**` or a `](`
    // reaching the page means copy used a mark it does not implement.
    for (const { Page } of DOCS) {
      for (const locale of LOCALES) {
        document.body.innerHTML = "";
        await renderDoc(Page, locale);
        const text = document.body.textContent ?? "";
        expect(text).not.toMatch(/\*\*/);
        expect(text).not.toMatch(/\]\(/);
      }
    }
  });

  test("links out of the policies are real routes, not placeholders", async () => {
    await renderDoc(TermsPage, "en");
    const prose = document.querySelector(".blog-prose")!;
    const internal = Array.from(prose.querySelectorAll("a"))
      .map((a) => a.getAttribute("href") ?? "")
      .filter((h) => h.startsWith("/"));
    expect(internal.length).toBeGreaterThan(0);
    for (const href of internal) expect(href).toMatch(/^\/(privacy|terms|contact)\/(vi|en)$/);
  });

  test("the contact page offers a pre-filled subject per reason", async () => {
    await renderDoc(ContactPage, "en");
    const subjects = Array.from(document.querySelectorAll('a[href*="?subject="]')).map((a) =>
      decodeURIComponent((a.getAttribute("href") ?? "").split("subject=")[1]),
    );
    // Billing and privacy are the two that must be sortable on arrival: one is
    // somebody's money, the other has a legal clock attached.
    expect(subjects).toContain("DoThesis — billing");
    expect(subjects).toContain("DoThesis — privacy");
    expect(new Set(subjects).size).toBe(subjects.length);
  });

  test("the contact page is not a form", async () => {
    // There is no endpoint behind this page, by decision. A form appearing here
    // would post into nothing and silently drop the message.
    await renderDoc(ContactPage, "vi");
    expect(document.querySelector("form")).toBeNull();
    expect(screen.getByText(EMAIL)).toBeTruthy();
  });
});

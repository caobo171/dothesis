/**
 * DoThesis marketing landing page.
 *
 * Imported from the Claude Design project "DoThesis Landing Page"
 * (db96bc1b-0ad3-4fbd-a8ee-f837e4f47b44). Section order and copy follow the
 * design; the design-system component classes it depends on live in
 * ./landing.css rather than in app/globals.css, so nothing here re-tunes the
 * in-app surfaces.
 *
 * This route sits outside the (inapp) and (chat) groups, so it gets only the
 * root layout — no sidebar, no auth chrome.
 */
import type { Metadata } from "next";

import "./landing.css";

import { Comparison } from "./_components/Comparison";
import { Faq } from "./_components/Faq";
import { Features } from "./_components/Features";
import { FinalCta } from "./_components/FinalCta";
import { Footer } from "./_components/Footer";
import { Hero, LogoStrip } from "./_components/Hero";
import { Nav } from "./_components/Nav";
import { Tools } from "./_components/Tools";
import { UseCases } from "./_components/UseCases";

export const metadata: Metadata = {
  title: "DoThesis — Draft with conviction",
  // "19 specialized agents" was dropped from the Hero and the stats row as
  // "no longer accurate" (see the comments in FinalCta.tsx and Hero.tsx) but
  // survived here, where it is still user-visible in search results and social
  // previews. A number the codebase itself documents as false is the one claim
  // that cannot be argued about.
  description:
    "From a topic idea to a submitted thesis. One thread, sources it looked up, every citation checked against your reference list — an AI thesis agent across five modules.",
};

export default function LandingPage() {
  return (
    <div className="lp-root">
      <Nav />
      <main>
        <Hero />
        <LogoStrip />
        <Features />
        <Comparison />
        <Tools />
        {/* Testimonials removed: the three quotes were attributed to named
            people with degrees and institutions, and nothing anywhere backed
            them — no CMS, no seed data, no consent record. Invented reviews are
            not a copy problem to soften, so the section is gone until there are
            real ones with releases. */}
        <UseCases />
        <Faq />
        <FinalCta />
      </main>
      <Footer />
    </div>
  );
}

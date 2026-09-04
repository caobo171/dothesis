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
import { Testimonials } from "./_components/Testimonials";
import { Tools } from "./_components/Tools";
import { UseCases } from "./_components/UseCases";

export const metadata: Metadata = {
  title: "DoThesis — Draft with conviction",
  description:
    "From a topic idea to a submitted thesis. One thread, your sources, every citation verified — an AI thesis agent with 19 specialized agents across five modules.",
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
        <Testimonials />
        <UseCases />
        <Faq />
        <FinalCta />
      </main>
      <Footer />
    </div>
  );
}

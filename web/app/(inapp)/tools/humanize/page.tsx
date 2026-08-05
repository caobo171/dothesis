"use client";

import { HumanizeTool } from "../_components/HumanizeTool";

// One route per tool. The panel already renders its own title and blurb, so the
// page is just the mount point — the sidebar entry is what names it.
export default function HumanizePage() {
  return <HumanizeTool />;
}

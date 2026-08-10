"use client";

import { SimilarityDocument } from "../_components/SimilarityDocument";

// One route per tool, same as humanize/citation — the panel renders its own
// copy and the sidebar entry is what names it.
export default function SimilarityPage() {
  return <SimilarityDocument />;
}

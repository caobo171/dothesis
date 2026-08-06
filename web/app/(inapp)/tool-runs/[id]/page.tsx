import { Suspense } from "react";

import RunDetail from "../_components/RunDetail";

/**
 * One tool run, with the paragraph diff.
 *
 * The list can say "80 đoạn đã viết lại"; only this page can show WHICH words
 * moved. That is what a student needs before handing the file to a supervisor,
 * and what an admin needs to answer "what did your tool do to my document".
 */
export default async function RunDetailPage(
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  return (
    <Suspense fallback={<div className="text-ink-500">Loading…</div>}>
      <RunDetail runId={id} />
    </Suspense>
  );
}

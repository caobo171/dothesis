import { Suspense } from "react";

import ToolRuns from "./_components/ToolRuns";

/**
 * The student's own tool history — the counterpart to /admin/tools.
 *
 * Admins could always see every run; the person who paid for one could not see
 * their own except as a footnote under the credit ledger. Now it is a
 * destination in its own right, which is what it needs to be: it is where the
 * stored input and output are downloaded from, where a document is re-run, and
 * where a run in flight reports its progress.
 */
export default function ToolRunsPage() {
  return (
    <Suspense fallback={<div className="text-ink-500">Loading…</div>}>
      <ToolRuns />
    </Suspense>
  );
}

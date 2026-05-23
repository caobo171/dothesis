import { Suspense } from "react";
import Credit from "./_components/Credit";

export default function CreditPage() {
  return (
    <Suspense fallback={<div className="text-ink-500">Loading…</div>}>
      <Credit />
    </Suspense>
  );
}

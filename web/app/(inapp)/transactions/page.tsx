import { Suspense } from "react";
import Transactions from "./_components/Transactions";

export default function TransactionsPage() {
  return (
    <Suspense fallback={<div className="text-ink-500">Loading…</div>}>
      <Transactions />
    </Suspense>
  );
}

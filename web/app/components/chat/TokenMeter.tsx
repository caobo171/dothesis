import { Zap } from "lucide-react";


export function TokenMeter({ credits }: { credits: number }) {
  // Below 5000 credits we surface a warning to prompt the user to top up
  const isLow = credits < 5000;
  return (
    <div
      data-testid="token-meter"
      className={`flex items-center gap-1 text-xs ${
        isLow ? "text-red-600 font-semibold" : "text-gray-500"
      }`}
    >
      <Zap className="w-3 h-3" />
      <span>{credits.toLocaleString()}</span>
    </div>
  );
}

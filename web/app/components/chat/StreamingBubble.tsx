import { AssistantFrame, humanizeTechnicalCopy } from "./MessageBubble";

// Shares AssistantFrame with the final MessageBubble so the in-flight and
// settled turns have identical silhouettes (no layout jump on stream end).
export function StreamingBubble({ text, moduleTag }: { text: string; moduleTag?: string | null }) {
  // Hide the raw `{{cite: …}}` grounding markers while streaming — they render
  // as pills only once the message settles (MessageBubble). Showing the raw
  // marker mid-stream looks like a glitch. Keep the label so the sentence reads.
  const clean = humanizeTechnicalCopy(
    text.replace(/\{\{cite:\s*([^{}|]+?)(?:\|[^{}]*)?\}\}/g, "$1"),
  ).trimEnd();
  return (
    <AssistantFrame moduleTag={moduleTag}>
      <div className="whitespace-pre-wrap">
        {clean}
        {/* Blinking cursor signals that the stream is still in-flight */}
        <span
          data-testid="streaming-cursor"
          className="inline-block w-0.5 h-4 bg-primary-600 animate-pulse ml-0.5"
        />
      </div>
    </AssistantFrame>
  );
}

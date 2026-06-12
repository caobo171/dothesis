import { AssistantFrame } from "./MessageBubble";

// Shares AssistantFrame with the final MessageBubble so the in-flight and
// settled turns have identical silhouettes (no layout jump on stream end).
export function StreamingBubble({ text, moduleTag }: { text: string; moduleTag?: string | null }) {
  return (
    <AssistantFrame moduleTag={moduleTag}>
      <div className="whitespace-pre-wrap">
        {text}
        {/* Blinking cursor signals that the stream is still in-flight */}
        <span
          data-testid="streaming-cursor"
          className="inline-block w-0.5 h-4 bg-primary-600 animate-pulse ml-0.5"
        />
      </div>
    </AssistantFrame>
  );
}

import { AssistantFrame } from "./MessageBubble";

/**
 * Three-dot "agent is thinking" indicator.
 *
 * Rendered between when the user's message lands and when the first SSE token
 * arrives — that gap is the LLM latency window (extraction → routing → next
 * question generation), which previously felt like a stalled UI. Shares
 * AssistantFrame with StreamingBubble so the transition from thinking →
 * streaming is seamless.
 */
export function ThinkingBubble({ moduleTag }: { moduleTag?: string | null }) {
  return (
    <AssistantFrame moduleTag={moduleTag} data-testid="thinking-bubble">
      <div className="flex items-center gap-1.5 py-0.5" aria-label="Agent is thinking">
        <span
          className="h-2 w-2 rounded-full bg-ink-400 animate-bounce"
          style={{ animationDelay: "0ms" }}
        />
        <span
          className="h-2 w-2 rounded-full bg-ink-400 animate-bounce"
          style={{ animationDelay: "150ms" }}
        />
        <span
          className="h-2 w-2 rounded-full bg-ink-400 animate-bounce"
          style={{ animationDelay: "300ms" }}
        />
      </div>
    </AssistantFrame>
  );
}

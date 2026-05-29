/**
 * Three-dot "agent is thinking" indicator.
 *
 * Rendered between when the user's message lands and when the first SSE token
 * arrives — that gap is the LLM latency window (extraction → routing → next
 * question generation), which previously felt like a stalled UI. Matches the
 * visual language of StreamingBubble (left-aligned, gray, optional module
 * tag) so the transition from thinking → streaming is seamless.
 */
export function ThinkingBubble({ moduleTag }: { moduleTag?: string | null }) {
  return (
    <div className="flex justify-start mb-3" data-role="assistant" data-testid="thinking-bubble">
      <div className="max-w-[70%] rounded-2xl rounded-bl-sm bg-gray-50 text-gray-900 px-4 py-3 border border-gray-200">
        {moduleTag && (
          <div className="text-[10px] uppercase tracking-wider text-gray-400 mb-1">{moduleTag}</div>
        )}
        <div className="flex items-center gap-1.5" aria-label="Agent is thinking">
          <span
            className="h-2 w-2 rounded-full bg-gray-400 animate-bounce"
            style={{ animationDelay: "0ms" }}
          />
          <span
            className="h-2 w-2 rounded-full bg-gray-400 animate-bounce"
            style={{ animationDelay: "150ms" }}
          />
          <span
            className="h-2 w-2 rounded-full bg-gray-400 animate-bounce"
            style={{ animationDelay: "300ms" }}
          />
        </div>
      </div>
    </div>
  );
}

/**
 * Inline error indicator — shown when the backend emits an SSE
 * `{type: error, message}` event mid-stream (LLM timeout, graph crash,
 * provider 5xx, ...).
 *
 * Until this existed the user had no way to tell their request failed —
 * the optimistic message stayed up and the stream just ended quietly,
 * which looked identical to a slow but successful turn. Worst-case fail
 * mode in the M2 msgpack crash where every turn vanished into the void.
 */
export function ErrorBubble({ message }: { message: string }) {
  return (
    <div
      className="flex justify-start mb-3"
      data-role="assistant"
      data-testid="error-bubble"
    >
      <div className="max-w-[80%] rounded-2xl rounded-bl-sm bg-red-50 border border-red-200 px-4 py-3 text-sm">
        <div className="flex items-start gap-2">
          <span aria-hidden="true" className="text-red-500 text-base leading-none mt-0.5">
            ⚠
          </span>
          <div className="flex-1">
            <div className="font-semibold text-red-900 mb-1">
              Something went wrong
            </div>
            {/* Backend-supplied message — usually contains the exception
                type + a short reason. Render as plain text so it can't
                escape into the surrounding chat with surprise markdown. */}
            <div className="text-red-800 break-words font-mono text-xs">
              {message}
            </div>
            <div className="text-red-700 mt-2 text-xs">
              Try again, or refine your message and resend.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

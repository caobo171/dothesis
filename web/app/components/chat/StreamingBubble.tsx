export function StreamingBubble({ text, moduleTag }: { text: string; moduleTag?: string | null }) {
  return (
    <div className="flex justify-start mb-3" data-role="assistant">
      <div className="max-w-[70%] rounded-2xl rounded-bl-sm bg-gray-50 text-gray-900 px-4 py-2 border border-gray-200">
        {/* Show module tag when available */}
        {moduleTag && (
          <div className="text-[10px] uppercase tracking-wider text-gray-400 mb-1">{moduleTag}</div>
        )}
        <div className="whitespace-pre-wrap">
          {text}
          {/* Blinking cursor signals that the stream is still in-flight */}
          <span
            data-testid="streaming-cursor"
            className="inline-block w-0.5 h-4 bg-purple-600 animate-pulse ml-0.5"
          />
        </div>
      </div>
    </div>
  );
}

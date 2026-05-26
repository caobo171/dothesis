import { ReactNode } from "react";

export type MessageBubbleProps = {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  moduleTag?: string | null;
  children?: ReactNode;
};


export function MessageBubble({ role, content, moduleTag, children }: MessageBubbleProps) {
  const isUser = role === "user";
  const isSystem = role === "system";

  return (
    <div
      data-role={role}
      className={`flex ${isUser ? "justify-end" : "justify-start"} mb-3`}
    >
      <div
        className={
          isUser
            ? "max-w-[70%] rounded-2xl rounded-br-sm bg-purple-600 text-white px-4 py-2"
            : isSystem
            ? "max-w-[70%] rounded-md bg-gray-100 text-gray-600 px-3 py-1 text-sm italic"
            : "max-w-[70%] rounded-2xl rounded-bl-sm bg-gray-50 text-gray-900 px-4 py-2 border border-gray-200"
        }
      >
        {/* Show module tag for assistant messages only */}
        {moduleTag && !isUser && !isSystem && (
          <div className="text-[10px] uppercase tracking-wider text-gray-400 mb-1">{moduleTag}</div>
        )}
        <div className="whitespace-pre-wrap">{content}</div>
        {children}
      </div>
    </div>
  );
}

import ReactMarkdown from "react-markdown";
import { type Message } from "@/features/websocket/protocol";
import { PrimitiveRenderer } from "@/components/server-driven/PrimitiveRenderer";

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "items-start gap-2"}`}>
      {!isUser && (
        <div className="w-6 h-6 rounded-full bg-plum-voltage/20 flex items-center justify-center flex-shrink-0 mt-1">
          <span className="text-[10px] text-plum-voltage font-semibold">Z</span>
        </div>
      )}

      <div className={`max-w-[80%] ${isUser ? "items-end" : "items-start"} flex flex-col`}>
        {message.text && (
          <div
            className={`px-4 py-2.5 rounded-[20px] text-sm leading-relaxed ${
              isUser
                ? "bg-plum-voltage text-white rounded-br-[6px]"
                : "border border-white/10 text-white rounded-bl-[6px]"
            }`}
          >
            <ReactMarkdown
              components={{
                p: ({ children }) => <p className="m-0">{children}</p>,
                code: ({ children }) => (
                  <code className="bg-white/10 rounded px-1 py-0.5 text-xs font-mono">
                    {children}
                  </code>
                ),
                pre: ({ children }) => (
                  <pre className="bg-white/5 rounded-xl p-3 my-2 overflow-x-auto text-xs font-mono">
                    {children}
                  </pre>
                ),
              }}
            >
              {message.text}
            </ReactMarkdown>
          </div>
        )}

        {message.components.map((c, i) => (
          <PrimitiveRenderer key={i} node={c} />
        ))}

        <p className="mt-1 px-1 text-[10px] text-smoke">
          {formatTime(message.created_at)}
        </p>
      </div>
    </div>
  );
}

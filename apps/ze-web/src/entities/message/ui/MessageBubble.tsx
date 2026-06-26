import type { MessageSchema as Message } from "@ze/client";
import { Info } from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { ConnectedPrimitiveTree } from "@/entities/primitive-tree";
import { MessageTracePanel } from "@/widgets/message-trace";

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
  const [traceOpen, setTraceOpen] = useState(false);

  return (
    <div className={`flex ${isUser ? "justify-end" : "items-start gap-2"}`}>
      {!isUser && (
        <div className="w-6 h-6 rounded-full bg-plum-voltage/20 flex items-center justify-center flex-shrink-0 mt-1">
          <span className="text-[10px] text-plum-voltage font-semibold">Z</span>
        </div>
      )}

      <div className={`max-w-[80%] ${isUser ? "items-end" : "items-start"} flex flex-col`}>
        {message.text && (
          <div className="group relative">
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

            {!isUser && message.id !== "__streaming__" && (
              <button
                onClick={() => setTraceOpen(!traceOpen)}
                title="Why did Ze say this?"
                className="absolute -top-1 -right-1 opacity-0 group-hover:opacity-100 transition-opacity w-5 h-5 rounded-full bg-white/[0.08] hover:bg-white/[0.15] flex items-center justify-center"
              >
                <Info className="w-3 h-3 text-smoke" />
              </button>
            )}
          </div>
        )}

        {message.components.length > 0 && (
          <ConnectedPrimitiveTree components={message.components} />
        )}

        {traceOpen && !isUser && message.id !== "__streaming__" && (
          <MessageTracePanel messageId={message.id} />
        )}

        <p className="mt-1 px-1 text-[10px] text-smoke">{formatTime(message.created_at)}</p>
      </div>
    </div>
  );
}

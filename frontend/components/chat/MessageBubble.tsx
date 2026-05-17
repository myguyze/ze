"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import type { ZeMessage } from "@/types"

interface Props {
  message: ZeMessage
  isStreaming: boolean
}

export default function MessageBubble({ message, isStreaming }: Props) {
  const [showMeta, setShowMeta] = useState(false)

  if (message.role === "system") {
    return (
      <div className="text-center text-muted text-xs py-1">
        {message.content}
      </div>
    )
  }

  const isUser = message.role === "user"

  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div className="max-w-[75%]">
        <div
          className={cn(
            "rounded-2xl px-4 py-3 text-sm leading-relaxed break-words",
            isUser
              ? "bg-user-bubble text-slate-900 rounded-br-sm"
              : "bg-agent-bubble text-slate-100 rounded-bl-sm"
          )}
        >
          {message.content}
          {isStreaming && (
            <span className="inline-block ml-0.5 animate-pulse opacity-75">▋</span>
          )}
        </div>

        {message.meta && (
          <div className={cn("mt-1", isUser ? "text-right" : "text-left")}>
            <button
              onClick={() => setShowMeta((v) => !v)}
              className="text-muted text-xs hover:text-slate-400 transition-colors select-none"
              aria-label="Toggle routing info"
            >
              ℹ
            </button>
            {showMeta && (
              <div className="text-xs text-muted mt-1 space-y-0.5 leading-relaxed">
                <div>Agent: <span className="text-slate-400">{message.meta.agent || "—"}</span></div>
                <div>Method: <span className="text-slate-400">{message.meta.routingMethod}</span></div>
                {message.meta.confidence !== null && (
                  <div>
                    Confidence:{" "}
                    <span className="text-slate-400">
                      {(message.meta.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

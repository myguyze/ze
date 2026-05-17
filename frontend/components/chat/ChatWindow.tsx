"use client"

import { useEffect, useRef } from "react"
import type { UiState, ZeMessage } from "@/types"
import MessageBubble from "./MessageBubble"
import MessageInput from "./MessageInput"

interface Props {
  messages: ZeMessage[]
  uiState: UiState
  onSend: (text: string) => void
}

export default function ChatWindow({ messages, uiState, onSend }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  const disabled = uiState !== "idle"
  const streamingId = messages.find((m) => m.isStreaming)?.id

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-3">
        {messages.length === 0 && (
          <p className="text-center text-muted text-sm mt-20 select-none">
            Ask Ze anything.
          </p>
        )}
        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            isStreaming={msg.id === streamingId}
          />
        ))}
        <div ref={bottomRef} />
      </div>
      <MessageInput onSend={onSend} disabled={disabled} />
    </div>
  )
}

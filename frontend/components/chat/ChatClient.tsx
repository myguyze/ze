"use client"

import { useEffect } from "react"
import { env } from "@/lib/env"
import { useZeSocket } from "@/hooks/useZeSocket"
import ChatWindow from "./ChatWindow"
import ConfirmationModal from "@/components/overlays/ConfirmationModal"

interface Props {
  sessionId: string
}

export default function ChatClient({ sessionId }: Props) {
  const { messages, uiState, pendingConfirmation, sendMessage, sendConfirm } =
    useZeSocket(sessionId)

  // Persist session ID in a cookie so page.tsx can read it on subsequent SSR visits
  useEffect(() => {
    if (!document.cookie.includes("ze_session_id=")) {
      document.cookie = `ze_session_id=${sessionId}; path=/; max-age=2592000`
    }
  }, [sessionId])

  return (
    <div className="flex flex-col h-screen">
      {uiState === "reconnecting" && (
        <div className="bg-slate-700/60 text-slate-400 text-xs text-center py-1.5 shrink-0">
          Reconnecting…
        </div>
      )}
      {uiState === "disconnected" && (
        <div className="bg-red-900/60 text-red-300 text-xs text-center py-1.5 shrink-0">
          Connection lost. Reload to reconnect.
        </div>
      )}

      <div className="flex-1 overflow-hidden">
        <ChatWindow messages={messages} uiState={uiState} onSend={sendMessage} />
      </div>

      {pendingConfirmation && (
        <ConfirmationModal
          confirmation={pendingConfirmation}
          onConfirm={() => sendConfirm("yes")}
          onReject={() => sendConfirm("no")}
          onEdit={(edited) => sendConfirm("edit", edited)}
          timeoutSeconds={env.NEXT_PUBLIC_CONFIRM_TIMEOUT_SECONDS}
        />
      )}
    </div>
  )
}

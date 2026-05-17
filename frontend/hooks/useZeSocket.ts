"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { env } from "@/lib/env"
import type { ConfirmationRequest, UiState, WsServerMessage, ZeMessage } from "@/types"

export interface UseZeSocketReturn {
  sendMessage: (content: string) => void
  sendConfirm: (decision: "yes" | "no" | "edit", editContent?: string) => void
  messages: ZeMessage[]
  uiState: UiState
  pendingConfirmation: ConfirmationRequest | null
}

const BACKOFF_BASE = 1000
const BACKOFF_FACTOR = 2
const BACKOFF_MAX = 30000
const BACKOFF_JITTER = 0.2

function makeId(): string {
  return Math.random().toString(36).slice(2) + Date.now().toString(36)
}

// Returns Infinity when raw delay would hit the max — signals "stop retrying".
function nextBackoffMs(attempt: number): number {
  const raw = Math.min(BACKOFF_BASE * Math.pow(BACKOFF_FACTOR, attempt), BACKOFF_MAX)
  if (raw >= BACKOFF_MAX) return Infinity
  const jitter = raw * BACKOFF_JITTER * (Math.random() * 2 - 1)
  return raw + jitter
}

export function useZeSocket(sessionId: string): UseZeSocketReturn {
  const [messages, setMessages] = useState<ZeMessage[]>([])
  const [uiState, setUiState] = useState<UiState>("idle")
  const [pendingConfirmation, setPendingConfirmation] = useState<ConfirmationRequest | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const streamingIdRef = useRef<string | null>(null)
  const attemptRef = useRef(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)

  const connect = useCallback(() => {
    if (!mountedRef.current) return

    const ws = new WebSocket(`${env.NEXT_PUBLIC_ZE_WS_URL}/ws/${sessionId}`)
    wsRef.current = ws

    ws.onopen = () => {
      if (!mountedRef.current) return
      attemptRef.current = 0
      setUiState("idle")
    }

    ws.onmessage = (event: MessageEvent) => {
      if (!mountedRef.current) return
      let msg: WsServerMessage
      try {
        msg = JSON.parse(event.data as string) as WsServerMessage
      } catch {
        return
      }

      if (msg.type === "token") {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === streamingIdRef.current
              ? { ...m, content: m.content + msg.content }
              : m
          )
        )
      } else if (msg.type === "done") {
        if (streamingIdRef.current) {
          const finishedId = streamingIdRef.current
          streamingIdRef.current = null
          setMessages((prev) =>
            prev.map((m) =>
              m.id === finishedId
                ? {
                    ...m,
                    isStreaming: false,
                    meta: {
                      agent: msg.agent,
                      routingMethod: msg.routing_method as "embedding" | "haiku",
                      confidence: msg.confidence,
                    },
                  }
                : m
            )
          )
        }
        setUiState("idle")
      } else if (msg.type === "confirmation_request") {
        setPendingConfirmation({
          type: "confirmation_request",
          draft: msg.draft,
          agent: msg.agent,
          action: msg.action,
        })
        setUiState("awaiting_confirmation")
      } else if (msg.type === "confirmation_expired") {
        setPendingConfirmation(null)
        setUiState("idle")
        setMessages((prev) => [
          ...prev,
          {
            id: makeId(),
            role: "system",
            content: "Confirmation expired — action was cancelled.",
            isStreaming: false,
          },
        ])
      } else if (msg.type === "error") {
        const streamId = streamingIdRef.current
        streamingIdRef.current = null
        const errEntry: ZeMessage = {
          id: makeId(),
          role: "system",
          content: `Error: ${msg.message}`,
          isStreaming: false,
        }
        setMessages((prev) => {
          const base = streamId
            ? prev.map((m) => (m.id === streamId ? { ...m, isStreaming: false } : m))
            : prev
          return [...base, errEntry]
        })
        setUiState("idle")
      }
    }

    ws.onclose = () => {
      if (!mountedRef.current) return
      wsRef.current = null

      // Close out any in-flight streaming message so it doesn't stay "streaming" forever
      if (streamingIdRef.current) {
        const streamId = streamingIdRef.current
        streamingIdRef.current = null
        setMessages((prev) =>
          prev.map((m) => (m.id === streamId ? { ...m, isStreaming: false } : m))
        )
      }

      const delay = nextBackoffMs(attemptRef.current)
      if (!isFinite(delay)) {
        setUiState("disconnected")
        return
      }

      setUiState("reconnecting")
      attemptRef.current += 1
      reconnectTimerRef.current = setTimeout(connect, delay)
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [sessionId])

  useEffect(() => {
    mountedRef.current = true
    connect()
    return () => {
      mountedRef.current = false
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
      wsRef.current?.close()
    }
  }, [connect])

  const sendMessage = useCallback((content: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return

    const agentMsgId = makeId()
    streamingIdRef.current = agentMsgId

    setMessages((prev) => [
      ...prev,
      { id: makeId(), role: "user", content, isStreaming: false },
      { id: agentMsgId, role: "agent", content: "", isStreaming: true },
    ])
    setUiState("streaming")
    wsRef.current.send(JSON.stringify({ type: "user", content }))
  }, [])

  const sendConfirm = useCallback(
    (decision: "yes" | "no" | "edit", editContent?: string) => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return

      if (decision !== "no") {
        const agentMsgId = makeId()
        streamingIdRef.current = agentMsgId
        setMessages((prev) => [
          ...prev,
          { id: agentMsgId, role: "agent", content: "", isStreaming: true },
        ])
      }

      setPendingConfirmation(null)
      setUiState("streaming")
      wsRef.current.send(
        JSON.stringify({ type: "confirm", decision, edit_content: editContent ?? null })
      )
    },
    []
  )

  return { sendMessage, sendConfirm, messages, uiState, pendingConfirmation }
}

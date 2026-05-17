"use client"

import { useRef } from "react"
import { cn } from "@/lib/utils"

interface Props {
  onSend: (text: string) => void
  disabled: boolean
}

export default function MessageInput({ onSend, disabled }: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const submit = () => {
    const text = textareaRef.current?.value.trim()
    if (!text || disabled) return
    onSend(text)
    if (textareaRef.current) textareaRef.current.value = ""
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className="border-t border-slate-800 p-4">
      <div className={cn("flex gap-3 items-end", disabled && "opacity-60")}>
        <textarea
          ref={textareaRef}
          disabled={disabled}
          onKeyDown={handleKeyDown}
          placeholder="Message Ze…"
          rows={1}
          className="flex-1 bg-slate-800 text-slate-100 rounded-xl px-4 py-3 text-sm resize-none focus:outline-none focus:ring-1 focus:ring-indigo-500 placeholder:text-muted disabled:cursor-not-allowed"
        />
        <button
          onClick={submit}
          disabled={disabled}
          className="px-4 py-3 bg-indigo-600 text-white text-sm rounded-xl hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shrink-0"
        >
          Send
        </button>
      </div>
    </div>
  )
}

"use client"

import { useState } from "react"

interface Props {
  initialContent: string
  onSave: (edited: string) => void
  onCancel: () => void
}

export default function DraftReview({ initialContent, onSave, onCancel }: Props) {
  const [content, setContent] = useState(initialContent)

  return (
    <div>
      <textarea
        className="w-full bg-slate-900 text-slate-200 text-sm rounded-lg p-3 font-mono resize-y min-h-32 focus:outline-none focus:ring-1 focus:ring-indigo-500 mb-4"
        value={content}
        onChange={(e) => setContent(e.target.value)}
        rows={8}
        autoFocus
      />
      <div className="flex gap-3 justify-end">
        <button
          onClick={onCancel}
          className="px-4 py-2 text-sm rounded-lg bg-slate-700 text-slate-200 hover:bg-slate-600 transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={() => onSave(content)}
          className="px-4 py-2 text-sm rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 transition-colors"
        >
          Send
        </button>
      </div>
    </div>
  )
}

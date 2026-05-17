"use client"

import { useEffect, useState } from "react"
import type { ConfirmationRequest } from "@/types"
import DraftReview from "./DraftReview"

interface Props {
  confirmation: ConfirmationRequest
  onConfirm: () => void
  onReject: () => void
  onEdit: (editedContent: string) => void
  timeoutSeconds: number
}

export default function ConfirmationModal({
  confirmation,
  onConfirm,
  onReject,
  onEdit,
  timeoutSeconds,
}: Props) {
  const [secondsLeft, setSecondsLeft] = useState(timeoutSeconds)
  const [expired, setExpired] = useState(false)
  const [showEdit, setShowEdit] = useState(false)

  // Reset and start countdown whenever the confirmation payload changes
  useEffect(() => {
    setSecondsLeft(timeoutSeconds)
    setExpired(false)
    setShowEdit(false)

    const interval = setInterval(() => {
      setSecondsLeft((s) => {
        if (s <= 1) {
          clearInterval(interval)
          setExpired(true)
          return 0
        }
        return s - 1
      })
    }, 1000)

    return () => clearInterval(interval)
  }, [confirmation, timeoutSeconds])

  const mm = Math.floor(secondsLeft / 60).toString().padStart(2, "0")
  const ss = (secondsLeft % 60).toString().padStart(2, "0")

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
      <div className="bg-slate-800 rounded-xl p-6 max-w-lg w-full mx-4 shadow-2xl border border-slate-700">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-semibold text-slate-100">Confirm action</h2>
          <span className={`text-sm font-mono tabular-nums ${expired ? "text-red-400" : "text-muted"}`}>
            {expired ? "Expired" : `${mm}:${ss}`}
          </span>
        </div>

        {(confirmation.agent || confirmation.action) && (
          <div className="mb-3 text-xs text-muted">
            {confirmation.agent && <span className="text-slate-400">{confirmation.agent}</span>}
            {confirmation.agent && confirmation.action && <span> · </span>}
            {confirmation.action && <span>{confirmation.action}</span>}
          </div>
        )}

        {showEdit ? (
          <DraftReview
            initialContent={confirmation.draft}
            onSave={(edited) => {
              setShowEdit(false)
              onEdit(edited)
            }}
            onCancel={() => setShowEdit(false)}
          />
        ) : (
          <>
            <pre className="bg-slate-900 rounded-lg p-4 text-sm text-slate-200 whitespace-pre-wrap overflow-auto max-h-64 mb-6 font-mono">
              {confirmation.draft}
            </pre>

            {expired ? (
              <p className="text-red-400 text-sm text-center py-2">
                Confirmation expired. This action was cancelled.
              </p>
            ) : (
              <div className="flex gap-3 justify-end">
                <button
                  onClick={onReject}
                  className="px-4 py-2 text-sm rounded-lg bg-slate-700 text-slate-200 hover:bg-slate-600 transition-colors"
                >
                  No
                </button>
                <button
                  onClick={() => setShowEdit(true)}
                  className="px-4 py-2 text-sm rounded-lg bg-slate-700 text-slate-200 hover:bg-slate-600 transition-colors"
                >
                  Edit
                </button>
                <button
                  onClick={onConfirm}
                  className="px-4 py-2 text-sm rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 transition-colors"
                >
                  Yes
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

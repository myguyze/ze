import { cookies } from "next/headers"
import ChatClient from "@/components/chat/ChatClient"

export default function Page() {
  const cookieStore = cookies()
  // Use the persisted session ID if available; otherwise generate a fresh one.
  // The client will set the cookie on first load so subsequent SSR visits are stable.
  const sessionId = cookieStore.get("ze_session_id")?.value ?? crypto.randomUUID()
  return <ChatClient sessionId={sessionId} />
}

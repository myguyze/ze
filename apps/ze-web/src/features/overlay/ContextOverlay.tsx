import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X } from "lucide-react";
import { useOverlay } from "./useOverlay";
import { useChatSession } from "@/features/chat/hooks/useChatSession";
import { ChatMessageList } from "@/features/chat/components/ChatMessageList";
import { ChatInput } from "@/features/chat/components/ChatInput";

export function ContextOverlay() {
  const { open, close, screen, entityId } = useOverlay();
  const [input, setInput] = useState("");
  const { messages, showTyping, typingText, streamingText, isThinking, sendMessage } = useChatSession({
    ephemeral: true,
    active: open,
    context: { screen, ...(entityId && { goal_id: entityId }) },
  });

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") close();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [close]);

  function handleSend() {
    if (sendMessage(input)) {
      setInput("");
    }
  }

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            className="fixed inset-0 z-40 bg-black/40"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={close}
          />

          <motion.div
            className="fixed inset-x-0 bottom-0 z-50 flex flex-col bg-black border-t border-white/10 rounded-t-pill max-h-[50vh]"
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={{ type: "spring", damping: 30, stiffness: 300 }}
          >
            <div className="flex items-center justify-between px-4 py-3 border-b border-white/10 flex-shrink-0">
              <div className="w-8 h-1 rounded-full bg-white/20 mx-auto absolute left-1/2 -translate-x-1/2 top-3" />
              <span className="text-xs text-smoke tracking-widest uppercase">Ze · {screen}</span>
              <button onClick={close} className="text-smoke hover:text-white transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>

            <ChatMessageList
              messages={messages}
              showTyping={showTyping}
              typingText={typingText}
              streamingText={streamingText}
              className="flex-1 overflow-y-auto px-4 py-3 space-y-3 min-h-0"
            />

            <ChatInput
              value={input}
              onChange={setInput}
              onSend={handleSend}
              disabled={isThinking}
              placeholder={`Ask Ze about ${screen}…`}
            />
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

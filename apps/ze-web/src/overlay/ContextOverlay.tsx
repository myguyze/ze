import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, ArrowUp } from "lucide-react";
import { useOverlay } from "./useOverlay";
import { send } from "@/ws/useWebSocket";
import { useWebSocket } from "@/ws/useWebSocket";
import { type InboundFrame, type Message } from "@/ws/protocol";
import { MessageBubble } from "@/screens/chat/MessageBubble";
import { TypingIndicator } from "@/screens/chat/TypingIndicator";

export function ContextOverlay() {
  const { open, close, screen, entityId, thinking: isThinking, setThinking } = useOverlay();
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [showTyping, setShowTyping] = useState(false);
  const typingTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const bottomRef = useRef<HTMLDivElement>(null);

  useWebSocket((frame: InboundFrame) => {
    if (!open) return;
    switch (frame.type) {
      case "message":
        setMessages((prev) => [...prev, frame.message]);
        setThinking(false);
        setShowTyping(false);
        break;
      case "typing":
        setShowTyping(true);
        clearTimeout(typingTimer.current);
        typingTimer.current = setTimeout(() => setShowTyping(false), 3000);
        break;
      case "edit":
      case "confirm_request":
      case "confirm_cancel":
      case "error":
      case "refresh":
      case "pong":
        break;
      default: {
        const _exhaustive: never = frame;
        void _exhaustive;
      }
    }
  });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, showTyping]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") close();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [close]);

  function handleSend() {
    const text = input.trim();
    if (!text || isThinking) return;
    setInput("");
    setThinking(true);
    send({
      type: "message",
      text,
      context: { screen, ...(entityId && { goal_id: entityId }) },
    });
  }

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* backdrop */}
          <motion.div
            className="fixed inset-0 z-40 bg-black/40"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={close}
          />

          {/* panel */}
          <motion.div
            className="fixed inset-x-0 bottom-0 z-50 flex flex-col bg-black border-t border-white/10 rounded-t-[24px] max-h-[50vh]"
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={{ type: "spring", damping: 30, stiffness: 300 }}
          >
            {/* handle + header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-white/10 flex-shrink-0">
              <div className="w-8 h-1 rounded-full bg-white/20 mx-auto absolute left-1/2 -translate-x-1/2 top-3" />
              <span className="text-xs text-[#9a9a9a] tracking-widest uppercase">Ze · {screen}</span>
              <button onClick={close} className="text-[#9a9a9a] hover:text-white transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* messages */}
            <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 min-h-0">
              {messages.map((msg) => (
                <MessageBubble key={msg.id} message={msg} />
              ))}
              {showTyping && <TypingIndicator />}
              <div ref={bottomRef} />
            </div>

            {/* input */}
            <div className="flex items-center gap-2 px-4 py-3 border-t border-white/10 flex-shrink-0">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSend()}
                disabled={isThinking}
                placeholder={`Ask Ze about ${screen}…`}
                className="flex-1 bg-transparent text-sm text-white placeholder:text-[#9a9a9a] focus:outline-none disabled:opacity-40"
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || isThinking}
                className="w-8 h-8 rounded-full bg-[#8052ff] text-white flex items-center justify-center disabled:opacity-40 transition-opacity"
              >
                <ArrowUp className="w-4 h-4" />
              </button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

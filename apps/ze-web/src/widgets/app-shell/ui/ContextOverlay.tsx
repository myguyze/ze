import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ExternalLink, GripHorizontal, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ChatInput, ChatMessageList } from "@/entities/message";
import { useSession } from "@/entities/session";
import { useOverlayStore } from "@/features/open-context-overlay";
import { useChatWorkspace } from "@/widgets/chat-workspace";

const DESKTOP_W = 368;
const DESKTOP_H = 520;
const EDGE_GAP = 24;

function useIsMobile() {
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 768);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 767px)");
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);
  return isMobile;
}

// ─── Shared chat hook for the overlay ────────────────────────────────────────

function useOverlayChat(open: boolean, screen: string, entityId?: string, overlayThreadId?: string) {
  const [input, setInput] = useState("");
  const { messages, showTyping, typingText, streamingText, isThinking, sendMessage } =
    useChatWorkspace({
      active: open,
      context: { screen, ...(entityId && { goal_id: entityId }) },
      threadId: overlayThreadId,
    });

  useEffect(() => {
    if (!open) setInput("");
  }, [open]);

  function handleSend() {
    if (sendMessage(input)) setInput("");
  }

  return { input, setInput, messages, showTyping, typingText, streamingText, isThinking, handleSend };
}

// ─── Open-in-chat action ──────────────────────────────────────────────────────

function useOpenInChat(overlayThreadId: string, close: () => void) {
  const selectSession = useSession((s) => s.selectSession);
  const navigate = useNavigate();

  return () => {
    selectSession(overlayThreadId);
    navigate("/");
    close();
  };
}

// ─── Mobile Bottom Sheet ──────────────────────────────────────────────────────

interface SheetProps {
  open: boolean;
  close: () => void;
  screen: string;
  entityId?: string;
  prefillMessage?: string;
  clearPrefill: () => void;
  overlayThreadId: string;
}

function MobileChatSheet({
  open, close, screen, entityId, prefillMessage, clearPrefill, overlayThreadId,
}: SheetProps) {
  const chat = useOverlayChat(open, screen, entityId, overlayThreadId);
  const openInChat = useOpenInChat(overlayThreadId, close);

  useEffect(() => {
    if (open && prefillMessage) {
      chat.setInput(prefillMessage);
      clearPrefill();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [close]);

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            className="fixed inset-0 z-40 bg-black/50 backdrop-blur-[2px]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={close}
          />

          <motion.div
            className="fixed inset-x-0 bottom-0 z-50 flex flex-col bg-black border-t border-white/10 rounded-t-[20px] max-h-[65vh]"
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={{ type: "spring", damping: 28, stiffness: 280 }}
          >
            {/* Drag handle pill */}
            <div className="flex justify-center pt-3 pb-1 flex-shrink-0">
              <div className="w-10 h-1 rounded-full bg-white/20" />
            </div>

            {/* Header */}
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/10 flex-shrink-0">
              <span className="text-xs text-smoke tracking-widest uppercase font-medium">
                Ze · {screen}
              </span>
              <div className="flex items-center gap-0.5">
                <button
                  onClick={openInChat}
                  aria-label="Open in chat"
                  title="Open in chat"
                  className="w-8 h-8 flex items-center justify-center rounded-lg text-smoke hover:text-plum-voltage hover:bg-plum-voltage/10 transition-colors"
                >
                  <ExternalLink className="w-4 h-4" />
                </button>
                <button
                  onClick={close}
                  aria-label="Close"
                  className="w-8 h-8 flex items-center justify-center rounded-lg text-smoke hover:text-white hover:bg-white/[0.06] transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            <ChatMessageList
              messages={chat.messages}
              showTyping={chat.showTyping}
              typingText={chat.typingText}
              streamingText={chat.streamingText}
              className="flex-1 overflow-y-auto px-4 py-3 space-y-3 min-h-0"
            />

            <ChatInput
              value={chat.input}
              onChange={chat.setInput}
              onSend={chat.handleSend}
              disabled={chat.isThinking}
              placeholder={`Ask Ze about ${screen}…`}
            />
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

// ─── Desktop Floating Widget ──────────────────────────────────────────────────

interface WidgetProps extends SheetProps {
  toggle: () => void;
}

function DesktopChatWidget({
  open, toggle, close, screen, entityId, prefillMessage, clearPrefill, overlayThreadId,
}: WidgetProps) {
  const chat = useOverlayChat(open, screen, entityId, overlayThreadId);
  const openInChat = useOpenInChat(overlayThreadId, close);
  const location = useLocation();

  const [dragConstraints, setDragConstraints] = useState({
    top: 0, left: 0, right: 0, bottom: 0,
  });

  useEffect(() => {
    const update = () =>
      setDragConstraints({
        top: -(window.innerHeight - DESKTOP_H - EDGE_GAP * 2),
        left: -(window.innerWidth - DESKTOP_W - EDGE_GAP * 2),
        right: 0,
        bottom: 0,
      });
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  useEffect(() => {
    if (open && prefillMessage) {
      chat.setInput(prefillMessage);
      clearPrefill();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && open) close(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [close, open]);

  const isOnChatPage = location.pathname === "/";

  return (
    <motion.div
      drag
      dragMomentum={false}
      dragElastic={0}
      dragConstraints={dragConstraints}
      className="fixed bottom-6 right-6 z-50"
    >
      <AnimatePresence mode="wait">
        {!open && !isOnChatPage && (
          // ── FAB (collapsed) — hidden on the chat page ────────────────────
          <motion.button
            key="fab"
            onClick={toggle}
            className="w-14 h-14 rounded-full bg-plum-voltage text-white flex items-center justify-center shadow-lg shadow-plum-voltage/30 hover:bg-plum-voltage/90 transition-colors cursor-pointer"
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0, opacity: 0 }}
            transition={{ type: "spring", damping: 22, stiffness: 300 }}
            whileHover={{ scale: 1.06 }}
            whileTap={{ scale: 0.93 }}
            title="Open Ze (⌘K)"
          >
            <span className="text-sm font-semibold tracking-tight">Ze</span>
          </motion.button>
        )}

        {open && (
          // ── Expanded panel ───────────────────────────────────────────────
          <motion.div
            key="panel"
            className="flex flex-col bg-black border border-white/10 rounded-2xl overflow-hidden shadow-2xl shadow-black/60 ring-1 ring-plum-voltage/10"
            style={{ width: DESKTOP_W, height: DESKTOP_H }}
            initial={{ scale: 0.88, opacity: 0, y: 16 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.88, opacity: 0, y: 16 }}
            transition={{ type: "spring", damping: 26, stiffness: 320 }}
          >
            {/* Header — drag handle */}
            <div className="flex items-center justify-between px-3 py-2.5 border-b border-white/10 flex-shrink-0 cursor-grab active:cursor-grabbing">
              <div className="flex items-center gap-2 min-w-0">
                <GripHorizontal className="w-3.5 h-3.5 text-white/25 flex-shrink-0" />
                <span className="text-xs text-smoke tracking-widest uppercase font-medium truncate">
                  Ze · {screen}
                </span>
              </div>
              <div className="flex items-center gap-0.5">
                <button
                  onPointerDown={(e) => e.stopPropagation()}
                  onClick={openInChat}
                  aria-label="Open in chat"
                  title="Open in chat"
                  className="w-7 h-7 flex items-center justify-center rounded-lg text-smoke hover:text-plum-voltage hover:bg-plum-voltage/10 transition-colors"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                </button>
                <button
                  onPointerDown={(e) => e.stopPropagation()}
                  onClick={close}
                  aria-label="Collapse"
                  title="Collapse"
                  className="w-7 h-7 flex items-center justify-center rounded-lg text-smoke hover:text-white hover:bg-white/[0.06] transition-colors"
                >
                  <ChevronDown className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Message list — stop propagation so scroll doesn't fight drag */}
            <div
              className="flex-1 min-h-0 overflow-hidden"
              onPointerDown={(e) => e.stopPropagation()}
            >
              <ChatMessageList
                messages={chat.messages}
                showTyping={chat.showTyping}
                typingText={chat.typingText}
                streamingText={chat.streamingText}
                className="h-full overflow-y-auto px-3 py-3 space-y-3"
              />
            </div>

            {/* Input — stop propagation so typing doesn't fight drag */}
            <div onPointerDown={(e) => e.stopPropagation()}>
              <ChatInput
                value={chat.input}
                onChange={chat.setInput}
                onSend={chat.handleSend}
                disabled={chat.isThinking}
                placeholder={`Ask Ze about ${screen}…`}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ─── Root ─────────────────────────────────────────────────────────────────────

export function ContextOverlay() {
  const {
    open, close, toggle, screen, entityId, prefillMessage, clearPrefill, overlayThreadId,
  } = useOverlayStore();
  const isMobile = useIsMobile();

  if (isMobile) {
    return (
      <MobileChatSheet
        open={open}
        close={close}
        screen={screen}
        entityId={entityId}
        prefillMessage={prefillMessage}
        clearPrefill={clearPrefill}
        overlayThreadId={overlayThreadId}
      />
    );
  }

  return (
    <DesktopChatWidget
      open={open}
      toggle={toggle}
      close={close}
      screen={screen}
      entityId={entityId}
      prefillMessage={prefillMessage}
      clearPrefill={clearPrefill}
      overlayThreadId={overlayThreadId}
    />
  );
}

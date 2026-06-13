import { motion } from "framer-motion";
import { MessageCircle } from "lucide-react";
import { useWsStore } from "@/ws/useWebSocket";
import { useOverlay } from "./useOverlay";
import { cn } from "@/lib/cn";

export function FloatingButton({ screen, entityId }: { screen: string; entityId?: string }) {
  const { openFor } = useOverlay();
  const isThinking = useWsStore((s) => s.isThinking);

  return (
    <motion.button
      onClick={() => openFor(screen, entityId)}
      className={cn(
        "fixed bottom-6 right-6 z-40 w-12 h-12 rounded-full bg-[#8052ff] text-white flex items-center justify-center shadow-lg",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-[#8052ff] focus-visible:ring-offset-2 focus-visible:ring-offset-black",
      )}
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.95 }}
    >
      {isThinking && (
        <motion.span
          className="absolute inset-0 rounded-full border-2 border-[#8052ff]"
          animate={{ scale: [1, 1.4], opacity: [0.6, 0] }}
          transition={{ duration: 1.5, repeat: Infinity }}
        />
      )}
      <MessageCircle className="w-5 h-5" />
    </motion.button>
  );
}

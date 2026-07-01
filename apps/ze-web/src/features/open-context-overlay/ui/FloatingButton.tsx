import { motion } from "framer-motion";
import { MessageCircle } from "lucide-react";
import { useEffect } from "react";
import { useOverlayStore } from "@/features/open-context-overlay";
import { useWsStore } from "@/shared/api";
import { cn } from "@/shared/lib";

export function FloatingButton({ screen, entityId }: { screen: string; entityId?: string }) {
  const { openFor, setScreen } = useOverlayStore();
  const isThinking = useWsStore((s) => s.isThinking);

  // Register this page's context so the desktop FAB opens with the right screen label.
  useEffect(() => {
    setScreen(screen, entityId);
    return () => setScreen("chat");
  }, [screen, entityId, setScreen]);

  // On desktop the widget provides its own FAB — hide this one to avoid duplicates.
  return (
    <motion.button
      onClick={() => openFor(screen, entityId)}
      className={cn(
        "fixed bottom-20 right-6 z-40 w-12 h-12 rounded-full bg-plum-voltage text-white flex items-center justify-center shadow-lg md:hidden",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-plum-voltage focus-visible:ring-offset-2 focus-visible:ring-offset-black",
      )}
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.95 }}
    >
      {isThinking && (
        <motion.span
          className="absolute inset-0 rounded-full border-2 border-plum-voltage"
          animate={{ scale: [1, 1.4], opacity: [0.6, 0] }}
          transition={{ duration: 1.5, repeat: Infinity }}
        />
      )}
      <MessageCircle className="w-5 h-5" />
    </motion.button>
  );
}

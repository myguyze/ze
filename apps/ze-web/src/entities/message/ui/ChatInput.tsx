import { motion } from "framer-motion";
import { ArrowUp } from "lucide-react";
import { useRef, type KeyboardEvent } from "react";
import { useWsStore } from "@/shared/api";
import { cn } from "@/shared/lib/cn";

interface ChatInputProps {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  disabled?: boolean;
  placeholder?: string;
}

export function ChatInput({ value, onChange, onSend, disabled, placeholder }: ChatInputProps) {
  const isThinking = useWsStore((s) => s.isThinking);
  const isDisabled = disabled ?? isThinking;
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function handleKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  }

  function handleInput() {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }

  return (
    <div className="flex items-end gap-3 px-4 py-3 border-t border-white/10">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          handleInput();
        }}
        onKeyDown={handleKey}
        disabled={isDisabled}
        placeholder={placeholder ?? (isThinking ? "Ze is thinking…" : "Message Ze")}
        rows={1}
        className={cn(
          "flex-1 resize-none bg-transparent text-sm text-white placeholder:text-smoke focus:outline-none disabled:opacity-50",
          "max-h-40 overflow-y-auto leading-relaxed",
        )}
        style={{ height: "auto" }}
      />
      <motion.button
        onClick={onSend}
        disabled={!value.trim() || isDisabled}
        className="w-8 h-8 rounded-full bg-plum-voltage text-white flex items-center justify-center disabled:opacity-40 flex-shrink-0 transition-opacity"
        whileTap={{ scale: 0.9 }}
      >
        <ArrowUp className="w-4 h-4" />
      </motion.button>
    </div>
  );
}

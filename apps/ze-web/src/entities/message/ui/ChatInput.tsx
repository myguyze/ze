import { motion } from "framer-motion";
import { ArrowUp } from "lucide-react";
import { useRef, type KeyboardEvent } from "react";
import { cn } from "@/shared/lib/cn";

interface ChatInputProps {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  disabled?: boolean;
  placeholder?: string;
}

export function ChatInput({ value, onChange, onSend, disabled, placeholder }: ChatInputProps) {
  const isDisabled = disabled ?? false;
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
    <div className="flex-shrink-0 pt-4">
      <div
        className={cn(
          "flex min-h-9 items-end gap-2 rounded-pill border border-white/15 bg-white/[0.03] px-4 py-2 transition-colors",
          "focus-within:border-plum-voltage/50",
          isDisabled && "opacity-50",
        )}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            handleInput();
          }}
          onKeyDown={handleKey}
          disabled={isDisabled}
          placeholder={placeholder ?? (isDisabled ? "Ze is thinking…" : "Message Ze")}
          rows={1}
          className={cn(
            "min-h-[1.5rem] max-h-40 flex-1 resize-none overflow-y-auto bg-transparent text-sm leading-relaxed text-white placeholder:text-smoke focus:outline-none disabled:cursor-not-allowed",
          )}
          style={{ height: "auto" }}
        />
        <motion.button
          type="button"
          onClick={onSend}
          disabled={!value.trim() || isDisabled}
          aria-label="Send message"
          className="flex size-8 flex-shrink-0 items-center justify-center rounded-full bg-plum-voltage text-white transition-opacity disabled:opacity-40"
          whileTap={{ scale: 0.9 }}
        >
          <ArrowUp className="size-4" />
        </motion.button>
      </div>
    </div>
  );
}

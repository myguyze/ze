import { useEffect } from "react";
import { motion, stagger, useAnimate } from "framer-motion";
import { cn } from "@/lib/cn";

export function TextGenerateEffect({
  words,
  className,
}: {
  words: string;
  className?: string;
}) {
  const [scope, animate] = useAnimate();
  const wordsArray = words.split(" ");

  useEffect(() => {
    void animate(
      "span",
      { opacity: 1 },
      { duration: 1, delay: stagger(0.15) },
    );
  }, [animate]);

  return (
    <motion.div ref={scope} className={cn("", className)}>
      {wordsArray.map((word, i) => (
        <motion.span key={i} className="opacity-0 mr-1 text-white">
          {word}
        </motion.span>
      ))}
    </motion.div>
  );
}

export function TypingDots({ className }: { className?: string }) {
  return (
    <div className={cn("flex gap-1 items-center", className)}>
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="w-1.5 h-1.5 rounded-full bg-[#8052ff]"
          animate={{ opacity: [0.2, 1, 0.2] }}
          transition={{ duration: 1.2, delay: i * 0.2, repeat: Infinity }}
        />
      ))}
    </div>
  );
}

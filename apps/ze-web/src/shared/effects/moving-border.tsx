import { motion, useAnimationFrame, useMotionTemplate, useMotionValue, useTransform } from "framer-motion";
import { useRef } from "react";
import { cn } from "@/shared/lib/cn";

export function MovingBorder({
  children,
  className,
  containerClassName,
  duration = 2000,
  rx = "24px",
  ry = "24px",
}: {
  children: React.ReactNode;
  className?: string;
  containerClassName?: string;
  duration?: number;
  rx?: string;
  ry?: string;
}) {
  const pathRef = useRef<SVGRectElement>(null);
  const progress = useMotionValue<number>(0);

  useAnimationFrame((time) => {
    const length = pathRef.current?.getTotalLength();
    if (length) {
      const pxPerMillisecond = length / duration;
      progress.set((time * pxPerMillisecond) % length);
    }
  });

  const x = useTransform(progress, (val) => pathRef.current?.getPointAtLength(val).x ?? 0);
  const y = useTransform(progress, (val) => pathRef.current?.getPointAtLength(val).y ?? 0);

  const transform = useMotionTemplate`translateX(${x}px) translateY(${y}px) translateX(-50%) translateY(-50%)`;

  return (
    <div className={cn("relative p-[1px] overflow-hidden rounded-[24px]", containerClassName)}>
      <svg
        xmlns="http://www.w3.org/2000/svg"
        preserveAspectRatio="none"
        className="absolute inset-0 h-full w-full"
        width="100%"
        height="100%"
      >
        <rect
          fill="none"
          width="100%"
          height="100%"
          rx={rx}
          ry={ry}
          ref={pathRef}
        />
      </svg>
      <motion.div
        style={{ transform }}
        className="absolute h-10 w-10 opacity-[0.8]"
      >
        <div className="h-full w-full rounded-full bg-[#8052ff] blur-md" />
      </motion.div>
      <div className={cn("relative z-10", className)}>{children}</div>
    </div>
  );
}

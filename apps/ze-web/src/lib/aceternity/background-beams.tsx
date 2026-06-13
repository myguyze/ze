"use client";
import { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/cn";

export function BackgroundBeams({ className }: { className?: string }) {
  const beams = [
    { x1: "20%", y1: "0%", x2: "50%", y2: "100%", delay: 0 },
    { x1: "50%", y1: "0%", x2: "30%", y2: "100%", delay: 0.5 },
    { x1: "80%", y1: "0%", x2: "60%", y2: "100%", delay: 1 },
    { x1: "10%", y1: "0%", x2: "70%", y2: "100%", delay: 1.5 },
    { x1: "90%", y1: "0%", x2: "20%", y2: "100%", delay: 2 },
  ];

  return (
    <div className={cn("absolute inset-0 overflow-hidden pointer-events-none", className)}>
      <svg
        className="absolute inset-0 w-full h-full"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <radialGradient id="beam-fade" cx="50%" cy="0%" r="80%">
            <stop offset="0%" stopColor="#8052ff" stopOpacity="0.15" />
            <stop offset="100%" stopColor="#8052ff" stopOpacity="0" />
          </radialGradient>
        </defs>
        <rect width="100%" height="100%" fill="url(#beam-fade)" />
        {beams.map((beam, i) => (
          <motion.line
            key={i}
            x1={beam.x1}
            y1={beam.y1}
            x2={beam.x2}
            y2={beam.y2}
            stroke="#8052ff"
            strokeWidth="1"
            strokeOpacity="0"
            initial={{ strokeOpacity: 0 }}
            animate={{ strokeOpacity: [0, 0.3, 0] }}
            transition={{
              duration: 4,
              delay: beam.delay,
              repeat: Infinity,
              ease: "easeInOut",
            }}
          />
        ))}
      </svg>
    </div>
  );
}

// Simplified canvas-based version for richer effect
export function BackgroundBeamsCanvas({ className }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;

    function resize() {
      if (!canvas) return;
      canvas.width = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
    }
    resize();
    window.addEventListener("resize", resize);

    let t = 0;
    function draw() {
      if (!canvas || !ctx) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const beams = 6;
      for (let i = 0; i < beams; i++) {
        const phase = (t + i * 1.2) % (Math.PI * 2);
        const opacity = Math.max(0, Math.sin(phase) * 0.25);

        const x1 = (i / beams) * canvas.width + Math.sin(t * 0.3 + i) * 40;
        const x2 = ((i + 0.5) / beams) * canvas.width + Math.cos(t * 0.2 + i) * 60;

        const grad = ctx.createLinearGradient(x1, 0, x2, canvas.height);
        grad.addColorStop(0, `rgba(128, 82, 255, ${opacity})`);
        grad.addColorStop(0.5, `rgba(128, 82, 255, ${opacity * 0.5})`);
        grad.addColorStop(1, "rgba(128, 82, 255, 0)");

        ctx.beginPath();
        ctx.moveTo(x1, 0);
        ctx.lineTo(x2, canvas.height);
        ctx.strokeStyle = grad as unknown as string;
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }

      t += 0.008;
      animId = requestAnimationFrame(draw);
    }
    draw();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className={cn("absolute inset-0 w-full h-full pointer-events-none", className)}
    />
  );
}

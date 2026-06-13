import { useEffect, useRef } from "react";
import { cn } from "@/lib/cn";

interface Star {
  x: number;
  y: number;
  r: number;
  opacity: number;
  speed: number;
  phase: number;
}

export function GlowingStars({ className, count = 120 }: { className?: string; count?: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;
    let stars: Star[] = [];

    function resize() {
      if (!canvas) return;
      canvas.width = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
      stars = Array.from({ length: count }, () => ({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        r: Math.random() * 1.5 + 0.3,
        opacity: Math.random(),
        speed: Math.random() * 0.008 + 0.002,
        phase: Math.random() * Math.PI * 2,
      }));
    }
    resize();
    window.addEventListener("resize", resize);

    let t = 0;
    function draw() {
      if (!canvas || !ctx) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      for (const star of stars) {
        const opacity = (Math.sin(t * star.speed + star.phase) + 1) / 2;
        // Occasional plum-voltage tint
        const isViolet = star.phase > Math.PI * 1.5;
        ctx.beginPath();
        ctx.arc(star.x, star.y, star.r, 0, Math.PI * 2);
        ctx.fillStyle = isViolet
          ? `rgba(128, 82, 255, ${opacity * 0.8})`
          : `rgba(255, 255, 255, ${opacity * 0.6})`;
        ctx.fill();
      }

      t += 1;
      animId = requestAnimationFrame(draw);
    }
    draw();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener("resize", resize);
    };
  }, [count]);

  return (
    <canvas
      ref={canvasRef}
      className={cn("absolute inset-0 w-full h-full pointer-events-none", className)}
    />
  );
}

import type { ReactNode } from "react";

interface DashboardHeroProps {
  value: ReactNode;
  caption: ReactNode;
}

export function DashboardHero({ value, caption }: DashboardHeroProps) {
  return (
    <div>
      <p className="text-[64px] font-extralight leading-none tracking-tight text-white">
        {value}
      </p>
      <p className="mt-2 text-[10px] text-smoke tracking-widest uppercase">{caption}</p>
    </div>
  );
}

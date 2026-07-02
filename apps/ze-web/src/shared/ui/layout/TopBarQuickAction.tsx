import { ArrowUpRight } from "lucide-react";
import type { ReactNode } from "react";
import { Link, type LinkProps } from "react-router-dom";
import { cn } from "@/shared/lib/cn";

type TopBarQuickActionLinkProps = LinkProps & {
  children: ReactNode;
  showArrow?: boolean;
  className?: string;
};

export function TopBarQuickActionLink({
  children,
  showArrow = true,
  className,
  ...props
}: TopBarQuickActionLinkProps) {
  return (
    <Link
      {...props}
      className={cn(
        "inline-flex items-center gap-1.5 h-9 px-3 rounded-pill text-xs font-medium text-smoke hover:text-white hover:bg-white/5 transition-colors",
        className,
      )}
    >
      {children}
      {showArrow && <ArrowUpRight className="w-3.5 h-3.5 opacity-70" />}
    </Link>
  );
}

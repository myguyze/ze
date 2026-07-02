import { ArrowUpRight } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link, type LinkProps } from "react-router-dom";
import { cn } from "@/shared/lib/cn";

const quickActionClassName =
  "inline-flex items-center gap-1.5 h-9 px-3 rounded-pill text-xs font-medium text-smoke hover:text-white hover:bg-white/5 transition-colors";

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
    <Link {...props} className={cn(quickActionClassName, className)}>
      {children}
      {showArrow && <ArrowUpRight className="w-3.5 h-3.5 opacity-70" />}
    </Link>
  );
}

type TopBarQuickActionButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode;
  className?: string;
};

export function TopBarQuickActionButton({
  children,
  className,
  ...props
}: TopBarQuickActionButtonProps) {
  return (
    <button type="button" {...props} className={cn(quickActionClassName, className)}>
      {children}
    </button>
  );
}

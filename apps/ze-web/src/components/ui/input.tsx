import * as React from "react";
import { cn } from "@/lib/cn";

const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-10 w-full rounded-[24px] border border-white/15 bg-transparent px-4 py-2 text-sm text-white placeholder:text-[#9a9a9a] focus:outline-none focus:border-[#8052ff] disabled:cursor-not-allowed disabled:opacity-40 transition-colors",
          className,
        )}
        ref={ref}
        {...props}
      />
    );
  },
);
Input.displayName = "Input";

export { Input };

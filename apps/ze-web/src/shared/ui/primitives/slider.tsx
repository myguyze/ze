import * as SliderPrimitive from "@radix-ui/react-slider";
import * as React from "react";
import { cn } from "@/shared/lib/cn";

const Slider = React.forwardRef<
  React.ElementRef<typeof SliderPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof SliderPrimitive.Root> & {
    trackClassName?: string;
    thumbClassName?: string;
    thumbAriaLabel?: string;
    thumbAriaValueText?: string;
    thumbChildren?: React.ReactNode;
  }
>(
  (
    { className, trackClassName, thumbClassName, thumbAriaLabel, thumbAriaValueText, thumbChildren, children, ...props },
    ref,
  ) => (
    <SliderPrimitive.Root
      ref={ref}
      className={cn("relative flex w-full touch-none select-none items-center", className)}
      {...props}
    >
      <SliderPrimitive.Track
        className={cn(
          "relative h-1.5 w-full grow overflow-visible rounded-full bg-white/10",
          trackClassName,
        )}
      >
        {children}
        <SliderPrimitive.Range className="absolute h-full rounded-full bg-transparent" />
      </SliderPrimitive.Track>
      <SliderPrimitive.Thumb
        aria-label={thumbAriaLabel}
        aria-valuetext={thumbAriaValueText}
        className={cn(
          "block h-4 w-4 shrink-0 rounded-full bg-plum-voltage shadow transition-[box-shadow,transform] duration-150",
          "focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-plum-voltage/25",
          "active:scale-[1.15] active:shadow-[0_0_0_6px_rgba(128,82,255,0.25)]",
          "hover:scale-[1.1]",
          thumbClassName,
        )}
      >
        {thumbChildren}
      </SliderPrimitive.Thumb>
    </SliderPrimitive.Root>
  ),
);
Slider.displayName = SliderPrimitive.Root.displayName;

export { Slider };

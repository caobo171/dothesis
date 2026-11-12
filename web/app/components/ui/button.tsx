import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/app/lib/utils";

// Chatwoot's button (components-next/button/Button.vue), as crosssocial ports
// it, drawn with the Radix tokens: 8px radius, a 1px outline rather than a
// border so solid and outlined buttons are the same size, fixed heights, and a
// 2% press scale. The shadcn variant names stay so call sites do not change:
//   default     → primary solid   (one per view, the main action)
//   outline     → slate solid     (white, outlined: secondary actions)
//   secondary   → slate faded
//   ghost       → toolbar / icon buttons
//   destructive → red solid       (destructive actions only)
//   link        → primary link
const buttonVariants = cva(
  "inline-flex min-w-0 items-center justify-center gap-2 whitespace-nowrap rounded-btn outline outline-1 text-button transition-all duration-100 ease-out focus-visible:shadow-[var(--ring-focus)] active:enabled:scale-[0.98] disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "bg-primary-600 text-white outline-transparent hover:bg-primary-700",
        destructive: "bg-destructive-600 text-white outline-transparent hover:bg-destructive-700",
        outline: "bg-white text-ink-900 outline-ink-200 hover:bg-ink-100",
        secondary: "bg-ink-100 text-ink-900 outline-transparent hover:bg-ink-200",
        ghost: "text-ink-900 outline-transparent hover:bg-ink-100",
        link: "h-auto px-0 text-primary-700 outline-transparent underline-offset-2 hover:underline",
      },
      size: {
        default: "h-10 px-4",
        xs: "h-6 px-2 text-button-small",
        sm: "h-8 px-3",
        lg: "h-12 px-5 text-base",
        icon: "h-10 w-10 px-0",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };

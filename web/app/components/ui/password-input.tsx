"use client";

import * as React from "react";
import { Eye, EyeOff } from "lucide-react";

import { cn } from "@/app/lib/utils";
import { Input } from "./input";

// Password field with a show/hide eye toggle sitting inside the field, matching
// the pattern the category leaders (Jenni AI) use. Lives as its own component
// rather than a flag on <Input> so the reveal state stays local and every auth
// screen (login, signup, reset-password) can adopt the same control.
//
// `type` is owned by this component, so it is deliberately omitted from the
// props it accepts — everything else passes straight through to <Input>.
const PasswordInput = React.forwardRef<
  HTMLInputElement,
  Omit<React.ComponentProps<"input">, "type">
>(({ className, ...props }, ref) => {
  const [visible, setVisible] = React.useState(false);
  const Icon = visible ? EyeOff : Eye;

  return (
    <div className="relative">
      <Input
        type={visible ? "text" : "password"}
        // Room for the toggle so long values never run under the icon.
        className={cn("pr-10", className)}
        ref={ref}
        {...props}
      />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        // The label is the action, not the state — screen readers announce what
        // pressing it will do.
        aria-label={visible ? "Hide password" : "Show password"}
        className="absolute inset-y-0 right-0 flex items-center px-3 text-muted-foreground transition-colors hover:text-ink-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded-r-lg"
      >
        <Icon className="h-4 w-4" aria-hidden="true" />
      </button>
    </div>
  );
});
PasswordInput.displayName = "PasswordInput";

export { PasswordInput };

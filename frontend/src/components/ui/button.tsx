import React from "react";
import { cn } from "../../lib/utils";

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "ghost";
};

export function Button({ className, variant = "default", ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors",
        variant === "default" && "bg-slate-900 text-white hover:bg-slate-800",
        variant === "ghost" && "bg-transparent text-slate-700 hover:bg-sky-100 hover:text-sky-700",
        className
      )}
      {...props}
    />
  );
}


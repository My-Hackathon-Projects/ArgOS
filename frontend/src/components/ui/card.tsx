import * as React from "react";
import { cn } from "@/lib/utils";

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "card-shadow rounded-[1.125rem] border border-black/[0.04] bg-surface",
        className,
      )}
      {...props}
    />
  );
}

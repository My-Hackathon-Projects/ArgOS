import * as React from "react";
import { cn } from "@/lib/utils";

/** Shared page gutter: consistent max width + responsive padding under the nav. */
export function Container({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("mx-auto w-full max-w-6xl px-4 pt-10 sm:px-6 sm:pt-12 lg:px-8", className)}
      {...props}
    />
  );
}

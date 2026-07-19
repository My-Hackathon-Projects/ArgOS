"use client";

import * as React from "react";
import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

/** Centered modal over a blurred backdrop. Controlled: render with open/onClose.
 *  Enters with a scale+fade (transform-origin stays centered — it is a modal,
 *  not an anchored popover); closes instantly so dismissal feels immediate. */
export function Dialog({
  open,
  onClose,
  title,
  children,
  className,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  const [shown, setShown] = useState(false);

  useEffect(() => {
    if (!open) return;
    const raf = requestAnimationFrame(() => setShown(true));
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      cancelAnimationFrame(raf);
      setShown(false);
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className={cn(
        "fixed inset-0 z-50 flex items-center justify-center p-4 transition-opacity duration-200",
        shown ? "opacity-100" : "opacity-0",
      )}
      style={{ background: "rgba(0,0,0,0.32)", backdropFilter: "blur(4px)" }}
      onClick={onClose}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
        className={cn(
          "card-shadow w-full max-w-md rounded-[1.125rem] border border-black/[0.04] bg-surface p-6",
          "transition-[transform,opacity] duration-200 ease-[cubic-bezier(0.23,1,0.32,1)]",
          shown ? "scale-100 opacity-100" : "scale-[0.96] opacity-0",
          className,
        )}
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <h2 className="text-lg font-semibold tracking-tight text-foreground">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-full p-1 text-subtle transition-colors hover:bg-muted hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

/** Shared input styling for dialog forms. */
export const fieldClass =
  "h-10 w-full rounded-lg border border-border-strong bg-surface px-3 text-sm text-foreground placeholder:text-subtle focus:outline-none focus:ring-2 focus:ring-ring";

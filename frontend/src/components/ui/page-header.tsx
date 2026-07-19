import * as React from "react";
import { Aura, type AuraMotif } from "@/components/ui/aura";

/** Centered page opener with optional ambient motion behind it. */
export function PageHeader({
  eyebrow,
  title,
  subtitle,
  actions,
  accent,
  aura,
  auraColors,
}: {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  accent?: string;
  aura?: AuraMotif;
  auraColors?: string[];
}) {
  const color = accent ?? "var(--primary)";

  return (
    <div className="relative">
      {aura && (
        <div className="absolute -inset-x-10 -top-12 bottom-[-2rem]">
          <Aura motif={aura} colors={auraColors ?? [color]} />
        </div>
      )}
      <div className="relative mx-auto flex max-w-2xl flex-col items-center text-center">
        {eyebrow && (
          <div
            className="mb-3 inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em]"
            style={{
              color,
              background: `color-mix(in srgb, ${color} 9%, transparent)`,
            }}
          >
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{ background: color }}
              aria-hidden
            />
            {eyebrow}
          </div>
        )}
        <h1 className="font-display text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">
          {title}
        </h1>
        {subtitle && (
          <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-muted-foreground">
            {subtitle}
          </p>
        )}
        {actions && (
          <div className="mt-6 flex flex-wrap items-center justify-center gap-2">{actions}</div>
        )}
      </div>
    </div>
  );
}

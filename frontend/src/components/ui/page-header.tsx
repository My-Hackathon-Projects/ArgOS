import * as React from "react";

/** Centered, large-type page opener in the style of a product hero. */
export function PageHeader({
  eyebrow,
  title,
  subtitle,
  actions,
}: {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center text-center">
      {eyebrow && (
        <div className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-primary">
          {eyebrow}
        </div>
      )}
      <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
        {title}
      </h1>
      {subtitle && (
        <p className="mt-3 max-w-xl text-[15px] leading-relaxed text-muted-foreground">
          {subtitle}
        </p>
      )}
      {actions && <div className="mt-5 flex flex-wrap items-center justify-center gap-2">{actions}</div>}
    </div>
  );
}

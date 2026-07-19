import Link from "next/link";
import { BrainCircuit } from "lucide-react";

const PRODUCT_LINKS = [
  { href: "/sourcing", label: "Sourcing" },
  { href: "/inbound", label: "Inbound" },
  { href: "/founders", label: "Founders" },
  { href: "/opportunities", label: "Decisions" },
  { href: "/settings", label: "Thesis" },
];

const TEAM_LINKS = [
  { href: "/#about", label: "About us" },
  { href: "https://www.linkedin.com/in/icon1c/", label: "Rishabh", external: true },
  {
    href: "https://www.linkedin.com/in/alexandre-boving-04422a1b6/",
    label: "Alexandre",
    external: true,
  },
  { href: "https://www.linkedin.com/in/florian-sprick/", label: "Florian", external: true },
];

function LinkColumn({
  title,
  links,
}: {
  title: string;
  links: { href: string; label: string; external?: boolean }[];
}) {
  return (
    <div>
      <div className="mb-3 text-xs font-semibold uppercase tracking-wider text-subtle">
        {title}
      </div>
      <ul className="space-y-2">
        {links.map(({ href, label, external }) => (
          <li key={href}>
            {external ? (
              <a
                href={href}
                target="_blank"
                rel="noreferrer"
                className="text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                {label}
              </a>
            ) : (
              <Link
                href={href}
                className="text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                {label}
              </Link>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Footer() {
  return (
    <footer className="border-t border-black/[0.06] bg-surface/70">
      <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="flex flex-col justify-between gap-10 md:flex-row">
          <div className="max-w-sm">
            <div className="flex items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-foreground text-primary-foreground">
                <BrainCircuit className="h-4 w-4" />
              </span>
              <span className="font-display text-base font-semibold tracking-tight">ArgOS</span>
            </div>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
              An operating system for venture sourcing. Signals in, evidence-backed decisions
              out.
            </p>
          </div>
          <div className="flex gap-14">
            <LinkColumn title="Product" links={PRODUCT_LINKS} />
            <LinkColumn title="Team" links={TEAM_LINKS} />
          </div>
        </div>
        <p className="mt-10 border-t border-border pt-6 text-xs text-subtle">
          © ArgOS. All rights reserved.
        </p>
      </div>
    </footer>
  );
}

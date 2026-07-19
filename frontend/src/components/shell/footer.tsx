import Link from "next/link";
import { BrainCircuit } from "lucide-react";

const LINKS = [
  { href: "/#about", label: "About us" },
  { href: "/sourcing", label: "Sourcing" },
  { href: "/inbound", label: "Inbound" },
  { href: "/founders", label: "Founders" },
  { href: "/opportunities", label: "Opportunities" },
];

export function Footer() {
  return (
    <footer className="border-t border-black/[0.06] bg-surface">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
        <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-md bg-foreground text-primary-foreground">
              <BrainCircuit className="h-3.5 w-3.5" />
            </span>
            <span className="text-sm font-semibold tracking-tight">ArgOS</span>
          </div>
          <nav aria-label="Footer" className="flex flex-wrap items-center gap-x-5 gap-y-2">
            {LINKS.map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                className="text-xs text-muted-foreground transition-colors hover:text-foreground"
              >
                {label}
              </Link>
            ))}
          </nav>
        </div>
        <p className="text-xs text-subtle">© ArgOS. All rights reserved.</p>
      </div>
    </footer>
  );
}

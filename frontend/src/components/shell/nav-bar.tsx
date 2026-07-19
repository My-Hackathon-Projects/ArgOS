"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { BrainCircuit, Menu, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { HeartbeatBadge } from "@/components/shell/heartbeat-badge";

const NAV = [
  { href: "/sourcing", label: "Sourcing" },
  { href: "/founders", label: "Founders" },
  { href: "/settings", label: "Thesis" },
  { href: "/research", label: "Market Research" },
];

function isActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(href + "/");
}

export function NavBar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <header className="glass sticky top-0 z-50 border-b border-black/[0.06]">
      <div className="mx-auto flex h-12 max-w-6xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link
          href="/sourcing"
          className="flex items-center gap-2"
          aria-label="VC Brain home"
          onClick={() => setOpen(false)}
        >
          <span className="flex h-6 w-6 items-center justify-center rounded-md bg-foreground text-primary-foreground">
            <BrainCircuit className="h-3.5 w-3.5" />
          </span>
          <span className="text-sm font-semibold tracking-tight">VC Brain</span>
        </Link>

        <nav className="hidden items-center gap-1 md:flex" aria-label="Primary">
          {NAV.map(({ href, label }) => {
            const active = isActive(pathname, href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "relative rounded-full px-3.5 py-1.5 text-xs transition-colors duration-200",
                  active
                    ? "font-medium text-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {active && (
                  <motion.span
                    layoutId="nav-pill"
                    className="absolute inset-0 rounded-full bg-black/[0.05]"
                    transition={{ type: "spring", bounce: 0.18, duration: 0.5 }}
                  />
                )}
                <span className="relative">{label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="flex items-center gap-2">
          <HeartbeatBadge />
          <button
            type="button"
            className="flex h-8 w-8 items-center justify-center rounded-full text-foreground transition-colors hover:bg-black/[0.05] md:hidden"
            aria-expanded={open}
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? <X className="h-4.5 w-4.5" /> : <Menu className="h-4.5 w-4.5" />}
          </button>
        </div>
      </div>

      <AnimatePresence>
        {open && (
          <motion.nav
            key="mobile-menu"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.28, ease: [0.25, 0.1, 0.25, 1] }}
            className="glass overflow-hidden border-t border-black/[0.06] md:hidden"
            aria-label="Primary mobile"
          >
            <ul className="px-4 py-3">
              {NAV.map(({ href, label }, i) => (
                <motion.li
                  key={href}
                  initial={{ opacity: 0, y: -6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.04 * i, duration: 0.25 }}
                >
                  <Link
                    href={href}
                    onClick={() => setOpen(false)}
                    className={cn(
                      "block rounded-xl px-3 py-2.5 text-[15px] transition-colors",
                      isActive(pathname, href)
                        ? "font-semibold text-foreground"
                        : "text-muted-foreground hover:bg-black/[0.04] hover:text-foreground",
                    )}
                  >
                    {label}
                  </Link>
                </motion.li>
              ))}
            </ul>
          </motion.nav>
        )}
      </AnimatePresence>
    </header>
  );
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Radar,
  Users,
  SlidersHorizontal,
  LineChart,
  BrainCircuit,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { HeartbeatBadge } from "@/components/sourcing/heartbeat-badge";

const NAV = [
  { href: "/sourcing", label: "Sourcing", icon: Radar },
  { href: "/founders", label: "Founders", icon: Users },
  { href: "/settings", label: "Thesis", icon: SlidersHorizontal },
  { href: "/research", label: "Market Research", icon: LineChart },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 flex h-screen w-64 shrink-0 flex-col border-r border-border bg-surface">
        <div className="flex items-center gap-2.5 px-6 py-5">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-foreground text-primary-foreground">
            <BrainCircuit className="h-[18px] w-[18px]" />
          </span>
          <span className="text-[15px] font-semibold tracking-tight">VC Brain</span>
        </div>

        <nav className="flex flex-1 flex-col gap-0.5 px-3">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || pathname.startsWith(href + "/");
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "group flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition-colors",
                  active
                    ? "bg-accent-soft font-medium text-primary"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                <Icon className="h-[18px] w-[18px]" />
                <span>{label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="px-5 py-4">
          <HeartbeatBadge />
        </div>
      </aside>

      <main className="min-w-0 flex-1">{children}</main>
    </div>
  );
}

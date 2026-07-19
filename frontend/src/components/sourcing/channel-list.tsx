"use client";

import { useListChannels } from "@/api/generated/default/default";
import { Skeleton } from "@/components/ui/skeleton";
import { sourceGradient, splitChannelName } from "@/lib/source-style";

export function ChannelList() {
  const { data, isLoading } = useListChannels();

  if (isLoading) {
    return (
      <div className="space-y-1.5">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="flex items-center gap-3 px-2 py-2">
            <Skeleton className="h-7 w-7 rounded-full" />
            <div className="flex-1 space-y-1.5">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-2.5 w-32" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  const channels = data ?? [];
  const enabled = channels.filter((c) => c.enabled).length;

  return (
    <div>
      <div className="mb-3 flex items-baseline justify-between px-2">
        <h2 className="text-sm font-semibold text-foreground">Monitoring</h2>
        <span className="text-xs text-subtle">{enabled} active</span>
      </div>
      <ul className="space-y-0.5">
        {channels.map((c) => {
          const { title, subtitle } = splitChannelName(c.name);
          return (
            <li
              key={c.name}
              className="flex items-center gap-3 rounded-xl px-2 py-2 transition-colors hover:bg-muted"
            >
              <span
                className="h-7 w-7 shrink-0 rounded-full ring-1 ring-black/5"
                style={{ background: sourceGradient(c.type) }}
                aria-hidden
              />
              <div className="min-w-0 flex-1">
                <div className="truncate text-[13px] font-medium text-foreground">{title}</div>
                {subtitle && (
                  <div className="truncate text-xs text-muted-foreground">{subtitle}</div>
                )}
              </div>
              {c.yield_count > 0 && (
                <span
                  className="shrink-0 rounded-full bg-muted px-1.5 py-0.5 text-[10px] tabular-nums text-muted-foreground"
                  title="signals yielded"
                >
                  {c.yield_count}
                </span>
              )}
              <span
                className={`h-1.5 w-1.5 shrink-0 rounded-full ${c.enabled ? "bg-emerald-500" : "bg-zinc-300"}`}
                title={c.enabled ? "active" : "paused"}
              />
            </li>
          );
        })}
      </ul>
    </div>
  );
}

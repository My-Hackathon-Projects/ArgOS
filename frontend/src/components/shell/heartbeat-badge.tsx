"use client";

import { useHealth } from "@/api/generated/default/default";

/** Compact backend-health pill for the nav bar: pulsing dot + signal count. */
export function HeartbeatBadge() {
  const { data, isError } = useHealth({ query: { refetchInterval: 4000 } });
  const ok = !isError;

  return (
    <div className="flex items-center gap-2 rounded-full bg-black/[0.04] px-3 py-1.5">
      <span className="relative flex h-1.5 w-1.5">
        {ok && (
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
        )}
        <span
          className={`relative inline-flex h-1.5 w-1.5 rounded-full ${ok ? "bg-emerald-500" : "bg-danger"}`}
        />
      </span>
      <span className="text-xs font-medium text-foreground">
        {ok ? "Live" : "Offline"}
        {data != null && (
          <span className="ml-1 hidden font-normal text-muted-foreground sm:inline">
            · {data.signals} signals
          </span>
        )}
      </span>
    </div>
  );
}

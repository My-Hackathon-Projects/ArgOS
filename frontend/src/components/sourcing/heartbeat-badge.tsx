"use client";

import { useHealth } from "@/api/generated/default/default";

export function HeartbeatBadge() {
  const { data, isError } = useHealth({ query: { refetchInterval: 4000 } });
  const ok = !isError;

  return (
    <div className="flex items-center gap-2.5 rounded-xl border border-border bg-surface-muted px-3 py-2">
      <span className="relative flex h-2 w-2">
        {ok && (
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
        )}
        <span
          className={`relative inline-flex h-2 w-2 rounded-full ${ok ? "bg-emerald-500" : "bg-rose-500"}`}
        />
      </span>
      <div className="text-xs leading-tight">
        <div className="font-medium text-foreground">{ok ? "Live" : "Offline"}</div>
        <div className="text-muted-foreground">
          {data ? `${data.signals} signals` : "connecting…"}
        </div>
      </div>
    </div>
  );
}

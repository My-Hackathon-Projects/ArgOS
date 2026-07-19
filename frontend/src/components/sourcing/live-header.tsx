"use client";

import { relativeTime } from "@/lib/format";

// One heartbeat beat spanning 64px; repeated + scrolled -64px for a seamless EKG monitor.
const SEG = "h22 l4 -10 l5 20 l5 -22 l4 12 h24";

function Ekg() {
  const d = `M0 16 ${SEG.repeat(10)}`;
  const mask = "linear-gradient(90deg,transparent,#000 12%,#000 88%,transparent)";
  return (
    <div
      className="relative h-8 w-28 overflow-hidden"
      style={{ maskImage: mask, WebkitMaskImage: mask }}
      aria-hidden
    >
      <svg
        className="absolute left-0 top-0 h-8 animate-ekg"
        width="800"
        height="32"
        viewBox="0 0 800 32"
        fill="none"
        preserveAspectRatio="none"
      >
        <path
          d={d}
          stroke="var(--primary)"
          strokeWidth="1.75"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      </svg>
    </div>
  );
}

export function LiveHeader({
  count,
  channels,
  newestIso,
}: {
  count: number;
  channels?: number;
  newestIso?: string | null;
}) {
  return (
    <div className="card-shadow mb-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-[1.125rem] border border-black/[0.04] bg-surface px-4 py-2.5">
      <div className="flex items-center gap-3">
        <span className="relative flex h-2.5 w-2.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-70" />
          <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
        </span>
        <span className="text-sm font-semibold tracking-tight text-foreground">Live</span>
        <Ekg />
      </div>
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        {channels != null && (
          <>
            <span>
              <span className="font-medium text-foreground tabular-nums">{channels}</span> channels
              monitored
            </span>
            <span aria-hidden>·</span>
          </>
        )}
        <span>
          <span className="font-medium text-foreground tabular-nums">{count}</span> signals received
        </span>
        {newestIso && (
          <>
            <span aria-hidden>·</span>
            <span>newest {relativeTime(newestIso)}</span>
          </>
        )}
      </div>
    </div>
  );
}

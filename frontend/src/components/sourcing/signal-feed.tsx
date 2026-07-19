"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { useListSignals, useListChannels } from "@/api/generated/default/default";
import { SignalCard } from "./signal-card";
import { LiveHeader } from "./live-header";
import { Skeleton } from "@/components/ui/skeleton";

export function SignalFeed() {
  const { data, isLoading, isError } = useListSignals(
    { limit: 40 },
    { query: { refetchInterval: 5000 } },
  );
  const { data: channels } = useListChannels();

  // Track which signal ids we've already shown so freshly-arrived ones can flash in.
  const seen = useRef<Set<string>>(new Set());
  const [flashing, setFlashing] = useState<Set<string>>(new Set());

  // Re-render every 15s so relative timestamps keep ticking (feels live).
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 15000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!data) return;
    const primed = seen.current.size > 0;
    const fresh = data.filter((s) => !seen.current.has(s.id)).map((s) => s.id);
    data.forEach((s) => seen.current.add(s.id));
    if (primed && fresh.length) {
      setFlashing((prev) => new Set([...prev, ...fresh]));
      const timer = setTimeout(() => {
        setFlashing((prev) => {
          const next = new Set(prev);
          fresh.forEach((id) => next.delete(id));
          return next;
        });
      }, 2600);
      return () => clearTimeout(timer);
    }
  }, [data]);

  if (isLoading) {
    return (
      <div className="space-y-2.5">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="flex gap-3.5 rounded-2xl border border-border bg-surface p-4">
            <Skeleton className="h-9 w-9 shrink-0 rounded-full" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-3.5 w-1/2" />
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-24" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-2xl border border-border bg-surface p-6 text-sm text-muted-foreground">
        Could not reach the sourcing backend. Is it running on{" "}
        <code className="text-foreground">localhost:8000</code>?
      </div>
    );
  }

  if (!data?.length) {
    return (
      <div className="rounded-2xl border border-dashed border-border-strong bg-surface p-8 text-center text-sm text-muted-foreground">
        No signals yet. Run discovery to start populating the feed.
      </div>
    );
  }

  const activeChannels = channels?.filter((c) => c.enabled).length;

  return (
    <div>
      <LiveHeader count={data.length} channels={activeChannels} newestIso={data[0]?.ingested_at} />
      <div className="space-y-2.5">
        <AnimatePresence initial={false}>
          {data.map((signal, i) => (
            <motion.div
              key={signal.id}
              layout
              initial={{ opacity: 0, y: -14, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.35, delay: Math.min(i * 0.025, 0.3) }}
            >
              <SignalCard signal={signal} flash={flashing.has(signal.id)} />
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}

import { ExternalLink } from "lucide-react";
import type { SignalListItem } from "@/api/generated/model";
import { Badge } from "@/components/ui/badge";
import { relativeTime } from "@/lib/format";
import { humanize, sourceGradient } from "@/lib/source-style";
import { cn } from "@/lib/utils";

export function SignalCard({ signal, flash }: { signal: SignalListItem; flash?: boolean }) {
  const time = relativeTime(signal.occurred_at ?? signal.ingested_at);
  const gradient = sourceGradient(signal.source);

  return (
    <div
      className={cn(
        "card-shadow card-shadow-hover flex gap-3.5 rounded-[1.125rem] border bg-surface p-4 transition-shadow duration-300",
        flash ? "signal-flash border-primary/40" : "border-black/[0.04]",
      )}
    >
      <span className="relative mt-0.5 h-9 w-9 shrink-0" aria-hidden>
        {flash && (
          <span
            className="absolute inset-0 animate-ping rounded-full opacity-60"
            style={{ background: gradient }}
          />
        )}
        <span
          className="relative block h-9 w-9 rounded-full ring-1 ring-black/5"
          style={{ background: gradient }}
        />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm font-medium text-foreground">
            {signal.title ?? humanize(signal.signal_type)}
          </p>
          <div className="flex shrink-0 items-center gap-2">
            {flash && <Badge variant="primary">New</Badge>}
            {signal.url && (
              <a
                href={signal.url}
                target="_blank"
                rel="noreferrer"
                className="mt-0.5 text-subtle transition-colors hover:text-primary"
                aria-label="Open source"
              >
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            )}
          </div>
        </div>
        {signal.summary && (
          <p className="mt-1 line-clamp-2 text-[13px] leading-relaxed text-muted-foreground">
            {signal.summary}
          </p>
        )}
        <div className="mt-2.5 flex flex-wrap items-center gap-2 text-xs text-subtle">
          <Badge variant="outline">{humanize(signal.signal_type)}</Badge>
          <span className="font-medium text-muted-foreground">{signal.source}</span>
          {signal.source_reliability != null && (
            <>
              <span aria-hidden>·</span>
              <span className="tabular-nums">
                reliability {Math.round(signal.source_reliability * 100)}%
              </span>
            </>
          )}
          {time && (
            <>
              <span aria-hidden>·</span>
              <span>{time}</span>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

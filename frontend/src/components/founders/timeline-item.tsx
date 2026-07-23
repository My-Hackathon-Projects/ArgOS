import { ExternalLink } from "lucide-react";
import type { FounderSignal } from "@/api/generated/model";
import { Badge } from "@/components/ui/badge";
import { relativeTime } from "@/lib/format";
import { humanize, sourceGradient } from "@/lib/source-style";

/** One entry in the founder's signal timeline: source dot, title, meta line.
 *  The whole body is a link when the signal has a source URL. */
export function TimelineItem({ s }: { s: FounderSignal }) {
  const time = relativeTime(s.occurred_at);

  const content = (
    <>
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium text-foreground">
          {s.title ?? humanize(s.signal_type)}
        </p>
        {s.url && <ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0 text-subtle" aria-hidden />}
      </div>
      {s.summary && (
        <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">{s.summary}</p>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-subtle">
        <Badge variant="outline">{humanize(s.signal_type)}</Badge>
        <span className="font-medium text-muted-foreground">{s.source}</span>
        {time && (
          <>
            <span aria-hidden>·</span>
            <span>{time}</span>
          </>
        )}
      </div>
    </>
  );

  return (
    <div className="flex gap-3.5">
      <div className="flex flex-col items-center">
        <span
          className="h-8 w-8 shrink-0 rounded-full ring-1 ring-black/5"
          style={{ background: sourceGradient(s.source) }}
          aria-hidden
        />
        <span className="mt-1 w-px flex-1 bg-border" />
      </div>
      {s.url ? (
        <a
          href={s.url}
          target="_blank"
          rel="noreferrer"
          aria-label={`Open source: ${s.title ?? humanize(s.signal_type)}`}
          className="-mx-2 mb-6 min-w-0 flex-1 rounded-xl px-2 py-1 transition-all duration-200 hover:bg-black/[0.03] active:scale-[0.995]"
        >
          {content}
        </a>
      ) : (
        <div className="min-w-0 flex-1 pb-6">{content}</div>
      )}
    </div>
  );
}

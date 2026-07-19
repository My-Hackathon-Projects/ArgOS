"use client";

import Link from "next/link";
import {
  ArrowLeft,
  AtSign,
  Briefcase,
  Code2,
  ExternalLink,
  Globe,
  MapPin,
} from "lucide-react";
import { useGetFounder } from "@/api/generated/default/default";
import type { FounderSignal } from "@/api/generated/model";
import { Badge, type BadgeProps } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { initials, relativeTime } from "@/lib/format";
import { humanize, sourceGradient } from "@/lib/source-style";

function statusBadge(status: string): { variant: BadgeProps["variant"]; label: string } {
  if (status === "confirmed") return { variant: "success", label: "Confirmed" };
  if (status === "needs_review") return { variant: "danger", label: "Needs review" };
  return { variant: "muted", label: "Candidate" };
}

function identityHref(kind: string, val: string): string {
  if (val.startsWith("http")) return val;
  const clean = val.replace(/^@/, "");
  if (kind === "github") return `https://github.com/${clean}`;
  if (kind === "twitter") return `https://twitter.com/${clean}`;
  if (kind === "linkedin") return `https://linkedin.com/in/${clean}`;
  return `https://${clean}`;
}

const IDENTITY_ICONS = { github: Code2, twitter: AtSign, linkedin: Briefcase, website: Globe };

function TimelineItem({ s }: { s: FounderSignal }) {
  const time = relativeTime(s.occurred_at);
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
      <div className="min-w-0 flex-1 pb-6">
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm font-medium text-foreground">
            {s.title ?? humanize(s.signal_type)}
          </p>
          {s.url && (
            <a
              href={s.url}
              target="_blank"
              rel="noreferrer"
              className="mt-0.5 shrink-0 text-subtle hover:text-primary"
              aria-label="Open source"
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          )}
        </div>
        {s.summary && (
          <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">{s.summary}</p>
        )}
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-subtle">
          <Badge variant="outline">{humanize(s.signal_type)}</Badge>
          <span className="font-medium text-muted-foreground">{s.source}</span>
          {s.resolution_method && (
            <>
              <span aria-hidden>·</span>
              <span>
                matched via {s.resolution_method}
                {s.resolution_confidence != null &&
                  ` (${Math.round(s.resolution_confidence * 100)}%)`}
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

export function FounderDetail({ founderId }: { founderId: string }) {
  const { data: f, isLoading, isError } = useGetFounder(founderId);

  if (isError) {
    return (
      <Card className="p-6 text-sm text-muted-foreground">Founder not found.</Card>
    );
  }

  if (isLoading || !f) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full rounded-2xl" />
        <Skeleton className="h-64 w-full rounded-2xl" />
      </div>
    );
  }

  const s = statusBadge(f.status);
  const identity = f.identity;
  const links = (Object.keys(IDENTITY_ICONS) as (keyof typeof IDENTITY_ICONS)[])
    .map((k) => ({ kind: k, val: identity[k] }))
    .filter((x): x is { kind: keyof typeof IDENTITY_ICONS; val: string } => Boolean(x.val));

  return (
    <div className="space-y-6">
      <Link
        href="/founders"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Founders
      </Link>

      <Card className="p-6">
        <div className="flex items-start gap-4">
          <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-muted text-lg font-semibold text-muted-foreground">
            {initials(f.display_name)}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="font-serif text-2xl text-foreground">
                {f.display_name ?? "Unknown"}
              </h1>
              <Badge variant={s.variant}>{s.label}</Badge>
            </div>
            <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
              {f.occupation && <span>{f.occupation}</span>}
              {f.current_company && (
                <>
                  <span aria-hidden>·</span>
                  <span>{f.current_company}</span>
                </>
              )}
              {f.city && (
                <>
                  <span aria-hidden>·</span>
                  <span className="inline-flex items-center gap-1">
                    <MapPin className="h-3.5 w-3.5" />
                    {f.city}
                  </span>
                </>
              )}
            </div>
            {links.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {links.map(({ kind, val }) => {
                  const Icon = IDENTITY_ICONS[kind];
                  return (
                    <a
                      key={kind}
                      href={identityHref(kind, val)}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1.5 rounded-full border border-border-strong bg-surface px-3 py-1 text-xs font-medium text-muted-foreground transition-colors hover:border-primary hover:text-primary"
                    >
                      <Icon className="h-3.5 w-3.5" />
                      {kind}
                    </a>
                  );
                })}
              </div>
            )}
          </div>
          {f.discovery_confidence != null && (
            <div className="shrink-0 text-right">
              <div className="font-serif text-3xl text-foreground">
                {Math.round(f.discovery_confidence * 100)}
                <span className="text-lg text-subtle">%</span>
              </div>
              <div className="text-xs text-subtle">discovery confidence</div>
            </div>
          )}
        </div>
      </Card>

      <div>
        <h2 className="mb-4 text-sm font-semibold text-foreground">
          Signal timeline
          <span className="ml-2 font-normal text-subtle">{f.signals.length}</span>
        </h2>
        {f.signals.length === 0 ? (
          <Card className="p-6 text-sm text-muted-foreground">No signals resolved yet.</Card>
        ) : (
          <div>
            {f.signals.map((sig, i) => (
              <TimelineItem key={i} s={sig} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

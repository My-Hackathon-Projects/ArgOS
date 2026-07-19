"use client";

import Link from "next/link";
import { ArrowLeft, AtSign, Briefcase, Code2, Globe, MapPin } from "lucide-react";
import { useGetFounder } from "@/api/generated/default/default";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { initials } from "@/lib/format";
import { statusBadge } from "@/components/founders/status";
import { TimelineItem } from "@/components/founders/timeline-item";

function identityHref(kind: string, val: string): string {
  if (val.startsWith("http")) return val;
  const clean = val.replace(/^@/, "");
  if (kind === "github") return `https://github.com/${clean}`;
  if (kind === "twitter") return `https://twitter.com/${clean}`;
  if (kind === "linkedin") return `https://linkedin.com/in/${clean}`;
  return `https://${clean}`;
}

const IDENTITY_ICONS = { github: Code2, twitter: AtSign, linkedin: Briefcase, website: Globe };

export function FounderDetail({ founderId }: { founderId: string }) {
  const { data: f, isLoading, isError } = useGetFounder(founderId);

  if (isError) {
    return <Card className="p-6 text-sm text-muted-foreground">Founder not found.</Card>;
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

      <Card className="p-5 sm:p-6">
        <div className="flex flex-wrap items-start gap-4">
          <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-muted text-lg font-semibold text-muted-foreground">
            {initials(f.display_name)}
          </span>
          <div className="min-w-0 flex-1 basis-56">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-2xl font-semibold tracking-tight text-foreground">
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
            <div className="shrink-0 sm:text-right">
              <div className="text-3xl font-semibold tracking-tight text-foreground">
                {Math.round(f.discovery_confidence * 100)}
                <span className="text-lg font-normal text-subtle">%</span>
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

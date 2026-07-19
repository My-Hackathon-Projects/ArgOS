"use client";

import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import type { FounderClaimItem } from "@/api/generated/model";
import { Badge, type BadgeProps } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { PAGE_SIZE, Pagination } from "@/components/ui/pagination";
import { humanize } from "@/lib/source-style";

function claimStatusBadge(status: string): { variant: BadgeProps["variant"]; label: string } {
  if (status === "verified") return { variant: "success", label: "Verified" };
  if (status === "contradicted") return { variant: "danger", label: "Contradicted" };
  if (status === "needs_review") return { variant: "danger", label: "Needs review" };
  return { variant: "muted", label: "Unverified" };
}

function TrustBar({ value }: { value: number | null }) {
  if (value == null) return <span className="text-xs text-subtle">—</span>;
  const pct = Math.round(value * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-14 overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full"
          style={{ width: `${pct}%`, background: "var(--axis-founder)" }}
        />
      </div>
      <span className="text-xs tabular-nums text-muted-foreground">{pct}%</span>
    </div>
  );
}

/** Corroborated claims with their Trust Scores: the evidence behind the Founder Score. */
export function ClaimsList({ claims }: { claims: FounderClaimItem[] }) {
  const [page, setPage] = useState(1);

  if (claims.length === 0) {
    return (
      <Card className="p-5 text-sm text-muted-foreground">
        No claims extracted yet. Claims appear after the claims agent processes this founder&apos;s
        signals.
      </Card>
    );
  }

  const visible = claims.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <>
      <Card className="overflow-hidden">
        <div className="divide-y divide-border">
          {visible.map((c, i) => {
            const s = claimStatusBadge(c.status);
            return (
              <div key={i} className="flex items-start gap-3 px-4 py-3.5 sm:px-5">
                <span
                  className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full"
                  style={{ background: "rgba(124,58,237,0.08)", color: "var(--axis-founder)" }}
                >
                  <ShieldCheck className="h-3.5 w-3.5" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm leading-snug text-foreground">{c.statement}</p>
                  <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-subtle">
                    {c.category && <Badge variant="outline">{humanize(c.category)}</Badge>}
                    <TrustBar value={c.trust_score} />
                    <span>
                      {c.evidence_count} source{c.evidence_count === 1 ? "" : "s"}
                    </span>
                    <Badge variant={s.variant}>{s.label}</Badge>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </Card>
      <Pagination
        page={page}
        pageCount={Math.max(1, Math.ceil(claims.length / PAGE_SIZE))}
        onPageChange={setPage}
      />
    </>
  );
}

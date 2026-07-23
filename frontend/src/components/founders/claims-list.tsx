"use client";

import { useState } from "react";
import { ChevronDown, ShieldCheck } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import type { ClaimTrustComponents, FounderClaimItem } from "@/api/generated/model";
import { Badge, type BadgeProps } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { PAGE_SIZE, Pagination } from "@/components/ui/pagination";
import { relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { humanize } from "@/lib/source-style";

// Every claim is sourced — "verified" here means the corroborating evidence cleared the
// trust bar, not that unlabeled claims are unsourced. Hence corroboration language, not
// "verified/unverified", which reads as "no evidence" to an investor.
// Number-first: badge ONLY the meaningful states. The sub-threshold majority (~95% of
// claims) carries no badge — the trust % + breakdown are the signal, and a constant
// "Uncorroborated" label would be noise (and every claim IS sourced, so it misleads).
function claimStatusBadge(status: string): { variant: BadgeProps["variant"]; label: string } | null {
  if (status === "verified") return { variant: "success", label: "Corroborated" };
  if (status === "contradicted") return { variant: "danger", label: "Contradicted" };
  if (status === "needs_review") return { variant: "danger", label: "Needs review" };
  return null;
}

function pct(v: number): number {
  return Math.round(v * 100);
}

function TrustBar({ value }: { value: number | null }) {
  const reduceMotion = useReducedMotion();
  if (value == null) return <span className="text-xs text-subtle">—</span>;
  const p = pct(value);
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-14 overflow-hidden rounded-full bg-muted">
        {/* Full-width bar scaled by trust — scaleX stays on the GPU, width doesn't. */}
        <motion.div
          className="h-full rounded-full"
          style={{ background: "var(--axis-founder)", transformOrigin: "left" }}
          initial={reduceMotion ? false : { scaleX: 0 }}
          whileInView={{ scaleX: p / 100 }}
          viewport={{ once: true, margin: "-20px" }}
          transition={{ duration: 0.6, ease: [0.23, 1, 0.32, 1] }}
        />
      </div>
      <span className="font-mono text-xs tabular-nums text-muted-foreground">{p}%</span>
    </div>
  );
}

/** The "show the receipts" panel: how the Trust Score was actually computed. */
function TrustBreakdown({ tc }: { tc: ClaimTrustComponents }) {
  const stats: { label: string; value: string }[] = [
    { label: "Support", value: `${pct(tc.support)}%` },
    { label: "Refute", value: tc.refute > 0 ? `${pct(tc.refute)}%` : "none" },
    {
      label: "Corroborating",
      value: `${tc.corroboration_n} ${tc.corroboration_n === 1 ? "source" : "sources"}`,
    },
    { label: "External check", value: tc.external_verified ? "passed" : "—" },
  ];
  return (
    <div className="mt-3 rounded-lg border border-border bg-surface-muted p-3 text-xs">
      <div className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-4">
        {stats.map((s) => (
          <div key={s.label}>
            <div className="text-subtle">{s.label}</div>
            <div className="mt-0.5 font-mono tabular-nums text-foreground">{s.value}</div>
          </div>
        ))}
      </div>
      {tc.sources.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <span className="text-subtle">Sources</span>
          {tc.sources.map((src, i) => (
            <Badge key={i} variant="outline">
              {humanize(src)}
            </Badge>
          ))}
        </div>
      )}
      <p className="mt-3 leading-relaxed text-subtle">
        Trust = corroborating evidence (noisy-OR), discounted by any refutation. A claim is
        Corroborated once it clears 70%.
      </p>
    </div>
  );
}

/** Corroborated claims with their Trust Scores: the evidence behind the Founder Score. */
export function ClaimsList({ claims }: { claims: FounderClaimItem[] }) {
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<number | null>(null);

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
            const absIndex = (page - 1) * PAGE_SIZE + i;
            const s = claimStatusBadge(c.status);
            const tc = c.trust_components;
            const expanded = open === absIndex;
            return (
              <div key={i} className="px-4 py-3.5 sm:px-5">
                <button
                  type="button"
                  onClick={() => tc && setOpen(expanded ? null : absIndex)}
                  aria-expanded={tc ? expanded : undefined}
                  disabled={!tc}
                  className="flex w-full items-start gap-3 text-left disabled:cursor-default"
                >
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
                        {c.supporting_count} supporting
                        {c.refuting_count > 0 && (
                          <span className="ml-1 font-medium text-rose-600">
                            · {c.refuting_count} refuting
                          </span>
                        )}
                      </span>
                      {c.updated_at && <span>updated {relativeTime(c.updated_at)}</span>}
                      {s && <Badge variant={s.variant}>{s.label}</Badge>}
                      {tc && (
                        <ChevronDown
                          className={cn(
                            "h-3.5 w-3.5 text-subtle transition-transform duration-200",
                            expanded && "rotate-180",
                          )}
                          aria-hidden
                        />
                      )}
                    </div>
                  </div>
                </button>
                <AnimatePresence initial={false}>
                  {expanded && tc && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.22, ease: [0.23, 1, 0.32, 1] }}
                      className="overflow-hidden pl-10"
                    >
                      <TrustBreakdown tc={tc} />
                    </motion.div>
                  )}
                </AnimatePresence>
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

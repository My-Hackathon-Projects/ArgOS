"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ExternalLink, FileText, Loader2, RefreshCw } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { useCreateMemo, useGetMemo } from "@/api/generated/default/default";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { relativeTime } from "@/lib/format";
import { GapsCard } from "@/components/market/gaps-card";
import { Section } from "@/components/market/section";

type Hypothesis = { statement: string; evidence_claim_ids?: string[] };

function SourceLinks({ urls }: { urls: string[] }) {
  if (urls.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {urls.slice(0, 8).map((u, i) => (
        <a
          key={i}
          href={u}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 rounded-full border border-border-strong px-2 py-0.5 text-[11px] text-muted-foreground transition-colors hover:border-primary hover:text-primary"
        >
          <ExternalLink className="h-3 w-3" />
          source
        </a>
      ))}
    </div>
  );
}

/** The investment memo: LLM prose with citation and gap anchors, generated on demand. */
export function MemoSection({ opportunityId }: { opportunityId: string }) {
  const qc = useQueryClient();
  const memo = useGetMemo(opportunityId, { query: { retry: false } });
  const create = useCreateMemo({
    mutation: { onSuccess: () => qc.invalidateQueries() },
  });
  const reduceMotion = useReducedMotion();

  const generate = () => create.mutate({ opportunityId });
  const m = memo.data;

  if (!m) {
    return (
      <Section title="Investment memo">
        <Card className="p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-start gap-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-primary">
                <FileText className="h-4.5 w-4.5" />
              </span>
              <div>
                <div className="text-sm font-medium text-foreground">
                  {create.isPending ? "Drafting memo" : "No memo yet"}
                </div>
                <p className="mt-1 max-w-md text-[13px] leading-relaxed text-muted-foreground">
                  {create.isPending
                    ? "Reading the three-axis screen, founder claims and market evidence…"
                    : "Compose a cited, decision-ready memo from the three-axis screen, founder claims and market evidence."}
                </p>
              </div>
            </div>
            <Button size="sm" onClick={generate} disabled={create.isPending}>
              {create.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              {create.isPending ? "Generating…" : "Generate memo"}
            </Button>
          </div>
          {create.isPending && (
            <div className="mt-4 space-y-2.5 border-t border-border pt-4" aria-hidden>
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-11/12" />
              <Skeleton className="h-3 w-4/5" />
              <Skeleton className="mt-4 h-3 w-32" />
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-2/3" />
            </div>
          )}
        </Card>
      </Section>
    );
  }

  const s = (m.sections ?? {}) as Record<string, unknown>;
  const hyps = Array.isArray(s.hypotheses) ? (s.hypotheses as Hypothesis[]) : [];
  const swot = (s.swot ?? {}) as Record<string, string[]>;
  const q = (m.quality ?? {}) as Record<string, unknown>;
  const provUrls = Array.isArray(q.provenance_urls) ? (q.provenance_urls as string[]) : [];

  return (
    <Section title="Investment memo">
      {/* Blur bridges the skeleton -> prose swap so it reads as one surface resolving,
          not two elements trading places. */}
      <motion.div
        className="space-y-3"
        initial={reduceMotion ? false : { opacity: 0, y: 8, filter: "blur(4px)" }}
        animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
        transition={{ duration: 0.45, ease: [0.23, 1, 0.32, 1] }}
      >
        <Card className="p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              {q.all_citations_resolved === true && (
                <Badge variant="success">citations resolved</Badge>
              )}
              {m.confidence != null && (
                <span className="text-xs tabular-nums text-muted-foreground">
                  confidence {Math.round(m.confidence * 100)}%
                </span>
              )}
              <span className="text-xs text-subtle">
                {provUrls.length} sources · generated {relativeTime(m.generated_at)}
              </span>
            </div>
            <Button size="sm" variant="secondary" onClick={generate} disabled={create.isPending}>
              {create.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              Regenerate
            </Button>
          </div>

          {typeof s.snapshot === "string" && (
            <div className="mt-4 border-t border-border pt-4">
              <div className="text-xs font-semibold uppercase tracking-wider text-subtle">
                Snapshot
              </div>
              <p className="mt-1.5 text-sm leading-relaxed text-foreground">{s.snapshot}</p>
            </div>
          )}

          {hyps.length > 0 && (
            <div className="mt-4 border-t border-border pt-4">
              <div className="text-xs font-semibold uppercase tracking-wider text-subtle">
                Investment hypotheses
              </div>
              <ul className="mt-2 space-y-2">
                {hyps.map((h, i) => (
                  <li key={i} className="text-sm leading-relaxed text-foreground">
                    <span className="mr-1 text-primary">•</span>
                    {h.statement}
                    <span className="ml-1 text-[11px] text-subtle">
                      [{h.evidence_claim_ids?.length ?? 0} cited]
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {m.recommendation && (
            <div
              className="mt-4 rounded-xl p-4"
              style={{ background: "var(--accent-soft)" }}
            >
              <div className="text-xs font-semibold uppercase tracking-wider text-primary">
                Recommendation
              </div>
              <p className="mt-1.5 text-sm leading-relaxed text-foreground">
                {m.recommendation}
              </p>
            </div>
          )}
        </Card>

        {Object.keys(swot).length > 0 && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {(["strengths", "weaknesses", "opportunities", "threats"] as const).map((k) =>
              (swot[k] ?? []).length > 0 ? (
                <Card key={k} className="p-4">
                  <div className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-subtle">
                    {k}
                  </div>
                  <ul className="space-y-1">
                    {(swot[k] ?? []).map((b, i) => (
                      <li key={i} className="text-[13px] leading-relaxed text-muted-foreground">
                        {b}
                      </li>
                    ))}
                  </ul>
                </Card>
              ) : null,
            )}
          </div>
        )}

        {m.gaps.length > 0 && <GapsCard gaps={m.gaps} />}
        <SourceLinks urls={provUrls} />
      </motion.div>
    </Section>
  );
}

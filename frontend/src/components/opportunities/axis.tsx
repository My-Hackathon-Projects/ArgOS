"use client";

import { motion, useReducedMotion } from "motion/react";
import type { OpportunityAxisSummary } from "@/api/generated/model";
import { TrendIcon, verdictBadge } from "@/components/market/meta";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { CountUp } from "@/components/ui/count-up";

const EASE_OUT_STRONG = [0.23, 1, 0.32, 1] as const;
const EASE_IN_OUT_STRONG = [0.77, 0, 0.175, 1] as const;

export const AXIS_ORDER = ["founder", "market", "idea"] as const;

export const AXIS_STYLE: Record<string, { label: string; color: string; soft: string }> = {
  founder: { label: "Founder", color: "var(--axis-founder)", soft: "rgba(124,58,237,0.08)" },
  market: { label: "Market", color: "var(--axis-market)", soft: "rgba(0,113,227,0.08)" },
  idea: { label: "Idea vs market", color: "var(--axis-idea)", soft: "rgba(5,150,105,0.08)" },
};

/** Compact colored chip for list rows: axis initial + score. */
export function AxisChip({ a }: { a: OpportunityAxisSummary }) {
  const style = AXIS_STYLE[a.axis] ?? AXIS_STYLE.market;
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium tabular-nums"
      style={{ color: style.color, background: style.soft }}
      title={`${style.label}: ${a.verdict}`}
    >
      {style.label}
      <span className="font-semibold">{a.score ?? "—"}</span>
    </span>
  );
}

/** Full scoring card for the detail page; renders a pending state without data.
 *  The three cards enter with a small stagger (keyed off AXIS_ORDER, so no parent
 *  wiring needed) and each score counts up — three deliberately separate readings,
 *  never one blended number. */
export function AxisScoreCard({
  axis,
  data,
}: {
  axis: (typeof AXIS_ORDER)[number];
  data: OpportunityAxisSummary | undefined;
}) {
  const style = AXIS_STYLE[axis];
  const vb = data ? verdictBadge(data.verdict) : null;
  const reduceMotion = useReducedMotion();
  const delay = AXIS_ORDER.indexOf(axis) * 0.07;
  return (
    <motion.div
      initial={reduceMotion ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay, ease: EASE_OUT_STRONG }}
    >
      <Card className="relative overflow-hidden p-5">
        <motion.span
          className="absolute inset-x-0 top-0 h-1"
          style={{ background: style.color, transformOrigin: "left" }}
          initial={reduceMotion ? false : { scaleX: 0 }}
          animate={{ scaleX: 1 }}
          transition={{ duration: 0.5, delay: delay + 0.15, ease: EASE_IN_OUT_STRONG }}
          aria-hidden
        />
        <div
          className="text-xs font-semibold uppercase tracking-wider"
          style={{ color: style.color }}
        >
          {style.label}
        </div>
        {data ? (
          <>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="font-mono text-4xl font-semibold tracking-tight tabular-nums text-foreground">
                {data.score != null ? <CountUp value={data.score} /> : "—"}
              </span>
              <span className="text-xs text-subtle">/ 100</span>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              {vb && <Badge variant={vb.variant}>{vb.label}</Badge>}
              <span className="flex items-center gap-1">
                <TrendIcon trend={data.trend} />
                {data.trend}
              </span>
              {data.confidence != null && (
                <span className="tabular-nums">conf {Math.round(data.confidence * 100)}%</span>
              )}
            </div>
            {data.rationale && (
              <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-muted-foreground">
                {data.rationale}
              </p>
            )}
            {(data.gaps?.length ?? 0) > 0 && (
              <ul className="mt-2 space-y-0.5">
                {(data.gaps ?? []).slice(0, 3).map((g, i) => (
                  <li key={i} className="text-[11px] leading-snug text-amber-700">
                    {g}
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : (
          <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
            Not scored yet. This axis fills in when its agent runs for the opportunity.
          </p>
        )}
      </Card>
    </motion.div>
  );
}

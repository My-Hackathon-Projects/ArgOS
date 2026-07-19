"use client";

import type { ScorePoint } from "@/api/generated/model";

/** Inline score-history sparkline — trend over time, not just the snapshot.
 *  Renders only when there are >=2 points (a single point has no trend). The delta is
 *  also shown as text so the trend is never color/shape-alone. */
export function ScoreSparkline({ history }: { history: ScorePoint[] }) {
  const pts = history.filter((h) => h.score != null);
  if (pts.length < 2) return null;

  const w = 96;
  const h = 28;
  const pad = 3;
  const scores = pts.map((p) => p.score as number);
  const min = Math.min(...scores);
  const max = Math.max(...scores);
  const span = max - min || 1;
  const x = (i: number) => pad + (i * (w - 2 * pad)) / (pts.length - 1);
  const y = (s: number) => h - pad - ((s - min) * (h - 2 * pad)) / span;
  const points = scores.map((s, i) => `${x(i).toFixed(1)},${y(s).toFixed(1)}`).join(" ");

  const first = scores[0];
  const last = scores[scores.length - 1];
  const delta = Math.round(last - first);
  const label = `Founder Score trend: ${Math.round(first)} to ${Math.round(last)} over ${pts.length} updates`;

  return (
    <div className="mt-1 flex items-center gap-2" title={label}>
      <svg width={w} height={h} role="img" aria-label={label} className="shrink-0 overflow-visible">
        <polyline
          points={points}
          fill="none"
          stroke="var(--axis-founder)"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle
          cx={x(pts.length - 1)}
          cy={y(last)}
          r="3"
          fill="var(--axis-founder)"
          stroke="var(--surface, #fff)"
          strokeWidth="2"
        />
      </svg>
      <span className="text-xs tabular-nums text-subtle">
        {Math.round(first)} → {Math.round(last)}
        {delta !== 0 && <span className="ml-1">({delta > 0 ? "+" : ""}{delta})</span>}
      </span>
    </div>
  );
}

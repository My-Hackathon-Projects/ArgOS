import { ExternalLink, Minus, TrendingDown, TrendingUp } from "lucide-react";
import type { BadgeProps } from "@/components/ui/badge";

/** Small shared presentational helpers for the market research views. */

export function verdictBadge(v: string | null): { variant: BadgeProps["variant"]; label: string } {
  if (v === "bull") return { variant: "success", label: "Bull" };
  if (v === "bear") return { variant: "danger", label: "Bear" };
  return { variant: "muted", label: "Neutral" };
}

export function TrendIcon({ trend }: { trend: string | null }) {
  if (trend === "improving") return <TrendingUp className="h-4 w-4 text-emerald-600" />;
  if (trend === "declining") return <TrendingDown className="h-4 w-4 text-rose-600" />;
  return <Minus className="h-4 w-4 text-subtle" />;
}

export function Src({ url }: { url: string | null }) {
  if (!url) return null;
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 text-xs text-subtle transition-colors hover:text-primary"
    >
      source <ExternalLink className="h-3 w-3" />
    </a>
  );
}

export function Trust({ value }: { value: number | null }) {
  if (value == null) return null;
  return (
    <span className="text-xs tabular-nums text-subtle">trust {Math.round(value * 100)}%</span>
  );
}

export function BasisChip({ basis }: { basis: string | null }) {
  const label = basis === "estimated_bottom_up" ? "estimated" : (basis ?? "—");
  const cls =
    basis === "reported"
      ? "text-emerald-700 bg-emerald-50"
      : basis === "estimated_bottom_up"
        ? "text-amber-700 bg-amber-50"
        : "text-subtle bg-muted";
  return (
    <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ${cls}`}>{label}</span>
  );
}

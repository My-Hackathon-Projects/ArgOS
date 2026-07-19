"use client";

import { useState } from "react";
import { ChevronDown, GitBranch } from "lucide-react";
import { useGetFounderTrace } from "@/api/generated/default/default";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { relativeTime } from "@/lib/format";

// Only stages the backend actually emits (sourcing/persist.py, claims/service.py,
// inbound/service.py). Add labels here as new trace writers ship.
const STAGE_LABEL: Record<string, string> = {
  sourcing: "Sourcing",
  claims: "Claims",
  screen: "Screening",
};

function fmt(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "object") {
    return Object.entries(v as Record<string, unknown>)
      .map(([k, val]) => `${k.replace(/_/g, " ")}: ${typeof val === "object" && val !== null ? JSON.stringify(val) : String(val)}`)
      .join(" · ");
  }
  return String(v);
}

/** Step-level reasoning trace (stretch goal #1): what each agent did, in order, with evidence. */
export function TraceTimeline({ founderId }: { founderId: string }) {
  const { data: steps, isError } = useGetFounderTrace(founderId);
  const [open, setOpen] = useState(false);

  if (isError || !steps || steps.length === 0) return null; // additive — absent trace hides the panel

  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground"
      >
        <GitBranch className="h-4 w-4 text-subtle" />
        Reasoning trace
        <span className="font-normal text-subtle">{steps.length} steps</span>
        <ChevronDown
          className={`h-4 w-4 text-subtle transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <Card className="divide-y divide-border p-0">
          {steps.map((t, i) => (
            <div key={i} className="flex items-start gap-3 px-4 py-3">
              <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-primary" aria-hidden />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline">{STAGE_LABEL[t.stage] ?? t.stage}</Badge>
                  {t.agent && <span className="text-xs text-subtle">{t.agent}</span>}
                  <span className="text-xs text-subtle">{relativeTime(t.created_at)}</span>
                </div>
                {t.output != null && (
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                    {fmt(t.output)}
                  </p>
                )}
                {Array.isArray(t.evidence_ids) && t.evidence_ids.length > 0 && (
                  <p className="mt-0.5 text-xs text-subtle">
                    cites {t.evidence_ids.length} evidence item
                    {t.evidence_ids.length === 1 ? "" : "s"}
                  </p>
                )}
              </div>
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}

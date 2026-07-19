"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowUpRight, Loader2 } from "lucide-react";
import { useCreateOpportunity } from "@/api/generated/default/default";
import type { FounderDetail } from "@/api/generated/model";
import { Button } from "@/components/ui/button";
import { Dialog, fieldClass } from "@/components/ui/dialog";

/** The hand-trigger that turns a sourced founder into a pipeline deal.
 *  Sourcing/claims/scoring run automatically; entering screening is an investor
 *  decision, so this stays a deliberate click. */
export function PromoteButton({ founder }: { founder: FounderDetail }) {
  const router = useRouter();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [company, setCompany] = useState(founder.current_company ?? "");
  const [idea, setIdea] = useState("");
  const [sector, setSector] = useState("");
  const [geo, setGeo] = useState(founder.city ?? "");

  const { mutate, isPending, error } = useCreateOpportunity({
    mutation: {
      onSuccess: (opp) => {
        qc.invalidateQueries();
        setOpen(false);
        router.push(`/opportunities/${opp.id}`);
      },
    },
  });

  // Mirrors the backend validator: an opportunity needs an idea or a sector to screen against.
  const hasScreeningSubject = Boolean(idea.trim() || sector.trim());
  const canSubmit = hasScreeningSubject && !isPending;
  const errorDetail = (error?.response?.data as { detail?: unknown } | undefined)?.detail;

  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        <ArrowUpRight className="h-3.5 w-3.5" />
        Send to decisions
      </Button>
      <Dialog open={open} onClose={() => setOpen(false)} title="Add to decisions">
        <p className="mb-4 text-[13px] leading-relaxed text-muted-foreground">
          Moves {founder.display_name ?? "this founder"} into the decision loop. The
          three-axis screen and investment memo stay hand-triggered from the detail page.
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!canSubmit) return;
            mutate({
              data: {
                founder_id: founder.id,
                company_name: company.trim() || null,
                idea: idea.trim() || null,
                sector: sector.trim() || null,
                geo: geo.trim() || null,
              },
            });
          }}
          className="space-y-4"
        >
          <label className="block">
            <span className="mb-1.5 block text-xs font-medium text-muted-foreground">
              What are they building?
            </span>
            <textarea
              value={idea}
              onChange={(e) => setIdea(e.target.value)}
              placeholder="One or two sentences on the idea — this is what the market gets sized against."
              rows={3}
              className={`${fieldClass} h-auto py-2.5 leading-relaxed`}
              autoFocus
            />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1.5 block text-xs font-medium text-muted-foreground">Sector</span>
              <input
                value={sector}
                onChange={(e) => setSector(e.target.value)}
                placeholder="dev tools"
                className={fieldClass}
              />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-xs font-medium text-muted-foreground">Geo</span>
              <input
                value={geo}
                onChange={(e) => setGeo(e.target.value)}
                placeholder="Munich"
                className={fieldClass}
              />
            </label>
          </div>
          <label className="block">
            <span className="mb-1.5 block text-xs font-medium text-muted-foreground">
              Company (if one exists yet)
            </span>
            <input
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              placeholder="Stealth"
              className={fieldClass}
            />
          </label>

          {!hasScreeningSubject && !isPending && (
            <p className="text-xs text-subtle">An idea or a sector is needed to screen against.</p>
          )}
          {error != null && (
            <p className="text-[13px] text-danger">
              Could not create the decision record
              {typeof errorDetail === "string" ? `: ${errorDetail}` : ""}.
            </p>
          )}

          <Button type="submit" disabled={!canSubmit} className="w-full">
            {isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Creating…
              </>
            ) : (
              "Enter screening"
            )}
          </Button>
        </form>
      </Dialog>
    </>
  );
}

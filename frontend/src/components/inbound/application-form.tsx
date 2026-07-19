"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useCreateOpportunity, useListFounders } from "@/api/generated/default/default";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

const FIELD =
  "h-9 w-full rounded-xl bg-black/[0.04] px-3.5 text-sm text-foreground transition-colors placeholder:text-subtle hover:bg-black/[0.06] focus:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/** Log a new inbound application by hand; it becomes an opportunity in the screening loop. */
export function ApplicationForm({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const { data: founders } = useListFounders();
  const [company, setCompany] = useState("");
  const [idea, setIdea] = useState("");
  const [sector, setSector] = useState("");
  const [geo, setGeo] = useState("");
  const [founderId, setFounderId] = useState("");

  const { mutate, isPending, isError } = useCreateOpportunity({
    mutation: {
      onSuccess: () => {
        qc.invalidateQueries();
        onClose();
        setCompany("");
        setIdea("");
        setSector("");
        setGeo("");
        setFounderId("");
      },
    },
  });

  const canSubmit = (idea.trim() || sector.trim()) && !isPending;

  const submit = () =>
    mutate({
      data: {
        company_name: company.trim() || null,
        idea: idea.trim() || null,
        sector: sector.trim() || null,
        geo: geo.trim() || null,
        founder_id: founderId || null,
      },
    });

  return (
    <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.28, ease: [0.25, 0.1, 0.25, 1] }}
            className="overflow-hidden"
          >
            <Card className="mt-3 space-y-3 p-4 sm:p-5">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <label className="block">
                  <span className="mb-1 block text-xs font-medium text-muted-foreground">
                    Company (optional)
                  </span>
                  <input
                    className={FIELD}
                    value={company}
                    onChange={(e) => setCompany(e.target.value)}
                    placeholder="Acme Robotics"
                  />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs font-medium text-muted-foreground">
                    Founder (optional)
                  </span>
                  <select
                    className={`${FIELD} cursor-pointer appearance-none`}
                    value={founderId}
                    onChange={(e) => setFounderId(e.target.value)}
                  >
                    <option value="">Not linked yet</option>
                    {founders?.map((f) => (
                      <option key={f.id} value={f.id}>
                        {f.display_name ?? "Unknown"}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <label className="block">
                <span className="mb-1 block text-xs font-medium text-muted-foreground">
                  Idea (what are they building?)
                </span>
                <textarea
                  className={`${FIELD} h-20 resize-none py-2`}
                  value={idea}
                  onChange={(e) => setIdea(e.target.value)}
                  placeholder="On-device inference runtime that cuts GPU cost for robotics stacks"
                />
              </label>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <label className="block">
                  <span className="mb-1 block text-xs font-medium text-muted-foreground">
                    Sector
                  </span>
                  <input
                    className={FIELD}
                    value={sector}
                    onChange={(e) => setSector(e.target.value)}
                    placeholder="AI infrastructure"
                  />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs font-medium text-muted-foreground">Geo</span>
                  <input
                    className={FIELD}
                    value={geo}
                    onChange={(e) => setGeo(e.target.value)}
                    placeholder="Germany"
                  />
                </label>
              </div>
              <div className="flex items-center gap-3">
                <Button size="sm" disabled={!canSubmit} onClick={submit}>
                  {isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                  Log application
                </Button>
                <span className="text-xs text-subtle">Needs at least an idea or a sector.</span>
                {isError && (
                  <span className="text-xs text-danger">Could not save. Check the backend.</span>
                )}
              </div>
            </Card>
          </motion.div>
        )}
    </AnimatePresence>
  );
}

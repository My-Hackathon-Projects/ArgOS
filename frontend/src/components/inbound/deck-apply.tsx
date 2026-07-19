"use client";

import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { FileUp, Loader2 } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useApplyInbound } from "@/api/generated/default/default";
import type { ApplyResponse } from "@/api/generated/model";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

const FIELD =
  "h-9 w-full rounded-xl bg-black/[0.04] px-3.5 text-sm text-foreground transition-colors placeholder:text-subtle hover:bg-black/[0.06] focus:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/** Deck-based intake: PDF + company name through POST /apply. The backend extracts
 *  per-page signals, mints claims, and prescreens the application. */
export function DeckApply({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [company, setCompany] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [result, setResult] = useState<ApplyResponse | null>(null);

  const { mutate, isPending, isError, error } = useApplyInbound({
    mutation: {
      onSuccess: (r) => {
        setResult(r);
        qc.invalidateQueries();
      },
    },
  });

  const submit = () => {
    const deck = fileRef.current?.files?.[0];
    if (!deck || !company.trim()) return;
    setResult(null);
    mutate({ data: { deck, company_name: company.trim() } });
  };

  const detail =
    isError && error && typeof error === "object" && "response" in error
      ? String(
          (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail ??
            "Upload failed.",
        )
      : "Upload failed.";

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
                  Company
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
                  Pitch deck (PDF)
                </span>
                <input
                  ref={fileRef}
                  type="file"
                  accept="application/pdf"
                  onChange={(e) => setFileName(e.target.files?.[0]?.name ?? null)}
                  className="block w-full cursor-pointer text-xs text-muted-foreground file:mr-3 file:cursor-pointer file:rounded-full file:border-0 file:bg-black/[0.05] file:px-4 file:py-2 file:text-xs file:font-medium file:text-foreground hover:file:bg-black/[0.08]"
                />
              </label>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Button
                size="sm"
                onClick={submit}
                disabled={isPending || !company.trim() || !fileName}
              >
                {isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <FileUp className="h-4 w-4" />
                )}
                {isPending ? "Extracting and prescreening…" : "Submit application"}
              </Button>
              <span className="text-xs text-subtle">
                Extraction and prescreen take about 10 to 20 seconds.
              </span>
              {isError && <span className="text-xs text-danger">{detail}</span>}
            </div>
            {result && (
              <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3 text-xs text-muted-foreground">
                <Badge variant={result.prescreen_verdict === "pass" ? "success" : "danger"}>
                  prescreen {result.prescreen_verdict}
                </Badge>
                <span>{result.signals_ingested} signals extracted</span>
                <span aria-hidden>·</span>
                <span>{result.claims_minted} claims minted</span>
                <span aria-hidden>·</span>
                <span className="min-w-0 flex-1">{result.prescreen_reason}</span>
                <Button size="sm" variant="secondary" onClick={onClose}>
                  Done
                </Button>
              </div>
            )}
          </Card>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

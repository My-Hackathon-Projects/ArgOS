"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { FileUp, Loader2, Mail, ShieldX } from "lucide-react";
import { useApplyInbound } from "@/api/generated/default/default";
import { Button } from "@/components/ui/button";
import { Dialog, fieldClass } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

/** Manual stand-in for the email intake: in production decks arrive at the fund's
 *  application address; here the investor drops the same attachment directly.
 *  Runs the full inbound pipeline (extract -> claims -> prescreen), ~15s. */
export function ApplyButton() {
  const router = useRouter();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [company, setCompany] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const { mutate, isPending, data, error, reset } = useApplyInbound({
    mutation: {
      onSuccess: (res) => {
        qc.invalidateQueries();
        if (res.prescreen_verdict === "pass") {
          setOpen(false);
          router.push(`/opportunities/${res.opportunity_id}`);
        }
      },
    },
  });

  const close = () => {
    setOpen(false);
    setCompany("");
    setFile(null);
    reset();
  };

  const pickFile = (f: File | undefined) => {
    if (f && f.type === "application/pdf") setFile(f);
  };

  const canSubmit = company.trim().length > 0 && file !== null && !isPending;
  const rejected = data && data.prescreen_verdict !== "pass";
  const errorDetail = (error?.response?.data as { detail?: unknown } | undefined)?.detail;

  return (
    <>
      <Button onClick={() => setOpen(true)}>
        <FileUp className="h-4 w-4" />
        Upload a deck
      </Button>
      <Dialog open={open} onClose={close} title="New application">
        <p className="mb-4 flex items-start gap-2 text-[13px] leading-relaxed text-muted-foreground">
          <Mail className="mt-0.5 h-3.5 w-3.5 shrink-0 text-subtle" />
          In production this inbox is fed by email — founders send their deck to the fund&apos;s
          application address. Drop the same attachment here to run the intake agent directly.
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (canSubmit && file) mutate({ data: { deck: file, company_name: company.trim() } });
          }}
          className="space-y-4"
        >
          <label className="block">
            <span className="mb-1.5 block text-xs font-medium text-muted-foreground">
              Company name
            </span>
            <input
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              placeholder="Acme Robotics"
              className={fieldClass}
              disabled={isPending}
              autoFocus
            />
          </label>

          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              pickFile(e.dataTransfer.files[0]);
            }}
            disabled={isPending}
            className={cn(
              "flex w-full flex-col items-center gap-1.5 rounded-xl border border-dashed px-4 py-6 text-center transition-colors",
              dragOver
                ? "border-primary bg-accent-soft"
                : "border-border-strong hover:border-primary/60 hover:bg-muted/50",
            )}
          >
            <FileUp className="h-5 w-5 text-subtle" />
            {file ? (
              <span className="text-sm font-medium text-foreground">{file.name}</span>
            ) : (
              <>
                <span className="text-sm text-foreground">Drop the pitch deck here</span>
                <span className="text-xs text-subtle">PDF only</span>
              </>
            )}
          </button>
          <input
            ref={inputRef}
            type="file"
            accept="application/pdf"
            className="hidden"
            onChange={(e) => pickFile(e.target.files?.[0])}
          />

          {rejected && (
            <div className="rounded-xl bg-rose-50 p-3.5 text-[13px] leading-relaxed text-rose-700">
              <span className="mb-1 flex items-center gap-1.5 font-semibold">
                <ShieldX className="h-4 w-4" />
                Prescreen: rejected
              </span>
              {data.prescreen_reason}
              <button
                type="button"
                onClick={() => {
                  close();
                  router.push(`/opportunities/${data.opportunity_id}`);
                }}
                className="mt-2 block font-medium underline underline-offset-2"
              >
                View the application anyway
              </button>
            </div>
          )}
          {error != null && !rejected && (
            <p className="text-[13px] text-danger">
              Intake failed{typeof errorDetail === "string" ? `: ${errorDetail}` : ""}. Is the
              deck a readable PDF?
            </p>
          )}

          <Button type="submit" disabled={!canSubmit} className="w-full">
            {isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Extracting claims + prescreening…
              </>
            ) : (
              "Run intake"
            )}
          </Button>
        </form>
      </Dialog>
    </>
  );
}

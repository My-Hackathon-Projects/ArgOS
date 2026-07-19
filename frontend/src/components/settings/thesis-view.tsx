"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Check } from "lucide-react";
import {
  getGetThesisQueryKey,
  useGetThesis,
  useUpdateThesis,
} from "@/api/generated/default/default";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

const splitList = (s: string): string[] =>
  s
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
const joinList = (a?: string[] | null): string => (a ?? []).join(", ");

function prefList(prefs: Record<string, unknown> | null, key: string): string {
  const v = prefs?.[key];
  return Array.isArray(v) ? (v as unknown[]).filter((x) => typeof x === "string").join(", ") : "";
}

const INPUT =
  "w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-foreground placeholder:text-subtle focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/30";

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid grid-cols-1 gap-1.5 border-b border-border px-5 py-4 last:border-0 sm:grid-cols-[170px_1fr] sm:gap-4 sm:px-6">
      <div className="pt-2">
        <div className="text-sm font-medium text-muted-foreground">{label}</div>
        {hint && <div className="mt-0.5 text-xs text-subtle">{hint}</div>}
      </div>
      <div>{children}</div>
    </div>
  );
}

type FormState = {
  name: string;
  industries: string;
  geo: string;
  stage: string;
  keywords: string;
  schools: string;
  traits: string;
  check_size: string;
  ownership: string;
  risk: string;
  free_text: string;
};

const EMPTY: FormState = {
  name: "",
  industries: "",
  geo: "",
  stage: "",
  keywords: "",
  schools: "",
  traits: "",
  check_size: "",
  ownership: "",
  risk: "",
  free_text: "",
};

export function ThesisView() {
  const { data, isLoading, isError } = useGetThesis();
  const qc = useQueryClient();
  const update = useUpdateThesis({
    mutation: { onSuccess: () => qc.invalidateQueries({ queryKey: getGetThesisQueryKey() }) },
  });

  const [form, setForm] = useState<FormState>(EMPTY);
  const [prefs, setPrefs] = useState<Record<string, unknown> | null>(null);
  const [saved, setSaved] = useState(false);
  const [hydratedFrom, setHydratedFrom] = useState<unknown>(null);

  // Hydrate the form from the loaded thesis (render-phase sync — resets to server values on change).
  if (data && data !== hydratedFrom) {
    setHydratedFrom(data);
    const p = (data.founder_preferences as Record<string, unknown> | null) ?? null;
    setPrefs(p);
    setForm({
      name: data.name ?? "",
      industries: joinList(data.industries),
      geo: joinList(data.geo),
      stage: joinList(data.stage),
      keywords: joinList(data.keywords),
      schools: prefList(p, "schools"),
      traits: prefList(p, "traits"),
      check_size: data.check_size != null ? String(data.check_size) : "",
      ownership: data.ownership != null ? String(data.ownership) : "",
      risk: data.risk ?? "",
      free_text: data.free_text ?? "",
    });
  }

  if (isError) {
    return <Card className="p-6 text-sm text-muted-foreground">No default thesis set.</Card>;
  }
  if (isLoading || !data) {
    return <Skeleton className="h-96 w-full rounded-2xl" />;
  }

  const set = (k: keyof FormState) => (v: string) => {
    setForm((f) => ({ ...f, [k]: v }));
    setSaved(false);
  };

  const save = () => {
    const nextPrefs = {
      ...(prefs ?? {}),
      schools: splitList(form.schools),
      traits: splitList(form.traits),
    };
    update.mutate(
      {
        data: {
          name: form.name.trim() || null,
          industries: splitList(form.industries),
          geo: splitList(form.geo),
          stage: splitList(form.stage),
          keywords: splitList(form.keywords),
          founder_preferences: nextPrefs,
          check_size: form.check_size.trim() ? Number(form.check_size) : null,
          ownership: form.ownership.trim() ? Number(form.ownership) : null,
          risk: form.risk.trim() || null,
          free_text: form.free_text.trim() || null,
        },
      },
      { onSuccess: () => setSaved(true) },
    );
  };

  const textField = (k: keyof FormState, ph: string) => (
    <input className={INPUT} value={form[k]} onChange={(e) => set(k)(e.target.value)} placeholder={ph} />
  );

  return (
    <div>
      <Card className="overflow-hidden">
        <Field label="Fund name">{textField("name", "e.g. Munich AI/robotics")}</Field>
        <Field label="Industries" hint="comma-separated">
          {textField("industries", "AI infrastructure, robotics, machine learning")}
        </Field>
        <Field label="Geography" hint="comma-separated">
          {textField("geo", "Germany, Munich, Tübingen")}
        </Field>
        <Field label="Stage" hint="comma-separated">
          {textField("stage", "pre-idea, pre-seed, seed")}
        </Field>
        <Field label="Keywords" hint="comma-separated">
          {textField("keywords", "LLM infra, autonomy, agents")}
        </Field>
        <Field label="Target schools" hint="founder profile · comma-separated">
          {textField("schools", "TUM, ETH Zurich")}
        </Field>
        <Field label="Founder traits" hint="comma-separated">
          {textField("traits", "technical, no prior VC backing")}
        </Field>
        <Field label="Check size" hint="$M">
          <input
            className={INPUT}
            type="number"
            step="0.1"
            value={form.check_size}
            onChange={(e) => set("check_size")(e.target.value)}
            placeholder="1.5"
          />
        </Field>
        <Field label="Target ownership" hint="fraction 0–1">
          <input
            className={INPUT}
            type="number"
            step="0.01"
            value={form.ownership}
            onChange={(e) => set("ownership")(e.target.value)}
            placeholder="0.1"
          />
        </Field>
        <Field label="Risk appetite">{textField("risk", "high / moderate / low")}</Field>
        <Field label="Notes">
          <textarea
            className={`${INPUT} min-h-[84px] resize-y`}
            value={form.free_text}
            onChange={(e) => set("free_text")(e.target.value)}
            placeholder="Free-text thesis notes…"
          />
        </Field>
        <div className="flex items-center gap-3 px-5 py-4 sm:px-6">
          <Button onClick={save} disabled={update.isPending}>
            {update.isPending ? "Saving…" : "Save thesis"}
          </Button>
          {saved && !update.isPending && (
            <span className="flex items-center gap-1 text-sm text-emerald-600">
              <Check className="h-4 w-4" /> Saved
            </span>
          )}
          {update.isError && (
            <span className="text-sm text-rose-600">Save failed — is the backend running?</span>
          )}
        </div>
      </Card>
      <p className="mt-3 px-1 text-xs text-subtle">
        Your thesis drives discovery, screening, and market scoring. Edits persist and apply on the
        next run.
      </p>
    </div>
  );
}

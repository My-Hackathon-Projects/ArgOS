"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Check, X } from "lucide-react";
import {
  getGetThesisQueryKey,
  useGetThesis,
  useUpdateThesis,
} from "@/api/generated/default/default";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

function prefArr(prefs: Record<string, unknown> | null, key: string): string[] {
  const v = prefs?.[key];
  return Array.isArray(v) ? (v as unknown[]).filter((x): x is string => typeof x === "string") : [];
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

/** Chip/tag multiselect: values render as removable chips; type + Enter/comma to add. */
function TagInput({
  values,
  onChange,
  placeholder,
  suggestions,
}: {
  values: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
  suggestions?: string[];
}) {
  const [draft, setDraft] = useState("");
  const add = (raw: string) => {
    const t = raw.trim();
    if (t && !values.some((v) => v.toLowerCase() === t.toLowerCase())) onChange([...values, t]);
    setDraft("");
  };
  const remove = (v: string) => onChange(values.filter((x) => x !== v));
  const openSuggestions = (suggestions ?? []).filter(
    (s) => !values.some((v) => v.toLowerCase() === s.toLowerCase()),
  );

  return (
    <div>
      <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-border bg-surface px-2 py-1.5 focus-within:border-primary focus-within:ring-1 focus-within:ring-primary/30">
        {values.map((v) => (
          <span
            key={v}
            className="inline-flex items-center gap-1 rounded-full bg-accent-soft py-0.5 pl-2.5 pr-1 text-xs font-medium text-primary"
          >
            {v}
            <button
              type="button"
              onClick={() => remove(v)}
              className="rounded-full p-0.5 text-primary/60 transition-colors hover:bg-primary/10 hover:text-primary"
              aria-label={`Remove ${v}`}
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
        <input
          className="min-w-[120px] flex-1 bg-transparent px-1 py-0.5 text-sm text-foreground placeholder:text-subtle focus:outline-none"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === ",") {
              e.preventDefault();
              add(draft);
            } else if (e.key === "Backspace" && !draft && values.length) {
              remove(values[values.length - 1]);
            }
          }}
          onBlur={() => draft && add(draft)}
          placeholder={values.length ? "" : placeholder}
        />
      </div>
      {openSuggestions.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {openSuggestions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => add(s)}
              className="rounded-full border border-border-strong px-2 py-0.5 text-xs text-muted-foreground transition-colors hover:border-primary hover:text-primary"
            >
              + {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

type FormState = {
  name: string;
  industries: string[];
  geo: string[];
  stage: string[];
  keywords: string[];
  schools: string[];
  traits: string[];
  check_size: string;
  ownership: string;
  risk: string;
  free_text: string;
};

const EMPTY: FormState = {
  name: "",
  industries: [],
  geo: [],
  stage: [],
  keywords: [],
  schools: [],
  traits: [],
  check_size: "",
  ownership: "",
  risk: "",
  free_text: "",
};

const STAGE_SUGGESTIONS = ["pre-idea", "pre-seed", "seed", "series A", "series B", "growth"];
const RISK_SUGGESTIONS = ["low", "moderate", "high"];

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
      industries: data.industries ?? [],
      geo: data.geo ?? [],
      stage: data.stage ?? [],
      keywords: data.keywords ?? [],
      schools: prefArr(p, "schools"),
      traits: prefArr(p, "traits"),
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

  const setList = (k: keyof FormState) => (v: string[]) => {
    setForm((f) => ({ ...f, [k]: v }));
    setSaved(false);
  };
  const setStr = (k: keyof FormState) => (v: string) => {
    setForm((f) => ({ ...f, [k]: v }));
    setSaved(false);
  };

  const save = () => {
    const nextPrefs = { ...(prefs ?? {}), schools: form.schools, traits: form.traits };
    update.mutate(
      {
        data: {
          name: form.name.trim() || null,
          industries: form.industries,
          geo: form.geo,
          stage: form.stage,
          keywords: form.keywords,
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

  return (
    <div>
      <Card className="overflow-hidden">
        <Field label="Fund name">
          <input
            className={INPUT}
            value={form.name}
            onChange={(e) => setStr("name")(e.target.value)}
            placeholder="e.g. Munich AI/robotics"
          />
        </Field>
        <Field label="Industries" hint="add tags — type + Enter">
          <TagInput
            values={form.industries}
            onChange={setList("industries")}
            placeholder="AI infrastructure…"
          />
        </Field>
        <Field label="Geography" hint="add tags">
          <TagInput values={form.geo} onChange={setList("geo")} placeholder="Germany, Munich…" />
        </Field>
        <Field label="Stage" hint="add tags">
          <TagInput
            values={form.stage}
            onChange={setList("stage")}
            placeholder="seed…"
            suggestions={STAGE_SUGGESTIONS}
          />
        </Field>
        <Field label="Keywords" hint="add tags">
          <TagInput
            values={form.keywords}
            onChange={setList("keywords")}
            placeholder="LLM infra, agents…"
          />
        </Field>
        <Field label="Target schools" hint="founder profile">
          <TagInput
            values={form.schools}
            onChange={setList("schools")}
            placeholder="TUM, ETH Zurich…"
          />
        </Field>
        <Field label="Founder traits">
          <TagInput
            values={form.traits}
            onChange={setList("traits")}
            placeholder="technical…"
          />
        </Field>
        <Field label="Check size" hint="$M">
          <input
            className={INPUT}
            type="number"
            step="0.1"
            value={form.check_size}
            onChange={(e) => setStr("check_size")(e.target.value)}
            placeholder="1.5"
          />
        </Field>
        <Field label="Target ownership" hint="fraction 0–1">
          <input
            className={INPUT}
            type="number"
            step="0.01"
            value={form.ownership}
            onChange={(e) => setStr("ownership")(e.target.value)}
            placeholder="0.1"
          />
        </Field>
        <Field label="Risk appetite">
          <div>
            <input
              className={INPUT}
              value={form.risk}
              onChange={(e) => setStr("risk")(e.target.value)}
              placeholder="moderate"
            />
            <div className="mt-1.5 flex flex-wrap gap-1">
              {RISK_SUGGESTIONS.map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => setStr("risk")(r)}
                  className={`rounded-full border px-2 py-0.5 text-xs transition-colors ${
                    form.risk === r
                      ? "border-primary text-primary"
                      : "border-border-strong text-muted-foreground hover:border-primary hover:text-primary"
                  }`}
                >
                  {r}
                </button>
              ))}
            </div>
          </div>
        </Field>
        <Field label="Notes">
          <textarea
            className={`${INPUT} min-h-[84px] resize-y`}
            value={form.free_text}
            onChange={(e) => setStr("free_text")(e.target.value)}
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

"use client";

import { useGetThesis } from "@/api/generated/default/default";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { humanize } from "@/lib/source-style";

function Chips({ items }: { items?: string[] | null }) {
  if (!items?.length) return <span className="text-sm text-subtle">—</span>;
  return (
    <>
      {items.map((x) => (
        <Badge key={x} variant="primary">
          {x}
        </Badge>
      ))}
    </>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-1 items-start gap-1.5 border-b border-border px-5 py-4 last:border-0 sm:grid-cols-[140px_1fr] sm:gap-4 sm:px-6">
      <div className="pt-0.5 text-sm font-medium text-muted-foreground">{label}</div>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </div>
  );
}

export function ThesisView() {
  const { data, isLoading, isError } = useGetThesis();

  if (isError) {
    return <Card className="p-6 text-sm text-muted-foreground">No default thesis set.</Card>;
  }

  if (isLoading || !data) {
    return <Skeleton className="h-72 w-full rounded-2xl" />;
  }

  const prefs = data.founder_preferences ?? {};
  const prefEntries = Object.entries(prefs).filter(
    ([, v]) => Array.isArray(v) && v.length > 0,
  ) as [string, string[]][];

  return (
    <>
      <Card>
        <div className="border-b border-border px-5 py-4 sm:px-6">
          <div className="text-xs uppercase tracking-wider text-subtle">Active thesis</div>
          <div className="mt-0.5 text-xl font-semibold tracking-tight text-foreground">
            {data.name ?? "Default thesis"}
          </div>
        </div>
        <Field label="Industries">
          <Chips items={data.industries} />
        </Field>
        <Field label="Geography">
          <Chips items={data.geo} />
        </Field>
        <Field label="Stage">
          <Chips items={data.stage} />
        </Field>
        <Field label="Keywords">
          <Chips items={data.keywords} />
        </Field>
        {prefEntries.map(([k, v]) => (
          <Field key={k} label={humanize(k)}>
            <Chips items={v} />
          </Field>
        ))}
      </Card>

      <p className="mt-3 px-1 text-xs text-subtle">
        Read-only for now — the thesis is synced from code and drives discovery. An editable form
        writes back once the <code className="text-muted-foreground">PUT /thesis</code> endpoint
        lands.
      </p>
    </>
  );
}

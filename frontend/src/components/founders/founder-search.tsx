"use client";

import { useState } from "react";
import Link from "next/link";
import { Search, Sparkles } from "lucide-react";
import { useSearchFounders } from "@/api/generated/default/default";
import type { FounderMatch } from "@/api/generated/model";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

const EXAMPLE = "technical founder, Berlin, AI infra, no prior VC backing, top-tier accelerator";

export function FounderSearch() {
  const [q, setQ] = useState("");
  const search = useSearchFounders();
  const res = search.data;

  const run = () => {
    const query = q.trim();
    if (query) search.mutate({ data: { query } });
  };

  return (
    <div className="mb-8">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          run();
        }}
        className="flex gap-2"
      >
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-subtle" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={`Ask in plain English — e.g. "${EXAMPLE}"`}
            className="h-11 w-full rounded-full border border-border-strong bg-surface pl-11 pr-4 text-sm text-foreground placeholder:text-subtle focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
        </div>
        <Button type="submit" disabled={search.isPending || !q.trim()}>
          {search.isPending ? "Searching…" : "Search"}
        </Button>
      </form>
      <p className="mt-1.5 flex items-center gap-1 text-xs text-subtle">
        <Sparkles className="h-3 w-3" />
        Multi-attribute query — one reasoning pass over every founder, not keyword filters.
      </p>

      {search.isError && (
        <Card className="mt-4 p-4 text-sm text-muted-foreground">Search failed — try again.</Card>
      )}

      {res && (
        <div className="mt-4 space-y-3">
          <div className="flex flex-wrap items-center gap-1.5 text-xs text-subtle">
            <span>Read as:</span>
            {res.criteria.map((c, i) => (
              <Badge key={i} variant="outline">
                {c}
              </Badge>
            ))}
          </div>
          {res.matches.length === 0 ? (
            <Card className="p-4 text-sm text-muted-foreground">
              No founders match all of that yet.
            </Card>
          ) : (
            res.matches.map((m: FounderMatch) => (
              <Link key={m.founder_id} href={`/founders/${m.founder_id}`} className="block">
                <Card className="p-4 transition-colors hover:border-primary">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium text-foreground">
                          {m.display_name ?? "Unknown"}
                        </span>
                        {m.current_company && (
                          <span className="text-xs text-subtle">{m.current_company}</span>
                        )}
                        {m.city && <span className="text-xs text-subtle">· {m.city}</span>}
                      </div>
                      <p className="mt-1 text-[13px] text-muted-foreground">{m.reason}</p>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {m.matched.map((c, i) => (
                          <Badge key={i} variant="success">
                            {c}
                          </Badge>
                        ))}
                      </div>
                    </div>
                    <div className="shrink-0 text-right">
                      <div className="font-serif text-xl text-foreground">
                        {m.founder_score != null ? Math.round(m.founder_score) : "—"}
                      </div>
                      <div className="text-[10px] text-subtle">
                        score · {Math.round(m.relevance * 100)}% match
                      </div>
                    </div>
                  </div>
                </Card>
              </Link>
            ))
          )}
        </div>
      )}
    </div>
  );
}

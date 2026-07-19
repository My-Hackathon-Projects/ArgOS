"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Loader2, Sparkles } from "lucide-react";
import { useDiscoveryRun } from "@/api/generated/default/default";
import { Button } from "@/components/ui/button";

export function DiscoveryButton() {
  const qc = useQueryClient();
  const { mutate, isPending } = useDiscoveryRun({
    mutation: { onSuccess: () => qc.invalidateQueries() },
  });

  return (
    <Button onClick={() => mutate()} disabled={isPending} title="Thesis → search → resolve → persist">
      {isPending ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : (
        <Sparkles className="h-4 w-4" />
      )}
      {isPending ? "Discovering…" : "Run discovery"}
    </Button>
  );
}

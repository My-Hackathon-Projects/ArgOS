import type { BadgeProps } from "@/components/ui/badge";

/** Shared founder-status → badge mapping (table + detail). */
export function statusBadge(status: string): { variant: BadgeProps["variant"]; label: string } {
  if (status === "confirmed") return { variant: "success", label: "Confirmed" };
  if (status === "needs_review") return { variant: "danger", label: "Needs review" };
  return { variant: "muted", label: "Candidate" };
}

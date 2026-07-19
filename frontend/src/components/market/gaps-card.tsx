import { AlertTriangle } from "lucide-react";
import { Card } from "@/components/ui/card";

/** Honestly flagged research gaps. A gap beats an invented number. */
export function GapsCard({ gaps }: { gaps: string[] }) {
  return (
    <Card className="p-4">
      <ul className="space-y-1.5">
        {gaps.map((g, i) => (
          <li key={i} className="flex items-start gap-2 text-xs text-muted-foreground">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
            {g}
          </li>
        ))}
      </ul>
    </Card>
  );
}

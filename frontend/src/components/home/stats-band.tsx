"use client";

import {
  useHealth,
  useListChannels,
  useListFounders,
  useListOpportunities,
} from "@/api/generated/default/default";
import { Card } from "@/components/ui/card";
import { CountUp } from "@/components/ui/count-up";

/** Live product numbers, straight from the API: proof the system is running,
 *  not a mockup. Values count up once when scrolled into view. */
export function StatsBand() {
  const { data: health } = useHealth();
  const { data: founders } = useListFounders();
  const { data: channels } = useListChannels();
  const { data: deals } = useListOpportunities();

  const stats = [
    { label: "Live signals", value: health?.signals, color: "#0071e3" },
    { label: "Founders resolved", value: founders?.length, color: "#7c3aed" },
    {
      label: "Channels watched",
      value: channels?.filter((c) => c.enabled).length,
      color: "#059669",
    },
    { label: "Deals in the loop", value: deals?.length, color: "#d97706" },
  ];

  return (
    <section aria-label="Live numbers" className="mt-14 sm:mt-16">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {stats.map(({ label, value, color }) => (
          <Card key={label} className="p-5 text-center">
            <div
              className="font-mono text-3xl font-semibold tabular-nums tracking-tight sm:text-4xl"
              style={{ color }}
            >
              {value != null ? <CountUp value={value} duration={1.2} /> : "—"}
            </div>
            <div className="mt-1 text-xs font-medium uppercase tracking-wider text-subtle">
              {label}
            </div>
          </Card>
        ))}
      </div>
    </section>
  );
}

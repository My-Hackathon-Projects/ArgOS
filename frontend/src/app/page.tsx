import Link from "next/link";
import { LineChart, Radar, Scale, ShieldCheck } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Container } from "@/components/ui/container";
import { ConvergenceHero } from "@/components/home/convergence-hero";
import { TeamSection } from "@/components/home/team-section";

const PIPELINE = [
  {
    icon: Radar,
    title: "Sourcing",
    href: "/sourcing",
    color: "#0071e3",
    soft: "rgba(0,113,227,0.08)",
    text: "Thirteen public channels, from arXiv to GitHub to Devpost, are watched continuously and every raw signal is resolved to a real person.",
  },
  {
    icon: ShieldCheck,
    title: "Screening",
    href: "/founders",
    color: "#7c3aed",
    soft: "rgba(124,58,237,0.08)",
    text: "Noisy signals collapse into corroborated claims. Trust and Founder Scores stay deterministic formulas, so every number can be audited.",
  },
  {
    icon: LineChart,
    title: "Diligence",
    href: "/opportunities",
    color: "#059669",
    soft: "rgba(5,150,105,0.08)",
    text: "A market research agent sizes TAM, SAM and SOM, maps competitors and comparable rounds, and flags gaps instead of inventing figures.",
  },
  {
    icon: Scale,
    title: "Decision",
    href: "/opportunities",
    color: "#d97706",
    soft: "rgba(217,119,6,0.09)",
    text: "A three axis screen across founder, market and idea feeds the investment memo and the final call.",
  },
];

export default function HomePage() {
  return (
    <Container>
      {/* Hero with the signal-convergence intro animation */}
      <ConvergenceHero />

      {/* What we do */}
      <section aria-label="What we do" className="mt-14 sm:mt-20">
        <h2 className="mb-5 text-center text-sm font-semibold uppercase tracking-[0.14em] text-subtle">
          One funnel, four stages
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {PIPELINE.map(({ icon: Icon, title, href, color, soft, text }) => (
            <Link key={title} href={href} className="block">
              <Card className="card-shadow-hover relative h-full overflow-hidden p-5 transition-shadow duration-300">
                <span className="absolute inset-x-0 top-0 h-1" style={{ background: color }} aria-hidden />
                <span
                  className="flex h-10 w-10 items-center justify-center rounded-xl"
                  style={{ background: soft, color }}
                >
                  <Icon className="h-5 w-5" />
                </span>
                <h3 className="mt-4 text-base font-semibold text-foreground">{title}</h3>
                <p className="mt-1.5 text-[13px] leading-relaxed text-muted-foreground">{text}</p>
              </Card>
            </Link>
          ))}
        </div>
      </section>

      <TeamSection />
    </Container>
  );
}

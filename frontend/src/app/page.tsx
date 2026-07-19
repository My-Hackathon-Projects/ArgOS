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
    text: "Thirteen public channels, from arXiv to GitHub to Devpost, are watched continuously and every raw signal is resolved to a real person.",
  },
  {
    icon: ShieldCheck,
    title: "Screening",
    href: "/founders",
    text: "Noisy signals collapse into corroborated claims. Trust and Founder Scores stay deterministic formulas, so every number can be audited.",
  },
  {
    icon: LineChart,
    title: "Diligence",
    href: "/research",
    text: "A market research agent sizes TAM, SAM and SOM, maps competitors and comparable rounds, and flags gaps instead of inventing figures.",
  },
  {
    icon: Scale,
    title: "Decision",
    href: null,
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
          {PIPELINE.map(({ icon: Icon, title, href, text }) => {
            const body = (
              <>
                <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent-soft text-primary">
                  <Icon className="h-5 w-5" />
                </span>
                <h3 className="mt-4 text-base font-semibold text-foreground">{title}</h3>
                <p className="mt-1.5 text-[13px] leading-relaxed text-muted-foreground">{text}</p>
              </>
            );
            return href ? (
              <Link key={title} href={href} className="block">
                <Card className="card-shadow-hover h-full p-5 transition-shadow duration-300">
                  {body}
                </Card>
              </Link>
            ) : (
              <Card key={title} className="h-full p-5">
                {body}
              </Card>
            );
          })}
        </div>
      </section>

      <TeamSection />
    </Container>
  );
}

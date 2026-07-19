import { Mail } from "lucide-react";
import { Card } from "@/components/ui/card";
import { initials } from "@/lib/format";

const TEAM = [
  { name: "Rishabh Tiwari", email: "rishtiwari98@gmail.com" },
  { name: "Alexandre Boving", email: "alexandre.boving@gmail.com" },
  { name: "Florian Sprick", email: "floriansprick@hotmail.com" },
];

/** About Us: who built VC Brain. Anchored so the footer and hero can link to it. */
export function TeamSection() {
  return (
    <section id="about" aria-label="About us" className="mt-14 scroll-mt-20 sm:mt-20">
      <h2 className="mb-1 text-center text-sm font-semibold uppercase tracking-[0.14em] text-subtle">
        About us
      </h2>
      <p className="mx-auto mb-6 max-w-xl text-center text-sm leading-relaxed text-muted-foreground">
        We are the team behind VC Brain, built for Challenge 02 of the Maschmeyer Group and
        Hack-Nation hackathon.
      </p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {TEAM.map(({ name, email }) => (
          <Card key={email} className="card-shadow-hover p-5 text-center transition-shadow duration-300">
            <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-muted text-sm font-semibold text-muted-foreground">
              {initials(name)}
            </span>
            <div className="mt-3 text-sm font-semibold text-foreground">{name}</div>
            <a
              href={`mailto:${email}`}
              className="mt-1 inline-flex items-center gap-1.5 break-all text-xs text-muted-foreground transition-colors hover:text-primary"
            >
              <Mail className="h-3 w-3 shrink-0" />
              {email}
            </a>
          </Card>
        ))}
      </div>
    </section>
  );
}

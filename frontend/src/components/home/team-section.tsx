import Image from "next/image";
import { Mail, User } from "lucide-react";
import { Card } from "@/components/ui/card";

const TEAM = [
  {
    name: "Rishabh Tiwari",
    email: "rishtiwari98@gmail.com",
    linkedin: "https://www.linkedin.com/in/icon1c/",
    photo: "/images/rishabh-tiwari.jpeg",
  },
  {
    name: "Alexandre Boving",
    email: "alexandre.boving@gmail.com",
    linkedin: "https://www.linkedin.com/in/alexandre-boving-04422a1b6/",
    photo: null,
  },
  {
    name: "Florian Sprick",
    email: "floriansprick@hotmail.com",
    linkedin: "https://www.linkedin.com/in/florian-sprick/",
    photo: null,
  },
];

function Avatar({ photo, name }: { photo: string | null; name: string }) {
  if (photo) {
    return (
      <Image
        src={photo}
        alt={name}
        width={128}
        height={128}
        className="mx-auto h-16 w-16 rounded-full object-cover ring-1 ring-black/5"
      />
    );
  }
  // Photo placeholder until the teammate drops their picture into public/images.
  return (
    <span className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-muted ring-1 ring-black/5">
      <User className="h-7 w-7 text-subtle" aria-hidden />
    </span>
  );
}

/** About Us: who built VC Brain. Anchored so the footer and hero can link to it. */
export function TeamSection() {
  return (
    <section id="about" aria-label="About us" className="mt-14 scroll-mt-20 sm:mt-20">
      <h2 className="mb-1 text-center text-sm font-semibold uppercase tracking-[0.14em] text-subtle">
        About us
      </h2>
      <p className="mx-auto mb-6 max-w-xl text-center text-sm leading-relaxed text-muted-foreground">
        Three founding engineers from diverse backgrounds, building the brain a modern venture
        fund runs on.
      </p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {TEAM.map(({ name, email, linkedin, photo }) => (
          <Card
            key={email}
            className="card-shadow-hover p-5 text-center transition-shadow duration-300"
          >
            <Avatar photo={photo} name={name} />
            <div className="mt-3 flex items-center justify-center gap-1.5">
              <span className="text-sm font-semibold text-foreground">{name}</span>
              <a
                href={linkedin}
                target="_blank"
                rel="noreferrer"
                aria-label={`${name} on LinkedIn`}
                className="transition-opacity hover:opacity-80"
              >
                <span className="flex h-4 w-4 items-center justify-center rounded-[3px] bg-[#0a66c2] text-[9px] font-bold leading-none text-white">
                  in
                </span>
              </a>
            </div>
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

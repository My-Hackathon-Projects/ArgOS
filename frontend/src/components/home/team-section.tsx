import Image from "next/image";
import { Mail } from "lucide-react";
import { Card } from "@/components/ui/card";

const TEAM = [
  {
    name: "Rishabh Tiwari",
    role: "Co-Founder",
    email: "rishtiwari98@gmail.com",
    linkedin: "https://www.linkedin.com/in/icon1c/",
    photo: "/images/rishabh-tiwari.jpeg",
    bio: "Software developer and applied AI researcher with experience across Amazon, Porsche, and SAP. He builds the resilient software architecture that helps ArgOS scale.",
    chips: ["SAP", "Porsche", "Amazon"],
  },
  {
    name: "Alexandre Boving",
    role: "Co-Founder",
    email: "alexandre.boving@gmail.com",
    linkedin: "https://www.linkedin.com/in/alexandre-boving-04422a1b6/",
    photo: "/images/alexandre-boving.png",
    bio: "Co-founding engineer building ArgOS's autonomous funnel, from raw public signals through to the investment decision.",
    chips: [],
  },
  {
    name: "Florian Sprick",
    role: "Co-Founder",
    email: "floriansprick@hotmail.com",
    linkedin: "https://www.linkedin.com/in/florian-sprick/",
    photo: "/images/florian-sprick.jpeg",
    bio: "Machine learning researcher with experience across ZEISS, Fraunhofer, and AI Center Tübingen. He builds the agent harness that helps ArgOS identify high-potential founders.",
    chips: ["AI Center Tübingen", "Zeiss", "Fraunhofer"],
  },
];

function Avatar({ photo, name }: { photo: string | null; name: string }) {
  if (photo) {
    return (
      <Image
        src={photo}
        alt={name}
        width={112}
        height={112}
        className="h-14 w-14 shrink-0 rounded-full object-cover ring-1 ring-black/[0.06]"
      />
    );
  }
  // Initials placeholder until the teammate drops their picture into public/images.
  const initials = name
    .split(" ")
    .map((part) => part[0])
    .join("");
  return (
    <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-muted text-sm font-semibold tracking-wide text-subtle ring-1 ring-black/[0.06]">
      {initials}
    </span>
  );
}

/** Team: who built ArgOS. Anchored so the footer and hero can link to it. */
export function TeamSection() {
  return (
    <section id="about" aria-label="Team" className="mt-16 scroll-mt-20 sm:mt-24">
      <p className="font-mono text-xs font-medium uppercase tracking-[0.28em] text-subtle">
        Team
      </p>
      <h2 className="mt-3 max-w-xl text-3xl font-semibold leading-[1.12] tracking-tight text-foreground sm:text-4xl">
        Built by people who believe in what&apos;s possible.
      </h2>
      <div className="mt-8 grid grid-cols-1 gap-4 md:grid-cols-3 sm:mt-10">
        {TEAM.map(({ name, role, email, linkedin, photo, bio, chips }) => (
          <Card
            key={email}
            className="card-shadow-hover flex flex-col p-6 transition-shadow duration-300"
          >
            <div className="flex items-center gap-4">
              <Avatar photo={photo} name={name} />
              <div className="min-w-0">
                <h3 className="text-base font-semibold text-foreground">{name}</h3>
                <div className="mt-0.5 flex items-center gap-2">
                  <span className="font-mono text-xs tracking-wide text-subtle">{role}</span>
                  <a
                    href={linkedin}
                    target="_blank"
                    rel="noreferrer"
                    aria-label={`${name} on LinkedIn`}
                    className="transition-opacity hover:opacity-70"
                  >
                    <span className="flex h-3.5 w-3.5 items-center justify-center rounded-[3px] bg-[#0a66c2] text-[8px] font-bold leading-none text-white">
                      in
                    </span>
                  </a>
                  <a
                    href={`mailto:${email}`}
                    aria-label={`Email ${name}`}
                    className="text-subtle transition-colors hover:text-primary"
                  >
                    <Mail className="h-3.5 w-3.5" />
                  </a>
                </div>
              </div>
            </div>
            <p className="mt-4 text-sm leading-relaxed text-muted-foreground">{bio}</p>
            {chips.length > 0 && (
              <div className="mt-auto flex flex-wrap gap-2 pt-4">
                {chips.map((chip) => (
                  <span
                    key={chip}
                    className="rounded-full bg-muted px-3 py-1 text-xs font-medium text-muted-foreground"
                  >
                    {chip}
                  </span>
                ))}
              </div>
            )}
          </Card>
        ))}
      </div>
    </section>
  );
}

// Maps a signal source / channel type to a gradient orb + label. One place to restyle.

const GRADIENTS: Record<string, string> = {
  github: "linear-gradient(135deg,#8b5cf6,#ec4899)",
  code: "linear-gradient(135deg,#8b5cf6,#ec4899)",
  arxiv: "linear-gradient(135deg,#f59e0b,#f97316)",
  paper: "linear-gradient(135deg,#f59e0b,#f97316)",
  producthunt: "linear-gradient(135deg,#fb7185,#f43f5e)",
  launch: "linear-gradient(135deg,#fb7185,#f43f5e)",
  hackathon: "linear-gradient(135deg,#38bdf8,#6366f1)",
  devpost: "linear-gradient(135deg,#38bdf8,#6366f1)",
  linkedin: "linear-gradient(135deg,#0ea5e9,#2563eb)",
  social: "linear-gradient(135deg,#22d3ee,#3b82f6)",
  twitter: "linear-gradient(135deg,#22d3ee,#3b82f6)",
  web: "linear-gradient(135deg,#34d399,#10b981)",
  company: "linear-gradient(135deg,#64748b,#334155)",
  patent: "linear-gradient(135deg,#f472b6,#a855f7)",
  accelerator: "linear-gradient(135deg,#fbbf24,#fb923c)",
  club: "linear-gradient(135deg,#a3e635,#22c55e)",
  default: "linear-gradient(135deg,#a1a1aa,#71717a)",
};

export function sourceGradient(key: string | null | undefined): string {
  if (!key) return GRADIENTS.default;
  return GRADIENTS[key.toLowerCase()] ?? GRADIENTS.default;
}

// Flat endpoint colors of the gradients above, for canvas drawing (home hero particles).
export const SOURCE_COLORS = [
  "#8b5cf6", "#ec4899", "#f59e0b", "#f97316", "#fb7185", "#38bdf8", "#6366f1",
  "#0ea5e9", "#2563eb", "#22d3ee", "#3b82f6", "#34d399", "#10b981", "#f472b6",
  "#a855f7", "#fbbf24", "#fb923c", "#a3e635", "#22c55e",
];

// Humanize a signal_type like "research_profile" -> "Research profile".
export function humanize(s: string | null | undefined): string {
  if (!s) return "";
  const t = s.replace(/[_-]+/g, " ").trim();
  return t.charAt(0).toUpperCase() + t.slice(1);
}

// Channel names look like "arXiv — research-paper authors"; split into title + subtitle.
export function splitChannelName(name: string): { title: string; subtitle: string } {
  const parts = name.split(/\s+[—–-]\s+/);
  if (parts.length > 1) {
    return { title: parts[0].trim(), subtitle: parts.slice(1).join(" · ").trim() };
  }
  return { title: name, subtitle: "" };
}

type ChannelLogoInput = {
  name: string;
  type: string | null;
  domain: string | null;
};

type ChannelLogo = {
  src: string | null;
  label: string;
  fallback: string;
};

const CHANNEL_LOGOS: Array<{ match: string[]; domain: string; label: string }> = [
  { match: ["github"], domain: "github.com", label: "GitHub" },
  { match: ["arxiv"], domain: "arxiv.org", label: "arXiv" },
  {
    match: ["google patents", "patents.google.com"],
    domain: "patents.google.com",
    label: "Google Patents",
  },
  { match: ["product hunt", "producthunt"], domain: "producthunt.com", label: "Product Hunt" },
  {
    match: ["hacker news", "news.ycombinator"],
    domain: "news.ycombinator.com",
    label: "Hacker News",
  },
  { match: ["devpost"], domain: "devpost.com", label: "Devpost" },
  { match: ["major league hacking", "mlh"], domain: "mlh.io", label: "Major League Hacking" },
  { match: ["crunchbase"], domain: "crunchbase.com", label: "Crunchbase" },
  { match: ["linkedin"], domain: "linkedin.com", label: "LinkedIn" },
  { match: ["x / twitter", "twitter"], domain: "x.com", label: "X" },
  {
    match: ["accelerator", "incubator"],
    domain: "ycombinator.com",
    label: "Accelerator cohorts",
  },
  {
    match: ["student clubs", "university labs"],
    domain: "tum-ai.com",
    label: "AI student clubs",
  },
];

function faviconUrl(domain: string): string {
  return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=64`;
}

export function channelLogo(channel: ChannelLogoInput): ChannelLogo {
  const { title } = splitChannelName(channel.name);
  const haystack = `${channel.name} ${channel.type ?? ""} ${channel.domain ?? ""}`.toLowerCase();
  const mapped = CHANNEL_LOGOS.find((logo) =>
    logo.match.some((candidate) => haystack.includes(candidate)),
  );
  const domain = channel.domain ?? mapped?.domain ?? null;
  const label = mapped?.label ?? title;

  return {
    src: domain ? faviconUrl(domain) : null,
    label,
    fallback: label.trim().charAt(0).toUpperCase() || "?",
  };
}

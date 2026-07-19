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
    return { title: parts[0].trim(), subtitle: parts.slice(1).join(" — ").trim() };
  }
  return { title: name, subtitle: "" };
}

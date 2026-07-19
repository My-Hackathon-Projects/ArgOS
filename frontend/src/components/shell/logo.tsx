/** The ArgOS mark: a bold A monogram, crossbar carrying the signal gradient.
 *  Inline SVG so it stays crisp at any size with zero network cost.
 *  Canonical file lives at docs/images/argos-logo.svg — keep them identical. */
export function ArgosLogo({ className = "h-7 w-7" }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" className={className} aria-hidden>
      <defs>
        <linearGradient id="argos-bar" x1="24" y1="37.5" x2="40" y2="37.5" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#0071e3" />
          <stop offset="1" stopColor="#7c3aed" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="15" fill="#1c1b18" />
      <path
        d="M19 48 L32 15 L45 48"
        stroke="#ffffff" strokeWidth="6.5" strokeLinecap="round" strokeLinejoin="round"
      />
      <path d="M24.8 37.5 L39.2 37.5" stroke="url(#argos-bar)" strokeWidth="6.5" strokeLinecap="round" />
    </svg>
  );
}

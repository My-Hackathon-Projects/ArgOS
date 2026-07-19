"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { SOURCE_COLORS } from "@/lib/source-style";

const RUN_MS = 4200; // total particle run before the canvas fades out

type Particle = {
  startX: number;
  startY: number;
  color: string;
  size: number;
  delay: number; // ms
  duration: number; // ms
  arc: number; // perpendicular curve amplitude
};

function easeInOutCubic(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

/** Signals converging: source-colored particles fly in from the edges and collapse
 *  into the center of the hero while the copy fades in. Plays once per mount,
 *  then the canvas fades away. Skipped entirely under prefers-reduced-motion. */
export function ConvergenceHero() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const reduced = useReducedMotion();
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (reduced) return;
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const parent = canvas.parentElement as HTMLElement;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let w = 0;
    let h = 0;

    const resize = () => {
      const rect = parent.getBoundingClientRect();
      w = rect.width;
      h = rect.height;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener("resize", resize);

    const count = w < 640 ? 48 : 90;
    const particles: Particle[] = Array.from({ length: count }, () => {
      const angle = Math.random() * Math.PI * 2;
      const radius = Math.max(w, h) * (0.55 + Math.random() * 0.5);
      return {
        startX: w / 2 + Math.cos(angle) * radius,
        startY: h / 2 + Math.sin(angle) * radius * 0.7,
        color: SOURCE_COLORS[Math.floor(Math.random() * SOURCE_COLORS.length)],
        size: 1.6 + Math.random() * 2.6,
        delay: Math.random() * 1100,
        duration: 1500 + Math.random() * 1300,
        arc: (Math.random() - 0.5) * Math.min(w, h) * 0.5,
      };
    });

    let raf = 0;
    const t0 = performance.now();

    const frame = (now: number) => {
      const elapsed = now - t0;
      ctx.clearRect(0, 0, w, h);
      const cx = w / 2;
      const cy = h / 2;

      for (const p of particles) {
        const t = Math.min(Math.max((elapsed - p.delay) / p.duration, 0), 1);
        if (t <= 0) continue;
        const e = easeInOutCubic(t);
        // Straight path to center plus a perpendicular sine bow for a comet-like arc.
        const x = p.startX + (cx - p.startX) * e;
        const y = p.startY + (cy - p.startY) * e;
        const dx = cx - p.startX;
        const dy = cy - p.startY;
        const len = Math.hypot(dx, dy) || 1;
        const bowX = (-dy / len) * Math.sin(e * Math.PI) * p.arc;
        const bowY = (dx / len) * Math.sin(e * Math.PI) * p.arc;
        // Fade in quickly, fade out as it arrives.
        const alpha = t < 0.15 ? t / 0.15 : t > 0.82 ? Math.max(1 - (t - 0.82) / 0.18, 0) : 1;

        ctx.globalAlpha = alpha * 0.9;
        ctx.fillStyle = p.color;
        ctx.shadowColor = p.color;
        ctx.shadowBlur = 8;
        ctx.beginPath();
        ctx.arc(x + bowX, y + bowY, p.size * (1 - e * 0.55), 0, Math.PI * 2);
        ctx.fill();
      }

      // Soft pulse rings once the swarm starts landing.
      if (elapsed > 2100) {
        const pt = Math.min((elapsed - 2100) / 1600, 1);
        ctx.globalAlpha = (1 - pt) * 0.35;
        ctx.shadowBlur = 0;
        ctx.strokeStyle = "#0071e3";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(cx, cy, 14 + pt * Math.min(w, h) * 0.32, 0, Math.PI * 2);
        ctx.stroke();
      }

      ctx.globalAlpha = 1;
      if (elapsed < RUN_MS) {
        raf = requestAnimationFrame(frame);
      } else {
        setDone(true);
      }
    };
    raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, [reduced]);

  // Copy fades in while the swarm is still flying; instant under reduced motion.
  const appear = (delay: number) =>
    reduced
      ? {}
      : {
          initial: { opacity: 0, y: 12 },
          animate: { opacity: 1, y: 0 },
          transition: { delay, duration: 0.6, ease: [0.25, 0.1, 0.25, 1] as const },
        };

  return (
    <div className="relative">
      {!reduced && (
        <canvas
          ref={canvasRef}
          aria-hidden
          // Explicit CSS size: the width/height ATTRIBUTES hold the HiDPI bitmap size
          // (css * dpr); without CSS sizing the canvas would render at bitmap width and
          // overflow the page horizontally on retina screens.
          className={`pointer-events-none absolute inset-0 h-full w-full transition-opacity duration-700 ${done ? "opacity-0" : "opacity-100"}`}
        />
      )}
      <div className="relative mx-auto flex max-w-2xl flex-col items-center pt-6 text-center sm:pt-12">
        <motion.div
          {...appear(0.5)}
          className="mb-2 text-xs font-semibold tracking-[0.14em] text-primary"
        >
          ArgOS
        </motion.div>
        <motion.h1
          {...appear(0.8)}
          className="font-display text-4xl font-semibold tracking-tight text-foreground sm:text-6xl"
        >
          An operating system for <span className="text-gradient">venture sourcing</span>
        </motion.h1>
        <motion.p
          {...appear(1.1)}
          className="mt-4 max-w-xl text-[15px] leading-relaxed text-muted-foreground sm:text-base"
        >
          ArgOS watches the open web for founders before they appear in any startup database,
          then turns noisy signals into scored, evidence backed investment decisions.
        </motion.p>
        <motion.div
          {...appear(1.4)}
          className="mt-6 flex flex-wrap items-center justify-center gap-3"
        >
          <Link
            href="/sourcing"
            className="inline-flex h-11 items-center gap-2 rounded-full bg-primary px-6 text-sm font-medium text-primary-foreground transition-all duration-200 hover:bg-primary-hover active:scale-[0.97]"
          >
            Open the app
            <ArrowRight className="h-4 w-4" />
          </Link>
          <a
            href="#about"
            className="inline-flex h-11 items-center rounded-full bg-black/[0.05] px-6 text-sm font-medium text-foreground transition-all duration-200 hover:bg-black/[0.08] active:scale-[0.97]"
          >
            Meet the team
          </a>
        </motion.div>
      </div>
    </div>
  );
}

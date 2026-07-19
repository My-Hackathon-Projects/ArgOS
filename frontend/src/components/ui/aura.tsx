"use client";

import { useEffect, useRef } from "react";
import { useReducedMotion } from "motion/react";

export type AuraMotif = "rings" | "constellation" | "drift" | "orbits";

type Node = { bx: number; by: number; amp: number; speed: number; phase: number };
type Orb = { x: number; y: number; r: number; speed: number; wobble: number; phase: number };

/** Ambient canvas behind a page header. Each section gets its own motif and accent
 *  so pages read as places, not forms: radar rings (sourcing), drifting orbs
 *  (inbound/thesis), a constellation of people (founders), three-axis orbits
 *  (decisions). Low alpha, masked to fade out, static frame under reduced motion. */
export function Aura({
  motif,
  colors,
  className = "",
}: {
  motif: AuraMotif;
  colors: string[];
  className?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const reduced = useReducedMotion();

  useEffect(() => {
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

    // Seed the moving parts once so resize does not reshuffle the scene.
    const nodes: Node[] = Array.from({ length: 26 }, () => ({
      bx: Math.random(),
      by: Math.random(),
      amp: 8 + Math.random() * 18,
      speed: 0.15 + Math.random() * 0.3,
      phase: Math.random() * Math.PI * 2,
    }));
    const orbs: Orb[] = Array.from({ length: 14 }, () => ({
      x: Math.random(),
      y: Math.random(),
      r: 22 + Math.random() * 34,
      speed: 5 + Math.random() * 9,
      wobble: 10 + Math.random() * 24,
      phase: Math.random() * Math.PI * 2,
    }));

    const drawRings = (t: number) => {
      const cx = w / 2;
      const cy = h * 0.42;
      const maxR = Math.min(w * 0.42, h * 1.4);
      for (let i = 0; i < 4; i++) {
        const p = (t * 0.16 + i / 4) % 1;
        ctx.globalAlpha = (1 - p) * 0.26;
        ctx.strokeStyle = colors[0];
        ctx.lineWidth = 1.25;
        ctx.beginPath();
        ctx.arc(cx, cy, 12 + p * maxR, 0, Math.PI * 2);
        ctx.stroke();
      }
      // Radar sweep line.
      const a = t * 0.7;
      const grad = ctx.createLinearGradient(cx, cy, cx + Math.cos(a) * maxR, cy + Math.sin(a) * maxR);
      grad.addColorStop(0, colors[0]);
      grad.addColorStop(1, "transparent");
      ctx.globalAlpha = 0.3;
      ctx.strokeStyle = grad;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + Math.cos(a) * maxR, cy + Math.sin(a) * maxR);
      ctx.stroke();
    };

    const nodePos = (n: Node, t: number) => ({
      x: n.bx * w + Math.sin(t * n.speed + n.phase) * n.amp,
      y: n.by * h + Math.cos(t * n.speed * 0.8 + n.phase) * n.amp,
    });

    const drawConstellation = (t: number) => {
      const pts = nodes.map((n) => nodePos(n, t));
      const linkDist = Math.min(w, 900) * 0.11;
      for (let i = 0; i < pts.length; i++) {
        for (let j = i + 1; j < pts.length; j++) {
          const d = Math.hypot(pts[i].x - pts[j].x, pts[i].y - pts[j].y);
          if (d < linkDist) {
            ctx.globalAlpha = (1 - d / linkDist) * 0.22;
            ctx.strokeStyle = colors[0];
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(pts[i].x, pts[i].y);
            ctx.lineTo(pts[j].x, pts[j].y);
            ctx.stroke();
          }
        }
      }
      for (const p of pts) {
        ctx.globalAlpha = 0.5;
        ctx.fillStyle = colors[0];
        ctx.beginPath();
        ctx.arc(p.x, p.y, 1.8, 0, Math.PI * 2);
        ctx.fill();
      }
    };

    const drawDrift = (t: number) => {
      for (const o of orbs) {
        const y = ((o.y * h - t * o.speed) % (h + o.r * 2)) + (h + o.r * 2);
        const yy = (y % (h + o.r * 2)) - o.r;
        const x = o.x * w + Math.sin(t * 0.4 + o.phase) * o.wobble;
        ctx.globalAlpha = 0.12;
        ctx.fillStyle = colors[0];
        ctx.shadowColor = colors[0];
        ctx.shadowBlur = 26;
        ctx.beginPath();
        ctx.arc(x, yy, o.r, 0, Math.PI * 2);
        ctx.fill();
        ctx.shadowBlur = 0;
      }
    };

    const drawOrbits = (t: number) => {
      const cx = w / 2;
      const cy = h * 0.48;
      const base = Math.min(w * 0.3, 280);
      const tilts = [-0.32, 0.12, 0.5];
      const scales = [0.68, 0.88, 1.08];
      for (let i = 0; i < 3; i++) {
        const color = colors[i % colors.length];
        const rx = base * scales[i];
        const ry = rx * 0.32;
        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate(tilts[i]);
        ctx.globalAlpha = 0.2;
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.25;
        ctx.beginPath();
        ctx.ellipse(0, 0, rx, ry, 0, 0, Math.PI * 2);
        ctx.stroke();
        // The satellite riding this orbit.
        const a = t * (0.5 + i * 0.17) + i * 2;
        ctx.globalAlpha = 0.75;
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(Math.cos(a) * rx, Math.sin(a) * ry, 3, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      }
    };

    const draw = (t: number) => {
      ctx.clearRect(0, 0, w, h);
      if (motif === "rings") drawRings(t);
      else if (motif === "constellation") drawConstellation(t);
      else if (motif === "orbits") drawOrbits(t);
      else drawDrift(t);
      ctx.globalAlpha = 1;
    };

    if (reduced) {
      draw(1.7); // one calm, static frame
      return () => window.removeEventListener("resize", resize);
    }

    let raf = 0;
    const t0 = performance.now();
    const frame = (now: number) => {
      draw((now - t0) / 1000);
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, [motif, colors, reduced]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      className={`pointer-events-none h-full w-full ${className}`}
      style={{
        maskImage: "linear-gradient(180deg, #000 0%, #000 55%, transparent 100%)",
        WebkitMaskImage: "linear-gradient(180deg, #000 0%, #000 55%, transparent 100%)",
      }}
    />
  );
}

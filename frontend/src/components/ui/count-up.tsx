"use client";

import { useEffect, useRef } from "react";
import { animate, useInView, useReducedMotion } from "motion/react";

/** Animated integer that counts up once when it scrolls into view.
 *  Writes to textContent directly (no re-renders); reduced motion jumps straight
 *  to the final value. Used for scores — pair with font-mono tabular-nums so
 *  digits don't jitter horizontally while counting. */
export function CountUp({
  value,
  duration = 0.9,
  className,
}: {
  value: number;
  duration?: number;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    const el = ref.current;
    if (!el || !inView) return;
    if (reduceMotion) {
      el.textContent = String(Math.round(value));
      return;
    }
    const controls = animate(0, value, {
      duration,
      ease: [0.23, 1, 0.32, 1],
      onUpdate: (v) => {
        el.textContent = String(Math.round(v));
      },
    });
    return () => controls.stop();
  }, [inView, value, duration, reduceMotion]);

  return (
    <span ref={ref} className={className}>
      0
    </span>
  );
}

"use client";

import { motion, useReducedMotion } from "motion/react";

/** Titled block that softly fades up as it scrolls into view. */
export function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const reduced = useReducedMotion();
  return (
    <motion.section
      initial={reduced ? false : { opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.5, ease: [0.25, 0.1, 0.25, 1] }}
      className="mt-10"
    >
      <h3 className="mb-3 text-sm font-semibold text-foreground">{title}</h3>
      {children}
    </motion.section>
  );
}

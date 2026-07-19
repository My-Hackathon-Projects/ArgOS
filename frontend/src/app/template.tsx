"use client";

import { motion, useReducedMotion } from "motion/react";

/** Remounts on every navigation (Next.js template convention), giving each
 *  page a soft fade-and-rise entrance. */
export default function Template({ children }: { children: React.ReactNode }) {
  const reduced = useReducedMotion();

  return (
    <motion.div
      initial={reduced ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: [0.25, 0.1, 0.25, 1] }}
    >
      {children}
    </motion.div>
  );
}

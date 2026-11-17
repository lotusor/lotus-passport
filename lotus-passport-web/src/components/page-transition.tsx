'use client';

import { AnimatePresence, motion } from 'framer-motion';
import { usePathname } from 'next/navigation';
import { useEffect, type ReactNode } from 'react';
import { useT } from './providers';

export function PageTransition({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const transition = useT({ duration: 0.32, ease: [0.22, 1, 0.36, 1] });

  useEffect(() => {
    const t = window.setTimeout(() => {
      const h1 = document.querySelector<HTMLElement>('main h1');
      h1?.focus({ preventScroll: true });
    }, 340);
    return () => window.clearTimeout(t);
  }, [pathname]);

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={pathname}
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -10 }}
        transition={transition}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}
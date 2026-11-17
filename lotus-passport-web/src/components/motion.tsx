'use client';

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import type { Transition } from 'framer-motion';

const InstantContext = createContext(false);

export function useInstant(): boolean {
  return useContext(InstantContext);
}

/** 隐藏标签页 / reduced-motion 下所有转场零时长，保证 exit 收敛、内容可达 */
export function useT(t: Transition): Transition {
  const instant = useInstant();
  return instant ? { duration: 0 } : t;
}

export function MotionEnv({ children }: { children: ReactNode }) {
  const [instant, setInstant] = useState(
    () =>
      typeof document !== 'undefined' &&
      (document.visibilityState === 'hidden' || window.matchMedia('(prefers-reduced-motion: reduce)').matches),
  );

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setInstant(document.visibilityState === 'hidden' || mq.matches);
    document.addEventListener('visibilitychange', update);
    mq.addEventListener('change', update);
    return () => {
      document.removeEventListener('visibilitychange', update);
      mq.removeEventListener('change', update);
    };
  }, []);

  return <InstantContext.Provider value={instant}>{children}</InstantContext.Provider>;
}
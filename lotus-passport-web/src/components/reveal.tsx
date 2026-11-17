'use client';

import { useEffect, useRef, useState, type ReactNode } from 'react';

interface RevealProps {
  children: ReactNode;
  delay?: number;
  className?: string;
}

export function Reveal({ children, delay = 0, className = '' }: RevealProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    // 隐藏标签页 / 零尺寸视口下 IO 永不触发：直接呈现，保证内容可达
    const degraded =
      !('IntersectionObserver' in window) ||
      document.visibilityState === 'hidden' ||
      window.innerWidth === 0 ||
      window.innerHeight === 0;
    if (degraded) {
      setInView(true);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setInView(true);
            io.disconnect();
          }
        });
      },
      { threshold: 0.12 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={`reveal ${inView ? 'is-in' : ''} ${className}`}
      style={{ ['--d' as string]: `${delay}ms` }}
    >
      {children}
    </div>
  );
}
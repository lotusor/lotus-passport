'use client';

import { useEffect, useState, type ReactNode } from 'react';
import { IconTerminal } from './icons';

const SPIN_CHARS = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];

export function TermLoad({ label }: { label: string }) {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => setI((v) => (v + 1) % SPIN_CHARS.length), 80);
    return () => window.clearInterval(t);
  }, []);
  return (
    <p className="term-load" role="status">
      <span className="spin-char" aria-hidden>
        {SPIN_CHARS[i]}
      </span>
      ▸ {label}…
    </p>
  );
}

export function SkeletonRows({ n = 3 }: { n?: number }) {
  return (
    <div className="flex-col gap-3" aria-hidden>
      {Array.from({ length: n }).map((_, i) => (
        <div key={i} className="skeleton skeleton-block" />
      ))}
    </div>
  );
}

interface EmptyStateProps {
  title: string;
  desc?: string;
  action?: ReactNode;
}

export function EmptyState({ title, desc, action }: EmptyStateProps) {
  return (
    <div className="empty">
      <IconTerminal className="empty-icon" />
      <p className="empty-title">{title}</p>
      {desc && <p className="empty-desc">{desc}</p>}
      {action}
    </div>
  );
}
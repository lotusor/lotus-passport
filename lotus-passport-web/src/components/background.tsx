'use client';

import { useEffect } from 'react';

export function ScrollDriver() {
  useEffect(() => {
    let raf = 0;
    const onScroll = () => {
      if (raf) return;
      raf = window.requestAnimationFrame(() => {
        raf = 0;
        document.documentElement.style.setProperty('--scroll-y', String(window.scrollY));
      });
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', onScroll);
      if (raf) window.cancelAnimationFrame(raf);
    };
  }, []);
  return null;
}

export function Background() {
  return (
    <div className="bg-field" aria-hidden>
      <div className="bg-dots" />
      <svg className="bg-ring" viewBox="0 0 720 720" fill="none">
        <circle cx="360" cy="360" r="340" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="360" cy="360" r="300" stroke="currentColor" strokeWidth="1" strokeDasharray="4 10" />
        <circle cx="360" cy="360" r="180" stroke="currentColor" strokeWidth="1" />
        <path d="M360 10v60M360 650v60M10 360h60M650 360h60" stroke="currentColor" strokeWidth="1.5" />
      </svg>
      <svg className="bg-ring bg-ring--low" viewBox="0 0 640 640" fill="none">
        <circle cx="320" cy="320" r="300" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="320" cy="320" r="240" stroke="currentColor" strokeWidth="1" strokeDasharray="2 8" />
      </svg>
      <span className="bg-shard bg-shard--a" />
      <span className="bg-shard bg-shard--b" />
      <span className="bg-shard bg-shard--c" />
      <div className="bg-grain" />
    </div>
  );
}
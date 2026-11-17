'use client';

import { useEffect, useRef, type HTMLAttributes, type PointerEvent, type ReactNode } from 'react';
import { useInstant } from './motion';

const GLOW_SIZE = 240;

interface GlassPanelProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  sheen?: boolean;
  hover?: boolean;
}

export function GlassPanel({ children, sheen = true, hover = false, className = '', ...rest }: GlassPanelProps) {
  const ref = useRef<HTMLDivElement>(null);
  const sheenRef = useRef<HTMLSpanElement>(null);
  const glowRef = useRef<HTMLSpanElement>(null);
  const instant = useInstant();
  const capable = useRef(false);
  const target = useRef({ x: 0, y: 0 });
  const current = useRef({ x: 0, y: 0 });
  const raf = useRef(0);
  const last = useRef(0);
  const hovering = useRef(false);

  useEffect(() => {
    capable.current = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
    return () => cancelAnimationFrame(raf.current);
  }, []);

  useEffect(() => {
    if (instant) {
      hovering.current = false;
      cancelAnimationFrame(raf.current);
      raf.current = 0;
      sheenRef.current?.classList.remove('is-live');
    }
  }, [instant]);

  const tick = (t: number) => {
    const glow = glowRef.current;
    if (!glow) {
      raf.current = 0;
      return;
    }
    const dt = Math.min(48, t - last.current);
    last.current = t;
    const k = 1 - Math.exp(-dt / 90);
    current.current.x += (target.current.x - current.current.x) * k;
    current.current.y += (target.current.y - current.current.y) * k;
    glow.style.transform = `translate3d(${current.current.x - GLOW_SIZE / 2}px, ${current.current.y - GLOW_SIZE / 2}px, 0)`;
    const dx = target.current.x - current.current.x;
    const dy = target.current.y - current.current.y;
    if (hovering.current || dx * dx + dy * dy > 0.04) {
      raf.current = requestAnimationFrame(tick);
    } else {
      raf.current = 0;
    }
  };

  const point = (e: PointerEvent<HTMLDivElement>) => {
    const rect = ref.current!.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  const start = () => {
    if (!raf.current) {
      last.current = performance.now();
      raf.current = requestAnimationFrame(tick);
    }
  };

  const onPointerEnter = (e: PointerEvent<HTMLDivElement>) => {
    if (!capable.current || instant) return;
    const p = point(e);
    target.current = p;
    current.current = { ...p };
    hovering.current = true;
    sheenRef.current?.classList.add('is-live');
    start();
  };

  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (!capable.current || instant || !hovering.current) return;
    target.current = point(e);
    start();
  };

  const onPointerLeave = () => {
    hovering.current = false;
    sheenRef.current?.classList.remove('is-live');
  };

  const live = sheen && !instant;

  return (
    <div
      ref={ref}
      className={`glass ${hover ? 'glass-hover' : ''} ${className}`}
      onPointerEnter={live ? onPointerEnter : undefined}
      onPointerMove={live ? onPointerMove : undefined}
      onPointerLeave={live ? onPointerLeave : undefined}
      {...rest}
    >
      {sheen && (
        <span ref={sheenRef} className="glass-sheen" aria-hidden>
          <span ref={glowRef} className="glass-glow" />
        </span>
      )}
      {children}
    </div>
  );
}
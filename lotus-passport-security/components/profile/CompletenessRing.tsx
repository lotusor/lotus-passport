"use client";

import * as React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Sparkles } from "@/components/icons";

const toneColor: Record<string, string> = {
  success: "#2f9e6f",
  accent: "#d9543f",
  warn: "#c98a1b",
  danger: "#d23b3b",
};

function useCountUp(target: number, duration = 700) {
  const reduce = useReducedMotion();
  const [val, setVal] = React.useState(target);
  const prev = React.useRef(target);
  React.useEffect(() => {
    if (reduce) {
      setVal(target);
      return;
    }
    const start = prev.current;
    const t0 = performance.now();
    let raf = 0;
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      setVal(Math.round(start + (target - start) * eased));
      if (p < 1) raf = requestAnimationFrame(tick);
      else prev.current = target;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration, reduce]);
  return val;
}

export function CompletenessRing({
  score,
  hint,
}: {
  score: number;
  hint?: string;
}) {
  const color =
    score >= 90 ? toneColor.success : score >= 65 ? toneColor.accent : toneColor.warn;
  const display = useCountUp(score);

  const r = 52;
  const C = 2 * Math.PI * r;
  const offset = C * (1 - score / 100);

  return (
    <div className="relative overflow-hidden rounded-3xl border border-line bg-surface p-6 shadow-soft">
      <div
        className="pointer-events-none absolute -right-16 -top-16 h-44 w-44 rounded-full blur-3xl"
        style={{ background: `${color}22` }}
      />
      <div className="relative">
        <div className="flex items-center gap-2 text-sm font-medium text-ink-soft">
          <Sparkles className="h-4 w-4 text-accent" />
          资料完整度
        </div>
        <div className="mt-4 flex items-center gap-5">
          <div className="relative h-32 w-32 shrink-0">
            <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90">
              <defs>
                <linearGradient id="compGrad" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0%" stopColor={color} stopOpacity="0.85" />
                  <stop offset="100%" stopColor={color} />
                </linearGradient>
              </defs>
              <circle
                cx="60"
                cy="60"
                r={r}
                fill="none"
                stroke="#e9e5dd"
                strokeWidth="9"
              />
              <motion.circle
                cx="60"
                cy="60"
                r={r}
                fill="none"
                stroke="url(#compGrad)"
                strokeWidth="9"
                strokeLinecap="round"
                strokeDasharray={C}
                initial={false}
                animate={{ strokeDashoffset: offset }}
                transition={{ type: "spring", stiffness: 90, damping: 18 }}
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-3xl font-bold tabular-nums text-ink">
                {display}
              </span>
              <span className="text-xs text-ink-muted">%</span>
            </div>
          </div>
          <div className="min-w-0">
            <p className="text-sm leading-relaxed text-ink-muted">
              {hint ?? "补全资料可获得更完整的账户体验"}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

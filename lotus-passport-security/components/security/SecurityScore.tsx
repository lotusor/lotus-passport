"use client";

import * as React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Check, Sparkles } from "@/components/icons";
import type { SecurityFactors } from "@/lib/data";
import { cn } from "@/lib/cn";

const WEIGHTS: Record<Exclude<keyof SecurityFactors, "passkey">, number> = {
  password: 50,
  monitoring: 50,
};

const LABELS: Record<Exclude<keyof SecurityFactors, "passkey">, string> = {
  password: "登录密码已设置",
  monitoring: "登录异常监控",
};

function computeScore(f: SecurityFactors) {
  return (Object.keys(WEIGHTS) as (keyof typeof WEIGHTS)[]).reduce(
    (sum, k) => sum + (f[k] ? WEIGHTS[k] : 0),
    0
  );
}

function levelOf(score: number) {
  if (score >= 90) return { text: "优秀", tone: "success", hint: "账户防护已达到最优状态" };
  if (score >= 70) return { text: "良好", tone: "accent", hint: "再开启一项即可达到优秀" };
  if (score >= 50) return { text: "中等", tone: "warn", hint: "建议尽快补全关键防护" };
  return { text: "待加强", tone: "danger", hint: "账户存在较高风险，请立即加固" };
}

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

export function SecurityScore({ factors }: { factors: SecurityFactors }) {
  const score = computeScore(factors);
  const level = levelOf(score);
  const color = toneColor[level.tone];
  const display = useCountUp(score);

  const r = 52;
  const C = 2 * Math.PI * r;
  const offset = C * (1 - score / 100);

  const items = (Object.keys(LABELS) as (keyof typeof LABELS)[]).map((k) => ({
    key: k,
    label: LABELS[k],
    on: factors[k],
  }));

  return (
    <div className="relative overflow-hidden rounded-3xl border border-line bg-surface p-6 shadow-soft">
      {/* ambient glow */}
      <div
        className="pointer-events-none absolute -right-16 -top-16 h-44 w-44 rounded-full blur-3xl"
        style={{ background: `${color}22` }}
      />
      <div className="relative">
        <div className="flex items-center gap-2 text-sm font-medium text-ink-soft">
          <Sparkles className="h-4 w-4 text-accent" />
          安全评分
        </div>

        <div className="mt-4 flex items-center gap-5">
          <div className="relative h-32 w-32 shrink-0">
            <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90">
              <defs>
                <linearGradient id="scoreGrad" x1="0" y1="0" x2="1" y2="1">
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
                stroke="url(#scoreGrad)"
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
              <span className="text-xs text-ink-muted">/ 100</span>
            </div>
          </div>

          <div className="min-w-0">
            <span
              className="inline-flex items-center rounded-full px-2.5 py-0.5 text-sm font-semibold"
              style={{ background: `${color}1a`, color }}
            >
              {level.text}
            </span>
            <p className="mt-2 text-sm leading-relaxed text-ink-muted">
              {level.hint}
            </p>
          </div>
        </div>

        <ul className="mt-5 space-y-2.5">
          {items.map((it) => (
            <li key={it.key} className="flex items-center gap-2.5 text-sm">
              <span
                className={cn(
                  "grid h-5 w-5 place-items-center rounded-full",
                  it.on ? "bg-success-soft text-success" : "bg-ink/5 text-ink-muted"
                )}
              >
                {it.on ? (
                  <Check className="h-3.5 w-3.5" />
                ) : (
                  <span className="h-1.5 w-1.5 rounded-full bg-ink-muted/50" />
                )}
              </span>
              <span className={cn(it.on ? "text-ink" : "text-ink-muted")}>
                {it.label}
              </span>
            </li>
          ))}
        </ul>

      </div>
    </div>
  );
}

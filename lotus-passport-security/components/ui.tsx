import * as React from "react";
import { cn } from "@/lib/cn";

/* ----------------------------- Button ----------------------------- */
type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

const btnBase =
  "inline-flex items-center justify-center gap-2 font-medium rounded-xl transition-all duration-150 active:scale-[0.98] disabled:opacity-50 disabled:pointer-events-none select-none focus-visible:outline-2";

const btnVariants: Record<Variant, string> = {
  primary: "bg-accent text-white shadow-soft hover:bg-accent-ink",
  secondary:
    "bg-surface text-ink border border-line hover:border-ink/30 hover:bg-paper",
  ghost: "bg-transparent text-ink-soft hover:bg-ink/5",
  danger: "bg-danger text-white shadow-soft hover:brightness-95",
};

const btnSizes: Record<Size, string> = {
  sm: "min-h-[40px] px-3.5 text-sm",
  md: "min-h-[44px] px-5 text-[15px]",
  lg: "min-h-[48px] px-6 text-base",
};

export const Button = React.forwardRef<
  HTMLButtonElement,
  React.ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: Variant;
    size?: Size;
  }
>(({ variant = "primary", size = "md", className, ...props }, ref) => (
  <button
    ref={ref}
    className={cn(btnBase, btnVariants[variant], btnSizes[size], className)}
    {...props}
  />
));
Button.displayName = "Button";

/* ------------------------------ Card ------------------------------ */
export function Card({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-3xl border border-line bg-surface shadow-soft",
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
}

/* --------------------------- SectionCard -------------------------- */
export function SectionCard({
  icon: Icon,
  title,
  description,
  action,
  children,
  className,
}: {
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  title: string;
  description?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Card className={cn("overflow-hidden", className)}>
      <div className="flex items-start gap-4 p-5 sm:p-6 border-b border-line">
        <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-accent-soft text-accent">
          <Icon className="h-5 w-5" />
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="text-lg font-semibold tracking-tight text-ink">
            {title}
          </h3>
          {description && (
            <p className="mt-1 text-sm leading-relaxed text-ink-muted">
              {description}
            </p>
          )}
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </div>
      <div className="p-5 sm:p-6">{children}</div>
    </Card>
  );
}

/* ------------------------------ Badge ------------------------------ */
type Tone = "accent" | "success" | "warn" | "danger" | "neutral";

const badgeTones: Record<Tone, string> = {
  accent: "bg-accent-soft text-accent-ink",
  success: "bg-success-soft text-success",
  warn: "bg-warn-soft text-warn",
  danger: "bg-danger-soft text-danger",
  neutral: "bg-ink/5 text-ink-muted",
};

export function Badge({
  tone = "neutral",
  className,
  children,
}: {
  tone?: Tone;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium",
        badgeTones[tone],
        className
      )}
    >
      {children}
    </span>
  );
}

/* ------------------------------ Toggle ----------------------------- */
export function Toggle({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full px-0.5 transition-colors duration-200 justify-start",
        checked ? "bg-accent" : "bg-ink/15",
        disabled && "opacity-50 pointer-events-none"
      )}
    >
      <span
        className={cn(
          "h-5 w-5 rounded-full bg-white shadow-sm transition-transform duration-200",
          checked ? "translate-x-[22px]" : "translate-x-0"
        )}
      />
    </button>
  );
}

/* ----------------------------- Skeleton ---------------------------- */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton h-4 w-full", className)} />;
}

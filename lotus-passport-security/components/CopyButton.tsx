"use client";

import * as React from "react";
import { Check, Copy } from "@/components/icons";
import { cn } from "@/lib/cn";

export function CopyButton({
  value,
  label,
  className,
}: {
  value: string;
  label?: string;
  className?: string;
}) {
  const [copied, setCopied] = React.useState(false);

  const onClick = async () => {
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      /* clipboard may be unavailable; ignore */
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label ?? "复制"}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-lg px-2 text-sm text-ink-muted transition-colors hover:bg-ink/5 hover:text-ink min-h-[36px]",
        className
      )}
    >
      {copied ? (
        <Check className="h-4 w-4 text-success" />
      ) : (
        <Copy className="h-4 w-4" />
      )}
      {label && <span>{copied ? "已复制" : label}</span>}
    </button>
  );
}

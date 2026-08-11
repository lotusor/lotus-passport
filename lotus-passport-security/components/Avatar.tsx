"use client";

import * as React from "react";
import { cn } from "@/lib/cn";

const GRADIENTS = [
  "from-[#d9543f] to-[#c98a1b]",
  "from-[#2f9e6f] to-[#1f6f8b]",
  "from-[#7c5cff] to-[#d9543f]",
  "from-[#1f6f8b] to-[#2f9e6f]",
];

function pickGradient(seed: string): string {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) | 0;
  return GRADIENTS[Math.abs(h) % GRADIENTS.length];
}

/** 统一头像：有图显示图，无图显示昵称首字母渐变块。src 可为本地 /media 或外部 URL。 */
export function Avatar({
  src,
  name,
  size = 80,
  className,
  rounded = "rounded-3xl",
}: {
  src?: string;
  name: string;
  size?: number;
  className?: string;
  rounded?: string;
}) {
  const initial = (name || "?").trim().charAt(0).toUpperCase() || "?";
  const dim = { width: size, height: size };

  if (src) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={src}
        alt={name || "头像"}
        style={dim}
        className={cn("object-cover shadow-lift", rounded, className)}
      />
    );
  }
  return (
    <span
      style={dim}
      className={cn(
        "grid place-items-center bg-gradient-to-br text-white shadow-lift",
        pickGradient(name || "?"),
        rounded,
        className
      )}
    >
      <span style={{ fontSize: size * 0.4 }} className="font-bold">
        {initial}
      </span>
    </span>
  );
}

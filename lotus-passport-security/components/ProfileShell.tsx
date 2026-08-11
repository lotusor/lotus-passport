"use client";

import * as React from "react";
import { Sidebar } from "@/components/sidebar";
import { Menu } from "@/components/icons";
import { useAuth } from "@/lib/auth-context";
import { AuthGate } from "@/components/AuthGate";

export function ProfileShell({
  title,
  eyebrow = "账户中心",
  subtitle,
  children,
  aside,
}: {
  title: string;
  eyebrow?: string;
  subtitle?: string;
  children: React.ReactNode;
  aside?: React.ReactNode;
}) {
  const [sidebarOpen, setSidebarOpen] = React.useState(false);
  const { user } = useAuth();
  const initial = (user?.nickname || "?").charAt(0).toUpperCase();

  return (
    <AuthGate>
      <div className="flex min-h-[100dvh]">
        <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

        <main className="relative z-10 flex-1 min-w-0">
          {/* Mobile top bar */}
          <header className="sticky top-0 z-30 flex items-center justify-between gap-4 border-b border-line bg-surface/80 px-4 py-3 backdrop-blur lg:hidden">
            <button
              onClick={() => setSidebarOpen(true)}
              aria-label="打开菜单"
              className="grid h-10 w-10 place-items-center rounded-xl text-ink-soft hover:bg-ink/5 min-h-[44px] min-w-[44px]"
            >
              <Menu className="h-5 w-5" />
            </button>
            <span className="text-sm font-semibold text-ink">{title}</span>
            <span className="grid h-9 w-9 place-items-center rounded-full bg-accent/90 text-sm font-semibold text-white">
              {initial}
            </span>
          </header>

          <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 lg:px-8 lg:py-10">
            {/* Page header */}
            <div className="mb-8">
              <p className="text-sm font-medium text-accent">{eyebrow}</p>
              <h1 className="mt-2 text-3xl font-bold tracking-tight text-ink sm:text-4xl">
                {title}
              </h1>
              {subtitle && (
                <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-ink-muted">
                  {subtitle}
                </p>
              )}
            </div>

            {aside ? (
              <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
                <div className="order-2 space-y-6 lg:order-1">{children}</div>
                <aside className="order-1 lg:order-2">
                  <div className="lg:sticky lg:top-24">{aside}</div>
                </aside>
              </div>
            ) : (
              <div className="space-y-6">{children}</div>
            )}
          </div>
        </main>
      </div>
    </AuthGate>
  );
}
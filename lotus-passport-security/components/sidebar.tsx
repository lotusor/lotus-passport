"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { cn } from "@/lib/cn";
import { useAuth } from "@/lib/auth-context";
import {
  Shield,
  UserCircle,
  Smartphone,
  Link2,
  Key,
  LogOut,
  Lotus,
} from "@/components/icons";
import { Avatar } from "@/components/Avatar";

const navItems = [
  { id: "basic", label: "个人资料", icon: UserCircle, href: "/profile/basic" },
  {
    id: "security",
    label: "安全设置",
    icon: Shield,
    href: "/profile/security",
  },
  {
    id: "devices",
    label: "登录设备",
    icon: Smartphone,
    href: "/profile/devices",
  },
  { id: "oauth", label: "关联账号", icon: Link2, href: "/profile/oauth" },
  {
    id: "clients",
    label: "授权应用",
    icon: Key,
    href: "/profile/oauth-clients",
  },
];

function isActive(pathname: string, href: string) {
  if (href === "/profile/security")
    return pathname === "/profile/security" || pathname === "/";
  return pathname === href || pathname.startsWith(href + "/");
}

function SidebarContent({
  pathname,
  onNavigate,
}: {
  pathname: string;
  onNavigate?: () => void;
}) {
  const { user, logout } = useAuth();
  const router = useRouter();

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  const nickname = user?.nickname || "未登录";
  const email = user?.email || "";
  const avatar = user?.avatar || "";
  const providers = user?.providers || [];

  return (
    <div className="flex h-full flex-col p-5">
      {/* Brand */}
      <Link
        href="/profile/security"
        className="flex items-center gap-3 px-2 pb-6"
      >
        <span className="grid h-10 w-10 place-items-center rounded-2xl bg-white shadow-lg overflow-hidden">
          <Lotus className="h-10 w-10 text-accent" />
        </span>
        <div className="leading-tight">
          <p className="text-sm font-semibold text-white">莲花通行证</p>
          <p className="text-xs text-white/50">Lotus Passport</p>
        </div>
      </Link>

      {/* User card */}
      <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-4">
        <div className="flex items-center gap-3">
          <Avatar
            src={avatar}
            name={nickname}
            size={44}
            rounded="rounded-full"
            className="ring-1 ring-white/20"
          />
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-white">
              {nickname}
            </p>
            <p className="truncate text-xs text-white/50">
              {email || "未绑定邮箱"}
            </p>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-1.5">
          <span className="rounded-full bg-accent/20 px-2 py-0.5 text-[11px] font-medium text-accent-soft">
            通行证用户
          </span>
          {providers.includes("github") && (
            <span className="rounded-full bg-[#24292f]/20 px-2 py-0.5 text-[11px] font-medium text-[#adbac7]">
              GitHub
            </span>
          )}
          {providers.includes("wechat") && (
            <span className="rounded-full bg-[#07C160]/20 px-2 py-0.5 text-[11px] font-medium text-[#07C160]">
              微信
            </span>
          )}
          {providers.includes("qq") && (
            <span className="rounded-full bg-[#12B7F5]/20 px-2 py-0.5 text-[11px] font-medium text-[#12B7F5]">
              QQ
            </span>
          )}
        </div>
      </div>

      {/* Nav */}
      <nav className="mt-6 flex-1 space-y-1">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = isActive(pathname, item.href);
          return (
            <Link
              key={item.id}
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex w-full items-center gap-3 rounded-2xl px-3 py-3 text-sm font-medium transition-colors min-h-[44px]",
                active
                  ? "bg-white/10 text-white"
                  : "text-white/60 hover:bg-white/5 hover:text-white"
              )}
            >
              <Icon className="h-5 w-5" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Logout */}
      <button
        onClick={handleLogout}
        className="mt-4 flex w-full items-center gap-3 rounded-2xl px-3 py-3 text-sm font-medium text-white/60 transition-colors hover:bg-white/5 hover:text-white min-h-[44px]"
      >
        <LogOut className="h-5 w-5" />
        退出登录
      </button>
    </div>
  );
}

export function Sidebar({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const pathname = usePathname();
  return (
    <>
      {/* Desktop */}
      <aside className="hidden w-[280px] shrink-0 bg-panel lg:block">
        <div className="sticky top-0 h-[100dvh]">
          <SidebarContent pathname={pathname} />
        </div>
      </aside>

      {/* Mobile drawer */}
      <AnimatePresence>
        {open && (
          <motion.div
            className="fixed inset-0 z-40 lg:hidden"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <div
              className="absolute inset-0 bg-ink/50 backdrop-blur-sm"
              onClick={onClose}
              aria-hidden
            />
            <motion.div
              className="absolute left-0 top-0 h-[100dvh] w-[280px] bg-panel"
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ type: "spring", stiffness: 320, damping: 32 }}
            >
              <SidebarContent pathname={pathname} onNavigate={onClose} />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
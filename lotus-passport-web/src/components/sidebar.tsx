'use client';

import { motion } from 'framer-motion';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { refreshSession } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { accessSecondsLeft } from '@/lib/tokens';
import { fmtCountdown } from '@/lib/format';
import { Avatar } from './avatar';
import {
  IconDevices,
  IconHistory,
  IconLayers,
  IconLink,
  IconLogout,
  IconOverview,
  IconShield,
  IconUser,
  IconX,
} from './icons';
import { useToast } from './toast';
import { useT } from './motion';

export const NAV_ITEMS = [
  { href: '/account', label: '总览', idx: '01', icon: IconOverview },
  { href: '/account/profile', label: '个人资料', idx: '02', icon: IconUser },
  { href: '/account/security', label: '账户安全', idx: '03', icon: IconShield },
  { href: '/account/connections', label: '登录方式', idx: '04', icon: IconLink },
  { href: '/account/devices', label: '授权设备', idx: '05', icon: IconDevices },
  { href: '/account/sessions', label: '在线会话', idx: '06', icon: IconLayers },
  { href: '/account/activity', label: '登录历史', idx: '07', icon: IconHistory },
] as const;

function TokenCountdown() {
  const [left, setLeft] = useState(() => accessSecondsLeft());

  useEffect(() => {
    const tick = () => {
      const s = accessSecondsLeft();
      setLeft(s);
      if (s > 0 && s <= 60) void refreshSession();
    };
    tick();
    const t = window.setInterval(tick, 1000);
    return () => window.clearInterval(t);
  }, []);

  return (
    <div className={`token-chip glass-inset ${left > 0 && left < 300 ? 'is-low' : ''}`} title="访问令牌剩余有效期">
      <span>ACCESS</span>
      <span>{left > 0 ? fmtCountdown(left) : '——:——'}</span>
    </div>
  );
}

interface SidebarProps {
  open: boolean;
  onClose: () => void;
}

export function Sidebar({ open, onClose }: SidebarProps) {
  const pathname = usePathname().replace(/\/+$/, '') || '/';
  const router = useRouter();
  const { user, logout } = useAuth();
  const { push } = useToast();
  const [loggingOut, setLoggingOut] = useState(false);
  const indicatorT = useT({ duration: 0.32, ease: [0.22, 1, 0.36, 1] });

  const onLogout = async () => {
    setLoggingOut(true);
    await logout();
    push('info', '已登出', '令牌已在服务端吊销');
    router.replace('/login');
  };

  return (
    <>
      {open && <button type="button" className="scrim" aria-label="关闭导航" onClick={onClose} />}
      <nav className={`sidebar ${open ? 'is-open' : ''}`} aria-label="账户中心导航">
        <div className="flex items-center justify-between gap-3">
          <Link href="/account" className="brand" onClick={onClose}>
            <svg className="brand-mark" viewBox="0 0 40 40" fill="none" aria-hidden>
              <rect x="2" y="2" width="36" height="36" rx="10" stroke="currentColor" strokeWidth="1.6" />
              <path d="M20 9l7 11-7 11-7-11 7-11z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
              <path d="M13 20h14" stroke="currentColor" strokeWidth="1.6" />
            </svg>
            <span>
              <span className="brand-name">LOTUS PASSPORT</span>
              <br />
              <span className="brand-sub">Identity Terminal</span>
            </span>
          </Link>
          <button type="button" className="btn btn-ghost btn-icon topbar-menu" aria-label="关闭导航" onClick={onClose}>
            <IconX width={18} height={18} />
          </button>
        </div>

        <div className="nav">
          {NAV_ITEMS.map((item) => {
            const active = pathname === item.href;
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`nav-item ${active ? 'is-active' : ''}`}
                aria-current={active ? 'page' : undefined}
                onClick={onClose}
              >
                {active && (
                  <motion.span
                    layoutId="nav-indicator"
                    className="nav-indicator"
                    transition={indicatorT}
                  />
                )}
                <Icon className="nav-icon" />
                {item.label}
                <span className="nav-idx" aria-hidden>
                  {item.idx}
                </span>
              </Link>
            );
          })}
        </div>

        <div className="sidebar-foot">
          <TokenCountdown />
          <div className="user-chip">
            <Avatar src={user?.avatar ?? ''} name={user?.nickname ?? ''} size="sm" />
            <div className="user-chip-meta">
              <p className="truncate small" style={{ fontWeight: 600 }}>
                {user?.nickname || '未命名旅客'}
              </p>
              <p className="truncate mono faint" style={{ fontSize: 'var(--fs-label)' }}>
                {user?.email || user?.passport_user_id.slice(0, 8) || '—'}
              </p>
            </div>
            <button
              type="button"
              className="btn btn-ghost btn-icon"
              aria-label="登出"
              title="登出"
              disabled={loggingOut}
              onClick={onLogout}
            >
              <IconLogout width={18} height={18} />
            </button>
          </div>
        </div>
      </nav>
    </>
  );
}
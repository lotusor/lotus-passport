'use client';

import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState, type ReactNode } from 'react';
import { IconMenu } from '@/components/icons';
import { PageTransition } from '@/components/page-transition';
import { Sidebar } from '@/components/sidebar';
import { TermLoad } from '@/components/term-load';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import type { DevStatus } from '@/lib/types';

export default function AccountLayout({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [drawer, setDrawer] = useState(false);
  const [devMode, setDevMode] = useState(false);

  useEffect(() => {
    if (status === 'guest') router.replace('/login');
  }, [status, router]);

  useEffect(() => {
    setDrawer(false);
  }, [pathname]);

  useEffect(() => {
    api<DevStatus>('/dev/status/', { auth: false })
      .then((s) => setDevMode(s.dev_login_enabled))
      .catch(() => setDevMode(false));
  }, []);

  if (status !== 'authed') {
    return (
      <main className="center-page">
        <TermLoad label="restoring session" />
      </main>
    );
  }

  return (
    <div className="shell">
      <Sidebar open={drawer} onClose={() => setDrawer(false)} />
      <div className="main">
        <header className="topbar">
          <button
            type="button"
            className="btn btn-ghost btn-icon topbar-menu"
            aria-label="打开导航"
            aria-expanded={drawer}
            onClick={() => setDrawer(true)}
          >
            <IconMenu width={18} height={18} />
          </button>
          <span className="topbar-title">LOTUS PASSPORT // ACCOUNT</span>
          <span className="topbar-spacer" />
          {devMode && (
            <span className="chip chip--amber">
              <span className="chip-dot" />
              DEV MODE
            </span>
          )}
          <span className="chip chip--phos">
            <span className="chip-dot" />
            ACTIVE
          </span>
        </header>
        <main className="content" id="main">
          <PageTransition>{children}</PageTransition>
        </main>
      </div>
    </div>
  );
}
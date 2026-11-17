import Link from 'next/link';
import { GlassPanel } from '@/components/glass';
import { IconArrowLeft, IconTerminal } from '@/components/icons';

export default function NotFound() {
  return (
    <main className="center-page">
      <GlassPanel className="center-card" style={{ textAlign: 'center' }}>
        <IconTerminal width={40} height={40} style={{ color: 'var(--phos)', marginInline: 'auto' }} />
        <p className="kicker">ERR // ROUTE NOT FOUND</p>
        <h1 style={{ fontSize: 'var(--fs-stat)' }}>404</h1>
        <p className="dim small">请求的路径不在本终端的路由表中。</p>
        <Link href="/" className="btn btn-primary btn-block">
          <IconArrowLeft width={16} height={16} />
          返回主终端
        </Link>
      </GlassPanel>
    </main>
  );
}
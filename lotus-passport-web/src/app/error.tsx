'use client';

import { GlassPanel } from '@/components/glass';
import { IconAlert, IconRefresh } from '@/components/icons';

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="center-page">
      <GlassPanel className="center-card">
        <p className="kicker kicker--red">KERNEL PANIC // 渲染异常</p>
        <h1 style={{ fontSize: 'var(--fs-title)' }}>终端遇到意外错误</h1>
        <p className="notice notice--red">
          <IconAlert />
          {error.message || '未知错误'}
        </p>
        <button type="button" className="btn btn-primary btn-block" onClick={reset}>
          <IconRefresh width={16} height={16} />
          重新加载
        </button>
      </GlassPanel>
    </main>
  );
}
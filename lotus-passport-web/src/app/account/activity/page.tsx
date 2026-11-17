'use client';

import { useCallback, useEffect, useState } from 'react';
import { GlassPanel } from '@/components/glass';
import { IconCheck, IconRefresh, IconX } from '@/components/icons';
import { Reveal } from '@/components/reveal';
import { EmptyState, SkeletonRows, TermLoad } from '@/components/term-load';
import { api } from '@/lib/api';
import { fmtDateTime, fmtRelative, reasonLabel } from '@/lib/format';
import type { LoginEvent } from '@/lib/types';

type Filter = 'all' | 'success' | 'failed';

const FILTERS: [Filter, string][] = [
  ['all', '全部'],
  ['success', '成功'],
  ['failed', '失败'],
];

export default function ActivityPage() {
  const [events, setEvents] = useState<LoginEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [filter, setFilter] = useState<Filter>('all');

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      setEvents(await api<LoginEvent[]>('/security/login-history/'));
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const shown = events.filter((e) => filter === 'all' || e.status === filter);

  return (
    <>
      <div className="page-head">
        <p className="kicker">ACCOUNT // 07</p>
        <div className="page-head-row">
          <h1 tabIndex={-1}>登录历史</h1>
          <div className="flex gap-2" role="group" aria-label="按状态筛选">
            {FILTERS.map(([key, label]) => (
              <button
                key={key}
                type="button"
                className={`btn btn-sm ${filter === key ? 'btn-primary' : ''}`}
                aria-pressed={filter === key}
                onClick={() => setFilter(key)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <p className="page-desc">最近 50 条认证尝试的不可变审计记录，成功与失败都会留痕。</p>
      </div>

      {loading ? (
        <>
          <TermLoad label="reading audit log" />
          <SkeletonRows n={4} />
        </>
      ) : error ? (
        <GlassPanel>
          <EmptyState
            title="LOAD FAILED // 加载失败"
            action={
              <button type="button" className="btn" onClick={load}>
                <IconRefresh width={16} height={16} />
                重试
              </button>
            }
          />
        </GlassPanel>
      ) : shown.length === 0 ? (
        <GlassPanel>
          <EmptyState
            title="NO EVENTS // 暂无记录"
            desc={filter === 'all' ? '完成一次登录后这里会出现记录。' : '当前筛选条件下没有记录。'}
          />
        </GlassPanel>
      ) : (
        <Reveal>
          <GlassPanel className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">时间</th>
                  <th scope="col">设备</th>
                  <th scope="col">位置</th>
                  <th scope="col">IP</th>
                  <th scope="col">状态</th>
                  <th scope="col">原因</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((ev) => (
                  <tr key={ev.id}>
                    <td title={fmtDateTime(ev.time)}>
                      <span className="mono">{fmtRelative(ev.time)}</span>
                    </td>
                    <td>{ev.device || '未知客户端'}</td>
                    <td className="dim">{ev.location || '未知位置'}</td>
                    <td className="mono">{ev.ip || '—'}</td>
                    <td>
                      <span className={`chip ${ev.status === 'success' ? 'chip--phos' : 'chip--red'}`}>
                        {ev.status === 'success' ? <IconCheck width={12} height={12} /> : <IconX width={12} height={12} />}
                        {ev.status === 'success' ? '成功' : '失败'}
                      </span>
                    </td>
                    <td className="dim">{ev.status === 'success' ? '—' : reasonLabel(ev.reason)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </GlassPanel>
        </Reveal>
      )}
    </>
  );
}
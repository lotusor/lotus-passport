'use client';

import { useCallback, useEffect, useState } from 'react';
import { GlassPanel } from '@/components/glass';
import { DEVICE_ICONS, IconAlert, IconRefresh, IconSpinner, IconTrash } from '@/components/icons';
import { Modal } from '@/components/modal';
import { Reveal } from '@/components/reveal';
import { EmptyState, SkeletonRows, TermLoad } from '@/components/term-load';
import { useToast } from '@/components/toast';
import { api, ApiException } from '@/lib/api';
import { fmtDateTime, fmtRelative } from '@/lib/format';
import type { Session } from '@/lib/types';

export default function SessionsPage() {
  const { push } = useToast();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [revokeTarget, setRevokeTarget] = useState<Session | null>(null);
  const [revokeAll, setRevokeAll] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      setSessions(await api<Session[]>('/sessions/'));
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const revokeOne = async () => {
    if (!revokeTarget || busy) return;
    setBusy(true);
    const prev = sessions;
    setSessions((list) => list.filter((s) => s.id !== revokeTarget.id));
    try {
      await api(`/sessions/${revokeTarget.id}/`, { method: 'DELETE' });
      push('success', '会话已注销', '该设备的令牌已失效');
      setRevokeTarget(null);
    } catch (err) {
      setSessions(prev);
      push('error', '注销失败', err instanceof ApiException ? err.message : '网络异常');
    } finally {
      setBusy(false);
    }
  };

  const revokeOthers = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const res = await api<{ revoked: number; detail: string }>('/sessions/', { method: 'DELETE' });
      push('success', res.detail, `共注销 ${res.revoked} 个其它会话`);
      setRevokeAll(false);
      await load();
    } catch (err) {
      push('error', '批量注销失败', err instanceof ApiException ? err.message : '网络异常');
    } finally {
      setBusy(false);
    }
  };

  const others = sessions.filter((s) => !s.current);

  return (
    <>
      <div className="page-head">
        <p className="kicker">ACCOUNT // 06</p>
        <div className="page-head-row">
          <h1 tabIndex={-1}>在线会话</h1>
          {others.length > 0 && (
            <button type="button" className="btn btn-danger btn-sm" onClick={() => setRevokeAll(true)}>
              <IconTrash width={14} height={14} />
              注销其它全部会话
            </button>
          )}
        </div>
        <p className="page-desc">每个会话对应一次登录签发的令牌对。注销会话会立即吊销其刷新令牌。</p>
      </div>

      {loading ? (
        <>
          <TermLoad label="querying active sessions" />
          <SkeletonRows n={3} />
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
      ) : sessions.length === 0 ? (
        <GlassPanel>
          <EmptyState title="NO SESSIONS // 暂无会话" desc="登录成功后会话会出现在这里。" />
        </GlassPanel>
      ) : (
        <Reveal>
          <GlassPanel>
            <div className="row-list">
              {sessions.map((s) => {
                const Icon = DEVICE_ICONS[s.device_type] ?? DEVICE_ICONS.other;
                return (
                  <div className={`row-item ${s.current ? 'is-current' : ''}`} key={s.id}>
                    <span className={`row-icon ${s.current ? 'row-icon--phos' : ''}`}>
                      <Icon />
                    </span>
                    <div className="row-meta">
                      <p className="row-title">
                        <span className="truncate">{s.device || '未知客户端'}</span>
                        {s.current && (
                          <span className="chip chip--phos">
                            <span className="chip-dot" />
                            当前会话
                          </span>
                        )}
                      </p>
                      <p className="row-sub">
                        {s.location || '未知位置'} · {s.ip || '—'} · 登录于 {fmtDateTime(s.created_at)}
                      </p>
                      <p className="row-sub">
                        最近活跃 {fmtRelative(s.last_active_at)} · JTI {s.jti.slice(0, 8)}…
                      </p>
                    </div>
                    {!s.current && (
                      <div className="row-actions">
                        <button type="button" className="btn btn-danger btn-sm" onClick={() => setRevokeTarget(s)}>
                          注销
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </GlassPanel>
        </Reveal>
      )}

      <p className="notice mt-5">
        <IconAlert />
        ACCESS 令牌有效期 30 分钟，REFRESH 令牌 14 天；离线验签的接入应用在令牌自然过期前仍可能信任已吊销令牌。
      </p>

      <Modal
        open={revokeTarget !== null}
        onClose={() => setRevokeTarget(null)}
        title="注销该会话？"
        footer={
          <>
            <button type="button" className="btn" onClick={() => setRevokeTarget(null)}>
              取消
            </button>
            <button type="button" className="btn btn-danger" disabled={busy} onClick={revokeOne}>
              {busy ? <IconSpinner width={16} height={16} /> : null}
              确认注销
            </button>
          </>
        }
      >
        <p className="dim small">
          「{revokeTarget?.device || '该会话'}」将被立即吊销，对应设备需要重新登录。
        </p>
      </Modal>

      <Modal
        open={revokeAll}
        onClose={() => setRevokeAll(false)}
        title="注销其它全部会话？"
        footer={
          <>
            <button type="button" className="btn" onClick={() => setRevokeAll(false)}>
              取消
            </button>
            <button type="button" className="btn btn-danger" disabled={busy} onClick={revokeOthers}>
              {busy ? <IconSpinner width={16} height={16} /> : null}
              全部注销
            </button>
          </>
        }
      >
        <p className="dim small">将注销除当前会话外的 {others.length} 个会话，其它设备需重新登录。当前会话不受影响。</p>
      </Modal>
    </>
  );
}
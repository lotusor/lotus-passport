'use client';

import { useCallback, useEffect, useState } from 'react';
import { GlassPanel } from '@/components/glass';
import { DEVICE_ICONS, IconAlert, IconCheck, IconPencil, IconRefresh, IconSpinner, IconTrash, IconX } from '@/components/icons';
import { Modal } from '@/components/modal';
import { Reveal } from '@/components/reveal';
import { EmptyState, SkeletonRows, TermLoad } from '@/components/term-load';
import { useToast } from '@/components/toast';
import { api, ApiException } from '@/lib/api';
import { DEVICE_TYPE_LABELS, fmtRelative } from '@/lib/format';
import type { Device, Session } from '@/lib/types';

export default function DevicesPage() {
  const { push } = useToast();
  const [devices, setDevices] = useState<Device[]>([]);
  const [current, setCurrent] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState('');
  const [savingId, setSavingId] = useState<number | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<Device | null>(null);
  const [revoking, setRevoking] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const [devs, sessions] = await Promise.all([api<Device[]>('/devices/'), api<Session[]>('/sessions/')]);
      setDevices(devs);
      setCurrent(sessions.find((s) => s.current) ?? null);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const isCurrentDevice = (d: Device) =>
    current !== null && d.device_type === current.device_type && d.os === current.os && d.browser === current.browser;

  const saveName = async (d: Device) => {
    const name = editName.trim();
    setEditingId(null);
    if (!name || name === d.name) return;
    const prev = devices;
    setDevices((list) => list.map((x) => (x.id === d.id ? { ...x, name } : x)));
    setSavingId(d.id);
    try {
      await api(`/devices/${d.id}/`, { method: 'PATCH', body: { name } });
      push('success', '设备已重命名', name);
    } catch (err) {
      setDevices(prev);
      push('error', '重命名失败', err instanceof ApiException ? err.message : '网络异常');
    } finally {
      setSavingId(null);
    }
  };

  const toggleTrust = async (d: Device) => {
    const next = !d.trusted;
    const prev = devices;
    setDevices((list) => list.map((x) => (x.id === d.id ? { ...x, trusted: next } : x)));
    try {
      await api(`/devices/${d.id}/`, { method: 'PATCH', body: { trusted: next } });
      push(
        next ? 'success' : 'warning',
        next ? '已标记为受信任' : '已取消信任',
        next ? '该设备可继续自动登录' : '该设备的全部会话已注销，下次访问需重新登录',
      );
      if (!next) void load();
    } catch (err) {
      setDevices(prev);
      push('error', '操作失败', err instanceof ApiException ? err.message : '网络异常');
    }
  };

  const onRevoke = async () => {
    if (!revokeTarget || revoking) return;
    setRevoking(true);
    try {
      await api(`/devices/${revokeTarget.id}/`, { method: 'DELETE' });
      push('success', '设备已撤销', '该设备的全部会话已注销');
      setRevokeTarget(null);
      await load();
    } catch (err) {
      push('error', '撤销失败', err instanceof ApiException ? err.message : '网络异常');
    } finally {
      setRevoking(false);
    }
  };

  return (
    <>
      <div className="page-head">
        <p className="kicker">ACCOUNT // 05</p>
        <h1 tabIndex={-1}>授权设备</h1>
        <p className="page-desc">每次成功登录都会按设备指纹记录并默认信任。取消信任或撤销设备会立即注销其全部会话。</p>
      </div>

      {loading ? (
        <>
          <TermLoad label="querying trusted devices" />
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
      ) : devices.length === 0 ? (
        <GlassPanel>
          <EmptyState title="NO DEVICES // 暂无设备记录" desc="完成一次登录后，设备会自动出现在这里。" />
        </GlassPanel>
      ) : (
        <Reveal>
          <GlassPanel>
            <div className="row-list">
              {devices.map((d) => {
                const Icon = DEVICE_ICONS[d.device_type] ?? DEVICE_ICONS.other;
                const here = isCurrentDevice(d);
                return (
                  <div className={`row-item ${here ? 'is-current' : ''}`} key={d.id}>
                    <span className={`row-icon ${d.trusted ? 'row-icon--phos' : ''}`}>
                      <Icon />
                    </span>
                    <div className="row-meta">
                      {editingId === d.id ? (
                        <span className="flex gap-2 items-center">
                          <input
                            className="input"
                            style={{ minHeight: 36, padding: 'var(--sp-2) var(--sp-3)' }}
                            value={editName}
                            maxLength={128}
                            aria-label="设备名称"
                            autoFocus
                            onChange={(e) => setEditName(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') void saveName(d);
                              if (e.key === 'Escape') setEditingId(null);
                            }}
                          />
                          <button type="button" className="btn btn-sm btn-icon" aria-label="保存名称" onClick={() => void saveName(d)}>
                            <IconCheck width={14} height={14} />
                          </button>
                          <button type="button" className="btn btn-sm btn-icon" aria-label="取消编辑" onClick={() => setEditingId(null)}>
                            <IconX width={14} height={14} />
                          </button>
                        </span>
                      ) : (
                        <p className="row-title">
                          <span className="truncate">{d.name || DEVICE_TYPE_LABELS[d.device_type]}</span>
                          {here && (
                            <span className="chip chip--phos">
                              <span className="chip-dot" />
                              当前设备
                            </span>
                          )}
                          {savingId === d.id && <IconSpinner width={14} height={14} />}
                          <button
                            type="button"
                            className="btn btn-ghost btn-icon btn-sm"
                            aria-label="重命名设备"
                            onClick={() => {
                              setEditingId(d.id);
                              setEditName(d.name);
                            }}
                          >
                            <IconPencil width={14} height={14} />
                          </button>
                        </p>
                      )}
                      <p className="row-sub">
                        {d.os || '未知系统'} · {d.browser || '未知浏览器'} · {d.location || '未知位置'}
                      </p>
                      <p className="row-sub">
                        最近活跃 {fmtRelative(d.last_active_at)}
                        {d.first_trusted_at ? ` · 首次信任 ${fmtRelative(d.first_trusted_at)}` : ''}
                      </p>
                    </div>
                    <div className="row-actions">
                      <span className="flex items-center gap-2">
                        <span className="mono faint" style={{ fontSize: 'var(--fs-label)' }}>
                          {d.trusted ? '受信任' : '未信任'}
                        </span>
                        <button
                          type="button"
                          role="switch"
                          className="switch"
                          aria-checked={d.trusted}
                          aria-label={`信任设备 ${d.name || DEVICE_TYPE_LABELS[d.device_type]}`}
                          onClick={() => void toggleTrust(d)}
                        />
                      </span>
                      <button
                        type="button"
                        className="btn btn-ghost btn-icon"
                        aria-label="撤销设备"
                        title="撤销设备"
                        onClick={() => setRevokeTarget(d)}
                      >
                        <IconTrash width={16} height={16} />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </GlassPanel>
        </Reveal>
      )}

      <p className="notice mt-5">
        <IconAlert />
        设备指纹按「类型 + 系统 + 浏览器」去重；同一设备重复登录只刷新活跃时间。
      </p>

      <Modal
        open={revokeTarget !== null}
        onClose={() => setRevokeTarget(null)}
        title="撤销该设备？"
        footer={
          <>
            <button type="button" className="btn" onClick={() => setRevokeTarget(null)}>
              取消
            </button>
            <button type="button" className="btn btn-danger" disabled={revoking} onClick={onRevoke}>
              {revoking ? <IconSpinner width={16} height={16} /> : null}
              确认撤销
            </button>
          </>
        }
      >
        <p className="dim small">
          撤销「{revokeTarget?.name || '该设备'}」将删除设备记录并立即注销其全部会话，该设备下次访问需重新登录。
        </p>
      </Modal>
    </>
  );
}
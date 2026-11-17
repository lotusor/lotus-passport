'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState, type PointerEvent } from 'react';
import { Avatar } from '@/components/avatar';
import { GlassPanel } from '@/components/glass';
import {
  IconChevronRight,
  IconCopy,
  IconDevices,
  IconKey,
  IconLink,
  IconMail,
  IconRefresh,
} from '@/components/icons';
import { buildMrz, Mrz } from '@/components/mrz';
import { Reveal } from '@/components/reveal';
import { Stamp } from '@/components/stamp';
import { EmptyState, SkeletonRows, TermLoad } from '@/components/term-load';
import { useToast } from '@/components/toast';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { fmtRelative, PROVIDER_LABELS } from '@/lib/format';
import type { Device, LoginEvent, OAuthAccountRow, PasswordStatus, Profile, Session } from '@/lib/types';

interface OverviewData {
  profile: Profile;
  password: PasswordStatus;
  accounts: OAuthAccountRow[];
  devices: Device[];
  sessions: Session[];
  history: LoginEvent[];
}

function TiltCard({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const onMove = (e: PointerEvent<HTMLDivElement>) => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width - 0.5;
    const py = (e.clientY - r.top) / r.height - 0.5;
    el.style.setProperty('--ry', `${px * 4}deg`);
    el.style.setProperty('--rx', `${-py * 4}deg`);
  };
  const onLeave = () => {
    const el = ref.current;
    if (!el) return;
    el.style.setProperty('--rx', '0deg');
    el.style.setProperty('--ry', '0deg');
  };
  return (
    <div ref={ref} onPointerMove={onMove} onPointerLeave={onLeave}>
      {children}
    </div>
  );
}

export default function AccountOverview() {
  const { user } = useAuth();
  const { push } = useToast();
  const [data, setData] = useState<OverviewData | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const [profile, password, accountsRes, devices, sessions, history] = await Promise.all([
        api<Profile>('/profile/'),
        api<PasswordStatus>('/security/password/'),
        api<{ accounts: OAuthAccountRow[] }>('/oauth/accounts/'),
        api<Device[]>('/devices/'),
        api<Session[]>('/sessions/'),
        api<LoginEvent[]>('/security/login-history/'),
      ]);
      setData({ profile, password, accounts: accountsRes.accounts, devices, sessions, history });
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const copyId = async () => {
    if (!data) return;
    try {
      await navigator.clipboard.writeText(data.profile.passport_user_id);
      push('success', '已复制身份 ID');
    } catch {
      push('error', '复制失败', '浏览器拒绝了剪贴板访问');
    }
  };

  if (loading) {
    return (
      <>
        <div className="page-head">
          <p className="kicker">ACCOUNT // 01</p>
          <h1 tabIndex={-1}>总览</h1>
        </div>
        <TermLoad label="loading identity" />
        <SkeletonRows n={3} />
      </>
    );
  }

  if (error || !data) {
    return (
      <>
        <div className="page-head">
          <p className="kicker">ACCOUNT // 01</p>
          <h1 tabIndex={-1}>总览</h1>
        </div>
        <GlassPanel>
          <EmptyState
            title="LOAD FAILED // 数据加载失败"
            desc="无法从认证中心读取账户数据，请检查网络后重试。"
            action={
              <button type="button" className="btn" onClick={load}>
                <IconRefresh width={16} height={16} />
                重试
              </button>
            }
          />
        </GlassPanel>
      </>
    );
  }

  const { profile, password, accounts, devices, sessions, history } = data;
  const current = sessions.find((s) => s.current);
  const trustedCount = devices.filter((d) => d.trusted).length;
  const mrz = buildMrz(profile);

  return (
    <>
      <div className="page-head">
        <p className="kicker">ACCOUNT // 01</p>
        <div className="page-head-row">
          <h1 tabIndex={-1}>总览</h1>
          <span className="chip chip--phos">
            <span className="chip-dot" />
            身份已验证
          </span>
        </div>
        <p className="page-desc">你的统一身份档案与安全态势。通行证只做身份认证，业务数据归各接入应用。</p>
      </div>

      <Reveal>
        <TiltCard>
          <GlassPanel className="id-card" sheen>
            <Stamp animated />
            <div className="id-card-body">
              <div className="id-card-top">
                <Avatar src={profile.avatar} name={profile.nickname} size="lg" />
                <div className="id-card-meta">
                  <p className="kicker kicker--dim">LOTUS PASSPORT // HOLDER</p>
                  <p className="id-name">{profile.nickname || '未命名旅客'}</p>
                  <p className="id-sub">
                    {profile.username ? `@${profile.username}` : '未设置用户名'}
                    {profile.email ? ` · ${profile.email}` : ' · 未绑定邮箱'}
                  </p>
                  <div className="flex gap-2 flex-wrap">
                    {accounts.length > 0 ? (
                      accounts.map((a) => (
                        <span key={a.provider} className="chip chip--phos">
                          <span className="chip-dot" />
                          {PROVIDER_LABELS[a.provider]}
                        </span>
                      ))
                    ) : (
                      <span className="chip">
                        <span className="chip-dot" />
                        邮箱账户
                      </span>
                    )}
                  </div>
                </div>
              </div>
              <div className="id-fields">
                <div>
                  <p className="id-field-label">签发机构</p>
                  <p className="id-field-value mono">LOTUS PASSPORT · EACM</p>
                </div>
                <div>
                  <p className="id-field-label">身份 ID</p>
                  <button type="button" className="copy-chip" onClick={copyId} title="复制完整身份 ID">
                    <span className="truncate">{profile.passport_user_id}</span>
                    <IconCopy width={12} height={12} />
                  </button>
                </div>
              </div>
            </div>
            <Mrz lines={mrz} />
          </GlassPanel>
        </TiltCard>
      </Reveal>

      <h2 className="section-title">安全态势</h2>
      <div className="grid grid-4">
        {[
          {
            href: '/account/security',
            icon: IconKey,
            label: '账户密码',
            value: password.has_password ? '已设置' : '未设置',
            ok: password.has_password,
            delay: 0,
          },
          {
            href: '/account/security',
            icon: IconMail,
            label: '邮箱绑定',
            value: profile.email ? '已绑定' : '未绑定',
            ok: Boolean(profile.email),
            delay: 60,
          },
          {
            href: '/account/connections',
            icon: IconLink,
            label: '登录方式',
            value: `${accounts.length + (password.has_password ? 1 : 0)} 种`,
            ok: accounts.length + (password.has_password ? 1 : 0) > 0,
            delay: 120,
          },
          {
            href: '/account/devices',
            icon: IconDevices,
            label: '受信任设备',
            value: `${trustedCount} 台`,
            ok: trustedCount > 0,
            delay: 180,
          },
        ].map((s) => {
          const Icon = s.icon;
          return (
            <Reveal key={s.label} delay={s.delay}>
              <Link href={s.href} className="glass glass-hover stat-card">
                <span className="stat-top">
                  <span className="stat-label">{s.label}</span>
                  <Icon className="stat-icon" />
                </span>
                <span className="stat-value" style={{ color: s.ok ? 'var(--ink)' : 'var(--amber)' }}>
                  {s.value}
                </span>
                <span className={`chip ${s.ok ? 'chip--phos' : 'chip--amber'}`}>
                  <span className="chip-dot" />
                  {s.ok ? '正常' : '建议完善'}
                </span>
              </Link>
            </Reveal>
          );
        })}
      </div>

      <div className="grid grid-2 mt-6">
        <Reveal>
          <GlassPanel className="panel">
            <div className="panel-head">
              <h2 style={{ fontSize: 'var(--fs-body)' }}>最近登录活动</h2>
              <Link href="/account/activity" className="btn btn-ghost btn-sm">
                查看全部
                <IconChevronRight width={14} height={14} />
              </Link>
            </div>
            {history.length === 0 ? (
              <EmptyState title="NO EVENTS // 暂无记录" desc="成功或失败的登录尝试都会记录在这里。" />
            ) : (
              <div className="row-list">
                {history.slice(0, 5).map((ev) => (
                  <div className="row-item" key={ev.id}>
                    <div className="row-meta">
                      <p className="row-title truncate">{ev.device || '未知客户端'}</p>
                      <p className="row-sub">
                        {fmtRelative(ev.time)} · {ev.location || '未知位置'}
                      </p>
                    </div>
                    <span className={`chip ${ev.status === 'success' ? 'chip--phos' : 'chip--red'}`}>
                      <span className="chip-dot" />
                      {ev.status === 'success' ? '成功' : '失败'}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </GlassPanel>
        </Reveal>

        <Reveal delay={80}>
          <GlassPanel className="panel">
            <div className="panel-head">
              <h2 style={{ fontSize: 'var(--fs-body)' }}>当前会话</h2>
              <Link href="/account/sessions" className="btn btn-ghost btn-sm">
                管理会话
                <IconChevronRight width={14} height={14} />
              </Link>
            </div>
            {current ? (
              <div className="flex-col gap-3">
                <div className="row-item is-current" style={{ borderRadius: 'var(--r-ctrl)', border: '1px solid var(--line)' }}>
                  <div className="row-meta">
                    <p className="row-title">
                      {current.device || '未知客户端'}
                      <span className="chip chip--phos">
                        <span className="chip-dot" />
                        当前
                      </span>
                    </p>
                    <p className="row-sub">
                      {current.location || '未知位置'} · {current.ip || '—'}
                    </p>
                  </div>
                </div>
                <p className="faint small mono">
                  共 {sessions.length} 个活跃会话 · ACCESS 30MIN / REFRESH 14D
                </p>
              </div>
            ) : (
              <EmptyState title="NO SESSION // 无会话记录" desc="本次登录的会话尚未写入，稍后刷新即可看到。" />
            )}
          </GlassPanel>
        </Reveal>
      </div>
    </>
  );
}
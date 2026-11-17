'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState, type DragEvent, type FormEvent } from 'react';
import { Avatar } from '@/components/avatar';
import { TextAreaField, TextField } from '@/components/field';
import { GlassPanel } from '@/components/glass';
import { IconAlert, IconSpinner, IconUpload } from '@/components/icons';
import { Reveal } from '@/components/reveal';
import { SkeletonRows, TermLoad } from '@/components/term-load';
import { useToast } from '@/components/toast';
import { api, ApiException } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import type { Profile, UserInfo } from '@/lib/types';

const AVATAR_MAX_BYTES = 128 * 1024;
const AVATAR_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];

export default function ProfilePage() {
  const { refreshUser } = useAuth();
  const { push } = useToast();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  const [nickname, setNickname] = useState('');
  const [username, setUsername] = useState('');
  const [bio, setBio] = useState('');
  const [phone, setPhone] = useState('');
  const [saving, setSaving] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const [avatarPreview, setAvatarPreview] = useState('');
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const previewUrl = useRef('');

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const p = await api<Profile>('/profile/');
      setProfile(p);
      setNickname(p.nickname);
      setUsername(p.username ?? '');
      setBio(p.bio);
      setPhone(p.phone);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    return () => {
      if (previewUrl.current) URL.revokeObjectURL(previewUrl.current);
    };
  }, [load]);

  const dirty =
    profile !== null &&
    (nickname !== profile.nickname ||
      username !== (profile.username ?? '') ||
      bio !== profile.bio ||
      phone !== profile.phone);

  const onSave = async (e: FormEvent) => {
    e.preventDefault();
    if (!profile || saving || !dirty) return;
    setSaving(true);
    setFieldErrors({});
    const body: Record<string, string> = {};
    if (nickname !== profile.nickname) body.nickname = nickname;
    if (username !== (profile.username ?? '')) body.username = username;
    if (bio !== profile.bio) body.bio = bio;
    if (phone !== profile.phone) body.phone = phone;
    try {
      const next = await api<Profile>('/profile/', { method: 'PATCH', body });
      setProfile(next);
      push('success', '资料已保存');
      void refreshUser();
    } catch (err) {
      if (err instanceof ApiException) {
        if (err.status === 409) {
          setFieldErrors({ username: err.message });
        } else if (err.message.includes('用户名')) {
          setFieldErrors({ username: err.message });
        } else if (err.message.includes('手机号')) {
          setFieldErrors({ phone: err.message });
        } else {
          push('error', '保存失败', err.message);
        }
      } else {
        push('error', '保存失败', '网络异常，请稍后重试');
      }
    } finally {
      setSaving(false);
    }
  };

  const uploadAvatar = async (file: File) => {
    if (uploading) return;
    if (!AVATAR_TYPES.includes(file.type)) {
      push('error', '格式不支持', '仅支持 JPG / PNG / WebP / GIF 图片');
      return;
    }
    if (file.size > AVATAR_MAX_BYTES) {
      push('error', '文件过大', '头像不能超过 128KB');
      return;
    }
    if (previewUrl.current) URL.revokeObjectURL(previewUrl.current);
    previewUrl.current = URL.createObjectURL(file);
    setAvatarPreview(previewUrl.current);
    setUploading(true);
    const form = new FormData();
    form.append('file', file);
    try {
      const info = await api<UserInfo>('/profile/avatar/', { method: 'POST', body: form });
      setProfile((p) => (p ? { ...p, avatar: info.avatar } : p));
      setAvatarPreview('');
      push('success', '头像已更新');
      void refreshUser();
    } catch (err) {
      setAvatarPreview('');
      push('error', '上传失败', err instanceof ApiException ? err.message : '网络异常');
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = '';
    }
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) void uploadAvatar(file);
  };

  if (loading) {
    return (
      <>
        <div className="page-head">
          <p className="kicker">ACCOUNT // 02</p>
          <h1 tabIndex={-1}>个人资料</h1>
        </div>
        <TermLoad label="loading profile" />
        <SkeletonRows n={2} />
      </>
    );
  }

  if (loadError || !profile) {
    return (
      <>
        <div className="page-head">
          <p className="kicker">ACCOUNT // 02</p>
          <h1 tabIndex={-1}>个人资料</h1>
        </div>
        <GlassPanel className="panel">
          <p className="notice notice--red">
            <IconAlert />
            资料加载失败，请刷新页面重试。
          </p>
        </GlassPanel>
      </>
    );
  }

  return (
    <>
      <div className="page-head">
        <p className="kicker">ACCOUNT // 02</p>
        <h1 tabIndex={-1}>个人资料</h1>
        <p className="page-desc">这些资料会随身份令牌提供给接入应用。邮箱更改需经安全验证，请在账户安全页操作。</p>
      </div>

      <div className="grid grid-2">
        <Reveal>
          <GlassPanel className="panel">
            <h2 className="section-title" style={{ marginTop: 0 }}>
              头像
            </h2>
            <div className="flex-col items-center gap-4">
              <Avatar src={avatarPreview || profile.avatar} name={profile.nickname} size="lg" />
              <div
                className="glass-inset w-full"
                style={{
                  padding: 'var(--sp-5)',
                  textAlign: 'center',
                  borderStyle: dragging ? 'solid' : 'dashed',
                  borderColor: dragging ? 'rgba(var(--phos-rgb), 0.6)' : undefined,
                }}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
              >
                <p className="dim small">拖拽图片到此处，或</p>
                <button
                  type="button"
                  className="btn mt-4"
                  disabled={uploading}
                  onClick={() => fileInput.current?.click()}
                >
                  {uploading ? <IconSpinner width={16} height={16} /> : <IconUpload width={16} height={16} />}
                  {uploading ? '上传中' : '选择图片'}
                </button>
                <input
                  ref={fileInput}
                  type="file"
                  accept={AVATAR_TYPES.join(',')}
                  hidden
                  aria-label="选择头像文件"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) void uploadAvatar(f);
                  }}
                />
                <p className="field-hint mt-4">JPG / PNG / WebP / GIF · ≤ 128KB · 服务端自动裁切为方形</p>
              </div>
            </div>
          </GlassPanel>
        </Reveal>

        <Reveal delay={80}>
          <GlassPanel className="panel">
            <h2 className="section-title" style={{ marginTop: 0 }}>
              基本资料
            </h2>
            <form className="auth-form" onSubmit={onSave}>
              <TextField
                label="昵称"
                value={nickname}
                maxLength={64}
                onChange={(e) => setNickname(e.target.value)}
                placeholder="展示给接入应用的名称"
              />
              <TextField
                label="用户名"
                value={username}
                maxLength={64}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="3-64 位，可用于密码登录"
                error={fieldErrors.username}
                hint="全局唯一；留空表示不设置"
              />
              <TextAreaField
                label="简介"
                value={bio}
                maxLength={280}
                onChange={(e) => setBio(e.target.value)}
                placeholder="一句话介绍自己（可选）"
                hint={`${bio.length}/280`}
              />
              <TextField
                label="手机号"
                value={phone}
                inputMode="numeric"
                maxLength={20}
                onChange={(e) => setPhone(e.target.value.replace(/\D/g, ''))}
                placeholder="选填，加密存储"
                error={fieldErrors.phone}
                hint="6-20 位数字；服务端 AES-256 加密，明文不落库"
              />
              <div className="field">
                <span className="label">邮箱</span>
                <div className="glass-inset flex items-center justify-between gap-3" style={{ padding: 'var(--sp-3) var(--sp-4)' }}>
                  <span className="mono small truncate">{profile.email || '未绑定'}</span>
                  <Link href="/account/security" className="btn btn-ghost btn-sm" style={{ flex: 'none' }}>
                    去安全页{profile.email ? '更改' : '绑定'}
                  </Link>
                </div>
              </div>
              <button type="submit" className="btn btn-primary btn-block" disabled={saving || !dirty}>
                {saving ? <IconSpinner width={16} height={16} /> : null}
                {saving ? '保存中' : dirty ? '保存修改' : '无待保存修改'}
              </button>
            </form>
          </GlassPanel>
        </Reveal>
      </div>
    </>
  );
}
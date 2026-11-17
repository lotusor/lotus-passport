import type { Provider } from './types';

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

export function fmtRelative(iso: string | null | undefined): string {
  if (!iso) return '—';
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return '—';
  const diff = Math.max(0, Date.now() - t);
  const min = Math.floor(diff / 60000);
  if (min < 1) return '刚刚';
  if (min < 60) return `${min} 分钟前`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} 小时前`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day} 天前`;
  return fmtDateTime(iso).slice(0, 10);
}

export function fmtCountdown(seconds: number): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(Math.floor(seconds / 60))}:${p(seconds % 60)}`;
}

const REASON_LABELS: Record<string, string> = {
  bad_credentials: '账号或密码错误',
  bad_email_code: '邮箱验证码错误',
  provider_comm: '第三方平台通信失败',
  no_provider_id: '无法获取第三方身份',
  bind_session: '绑定会话失效',
  bind_conflict: '第三方身份已被占用',
};

export function reasonLabel(reason: string): string {
  if (!reason) return '—';
  return REASON_LABELS[reason] ?? reason;
}

export const PROVIDER_LABELS: Record<Provider, string> = {
  github: 'GitHub',
  qq: 'QQ',
  wechat: '微信',
};

export const DEVICE_TYPE_LABELS: Record<string, string> = {
  desktop: '桌面设备',
  mobile: '手机',
  tablet: '平板',
  other: '其他设备',
};

export function initialOf(name: string): string {
  const ch = (name || '?').trim().charAt(0);
  return ch.toUpperCase();
}

export function passwordScore(pw: string): number {
  if (!pw) return 0;
  let score = 0;
  if (pw.length >= 8) score += 1;
  if (/[a-zA-Z]/.test(pw) && /\d/.test(pw)) score += 1;
  if (pw.length >= 12) score += 1;
  if (/[^a-zA-Z0-9]/.test(pw)) score += 1;
  return score;
}

export function passwordRuleError(pw: string): string | null {
  if (!pw) return '新密码不能为空';
  if (pw.length < 8) return '密码至少 8 位';
  if (!(/[a-zA-Z]/.test(pw) && /\d/.test(pw))) return '密码需同时包含字母和数字';
  return null;
}
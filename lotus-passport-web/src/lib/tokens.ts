import type { JwtClaims, TokenPair } from './types';

const KEY_ACCESS = 'lp.access';
const KEY_REFRESH = 'lp.refresh';
const KEY_PID = 'lp.pid';

function storage(): Storage | null {
  return typeof window === 'undefined' ? null : window.localStorage;
}

export function getAccess(): string {
  return storage()?.getItem(KEY_ACCESS) ?? '';
}

export function getRefresh(): string {
  return storage()?.getItem(KEY_REFRESH) ?? '';
}

export function setTokens(pair: Pick<TokenPair, 'access' | 'refresh' | 'passport_user_id'>): void {
  const s = storage();
  if (!s) return;
  s.setItem(KEY_ACCESS, pair.access);
  s.setItem(KEY_REFRESH, pair.refresh);
  s.setItem(KEY_PID, pair.passport_user_id);
}

export function setAccess(access: string): void {
  storage()?.setItem(KEY_ACCESS, access);
}

export function clearTokens(): void {
  const s = storage();
  if (!s) return;
  s.removeItem(KEY_ACCESS);
  s.removeItem(KEY_REFRESH);
  s.removeItem(KEY_PID);
}

export function decodeJwtClaims(token: string): JwtClaims | null {
  if (!token) return null;
  try {
    const part = token.split('.')[1];
    const b64 = part.replace(/-/g, '+').replace(/_/g, '/');
    const json = decodeURIComponent(
      atob(b64)
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join(''),
    );
    return JSON.parse(json) as JwtClaims;
  } catch {
    return null;
  }
}

export function accessSecondsLeft(): number {
  const claims = decodeJwtClaims(getAccess());
  if (!claims?.exp) return 0;
  return Math.max(0, Math.floor(claims.exp - Date.now() / 1000));
}
import { clearTokens, getAccess, getRefresh, setAccess } from './tokens';

export const API_BASE = '/api/v1';

export const AUTH_EXPIRED_EVENT = 'lp:auth-expired';

export class ApiException extends Error {
  status: number;
  code: number | string;
  captchaRequired: boolean;
  retryAfter?: number;

  constructor(status: number, code: number | string, message: string, extra?: { captchaRequired?: boolean; retryAfter?: number }) {
    super(message);
    this.name = 'ApiException';
    this.status = status;
    this.code = code;
    this.captchaRequired = extra?.captchaRequired ?? false;
    this.retryAfter = extra?.retryAfter;
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  auth?: boolean;
  signal?: AbortSignal;
}

let refreshInFlight: Promise<boolean> | null = null;

export function refreshSession(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = doRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

async function doRefresh(): Promise<boolean> {
  const refresh = getRefresh();
  if (!refresh) return false;
  try {
    const res = await fetch(`${API_BASE}/token/refresh/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      cache: 'no-store',
      body: JSON.stringify({ refresh }),
    });
    if (!res.ok) throw new Error(String(res.status));
    const data = (await res.json()) as { access?: string };
    if (!data.access) throw new Error('no access in refresh response');
    setAccess(data.access);
    return true;
  } catch {
    clearTokens();
    window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT));
    return false;
  }
}

async function parseError(res: Response): Promise<ApiException> {
  let code: number | string = res.status;
  let message = `请求失败（HTTP ${res.status}）`;
  let captchaRequired = false;
  let retryAfter: number | undefined;
  try {
    const data = await res.json();
    const err = data?.error;
    if (err) {
      code = err.code ?? res.status;
      message = err.message ?? message;
      captchaRequired = Boolean(err.captcha_required) || code === 'captcha_required';
      retryAfter = typeof err.retry_after === 'number' ? err.retry_after : undefined;
    } else if (typeof data?.detail === 'string') {
      message = data.detail;
    }
  } catch {
    /* 非 JSON 错误体：保留默认文案 */
  }
  return new ApiException(res.status, code, message, { captchaRequired, retryAfter });
}

export async function api<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, auth = true, signal } = opts;
  const isForm = body instanceof FormData;

  const send = async (token: string): Promise<Response> => {
    const headers: Record<string, string> = {};
    if (body !== undefined && !isForm) headers['Content-Type'] = 'application/json';
    if (auth && token) headers['Authorization'] = `Bearer ${token}`;
    return fetch(`${API_BASE}${path}`, {
      method,
      headers,
      cache: 'no-store',
      body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
      signal,
    });
  };

  let res = await send(auth ? getAccess() : '');

  if (res.status === 401 && auth && getRefresh()) {
    const ok = await refreshSession();
    if (ok) res = await send(getAccess());
  }

  if (res.status === 204) return null as T;
  if (!res.ok) throw await parseError(res);

  const text = await res.text();
  if (!text) return null as T;
  return JSON.parse(text) as T;
}
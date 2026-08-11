/**
 * 莲花通行证 — API 客户端
 *
 * 所有与 Django 后端 (lotus-passport) 的通信都通过这里。
 * 浏览器端：同源代理 (/api/... → next.config.mjs rewrites)
 * 服务端：直连 PASSPORT_API_BASE (默认 http://localhost:8000)
 */
const API_BASE =
  typeof window !== "undefined"
    ? // 浏览器端：走同源，由 next.config.mjs 的 rewrites 代理到后端。
      // 好处是没有跨域预检、cookie 同源、生产环境交给 Nginx 统一反代。
      ""
    : // 服务端渲染 / 构建期：没有同源可言，必须直连后端。
      process.env.PASSPORT_API_ORIGIN || "http://localhost:8000";

import type {
  Session,
  LoginEvent,
  AuthDevice,
  Passkey,
  Provider,
} from "@/lib/data";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
export interface UserInfo {
  passport_user_id: string;
  email: string;
  nickname: string;
  /** 后端 ProfileSerializer 返回；注销确认弹窗用它作为核对文字 */
  username: string;
  avatar: string;
  providers: string[];
  is_active: boolean;
  /** 只读派生字段：账户是否设有可用密码（§9.4f 注销 step-up 依据） */
  has_password?: boolean;
  /** 以下字段由后端 ProfileSerializer 返回，本地资料页用于回填 */
  phone?: string;
  bio?: string;
}

export interface OAuthLoginResponse {
  authorize_url: string;
}

export interface OAuthCallbackResponse {
  access: string;
  refresh: string;
  token_type: string;
  passport_user_id: string;
}

export interface TokenRefreshResponse {
  access: string;
}

export interface PasswordLoginResponse {
  access: string;
  refresh: string;
  token_type: string;
  passport_user_id: string;
}

export interface ApiError {
  error: {
    code: number | string;
    message: string;
    retry_after?: number;
    captcha_required?: boolean;
  };
}

export interface DevStatus {
  debug: boolean;
  dev_login_enabled: boolean;
  providers: string[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
export class ApiException extends Error {
  code: number;
  errorCode?: number | string;
  retryAfter?: number;
  captchaRequired?: boolean;
  constructor(
    message: string,
    code: number,
    error?: {
      code?: number | string;
      retry_after?: number;
      captcha_required?: boolean;
    }
  ) {
    super(message);
    this.name = "ApiException";
    this.code = code;
    this.errorCode = error?.code;
    this.retryAfter = error?.retry_after;
    this.captchaRequired = error?.captcha_required;
  }
}

async function request<T>(
  path: string,
  opts: RequestInit = {},
  token?: string | null
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(opts.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const url = `${API_BASE}${path}`;
  const res = await fetch(url, { ...opts, headers });

  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    let err: ApiError["error"] | undefined;
    try {
      const body: ApiError = await res.json();
      err = body.error;
      msg = body.error?.message || msg;
    } catch {
      /* fall through */
    }
    throw new ApiException(msg, res.status, err);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * 发起 OAuth 登录，返回提供商的授权链接。
 * 传入 redirectUri（通常是 `${origin}/auth/callback`）后，后端会在回调完成、
 * 签发 JWT 后把 token 以 URL fragment 的形式弹回该地址；前端 /auth/callback 负责解析。
 */
export async function getOAuthLoginUrl(
  provider: "github" | "wechat" | "qq",
  redirectUri?: string
): Promise<OAuthLoginResponse> {
  const qs = redirectUri ? `?redirect_uri=${encodeURIComponent(redirectUri)}` : "";
  return request(`/api/v1/oauth/${provider}/login/${qs}`);
}

/**
 * 密码登录（§9.4a）。公开端点，用邮箱或用户名 + 密码换取 JWT。
 * 纯 OAuth 账户（无可用密码）后端统一返回 401，不会泄露账户类型。
 */
export async function passwordLogin(
  identifier: string,
  password: string,
  captcha?: string
): Promise<PasswordLoginResponse> {
  const body: Record<string, string> = { identifier, password };
  if (captcha) body.captcha = captcha;
  return request<PasswordLoginResponse>("/api/v1/login/", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * 处理 OAuth 回调，交换 code → JWT。
 * 真实流程中浏览器会跳转到提供商的回调 URL，后端直接返回 JWT。
 * 这里提供的是前端拿到 code 后调用的方法（用于测试 / 调试）。
 */
export async function exchangeOAuthCode(
  provider: string,
  code: string,
  state: string
): Promise<OAuthCallbackResponse> {
  return request(
    `/api/v1/oauth/${provider}/callback/?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`
  );
}

/** 用 access token 获取用户身份（algo_rank 核心契约）。 */
export async function fetchUserInfo(
  token: string
): Promise<UserInfo> {
  return request("/api/v1/userinfo/", {}, token);
}

/** 刷新 access token。 */
export async function refreshAccessToken(
  refreshToken: string
): Promise<TokenRefreshResponse> {
  return request("/api/v1/token/refresh/", {
    method: "POST",
    body: JSON.stringify({ refresh: refreshToken }),
  });
}

/** 更新本人资料（§9.1）。后端 PATCH 仅接受 nickname/avatar/bio/phone，email 只读忽略。 */
export async function updateProfile(
  token: string,
  data: {
    nickname?: string;
    username?: string;
    avatar?: string;
    bio?: string;
    phone?: string;
  }
): Promise<UserInfo> {
  return request<UserInfo>(
    "/api/v1/profile/",
    {
      method: "PATCH",
      body: JSON.stringify(data),
    },
    token
  );
}

/**
 * 上传本地头像文件（§9.1）。multipart/form-data，字段名 `file`。
 * 后端校验类型与大小（≤128KB）并重压，返回最新 UserInfo（含新 avatar）。
 */
export async function uploadAvatar(token: string, file: File): Promise<UserInfo> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${API_BASE}/api/v1/profile/avatar/`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: fd,
  });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    let err: ApiError["error"] | undefined;
    try {
      const body: ApiError = await res.json();
      err = body.error;
      msg = body.error?.message || msg;
    } catch {
      /* fall through */
    }
    throw new ApiException(msg, res.status, err);
  }
  return res.json() as Promise<UserInfo>;
}

/**
 * 注销当前账户（§9.4f）。不可逆。
 *
 * 请求体固定带 `confirm: true`；当账户设有密码（`UserInfo.has_password`）时，
 * 前端必须额外带上 `current_password` 作为 step-up，否则后端返回 400。
 * 成功返回 204（无响应体），故不走通用 `request` 的 JSON 解析。
 */
export async function deleteAccount(
  token: string,
  currentPassword?: string
): Promise<void> {
  const body: Record<string, unknown> = { confirm: true };
  if (currentPassword) body.current_password = currentPassword;

  const res = await fetch(`${API_BASE}/api/v1/profile/`, {
    method: "DELETE",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const b: ApiError = await res.json();
      msg = b.error?.message || msg;
    } catch {
      /* 部分错误无 JSON 体，沿用 HTTP 状态描述 */
    }
    throw new ApiException(msg, res.status);
  }
  // 204 No Content —— 无需解析响应体
}

/** 后端 ISO 时间 → 前端展示串（YYYY-MM-DD HH:mm），失败回退「—」。 */
function fmtTs(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(
    d.getHours()
  )}:${p(d.getMinutes())}`;
}

/** 本人完整资料（§9.1）。比 /userinfo/ 多返回 phone / has_password，供资料页回填与注销 step-up 判定。 */
export async function getProfile(token: string): Promise<UserInfo> {
  return request<UserInfo>("/api/v1/profile/", {}, token);
}

/** 活跃会话列表（§9.4d）。后端注入 `current`；仅取前端展示字段。 */
export async function getSessions(token: string): Promise<Session[]> {
  const rows = await request<Array<Record<string, unknown>>>(
    "/api/v1/sessions/",
    {},
    token
  );
  return rows.map((r) => ({
    id: String(r.id),
    device: (r.device as string) || "未知设备",
    browser: (r.browser as string) || "—",
    os: (r.os as string) || "—",
    location: (r.location as string) || "未知位置",
    lastActive: fmtTs((r.last_active_at as string) ?? null),
    current: Boolean(r.current),
  }));
}

/** 注销单个会话（§9.4d）。当前会话不可注销（后端 400）。成功 204 无响应体。 */
export async function revokeSession(token: string, id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${id}/`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const b: ApiError = await res.json();
      msg = b.error?.message || msg;
    } catch {
      /* 部分错误无 JSON 体，沿用 HTTP 状态描述 */
    }
    throw new ApiException(msg, res.status);
  }
}

/** 登录历史（§9.4e）。取最近 50 条，仅映射前端展示字段。 */
export async function getLoginHistory(token: string): Promise<LoginEvent[]> {
  const rows = await request<Array<Record<string, unknown>>>(
    "/api/v1/security/login-history/",
    {},
    token
  );
  return rows.map((r) => ({
    id: String(r.id),
    time: fmtTs((r.time as string) ?? null),
    location: (r.location as string) || "未知位置",
    ip: (r.ip as string) || "—",
    device: (r.device as string) || "未知客户端",
    status: (r.status as "success" | "failed") || "success",
  }));
}

// ---------------------------------------------------------------------------
// 授权设备（§9.3）
// ---------------------------------------------------------------------------

/** 授权设备列表。后端无 `current` 标记，调用方需用当前会话自行判定「本机」。 */
export async function getDevices(token: string): Promise<AuthDevice[]> {
  const rows = await request<Array<Record<string, unknown>>>(
    "/api/v1/devices/",
    {},
    token
  );
  return rows.map((r) => ({
    id: String(r.id),
    name: (r.name as string) || "未命名设备",
    type:
      r.device_type === "mobile"
        ? "mobile"
        : r.device_type === "tablet"
          ? "tablet"
          : "desktop",
    os: (r.os as string) || "—",
    browser: (r.browser as string) || "—",
    location: (r.location as string) || "未知位置",
    lastActive: fmtTs((r.last_active_at as string) ?? null),
    current: false,
    trusted: Boolean(r.trusted),
    firstTrusted: fmtTs((r.first_trusted_at as string) ?? null),
  }));
}

/** 撤销（删除）某授权设备（§9.3）。成功 204 无响应体。 */
export async function revokeDevice(token: string, id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/devices/${id}/`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    throw new ApiException(await _errMsg(res), res.status);
  }
}

/** 切换某设备的「信任」状态（§9.3）。成功返回更新后的设备。 */
export async function setDeviceTrust(
  token: string,
  id: string,
  trusted: boolean
): Promise<void> {
  await request(
    `/api/v1/devices/${id}/`,
    { method: "PATCH", body: JSON.stringify({ trusted }) },
    token
  );
}

// ---------------------------------------------------------------------------
// 通行密钥 / WebAuthn（§9.4b）
// ---------------------------------------------------------------------------

interface RegistrationOptions {
  challenge: string;
  user: { id: string; name: string; displayName: string };
  excludeCredentials?: Array<{ id: string; type?: string; transports?: string[] }>;
  rp?: { name: string; id?: string };
  pubKeyCredParams?: unknown[];
  authenticatorSelection?: unknown;
  attestation?: string;
  timeout?: number;
  [key: string]: unknown;
}

/** 通行密钥列表（§9.4b）。 */
export async function getPasskeys(token: string): Promise<Passkey[]> {
  const data = await request<{ passkeys: Array<Record<string, unknown>> }>(
    "/api/v1/security/passkeys/",
    {},
    token
  );
  return (data.passkeys || []).map((r) => ({
    id: String(r.id),
    name: (r.name as string) || "通行密钥",
    device: (r.device as string) || "—",
    added: fmtTs((r.added_at as string) ?? null),
    lastUsed: fmtTs((r.last_used_at as string) ?? null),
  }));
}

/** 删除某通行密钥（§9.4b）。成功 204 无响应体。 */
export async function deletePasskey(token: string, id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/webauthn/${id}/`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    throw new ApiException(await _errMsg(res), res.status);
  }
}

function b64urlToBytes(s: string): Uint8Array {
  const b64 = s.replace(/-/g, "+").replace(/_/g, "/");
  const pad = b64.length % 4 ? "=".repeat(4 - (b64.length % 4)) : "";
  const bin = atob(b64 + pad);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

function bufToB64url(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function buildCreationOptions(opts: RegistrationOptions): PublicKeyCredentialCreationOptions {
  return {
    ...opts,
    challenge: b64urlToBytes(opts.challenge),
    user: { ...opts.user, id: b64urlToBytes(opts.user.id) },
    excludeCredentials: (opts.excludeCredentials || []).map((c) => ({
      ...c,
      id: b64urlToBytes(c.id),
    })),
  } as PublicKeyCredentialCreationOptions;
}

function credentialToJSON(cred: PublicKeyCredential) {
  const res = cred.response as AuthenticatorAttestationResponse;
  return {
    id: cred.id,
    rawId: bufToB64url(cred.rawId),
    type: cred.type,
    response: {
      clientDataJSON: bufToB64url(res.clientDataJSON),
      attestationObject: bufToB64url(res.attestationObject),
      transports: res.getTransports ? res.getTransports() : [],
    },
  };
}

/**
 * 注册新通行密钥（§9.4b）：向后端取注册选项 → 调浏览器 WebAuthn 仪式 →
 * 把 attestation 回传后端落库。需在用户手势（点击）中调用，否则浏览器拒绝。
 */
export async function registerPasskey(
  token: string,
  name?: string
): Promise<Passkey> {
  const opts = await request<RegistrationOptions>(
    "/api/v1/webauthn/options/register/",
    { method: "POST" },
    token
  );
  const cred = await navigator.credentials.create({
    publicKey: buildCreationOptions(opts),
  });
  if (!cred) throw new ApiException("未能创建通行密钥", 400);
  const response = credentialToJSON(cred as PublicKeyCredential);
  const pk = await request<Record<string, unknown>>(
    "/api/v1/webauthn/register/",
    { method: "POST", body: JSON.stringify({ response, name }) },
    token
  );
  return {
    id: String(pk.id),
    name: (pk.name as string) || "通行密钥",
    device: (pk.device as string) || "—",
    added: fmtTs((pk.added_at as string) ?? null),
    lastUsed: fmtTs((pk.last_used_at as string) ?? null),
  };
}

// ---------------------------------------------------------------------------
// 登录密码（§9.4a）
// ---------------------------------------------------------------------------

export interface PasswordStatus {
  has_password: boolean;
  password_changed_at: string | null;
}

/** 账户是否设有密码 + 上次修改时间（§9.4a）。 */
export async function getPasswordStatus(token: string): Promise<PasswordStatus> {
  return request<PasswordStatus>("/api/v1/security/password/", {}, token);
}

/** 设置 / 修改密码（§9.4a）。OAuth-only 账户无需 currentPassword（后端放行）。 */
export async function changePassword(
  token: string,
  newPassword: string,
  currentPassword?: string
): Promise<PasswordStatus> {
  return request<PasswordStatus>(
    "/api/v1/security/password/change/",
    {
      method: "POST",
      body: JSON.stringify({
        new_password: newPassword,
        current_password: currentPassword || "",
      }),
    },
    token
  );
}

// ---------------------------------------------------------------------------
// 关联第三方账号（§9.2）
// ---------------------------------------------------------------------------

export interface OAuthAccount {
  provider: string;
  label: string;
  linked_at: string;
}

/** 已绑定的第三方账号列表（§9.2）。 */
export async function getOAuthAccounts(token: string): Promise<OAuthAccount[]> {
  const data = await request<{ accounts: OAuthAccount[] }>(
    "/api/v1/oauth/accounts/",
    {},
    token
  );
  return data.accounts || [];
}

/** 解绑某第三方账号（§9.2）。成功 204 无响应体。 */
export async function unbindOAuth(token: string, provider: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/oauth/${provider}/`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    throw new ApiException(await _errMsg(res), res.status);
  }
}

/**
 * 发起绑定：后端返回提供商的 authorize_url，浏览器跳转完成 OAuth 后由共享回调
 * 以 `?bound=<provider>&status=success` 回跳 redirectUri。
 */
export async function getOAuthBindUrl(
  token: string,
  provider: string,
  redirectUri: string
): Promise<string> {
  const qs = `?redirect_uri=${encodeURIComponent(redirectUri)}`;
  const data = await request<{ authorize_url: string }>(
    `/api/v1/oauth/${provider}/bind/${qs}`,
    { method: "POST" },
    token
  );
  return data.authorize_url;
}

/** 从非 2xx 响应里尽量取出后端错误文案。 */
async function _errMsg(res: Response): Promise<string> {
  let msg = `HTTP ${res.status}`;
  try {
    const b: ApiError = await res.json();
    msg = b.error?.message || msg;
  } catch {
    /* 部分错误无 JSON 体 */
  }
  return msg;
}

/** 健康检查。 */
export async function healthCheck(): Promise<{
  status: string;
  service: string;
}> {
  return request("/api/v1/health/");
}

// ---------------------------------------------------------------------------
// 开发模式（后端 DEBUG=True 时才存在，生产环境这些路由直接 404）
// ---------------------------------------------------------------------------

/**
 * 探测后端是否开放了模拟登录。
 * 生产环境路由不存在 → 静默返回 disabled，不弹错。
 */
export async function fetchDevStatus(): Promise<DevStatus> {
  try {
    return await request<DevStatus>("/api/v1/dev/status/");
  } catch {
    return { debug: false, dev_login_enabled: false, providers: [] };
  }
}

/**
 * 构造模拟登录跳转地址。后端会签发真实 JWT 并 302 回 redirectUri，
 * token 放在 URL fragment 里 —— 与真实 OAuth 回调完全一致，
 * 所以 /auth/callback 页面无需任何特判。
 */
export function getDevLoginUrl(provider: string, redirectUri: string): string {
  const qs = new URLSearchParams({ provider, redirect_uri: redirectUri });
  return `${API_BASE}/api/v1/dev/login/?${qs.toString()}`;
}
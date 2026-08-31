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

/** 授权确认页所需的应用信息（GET /api/v1/oauth/consent/?ticket=）。 */
export interface OAuthConsentInfo {
  app_name: string;
  app_origin: string;
  app_logo: string;
  scopes: string[];
  provider: string;
  passport_user_id: string;
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
 *
 * 传 codeChallenge（S256）时走「授权码 + PKCE」模式（推荐）：后端在回调完成
 * 后只把一次性 code 以 `?code=` 回跳，令牌由 exchangeAuthToken() 换取，
 * 不再经 URL fragment 下发。不传时为旧 fragment 模式（过渡兼容）。
 */
export async function getOAuthLoginUrl(
  provider: "github" | "wechat" | "qq",
  redirectUri?: string,
  codeChallenge?: string
): Promise<OAuthLoginResponse> {
  const params = new URLSearchParams();
  if (redirectUri) params.set("redirect_uri", redirectUri);
  if (codeChallenge) {
    params.set("code_challenge", codeChallenge);
    params.set("code_challenge_method", "S256");
  }
  const qs = params.toString() ? `?${params.toString()}` : "";
  return request(`/api/v1/oauth/${provider}/login/${qs}`);
}

/**
 * 授权码 + PKCE 换令牌：POST /api/v1/oauth/token/ {code, code_verifier}。
 * code 由回调页 `?code=` 提供；code_verifier 由发起登录时存入 sessionStorage。
 */
export async function exchangeAuthToken(
  code: string,
  codeVerifier: string
): Promise<OAuthCallbackResponse> {
  return request<OAuthCallbackResponse>("/api/v1/oauth/token/", {
    method: "POST",
    body: JSON.stringify({ code, code_verifier: codeVerifier }),
  });
}

/**
 * 取授权确认页所需的应用信息（应用名 / 申请的权限范围）。
 * 用于外部应用接入时展示「是否授权 xxx 访问你的资料」中间页。
 */
export async function getOAuthConsentInfo(ticket: string): Promise<OAuthConsentInfo> {
  return request(`/api/v1/oauth/consent/?ticket=${encodeURIComponent(ticket)}`);
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
// 通行密钥 / WebAuthn（§9.4b）已于 2026-08-27 砍除：后端端点/模型已移除，
// 前端 API 函数与 UI 一并删除。
// ---------------------------------------------------------------------------

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
 * 构造模拟登录跳转地址。传 codeChallenge 时走授权码 + PKCE 模式
 * （与真实登录的新模式一致）；否则旧 fragment 模式。
 */
export function getDevLoginUrl(
  provider: string,
  redirectUri: string,
  codeChallenge?: string
): string {
  const qs = new URLSearchParams({ provider, redirect_uri: redirectUri });
  if (codeChallenge) {
    qs.set("code_challenge", codeChallenge);
    qs.set("code_challenge_method", "S256");
  }
  return `${API_BASE}/api/v1/dev/login/?${qs.toString()}`;
}

// ---------------------------------------------------------------------------
// 密码找回（§9.4a reset）
// ---------------------------------------------------------------------------

/** 请求密码重置邮件。未配置 SMTP 时后端返回 503（邮件服务未配置）。 */
export async function requestPasswordReset(identifier: string): Promise<void> {
  await request("/api/v1/security/password/reset-request/", {
    method: "POST",
    body: JSON.stringify({ identifier }),
  });
}

/** 用邮件里的一次性 token 设置新密码。成功后所有会话被吊销，需重新登录。 */
export async function confirmPasswordReset(
  token: string,
  newPassword: string
): Promise<void> {
  await request("/api/v1/security/password/reset/", {
    method: "POST",
    body: JSON.stringify({ token, new_password: newPassword }),
  });
}

// ---------------------------------------------------------------------------
// 邮箱验证码（2026-08-27）：登录即注册 / 首次绑定 / 更改邮箱
// ---------------------------------------------------------------------------

export type EmailCodePurpose = "login" | "bind" | "new" | "old";

/** 请求验证码。purpose 语义见后端 EmailCodeSendView（bind/new/old 需登录态）。 */
export async function sendEmailCode(
  email: string,
  purpose: EmailCodePurpose,
  token?: string | null
): Promise<void> {
  await request(
    "/api/v1/security/email/send-code/",
    { method: "POST", body: JSON.stringify({ email, purpose }) },
    token
  );
}

/** 邮箱验证码登录；无账号自动注册（返回 created 标记）。 */
export async function emailLogin(
  email: string,
  code: string
): Promise<PasswordLoginResponse & { created: boolean }> {
  return request<PasswordLoginResponse & { created: boolean }>(
    "/api/v1/login/email/",
    { method: "POST", body: JSON.stringify({ email, code }) }
  );
}

/** 首次绑定邮箱（码已发到目标新邮箱；有密码账户需 currentPassword）。 */
export async function bindEmail(
  token: string,
  email: string,
  code: string,
  currentPassword?: string
): Promise<void> {
  await request(
    "/api/v1/security/email/bind/",
    {
      method: "POST",
      body: JSON.stringify({ email, code, current_password: currentPassword || "" }),
    },
    token
  );
}

/**
 * 更改邮箱（双重验证）：newCode 发到新邮箱、oldCode 发到旧邮箱，
 * 有密码账户另需 currentPassword。三者都通过才换绑。
 */
export async function changeEmail(
  token: string,
  newEmail: string,
  newCode: string,
  oldCode: string,
  currentPassword?: string
): Promise<void> {
  await request(
    "/api/v1/security/email/change/",
    {
      method: "POST",
      body: JSON.stringify({
        new_email: newEmail,
        new_code: newCode,
        old_code: oldCode,
        current_password: currentPassword || "",
      }),
    },
    token
  );
}
// ---------- 通用（provider 无关）OAuth 登录入口 ----------
const GENERIC_TICKET_KEY = "oauth_generic_ticket";

/** 登录页读取 ?oticket= 后暂存（跨 /login/password、/login/email 子页存续） */
export function stashGenericTicket(ticket: string) {
  try {
    sessionStorage.setItem(GENERIC_TICKET_KEY, ticket);
  } catch {}
}

/**
 * 登录成功后调用：若存在通用登录票据，则用当前会话换取接入方回调地址并
 * 整页跳转。返回 true 表示已接管跳转，调用方应中止自身的路由跳转。
 */
export async function continueGenericLogin(accessToken: string): Promise<boolean> {
  const ticket = (() => {
    try {
      return sessionStorage.getItem(GENERIC_TICKET_KEY);
    } catch {
      return null;
    }
  })();
  if (!ticket || !accessToken) return false;
  try {
    const resp = await fetch(`${API_BASE}/api/v1/oauth/continue/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({ ticket }),
    });
    if (!resp.ok) return false;
    const data = (await resp.json()) as { redirect_url?: string };
    if (!data?.redirect_url) return false;
    try {
      sessionStorage.removeItem(GENERIC_TICKET_KEY);
    } catch {}
    window.location.href = data.redirect_url;
    return true;
  } catch {
    return false;
  }
}

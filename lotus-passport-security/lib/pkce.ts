/**
 * PKCE（RFC 7636）工具 — 授权码 + PKCE 登录模式。
 *
 * 发起登录时生成 code_verifier（存 sessionStorage，回调页消费后清除），
 * 把 S256(code_verifier) 作为 code_challenge 传给后端；回调页拿到一次性
 * code 后用 {code, code_verifier} 换取真正的令牌（POST /api/v1/oauth/token/），
 * 令牌从此不再经 URL fragment 下发（不进浏览器历史/Referrer）。
 */

const VERIFIER_KEY = "oauth_pkce_verifier";
const VERIFIER_COOKIE = "pp_pkce_v";

// ---- storage 兜底：部分手机浏览器跨站跳转往返会丢 sessionStorage，verifier
// ---- 双写短期第一方 cookie（SameSite=Lax，回跳为顶级导航不受影响）。
const COOKIE_MAX_AGE = 900 // 15 分钟，足够一次登录流

function setVerifierCookie(name: string, verifier: string) {
  const secure = location.protocol === "https:" ? "; Secure" : ""
  document.cookie = `${name}=${encodeURIComponent(verifier)}; max-age=${COOKIE_MAX_AGE}; path=/; SameSite=Lax${secure}`
}
function readVerifierCookie(name: string): string | null {
  const m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"))
  return m ? decodeURIComponent(m[1]) : null
}
function clearVerifierCookie(name: string) {
  const secure = location.protocol === "https:" ? "; Secure" : ""
  document.cookie = `${name}=; max-age=0; path=/; SameSite=Lax${secure}`
}


/** 生成 43-128 字符的随机 code_verifier（RFC 7636 §4.1 字符集）。 */
function randomVerifier(): string {
  const bytes = new Uint8Array(48); // 48 bytes -> 64 chars base64url
  crypto.getRandomValues(bytes);
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/** BASE64URL(SHA256(verifier)) — S256 code challenge。 */
export async function s256Challenge(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(verifier)
  );
  const bytes = new Uint8Array(digest);
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/**
 * 生成新的 PKCE 对：verifier 存 sessionStorage（key 常量），返回 challenge。
 * 回调页用 takeVerifier() 取回。
 */
export async function createPkcePair(): Promise<string> {
  const verifier = randomVerifier();
  try {
    sessionStorage.setItem(VERIFIER_KEY, verifier);
  } catch {}
  setVerifierCookie(VERIFIER_COOKIE, verifier);
  return s256Challenge(verifier);
}

/** 取回 code_verifier 并清除存储（一次性）。无 verifier 时返回 null。 */
export function takeVerifier(): string | null {
  let v: string | null = null;
  try {
    v = sessionStorage.getItem(VERIFIER_KEY);
    sessionStorage.removeItem(VERIFIER_KEY);
  } catch {}
  if (!v) v = readVerifierCookie(VERIFIER_COOKIE);
  clearVerifierCookie(VERIFIER_COOKIE);
  return v;
}

export type Role = {
  label: string;
  tone: "accent" | "success" | "warn" | "neutral";
};

export type Passkey = {
  id: string;
  name: string;
  device: string;
  added: string;
  lastUsed: string;
};

export type Session = {
  id: string;
  device: string;
  browser: string;
  os: string;
  location: string;
  lastActive: string;
  current: boolean;
};

export type LoginEvent = {
  id: string;
  time: string;
  location: string;
  ip: string;
  device: string;
  status: "success" | "failed";
};

export type Provider = {
  id: "wechat" | "qq" | "github";
  name: string;
  hint: string;
  linked: boolean;
  account?: string;
};

export type SecurityFactors = {
  password: boolean;
  monitoring: boolean;
  /** @deprecated Passkey 功能已下线，字段保留仅作兼容 */
  passkey?: boolean;
};

export const user = {
  name: "林清越",
  username: "qingyue.lin",
  passportUserId: "pp_8f3a2c91",
  email: "qingyue.lin@eacm.cn",
  initial: "林",
  verified: true,
  roles: [
    { label: "通行证用户", tone: "accent" },
    { label: "已实名认证", tone: "success" },
    { label: "学校未绑定", tone: "warn" },
  ] as Role[],
  joined: "2024-03-18",
};

/* ---- Basic profile (editable) ---- */
export const basicProfile = {
  nickname: "林清越",
  username: "qingyue.lin",
  email: "qingyue.lin@eacm.cn",
  phone: "13800006620",
  bio: "算法竞赛爱好者，关注 ICPC 与 Codeforces 区域赛。",
};

/* ---- Authorized devices (trusted login devices) ---- */
export type AuthDevice = {
  id: string;
  name: string;
  type: "desktop" | "mobile" | "tablet";
  os: string;
  browser: string;
  location: string;
  lastActive: string;
  current: boolean;
  trusted: boolean;
  firstTrusted: string;
};

export const authorizedDevices: AuthDevice[] = [
  {
    id: "d-1",
    name: "MacBook Pro",
    type: "desktop",
    os: "macOS 15.1",
    browser: "Chrome 128",
    location: "中国杭州",
    lastActive: "当前设备",
    current: true,
    trusted: true,
    firstTrusted: "2024-03-18",
  },
  {
    id: "d-2",
    name: "Pixel 9",
    type: "mobile",
    os: "Android 15",
    browser: "Chrome 128",
    location: "中国杭州",
    lastActive: "12 分钟前",
    current: false,
    trusted: true,
    firstTrusted: "2024-06-11",
  },
  {
    id: "d-3",
    name: "iPad Air",
    type: "tablet",
    os: "iPadOS 18",
    browser: "Safari 18",
    location: "中国上海",
    lastActive: "3 天前",
    current: false,
    trusted: false,
    firstTrusted: "2024-09-02",
  },
];

/* ---- OAuth clients (developer apps integrating with the passport) ---- */
export type OAuthClient = {
  id: string;
  name: string;
  description: string;
  clientId: string;
  clientSecret: string;
  redirectUris: string[];
  scopes: ("profile" | "email" | "school")[];
  status: "active" | "paused";
  created: string;
  lastUsed: string;
};

export const SCOPE_LABELS: Record<"profile" | "email" | "school", string> = {
  profile: "基础资料",
  email: "邮箱",
  school: "学校信息",
};

export const oauthClients: OAuthClient[] = [
  {
    id: "c-1",
    name: "E-algo Rank",
    description: "算法竞赛排名系统，按学校维度统计积分。",
    clientId: "lot_1a2b3c4d5e6f",
    clientSecret: "cs_live_7Qx2K9mP4vR8wL1z",
    redirectUris: ["https://rank.eacm.cn/callback"],
    scopes: ["profile", "email", "school"],
    status: "active",
    created: "2025-01-12",
    lastUsed: "2 小时前",
  },
  {
    id: "c-2",
    name: "作业评测平台",
    description: "课程作业自动评测与查重。",
    clientId: "lot_7f8e9d0c1b2a",
    clientSecret: "cs_live_3Hn6TtY8uI0oP5a",
    redirectUris: [
      "https://judge.eacm.cn/auth/callback",
      "https://judge.eacm.cn/oauth2/callback",
    ],
    scopes: ["profile", "email"],
    status: "active",
    created: "2025-04-03",
    lastUsed: "昨天",
  },
  {
    id: "c-3",
    name: "内部数据看板",
    description: "运营数据可视化看板。",
    clientId: "lot_3c4d5e6f7a8b",
    clientSecret: "cs_live_9Wq1EeR2tY4uI6o",
    redirectUris: ["https://bi.eacm.cn/login"],
    scopes: ["profile"],
    status: "paused",
    created: "2025-07-20",
    lastUsed: "12 天前",
  },
];

export const passwordState = {
  lastChanged: "2026-05-22",
  strength: "强" as "弱" | "中" | "强",
};

export const passkeys: Passkey[] = [
  {
    id: "pk-1",
    name: "MacBook Pro",
    device: "Touch ID · macOS",
    added: "2026-04-02",
    lastUsed: "2 分钟前",
  },
  {
    id: "pk-2",
    name: "Pixel 9",
    device: "屏幕指纹 · Android",
    added: "2026-06-11",
    lastUsed: "昨天 21:40",
  },
];

export const sessions: Session[] = [
  {
    id: "s-1",
    device: "MacBook Pro",
    browser: "Chrome 128 · macOS",
    os: "macOS 15.1",
    location: "中国杭州",
    lastActive: "当前会话",
    current: true,
  },
  {
    id: "s-2",
    device: "Pixel 9",
    browser: "Chrome 128 · Android",
    os: "Android 15",
    location: "中国杭州",
    lastActive: "12 分钟前",
    current: false,
  },
  {
    id: "s-3",
    device: "iPad Air",
    browser: "Safari 18 · iPadOS",
    os: "iPadOS 18",
    location: "中国上海",
    lastActive: "3 天前",
    current: false,
  },
];

export const loginHistory: LoginEvent[] = [
  {
    id: "l-1",
    time: "2026-08-04 16:20",
    location: "中国杭州",
    ip: "36.112.x.x",
    device: "Chrome · macOS",
    status: "success",
  },
  {
    id: "l-2",
    time: "2026-08-04 09:02",
    location: "中国杭州",
    ip: "36.112.x.x",
    device: "Chrome · Android",
    status: "success",
  },
  {
    id: "l-3",
    time: "2026-08-03 23:41",
    location: "未知位置",
    ip: "45.83.x.x",
    device: "未知客户端",
    status: "failed",
  },
  {
    id: "l-4",
    time: "2026-08-02 18:15",
    location: "中国上海",
    ip: "101.89.x.x",
    device: "Safari · iPadOS",
    status: "success",
  },
];

export const providers: Provider[] = [
  {
    id: "wechat",
    name: "微信",
    hint: "扫码快捷登录，绑定后可用微信一键登录",
    linked: true,
    account: "微信用户_4821",
  },
  {
    id: "qq",
    name: "QQ",
    hint: "关联 QQ 账号，支持 QQ 快捷登录",
    linked: false,
  },
  {
    id: "github",
    name: "GitHub",
    hint: "面向开发者，支持 GitHub OAuth 登录",
    linked: true,
    account: "@qingyue",
  },
];

/**
 * 前端展示层类型与常量。
 *
 * 2026-08-27 mock 收口：本文件曾有大量假数据（用户「林清越」、假 passkey/
 * sessions/loginHistory/oauthClients 等）——除 oauthClients 相关常量随 §9.5
 * 页面改为「规划中」空态一并移除外，其余 mock 已随各页面切换真实接口而删除。
 * 现在只保留仍被引用的**类型**，不再导出任何演示数据。
 */

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
};

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

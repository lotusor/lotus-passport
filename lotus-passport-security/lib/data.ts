/**
 * 前端展示层类型与常量。
 *
 * 只保留仍被页面引用的类型定义；展示数据一律来自后端 API，不在仓库内维护演示数据。
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

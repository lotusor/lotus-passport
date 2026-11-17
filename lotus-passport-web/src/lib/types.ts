export type Provider = 'github' | 'qq' | 'wechat';

export interface UserInfo {
  passport_user_id: string;
  email: string;
  username: string;
  nickname: string;
  avatar: string;
  bio: string;
  providers: Provider[];
  is_active: boolean;
}

export interface Profile {
  passport_user_id: string;
  email: string;
  username: string | null;
  nickname: string;
  avatar: string;
  bio: string;
  phone: string;
  has_password: boolean;
}

export interface TokenPair {
  access: string;
  refresh: string;
  passport_user_id: string;
  token_type: string;
  jti: string;
  created?: boolean;
}

export interface Device {
  id: number;
  name: string;
  device_type: 'desktop' | 'mobile' | 'tablet' | 'other';
  os: string;
  browser: string;
  location: string;
  trusted: boolean;
  first_trusted_at: string | null;
  last_active_at: string;
}

export interface Session {
  id: number;
  jti: string;
  device: string;
  device_type: 'desktop' | 'mobile' | 'tablet' | 'other';
  os: string;
  browser: string;
  location: string;
  ip: string;
  created_at: string;
  last_active_at: string;
  current: boolean;
}

export interface LoginEvent {
  id: number;
  time: string;
  location: string;
  ip: string;
  device: string;
  status: 'success' | 'failed';
  reason: string;
}

export interface OAuthAccountRow {
  provider: Provider;
  label: string;
  linked_at: string;
}

export interface PasswordStatus {
  has_password: boolean;
  password_changed_at: string | null;
}

export interface ConsentInfo {
  app_name: string;
  app_origin: string;
  app_logo: string;
  scopes: string[];
  provider: Provider;
  passport_user_id: string;
}

export interface DevStatus {
  debug: boolean;
  dev_login_enabled: boolean;
  providers: Provider[];
}

export interface JwtClaims {
  exp?: number;
  iat?: number;
  jti?: string;
  passport_user_id?: string;
  email?: string;
  nickname?: string;
}
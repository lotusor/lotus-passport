/**
 * Type declarations for lotus-passport.
 *
 * Hand-written rather than generated: the runtime is plain ESM with no build
 * step, so integrators get types without the SDK needing a compiler in CI.
 */

export declare class PassportError extends Error {}
export declare class PassportConfigError extends PassportError {}
export declare class PassportServiceError extends PassportError {
  statusCode?: number;
  constructor(message: string, statusCode?: number);
}
export declare class JWKSError extends PassportServiceError {}
export declare class TokenError extends PassportError {}
export declare class TokenExpiredError extends TokenError {}
export declare class TokenInvalidError extends TokenError {}
export declare class UnknownSigningKeyError extends TokenInvalidError {}

export interface PassportIdentity {
  /** Stable UUID issued by passport. Store this on your local user row. */
  passportUserId: string;
  email: string;
  nickname: string;
  /** Only populated by `getUserinfo()`. */
  avatar: string;
  /** Only populated by `getUserinfo()`. */
  providers: string[];
  claims: Record<string, any>;
  source: 'jwt' | 'userinfo';
  expiresAt: Date | null;
}

export interface TokenPair {
  access: string;
  refresh: string;
  tokenType: string;
}

export interface JWKSCacheOptions {
  /** Freshness window in ms. Default 600000. */
  ttl?: number;
  /** Minimum ms between forced (unknown-kid) refreshes. Default 30000. */
  cooldown?: number;
  /** Fetch timeout in ms. Default 5000. */
  timeout?: number;
  fetchImpl?: typeof fetch;
  now?: () => number;
}

export declare class JWKSCache {
  jwksUrl: string;
  readonly isFresh: boolean;
  constructor(jwksUrl: string, options?: JWKSCacheOptions);
  keyIds(): string[];
  clear(): void;
  getKey(kid?: string): Promise<CryptoKey>;
  refresh(): Promise<void>;
}

export declare function parseJwks(document: {
  keys?: Array<Record<string, unknown>>;
}): Promise<Map<string, CryptoKey>>;

export interface PassportClientOptions {
  /** Expected `iss`. `null` disables the check. Default `'lotus-passport'`. */
  issuer?: string | null;
  /** Expected `aud`. Omit to skip the check. */
  audience?: string;
  /** Accepted algorithms. Symmetric ones and `none` are rejected. */
  algorithms?: string[];
  /** Clock skew tolerance in **seconds**. Default 30. */
  clockTolerance?: number;
  /** JWKS cache lifetime in ms. Default 600000. */
  cacheTtl?: number;
  /** Unknown-kid refresh throttle in ms. Default 30000. */
  cooldown?: number;
  /** HTTP timeout in ms. Default 5000. */
  timeout?: number;
  fetchImpl?: typeof fetch;
  jwksUrl?: string;
  userinfoUrl?: string;
  refreshUrl?: string;
}

export declare class PassportClient {
  readonly baseUrl: string;
  issuer: string | null;
  audience?: string;
  algorithms: string[];
  jwksUrl: string;
  userinfoUrl: string;
  refreshUrl: string;
  configurationUrl: string;
  jwks: JWKSCache;

  constructor(baseUrl: string, options?: PassportClientOptions);

  discover(): Promise<Record<string, any>>;
  verifyToken(token: string, options?: { requiredClaims?: string[] }): Promise<PassportIdentity>;
  verifyHeader(authorization?: string | null): Promise<PassportIdentity>;
  getUserinfo(token: string, options?: { verifyFirst?: boolean }): Promise<PassportIdentity>;
  refresh(refreshToken: string): Promise<TokenPair>;

  static extractBearer(authorization?: string | null): string | null;
}

export declare function createPassportClient(
  baseUrl: string,
  options?: PassportClientOptions,
): PassportClient;

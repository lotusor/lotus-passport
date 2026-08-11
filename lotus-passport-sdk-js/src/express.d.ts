import type { PassportClient, PassportIdentity } from './index.js';

export interface PassportAuthOptions {
  /** Allow anonymous requests through with `req.passport === null`. */
  optional?: boolean;
  /** Also call `/userinfo` for avatar + linked providers (adds a round-trip). */
  online?: boolean;
}

/** Express middleware that verifies the Bearer token and sets `req.passport`. */
export declare function passportAuth(
  client: PassportClient,
  options?: PassportAuthOptions,
): (req: any, res: any, next: (err?: unknown) => void) => void;

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace Express {
    interface Request {
      passport?: PassportIdentity | null;
    }
  }
}

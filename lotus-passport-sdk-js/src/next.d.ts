import type { PassportClient, PassportIdentity } from './index.js';

/** Verify the Bearer token on a Request; throws on failure. */
export declare function requireIdentity(
  client: PassportClient,
  request: Request,
): Promise<PassportIdentity>;

/** Like `requireIdentity` but returns `null` for anonymous callers. */
export declare function optionalIdentity(
  client: PassportClient,
  request: Request,
): Promise<PassportIdentity | null>;

/** Map an SDK error to 401 (token problem) or 503 (passport unreachable). */
export declare function toErrorResponse(error: unknown): Response;

/** Guard for `middleware.ts`; resolves to `undefined` when the request may pass. */
export declare function passportMiddleware(
  client: PassportClient,
  request: Request,
): Promise<Response | undefined>;

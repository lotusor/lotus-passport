/**
 * Next.js helpers (App Router — Route Handlers, Server Actions, Middleware).
 *
 * Everything here is Edge-runtime safe: verification uses WebCrypto only, no
 * Node built-ins, no `jose`.
 *
 * Route Handler:
 * ```ts
 * import { requireIdentity, toErrorResponse } from 'lotus-passport/next';
 *
 * export async function GET(req: Request) {
 *   try {
 *     const identity = await requireIdentity(passport, req);
 *     return Response.json({ id: identity.passportUserId });
 *   } catch (err) {
 *     return toErrorResponse(err);
 *   }
 * }
 * ```
 *
 * @module lotus-passport/next
 */
import {
  PassportClient,
  PassportServiceError,
  TokenError,
  TokenExpiredError,
  TokenInvalidError,
} from './index.js';

/**
 * Verify the Bearer token on a standard `Request`.
 *
 * @param {PassportClient} client
 * @param {Request} request
 * @returns {Promise<import('./index.js').PassportIdentity>}
 * @throws {TokenInvalidError|TokenExpiredError|PassportServiceError}
 */
export async function requireIdentity(client, request) {
  const header = request.headers.get('authorization');
  const token = PassportClient.extractBearer(header);
  if (!token) throw new TokenInvalidError('缺少 Authorization: Bearer 令牌');
  return client.verifyToken(token);
}

/**
 * Same as {@link requireIdentity} but returns `null` for anonymous callers.
 *
 * @param {PassportClient} client
 * @param {Request} request
 * @returns {Promise<import('./index.js').PassportIdentity|null>}
 */
export async function optionalIdentity(client, request) {
  const token = PassportClient.extractBearer(request.headers.get('authorization'));
  if (!token) return null;
  try {
    return await client.verifyToken(token);
  } catch (err) {
    if (err instanceof TokenError) return null;
    throw err; // a passport outage is not "anonymous" — let it surface
  }
}

/**
 * Turn an SDK error into the right HTTP response.
 *
 * Token problems -> 401. Passport unreachable -> 503. Getting this wrong is how
 * an auth-server blip turns into "everyone got logged out".
 *
 * @param {unknown} error
 * @returns {Response}
 */
export function toErrorResponse(error) {
  if (error instanceof TokenExpiredError) {
    return Response.json(
      { error: { code: 401, message: '访问令牌已过期，请刷新' } },
      { status: 401, headers: { 'WWW-Authenticate': 'Bearer' } },
    );
  }
  if (error instanceof TokenError) {
    return Response.json(
      { error: { code: 401, message: `令牌无效: ${error.message}` } },
      { status: 401, headers: { 'WWW-Authenticate': 'Bearer' } },
    );
  }
  if (error instanceof PassportServiceError) {
    return Response.json(
      { error: { code: 503, message: `认证中心暂时不可用: ${error.message}` } },
      { status: 503 },
    );
  }
  return Response.json({ error: { code: 500, message: '服务器内部错误' } }, { status: 500 });
}

/**
 * Guard for `middleware.ts`. Returns `undefined` to let the request through.
 *
 * Note: middleware runs on *every* matched request, so keep the client at module
 * scope — a per-request client means a JWKS fetch per request.
 *
 * @param {PassportClient} client
 * @param {Request} request
 * @returns {Promise<Response|undefined>}
 */
export async function passportMiddleware(client, request) {
  try {
    await requireIdentity(client, request);
    return undefined;
  } catch (err) {
    return toErrorResponse(err);
  }
}

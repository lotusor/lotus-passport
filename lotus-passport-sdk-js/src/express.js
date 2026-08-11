/**
 * Express / Connect middleware.
 *
 * ```js
 * import express from 'express';
 * import { createPassportClient } from 'lotus-passport';
 * import { passportAuth } from 'lotus-passport/express';
 *
 * const passport = createPassportClient('https://passport.eacm.cn');
 * const app = express();
 *
 * app.get('/me', passportAuth(passport), (req, res) => {
 *   res.json({ id: req.passport.passportUserId });
 * });
 * ```
 *
 * @module lotus-passport/express
 */
import { PassportClient, PassportServiceError, TokenError, TokenExpiredError } from './index.js';

/**
 * Build middleware that verifies the Bearer token and sets `req.passport`.
 *
 * @param {PassportClient} client Shared client (module scope — one JWKS cache).
 * @param {object} [options]
 * @param {boolean} [options.optional=false] Allow anonymous (`req.passport = null`).
 * @param {boolean} [options.online=false] Also call `/userinfo` (adds a round-trip).
 * @returns {(req: any, res: any, next: Function) => void}
 */
export function passportAuth(client, options = {}) {
  const { optional = false, online = false } = options;

  return async function passportAuthMiddleware(req, res, next) {
    const token = PassportClient.extractBearer(req.headers?.authorization);
    if (!token) {
      if (optional) {
        req.passport = null;
        return next();
      }
      return res
        .status(401)
        .set('WWW-Authenticate', 'Bearer')
        .json({ error: { code: 401, message: '缺少 Authorization: Bearer 令牌' } });
    }

    try {
      req.passport = online ? await client.getUserinfo(token) : await client.verifyToken(token);
      return next();
    } catch (err) {
      if (err instanceof TokenExpiredError) {
        return res
          .status(401)
          .set('WWW-Authenticate', 'Bearer')
          .json({ error: { code: 401, message: '访问令牌已过期，请刷新' } });
      }
      if (err instanceof TokenError) {
        return res
          .status(401)
          .set('WWW-Authenticate', 'Bearer')
          .json({ error: { code: 401, message: `令牌无效: ${err.message}` } });
      }
      if (err instanceof PassportServiceError) {
        // 503, not 401 — the credential may be perfectly fine.
        return res
          .status(503)
          .json({ error: { code: 503, message: `认证中心暂时不可用: ${err.message}` } });
      }
      return next(err);
    }
  };
}

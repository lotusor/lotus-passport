/**
 * Lotus Passport SDK for JavaScript / TypeScript.
 *
 * Zero runtime dependencies — on purpose. Verification runs on the WebCrypto API
 * that ships with Node 18+, Deno, Bun, Cloudflare Workers, the Next.js Edge
 * runtime and browsers. Pulling in `jose` would have been less code here, but it
 * would also mean every integrator inherits our version pin and bundle weight
 * for what amounts to ~150 lines of RSASSA verification.
 *
 * @module lotus-passport
 */

// --------------------------------------------------------------------------- //
// errors
// --------------------------------------------------------------------------- //

/** Base class for every SDK failure. */
export class PassportError extends Error {
  constructor(message) {
    super(message);
    this.name = new.target.name;
  }
}

/** The SDK itself is misconfigured. */
export class PassportConfigError extends PassportError {}

/**
 * Passport was reachable but unusable (down, 5xx, malformed JWKS).
 * Map this to **503**, never 401 — otherwise an outage logs everyone out.
 */
export class PassportServiceError extends PassportError {
  constructor(message, statusCode) {
    super(message);
    this.statusCode = statusCode;
  }
}

/** JWKS could not be fetched or parsed. */
export class JWKSError extends PassportServiceError {}

/** The presented token is not acceptable. Always maps to **401**. */
export class TokenError extends PassportError {}

/** Signature is valid but `exp` has passed — the client should refresh. */
export class TokenExpiredError extends TokenError {}

/** Malformed, wrong signature, wrong issuer/audience, or unusable header. */
export class TokenInvalidError extends TokenError {}

/** The token's `kid` is not in the JWKS, even after a forced refresh. */
export class UnknownSigningKeyError extends TokenInvalidError {}

// --------------------------------------------------------------------------- //
// base64url / encoding helpers
// --------------------------------------------------------------------------- //
const textEncoder = new TextEncoder();
const textDecoder = new TextDecoder();

function base64UrlToBytes(value) {
  const normalised = value.replace(/-/g, '+').replace(/_/g, '/');
  const padded = normalised + '='.repeat((4 - (normalised.length % 4)) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function decodeJsonSegment(segment, label) {
  try {
    return JSON.parse(textDecoder.decode(base64UrlToBytes(segment)));
  } catch (err) {
    throw new TokenInvalidError(`malformed token ${label}: ${err.message}`);
  }
}

// --------------------------------------------------------------------------- //
// JWKS cache
// --------------------------------------------------------------------------- //
const ALLOWED_KTY = new Set(['RSA']);

/**
 * Caches the signing keys published by passport.
 *
 * Same three guarantees as the Python SDK: cache on the hot path, pick up key
 * rotation without a redeploy, and throttle the unknown-`kid` refresh so a flood
 * of forged tokens cannot be amplified into a JWKS flood against passport.
 */
export class JWKSCache {
  /**
   * @param {string} jwksUrl Absolute JWKS URL.
   * @param {object} [options]
   * @param {number} [options.ttl=600000] Freshness window in ms.
   * @param {number} [options.cooldown=30000] Minimum ms between forced refreshes.
   * @param {number} [options.timeout=5000] Fetch timeout in ms.
   * @param {typeof fetch} [options.fetchImpl] Custom fetch (tests, proxies, tracing).
   * @param {() => number} [options.now] Injectable clock.
   */
  constructor(jwksUrl, options = {}) {
    this.jwksUrl = jwksUrl;
    this.ttl = options.ttl ?? 600_000;
    this.cooldown = options.cooldown ?? 30_000;
    this.timeout = options.timeout ?? 5_000;
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch;
    this.now = options.now ?? (() => Date.now());

    /** @type {Map<string, CryptoKey>} */
    this.keys = new Map();
    this.fetchedAt = null;
    this.lastForced = Number.NEGATIVE_INFINITY;
    /** @type {Promise<void>|null} in-flight refresh, so N concurrent requests cause 1 fetch */
    this.inflight = null;
  }

  get isFresh() {
    return this.fetchedAt !== null && this.now() - this.fetchedAt < this.ttl;
  }

  keyIds() {
    return [...this.keys.keys()].sort();
  }

  clear() {
    this.keys.clear();
    this.fetchedAt = null;
  }

  /**
   * Resolve the verification key for a `kid`.
   *
   * @param {string|undefined} kid
   * @returns {Promise<CryptoKey>}
   * @throws {UnknownSigningKeyError} kid absent even after a forced refresh.
   * @throws {JWKSError} the document could not be fetched or parsed.
   */
  async getKey(kid) {
    if (!this.isFresh) await this.#refresh({ soft: true });

    let key = this.#lookup(kid);
    if (key) return key;

    if (this.now() - this.lastForced >= this.cooldown) {
      await this.#refresh({ soft: false });
      key = this.#lookup(kid);
      if (key) return key;
    }

    throw new UnknownSigningKeyError(
      `No signing key for kid=${JSON.stringify(kid)}. Known kids: ` +
        `${this.keyIds().join(', ') || '<empty>'}. Either the token came from another ` +
        'issuer, or key rotation has not propagated yet.',
    );
  }

  /** Force a refresh regardless of TTL. */
  async refresh() {
    await this.#refresh({ soft: false, throttle: false });
  }

  #lookup(kid) {
    if (kid) return this.keys.get(kid);
    if (this.keys.size === 1) return [...this.keys.values()][0];
    return undefined;
  }

  async #refresh({ soft, throttle = true }) {
    // Coalesce concurrent refreshes — a cold start with 200 in-flight requests
    // must not fire 200 JWKS fetches.
    if (this.inflight) return this.inflight;
    if (throttle) this.lastForced = this.now();

    this.inflight = (async () => {
      let document;
      try {
        const response = await this.#fetchJson(this.jwksUrl);
        if (response.status !== 200 || !response.body) {
          throw new JWKSError(
            `JWKS endpoint ${this.jwksUrl} returned HTTP ${response.status}`,
            response.status,
          );
        }
        document = response.body;
      } catch (err) {
        if (soft && this.keys.size > 0) return; // keep the warm cache during a blip
        throw err instanceof JWKSError ? err : new JWKSError(`JWKS fetch failed: ${err.message}`);
      }

      const parsed = await parseJwks(document);
      if (parsed.size === 0) {
        if (soft && this.keys.size > 0) return;
        throw new JWKSError(`JWKS document at ${this.jwksUrl} contains no usable key.`);
      }
      this.keys = parsed;
      this.fetchedAt = this.now();
    })().finally(() => {
      this.inflight = null;
    });

    return this.inflight;
  }

  async #fetchJson(url) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeout);
    try {
      const res = await this.fetchImpl(url, { signal: controller.signal });
      let body = null;
      try {
        body = await res.json();
      } catch {
        body = null;
      }
      return { status: res.status, body };
    } finally {
      clearTimeout(timer);
    }
  }
}

/**
 * Turn a JWKS document into importable CryptoKeys.
 *
 * `oct` (symmetric) and `use: "enc"` entries are dropped: a shared secret in a
 * *public* document is either a mistake or an attack, and an encryption key must
 * never be allowed to verify a signature.
 *
 * @param {{keys?: Array<Record<string, unknown>>}} document
 * @returns {Promise<Map<string, CryptoKey>>}
 */
export async function parseJwks(document) {
  const out = new Map();
  for (const entry of document?.keys ?? []) {
    if (!entry || typeof entry !== 'object') continue;
    if (!ALLOWED_KTY.has(entry.kty)) continue;
    if (entry.use !== undefined && entry.use !== 'sig') continue;
    try {
      const key = await crypto.subtle.importKey(
        'jwk',
        { kty: 'RSA', n: entry.n, e: entry.e, alg: 'RS256', ext: true },
        { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
        false,
        ['verify'],
      );
      out.set(entry.kid ?? '', key);
    } catch {
      // A single unusable key must not invalidate the whole set.
    }
  }
  return out;
}

// --------------------------------------------------------------------------- //
// client
// --------------------------------------------------------------------------- //
const DEFAULT_ALGORITHMS = ['RS256'];
const FORBIDDEN_ALGORITHMS = new Set(['none', 'HS256', 'HS384', 'HS512']);

/**
 * @typedef {object} PassportIdentity
 * @property {string} passportUserId Stable UUID — your join key.
 * @property {string} email
 * @property {string} nickname
 * @property {string} avatar Only populated by `getUserinfo()`.
 * @property {string[]} providers Only populated by `getUserinfo()`.
 * @property {Record<string, any>} claims Raw verified payload.
 * @property {'jwt'|'userinfo'} source
 * @property {Date|null} expiresAt
 */

function identityFromClaims(claims) {
  return {
    passportUserId: String(claims.passport_user_id ?? ''),
    email: claims.email ?? '',
    nickname: claims.nickname ?? '',
    avatar: '',
    providers: [],
    claims,
    source: 'jwt',
    expiresAt: claims.exp ? new Date(claims.exp * 1000) : null,
  };
}

function identityFromUserinfo(body, claims = {}) {
  return {
    passportUserId: String(body.passport_user_id ?? ''),
    email: body.email ?? '',
    nickname: body.nickname ?? '',
    avatar: body.avatar ?? '',
    providers: body.providers ?? [],
    claims,
    source: 'userinfo',
    expiresAt: claims.exp ? new Date(claims.exp * 1000) : null,
  };
}

/** Verify and resolve Lotus Passport identities. */
export class PassportClient {
  /**
   * @param {string} baseUrl e.g. `https://passport.eacm.cn`
   * @param {object} [options]
   * @param {string|null} [options.issuer='lotus-passport'] Expected `iss`; `null` disables the check.
   * @param {string} [options.audience] Expected `aud`; omit to skip.
   * @param {string[]} [options.algorithms=['RS256']]
   * @param {number} [options.clockTolerance=30] Skew tolerance in **seconds**.
   * @param {number} [options.cacheTtl=600000] JWKS cache lifetime in ms.
   * @param {number} [options.cooldown=30000] Unknown-kid refresh throttle in ms.
   * @param {number} [options.timeout=5000] HTTP timeout in ms.
   * @param {typeof fetch} [options.fetchImpl]
   * @param {string} [options.jwksUrl]
   * @param {string} [options.userinfoUrl]
   * @param {string} [options.refreshUrl]
   */
  constructor(baseUrl, options = {}) {
    if (!baseUrl || !baseUrl.trim()) {
      throw new PassportConfigError('baseUrl is required, e.g. https://passport.eacm.cn');
    }
    const algorithms = options.algorithms ?? DEFAULT_ALGORITHMS;
    const bad = algorithms.filter((a) => FORBIDDEN_ALGORITHMS.has(a));
    if (bad.length) {
      throw new PassportConfigError(
        `Refusing to accept ${JSON.stringify(bad)}. Passport signs with RS256; accepting a ` +
          'symmetric or "none" algorithm here would let anyone forge tokens with the public key.',
      );
    }

    this.baseUrl = baseUrl.replace(/\/+$/, '');
    this.issuer = options.issuer === undefined ? 'lotus-passport' : options.issuer;
    this.audience = options.audience;
    this.algorithms = algorithms;
    this.clockTolerance = options.clockTolerance ?? 30;
    this.timeout = options.timeout ?? 5_000;
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch;

    this.jwksUrl = options.jwksUrl ?? `${this.baseUrl}/.well-known/jwks.json`;
    this.userinfoUrl = options.userinfoUrl ?? `${this.baseUrl}/api/v1/userinfo/`;
    this.refreshUrl = options.refreshUrl ?? `${this.baseUrl}/api/v1/token/refresh/`;
    this.configurationUrl = `${this.baseUrl}/.well-known/passport-configuration`;

    this.jwks = new JWKSCache(this.jwksUrl, {
      ttl: options.cacheTtl,
      cooldown: options.cooldown,
      timeout: this.timeout,
      fetchImpl: this.fetchImpl,
    });
  }

  /**
   * Pull `/.well-known/passport-configuration` and adopt its endpoints.
   * @returns {Promise<Record<string, any>>}
   */
  async discover() {
    const { status, body } = await this.#request('GET', this.configurationUrl);
    if (status !== 200 || !body) {
      throw new PassportServiceError(
        `Discovery failed: ${this.configurationUrl} returned HTTP ${status}`,
        status,
      );
    }
    if (body.jwks_uri) {
      this.jwksUrl = body.jwks_uri;
      this.jwks.jwksUrl = body.jwks_uri;
      this.jwks.clear();
    }
    if (body.userinfo_endpoint) this.userinfoUrl = body.userinfo_endpoint;
    if (body.token_refresh_endpoint) this.refreshUrl = body.token_refresh_endpoint;
    if (body.issuer && this.issuer !== null) this.issuer = body.issuer;
    return body;
  }

  /**
   * Verify an access token offline.
   *
   * @param {string} token Raw JWT, no `Bearer ` prefix.
   * @param {object} [options]
   * @param {string[]} [options.requiredClaims=['passport_user_id']]
   * @returns {Promise<PassportIdentity>}
   */
  async verifyToken(token, options = {}) {
    const requiredClaims = options.requiredClaims ?? ['passport_user_id'];
    if (typeof token !== 'string' || !token) throw new TokenInvalidError('empty token');

    const parts = token.split('.');
    if (parts.length !== 3) throw new TokenInvalidError('token is not a compact JWS');
    const [headerB64, payloadB64, signatureB64] = parts;

    const header = decodeJsonSegment(headerB64, 'header');
    // Pin the algorithm from our allow-list, never from the header — trusting
    // header.alg is the textbook algorithm-confusion vulnerability.
    if (!this.algorithms.includes(header.alg)) {
      throw new TokenInvalidError(
        `unexpected alg=${JSON.stringify(header.alg)}; this client only accepts ` +
          `${JSON.stringify(this.algorithms)}`,
      );
    }

    const key = await this.jwks.getKey(header.kid);
    const valid = await crypto.subtle.verify(
      { name: 'RSASSA-PKCS1-v1_5' },
      key,
      base64UrlToBytes(signatureB64),
      textEncoder.encode(`${headerB64}.${payloadB64}`),
    );
    if (!valid) throw new TokenInvalidError('signature verification failed');

    const claims = decodeJsonSegment(payloadB64, 'payload');
    this.#validateClaims(claims, requiredClaims);
    return identityFromClaims(claims);
  }

  #validateClaims(claims, requiredClaims) {
    const now = Math.floor(Date.now() / 1000);
    const skew = this.clockTolerance;

    if (typeof claims.exp !== 'number') {
      throw new TokenInvalidError('token has no exp claim — refusing a non-expiring credential');
    }
    if (now - skew >= claims.exp) {
      throw new TokenExpiredError('access token expired; use the refresh token');
    }
    if (typeof claims.nbf === 'number' && now + skew < claims.nbf) {
      throw new TokenInvalidError('token is not valid yet (nbf)');
    }
    if (this.issuer !== null && claims.iss !== this.issuer) {
      throw new TokenInvalidError(
        `issuer mismatch: expected ${JSON.stringify(this.issuer)}, got ${JSON.stringify(claims.iss)}`,
      );
    }
    if (this.audience !== undefined) {
      const aud = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
      if (!aud.includes(this.audience)) {
        throw new TokenInvalidError(`audience mismatch: expected ${this.audience}`);
      }
    }
    for (const claim of requiredClaims) {
      if (!claims[claim]) throw new TokenInvalidError(`missing required claim: ${claim}`);
    }
  }

  /**
   * Verify a raw `Authorization` header value.
   * @param {string|null|undefined} authorization
   * @returns {Promise<PassportIdentity>}
   */
  async verifyHeader(authorization) {
    const token = PassportClient.extractBearer(authorization);
    if (!token) throw new TokenInvalidError('missing or malformed Authorization: Bearer header');
    return this.verifyToken(token);
  }

  /**
   * @param {string|null|undefined} authorization
   * @returns {string|null}
   */
  static extractBearer(authorization) {
    if (!authorization) return null;
    const parts = authorization.split(/\s+/).filter(Boolean);
    if (parts.length !== 2 || parts[0].toLowerCase() !== 'bearer') return null;
    return parts[1];
  }

  /**
   * Resolve the full profile from passport (network call).
   * @param {string} token
   * @param {{verifyFirst?: boolean}} [options]
   * @returns {Promise<PassportIdentity>}
   */
  async getUserinfo(token, options = {}) {
    const verifyFirst = options.verifyFirst ?? true;
    let claims = {};
    if (verifyFirst) claims = (await this.verifyToken(token)).claims;

    const { status, body } = await this.#request('GET', this.userinfoUrl, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (status === 401 || status === 403) {
      throw new TokenInvalidError(`passport rejected the token (HTTP ${status})`);
    }
    if (status !== 200 || !body) {
      throw new PassportServiceError(`userinfo failed: HTTP ${status}`, status);
    }
    return identityFromUserinfo(body, claims);
  }

  /**
   * Exchange a refresh token for a new access token.
   * @param {string} refreshToken
   * @returns {Promise<{access: string, refresh: string, tokenType: string}>}
   */
  async refresh(refreshToken) {
    const { status, body } = await this.#request('POST', this.refreshUrl, {
      body: { refresh: refreshToken },
    });
    if (status === 400 || status === 401) {
      throw new TokenInvalidError('refresh token rejected; the user must log in again');
    }
    if (status !== 200 || !body?.access) {
      throw new PassportServiceError(`refresh failed: HTTP ${status}`, status);
    }
    return {
      access: body.access,
      refresh: body.refresh ?? refreshToken,
      tokenType: body.token_type ?? 'Bearer',
    };
  }

  async #request(method, url, { headers = {}, body } = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeout);
    try {
      const res = await this.fetchImpl(url, {
        method,
        signal: controller.signal,
        headers: body ? { 'Content-Type': 'application/json', ...headers } : headers,
        body: body ? JSON.stringify(body) : undefined,
      });
      let parsed = null;
      try {
        parsed = await res.json();
      } catch {
        parsed = null;
      }
      return { status: res.status, body: parsed };
    } catch (err) {
      throw new PassportServiceError(`${method} ${url} failed: ${err.message}`);
    } finally {
      clearTimeout(timer);
    }
  }
}

/**
 * Convenience factory.
 * @param {string} baseUrl
 * @param {object} [options]
 * @returns {PassportClient}
 */
export function createPassportClient(baseUrl, options) {
  return new PassportClient(baseUrl, options);
}

/**
 * Offline test suite — runs with `node --test`, no npm install, no server.
 *
 * Keys are generated in-process with `node:crypto`, published through a stub
 * `fetch`, and used to mint tokens. That makes the nasty cases (forged kid,
 * algorithm confusion, rotation, passport outage) trivially reproducible.
 */
import assert from 'node:assert/strict';
import { createHmac, createSign, generateKeyPairSync } from 'node:crypto';
import test, { describe } from 'node:test';

import {
  PassportClient,
  PassportConfigError,
  PassportServiceError,
  TokenExpiredError,
  TokenInvalidError,
  UnknownSigningKeyError,
} from '../src/index.js';

const ISSUER = 'lotus-passport';
const PASSPORT_ID = '11111111-1111-1111-1111-111111111111';
const JWKS_URL = 'https://passport.test/.well-known/jwks.json';
const USERINFO_URL = 'https://passport.test/api/v1/userinfo/';
const REFRESH_URL = 'https://passport.test/api/v1/token/refresh/';

const b64 = (input) => Buffer.from(input).toString('base64url');

class KeyPair {
  constructor(kid) {
    this.kid = kid;
    const { privateKey, publicKey } = generateKeyPairSync('rsa', { modulusLength: 2048 });
    this.privateKey = privateKey;
    this.publicKey = publicKey;
  }

  jwk() {
    const { n, e } = this.publicKey.export({ format: 'jwk' });
    return { kty: 'RSA', use: 'sig', alg: 'RS256', kid: this.kid, n, e };
  }

  sign(overrides = {}, { kid = this.kid, ttl = 300, issuer = ISSUER } = {}) {
    const now = Math.floor(Date.now() / 1000);
    const payload = {
      token_type: 'access',
      user_id: '1',
      passport_user_id: PASSPORT_ID,
      email: 'sdk@lotus.local',
      nickname: 'sdk-tester',
      iat: now,
      exp: now + ttl,
      ...(issuer ? { iss: issuer } : {}),
      ...overrides,
    };
    const header = b64(JSON.stringify({ alg: 'RS256', typ: 'JWT', ...(kid ? { kid } : {}) }));
    const body = b64(JSON.stringify(payload));
    const signer = createSign('RSA-SHA256');
    signer.update(`${header}.${body}`);
    return `${header}.${body}.${signer.sign(this.privateKey).toString('base64url')}`;
  }
}

/** Minimal scriptable fetch. Counts JWKS hits so caching bugs are visible. */
function makeFetch(keys) {
  const state = {
    jwks: { status: 200, body: { keys } },
    routes: new Map(),
    jwksFetches: 0,
    calls: [],
    failNextJwks: false,
    lastBody: null,
  };

  const impl = async (url, init = {}) => {
    state.calls.push(`${init.method ?? 'GET'} ${url}`);
    if (init.body) state.lastBody = JSON.parse(init.body);
    if (String(url).endsWith('jwks.json')) {
      state.jwksFetches += 1;
      if (state.failNextJwks) {
        state.failNextJwks = false;
        throw new Error('passport unreachable');
      }
      return respond(state.jwks);
    }
    const route = state.routes.get(String(url));
    return respond(route ?? { status: 404, body: { error: 'not found' } });
  };

  const respond = ({ status, body }) => ({
    status,
    json: async () => {
      if (body === null || body === undefined) throw new Error('not json');
      return body;
    },
  });

  impl.state = state;
  return impl;
}

const primary = new KeyPair('lotus-passport-rsa-1');
const rotated = new KeyPair('lotus-passport-rsa-2');

function makeClient(fetchImpl, options = {}) {
  return new PassportClient('https://passport.test', {
    fetchImpl,
    issuer: ISSUER,
    cooldown: 0,
    ...options,
  });
}

// --------------------------------------------------------------------------- //
describe('verifyToken — happy path', () => {
  test('verifies a genuine token', async () => {
    const f = makeFetch([primary.jwk()]);
    const identity = await makeClient(f).verifyToken(primary.sign());

    assert.equal(identity.passportUserId, PASSPORT_ID);
    assert.equal(identity.email, 'sdk@lotus.local');
    assert.equal(identity.source, 'jwt');
    assert.ok(identity.expiresAt instanceof Date);
  });

  test('is offline after the first JWKS fetch', async () => {
    const f = makeFetch([primary.jwk()]);
    const client = makeClient(f);
    for (let i = 0; i < 10; i += 1) await client.verifyToken(primary.sign());
    assert.equal(f.state.jwksFetches, 1);
  });

  test('coalesces concurrent cold-start fetches', async () => {
    const f = makeFetch([primary.jwk()]);
    const client = makeClient(f);
    await Promise.all(Array.from({ length: 20 }, () => client.verifyToken(primary.sign())));
    assert.equal(f.state.jwksFetches, 1, 'a cold start must not fire one fetch per request');
  });

  test('derives the stock endpoint layout', () => {
    const client = new PassportClient('https://passport.eacm.cn/');
    assert.equal(client.jwksUrl, 'https://passport.eacm.cn/.well-known/jwks.json');
    assert.equal(client.userinfoUrl, 'https://passport.eacm.cn/api/v1/userinfo/');
    assert.equal(client.refreshUrl, 'https://passport.eacm.cn/api/v1/token/refresh/');
  });
});

describe('verifyToken — rejections', () => {
  test('expired token', async () => {
    const f = makeFetch([primary.jwk()]);
    await assert.rejects(
      () => makeClient(f, { clockTolerance: 0 }).verifyToken(primary.sign({}, { ttl: -60 })),
      TokenExpiredError,
    );
  });

  test('clock tolerance absorbs small skew', async () => {
    const f = makeFetch([primary.jwk()]);
    const identity = await makeClient(f, { clockTolerance: 60 }).verifyToken(
      primary.sign({}, { ttl: -10 }),
    );
    assert.equal(identity.passportUserId, PASSPORT_ID);
  });

  test('token signed by a key outside the JWKS', async () => {
    const f = makeFetch([primary.jwk()]);
    await assert.rejects(() => makeClient(f).verifyToken(rotated.sign()), UnknownSigningKeyError);
  });

  test('key substitution — attacker key, our kid', async () => {
    const f = makeFetch([primary.jwk()]);
    await assert.rejects(
      () => makeClient(f).verifyToken(rotated.sign({}, { kid: primary.kid })),
      TokenInvalidError,
    );
  });

  test('alg=none is rejected before any key lookup', async () => {
    const f = makeFetch([primary.jwk()]);
    const header = b64(JSON.stringify({ alg: 'none', typ: 'JWT', kid: primary.kid }));
    const body = b64(
      JSON.stringify({ passport_user_id: 'x', exp: Math.floor(Date.now() / 1000) + 300 }),
    );
    await assert.rejects(() => makeClient(f).verifyToken(`${header}.${body}.`), TokenInvalidError);
    assert.equal(f.state.jwksFetches, 0);
  });

  test('HS256 confusion using the public key as the secret', async () => {
    const f = makeFetch([primary.jwk()]);
    const pem = primary.publicKey.export({ type: 'spki', format: 'pem' });
    const header = b64(JSON.stringify({ alg: 'HS256', typ: 'JWT', kid: primary.kid }));
    const body = b64(
      JSON.stringify({
        passport_user_id: 'x',
        exp: Math.floor(Date.now() / 1000) + 300,
        iss: ISSUER,
      }),
    );
    const sig = createHmac('sha256', pem).update(`${header}.${body}`).digest('base64url');
    await assert.rejects(
      () => makeClient(f).verifyToken(`${header}.${body}.${sig}`),
      TokenInvalidError,
    );
  });

  test('constructor refuses unsafe algorithms', () => {
    assert.throws(
      () => new PassportClient('https://passport.test', { algorithms: ['RS256', 'HS256'] }),
      PassportConfigError,
    );
    assert.throws(() => new PassportClient(''), PassportConfigError);
  });

  test('issuer mismatch', async () => {
    const f = makeFetch([primary.jwk()]);
    await assert.rejects(
      () => makeClient(f).verifyToken(primary.sign({}, { issuer: 'evil-idp' })),
      TokenInvalidError,
    );
  });

  test('audience is enforced when configured', async () => {
    const f = makeFetch([primary.jwk()]);
    const client = makeClient(f, { audience: 'algo-rank' });
    assert.ok(await client.verifyToken(primary.sign({ aud: 'algo-rank' })));
    await assert.rejects(
      () => client.verifyToken(primary.sign({ aud: 'other-app' })),
      TokenInvalidError,
    );
    await assert.rejects(() => client.verifyToken(primary.sign()), TokenInvalidError);
  });

  test('a token with no exp is refused', async () => {
    const f = makeFetch([primary.jwk()]);
    const header = b64(JSON.stringify({ alg: 'RS256', typ: 'JWT', kid: primary.kid }));
    const body = b64(JSON.stringify({ passport_user_id: 'x', iss: ISSUER }));
    const signer = createSign('RSA-SHA256');
    signer.update(`${header}.${body}`);
    const token = `${header}.${body}.${signer.sign(primary.privateKey).toString('base64url')}`;
    await assert.rejects(() => makeClient(f).verifyToken(token), TokenInvalidError);
  });

  test('missing required claim', async () => {
    const f = makeFetch([primary.jwk()]);
    await assert.rejects(
      () => makeClient(f).verifyToken(primary.sign({ passport_user_id: '' })),
      TokenInvalidError,
    );
  });

  test('garbage input', async () => {
    const f = makeFetch([primary.jwk()]);
    const client = makeClient(f);
    for (const bad of ['', 'not-a-jwt', 'a.b.c']) {
      await assert.rejects(() => client.verifyToken(bad), TokenInvalidError);
    }
  });
});

describe('JWKS cache', () => {
  test('unknown kid forces exactly one refresh, then is throttled', async () => {
    const f = makeFetch([primary.jwk()]);
    const client = makeClient(f, { cooldown: 60_000 });
    await client.verifyToken(primary.sign()); // warm
    const baseline = f.state.jwksFetches;

    for (let i = 0; i < 20; i += 1) {
      await assert.rejects(
        () => client.verifyToken(rotated.sign({}, { kid: `forged-${i}` })),
        UnknownSigningKeyError,
      );
    }
    assert.ok(f.state.jwksFetches - baseline <= 1, 'throttle failed — attacker can amplify');
  });

  test('rotation is picked up without a restart', async () => {
    const f = makeFetch([primary.jwk()]);
    const client = makeClient(f);
    await client.verifyToken(primary.sign());

    f.state.jwks = { status: 200, body: { keys: [primary.jwk(), rotated.jwk()] } };
    const identity = await client.verifyToken(rotated.sign());
    assert.equal(identity.passportUserId, PASSPORT_ID);
  });

  test('a warm cache survives an outage', async () => {
    const f = makeFetch([primary.jwk()]);
    const client = makeClient(f, { cacheTtl: 0 }); // always stale -> always refresh
    await client.verifyToken(primary.sign());

    f.state.failNextJwks = true;
    assert.ok(await client.verifyToken(primary.sign()));
  });

  test('a cold cache outage surfaces as a service error', async () => {
    const f = makeFetch([primary.jwk()]);
    f.state.failNextJwks = true;
    await assert.rejects(() => makeClient(f).verifyToken(primary.sign()), PassportServiceError);
  });

  test('symmetric and encryption keys in the JWKS are ignored', async () => {
    const f = makeFetch([
      { kty: 'oct', kid: 'sneaky', k: 'c2VjcmV0', alg: 'HS256' },
      { ...primary.jwk(), kid: 'enc-key', use: 'enc' },
      primary.jwk(),
    ]);
    const client = makeClient(f);
    await client.verifyToken(primary.sign());
    assert.deepEqual(client.jwks.keyIds(), [primary.kid]);
  });
});

describe('header parsing', () => {
  test('extractBearer', () => {
    assert.equal(PassportClient.extractBearer('Bearer abc'), 'abc');
    assert.equal(PassportClient.extractBearer('bearer abc'), 'abc');
    assert.equal(PassportClient.extractBearer('Basic abc'), null);
    assert.equal(PassportClient.extractBearer('Bearer'), null);
    assert.equal(PassportClient.extractBearer(''), null);
    assert.equal(PassportClient.extractBearer(undefined), null);
  });

  test('verifyHeader', async () => {
    const f = makeFetch([primary.jwk()]);
    const client = makeClient(f);
    assert.ok(await client.verifyHeader(`Bearer ${primary.sign()}`));
    await assert.rejects(() => client.verifyHeader('Basic zzz'), TokenInvalidError);
  });
});

describe('online endpoints', () => {
  test('getUserinfo returns avatar + providers', async () => {
    const f = makeFetch([primary.jwk()]);
    f.state.routes.set(USERINFO_URL, {
      status: 200,
      body: {
        passport_user_id: PASSPORT_ID,
        email: 'sdk@lotus.local',
        nickname: 'sdk-tester',
        avatar: 'https://cdn/avatar.png',
        providers: ['github'],
      },
    });
    const identity = await makeClient(f).getUserinfo(primary.sign());
    assert.equal(identity.avatar, 'https://cdn/avatar.png');
    assert.deepEqual(identity.providers, ['github']);
    assert.equal(identity.source, 'userinfo');
  });

  test('getUserinfo verifies before spending a round-trip', async () => {
    const f = makeFetch([primary.jwk()]);
    await assert.rejects(
      () => makeClient(f).getUserinfo(rotated.sign()),
      UnknownSigningKeyError,
    );
    assert.ok(!f.state.calls.includes(`GET ${USERINFO_URL}`));
  });

  test('getUserinfo 401 is a token error, 500 is a service error', async () => {
    const f = makeFetch([primary.jwk()]);
    const client = makeClient(f);
    f.state.routes.set(USERINFO_URL, { status: 401, body: { error: 'nope' } });
    await assert.rejects(() => client.getUserinfo(primary.sign()), TokenInvalidError);

    f.state.routes.set(USERINFO_URL, { status: 500, body: null });
    await assert.rejects(() => client.getUserinfo(primary.sign()), PassportServiceError);
  });

  test('refresh', async () => {
    const f = makeFetch([primary.jwk()]);
    f.state.routes.set(REFRESH_URL, {
      status: 200,
      body: { access: 'new-access', refresh: 'new-refresh' },
    });
    const pair = await makeClient(f).refresh('old-refresh');
    assert.equal(pair.access, 'new-access');
    assert.deepEqual(f.state.lastBody, { refresh: 'old-refresh' });
  });

  test('refresh rejection', async () => {
    const f = makeFetch([primary.jwk()]);
    f.state.routes.set(REFRESH_URL, { status: 401, body: { detail: 'expired' } });
    await assert.rejects(() => makeClient(f).refresh('dead'), TokenInvalidError);
  });
});

describe('discovery', () => {
  test('adopts the advertised endpoints', async () => {
    const f = makeFetch([primary.jwk()]);
    f.state.routes.set('https://passport.test/.well-known/passport-configuration', {
      status: 200,
      body: {
        issuer: ISSUER,
        jwks_uri: 'https://cdn.test/keys/jwks.json',
        userinfo_endpoint: 'https://passport.test/api/v2/userinfo/',
      },
    });
    const client = makeClient(f);
    await client.discover();
    assert.equal(client.jwksUrl, 'https://cdn.test/keys/jwks.json');
    assert.equal(client.jwks.jwksUrl, 'https://cdn.test/keys/jwks.json');
    assert.ok(client.userinfoUrl.endsWith('/api/v2/userinfo/'));
  });

  test('missing discovery document is a service error', async () => {
    const f = makeFetch([primary.jwk()]);
    await assert.rejects(() => makeClient(f).discover(), PassportServiceError);
  });
});

assert.equal(JWKS_URL, 'https://passport.test/.well-known/jwks.json');

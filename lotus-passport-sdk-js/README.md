# lotus-passport (JavaScript / TypeScript)

Verify **Lotus Passport** unified-auth JWTs (RS256 + JWKS) in Node, Next.js, Deno,
Bun and Edge runtimes — **zero dependencies**, pure [WebCrypto](https://developer.mozilla.org/docs/Web/API/Web_Crypto_API).

- No `jose`, no Node built-ins — runs on **Node ≥ 18, Edge, Deno, Bun**
- RS256 verification against the public **JWKS** (`/.well-known/jwks.json`)
- **Offline** by default: `verifyToken()` does zero network I/O on the hot path
- **Algorithm-confusion safe**: accepted algorithm is pinned from an allow-list,
  never read from the token. `none` / `HS256/384/512` are rejected at construction.
- **Outage resilient**: a passport blip becomes `503`, not a mass-401 logout
- Adapters for **Express** and **Next.js** (App Router: Route Handlers + Middleware)

```bash
npm install lotus-passport
# or: pnpm add lotus-passport / yarn add lotus-passport / deno add npm:lotus-passport
```

---

## 1. Quickstart

```js
import { createPassportClient } from 'lotus-passport';

// One client per process — it owns the JWKS cache.
const passport = createPassportClient('https://passport.eacm.cn');

const identity = await passport.verifyToken(accessToken); // raw token, no "Bearer "
console.log(identity.passportUserId);  // your stable join key (UUID)
console.log(identity.email, identity.nickname);

// TypeScript:
// import type { PassportIdentity } from 'lotus-passport';
```

---

## 2. Two verification modes

| Method | Network | Use for |
|--------|---------|---------|
| `verifyToken(token)` | **None** (cached JWKS) | Every request — fast, survives passport outages |
| `getUserinfo(token)` | 1 round-trip to `/api/v1/userinfo/` | First sight of a user (avatar + providers), explicit refresh |

```js
const identity = await passport.verifyToken(token);     // offline
const full = await passport.getUserinfo(token);          // online enrichment
console.log(full.avatar, full.providers);
```

---

## 3. Framework adapters

### Express

```js
import express from 'express';
import { createPassportClient } from 'lotus-passport';
import { passportAuth } from 'lotus-passport/express';

const passport = createPassportClient('https://passport.eacm.cn');
const app = express();

app.get('/me', passportAuth(passport), (req, res) => {
  res.json({ passportUserId: req.passport.passportUserId });
});

// { online: true } also calls /userinfo; { optional: true } allows anonymous.
app.get('/profile', passportAuth(passport, { online: true }), (req, res) => {
  res.json({ avatar: req.passport.avatar });
});
```

### Next.js (App Router)

```ts
// app/api/me/route.ts
import { requireIdentity, toErrorResponse } from 'lotus-passport/next';

const passport = createPassportClient('https://passport.eacm.cn');

export async function GET(req: Request) {
  try {
    const identity = await requireIdentity(passport, req);
    return Response.json({ passportUserId: identity.passportUserId });
  } catch (err) {
    return toErrorResponse(err); // 401 bad token, 503 passport down
  }
}
```

`requireIdentity` / `optionalIdentity` / `toErrorResponse` / `passportMiddleware`
are all **Edge-runtime safe** (WebCrypto only).

---

## 4. Configuration

```js
createPassportClient(baseUrl, {
  issuer: 'lotus-passport',   // pin iss; null disables the check (legacy only)
  audience: undefined,        // expected aud; omit to skip
  algorithms: ['RS256'],      // symmetric algs rejected at construction
  clockTolerance: 30,         // skew tolerance in SECONDS (exp/nbf)
  cacheTtl: 600_000,          // JWKS cache lifetime in MS
  cooldown: 30_000,           // unknown-kid refresh throttle in MS (anti-DoS)
  timeout: 5_000,             // HTTP timeout in MS
  fetchImpl: globalThis.fetch,// inject a custom fetch (tests, proxies)
});
```

Endpoints are derived from `baseUrl` (`/.well-known/jwks.json`,
`/api/v1/userinfo/`, `/api/v1/token/refresh/`) and can be adopted at runtime via
`await passport.discover()` (reads `/.well-known/passport-configuration`).

---

## 5. Security model

| Threat | Defense |
|--------|---------|
| **Algorithm confusion** (`alg:none`, `HS256` w/ public key) | Accepted algorithms pinned from an allow-list at construction; token `alg` never trusted. Symmetric algs → `PassportConfigError`. |
| **Forged `kid` amplification DoS** | Unknown `kid` triggers a *throttled* refresh; concurrent cold starts coalesce onto one in-flight fetch. |
| **Replay from another RS256 issuer** | `iss` pinned (`issuer`). Foreign-issuer tokens rejected. |
| **Mass logout on passport outage** | JWKS cached (TTL) and survives short outages; only genuine token problems → 401, service problems → 503. |
| **Stale/symmetric keys in JWKS** | `oct` and `use:enc` keys dropped before use. |

---

## 6. Error → HTTP mapping

| Error | Meaning | HTTP |
|-------|---------|------|
| `TokenExpiredError` | `exp` passed | **401** |
| `TokenInvalidError` / `UnknownSigningKeyError` | malformed / wrong `iss` / bad signature / unknown `kid` | **401** |
| `PassportServiceError` / `JWKSError` | passport/JWKS unreachable | **503** |
| `PassportConfigError` | bad config (empty `baseUrl`, unsafe `algorithms`) | — (thrown at construction) |

Adapters translate these automatically: **401 for token problems, 503 for service
problems**.

---

## 7. Examples

Runnable samples in [`examples/`](./examples):

- `express_example.js` — protected Express API (`npm i express` to run)
- `next_example.js` — Next.js Route Handlers + Middleware (App Router)

```bash
node examples/express_example.js
```

---

## 8. Testing

```bash
npm test        # node --test, fully offline (self-generated RSA keys)
```

The suite covers algorithm-confusion rejection, key rotation, outage-grade
resilience, throttle/coalescing, and both adapters — with no network access.

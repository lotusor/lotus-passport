// Minimal Next.js App Router integration with Lotus Passport (RS256 + JWKS).
//
// Everything here is Edge-runtime safe: verification uses WebCrypto only (no Node
// built-ins, no `jose`). Copy the parts you need into your app.
//
// Importing by package name works because this file lives inside the SDK repo;
// in a consumer app it's just `npm i lotus-passport`.

import {
  PassportClient,
  createPassportClient,
  TokenError,
  TokenExpiredError,
} from 'lotus-passport';
import {
  requireIdentity,
  optionalIdentity,
  toErrorResponse,
  passportMiddleware,
} from 'lotus-passport/next';

// Module-scope client — the JWKS cache must be shared across requests.
const passport = createPassportClient('https://passport.eacm.cn');

// --------------------------------------------------------------------------- //
// app/api/me/route.js
// --------------------------------------------------------------------------- //
export async function GET(req) {
  try {
    const identity = await requireIdentity(passport, req);
    return Response.json({ passportUserId: identity.passportUserId });
  } catch (err) {
    return toErrorResponse(err); // 401 bad token, 503 passport down
  }
}

// --------------------------------------------------------------------------- //
// app/api/profile/route.js  (offline verify, then online lookup for avatar)
// --------------------------------------------------------------------------- //
export async function POST(req) {
  const token = PassportClient.extractBearer(req.headers.get('authorization'));
  if (!token) return toErrorResponse(new TokenError('missing token'));
  try {
    await passport.verifyToken(token); // cheap offline check first
    const full = await passport.getUserinfo(token); // enrich with avatar/providers
    return Response.json({ passportUserId: full.passportUserId, avatar: full.avatar });
  } catch (err) {
    return toErrorResponse(err);
  }
}

// --------------------------------------------------------------------------- //
// app/api/public/route.js  (anonymous allowed)
// --------------------------------------------------------------------------- //
export async function GET_PUBLIC(req) {
  const identity = await optionalIdentity(passport, req);
  if (!identity) return Response.json({ who: 'anonymous' });
  return Response.json({ passportUserId: identity.passportUserId });
}

// --------------------------------------------------------------------------- //
// middleware.ts  (guard selected routes)
// --------------------------------------------------------------------------- //
export async function middleware(req) {
  return passportMiddleware(passport, req);
}

// export const config = { matcher: ['/dashboard/:path*'] };

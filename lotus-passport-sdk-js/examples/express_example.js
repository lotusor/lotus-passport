// Minimal Express API protected by Lotus Passport (RS256 + JWKS).
//
// This file imports the SDK by package name ("lotus-passport") — Node 18+ resolves
// it to ../src via the package "exports" map, so it runs straight from this repo.
// For a consumer project, `npm i lotus-passport` and the same imports work.
//
// Run (from the repo root):
//     npm i express        # peer dep, only for this example
//     node examples/express_example.js
//
// Then:
//     curl -H "Authorization: Bearer <token>" http://127.0.0.1:3000/me

import express from 'express';
import { createPassportClient } from 'lotus-passport';
import { passportAuth } from 'lotus-passport/express';

// One shared client at module scope — it owns the JWKS cache. Reusing it means a
// JWKS fetch only on first unknown `kid` / rotation, not per request.
const passport = createPassportClient('https://passport.eacm.cn');

const app = express();

// PassportAuth sets req.passport to a verified identity, or returns 401/503.
app.get('/me', passportAuth(passport), (req, res) => {
  res.json({ passportUserId: req.passport.passportUserId, email: req.passport.email });
});

// online:true also calls /userinfo for avatar + linked providers (one extra hop).
app.get('/profile', passportAuth(passport, { online: true }), (req, res) => {
  res.json({ passportUserId: req.passport.passportUserId, avatar: req.passport.avatar });
});

// optional:true lets anonymous requests through (req.passport === null).
app.get('/public', passportAuth(passport, { optional: true }), (req, res) => {
  if (!req.passport) return res.json({ who: 'anonymous' });
  res.json({ passportUserId: req.passport.passportUserId });
});

app.listen(3000, () => console.log('listening on http://127.0.0.1:3000'));

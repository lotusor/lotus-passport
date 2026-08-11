# ---- Lotus Passport Security (Next.js SPA) — production image ----
#
# The app ships a server-side proxy route (app/api/v1/[...path]/route.ts) that
# forwards browser calls to the passport backend, so it MUST run as a Node
# server (`next start`). `next export` / static hosting is NOT an option —
# route handlers cannot be exported. Configure PASSPORT_API_ORIGIN at runtime.
#
# Multi-stage: deps -> builder -> runner.
# NODE_ENV is deliberately NOT set before `npm ci`: npm treats
# NODE_ENV=production as --omit=dev, which would strip typescript / tailwind /
# postcss (all devDependencies) and break `next build`.

# ---- deps: full install (incl. devDependencies) from the lockfile ---------- #
FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
# `npm ci` is lockfile-exact and fails loudly if package.json drifts from it.
RUN npm ci

# ---- builder: compile, then drop dev deps from node_modules --------------- #
FROM node:22-slim AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build \
    && npm prune --omit=dev

# ---- runner: lean runtime, non-root --------------------------------------- #
FROM node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

# Only what `next start` needs: prod node_modules + build output + config + public assets.
COPY --from=builder --chown=node:node /app/node_modules ./node_modules
COPY --from=builder --chown=node:node /app/.next ./.next
COPY --from=builder --chown=node:node /app/public ./public
COPY --from=builder --chown=node:node /app/package.json ./package.json
COPY --from=builder --chown=node:node /app/next.config.mjs ./next.config.mjs

USER node
EXPOSE 3000
CMD ["npm", "run", "start"]

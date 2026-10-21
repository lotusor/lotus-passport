#!/bin/sh
# Lotus Passport container entrypoint.
# Responsibilities (in order):
#   1. Block until PostgreSQL is reachable (avoids "migrate before DB is up").
#   2. Ensure an RS256 keypair exists (first boot only) — see note below.
#   3. Collect static (whitenoise serves them from inside gunicorn).
#   4. Apply migrations (idempotent — safe to run on every container start).
#   5. exec the CMD (gunicorn) so it receives SIGTERM/SIGINT for graceful shutdown.
set -e

# Only wait when we're actually on Postgres. SQLite dev images can skip this.
if [ -n "$DATABASE_URL" ] && echo "$DATABASE_URL" | grep -q "postgres"; then
  # Parse host/port out of postgres://user:pass@host:port/db
  _host=$(echo "$DATABASE_URL" | sed -E 's#.*@([^:/]+).*#\1#')
  _port=$(echo "$DATABASE_URL" | sed -E 's#.*:([0-9]+)/.*#\1#')
  _host="${_host:-db}"
  _port="${_port:-5432}"
  echo "entrypoint: waiting for PostgreSQL at ${_host}:${_port} ..."
  # shellcheck disable=SC2034
  until python - <<PY
import socket, sys
try:
    socket.create_connection(("${_host}", ${_port}), timeout=2)
except OSError:
    sys.exit(1)
sys.exit(0)
PY
  do
    sleep 1
  done
  echo "entrypoint: PostgreSQL is reachable."
fi

# RS256 signing keys.
#   * Env-PEM deployments (PASSPORT_JWT_PRIVATE_KEY set) manage keys externally.
#   * HS256 deployments (JWT_USE_RS256=False) need no keypair at all.
#   * Otherwise the keys live in /app/keys, which docker-compose backs with the
#     `passport_keys` named volume so they SURVIVE container recreation. The
#     command is idempotent: it only writes on the very first boot.
#   BACK UP THAT VOLUME. Losing it invalidates every outstanding token and
#   breaks offline (JWKS-cached) verification for integrators.
if [ -z "$PASSPORT_JWT_PRIVATE_KEY" ] && [ "$JWT_USE_RS256" != "False" ] \
   && [ "$JWT_USE_RS256" != "false" ] && [ "$JWT_USE_RS256" != "0" ]; then
  python manage.py generate_keys
fi

# Static assets served by whitenoise from inside gunicorn.
python manage.py collectstatic --noinput || true

# Apply schema migrations. Running on every start is safe and keeps
# rolling deploys/auto-recovery consistent without a separate migrate step.
python manage.py migrate --noinput

exec "$@"

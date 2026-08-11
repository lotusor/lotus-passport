# ---- Lotus Passport — production image ----
FROM python:3.13-slim

# Unbuffered + no .pyc keeps logs streaming and the image layer clean.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=passport.settings

WORKDIR /app

# Run as a non-root user. The app never needs root, so a compromise is contained.
RUN useradd --create-home --uid 10001 appuser

# Install deps first (best layer caching — only reinstalled when the lock changes).
# requirements.lock.txt pins exact versions for reproducible production builds.
COPY requirements.lock.txt /app/
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.lock.txt

# Copy source. Secrets ({.env,keys/,*.pem,db.*}) are excluded via .dockerignore
# and are therefore NOT present in the build context — they reach the container
# only through env_file / environment at runtime.
COPY . /app/

# Static assets served by whitenoise from inside gunicorn.
#
# JWT_USE_RS256=False is REQUIRED here: with RS256 on and no keys present, the
# DEBUG-default settings path would auto-generate an RSA keypair *during the
# build* and bake the private key into an image layer — shared by every
# deployment pulling that image. Forcing the HS256 branch keeps the build
# key-free; the real keypair is created at runtime (entrypoint) into the
# mounted `keys` volume, or supplied via PASSPORT_JWT_PRIVATE_KEY.
RUN JWT_USE_RS256=False python manage.py collectstatic --noinput || true

# `keys/` must exist and be owned by appuser BEFORE a named volume is mounted
# over it — Docker seeds a fresh named volume from the image path, ownership
# included. Without this the volume lands root-owned and generate_keys fails.
RUN mkdir -p /app/keys && chmod 700 /app/keys

# media/（用户上传头像等）：与 keys/ 同理——在镜像里先建好并随 /app 一起 chown 成
# appuser，这样挂载的 passport_media 命名卷会以正确属主播种；否则卷会落到 root，
# 而 gunicorn 以 appuser 运行，头像上传会 500。
RUN mkdir -p /app/media/avatars

# Entrypoint waits for Postgres, generates keys if missing, migrates, exec's CMD.
COPY docker/entrypoint.sh /app/docker/entrypoint.sh
RUN chmod +x /app/docker/entrypoint.sh \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "passport.wsgi:application", "-c", "gunicorn.conf.py"]

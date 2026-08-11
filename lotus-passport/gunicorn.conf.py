"""Gunicorn configuration for Lotus Passport."""
import multiprocessing
import os

bind = "0.0.0.0:8000"
workers = int(os.getenv("GUNICORN_WORKERS", str(max(2, multiprocessing.cpu_count() + 1))))
keepalive = 65
timeout = 60
graceful_timeout = 30
worker_class = "sync"

# Trust X-Forwarded-* headers coming from the nginx reverse proxy on the same
# Docker network. Without this, Django sees every request as coming from nginx
# and SECURE_PROXY_SSL_HEADER / request.is_secure() would be wrong.
forwarded_allow_ips = "*"
proxy_allow_ips = "*"

accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOGLEVEL", "info")

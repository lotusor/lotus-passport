"""Gunicorn configuration for Lotus Passport."""
import multiprocessing
import os

# 只监听回环：nginx（host 网络）反代 127.0.0.1:8000，公网一律走 443 vhost。
# 绑 0.0.0.0 会让直连 IP:8000 的请求绕过 TLS 终结、限流前置与响应头注入。
bind = "127.0.0.1:8000"
workers = int(os.getenv("GUNICORN_WORKERS", str(max(2, multiprocessing.cpu_count() + 1))))
keepalive = 65
timeout = 60
graceful_timeout = 30
worker_class = "sync"

# 只信任本机 nginx 注入的 X-Forwarded-*。写 "*" 时任何对端都能用自带的
# X-Forwarded-For 伪造 REMOTE_ADDR，从而绕过按 IP 的限流与登录锁定。
forwarded_allow_ips = "127.0.0.1"
proxy_allow_ips = "127.0.0.1"

accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOGLEVEL", "info")

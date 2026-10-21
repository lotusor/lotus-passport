"""Trusted reverse-proxy IP normalisation (security hardening §一.E).

Without this, any client can forge ``X-Forwarded-For`` and thus spoof the IP
that lands in audit/device tables and rate-limit keys. We only trust
``X-Forwarded-For`` when the *immediate* peer (``REMOTE_ADDR``) is a configured
trusted proxy; otherwise we strip the header and fall back to ``REMOTE_ADDR``.

This must run before anything else reads ``REMOTE_ADDR`` / ``X-Forwarded-For``,
so it is registered first in ``MIDDLEWARE``.
"""
from __future__ import annotations

import ipaddress

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin


class TrustedProxyMiddleware(MiddlewareMixin):
    def __init__(self, get_response=None):
        super().__init__(get_response)
        self.cidrs: list[ipaddress._BaseNetwork] = []
        for raw in getattr(settings, "TRUSTED_PROXY_CIDRS", []):
            raw = (raw or "").strip()
            if not raw:
                continue
            try:
                self.cidrs.append(ipaddress.ip_network(raw, strict=False))
            except ValueError:
                continue

    @staticmethod
    def _trusted(remote: str, cidrs: list[ipaddress._BaseNetwork]) -> bool:
        try:
            return any(ipaddress.ip_address(remote) in net for net in cidrs)
        except ValueError:
            return False

    def process_request(self, request):
        remote = request.META.get("REMOTE_ADDR", "")
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if self._trusted(remote, self.cidrs) and xff:
            # XFF 追加语义下「哪一段是真实客户端」取决于可信代理层数。
            # 稳健做法：从最后一跳向前回溯、跳过可信代理 IP，第一个非可信
            # 地址即真实客户端——既兼容多层可信代理，又防止客户端伪造首段
            # 污染限流与登录审计。
            hops = [h.strip() for h in xff.split(",") if h.strip()]
            real = hops[-1] if hops else remote
            for hop in reversed(hops):
                if not self._trusted(hop, self.cidrs):
                    real = hop
                    break
            request.META["REMOTE_ADDR"] = real
        else:
            # Untrusted peer: never believe a client-supplied XFF.
            request.META.pop("HTTP_X_FORWARDED_FOR", None)

"""
IP → 地理位置解析（§9.3 / §9.4d / §9.4e）。

登录时把客户端 IP 解析成「省 市」写入 Session / LoginEvent / TrustedDevice 的
location 字段，供前端「登录设备 / 登录历史」展示真实地理位置。

设计要点：
* 默认走**国内中文 IP 库**（pconline → ip-api 中文 兜底），返回「广东 广州」式
  中文省市，契合前端的中文界面。两条都是免密钥的公开 HTTP 接口。
* **内存缓存 + 超时降级**：同一 IP 24h 内只查一次，单次请求超时 0.8s；任何失败
  （网络/限流/解析异常）都优雅回退到 ""（前端展示为「未知位置」），绝不阻断登录。
* 私有/保留地址（127/10/172.16-31/192.168/::1）直接返回 ""，不发请求。
* 可在 settings 用 GEOIP_ENABLED=False 整体关闭（回归「未知位置」行为）。
"""
from __future__ import annotations

import ipaddress
import json
import logging
import threading
import time
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_CACHE_TTL = 60 * 60 * 24  # 24h
_HTTP_TIMEOUT = 0.8  # 秒，单次地理查询上限
_UA = {"User-Agent": "lotus-passport/1.0 (+geo)"}

_CACHE: dict[str, tuple[float, str]] = {}
_LOCK = threading.Lock()


def _is_private(ip: str) -> bool:
    """True 表示私有/保留/环回地址，无需（也无法）查地理库。"""
    if not ip:
        return True
    try:
        net = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return (
        net.is_private
        or net.is_loopback
        or net.is_link_local
        or net.is_reserved
        or net.is_multicast
    )


def _decode(text: bytes) -> str:
    """pconline 返回 GBK，ip-api 返回 UTF-8；两种都试一次。"""
    for enc in ("utf-8", "gbk"):
        try:
            return text.decode(enc)
        except UnicodeDecodeError:
            continue
    return text.decode("utf-8", "ignore")


def _format(country: str, region: str, city: str) -> str:
    """组装展示串。中国 IP 省略国名；region==city 时不重复。"""
    parts: list[str] = []
    if country and country not in ("中国", "China", "CN"):
        parts.append(country)
    if region:
        parts.append(region)
    if city and city != region:
        parts.append(city)
    return " ".join(parts).strip()


def _lookup_pconline(ip: str) -> str:
    """太平洋电脑网 IP 库（中文，国内访问快）。json=true 返回纯 JSON。"""
    url = f"https://whois.pconline.com.cn/ipJson.jsp?ip={ip}&json=true"
    r = requests.get(url, timeout=_HTTP_TIMEOUT, headers=_UA)
    data = json.loads(_decode(r.content))
    return _format(data.get("country") or "", data.get("pro") or "", data.get("city") or "")


def _lookup_ipapi(ip: str) -> str:
    """ip-api.com 中文兜底（免费 45/min，HTTP）。"""
    url = f"http://ip-api.com/json/{ip}?lang=zh-CN&fields=status,message,country,regionName,city"
    r = requests.get(url, timeout=_HTTP_TIMEOUT, headers=_UA)
    data = r.json()
    if data.get("status") != "success":
        return ""
    return _format(data.get("country") or "", data.get("regionName") or "", data.get("city") or "")


def _resolve_remote(ip: str) -> str:
    """依次尝试各数据源，返回「省 市」或 ""。"""
    for fn in (_lookup_pconline, _lookup_ipapi):
        try:
            loc = fn(ip)
            if loc:
                return loc
        except Exception:  # noqa: BLE001 — 任一数据源失败就换下一个
            continue
    return ""


def resolve_location(ip: str) -> str:
    """IP → 地理位置展示串。带缓存与降级，永不抛异常。"""
    if not getattr(settings, "GEOIP_ENABLED", True):
        return ""
    if _is_private(ip):
        return ""
    now = time.time()
    with _LOCK:
        hit = _CACHE.get(ip)
        if hit and now - hit[0] < _CACHE_TTL:
            return hit[1]
    loc = _resolve_remote(ip)
    with _LOCK:
        _CACHE[ip] = (now, loc)
    return loc


__all__ = ["resolve_location"]

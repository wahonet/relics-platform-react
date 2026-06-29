"""Web 安全相关的纯函数(无 FastAPI / 无第三方依赖,仅标准库)。

放在独立轻量模块里,既能被 main.py 复用,又能在不导入整个 FastAPI 应用
(及其 numpy / pydantic 等重依赖)的前提下单独做单元测试。

目前包含:
    resolve_cors_origins(cfg)   把 config 解析成 CORS 白名单

后续(Bug #4)将加入会话令牌的 HMAC 签发 / 校验。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import List, Optional, Tuple

# 开发模式下两个 Vite dev server 的来源(5174=React 主图 / 5173=Vue 后台)。
# 集成部署时前端与 API 同源(都在 :8000),本就不触发 CORS;这里主要照顾
# 直接跨源调用 API 的开发场景。
_DEFAULT_DEV_ORIGINS = [
    "http://127.0.0.1:5174",
    "http://localhost:5174",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
]


def resolve_cors_origins(cfg: dict | None) -> List[str]:
    """根据 config 返回一份具体的 CORS 来源白名单(绝不返回 '*')。

    规则:
    - `server.cors_origins` 给了非空 list 或逗号分隔字符串 → 原样采用(运维显式覆盖)。
    - 否则用内置开发来源 + 当前 server.host:port 的来源拼一份默认白名单。

    之所以不允许通配:`allow_origins=["*"]` 搭配 `allow_credentials=True`
    违反 CORS 规范,浏览器会拒绝携带 Cookie 的跨域请求(本平台用 Cookie 会话)。
    """
    server = ((cfg or {}).get("server") or {})

    configured = server.get("cors_origins")
    if isinstance(configured, str):
        configured = [o.strip() for o in configured.split(",") if o.strip()]
    if isinstance(configured, list):
        cleaned = [str(o).strip() for o in configured if str(o).strip()]
        if cleaned:
            return _dedupe(cleaned)

    origins = list(_DEFAULT_DEV_ORIGINS)

    host = str(server.get("host") or "127.0.0.1").strip()
    try:
        port = int(server.get("port") or 8000)
    except (TypeError, ValueError):
        port = 8000
    # host 可能是 0.0.0.0(对外监听),它不是合法的浏览器来源,跳过;
    # 同时补上回环地址,方便本机访问集成版。
    for h in (host, "127.0.0.1", "localhost"):
        if h and h != "0.0.0.0":
            origins.append(f"http://{h}:{port}")

    return _dedupe(origins)


def _dedupe(items: List[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


# ── 会话令牌(HMAC-SHA256 签名,纯标准库)──────────────────────
# 旧实现把 Cookie 值写死成 "authenticated",任何人手填该值即可冒充登录。
# 这里改成对 {用户名, 签发时间} 做 HMAC 签名:篡改或伪造都会校验失败。

def resolve_session_secret(cfg: dict | None) -> Tuple[bytes, str]:
    """返回 (secret_bytes, source)。优先级:
    环境变量 RELICS_SECRET_KEY > config.server.secret_key > 进程内随机。

    随机(ephemeral)来源意味着进程重启后旧会话全部失效——demo / 内网可接受,
    生产应显式配置一段固定的长随机密钥。
    """
    env_key = os.environ.get("RELICS_SECRET_KEY", "").strip()
    if env_key:
        return env_key.encode("utf-8"), "env:RELICS_SECRET_KEY"

    server = ((cfg or {}).get("server") or {})
    cfg_key = server.get("secret_key")
    if isinstance(cfg_key, str):
        cfg_key = cfg_key.strip()
        # 未被展开的 ${VAR} 占位符视为"未配置"。
        if cfg_key and not (cfg_key.startswith("${") and cfg_key.endswith("}")):
            return cfg_key.encode("utf-8"), "config:server.secret_key"

    return secrets.token_bytes(32), "ephemeral"


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64u_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign_session(username: str, secret: bytes, *, issued_at: Optional[int] = None) -> str:
    """签发会话令牌:``b64u(payload).b64u(hmac_sha256(payload))``。"""
    iat = int(issued_at if issued_at is not None else time.time())
    payload = json.dumps(
        {"u": username or "", "iat": iat},
        separators=(",", ":"),
        ensure_ascii=False,
    )
    raw = _b64u(payload.encode("utf-8"))
    sig = _b64u(hmac.new(secret, raw.encode("ascii"), hashlib.sha256).digest())
    return f"{raw}.{sig}"


def verify_session(
    token: Optional[str],
    secret: bytes,
    *,
    max_age: Optional[int] = None,
    now: Optional[int] = None,
) -> Optional[dict]:
    """校验令牌。签名不符 / 格式错 / 过期 → None;通过 → payload(含 u、iat)。

    用 hmac.compare_digest 做常数时间比较,避免计时侧信道;整体包在 try 里,
    任何畸形输入都安全地返回 None 而不抛异常。
    """
    if not token or not secret:
        return None
    try:
        raw, sig = token.split(".", 1)
        expected = _b64u(hmac.new(secret, raw.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, sig):
            return None
        payload = json.loads(_b64u_decode(raw).decode("utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if max_age is not None:
        ts = int(now if now is not None else time.time())
        try:
            iat = int(payload.get("iat", 0))
        except (TypeError, ValueError):
            return None
        if ts - iat > int(max_age):
            return None
    return payload

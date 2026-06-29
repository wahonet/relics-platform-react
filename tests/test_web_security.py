"""web_security 纯函数测试(仅需 pytest + 标准库)。

守护 Bug #3 的修复:CORS 白名单绝不能退化成 '*'(与 allow_credentials=True
同时使用会被浏览器拒绝)。
"""
from __future__ import annotations

import base64
import json

from web_security import (
    resolve_cookie_secure,
    resolve_cors_origins,
    resolve_session_secret,
    sign_session,
    verify_session,
)

_SECRET = b"unit-test-secret-0123456789abcdef"


def test_default_origins_are_concrete_not_wildcard():
    origins = resolve_cors_origins({})
    assert origins, "默认应返回非空白名单"
    assert "*" not in origins
    # 两个 dev server 来源都应在内。
    assert "http://127.0.0.1:5174" in origins
    assert "http://127.0.0.1:5173" in origins


def test_config_list_override_is_used_verbatim():
    origins = resolve_cors_origins(
        {"server": {"cors_origins": ["https://a.example", "https://b.example"]}}
    )
    assert origins == ["https://a.example", "https://b.example"]


def test_config_csv_string_override():
    origins = resolve_cors_origins(
        {"server": {"cors_origins": "https://a.example, https://b.example ,"}}
    )
    assert origins == ["https://a.example", "https://b.example"]


def test_includes_configured_host_port_but_not_wildcard_bind():
    origins = resolve_cors_origins({"server": {"host": "192.168.1.10", "port": 9000}})
    assert "http://192.168.1.10:9000" in origins
    # 0.0.0.0 是监听地址,不是合法浏览器来源,不应出现。
    assert all("0.0.0.0" not in o for o in origins)


def test_no_duplicate_origins():
    origins = resolve_cors_origins({"server": {"host": "127.0.0.1", "port": 8000}})
    assert len(origins) == len(set(origins))


def test_empty_or_garbage_config_falls_back_to_defaults():
    assert "*" not in resolve_cors_origins(None)
    assert resolve_cors_origins({"server": {"cors_origins": []}})  # 空 list → 默认
    assert resolve_cors_origins({"server": {"cors_origins": "   "}})  # 空串 → 默认


# ── 会话令牌(Bug #4)─────────────────────────────────────────
def test_sign_then_verify_roundtrip():
    tok = sign_session("alice", _SECRET, issued_at=1000)
    payload = verify_session(tok, _SECRET)
    assert payload == {"u": "alice", "iat": 1000}


def test_tampered_payload_is_rejected():
    tok = sign_session("alice", _SECRET)
    _, sig = tok.split(".", 1)
    forged = base64.urlsafe_b64encode(
        json.dumps({"u": "admin", "iat": 1}).encode()
    ).rstrip(b"=").decode()
    assert verify_session(f"{forged}.{sig}", _SECRET) is None


def test_wrong_secret_is_rejected():
    tok = sign_session("alice", _SECRET)
    assert verify_session(tok, b"a-different-secret") is None


def test_old_static_value_and_garbage_are_rejected():
    assert verify_session("authenticated", _SECRET) is None  # 旧的可伪造值
    assert verify_session("", _SECRET) is None
    assert verify_session(None, _SECRET) is None
    assert verify_session("no-dot-here", _SECRET) is None
    assert verify_session("a.b.c", _SECRET) is None


def test_expiry_enforced_when_max_age_set():
    tok = sign_session("alice", _SECRET, issued_at=1000)
    assert verify_session(tok, _SECRET, max_age=100, now=1050) is not None  # 未过期
    assert verify_session(tok, _SECRET, max_age=100, now=2000) is None      # 已过期


def test_resolve_secret_priority(monkeypatch):
    monkeypatch.delenv("RELICS_SECRET_KEY", raising=False)
    sec, src = resolve_session_secret({"server": {"secret_key": "abc"}})
    assert sec == b"abc" and src == "config:server.secret_key"

    monkeypatch.setenv("RELICS_SECRET_KEY", "envkey")
    sec, src = resolve_session_secret({"server": {"secret_key": "abc"}})
    assert sec == b"envkey" and src.startswith("env")

    monkeypatch.delenv("RELICS_SECRET_KEY", raising=False)
    sec, src = resolve_session_secret({"server": {"secret_key": "${RELICS_SECRET_KEY}"}})
    assert src == "ephemeral" and len(sec) >= 16  # 占位符视为未配置 → 随机


# ── Cookie Secure 标志(P2)────────────────────────────────────
def test_cookie_secure_defaults_false():
    assert resolve_cookie_secure(None) is False
    assert resolve_cookie_secure({}) is False
    assert resolve_cookie_secure({"server": {}}) is False


def test_cookie_secure_accepts_bool_and_strings():
    assert resolve_cookie_secure({"server": {"cookie_secure": True}}) is True
    assert resolve_cookie_secure({"server": {"cookie_secure": "true"}}) is True
    assert resolve_cookie_secure({"server": {"cookie_secure": "ON"}}) is True
    assert resolve_cookie_secure({"server": {"cookie_secure": "no"}}) is False
    assert resolve_cookie_secure({"server": {"cookie_secure": "garbage"}}) is False

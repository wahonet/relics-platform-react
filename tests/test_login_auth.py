from __future__ import annotations

import asyncio

import main
from web_security import verify_session


def _cookie_token(resp) -> str:
    sc = resp.headers["set-cookie"]
    assert "session=" in sc and "httponly" in sc.lower()
    return sc.split("session=", 1)[1].split(";", 1)[0]


def test_login_allows_when_auth_disabled(monkeypatch):
    monkeypatch.setattr(main, "_CONFIG", {"server": {"enable_auth": False}})

    resp = asyncio.run(main.api_login(main._LoginBody(username="anyone", password="wrong")))

    assert resp.status_code == 200
    token = _cookie_token(resp)
    # 关键:不再是可被任何人手填伪造的固定字符串。
    assert token != "authenticated"
    payload = verify_session(token, main._SECRET)
    assert payload is not None and payload["u"] == "anyone"


def test_login_checks_configured_users_when_auth_enabled(monkeypatch):
    monkeypatch.setattr(
        main,
        "_CONFIG",
        {
            "server": {
                "enable_auth": True,
                "users": [{"username": "admin", "password": "changeme"}],
            }
        },
    )

    ok = asyncio.run(main.api_login(main._LoginBody(username="admin", password="changeme")))
    bad = asyncio.run(main.api_login(main._LoginBody(username="admin", password="wrong")))

    assert ok.status_code == 200
    assert bad.status_code == 401
    payload = verify_session(_cookie_token(ok), main._SECRET)
    assert payload is not None and payload["u"] == "admin"


def test_forged_static_cookie_is_rejected():
    # 旧的 "authenticated" 值在新机制下必须无效(签名校验失败)。
    assert verify_session("authenticated", main._SECRET) is None

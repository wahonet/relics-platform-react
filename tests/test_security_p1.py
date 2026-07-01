"""批次 3b 安全 P1 回归:密码哈希(P1-08)、DOCX 上传加固(P0-03)。

API 401 vs 302(P1-07)的中间件分支很薄,由 test_login_auth 覆盖登录路径,此处不单独起 TestClient。
"""
from __future__ import annotations

import io
import zipfile

import pytest
from fastapi import HTTPException

from routers import admin
from web_security import hash_password, verify_password


# ── P1-08:密码哈希 ─────────────────────────────────────────────
def test_password_hash_roundtrip_and_unique_salt():
    h = hash_password("s3cret!")
    assert h.startswith("pbkdf2_sha256$")
    assert verify_password(h, "s3cret!") is True
    assert verify_password(h, "wrong") is False
    assert verify_password(h, "") is False
    # 随机 salt → 同密码两次哈希不同。
    assert hash_password("s3cret!") != h


def test_verify_password_accepts_legacy_plaintext():
    # 旧 config 的明文 password 必须仍能登录(平滑过渡)。
    assert verify_password("changeme", "changeme") is True
    assert verify_password("changeme", "nope") is False


def test_verify_password_rejects_empty_and_malformed():
    assert verify_password(None, "x") is False
    assert verify_password("", "x") is False
    assert verify_password("pbkdf2_sha256$bad", "x") is False  # 格式错
    assert verify_password("pbkdf2_sha256$10$ab$cd$ef", "x") is False  # 段数错


# ── P0-03:DOCX 上传加固 ────────────────────────────────────────
def test_safe_docx_filename_neutralizes_traversal():
    # basename 取值,目录穿越被抹掉。
    assert admin._safe_docx_filename("../../etc/evil.docx") == "evil.docx"
    assert admin._safe_docx_filename("正常档案.docx") == "正常档案.docx"


def test_safe_docx_filename_rejects_bad_names():
    for bad in (None, "", "noext.txt", "a.exe", "archive.doc"):
        with pytest.raises(HTTPException) as ei:
            admin._safe_docx_filename(bad)
        assert ei.value.status_code == 400


def test_safe_child_rejects_traversal(tmp_path):
    base = tmp_path
    assert admin._safe_child(base, "sub").resolve() == (base / "sub").resolve()
    with pytest.raises(HTTPException) as ei:
        admin._safe_child(base, "../evil")
    assert ei.value.status_code == 400


def _make_zip_bytes(*members: tuple[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members:
            zf.writestr(name, data)
    return buf.getvalue()


def test_validate_docx_zip_accepts_valid():
    # 含 word/document.xml,体积/压缩比正常 → 不抛。
    admin._validate_docx_zip(_make_zip_bytes(("word/document.xml", "<w:document/>")))


def test_validate_docx_zip_rejects_missing_document_xml():
    with pytest.raises(HTTPException) as ei:
        admin._validate_docx_zip(_make_zip_bytes(("word/other.xml", "<x/>")))
    assert ei.value.status_code == 400


def test_validate_docx_zip_rejects_non_zip():
    with pytest.raises(HTTPException) as ei:
        admin._validate_docx_zip(b"this is not a zip file")
    assert ei.value.status_code == 400


def test_validate_docx_zip_rejects_internal_traversal():
    # zip 成员名含 ..,即使有 document.xml 也要拒绝。
    with pytest.raises(HTTPException) as ei:
        admin._validate_docx_zip(_make_zip_bytes(("../evil.xml", "x"), ("word/document.xml", "y")))
    assert ei.value.status_code == 400

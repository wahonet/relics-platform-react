"""stats / survey / worklog / boundaries 路由端点测试(直接调用协程)。

全局 store 在测试进程里未 load(_use_db=False、relics 为空),故这些只读端点
应返回结构正确的"空"响应,验证装配与响应形状,无需 DB/网络。
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from routers import boundaries as bd
from routers import stats as stats_route
from routers import survey_routes as survey_route
from routers import worklog as wl


# ── stats ────────────────────────────────────────────────────
def test_stats_shape_on_empty_store():
    res = asyncio.run(stats_route.get_stats())
    assert res["total"] == 0
    for key in ("by_category", "by_township", "by_condition", "by_era"):
        assert key in res and isinstance(res[key], dict)
    assert res["has_3d_count"] == 0


# ── survey ───────────────────────────────────────────────────
def test_survey_routes_empty_by_default():
    assert asyncio.run(survey_route.get_survey_routes()) == {}


def test_village_coverage_default_shape():
    res = asyncio.run(survey_route.get_village_coverage())
    assert res == {"total": 0, "reached": 0, "unreached": 0, "villages": []}


# ── worklog ──────────────────────────────────────────────────
def test_worklog_dates_empty(monkeypatch):
    monkeypatch.setattr(wl, "_ledger_cache", None)
    monkeypatch.setattr(wl, "_ledger_by_date", None)
    monkeypatch.setattr(wl, "_find_ledger_path", lambda: None)
    monkeypatch.setattr(wl, "_get_pdf_list", lambda: {})

    res = asyncio.run(wl.worklog_dates())
    assert res == {"total_days": 0, "items": []}


def test_worklog_detail_missing_date(monkeypatch):
    monkeypatch.setattr(wl, "_ledger_cache", None)
    monkeypatch.setattr(wl, "_ledger_by_date", None)
    monkeypatch.setattr(wl, "_find_ledger_path", lambda: None)
    monkeypatch.setattr(wl, "_get_pdf_list", lambda: {})

    res = asyncio.run(wl.worklog_detail("2024-01-01"))
    assert res["date"] == "2024-01-01"
    assert res["has_pdf"] is False
    assert res["ledger"] is None


def test_worklog_parse_date_handles_excel_serial_and_datetime():
    import datetime as _dt
    assert wl._parse_date(_dt.datetime(2024, 11, 8)) == "2024-11-08"
    assert wl._parse_date(_dt.date(2024, 11, 8)) == "2024-11-08"
    assert wl._parse_date(45604) == "2024-11-08"   # Excel 序列日
    assert wl._parse_date(None) == ""


# ── boundaries(只测校验/读目录,不碰网络与删除)─────────────
def test_boundaries_list_reports_three_layers(monkeypatch, tmp_path):
    monkeypatch.setattr(bd, "_OUT_DIR", tmp_path)
    res = asyncio.run(bd.list_boundaries())
    names = [f["name"] for f in res["files"]]
    assert names == ["county.geojson", "townships.geojson", "villages.geojson"]
    assert all(f.get("missing") for f in res["files"])   # 空目录全部缺失


def test_boundaries_download_requires_adcode():
    req = bd.BoundaryDownloadRequest()  # 无 city/county adcode
    with pytest.raises(HTTPException) as ei:
        asyncio.run(bd.download_boundaries(req))
    assert ei.value.status_code == 400


def test_boundaries_download_townships_needs_county():
    req = bd.BoundaryDownloadRequest(
        city_adcode=370800, include_city_counties=False, include_townships=True
    )
    with pytest.raises(HTTPException) as ei:
        asyncio.run(bd.download_boundaries(req))
    assert ei.value.status_code == 400


def test_boundaries_export_404_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(bd, "_OUT_DIR", tmp_path)
    with pytest.raises(HTTPException) as ei:
        asyncio.run(bd.export_boundary(file="villages", crs="wgs84"))
    assert ei.value.status_code == 404


def test_boundaries_export_rejects_unsupported_crs(monkeypatch, tmp_path):
    # CRS 校验在文件存在性检查之前,故非法 crs 必先触发 400(与文件无关)。
    monkeypatch.setattr(bd, "_OUT_DIR", tmp_path)
    with pytest.raises(HTTPException) as ei:
        asyncio.run(bd.export_boundary(file="county", crs="nope"))
    assert ei.value.status_code == 400

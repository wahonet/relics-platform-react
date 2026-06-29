"""CRS 路由端点测试(直接调用协程,无需 httpx)。

覆盖 /api/crs/list、/api/crs/transform、/api/crs/transform-geojson 的成功与错误分支。
"""
from __future__ import annotations

import asyncio
import math

import pytest
from fastapi import HTTPException

from routers import crs as crs_route

_WM_HALF = math.pi * 6378137.0  # web mercator 半周长 ≈ 20037508.34


def test_list_crs_returns_all_supported():
    res = asyncio.run(crs_route.list_crs())
    ids = {it["id"] for it in res["items"]}
    assert {"wgs84", "cgcs2000", "web_mercator", "gcj02", "bd09",
            "cgcs2000_gk_3", "cgcs2000_gk_6"} <= ids
    # 每项带元信息。
    assert all("name" in it and "unit" in it for it in res["items"])


def test_transform_wgs84_to_web_mercator_known_value():
    req = crs_route.TransformRequest(
        src_crs="wgs84", dst_crs="web_mercator", coords=[[180.0, 0.0]]
    )
    res = asyncio.run(crs_route.crs_transform(req))
    assert res["count"] == 1
    x, y = res["coords"][0][0], res["coords"][0][1]
    assert abs(x - _WM_HALF) < 1.0
    assert abs(y) < 1e-6


def test_transform_preserves_extra_ordinates():
    req = crs_route.TransformRequest(
        src_crs="wgs84", dst_crs="wgs84", coords=[[116.4, 39.9, 42.0]]
    )
    res = asyncio.run(crs_route.crs_transform(req))
    assert res["coords"][0] == [116.4, 39.9, 42.0]   # 同 CRS 原样 + 保留高程


def test_transform_rejects_unsupported_crs():
    req = crs_route.TransformRequest(src_crs="wgs84", dst_crs="nope", coords=[[1.0, 2.0]])
    with pytest.raises(HTTPException) as ei:
        asyncio.run(crs_route.crs_transform(req))
    assert ei.value.status_code == 400


def test_transform_rejects_malformed_point():
    req = crs_route.TransformRequest(src_crs="wgs84", dst_crs="web_mercator", coords=[[1.0]])
    with pytest.raises(HTTPException) as ei:
        asyncio.run(crs_route.crs_transform(req))
    assert ei.value.status_code == 400


def test_transform_geojson_converts_and_tags_crs():
    gj = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {},
             "geometry": {"type": "Point", "coordinates": [180.0, 0.0]}}
        ],
    }
    req = crs_route.TransformGeojsonRequest(src_crs="wgs84", dst_crs="web_mercator", geojson=gj)
    res = asyncio.run(crs_route.crs_transform_geojson(req))
    out = res["geojson"]
    x = out["features"][0]["geometry"]["coordinates"][0]
    assert abs(x - _WM_HALF) < 1.0
    assert out["crs"]["properties"]["name"] == "web_mercator"


def test_transform_geojson_rejects_unsupported_crs():
    req = crs_route.TransformGeojsonRequest(src_crs="bad", dst_crs="wgs84", geojson={})
    with pytest.raises(HTTPException) as ei:
        asyncio.run(crs_route.crs_transform_geojson(req))
    assert ei.value.status_code == 400

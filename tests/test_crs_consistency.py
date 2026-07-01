"""批次2 CRS 一致性回归:P1-12(GCJ 中国范围 guard)、P1-13(GK 带号半数向上)、
P0-05/06(step06 转换判定 + 输出范围校验)。

目的是让 Python 侧(_common / crs / step06)与前端 crs.ts 在边界、境外、
半值经度上不再发散。
"""
from __future__ import annotations

from pathlib import Path

import crs
import step06_prepare_boundaries as step06
from _common import gcj02_to_wgs84, wgs84_to_gcj02


# ── P1-12:GCJ-02 中国范围 guard(对齐 crs.ts inChina)──────────────
def test_gcj_is_identity_outside_china():
    # 旧实现会对境外坐标也施加 GCJ delta,与前端 crs.ts 不一致。
    assert gcj02_to_wgs84(-122.4, 37.8) == (-122.4, 37.8)
    assert wgs84_to_gcj02(-122.4, 37.8) == (-122.4, 37.8)
    assert gcj02_to_wgs84(0.0, 0.0) == (0.0, 0.0)


def test_gcj_still_shifts_inside_china():
    g_lng, g_lat = wgs84_to_gcj02(116.404, 39.915)
    # 境内必须有数百米量级偏移(确证 guard 没把真转换也关掉)。
    assert abs(g_lng - 116.404) > 1e-3 or abs(g_lat - 39.915) > 1e-3
    # 往返仍回到原点。
    w_lng, w_lat = gcj02_to_wgs84(g_lng, g_lat)
    assert abs(w_lng - 116.404) < 1e-4
    assert abs(w_lat - 39.915) < 1e-4


# ── P1-13:GK 3° 带号半数向上(对齐 JS Math.round)──────────────────
def test_gk_zone_3deg_half_boundary_is_round_half_up():
    # 旧 Python round(银行家)给 38;JS Math.round 给 39。此处必须与 JS 一致。
    assert crs.gk_zone_for_lng(115.5, zone_width=3) == 39
    assert crs.gk_zone_for_lng(114.0, zone_width=3) == 38
    assert crs.gk_zone_for_lng(117.0, zone_width=3) == 39


def test_gk_zone_6deg_unchanged():
    assert crs.gk_zone_for_lng(117.0, zone_width=6) == 20


# ── P0-05 / P0-06:step06 转换判定 + 范围校验────────────────────────
def test_need_transform_gcj02_is_true_regardless_of_is_projected():
    # GCJ-02 经纬度 x≈116,is_projected 会返回 False,但必须转换。这是 P0-05 的核心。
    assert step06.need_transform_for_layer("gcj02", Path("does-not-exist.shp")) is True
    assert step06.need_transform_for_layer("gcj-02", Path("does-not-exist.shp")) is True


def test_need_transform_explicit_lonlat_is_false():
    assert step06.need_transform_for_layer("wgs84", Path("x.shp")) is False
    assert step06.need_transform_for_layer("cgcs2000", Path("x.shp")) is False
    assert step06.need_transform_for_layer("none", Path("x.shp")) is False


def test_need_transform_explicit_gk_is_true():
    for p in ("gauss_kruger", "cgcs2000_gk_3", "cgcs2000_gk_6"):
        assert step06.need_transform_for_layer(p, Path("x.shp")) is True


def test_need_transform_auto_falls_back_to_is_projected():
    # auto + 不存在的文件 → is_projected 返回 False。
    assert step06.need_transform_for_layer("auto", Path("does-not-exist.shp")) is False


def test_looks_like_lonlat_bounds():
    assert step06._looks_like_lonlat(116.0, 36.0) is True
    assert step06._looks_like_lonlat(-180.0, -90.0) is True
    assert step06._looks_like_lonlat(180.0, 90.0) is True
    # 无带号高斯坐标(假东向 ~500000)不是经纬度 → P0-06 靠这个抛错。
    assert step06._looks_like_lonlat(500123.4, 3912345.6) is False
    assert step06._looks_like_lonlat(180.001, 0.0) is False

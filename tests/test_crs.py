"""crs.py 坐标变换数值回归测试(纯 stdlib,经 _common 需要 pyyaml)。

crs.py 是全平台数学最密集、改动最易静默引入偏移的模块,此前零测试。
这里用“往返一致性 + 已知值”双手段守护:正反算来回一趟应回到原点,
个别点对照解析已知值。容差按各算法实际精度设定。

注意:_HELMERT 是模块级全局,autouse fixture 每个用例前后都复位为 None,
保证用例间隔离(否则一个用例注参会污染“默认 identity”的其它用例)。
"""
from __future__ import annotations

import math

import pytest

import crs


@pytest.fixture(autouse=True)
def _reset_helmert():
    crs.set_helmert_params(None)
    yield
    crs.set_helmert_params(None)


# ── 带号 / 中央经线 ───────────────────────────────────────────
def test_gk_zone_and_central_meridian():
    # 3°带:山东 117° → 39 带,中央经线回到 117。
    assert crs.gk_zone_for_lng(117.0, zone_width=3) == 39
    assert crs.gk_central_meridian(39, zone_width=3) == 117
    # 6°带:117° → 20 带,中央经线 20*6-3 = 117。
    assert crs.gk_zone_for_lng(117.0, zone_width=6) == 20
    assert crs.gk_central_meridian(20, zone_width=6) == 117


# ── 高斯-克吕格正反算往返 ─────────────────────────────────────
@pytest.mark.parametrize("lng,lat", [(117.0, 36.0), (117.3, 36.2), (116.4, 35.1)])
def test_gk_forward_inverse_roundtrip(lng, lat):
    x, y = crs.gk_forward(lng, lat, central_meridian=117.0)  # 默认含带号前缀
    lng2, lat2 = crs.gk_inverse(x, y, central_meridian=117.0)
    assert abs(lng2 - lng) < 1e-6
    assert abs(lat2 - lat) < 1e-6


def test_gk_false_easting_on_central_meridian():
    # 中央经线上,本地东向应正好是 50 万假偏移(去掉带号后)。
    x, _ = crs.gk_forward(117.0, 36.0, central_meridian=117.0, zone_prefix=False)
    assert abs(x - 500_000.0) < 1e-3


# ── Web Mercator ──────────────────────────────────────────────
def test_web_mercator_known_values():
    assert crs.wgs84_to_web_mercator(0.0, 0.0) == (0.0, 0.0)
    x, _ = crs.wgs84_to_web_mercator(180.0, 0.0)
    assert abs(x - math.pi * 6378137.0) < 0.1  # 半周长 ≈ 20037508.34 m


@pytest.mark.parametrize("lng,lat", [(116.4, 39.9), (-122.4, 37.8), (0.0, 0.0)])
def test_web_mercator_roundtrip(lng, lat):
    x, y = crs.wgs84_to_web_mercator(lng, lat)
    lng2, lat2 = crs.web_mercator_to_wgs84(x, y)
    assert abs(lng2 - lng) < 1e-6
    assert abs(lat2 - lat) < 1e-6


# ── GCJ-02 / BD-09 往返 ──────────────────────────────────────
@pytest.mark.parametrize("lng,lat", [(116.404, 39.915), (121.473, 31.230)])
def test_gcj02_roundtrip(lng, lat):
    g_lng, g_lat = crs.wgs84_to_gcj02(lng, lat)
    # GCJ 与 WGS 之间应有数百米量级偏移(确证转换确实生效,而非恒等)。
    assert abs(g_lng - lng) > 1e-3 or abs(g_lat - lat) > 1e-3
    w_lng, w_lat = crs.gcj02_to_wgs84(g_lng, g_lat)
    # gcj02_to_wgs84 是非迭代近似反算(在 GCJ 点上取偏移量),固有 ~1-2m 误差,
    # 故往返容差取 1e-4°(~11m)——仍远小于上面数百米的正向偏移,足够有意义。
    assert abs(w_lng - lng) < 1e-4
    assert abs(w_lat - lat) < 1e-4


@pytest.mark.parametrize("lng,lat", [(116.404, 39.915), (121.473, 31.230)])
def test_bd09_roundtrip(lng, lat):
    b_lng, b_lat = crs.wgs84_to_bd09(lng, lat)
    w_lng, w_lat = crs.bd09_to_wgs84(b_lng, b_lat)
    assert abs(w_lng - lng) < 1e-4
    assert abs(w_lat - lat) < 1e-4


# ── CGCS2000 ↔ WGS84:默认 identity,注参后非 identity ────────
def test_cgcs2000_identity_without_helmert():
    assert crs.get_helmert_params() is None
    assert crs.wgs84_to_cgcs2000(116.4, 39.9) == (116.4, 39.9)
    assert crs.cgcs2000_to_wgs84(116.4, 39.9) == (116.4, 39.9)


def test_cgcs2000_helmert_is_non_identity_and_bounded():
    crs.set_helmert_params(
        {"dx": 1.0, "dy": -1.0, "dz": 0.5, "rx": 0.01, "ry": -0.02, "rz": 0.03, "ds": 0.1}
    )
    assert crs.get_helmert_params() is not None
    out = crs.cgcs2000_to_wgs84(116.4, 39.9)
    # 应偏离原值(确证 7 参生效),但量级很小(米级 → 远小于 0.01°)。
    assert out != (116.4, 39.9)
    assert abs(out[0] - 116.4) < 0.01 and abs(out[1] - 39.9) < 0.01


def test_set_helmert_params_validates_required_keys():
    with pytest.raises(ValueError):
        crs.set_helmert_params({"dx": 1.0})  # 缺字段


# ── 统一入口 transform_point ──────────────────────────────────
def test_transform_point_identity_and_unsupported():
    assert crs.transform_point("wgs84", "wgs84", 116.4, 39.9) == (116.4, 39.9)
    with pytest.raises(ValueError):
        crs.transform_point("wgs84", "nope", 1.0, 2.0)
    with pytest.raises(ValueError):
        crs.transform_point("nope", "wgs84", 1.0, 2.0)


def test_transform_point_wgs84_gk_roundtrip():
    x, y = crs.transform_point(
        "wgs84", "cgcs2000_gk_3", 117.3, 36.2, central_meridian=117.0
    )
    lng, lat = crs.transform_point(
        "cgcs2000_gk_3", "wgs84", x, y, central_meridian=117.0
    )
    assert abs(lng - 117.3) < 1e-6
    assert abs(lat - 36.2) < 1e-6


# ── GeoJSON 整体变换 ─────────────────────────────────────────
def test_transform_geojson_same_crs_is_noop():
    gj = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [116.4, 39.9]},
         "properties": {}}]}
    assert crs.transform_geojson(gj, "wgs84", "wgs84") is gj


def test_transform_geojson_converts_points_and_tags_crs():
    gj = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [180.0, 0.0]},
         "properties": {}}]}
    out = crs.transform_geojson(gj, "wgs84", "web_mercator")
    x = out["features"][0]["geometry"]["coordinates"][0]
    assert abs(x - math.pi * 6378137.0) < 0.1
    assert out["crs"]["properties"]["name"] == "web_mercator"

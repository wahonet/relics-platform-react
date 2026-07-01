"""安全 P0 回归测试:生产 auth 闸门、demo 模式回环限制、瓦片坐标/数量上限、边界清理穿越。

这些覆盖外部评审第一轮的 P0-01(auth 闸门)、P0-04(边界清理穿越)、
P0-05(瓦片校验)、P0-06(瓦片任务上限)。
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

import main
import serve
import tile_routes
from routers import boundaries as bd


# ── P0-01:生产 auth 闸门(serve.py 启动前 + main.py 中间件兜底)──────────
def test_insecure_bind_reason_rejects_lan_without_auth():
    reason = serve.insecure_bind_reason("0.0.0.0", enable_auth=False, allow_insecure=False)
    assert reason is not None and "0.0.0.0" in reason


def test_insecure_bind_reason_allows_loopback_without_auth():
    # 本机 demo:host 是回环,auth 关闭是允许的(现有本地开发体验不变)。
    assert serve.insecure_bind_reason("127.0.0.1", False, False) is None
    assert serve.insecure_bind_reason("localhost", False, False) is None


def test_insecure_bind_reason_allows_lan_with_auth():
    assert serve.insecure_bind_reason("0.0.0.0", True, False) is None


def test_insecure_bind_reason_respects_explicit_allow():
    # 显式 allow_insecure_demo 也能放行(明知故犯的逃生开关)。
    assert serve.insecure_bind_reason("0.0.0.0", False, True) is None


def test_demo_mode_allows_client():
    assert main._demo_mode_allows_client("127.0.0.1", False) is True
    assert main._demo_mode_allows_client("::1", False) is True
    assert main._demo_mode_allows_client("192.168.1.5", False) is False
    assert main._demo_mode_allows_client("192.168.1.5", True) is True


# ── P0-04:边界清理路径穿越─────────────────────────────────────
def test_clear_boundaries_rejects_traversal_target(monkeypatch, tmp_path):
    monkeypatch.setattr(bd, "_OUT_DIR", tmp_path)
    with pytest.raises(HTTPException) as ei:
        asyncio.run(bd.clear_boundaries(targets="../dataset/relics_points"))
    assert ei.value.status_code == 400


def test_clear_boundaries_only_deletes_allowlisted_files(monkeypatch, tmp_path):
    monkeypatch.setattr(bd, "_OUT_DIR", tmp_path)
    (tmp_path / "county.geojson").write_text("{}", encoding="utf-8")
    (tmp_path / "townships.geojson").write_text("{}", encoding="utf-8")
    # 一个“长得像但不在白名单”的文件不会被删。
    (tmp_path / "villages.geojson").write_text("{}", encoding="utf-8")

    res = asyncio.run(bd.clear_boundaries(targets="county,townships"))
    assert set(res["removed"]) == {"county", "townships"}
    assert not (tmp_path / "county.geojson").exists()
    assert not (tmp_path / "townships.geojson").exists()
    assert (tmp_path / "villages.geojson").exists()  # 未在 targets 里,保留


# ── P0-05 / P0-06:瓦片坐标校验与任务上限─────────────────────────
def test_valid_tile_coord_range():
    assert tile_routes._valid_tile_coord(5, 0, 0) is True
    assert tile_routes._valid_tile_coord(5, 31, 31) is True      # z=5 → n=32, 最大索引 31
    assert tile_routes._valid_tile_coord(5, 32, 0) is False      # 越界
    assert tile_routes._valid_tile_coord(5, -1, 0) is False
    assert tile_routes._valid_tile_coord(0, 0, 0) is False       # 低于 TILE_MIN_ZOOM(1)
    assert tile_routes._valid_tile_coord(99, 0, 0) is False      # 高于 TILE_MAX_ZOOM(17)


def test_count_tiles_fast_matches_enumeration_for_small_area():
    bbox = (116.0, 35.0, 117.0, 36.0)
    zooms = [12, 13]
    fast = tile_routes._count_tiles_fast(["osm"], bbox, zooms)
    enumerated = sum(len(tile_routes._tiles_for_bounds(*bbox, z)) for z in zooms)
    assert fast == enumerated


def test_count_tiles_fast_rejects_huge_area_under_cap():
    # 全国范围 + 高 zoom 会远超 MAX_TILE_TASKS,前端据此拒绝、后端不构造任务列表。
    huge = (73.0, 18.0, 135.0, 54.0)
    est = tile_routes._count_tiles_fast(["arcgis_sat", "osm"], huge, [16, 17])
    assert est > tile_routes.MAX_TILE_TASKS

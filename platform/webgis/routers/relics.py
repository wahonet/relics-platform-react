"""文物查询相关 API。

新接口（推荐使用）：
    GET /api/relics/by-bbox          视口查询，极简 8 字段，目标 <50ms
    GET /api/relics/search?q=...     FTS5 全文搜索，返回精简列表

旧接口（deprecated，保留兼容）：
    GET /api/relics                  全量列表，迁移期保留但会记 warning
    GET /api/relics/{code}           单条完整详情
    GET /api/relics/{code}/photos    照片列表
    GET /api/relics/{code}/drawings  图纸列表
    GET /api/geojson/points          全量 points geojson
    GET /api/geojson/polygons        全量 polygons geojson
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Response

from data_loader import store

router = APIRouter(tags=["文物"])
log = logging.getLogger("uvicorn.error")


# ── 新：视口查询 ────────────────────────────────────────────
@router.get("/relics/by-bbox")
async def relics_by_bbox(
    min_lng: float = Query(..., description="视口西经"),
    min_lat: float = Query(..., description="视口南纬"),
    max_lng: float = Query(..., description="视口东经"),
    max_lat: float = Query(..., description="视口北纬"),
    category: str | None = Query(None, description="国标大类 0100..0600，逗号分隔支持多选"),
    rank: str | None = Query(None, description="保护级别 1..5，逗号分隔支持多选"),
    township: str | None = Query(None),
    search_type: str | None = Query(None, description="普查来源 2/12/110301"),
    limit: int = Query(2000, ge=1, le=5000),
):
    """视口 + 筛选查询，响应每条只含 8 字段（目标 < 250 字节/条）。
    bbox 会自动按 15% 缓冲扩展，便于快速拖动时复用缓存。"""
    if min_lng >= max_lng or min_lat >= max_lat:
        raise HTTPException(400, "bbox 参数无效：min 必须小于 max")

    # 15% buffer 扩展，学四普做法提升体验；超过视口一屏的拖动仍能命中缓存
    dlng = (max_lng - min_lng) * 0.15
    dlat = (max_lat - min_lat) * 0.15
    qmin_lng, qmax_lng = min_lng - dlng, max_lng + dlng
    qmin_lat, qmax_lat = min_lat - dlat, max_lat + dlat

    ranks = None
    if rank:
        ranks = [v.strip() for v in rank.split(",") if v.strip()]
    cats = None
    if category:
        cats = [v.strip() for v in category.split(",") if v.strip()]

    data = store.query_bbox(
        qmin_lng, qmin_lat, qmax_lng, qmax_lat,
        categories=cats,
        ranks=ranks,
        township=township or None,
        search_type=search_type or None,
        limit=limit,
    )
    truncated = len(data) >= limit

    response = Response(
        content=_dumps({"data": data, "total": len(data), "truncated": truncated}),
        media_type="application/json",
    )
    # 允许浏览器 / 反代短时缓存；坐标精度 5 位已保证 URL 命中率足够
    response.headers["Cache-Control"] = "public, max-age=30"
    return response


@router.get("/relics/search")
async def relics_search(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    limit: int = Query(20, ge=1, le=200),
):
    """FTS5 全文搜索（trigram tokenizer）。关键词 ≥3 字符走索引，
    2 字符以内走 LIKE fallback。返回与 by-bbox 相同的 8 字段格式。"""
    data = store.search_fulltext(q, limit=limit)
    return {"data": data, "total": len(data), "query": q}


# ── 兼容旧接口 ──────────────────────────────────────────────
@router.get("/relics", deprecated=True)
async def list_relics():
    """全部文物精简列表（DEPRECATED）。

    请改用 `/api/relics/by-bbox` 视口查询。迁移期保留用于 admin 老页面。"""
    log.warning("[deprecated] /api/relics 被调用，请迁移到 /api/relics/by-bbox")
    return store.get_relics_summary()


@router.get("/relics/{code}")
async def get_relic(code: str):
    """单个文物完整信息（含简介/照片/图纸列表）。"""
    relic = store.get_relic_full(code) if store._use_db else store.get_relic(code)
    if not relic:
        raise HTTPException(status_code=404, detail=f"文物 {code} 不存在")
    return relic


@router.get("/relics/{code}/photos")
async def get_relic_photos(code: str):
    if not store.get_relic(code):
        raise HTTPException(status_code=404, detail=f"文物 {code} 不存在")
    return store.get_photos(code)


@router.get("/relics/{code}/drawings")
async def get_relic_drawings(code: str):
    if not store.get_relic(code):
        raise HTTPException(status_code=404, detail=f"文物 {code} 不存在")
    return store.get_drawings(code)


@router.get("/relics/{code}/polygon")
async def get_relic_polygon(code: str):
    """单条文物的多边形几何（geojson Geometry，不含 feature 壳）。"""
    geom = store.polygon_of(code)
    if not geom:
        raise HTTPException(404, "此文物无多边形数据")
    return geom


@router.get("/geojson/points")
async def geojson_points():
    return store.geojson_points


@router.get("/geojson/polygons")
async def geojson_polygons():
    return store.geojson_polygons


# ── 工具 ────────────────────────────────────────────────────
def _dumps(obj) -> bytes:
    """默认走 stdlib json；byte 输出让 FastAPI Response 直接用，省一次编码。
    若后续引入 orjson 可在这里替换为 orjson.dumps。"""
    import json as _json
    return _json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

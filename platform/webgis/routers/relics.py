"""文物查询 API。

推荐接口:
    GET /api/relics/by-bbox      视口查询,极简 8 字段
    GET /api/relics/search       FTS5 全文搜索

兼容接口 (deprecated):
    GET /api/relics              全量列表
    GET /api/relics/{code}       单条完整详情
    GET /api/relics/{code}/photos / drawings / polygon
    GET /api/geojson/points / polygons
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response

from data_loader import store

router = APIRouter(tags=["文物"])


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
    """视口 + 筛选查询,每条 8 字段(目标 <250 B)。
    bbox 自动按 15% 缓冲扩展,便于快速拖动时命中缓存。"""
    if min_lng >= max_lng or min_lat >= max_lat:
        raise HTTPException(400, "bbox 参数无效：min 必须小于 max")

    # 15% 缓冲,短距离拖动时仍能命中同一请求。
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
    response.headers["Cache-Control"] = "public, max-age=30"
    return response


@router.get("/relics/search")
async def relics_search(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    limit: int = Query(20, ge=1, le=200),
):
    """FTS5 全文搜索(trigram)。关键词 >=3 字走索引,否则 LIKE fallback。
    返回格式与 by-bbox 一致。"""
    data = store.search_fulltext(q, limit=limit)
    return {"data": data, "total": len(data), "query": q}


@router.get("/relics/facets")
async def relics_facets(
    q: str | None = Query(None, description="名称/编号关键词"),
    category: str | None = Query(None, description="国标大类 0100..0600，逗号分隔多选"),
    rank: str | None = Query(None, description="保护级别 1..5，逗号分隔多选"),
    township: str | None = Query(None),
    search_type: str | None = Query(None),
    min_lng: float | None = Query(None),
    min_lat: float | None = Query(None),
    max_lng: float | None = Query(None),
    max_lat: float | None = Query(None),
):
    """当前筛选下的分面计数 + 总数 + has_3d,供前端 Dashboard/FilterPanel 联动而无需全量入内存。

    facets 含 category/rank/search_type(按国标全集 0 填充)+ township/era_stats/
    condition/ownership/industry/risk_factors(出现值按计数降序)。后四者来自 extra_json,
    对**过滤后**子集做一次内存归并;risk_factors 多值逐项计数,industry 取第一段。
    注:这些维度仅供"计数/展示",过滤 WHERE 只认 category/rank/township/search_type/bbox。
    四个 bbox 参数需齐全才生效。
    """
    cats = [v.strip() for v in category.split(",")] if category else None
    ranks = [v.strip() for v in rank.split(",")] if rank else None
    bbox = None
    if None not in (min_lng, min_lat, max_lng, max_lat):
        bbox = (min_lng, min_lat, max_lng, max_lat)

    return store.facet_counts(
        search=(q or "").strip() or None,
        categories=cats,
        ranks=ranks,
        township=(township or "").strip() or None,
        search_type=(search_type or "").strip() or None,
        bbox=bbox,
    )


@router.get("/relics/list")
async def relics_list(
    q: str | None = Query(None, description="名称/编号关键词"),
    category: str | None = Query(None, description="国标大类，逗号分隔多选"),
    rank: str | None = Query(None, description="保护级别，逗号分隔多选"),
    township: str | None = Query(None),
    search_type: str | None = Query(None),
    min_lng: float | None = Query(None),
    min_lat: float | None = Query(None),
    max_lng: float | None = Query(None),
    max_lat: float | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
):
    """当前筛选下的分页文物列表(精简行),供前端结果列表;不再依赖全量 /api/relics。
    每行 {code,name,category(编码),era,township,has_3d}。四个 bbox 参数需齐全才生效。"""
    cats = [v.strip() for v in category.split(",")] if category else None
    ranks = [v.strip() for v in rank.split(",")] if rank else None
    bbox = None
    if None not in (min_lng, min_lat, max_lng, max_lat):
        bbox = (min_lng, min_lat, max_lng, max_lat)

    return store.list_relics_filtered(
        search=(q or "").strip() or None,
        categories=cats,
        ranks=ranks,
        township=(township or "").strip() or None,
        search_type=(search_type or "").strip() or None,
        bbox=bbox,
        page=page,
        size=size,
    )


# ── 兼容旧接口 ──────────────────────────────────────────────
@router.get("/relics")
async def list_relics():
    """全量精简摘要列表(每条约 24 字段,不含简介/边界点)。

    这是前端 Dashboard / FilterPanel **跨维交叉筛选**的合法数据源:它们按
    现状/年代/行业/影响因素等维度(部分带展示变换:ERA_MAP 归并、行业取首段、
    影响因素多值)在客户端联动,需要一次性拿到全集。地图打点另走
    /api/relics/by-bbox(视口分页),二者分工不同 —— 本接口并非 by-bbox 的
    旧版替代品,故不再标 deprecated。

    大数据量(万条+/跨县跨省)下如需彻底去全量,改用 /api/relics/facets
    (分面计数 + 总数)+ /api/relics/list(分页行),把交叉筛选下推到服务端。
    """
    return store.get_relics_summary()


@router.get("/relics/{code}")
async def get_relic(code: str):
    """单条完整详情(含简介 / 照片 / 图纸)。"""
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
    """单条多边形几何(GeoJSON Geometry,不含 Feature 外壳)。"""
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
    """直接返回 utf-8 bytes,Response 无需再做一次编码。"""
    import json as _json
    return _json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

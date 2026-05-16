"""Relic management routes for the admin API."""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from codes import (  # noqa: E402
    CATEGORY_CODES,
    RANK_CODES,
    SEARCH_TYPE_CODES,
    normalize_category,
    normalize_rank,
    normalize_search_type,
)
from data_loader import store  # noqa: E402

router = APIRouter(tags=["??"])


# ── 文物 CRUD (DB + 乐观锁 + 审计) ────────────────────────
# 仅 DB 模式可用。调用方需传 expected_version,冲突返回 409。

def _require_db() -> None:
    if not getattr(store, "_use_db", False):
        raise HTTPException(503, "DB 未启用；请先运行 step07_build_db.py 并重启服务")


def _normalize_relic_payload(raw: dict) -> dict:
    """把中文字段(category_main / heritage_level / survey_type 等)标准化到 DB 编码;
    已经是编码的直接保留。"""
    p = dict(raw or {})
    if "category_main" in p and "category" not in p:
        p["category"] = normalize_category(p.pop("category_main"))
    elif "category" in p:
        p["category"] = normalize_category(p["category"])
    if "heritage_level" in p and "rank" not in p:
        p["rank"] = normalize_rank(p.pop("heritage_level"))
    elif "rank" in p:
        p["rank"] = normalize_rank(p["rank"])
    if "survey_type" in p and "search_type" not in p:
        p["search_type"] = normalize_search_type(p.pop("survey_type"))

    # legacy 字段兼容:center_lng/lat/alt、archive_code。
    if "center_lng" in p and "lng" not in p:
        p["lng"] = p.pop("center_lng")
    if "center_lat" in p and "lat" not in p:
        p["lat"] = p.pop("center_lat")
    if "center_alt" in p and "alt" not in p:
        p["alt"] = p.pop("center_alt")
    if "archive_code" in p and "code" not in p:
        p["code"] = p.pop("archive_code")
    return p


@router.post("/relics")
async def create_relic(
    payload: dict = Body(...),
    x_actor: Optional[str] = Header(None, alias="X-Actor"),
):
    """创建文物。payload 至少包含 code / name / lng / lat。"""
    _require_db()
    try:
        after = store.create_relic(_normalize_relic_payload(payload), actor=x_actor or "")
    except ValueError as e:
        msg = str(e)
        code = 409 if "已存在" in msg else 400
        raise HTTPException(code, msg)
    return {"ok": True, "relic": after}


@router.put("/relics/{code}")
async def update_relic(
    code: str,
    payload: dict = Body(...),
    x_actor: Optional[str] = Header(None, alias="X-Actor"),
):
    """更新文物。payload 必传 expected_version;冲突返回 409。"""
    _require_db()
    ev = payload.pop("expected_version", None)
    if ev is None:
        raise HTTPException(400, "缺少 expected_version（乐观锁）")
    try:
        after = store.update_relic(
            code, _normalize_relic_payload(payload),
            expected_version=int(ev), actor=x_actor or "",
        )
    except ValueError as e:
        msg = str(e)
        if msg == "VERSION_CONFLICT":
            raise HTTPException(409, "版本冲突：数据已被他人修改，请重新加载")
        if "不存在" in msg:
            raise HTTPException(404, msg)
        raise HTTPException(400, msg)
    return {"ok": True, "relic": after}


@router.delete("/relics/{code}")
async def delete_relic(
    code: str,
    x_actor: Optional[str] = Header(None, alias="X-Actor"),
):
    """软删除(status=-1)。可通过 PUT /relics/{code} 把 status 改回 1 恢复。"""
    _require_db()
    try:
        store.delete_relic(code, actor=x_actor or "")
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"ok": True}


@router.get("/audit")
async def list_audit(
    code: Optional[str] = None,
    limit: int = 100,
    action: Optional[str] = Query(None, description="多值逗号分隔：create,update,delete,rollback"),
    actor: Optional[str] = None,
    field: Optional[str] = Query(None, description="字段名 LIKE 过滤，如 'lng' / 'name'"),
    start_ts: Optional[int] = None,
    end_ts: Optional[int] = None,
):
    """审计日志列表,支持多条件筛选,最近在前。"""
    _require_db()
    actions = [a.strip() for a in (action or "").split(",") if a.strip()] or None
    return {
        "rows": store.list_audit(
            code=code, limit=max(1, min(limit, 500)),
            actions=actions,
            actor=(actor or "").strip() or None,
            field=(field or "").strip() or None,
            start_ts=start_ts, end_ts=end_ts,
        )
    }


@router.post("/audit/{audit_id}/rollback")
async def rollback_audit(
    audit_id: int,
    x_actor: Optional[str] = Header(None, alias="X-Actor"),
):
    """按审计记录回滚文物到 before_json 状态。"""
    _require_db()
    try:
        return store.rollback_audit(audit_id, actor=x_actor or "")
    except ValueError as e:
        msg = str(e)
        if msg == "VERSION_CONFLICT":
            raise HTTPException(409, "版本冲突：文物已被他人修改，请刷新后重试")
        if "不存在" in msg or "已彻底删除" in msg:
            raise HTTPException(404, msg)
        raise HTTPException(400, msg)


@router.get("/stats-overview")
async def stats_overview():
    """Dashboard 聚合指标,一次请求出齐所有卡片/图表数据;
    DB 未启用时走 legacy 内存聚合,仅返回基础字段。"""
    return store.admin_stats_overview()


@router.get("/codes")
async def codes_dict():
    """国标编码字典:category / rank / search_type → 中文标签。"""
    return {
        "categories": [{"code": c, "label": CATEGORY_CODES[c]} for c in CATEGORY_CODES],
        "ranks": [{"code": c, "label": RANK_CODES[c]} for c in RANK_CODES],
        "search_types": [{"code": c, "label": SEARCH_TYPE_CODES[c]} for c in SEARCH_TYPE_CODES],
    }


@router.get("/relics-townships")
async def relics_townships():
    """后台乡镇下拉,来源为 DB 中已入库文物。"""
    _require_db()
    return {"townships": store.admin_list_townships()}


def _parse_bbox(bbox: Optional[str]) -> Optional[tuple]:
    """解析 'minLng,minLat,maxLng,maxLat';格式非法返回 None。"""
    if not bbox:
        return None
    parts = [p.strip() for p in bbox.split(",") if p.strip()]
    if len(parts) != 4:
        return None
    try:
        mnl, mnt, mxl, mxt = [float(p) for p in parts]
        return (mnl, mnt, mxl, mxt)
    except ValueError:
        return None


@router.get("/relics")
async def list_relics(
    page: int = 1,
    size: int = 20,
    search: Optional[str] = None,
    category: Optional[str] = None,
    rank: Optional[str] = None,
    township: Optional[str] = None,
    search_type: Optional[str] = None,
    status: Optional[int] = None,
    bbox: Optional[str] = Query(None, description="minLng,minLat,maxLng,maxLat"),
    order_by: str = "updated_at_desc",
):
    """后台分页列表。category / rank 支持逗号多选。"""
    _require_db()
    categories = [c for c in (category or "").split(",") if c] or None
    ranks = [c for c in (rank or "").split(",") if c] or None
    return store.admin_list_relics(
        page=page, size=size, search=(search or "").strip() or None,
        categories=categories, ranks=ranks,
        township=(township or "").strip() or None,
        search_type=(search_type or "").strip() or None,
        status=status,
        bbox=_parse_bbox(bbox),
        order_by=order_by,
    )


@router.get("/relics/{code}/neighbors")
async def relic_neighbors(
    code: str,
    radius: float = Query(2000.0, ge=50, le=50000, description="米"),
    limit: int = Query(20, ge=1, le=100),
):
    """radius 米内的其它文物,按距离升序。"""
    _require_db()
    return {
        "code": code, "radius": radius,
        "items": store.admin_neighbors(code, radius_m=radius, limit=limit),
    }


@router.get("/relics/{code}")
async def get_relic_full(code: str):
    """文物全字段,含 _version 供乐观锁。"""
    _require_db()
    r = store.get_relic_full(code) if hasattr(store, "get_relic_full") else store.get_relic(code)
    if not r:
        raise HTTPException(404, f"未找到文物: {code}")
    return r


@router.post("/relics/bulk-update")
async def bulk_update_relics(
    payload: dict = Body(...),
    x_actor: Optional[str] = Header(None, alias="X-Actor"),
):
    """批量同字段更新。payload = {codes, fields}。

    - fields 仅保留可写字段;不接受 expected_version(逐条取当前 version)。
    - 乐观锁冲突 / 不存在 / 异常逐条记录,不中断其它条目。
    """
    _require_db()
    codes = payload.get("codes") or []
    fields = payload.get("fields") or {}
    if not isinstance(codes, list) or not codes:
        raise HTTPException(400, "codes 不能为空")
    if not isinstance(fields, dict) or not fields:
        raise HTTPException(400, "fields 不能为空")
    patch = _normalize_relic_payload(fields)
    # code 不允许批量改写。
    patch.pop("code", None)
    try:
        return store.admin_bulk_update(codes, patch, actor=x_actor or "")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/relics/bulk-status")
async def bulk_set_status(
    payload: dict = Body(...),
    x_actor: Optional[str] = Header(None, alias="X-Actor"),
):
    """批量改状态。payload = {codes, status}。status=-1 走软删(action=delete),
    0/1 走 bulk_update(action=update)。"""
    _require_db()
    codes = payload.get("codes") or []
    status = payload.get("status")
    if not isinstance(codes, list) or not codes:
        raise HTTPException(400, "codes 不能为空")
    if status not in (1, 0, -1):
        raise HTTPException(400, "status 只能是 1 / 0 / -1")
    if status == -1:
        return store.admin_bulk_delete(codes, actor=x_actor or "")
    return store.admin_bulk_update(codes, {"status": int(status)}, actor=x_actor or "")


@router.get("/relics-export")
async def export_relics(
    search: Optional[str] = None,
    category: Optional[str] = None,
    rank: Optional[str] = None,
    township: Optional[str] = None,
    search_type: Optional[str] = None,
    status: Optional[int] = None,
    codes: Optional[str] = Query(None, description="逗号分隔的 code 列表；给出时忽略其他筛选"),
    bbox: Optional[str] = Query(None, description="minLng,minLat,maxLng,maxLat"),
    order_by: str = "code_asc",
):
    """按筛选或显式 codes 列表导出 CSV(UTF-8 BOM,Excel 可直接打开)。"""
    _require_db()
    cat_list = [c for c in (category or "").split(",") if c] or None
    rank_list = [c for c in (rank or "").split(",") if c] or None
    code_list = [c.strip() for c in (codes or "").split(",") if c.strip()] or None

    fieldnames = [
        "code", "name",
        "category", "category_label",
        "rank", "rank_label",
        "search_type", "search_type_label",
        "era", "era_stats",
        "lng", "lat", "alt",
        "township", "village", "address",
        "has_3d", "has_pdf", "has_photo", "has_boundary",
        "photo_count", "drawing_count",
        "status", "version", "updated_at",
        "brief",
    ]

    def _gen():
        import io
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
        yield "\ufeff"  # UTF-8 BOM,Excel 识别中文
        writer.writeheader()
        yield buf.getvalue()
        buf.seek(0); buf.truncate(0)
        rows = store.admin_export_relics(
            search=(search or "").strip() or None,
            categories=cat_list, ranks=rank_list,
            township=(township or "").strip() or None,
            search_type=(search_type or "").strip() or None,
            status=status,
            codes=code_list,
            bbox=_parse_bbox(bbox),
            order_by=order_by,
        )
        for r in rows:
            row = dict(r)
            row["category_label"] = CATEGORY_CODES.get(str(row.get("category") or ""), "")
            row["rank_label"] = RANK_CODES.get(str(row.get("rank") or ""), "")
            row["search_type_label"] = SEARCH_TYPE_CODES.get(str(row.get("search_type") or ""), "")
            for k in ("has_3d", "has_pdf", "has_photo", "has_boundary"):
                row[k] = 1 if row.get(k) else 0
            writer.writerow(row)
            yield buf.getvalue()
            buf.seek(0); buf.truncate(0)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"relics-{ts}.csv"
    return StreamingResponse(
        _gen(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/relics/import")
async def import_relics(
    file: UploadFile = File(...),
    mode: str = Form("upsert"),          # upsert / create_only
    x_actor: Optional[str] = Header(None, alias="X-Actor"),
):
    """批量导入。接受 CSV / JSON 数组,按 code 匹配。

    - upsert:已存在走 update(从 DB 读最新 version),否则 create
    - create_only:已存在则跳过,仅新增

    返回逐行结果。无整体事务;大文件请分批导入。
    """
    _require_db()
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "空文件")

    items: list[dict] = []
    name = (file.filename or "").lower()
    if name.endswith(".json"):
        try:
            data = json.loads(raw.decode("utf-8-sig"))
        except json.JSONDecodeError as e:
            raise HTTPException(400, f"JSON 解析失败: {e}")
        if not isinstance(data, list):
            raise HTTPException(400, "JSON 顶层需是数组")
        items = data
    elif name.endswith(".csv"):
        import io
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        items = list(reader)
    else:
        raise HTTPException(400, "仅支持 .csv / .json")

    results = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
    for idx, raw_row in enumerate(items, start=1):
        p = _normalize_relic_payload(raw_row)
        code = (p.get("code") or "").strip()
        if not code:
            results["skipped"] += 1
            continue
        try:
            existing = store.get_relic(code)
            if existing:
                if mode == "create_only":
                    results["skipped"] += 1
                    continue
                ev = existing.get("_version")
                if ev is None:
                    # legacy 字典不含 version,直接读 DB 取最新值。
                    row = store._thread_conn().execute(
                        "SELECT version FROM relics WHERE code = ?", (code,)
                    ).fetchone()
                    ev = int(row["version"]) if row else 1
                store.update_relic(code, p, expected_version=int(ev), actor=x_actor or "import")
                results["updated"] += 1
            else:
                store.create_relic(p, actor=x_actor or "import")
                results["created"] += 1
        except Exception as e:
            results["failed"] += 1
            results["errors"].append({"line": idx, "code": code, "error": str(e)})
            if len(results["errors"]) > 50:
                break

    return results

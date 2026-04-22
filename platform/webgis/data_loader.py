"""全局数据容器。迁移期并存策略：

- 启动时优先检测 `data/output/dataset/relics.db`，存在则走 SQLite 模式
  （通过 Repository 方法查询），同时把完整文物记录缓存到 `self.relics`
  以保持与旧路由（`/api/relics`、`/api/stats`、admin 等）的兼容。
- DB 不存在时回退到老的 JSON 加载路径（完全兼容旧部署）。
- 新路由应优先使用 `store.query_bbox()` / `store.search_fulltext()`，
  只在需要全量时才用 `store.relics`。

对外接口保持向后兼容：
    store.relics / store.relics_map
    store.photo_index / store.photo_map
    store.drawing_index / store.drawing_map
    store.geojson_points / store.geojson_polygons
    store.township_stats / store.survey_routes / store.village_coverage
    store.pdf_map
    store.load() / store.get_relic() / store.get_photos() / store.get_drawings()
    store.get_relics_summary() / store.compute_stats()

新增接口（仅 DB 模式有效）：
    store.query_bbox(...)           视口查询，返回极简 8 字段
    store.search_fulltext(...)      FTS5 全文搜索
    store.get_relic_full(code)      单条文物完整详情（含 extra_json 合并）
    store.polygon_of(code)          单条文物的多边形 geojson 几何
"""
from __future__ import annotations

import csv
import json
import logging
import sqlite3
import sys
import threading
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

log = logging.getLogger("uvicorn.error")

# 让 codes.py 能被找到；webgis 已把 scripts/ 加到 sys.path，这里再兜底一次
_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from codes import CATEGORY_CODES, RANK_CODES, SEARCH_TYPE_CODES  # noqa: E402


# ── DB 行 → 旧 relic 字典 ─────────────────────────────────────
def _row_to_legacy(row: sqlite3.Row, extra: dict) -> dict:
    """DB 记录反向映射为老的文物字典格式（`archive_code/category_main/...`），
    用于兼容只认旧字段的路由和前端代码。"""
    d = dict(extra) if extra else {}
    d.update({
        "archive_code": row["code"],
        "name": row["name"],
        "category_main": CATEGORY_CODES.get(row["category"], "其他"),
        "heritage_level": RANK_CODES.get(row["rank"], ""),
        "survey_type": SEARCH_TYPE_CODES.get(row["search_type"] or "", row["search_type"] or ""),
        "center_lng": row["lng"],
        "center_lat": row["lat"],
        "center_alt": row["alt"],
        "township": row["township"] or "",
        "village": row["village"] or "",
        "address": row["address"] or "",
        "era": row["era"] or "",
        "era_stats": row["era_stats"] or "",
        "has_3d": bool(row["has_3d"]),
        "has_boundary": bool(row["has_boundary"]),
        "photo_count": row["photo_count"] or 0,
        "drawing_count": row["drawing_count"] or 0,
        "intro": row["brief"] or "",
        # 前端有时用它，给个兼容
        "_cat_code": row["category"],
        "_rank_code": row["rank"],
        "_version": row["version"] if "version" in row.keys() else 1,
    })
    return d


class DataStore:
    """全局数据容器。支持 SQLite (推荐) 与 JSON (fallback) 两种后端。
    `_use_db=True` 时所有查询走 DB；`self.relics` 仍会被填充以兼容旧接口。"""

    def __init__(self) -> None:
        self.relics: list[dict] = []
        self.relics_map: dict[str, dict] = {}
        self.photo_index: list[dict] = []
        self.photo_map: dict[str, list[dict]] = {}
        self.drawing_index: list[dict] = []
        self.drawing_map: dict[str, list[dict]] = {}
        self.pdf_map: dict[str, str] = {}
        self.geojson_points: dict = {}
        self.geojson_polygons: dict = {}
        self.township_stats: list[dict] = []
        self.survey_routes: dict[str, list[dict]] = {}
        self.village_coverage: dict = {}
        self._bounds: Optional[tuple[float, float, float, float]] = None

        # ── DB 相关 ────────────────────────────────────────
        self._use_db: bool = False
        self._db_path: Optional[Path] = None
        # 主连接在 lifespan 启动时打开，路由里按需通过 _thread_conn 拿到当前线程连接
        self._db: Optional[sqlite3.Connection] = None
        self._tls = threading.local()

    # ── 加载入口 ────────────────────────────────────────────
    def load(
        self,
        dataset_dir: str | Path,
        *,
        village_geojson: str | Path = "",
        pdf_dir: str | Path = "",
        survey_gps_csv: str | Path = "",
        bounds: Optional[tuple[float, float, float, float]] = None,
    ) -> None:
        """一次性加载全部数据源。如果 `dataset_dir/relics.db` 存在则
        走 DB 模式，否则回退到 JSON 加载（兼容旧部署）。"""
        dp = Path(dataset_dir)
        self._bounds = bounds

        db_file = dp / "relics.db"
        if db_file.exists():
            self._open_db(db_file)
            log.info("[数据] DB 模式: %s", db_file)
        else:
            log.warning("[数据] 未找到 relics.db，回退 JSON 模式。建议运行 step07_build_db.py")

        # PDF 索引：DB 没存全文件名列表，仍靠扫目录获得
        if pdf_dir:
            self._load_pdf_index(Path(pdf_dir))

        if self._use_db:
            # DB 模式下仍把全量 relics 填入内存兼容旧接口
            self._populate_legacy_from_db()
            self._load_geojson(dp)
            self._load_township_stats(dp / "township_stats.csv")
        else:
            self._load_relics(dp / "relics_full.json")
            self._load_photo_index(dp / "photo_index.csv")
            self._load_drawing_index(dp / "drawing_index.csv")
            self._load_geojson(dp)
            self._load_township_stats(dp / "township_stats.csv")

        if survey_gps_csv and Path(survey_gps_csv).exists():
            self._load_survey_routes(Path(survey_gps_csv))

        if village_geojson and Path(village_geojson).exists() and self.survey_routes:
            self._compute_village_coverage(Path(village_geojson))

    # ── SQLite 连接管理 ─────────────────────────────────────
    def _open_db(self, db_path: Path) -> None:
        self._db_path = db_path
        self._use_db = True
        # 主连接：启动时打开一次，用于同步的初始化工作。
        # 路由里按请求/线程取连接，走 _thread_conn。
        conn = sqlite3.connect(
            str(db_path),
            check_same_thread=False,
            isolation_level=None,  # autocommit，事务手动 BEGIN/COMMIT
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        self._db = conn

    def _thread_conn(self) -> sqlite3.Connection:
        """每线程一个连接，避免跨线程共享 sqlite3 cursor 的问题。"""
        if not self._db_path:
            raise RuntimeError("DB 未开启")
        c = getattr(self._tls, "conn", None)
        if c is None:
            c = sqlite3.connect(str(self._db_path), check_same_thread=False)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL;")
            c.execute("PRAGMA foreign_keys=ON;")
            self._tls.conn = c
        return c

    # ── DB 模式初始化 ────────────────────────────────────────
    def _populate_legacy_from_db(self) -> None:
        """把 DB 里所有文物读出来，填到 self.relics / self.relics_map /
        self.photo_map / self.drawing_map，保证旧接口零改动工作。"""
        assert self._db is not None
        self.relics.clear()
        self.relics_map.clear()
        self.photo_index.clear()
        self.photo_map.clear()
        self.drawing_index.clear()
        self.drawing_map.clear()

        for row in self._db.execute("SELECT * FROM relics WHERE status = 1"):
            extra = {}
            if row["extra_json"]:
                try:
                    extra = json.loads(row["extra_json"]) or {}
                except json.JSONDecodeError:
                    pass
            d = _row_to_legacy(row, extra)
            # 让 pdf_map 的 has_pdf 标记能反馈到这里
            if self.pdf_map.get(row["code"]):
                d["has_pdf"] = True
                d["pdf_path"] = self.pdf_map[row["code"]]
            self.relics.append(d)
            self.relics_map[row["code"]] = d

        # 照片 / 图纸索引
        for row in self._db.execute("SELECT relic_code, path, thumb_path, taken_at FROM photos"):
            p = {
                "archive_code": row["relic_code"],
                "path": row["path"],
                "thumb_path": row["thumb_path"] or "",
                "taken_at": row["taken_at"],
            }
            self.photo_index.append(p)
            self.photo_map.setdefault(row["relic_code"], []).append(p)

        for row in self._db.execute("SELECT relic_code, path FROM drawings"):
            dw = {"archive_code": row["relic_code"], "path": row["path"]}
            self.drawing_index.append(dw)
            self.drawing_map.setdefault(row["relic_code"], []).append(dw)

    # ── JSON 模式原有逻辑（完全保留） ────────────────────────
    def _load_relics(self, path: Path) -> None:
        if not path.exists():
            log.warning("[数据] 未找到 %s", path)
            return
        with open(path, "r", encoding="utf-8") as f:
            self.relics = json.load(f)
        for r in self.relics:
            code = r.get("archive_code")
            if code:
                self.relics_map[code] = r

    def _load_photo_index(self, path: Path) -> None:
        if not path.exists():
            return
        self.photo_index = self._read_csv(path)
        for p in self.photo_index:
            code = p.get("archive_code")
            if code:
                self.photo_map.setdefault(code, []).append(p)

    def _load_drawing_index(self, path: Path) -> None:
        if not path.exists():
            return
        self.drawing_index = self._read_csv(path)
        for d in self.drawing_index:
            code = d.get("archive_code")
            if code:
                self.drawing_map.setdefault(code, []).append(d)

    def _load_geojson(self, data_path: Path) -> None:
        pts = data_path / "relics_points.geojson"
        polys = data_path / "relics_polygons.geojson"
        if pts.exists():
            with open(pts, "r", encoding="utf-8") as f:
                self.geojson_points = json.load(f)
        if polys.exists():
            with open(polys, "r", encoding="utf-8") as f:
                self.geojson_polygons = json.load(f)

    def _load_township_stats(self, path: Path) -> None:
        if path.exists():
            self.township_stats = self._read_csv(path)

    def _load_pdf_index(self, pdf_dir: Path) -> None:
        if not pdf_dir.exists():
            log.warning("[PDF] 目录不存在: %s", pdf_dir)
            return
        for sub in pdf_dir.iterdir():
            if not sub.is_dir():
                continue
            pdfs = sorted(sub.glob("*.pdf"))
            if pdfs:
                self.pdf_map[sub.name] = f"{sub.name}/{pdfs[0].name}"
        log.info("[PDF] %d 个档案 PDF 已索引", len(self.pdf_map))

    def _load_survey_routes(self, path: Path) -> None:
        rows = self._read_csv(path)
        if not rows:
            return

        def _pick(row: dict, *keys: str) -> str:
            for k in keys:
                if k in row and row[k] not in (None, ""):
                    return str(row[k]).strip()
            return ""

        west, south, east, north = self._bounds or (-180.0, -90.0, 180.0, 90.0)
        groups: dict[str, list[dict]] = {}

        for row in rows:
            dt_str = _pick(row, "拍摄时间", "time", "datetime")
            lat_str = _pick(row, "纬度", "lat", "latitude")
            lon_str = _pick(row, "经度", "lon", "lng", "longitude")
            if not dt_str or not lat_str or not lon_str:
                continue
            try:
                lat = float(lat_str)
                lon = float(lon_str)
            except ValueError:
                continue
            if not (south < lat < north and west < lon < east):
                continue

            parts = dt_str.split(" ", 1)
            date_raw = parts[0]
            time_raw = parts[1] if len(parts) > 1 else "00:00:00"

            dp = date_raw.replace("/", "-").split("-")
            if len(dp) == 3:
                date = f"{int(dp[0]):04d}-{int(dp[1]):02d}-{int(dp[2]):02d}"
            else:
                date = date_raw

            tp = time_raw.split(":")
            time_val = ":".join(p.zfill(2) for p in tp[:3])
            if len(tp) < 3:
                time_val += ":00"

            groups.setdefault(date, []).append({
                "filename": _pick(row, "文件名", "filename"),
                "time": time_val,
                "lat": lat,
                "lon": lon,
            })

        for pts in groups.values():
            pts.sort(key=lambda p: p["time"])
        self.survey_routes = dict(sorted(groups.items()))
        total = sum(len(v) for v in self.survey_routes.values())
        log.info("[普查路线] 已加载 %d 天 / %d 个点", len(self.survey_routes), total)

    def _compute_village_coverage(self, village_path: Path) -> None:
        try:
            from shapely.geometry import Point, LineString, shape
            from shapely import STRtree
            from shapely.ops import prep
        except ImportError:
            log.warning("[村村达] 缺少 shapely 依赖，跳过空间分析")
            return

        with open(village_path, "r", encoding="utf-8") as f:
            vdata = json.load(f)
        features = vdata.get("features", [])
        if not features:
            return

        village_list: list[dict] = []
        polygons: list = []
        for feat in features:
            props = feat.get("properties", {})
            geom = feat.get("geometry")
            if not geom:
                continue
            try:
                poly = shape(geom)
                if not poly.is_valid:
                    poly = poly.buffer(0)
            except Exception:
                continue
            centroid = poly.centroid
            village_list.append({
                "name": props.get("ZLDWMC") or props.get("name") or "",
                "township": props.get("_township") or props.get("township") or "",
                "center_lat": round(centroid.y, 6),
                "center_lon": round(centroid.x, 6),
            })
            polygons.append(poly)

        tree = STRtree(polygons)
        prepped = [prep(p) for p in polygons]
        reached: set[int] = set()
        first_date: dict[int, str] = {}
        reached_by: dict[int, str] = {}

        for date in sorted(self.survey_routes.keys()):
            pts = self.survey_routes[date]
            coords = [(p["lon"], p["lat"]) for p in pts]
            if len(coords) >= 2:
                route_geom = LineString(coords)
            elif len(coords) == 1:
                route_geom = Point(coords[0])
            else:
                continue
            for idx in tree.query(route_geom):
                if idx not in reached and prepped[idx].intersects(route_geom):
                    reached.add(idx)
                    first_date[idx] = date
                    reached_by[idx] = "route"

        for r in self.relics:
            lat = r.get("center_lat")
            lng = r.get("center_lng")
            if not lat or not lng:
                continue
            try:
                pt = Point(float(lng), float(lat))
            except (TypeError, ValueError):
                continue
            for idx in tree.query(pt):
                if idx not in reached and prepped[idx].intersects(pt):
                    reached.add(idx)
                    first_date[idx] = ""
                    reached_by[idx] = "relic"

        villages = []
        for i, v in enumerate(village_list):
            v["reached"] = i in reached
            v["first_date"] = first_date.get(i, "")
            v["reached_by"] = reached_by.get(i, "")
            villages.append(v)

        reached_count = sum(1 for v in villages if v["reached"])
        self.village_coverage = {
            "total": len(villages),
            "reached": reached_count,
            "unreached": len(villages) - reached_count,
            "villages": villages,
        }
        log.info(
            "[村村达] %d/%d 村已到达 (%.1f%%)",
            reached_count, len(villages),
            reached_count / len(villages) * 100 if villages else 0,
        )

    # ── 兼容旧接口 ───────────────────────────────────────────
    def get_relic(self, code: str) -> Optional[dict]:
        return self.relics_map.get(code)

    def get_photos(self, code: str) -> list[dict]:
        return self.photo_map.get(code, [])

    def get_drawings(self, code: str) -> list[dict]:
        return self.drawing_map.get(code, [])

    def get_relics_summary(self) -> list[dict]:
        """返回不含简介/边界点的精简列表,用于地图打点和列表渲染。"""
        fields = [
            "archive_code", "name", "category_main", "category_sub",
            "era", "era_stats", "heritage_level", "township", "address",
            "center_lat", "center_lng", "center_alt",
            "has_boundary", "area", "condition_level", "risk_score",
            "ownership_type", "has_3d", "model_3d_path",
            "photo_count", "drawing_count",
            "survey_type", "industry", "risk_factors",
        ]
        result = []
        for r in self.relics:
            item = {k: r.get(k) for k in fields}
            pdf = self.pdf_map.get(r.get("archive_code", ""))
            item["has_pdf"] = pdf is not None
            item["pdf_path"] = pdf or ""
            result.append(item)
        return result

    def compute_stats(self) -> dict:
        total = len(self.relics)
        by_category: dict[str, int] = {}
        by_township: dict[str, int] = {}
        by_condition: dict[str, int] = {}
        by_era: dict[str, int] = {}
        has_3d_count = 0
        has_boundary_count = 0

        for r in self.relics:
            by_category[r.get("category_main", "未知")] = by_category.get(r.get("category_main", "未知"), 0) + 1
            by_township[r.get("township", "未知")] = by_township.get(r.get("township", "未知"), 0) + 1
            by_condition[r.get("condition_level", "未知")] = by_condition.get(r.get("condition_level", "未知"), 0) + 1
            by_era[r.get("era_stats", "未知")] = by_era.get(r.get("era_stats", "未知"), 0) + 1
            if r.get("has_3d"):
                has_3d_count += 1
            if r.get("has_boundary"):
                has_boundary_count += 1

        return {
            "total": total,
            "has_3d_count": has_3d_count,
            "has_boundary_count": has_boundary_count,
            "by_category": by_category,
            "by_township": by_township,
            "by_condition": by_condition,
            "by_era": by_era,
        }

    # ── Repository 新接口（DB 模式专用） ────────────────────
    def query_bbox(
        self,
        min_lng: float,
        min_lat: float,
        max_lng: float,
        max_lat: float,
        *,
        categories: Optional[Iterable[str]] = None,
        ranks: Optional[Iterable[str]] = None,
        township: Optional[str] = None,
        search_type: Optional[str] = None,
        limit: int = 2000,
    ) -> list[dict]:
        """视口 + 筛选查询，返回极简 8 字段格式（id/name/code/lng/lat/category/rank/has_3d）。
        bbox 由调用方负责 buffer 扩展（见 routers/relics.py）。
        `categories`/`ranks` 支持多选，传 None 或空表示不筛选。"""
        if not self._use_db:
            return self._query_bbox_memory(min_lng, min_lat, max_lng, max_lat,
                                            categories=categories, ranks=ranks,
                                            township=township, search_type=search_type,
                                            limit=limit)

        sql = [
            "SELECT r.id, r.code, r.name, r.category, r.rank, r.lng, r.lat, r.has_3d",
            "FROM relics_rtree AS s",
            "JOIN relics_rtree_map AS m ON m.id_int = s.id_int",
            "JOIN relics AS r ON r.id = m.relic_id",
            "WHERE s.max_lng >= ? AND s.min_lng <= ?",
            "  AND s.max_lat >= ? AND s.min_lat <= ?",
            "  AND r.status = 1",
        ]
        params: list = [min_lng, max_lng, min_lat, max_lat]

        if categories:
            cl = [str(v) for v in categories if v not in (None, "")]
            if cl:
                sql.append(f"  AND r.category IN ({','.join('?' for _ in cl)})")
                params.extend(cl)
        if ranks:
            rl = [str(v) for v in ranks if v not in (None, "")]
            if rl:
                sql.append(f"  AND r.rank IN ({','.join('?' for _ in rl)})")
                params.extend(rl)
        if township:
            sql.append("  AND r.township = ?")
            params.append(township)
        if search_type:
            sql.append("  AND r.search_type = ?")
            params.append(str(search_type))

        sql.append("LIMIT ?")
        params.append(int(limit))

        conn = self._thread_conn()
        rows = conn.execute("\n".join(sql), params).fetchall()
        return [
            {
                "id": r["id"],
                "code": r["code"],
                "name": r["name"],
                "lng": r["lng"],
                "lat": r["lat"],
                "category": r["category"],
                "rank": r["rank"],
                "has_3d": bool(r["has_3d"]),
            }
            for r in rows
        ]

    def _query_bbox_memory(
        self, min_lng, min_lat, max_lng, max_lat,
        *, categories, ranks, township, search_type, limit,
    ) -> list[dict]:
        """JSON 模式下的视口查询：全量遍历内存列表。仅作 fallback，
        性能无法应对 5 万条目标；建议尽快迁移到 DB 模式。"""
        from codes import normalize_category, normalize_rank, normalize_search_type

        rank_set = {str(v) for v in ranks} if ranks else None
        cat_set = {str(v) for v in categories} if categories else None
        out = []
        for r in self.relics:
            lng = r.get("center_lng")
            lat = r.get("center_lat")
            if lng is None or lat is None:
                continue
            try:
                lng = float(lng); lat = float(lat)
            except (TypeError, ValueError):
                continue
            if not (min_lng <= lng <= max_lng and min_lat <= lat <= max_lat):
                continue
            cat_code = normalize_category(r.get("category_main"))
            rk_code = normalize_rank(r.get("heritage_level"))
            st_code = normalize_search_type(r.get("survey_type"))
            if cat_set and cat_code not in cat_set:
                continue
            if rank_set and rk_code not in rank_set:
                continue
            if township and r.get("township") != township:
                continue
            if search_type and st_code != search_type:
                continue
            out.append({
                "id": r.get("archive_code"),
                "code": r.get("archive_code"),
                "name": r.get("name"),
                "lng": lng,
                "lat": lat,
                "category": cat_code,
                "rank": rk_code,
                "has_3d": bool(r.get("has_3d")),
            })
            if len(out) >= limit:
                break
        return out

    def search_fulltext(self, keyword: str, limit: int = 20) -> list[dict]:
        """FTS5 全文搜索。返回与 query_bbox 相同的 8 字段格式。
        - 关键词长度 >= 3：走 FTS5 trigram
        - 关键词长度 < 3：走 name LIKE fallback（保证短词也能用）"""
        kw = (keyword or "").strip()
        if not kw:
            return []

        if not self._use_db:
            return [r for r in [self._peek_memory(kw, limit)] if r][0] if self._peek_memory(kw, limit) else []

        conn = self._thread_conn()
        if len(kw) >= 3:
            sql = (
                "SELECT r.id, r.code, r.name, r.category, r.rank, r.lng, r.lat, r.has_3d "
                "FROM relics_fts f "
                "JOIN relics_rtree_map m ON m.id_int = f.rowid "
                "JOIN relics r ON r.id = m.relic_id "
                "WHERE f.relics_fts MATCH ? AND r.status = 1 "
                "LIMIT ?"
            )
            # FTS5 MATCH 会把关键词按 trigram 切分，"-/双引号" 等需要转义
            safe_kw = kw.replace('"', '""')
            rows = conn.execute(sql, (f'"{safe_kw}"', int(limit))).fetchall()
        else:
            sql = (
                "SELECT id, code, name, category, rank, lng, lat, has_3d "
                "FROM relics WHERE status = 1 AND name LIKE ? LIMIT ?"
            )
            rows = conn.execute(sql, (f"%{kw}%", int(limit))).fetchall()

        return [
            {
                "id": r["id"], "code": r["code"], "name": r["name"],
                "lng": r["lng"], "lat": r["lat"],
                "category": r["category"], "rank": r["rank"],
                "has_3d": bool(r["has_3d"]),
            }
            for r in rows
        ]

    def _peek_memory(self, kw: str, limit: int) -> list[dict]:
        """JSON fallback：遍历 self.relics 按 name contains 过滤。"""
        out = []
        for r in self.relics:
            if kw in (r.get("name") or ""):
                out.append({
                    "id": r.get("archive_code"), "code": r.get("archive_code"),
                    "name": r.get("name"),
                    "lng": r.get("center_lng"), "lat": r.get("center_lat"),
                    "category": r.get("category_main"), "rank": r.get("heritage_level"),
                    "has_3d": bool(r.get("has_3d")),
                })
                if len(out) >= limit:
                    break
        return out

    @lru_cache(maxsize=1024)
    def get_relic_full(self, code: str) -> Optional[dict]:
        """单条文物完整详情，含 extra_json 合并。DB 模式走 DB，否则走内存。"""
        if self._use_db:
            conn = self._thread_conn()
            row = conn.execute(
                "SELECT * FROM relics WHERE code = ? AND status = 1", (code,)
            ).fetchone()
            if not row:
                return None
            extra = {}
            if row["extra_json"]:
                try:
                    extra = json.loads(row["extra_json"]) or {}
                except json.JSONDecodeError:
                    pass
            d = _row_to_legacy(row, extra)
            d["photos"] = self.get_photos(code)
            d["drawings"] = self.get_drawings(code)
            if self.pdf_map.get(code):
                d["has_pdf"] = True
                d["pdf_path"] = self.pdf_map[code]
            return d
        return self.relics_map.get(code)

    def polygon_of(self, code: str) -> Optional[dict]:
        """单条文物的多边形几何 geojson。仅 DB 模式有效。"""
        if not self._use_db:
            return None
        conn = self._thread_conn()
        row = conn.execute(
            "SELECT geom_geojson FROM polygons WHERE relic_code = ?", (code,)
        ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["geom_geojson"])
        except json.JSONDecodeError:
            return None

    # ── 写入接口（Admin）─────────────────────────────────────
    # 乐观锁：每次 UPDATE 必须匹配 expected_version，成功后 version += 1。
    # 所有写操作都落审计表 audit_log，记录 before_json / after_json 便于回溯。

    # 允许通过 admin 写入的主表字段（白名单：避免 SQL 注入通过列名）
    _WRITABLE = {
        "name", "category", "rank", "search_type",
        "lng", "lat", "alt", "township", "village", "address",
        "era", "era_stats", "has_3d", "has_pdf", "has_photo",
        "has_boundary", "photo_count", "drawing_count",
        "brief", "extra_json", "status",
    }

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        return {k: row[k] for k in row.keys()}

    def _write_audit(
        self, conn: sqlite3.Connection, *,
        actor: str, action: str, code: str,
        before: Optional[dict], after: Optional[dict],
    ) -> None:
        import time
        conn.execute(
            "INSERT INTO audit_log (actor, action, relic_code, before_json, after_json, ts) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                actor or "",
                action,
                code,
                json.dumps(before, ensure_ascii=False) if before else None,
                json.dumps(after, ensure_ascii=False) if after else None,
                int(time.time()),
            ),
        )

    def _rtree_upsert(
        self, conn: sqlite3.Connection, relic_id: str, lng: float, lat: float,
    ) -> None:
        """将文物的 bbox 点同步到 R-Tree 与桥接表。"""
        row = conn.execute(
            "SELECT id_int FROM relics_rtree_map WHERE relic_id = ?", (relic_id,)
        ).fetchone()
        if row:
            id_int = row["id_int"]
            conn.execute(
                "UPDATE relics_rtree SET min_lng=?, max_lng=?, min_lat=?, max_lat=? WHERE id_int=?",
                (lng, lng, lat, lat, id_int),
            )
        else:
            # 用 rowid 占位：插入到 R-Tree 得到 id_int，再写桥接
            cur = conn.execute(
                "INSERT INTO relics_rtree (min_lng, max_lng, min_lat, max_lat) VALUES (?, ?, ?, ?)",
                (lng, lng, lat, lat),
            )
            id_int = cur.lastrowid
            conn.execute(
                "INSERT INTO relics_rtree_map (id_int, relic_id) VALUES (?, ?)",
                (id_int, relic_id),
            )

    def _fts_upsert(self, conn: sqlite3.Connection, row: dict) -> None:
        conn.execute("DELETE FROM relics_fts WHERE code = ?", (row["code"],))
        conn.execute(
            "INSERT INTO relics_fts (code, name, brief, era, township, village) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                row.get("code", ""),
                row.get("name", ""),
                row.get("brief") or "",
                row.get("era") or "",
                row.get("township") or "",
                row.get("village") or "",
            ),
        )

    def create_relic(self, payload: dict, *, actor: str = "") -> dict:
        """创建一条文物。payload 需包含 code/name/category/rank/lng/lat。
        成功返回创建后的完整记录；若 code 重复抛 ValueError。"""
        if not self._use_db:
            raise RuntimeError("create_relic 仅在 DB 模式可用")
        import time
        import uuid as _uuid

        code = str(payload.get("code", "")).strip()
        name = str(payload.get("name", "")).strip()
        if not code or not name:
            raise ValueError("缺少 code 或 name")
        try:
            lng = float(payload["lng"]); lat = float(payload["lat"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("lng/lat 必须是有效坐标")

        conn = self._thread_conn()
        exist = conn.execute("SELECT 1 FROM relics WHERE code = ?", (code,)).fetchone()
        if exist:
            raise ValueError(f"文物编号 {code} 已存在")

        relic_id = str(_uuid.uuid4())
        now = int(time.time())

        conn.execute("BEGIN")
        try:
            conn.execute(
                """INSERT INTO relics (
                    id, code, name, category, rank, search_type,
                    lng, lat, alt, township, village, address,
                    era, era_stats, has_3d, has_pdf, has_photo, has_boundary,
                    photo_count, drawing_count, brief, extra_json,
                    status, version, created_at, updated_at
                ) VALUES (?,?,?,?,?,?, ?,?,?,?,?,?, ?,?,?,?,?,?, ?,?,?,?, ?,?,?,?)""",
                (
                    relic_id, code, name,
                    str(payload.get("category") or "0600"),
                    str(payload.get("rank") or "5"),
                    payload.get("search_type"),
                    lng, lat,
                    float(payload["alt"]) if payload.get("alt") not in (None, "") else None,
                    payload.get("township"), payload.get("village"), payload.get("address"),
                    payload.get("era"), payload.get("era_stats"),
                    1 if payload.get("has_3d") else 0,
                    1 if payload.get("has_pdf") else 0,
                    1 if payload.get("has_photo") else 0,
                    1 if payload.get("has_boundary") else 0,
                    int(payload.get("photo_count") or 0),
                    int(payload.get("drawing_count") or 0),
                    payload.get("brief"),
                    json.dumps(payload.get("extra"), ensure_ascii=False) if payload.get("extra") else None,
                    int(payload.get("status", 1)),
                    1, now, now,
                ),
            )
            self._rtree_upsert(conn, relic_id, lng, lat)
            self._fts_upsert(conn, {
                "code": code, "name": name,
                "brief": payload.get("brief"),
                "era": payload.get("era"),
                "township": payload.get("township"),
                "village": payload.get("village"),
            })
            row = conn.execute("SELECT * FROM relics WHERE id = ?", (relic_id,)).fetchone()
            after = self._row_to_dict(row)
            self._write_audit(conn, actor=actor, action="create", code=code,
                              before=None, after=after)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        # 让内存兼容视图也立即反映新增
        self._populate_legacy_from_db()
        return after

    def update_relic(
        self, code: str, patch: dict, *, expected_version: int, actor: str = "",
    ) -> dict:
        """乐观锁更新。expected_version 不匹配时抛 ValueError("VERSION_CONFLICT")。
        `patch` 只能包含 `_WRITABLE` 里的字段，其它键被忽略。"""
        if not self._use_db:
            raise RuntimeError("update_relic 仅在 DB 模式可用")
        import time

        conn = self._thread_conn()
        before_row = conn.execute("SELECT * FROM relics WHERE code = ?", (code,)).fetchone()
        if not before_row:
            raise ValueError(f"文物 {code} 不存在")
        if int(before_row["version"]) != int(expected_version):
            raise ValueError("VERSION_CONFLICT")

        sets = []
        params: list = []
        for k, v in (patch or {}).items():
            if k not in self._WRITABLE:
                continue
            if k == "extra_json" and isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False)
            sets.append(f"{k} = ?")
            params.append(v)
        if not sets:
            raise ValueError("没有可更新的字段")

        now = int(time.time())
        sets.append("updated_at = ?")
        params.append(now)
        sets.append("version = version + 1")
        params.extend([code, expected_version])

        conn.execute("BEGIN")
        try:
            cur = conn.execute(
                f"UPDATE relics SET {', '.join(sets)} WHERE code = ? AND version = ?",
                params,
            )
            if cur.rowcount != 1:
                # 通常是被其他线程抢先更新，版本号不一致
                conn.execute("ROLLBACK")
                raise ValueError("VERSION_CONFLICT")
            row = conn.execute("SELECT * FROM relics WHERE code = ?", (code,)).fetchone()
            # 同步 R-Tree / FTS
            if ("lng" in patch) or ("lat" in patch):
                self._rtree_upsert(conn, row["id"], row["lng"], row["lat"])
            if any(k in patch for k in ("name", "brief", "era", "township", "village")):
                self._fts_upsert(conn, {
                    "code": row["code"], "name": row["name"],
                    "brief": row["brief"], "era": row["era"],
                    "township": row["township"], "village": row["village"],
                })
            after = self._row_to_dict(row)
            self._write_audit(conn, actor=actor, action="update", code=code,
                              before=self._row_to_dict(before_row), after=after)
            conn.execute("COMMIT")
        except Exception:
            try: conn.execute("ROLLBACK")
            except Exception: pass
            raise
        self._populate_legacy_from_db()
        return after

    def delete_relic(self, code: str, *, actor: str = "") -> None:
        """软删除：status 置 -1，版本号递增。保留主键与空间/FTS 索引以便恢复。"""
        if not self._use_db:
            raise RuntimeError("delete_relic 仅在 DB 模式可用")
        import time

        conn = self._thread_conn()
        before_row = conn.execute("SELECT * FROM relics WHERE code = ?", (code,)).fetchone()
        if not before_row:
            raise ValueError(f"文物 {code} 不存在")

        conn.execute("BEGIN")
        try:
            conn.execute(
                "UPDATE relics SET status = -1, version = version + 1, updated_at = ? WHERE code = ?",
                (int(time.time()), code),
            )
            self._write_audit(conn, actor=actor, action="delete", code=code,
                              before=self._row_to_dict(before_row), after=None)
            conn.execute("COMMIT")
        except Exception:
            try: conn.execute("ROLLBACK")
            except Exception: pass
            raise
        self._populate_legacy_from_db()

    def list_audit(
        self,
        *,
        code: Optional[str] = None,
        limit: int = 100,
        actions: Optional[Iterable[str]] = None,
        actor: Optional[str] = None,
        field: Optional[str] = None,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
    ) -> list[dict]:
        """读取审计日志，最近的在前。

        支持多条件筛选：
        - code: 精确匹配 relic_code
        - actions: 限定 action 集合（create/update/delete/rollback）
        - actor: actor LIKE %x%
        - field: 判定 before_json/after_json 中是否出现该字段（LIKE `%"field":%`）
        - start_ts / end_ts: 时间戳区间（秒）
        """
        if not self._use_db:
            return []
        conn = self._thread_conn()
        where: list[str] = []
        params: list = []
        if code:
            where.append("relic_code = ?"); params.append(code)
        if actions:
            al = [str(a) for a in actions if a]
            if al:
                where.append(f"action IN ({','.join('?' for _ in al)})")
                params.extend(al)
        if actor:
            where.append("actor LIKE ?"); params.append(f"%{actor}%")
        if field:
            # 匹配 JSON 字段 key（before 或 after 任一出现即命中）
            pat = f'%"{field}":%'
            where.append("(before_json LIKE ? OR after_json LIKE ?)")
            params.extend([pat, pat])
        if start_ts is not None:
            where.append("ts >= ?"); params.append(int(start_ts))
        if end_ts is not None:
            where.append("ts <= ?"); params.append(int(end_ts))
        where_sql = (" WHERE " + " AND ".join(where)) if where else ""
        rows = conn.execute(
            f"SELECT * FROM audit_log{where_sql} ORDER BY id DESC LIMIT ?",
            [*params, max(1, min(limit, 1000))],
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def rollback_audit(self, audit_id: int, *, actor: str = "") -> dict:
        """按审计记录回滚：
        - action=update：用 before_json 覆写当前值（当 _WRITABLE 白名单内）
        - action=delete：用 before_json 恢复（包含 status=before.status）
        - action=create：等价于再次软删当前文物

        会以当前版本号做乐观锁；若文物已被彻底删除则拒绝。
        额外写一条 audit，action=rollback，标明 target=<audit_id>。
        """
        if not self._use_db:
            raise RuntimeError("rollback_audit 仅在 DB 模式可用")
        conn = self._thread_conn()
        row = conn.execute(
            "SELECT id, action, relic_code, before_json, after_json FROM audit_log WHERE id=?",
            (int(audit_id),),
        ).fetchone()
        if not row:
            raise ValueError("审计记录不存在")
        action = row["action"] or ""
        code = row["relic_code"] or ""
        if not code:
            raise ValueError("该审计记录缺少 relic_code，无法回滚")
        before = json.loads(row["before_json"]) if row["before_json"] else None

        tag = f"rollback#{audit_id}"
        stamp = f"{actor or ''} [{tag}]".strip()

        if action == "create":
            # 回滚 create = 软删
            self.delete_relic(code, actor=stamp)
            return {"ok": True, "action_taken": "delete", "code": code}

        if action in ("update", "delete", "rollback"):
            if not before:
                raise ValueError("该记录缺少 before_json，无法回滚")
            cur = conn.execute(
                "SELECT version FROM relics WHERE code=?", (code,)
            ).fetchone()
            if not cur:
                raise ValueError("该文物已彻底删除，无法回滚")
            ev = int(cur["version"])
            patch = {k: before.get(k) for k in before.keys() if k in self._WRITABLE}
            if not patch:
                raise ValueError("before_json 无可写字段，无法回滚")
            self.update_relic(code, patch, expected_version=ev, actor=stamp)
            return {"ok": True, "action_taken": "update", "code": code}

        raise ValueError(f"不支持回滚的 action: {action}")

    def admin_neighbors(
        self,
        code: str,
        *,
        radius_m: float = 2000.0,
        limit: int = 20,
    ) -> list[dict]:
        """返回文物 `code` 附近 radius_m 米内的其它文物（按距离升序）。

        - 排除自己与软删除
        - 粗筛用 bbox（度数换算），精算用 haversine
        """
        if not self._use_db:
            return []
        import math
        conn = self._thread_conn()
        me = conn.execute(
            "SELECT lng, lat FROM relics WHERE code=?", (code,)
        ).fetchone()
        if not me or me["lng"] is None or me["lat"] is None:
            return []
        lng0 = float(me["lng"]); lat0 = float(me["lat"])
        # 度数边距：1° lat ≈ 111km
        dlat = radius_m / 111_000.0
        dlng = radius_m / (111_000.0 * max(math.cos(math.radians(lat0)), 0.01))
        rows = conn.execute(
            """
            SELECT code, name, category, rank, lng, lat, township, village, era_stats
            FROM relics
            WHERE status >= 0 AND code <> ?
              AND lng IS NOT NULL AND lat IS NOT NULL
              AND lng BETWEEN ? AND ? AND lat BETWEEN ? AND ?
            """,
            (code, lng0 - dlng, lng0 + dlng, lat0 - dlat, lat0 + dlat),
        ).fetchall()

        def _haversine(lng1, lat1, lng2, lat2) -> float:
            R = 6371_000.0
            p1 = math.radians(lat1); p2 = math.radians(lat2)
            dp = math.radians(lat2 - lat1); dl = math.radians(lng2 - lng1)
            a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
            return 2 * R * math.asin(math.sqrt(a))

        out: list[dict] = []
        for r in rows:
            d = _haversine(lng0, lat0, float(r["lng"]), float(r["lat"]))
            if d > radius_m:
                continue
            out.append({
                "code": r["code"],
                "name": r["name"],
                "category": r["category"],
                "rank": r["rank"],
                "lng": r["lng"],
                "lat": r["lat"],
                "township": r["township"] or "",
                "village": r["village"] or "",
                "era_stats": r["era_stats"] or "",
                "distance_m": round(d, 1),
            })
        out.sort(key=lambda x: x["distance_m"])
        return out[: max(1, min(int(limit), 200))]

    # ── 后台分页查询（给 /api/admin/relics 用） ─────────────────
    def admin_list_relics(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: Optional[str] = None,
        categories: Optional[Iterable[str]] = None,
        ranks: Optional[Iterable[str]] = None,
        township: Optional[str] = None,
        search_type: Optional[str] = None,
        status: Optional[int] = None,
        bbox: Optional[tuple] = None,
        order_by: str = "updated_at_desc",
    ) -> dict:
        """后台分页列表。返回 {data, total, page, size}。

        `search` 同时匹配 code 前缀和 name 子串；
        `status` 默认（None）返回 status >= 0 的正常/草稿条目，不含软删除。
        """
        if not self._use_db:
            # JSON 模式下没 DB，只能用内存 relics 做一次简单分页
            return self._admin_list_legacy(
                page=page, size=size, search=search,
                categories=categories, ranks=ranks,
                township=township, search_type=search_type,
            )

        where: list[str] = []
        params: list = []
        if search:
            where.append("(r.code LIKE ? OR r.name LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])
        if categories:
            cl = [str(v) for v in categories if v not in (None, "")]
            if cl:
                where.append(f"r.category IN ({','.join('?' for _ in cl)})")
                params.extend(cl)
        if ranks:
            rl = [str(v) for v in ranks if v not in (None, "")]
            if rl:
                where.append(f"r.rank IN ({','.join('?' for _ in rl)})")
                params.extend(rl)
        if township:
            where.append("r.township = ?")
            params.append(township)
        if search_type:
            where.append("r.search_type = ?")
            params.append(str(search_type))
        if status is None:
            where.append("r.status >= 0")
        else:
            where.append("r.status = ?")
            params.append(int(status))
        if bbox:
            try:
                mnl, mnt, mxl, mxt = [float(v) for v in bbox]
                if mnl > mxl: mnl, mxl = mxl, mnl
                if mnt > mxt: mnt, mxt = mxt, mnt
                where.append(
                    "r.lng IS NOT NULL AND r.lat IS NOT NULL "
                    "AND r.lng BETWEEN ? AND ? AND r.lat BETWEEN ? AND ?"
                )
                params.extend([mnl, mxl, mnt, mxt])
            except (TypeError, ValueError):
                pass

        where_sql = (" WHERE " + " AND ".join(where)) if where else ""

        order_map = {
            "updated_at_desc": "r.updated_at DESC",
            "updated_at_asc":  "r.updated_at ASC",
            "code_asc":        "r.code ASC",
            "code_desc":       "r.code DESC",
            "name_asc":        "r.name ASC",
        }
        order_sql = order_map.get(order_by, "r.updated_at DESC")

        page = max(1, int(page))
        size = max(1, min(int(size), 200))
        offset = (page - 1) * size

        conn = self._thread_conn()
        total_row = conn.execute(
            f"SELECT COUNT(*) AS n FROM relics AS r{where_sql}", params,
        ).fetchone()
        total = int(total_row["n"]) if total_row else 0

        rows = conn.execute(
            f"""
            SELECT r.id, r.code, r.name, r.category, r.rank, r.search_type,
                   r.lng, r.lat, r.township, r.village, r.era, r.era_stats,
                   r.has_3d, r.has_pdf, r.has_photo, r.has_boundary,
                   r.photo_count, r.drawing_count,
                   r.status, r.version, r.updated_at
            FROM relics AS r{where_sql}
            ORDER BY {order_sql}
            LIMIT ? OFFSET ?
            """,
            [*params, size, offset],
        ).fetchall()

        data = [
            {
                "id": r["id"],
                "code": r["code"],
                "name": r["name"],
                "category": r["category"],
                "rank": r["rank"],
                "search_type": r["search_type"] or "",
                "lng": r["lng"],
                "lat": r["lat"],
                "township": r["township"] or "",
                "village": r["village"] or "",
                "era": r["era"] or "",
                "era_stats": r["era_stats"] or "",
                "has_3d": bool(r["has_3d"]),
                "has_pdf": bool(r["has_pdf"]),
                "has_photo": bool(r["has_photo"]),
                "has_boundary": bool(r["has_boundary"]),
                "photo_count": r["photo_count"] or 0,
                "drawing_count": r["drawing_count"] or 0,
                "status": r["status"],
                "version": r["version"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]
        return {"data": data, "total": total, "page": page, "size": size}

    def _admin_list_legacy(
        self, *, page, size, search, categories, ranks,
        township, search_type,
    ) -> dict:
        """JSON 模式下的简易分页，性能只够 demo。"""
        from codes import normalize_category, normalize_rank, normalize_search_type
        rank_set = {str(v) for v in ranks} if ranks else None
        cat_set = {str(v) for v in categories} if categories else None
        s = (search or "").strip()
        out = []
        for r in self.relics:
            code = (r.get("archive_code") or "").strip()
            name = (r.get("name") or "").strip()
            if s and s not in code and s not in name:
                continue
            c = normalize_category(r.get("category_main"))
            rk = normalize_rank(r.get("heritage_level"))
            st = normalize_search_type(r.get("survey_type"))
            if cat_set and c not in cat_set:
                continue
            if rank_set and rk not in rank_set:
                continue
            if township and (r.get("township") or "") != township:
                continue
            if search_type and st != str(search_type):
                continue
            out.append({
                "id": code,
                "code": code,
                "name": name,
                "category": c,
                "rank": rk,
                "search_type": st,
                "lng": r.get("center_lng"),
                "lat": r.get("center_lat"),
                "township": r.get("township") or "",
                "village": r.get("village") or "",
                "era": r.get("era") or "",
                "era_stats": r.get("era_stats") or "",
                "has_3d": bool(r.get("has_3d")),
                "has_pdf": False,
                "has_photo": (r.get("photo_count") or 0) > 0,
                "has_boundary": bool(r.get("has_boundary")),
                "photo_count": r.get("photo_count") or 0,
                "drawing_count": r.get("drawing_count") or 0,
                "status": 1,
                "version": 1,
                "updated_at": None,
            })
        total = len(out)
        page = max(1, int(page)); size = max(1, min(int(size), 200))
        lo = (page - 1) * size
        return {"data": out[lo:lo + size], "total": total, "page": page, "size": size}

    # ── 批量操作（后台多选工具用）───────────────────────
    def admin_bulk_update(
        self,
        codes: Iterable[str],
        patch: dict,
        *,
        actor: str = "",
    ) -> dict:
        """对多条文物同字段批量更新；对每条各自读 version + 写回，
        乐观锁冲突 / 不存在 / 其它异常都单独记录，不打断整批。

        支持字段受 `_WRITABLE` 约束；空 patch 会抛 ValueError。
        返回：{ updated, not_found:[code…], failed:[{code,error}…] }。
        """
        if not self._use_db:
            raise RuntimeError("admin_bulk_update 仅在 DB 模式可用")
        clean = {k: v for k, v in (patch or {}).items() if k in self._WRITABLE}
        if not clean:
            raise ValueError("没有可更新的字段")

        updated = 0
        not_found: list[str] = []
        failed: list[dict] = []
        conn = self._thread_conn()
        for raw_code in codes or []:
            code = str(raw_code or "").strip()
            if not code:
                continue
            row = conn.execute(
                "SELECT version FROM relics WHERE code = ?", (code,)
            ).fetchone()
            if not row:
                not_found.append(code)
                continue
            try:
                self.update_relic(
                    code, dict(clean),
                    expected_version=int(row["version"]), actor=actor,
                )
                updated += 1
            except ValueError as e:
                failed.append({"code": code, "error": str(e)})
            except Exception as e:  # pragma: no cover - 兜底
                failed.append({"code": code, "error": str(e)})
        return {"updated": updated, "not_found": not_found, "failed": failed}

    def admin_bulk_delete(
        self, codes: Iterable[str], *, actor: str = "",
    ) -> dict:
        """批量软删除。和 admin_bulk_update 一样：错一条算一条，不打断。"""
        if not self._use_db:
            raise RuntimeError("admin_bulk_delete 仅在 DB 模式可用")
        deleted = 0
        not_found: list[str] = []
        failed: list[dict] = []
        for raw_code in codes or []:
            code = str(raw_code or "").strip()
            if not code:
                continue
            try:
                self.delete_relic(code, actor=actor)
                deleted += 1
            except ValueError as e:
                msg = str(e)
                if "不存在" in msg:
                    not_found.append(code)
                else:
                    failed.append({"code": code, "error": msg})
            except Exception as e:  # pragma: no cover
                failed.append({"code": code, "error": str(e)})
        return {"deleted": deleted, "not_found": not_found, "failed": failed}

    def admin_export_relics(
        self,
        *,
        search: Optional[str] = None,
        categories: Optional[Iterable[str]] = None,
        ranks: Optional[Iterable[str]] = None,
        township: Optional[str] = None,
        search_type: Optional[str] = None,
        status: Optional[int] = None,
        codes: Optional[Iterable[str]] = None,
        bbox: Optional[tuple] = None,
        order_by: str = "code_asc",
    ) -> Iterable[dict]:
        """按筛选条件/显式 code 列表导出所有匹配文物（生成器，适合流式写 CSV）。

        `codes` 给出时，其他筛选被忽略，只按这批 code 出。不分页——调用方负责节流。
        """
        if not self._use_db:
            # legacy 走内存：先拿 list 再一页页拉
            def _gen_legacy():
                page = 1
                while True:
                    r = self._admin_list_legacy(
                        page=page, size=200, search=search,
                        categories=categories, ranks=ranks,
                        township=township, search_type=search_type,
                    )
                    for row in r["data"]:
                        yield row
                    if page * r["size"] >= r["total"]:
                        break
                    page += 1
            yield from _gen_legacy()
            return

        conn = self._thread_conn()
        codes_list = [str(c).strip() for c in (codes or []) if str(c).strip()]

        where: list[str] = []
        params: list = []
        if codes_list:
            where.append(f"r.code IN ({','.join('?' for _ in codes_list)})")
            params.extend(codes_list)
        else:
            if search:
                where.append("(r.code LIKE ? OR r.name LIKE ?)")
                params.extend([f"%{search}%", f"%{search}%"])
            if categories:
                cl = [str(v) for v in categories if v not in (None, "")]
                if cl:
                    where.append(f"r.category IN ({','.join('?' for _ in cl)})")
                    params.extend(cl)
            if ranks:
                rl = [str(v) for v in ranks if v not in (None, "")]
                if rl:
                    where.append(f"r.rank IN ({','.join('?' for _ in rl)})")
                    params.extend(rl)
            if township:
                where.append("r.township = ?")
                params.append(township)
            if search_type:
                where.append("r.search_type = ?")
                params.append(str(search_type))
            if status is None:
                where.append("r.status >= 0")
            else:
                where.append("r.status = ?")
                params.append(int(status))
            if bbox:
                try:
                    mnl, mnt, mxl, mxt = [float(v) for v in bbox]
                    if mnl > mxl: mnl, mxl = mxl, mnl
                    if mnt > mxt: mnt, mxt = mxt, mnt
                    where.append(
                        "r.lng IS NOT NULL AND r.lat IS NOT NULL "
                        "AND r.lng BETWEEN ? AND ? AND r.lat BETWEEN ? AND ?"
                    )
                    params.extend([mnl, mxl, mnt, mxt])
                except (TypeError, ValueError):
                    pass

        where_sql = (" WHERE " + " AND ".join(where)) if where else ""
        order_map = {
            "updated_at_desc": "r.updated_at DESC",
            "updated_at_asc":  "r.updated_at ASC",
            "code_asc":        "r.code ASC",
            "code_desc":       "r.code DESC",
            "name_asc":        "r.name ASC",
        }
        order_sql = order_map.get(order_by, "r.code ASC")
        cur = conn.execute(
            f"""
            SELECT r.code, r.name, r.category, r.rank, r.search_type,
                   r.era, r.era_stats,
                   r.lng, r.lat, r.alt,
                   r.township, r.village, r.address,
                   r.has_3d, r.has_pdf, r.has_photo, r.has_boundary,
                   r.photo_count, r.drawing_count,
                   r.brief, r.status, r.version, r.updated_at
            FROM relics AS r{where_sql}
            ORDER BY {order_sql}
            """,
            params,
        )
        for r in cur:
            yield {k: r[k] for k in r.keys()}

    def admin_stats_overview(self) -> dict:
        """后台首页聚合指标：一次 SQL 拿齐，避免前端多次往返。

        返回字段：
          totals        各类汇总（总数、3D、PDF、照片、有边界、草稿、删除）
          by_category   文物大类分布（code/label/count）
          by_rank       保护级别分布
          by_search_type 普查来源分布
          by_township_top15  乡镇 Top15
          by_era_stats_top8  年代 Top8
          audit_14days  过去 14 天审计变更（按日按动作统计）
          audit_recent  最近 10 条审计记录（人话版）
          last_updated  数据库最新一次更新时间戳（秒）
        """
        if not self._use_db:
            return self._admin_stats_legacy()

        conn = self._thread_conn()

        # ── 总数 & 布尔字段计数（一条 SQL 搞完）────────
        t = conn.execute(
            """
            SELECT
                SUM(CASE WHEN status = 1  THEN 1 ELSE 0 END) AS total,
                SUM(CASE WHEN status = 0  THEN 1 ELSE 0 END) AS drafts,
                SUM(CASE WHEN status = -1 THEN 1 ELSE 0 END) AS deleted,
                SUM(CASE WHEN status = 1 AND has_3d = 1       THEN 1 ELSE 0 END) AS has_3d,
                SUM(CASE WHEN status = 1 AND has_pdf = 1      THEN 1 ELSE 0 END) AS has_pdf,
                SUM(CASE WHEN status = 1 AND has_photo = 1    THEN 1 ELSE 0 END) AS has_photo,
                SUM(CASE WHEN status = 1 AND has_boundary = 1 THEN 1 ELSE 0 END) AS has_boundary,
                MAX(updated_at) AS last_updated
            FROM relics
            """,
        ).fetchone()
        totals = {
            "total":        int(t["total"] or 0),
            "drafts":       int(t["drafts"] or 0),
            "deleted":      int(t["deleted"] or 0),
            "has_3d":       int(t["has_3d"] or 0),
            "has_pdf":      int(t["has_pdf"] or 0),
            "has_photo":    int(t["has_photo"] or 0),
            "has_boundary": int(t["has_boundary"] or 0),
        }
        last_updated = int(t["last_updated"] or 0)

        # ── 类别 / 级别 / 来源 分布 ─────────────────────
        from codes import CATEGORY_CODES, RANK_CODES, SEARCH_TYPE_CODES

        def _count_group(col: str) -> dict:
            rows = conn.execute(
                f"SELECT {col} AS k, COUNT(*) AS n FROM relics WHERE status = 1 GROUP BY {col}"
            ).fetchall()
            return {str(r["k"] or ""): int(r["n"]) for r in rows}

        cat_counts = _count_group("category")
        rank_counts = _count_group("rank")
        st_counts = _count_group("search_type")

        by_category = [
            {"code": c, "label": CATEGORY_CODES[c], "count": cat_counts.get(c, 0)}
            for c in CATEGORY_CODES
        ]
        by_rank = [
            {"code": c, "label": RANK_CODES[c], "count": rank_counts.get(c, 0)}
            for c in RANK_CODES
        ]
        by_search_type = [
            {"code": c, "label": SEARCH_TYPE_CODES[c], "count": st_counts.get(c, 0)}
            for c in SEARCH_TYPE_CODES
        ]

        # ── 乡镇 Top15 ─────────────────────────────────
        rows = conn.execute(
            """
            SELECT township AS k, COUNT(*) AS n FROM relics
            WHERE status = 1 AND township IS NOT NULL AND township <> ''
            GROUP BY township ORDER BY n DESC LIMIT 15
            """,
        ).fetchall()
        by_township_top = [{"name": r["k"], "count": int(r["n"])} for r in rows]

        # ── 年代 Top8 ─────────────────────────────────
        rows = conn.execute(
            """
            SELECT era_stats AS k, COUNT(*) AS n FROM relics
            WHERE status = 1 AND era_stats IS NOT NULL AND era_stats <> ''
            GROUP BY era_stats ORDER BY n DESC LIMIT 8
            """,
        ).fetchall()
        by_era_stats_top = [{"name": r["k"], "count": int(r["n"])} for r in rows]

        # ── 过去 14 天审计变更（按日按动作）────────────
        import time as _time
        now = int(_time.time())
        start = now - 13 * 86400
        # 按本地日统一到 00:00 方便分桶；这里用 sqlite date() 以 UTC 为准，
        # 对中国用户偏差约 8h，但统计趋势够用。前端不再二次转换。
        rows = conn.execute(
            """
            SELECT
                strftime('%Y-%m-%d', ts, 'unixepoch', 'localtime') AS day,
                action,
                COUNT(*) AS n
            FROM audit_log
            WHERE ts >= ?
            GROUP BY day, action
            """,
            (start,),
        ).fetchall()
        # 构造 14 天完整序列（缺失日补 0）
        import datetime as _dt
        today = _dt.date.fromtimestamp(now)
        days = [(today - _dt.timedelta(days=13 - i)).isoformat() for i in range(14)]
        action_map = {"create": {}, "update": {}, "delete": {}}
        for r in rows:
            act = r["action"] or "update"
            if act not in action_map:
                action_map[act] = {}
            action_map[act][r["day"]] = int(r["n"])
        audit_14days = {
            "days": days,
            "create": [action_map["create"].get(d, 0) for d in days],
            "update": [action_map["update"].get(d, 0) for d in days],
            "delete": [action_map["delete"].get(d, 0) for d in days],
        }

        # ── 最近 10 条审计 ─────────────────────────────
        rows = conn.execute(
            """
            SELECT a.id, a.ts, a.actor, a.action, a.relic_code, r.name
            FROM audit_log a
            LEFT JOIN relics r ON r.code = a.relic_code
            ORDER BY a.id DESC LIMIT 10
            """,
        ).fetchall()
        audit_recent = [
            {
                "id": r["id"],
                "ts": r["ts"],
                "actor": r["actor"] or "",
                "action": r["action"] or "",
                "relic_code": r["relic_code"] or "",
                "relic_name": r["name"] or "",
            }
            for r in rows
        ]

        return {
            "totals": totals,
            "by_category": by_category,
            "by_rank": by_rank,
            "by_search_type": by_search_type,
            "by_township_top": by_township_top,
            "by_era_stats_top": by_era_stats_top,
            "audit_14days": audit_14days,
            "audit_recent": audit_recent,
            "last_updated": last_updated,
        }

    def _admin_stats_legacy(self) -> dict:
        """JSON 模式下 fallback：从内存 relics 现算。只返最低限度字段。"""
        from codes import CATEGORY_CODES, RANK_CODES, SEARCH_TYPE_CODES
        from codes import normalize_category, normalize_rank, normalize_search_type

        total = len(self.relics)
        has_3d = sum(1 for r in self.relics if r.get("has_3d"))
        has_boundary = sum(1 for r in self.relics if r.get("has_boundary"))
        has_photo = sum(1 for r in self.relics if (r.get("photo_count") or 0) > 0)

        cat_counts: dict[str, int] = {}
        rank_counts: dict[str, int] = {}
        st_counts: dict[str, int] = {}
        twp_counts: dict[str, int] = {}
        era_counts: dict[str, int] = {}
        for r in self.relics:
            cat_counts[normalize_category(r.get("category_main"))] = cat_counts.get(normalize_category(r.get("category_main")), 0) + 1
            rank_counts[normalize_rank(r.get("heritage_level"))] = rank_counts.get(normalize_rank(r.get("heritage_level")), 0) + 1
            st = normalize_search_type(r.get("survey_type"))
            st_counts[st] = st_counts.get(st, 0) + 1
            t = (r.get("township") or "").strip()
            if t:
                twp_counts[t] = twp_counts.get(t, 0) + 1
            e = (r.get("era_stats") or "").strip()
            if e:
                era_counts[e] = era_counts.get(e, 0) + 1

        return {
            "totals": {
                "total": total, "drafts": 0, "deleted": 0,
                "has_3d": has_3d, "has_pdf": 0,
                "has_photo": has_photo, "has_boundary": has_boundary,
            },
            "by_category": [
                {"code": c, "label": CATEGORY_CODES[c], "count": cat_counts.get(c, 0)}
                for c in CATEGORY_CODES
            ],
            "by_rank": [
                {"code": c, "label": RANK_CODES[c], "count": rank_counts.get(c, 0)}
                for c in RANK_CODES
            ],
            "by_search_type": [
                {"code": c, "label": SEARCH_TYPE_CODES[c], "count": st_counts.get(c, 0)}
                for c in SEARCH_TYPE_CODES
            ],
            "by_township_top": [
                {"name": k, "count": v}
                for k, v in sorted(twp_counts.items(), key=lambda x: -x[1])[:15]
            ],
            "by_era_stats_top": [
                {"name": k, "count": v}
                for k, v in sorted(era_counts.items(), key=lambda x: -x[1])[:8]
            ],
            "audit_14days": {"days": [], "create": [], "update": [], "delete": []},
            "audit_recent": [],
            "last_updated": 0,
        }

    def admin_list_townships(self) -> list[str]:
        """DB 里出现过的 township 列表（去重排序，用于筛选下拉）。"""
        if not self._use_db:
            return sorted({(r.get("township") or "").strip() for r in self.relics if r.get("township")})
        conn = self._thread_conn()
        rows = conn.execute(
            "SELECT DISTINCT township FROM relics WHERE township IS NOT NULL AND township <> '' ORDER BY township"
        ).fetchall()
        return [r["township"] for r in rows]

    # ── 工具 ────────────────────────────────────────────────
    @staticmethod
    def _read_csv(path: Path) -> list[dict]:
        with open(path, "r", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))


store = DataStore()

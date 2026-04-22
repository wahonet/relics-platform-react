"""Relics Platform WebGIS 后端入口。

路径/模型/开关等全部来自 config.yaml + `_common.get_paths()`,
应用内不保留任何硬编码的县区/坐标/Key。
"""
from __future__ import annotations

import asyncio
import base64
import json
import math
import sys
import time
import urllib.request
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path

# 把 platform/scripts/ 和 webgis/ 自己加到 sys.path,这样
# `from _common import ...` 和 `from routers import ...` 都能
# 在不把 platform 当包安装的情况下直接 import。
PLATFORM_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLATFORM_ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from starlette.concurrency import run_in_threadpool  # noqa: E402
from starlette.middleware.base import BaseHTTPMiddleware  # noqa: E402

from _common import PROJECT_ROOT, detect_features, get_paths, load_config  # noqa: E402
from data_loader import store  # noqa: E402
from routers import admin, chat, relics, stats, survey_routes, worklog  # noqa: E402
from terrain_provider import get_tile_heights_fast, load_dem  # noqa: E402

# 瓦片缓存未命中时返回的 1x1 透明 PNG
_EMPTY_TILE = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lE"
    "QVQI12NgAAIABQABNjN9GQAAAAlwSFlzAAALEwAACxMBAJqcGAAA"
    "ABl0RVh0U29mdHdhcmUAcGFpbnQubmV0IDQuMC4xMkMEa+wAAAAN"
    "SURBVBhXY2BgYPgPAAEEAQBLzKDhAAAAAElFTkSuQmCC"
)

TILE_URLS = {
    "arcgis_sat": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    "osm": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    "gaode_anno": "https://wprd0{s}.is.autonavi.com/appmaptile?x={x}&y={y}&z={z}&lang=zh_cn&size=1&scl=1&style=8",
    # 高德卫星影像（webst 系列主机）与高德矢量路网（wprd 系列主机）——"在线影像/在线矢量"选项用。
    "gaode_sat": "https://webst0{s}.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}",
    "gaode_vec": "https://wprd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=7&x={x}&y={y}&z={z}",
}

# 只允许离线缓存命中,不许对上游回源的 provider。前端"离线影像/离线矢量"用这两项,
# 保证本地缓存为空时呈现纯黑底图,符合"默认离线地图应该是完全空白"的要求。
OFFLINE_ONLY_PROVIDERS = {"arcgis_sat", "osm"}

_CONFIG: dict = {}
_FEATURES: dict = {}
_PATHS = get_paths()
WEBGIS_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEBGIS_DIR / "templates"
STATIC_DIR = WEBGIS_DIR / "static"
TILE_CACHE_DIR = PROJECT_ROOT / "data" / "output" / "tile_cache"
TILE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
TERRAIN_CACHE_DIR = PROJECT_ROOT / "data" / "output" / "terrain_cache"
TERRAIN_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 瓦片并发控制：上游并发限流、内存 LRU、同 URL 请求去重
TILE_UPSTREAM_SEMAPHORE = asyncio.Semaphore(16)
TILE_MEM_CACHE: OrderedDict[str, bytes] = OrderedDict()
TILE_MEM_CACHE_MAX = 1000
TILE_INFLIGHT: dict[str, asyncio.Future] = {}


def _tile_mem_get(key: str) -> bytes | None:
    data = TILE_MEM_CACHE.get(key)
    if data is not None:
        TILE_MEM_CACHE.move_to_end(key)
    return data


def _tile_mem_put(key: str, data: bytes) -> None:
    TILE_MEM_CACHE[key] = data
    TILE_MEM_CACHE.move_to_end(key)
    while len(TILE_MEM_CACHE) > TILE_MEM_CACHE_MAX:
        TILE_MEM_CACHE.popitem(last=False)


def _offline_only() -> bool:
    features = (_CONFIG.get("features") or {})
    return bool(features.get("offline_only"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _CONFIG, _FEATURES
    _CONFIG = load_config()
    _FEATURES = detect_features().as_dict

    geo = _CONFIG.get("geo") or {}
    bounds = geo.get("bounds") or {}
    bbox = (
        bounds.get("west", -180.0),
        bounds.get("south", -90.0),
        bounds.get("east", 180.0),
        bounds.get("north", 90.0),
    )

    # 以下三项都是可选数据源,存在即加载
    village_gj = _PATHS.output_boundaries / "villages.geojson"  # 村村达需要
    village_arg = str(village_gj) if village_gj.exists() else ""
    pdf_dir = PROJECT_ROOT / "data" / "input" / "01_archives_pdf"
    survey_csv = _PATHS.input_worklogs / "survey_gps.csv"

    store.load(
        str(_PATHS.output_dataset),
        village_geojson=village_arg,
        pdf_dir=str(pdf_dir) if pdf_dir.exists() else "",
        survey_gps_csv=str(survey_csv) if survey_csv.exists() else "",
        bounds=bbox,
    )

    print(f"[启动] 已加载 {len(store.relics)} 条文物记录")
    print(f"[启动] 已加载 {len(store.photo_index)} 条照片索引")
    print(f"[启动] 已加载 {len(store.drawing_index)} 条图纸索引")
    print(f"[启动] 已索引 {len(store.pdf_map)} 个档案 PDF")
    print(f"[启动] 已加载 {len(store.survey_routes)} 天普查路线")
    if store.village_coverage:
        vc = store.village_coverage
        print(f"[启动] 村村达: {vc['reached']}/{vc['total']} 村已到达")

    cached = sum(1 for _ in TILE_CACHE_DIR.rglob("*.tile"))
    print(f"[启动] 瓦片缓存: {cached} 张 → {TILE_CACHE_DIR}")

    dem_dir = _PATHS.input_dem
    enable_dem = _feature_enabled("enable_dem", _FEATURES.get("dem", False))
    if enable_dem and dem_dir.exists():
        load_dem(str(dem_dir))
    else:
        print(f"[DEM] 已跳过（enable_dem={enable_dem}, exists={dem_dir.exists()}）")

    try:
        chat.init_chat()
    except Exception as e:
        print(f"[AI] 初始化失败: {e}")

    yield


def _feature_enabled(cfg_key: str, auto_value: bool) -> bool:
    """config.features.<cfg_key>: true/false 强制开关,其他值(含 'auto')
    回退到自动检测结果 auto_value。"""
    v = (_CONFIG.get("features") or {}).get(cfg_key, "auto")
    if isinstance(v, bool):
        return v
    if isinstance(v, str) and v.lower() in ("true", "yes", "on"):
        return True
    if isinstance(v, str) and v.lower() in ("false", "no", "off"):
        return False
    return bool(auto_value)


app = FastAPI(title="Relics Platform", version="1.0.0", lifespan=lifespan)

_PUBLIC_PREFIXES = ("/login", "/api/login", "/static/", "/tiles/", "/api/terrain/", "/api/platform/config")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not (_CONFIG.get("server") or {}).get("enable_auth", False):
            return await call_next(request)
        path = request.url.path
        if any(path == p or path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await call_next(request)
        if request.cookies.get("session") != "authenticated":
            return RedirectResponse(url="/login", status_code=302)
        return await call_next(request)


app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

app.include_router(relics.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(survey_routes.router, prefix="/api")
app.include_router(worklog.router, prefix="/api")


# 前端启动时拉取的运行时配置(项目名/中心点/特性开关/Cesium token 等)。
# 同时通过 _bootstrap_script 注入到 HTML 里,前端优先读 window.__PLATFORM_CONFIG,
# 拉不到再回退到本接口。
@app.get("/api/platform/config")
async def platform_config() -> JSONResponse:
    cfg = _CONFIG or {}
    proj = cfg.get("project", {}) or {}
    geo = cfg.get("geo", {}) or {}
    admin_cfg = cfg.get("administrative", {}) or {}
    api_cfg = cfg.get("api", {}) or {}

    def _resolved(val: str) -> str:
        if not val or (isinstance(val, str) and val.startswith("${") and val.endswith("}")):
            return ""
        return val

    cesium_token = _resolved((api_cfg.get("cesium_ion") or {}).get("token", ""))
    sf = api_cfg.get("siliconflow") or {}

    features_resolved = {
        "ai_chat": _feature_enabled("enable_ai_chat", bool(_resolved(sf.get("key", "")))),
        "worklog": _feature_enabled("enable_worklog", _FEATURES.get("worklogs", False)),
        "models_3d": _feature_enabled("enable_3d_model", _FEATURES.get("models_3d", False)),
        "dem": _feature_enabled("enable_dem", _FEATURES.get("dem", False)),
    }

    return JSONResponse({
        "project": {
            "name": proj.get("name", ""),
            "full_name": proj.get("full_name", ""),
            "data_cutoff": proj.get("data_cutoff", ""),
            "data_source": proj.get("data_source", ""),
        },
        "geo": geo,
        "administrative": {
            "county_name": admin_cfg.get("county_name", ""),
            "townships": admin_cfg.get("townships", []),
        },
        "features": features_resolved,
        "cesium_ion_token": cesium_token,
        "ai_chat": {
            "enabled": features_resolved["ai_chat"],
            "default_model": sf.get("default_model", ""),
            "available_models": sf.get("available_models", []),
        },
        "stats": {
            "relics_total": len(store.relics),
            "has_3d_count": sum(1 for r in store.relics if r.get("has_3d")),
        },
    })


@app.get("/api/config")
async def legacy_config() -> JSONResponse:
    """早期前端用的路径,保持 301 兼容。"""
    return await platform_config()


@app.get("/api/terrain/{level}/{x}/{y}")
async def terrain_tile(level: int, x: int, y: int):
    """DEM 瓦片：磁盘缓存 hit 直接 sendfile，否则现场采样并落盘。
    瓦片为 65*65 Float32，约 17KB，10w 块不到 2GB，全量预计算也可接受。"""
    cache_path = TERRAIN_CACHE_DIR / str(level) / str(x) / f"{y}.bin"
    if cache_path.exists():
        data = await run_in_threadpool(cache_path.read_bytes)
    else:
        data = await run_in_threadpool(get_tile_heights_fast, level, x, y)
        if data:
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                await run_in_threadpool(cache_path.write_bytes, data)
            except Exception as e:
                print(f"[terrain] 写缓存失败 {level}/{x}/{y}: {e}")
    if data is None:
        return Response(status_code=404)
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "public, max-age=86400",
            "Access-Control-Allow-Origin": "*",
        },
    )


def _fetch_tile(provider: str, z: int, x: int, y: int) -> bytes | None:
    tpl = TILE_URLS.get(provider)
    if not tpl:
        return None
    s = str((x % 4) + 1) if provider.startswith("gaode") else str(x % 4)
    url = tpl.format(s=s, x=x, y=y, z=z)
    headers = {"User-Agent": "Mozilla/5.0"}
    if provider.startswith("gaode"):
        headers["Referer"] = "https://www.amap.com/"
    req = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(req, timeout=20).read()


async def _fetch_and_cache_tile(
    provider: str, z: int, x: int, y: int, key: str, cache_path: Path,
    fut: asyncio.Future,
) -> None:
    """上游拉取 + 限流 + 写缓存 + 唤醒等待同一 key 的协程。"""
    try:
        async with TILE_UPSTREAM_SEMAPHORE:
            data = await run_in_threadpool(_fetch_tile, provider, z, x, y)
        if data:
            _tile_mem_put(key, data)
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                await run_in_threadpool(cache_path.write_bytes, data)
            except Exception as e:
                print(f"[tile] 写缓存失败 {key}: {e}")
        if not fut.done():
            fut.set_result(data)
    except Exception as e:
        print(f"[tile] 拉取失败 {key}: {e}")
        if not fut.done():
            fut.set_result(None)
    finally:
        TILE_INFLIGHT.pop(key, None)


@app.get("/tiles/{provider}/{z}/{x}/{y}")
async def tile_proxy(provider: str, z: int, x: int, y: int, request: Request):
    """瓦片代理:
    1) 内存 LRU / 磁盘缓存命中 → 直接返回;
    2) 未命中 + provider 属于 OFFLINE_ONLY_PROVIDERS 或 URL 带 ?offline=1 → 返回 1x1 透明 PNG;
    3) 未命中 + `features.offline_only=true` → 返回 1x1 透明 PNG;
    4) 未命中 + 允许回源 → 并发拉上游(Semaphore(16) + 同 URL 去重),写缓存,返回。
    `?t=<ts>` 的 t 参数仅用于客户端下载完成后破坏浏览器 HTTP 缓存。
    """
    key = f"{provider}/{z}/{x}/{y}"

    mem = _tile_mem_get(key)
    if mem is not None:
        return Response(
            content=mem, media_type="image/png",
            headers={"Cache-Control": "public, max-age=31536000"},
        )

    cache_path = TILE_CACHE_DIR / provider / str(z) / str(x) / f"{y}.tile"
    if cache_path.exists():
        data = await run_in_threadpool(cache_path.read_bytes)
        _tile_mem_put(key, data)
        return Response(
            content=data, media_type="image/png",
            headers={"Cache-Control": "public, max-age=31536000"},
        )

    # 用户请求"纯离线视图"时上游被禁用,保证底图彻底空白。
    wants_offline = request.query_params.get("offline") in ("1", "true", "yes")
    if (
        wants_offline
        or provider in OFFLINE_ONLY_PROVIDERS
        or _offline_only()
        or provider not in TILE_URLS
    ):
        return Response(content=_EMPTY_TILE, media_type="image/png")

    # 同一 key 的并发请求共用一个 future，避免对上游重复拉取
    fut = TILE_INFLIGHT.get(key)
    if fut is None:
        fut = asyncio.get_running_loop().create_future()
        TILE_INFLIGHT[key] = fut
        asyncio.create_task(_fetch_and_cache_tile(provider, z, x, y, key, cache_path, fut))

    try:
        data = await asyncio.wait_for(fut, timeout=25)
    except Exception:
        data = None
    if data:
        return Response(
            content=data, media_type="image/png",
            headers={"Cache-Control": "public, max-age=31536000"},
        )
    return Response(content=_EMPTY_TILE, media_type="image/png")


def _lon_to_tile_x(lon: float, z: int) -> int:
    return int((lon + 180) / 360 * (1 << z))


def _lat_to_tile_y(lat: float, z: int) -> int:
    lat_rad = math.radians(lat)
    return int((1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * (1 << z))


def _bounds_from_config() -> tuple[float, float, float, float]:
    geo = _CONFIG.get("geo") or {}
    b = geo.get("bounds") or {}
    return (
        float(b.get("west", 73.0)),
        float(b.get("south", 18.0)),
        float(b.get("east", 135.0)),
        float(b.get("north", 54.0)),
    )


def _tiles_for_bounds(west, south, east, north, z):
    x0 = _lon_to_tile_x(west, z)
    x1 = _lon_to_tile_x(east, z)
    y0 = _lat_to_tile_y(north, z)
    y1 = _lat_to_tile_y(south, z)
    return [(z, x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]


@app.get("/api/tiles/cache-status")
async def cache_status(provider: str = "arcgis_sat"):
    bbox = _bounds_from_config()
    total, cached_n = 0, 0
    for z in range(1, 16):
        tiles = _tiles_for_bounds(*bbox, z)
        total += len(tiles)
        for tz, tx, ty in tiles:
            if (TILE_CACHE_DIR / provider / str(tz) / str(tx) / f"{ty}.tile").exists():
                cached_n += 1
    return {"total": total, "cached": cached_n}


@app.post("/api/tiles/precache")
async def precache_tiles(provider: str = "arcgis_sat", min_zoom: int = 1, max_zoom: int = 15):
    import concurrent.futures

    if provider not in TILE_URLS:
        provider = "arcgis_sat"

    bbox = _bounds_from_config()
    tasks, skipped = [], 0
    zm = min(max_zoom + 1, 17)
    for z in range(max(1, min_zoom), zm):
        for tz, tx, ty in _tiles_for_bounds(*bbox, z):
            cp = TILE_CACHE_DIR / provider / str(tz) / str(tx) / f"{ty}.tile"
            if cp.exists():
                skipped += 1
            else:
                tasks.append((provider, tz, tx, ty, cp))

    def _dl_one(args):
        prov, z, x, y, cp = args
        try:
            data = _fetch_tile(prov, z, x, y)
            if data:
                cp.parent.mkdir(parents=True, exist_ok=True)
                cp.write_bytes(data)
                return True
        except Exception:
            return False

    def _run():
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            return list(pool.map(_dl_one, tasks))

    results = await run_in_threadpool(_run) if tasks else []
    downloaded = sum(1 for r in results if r)
    failed = sum(1 for r in results if not r)
    return {"downloaded": downloaded, "failed": failed, "skipped": skipped}


def _count_tiles_in_area(providers: list[str], bbox, zooms: list[int]) -> dict:
    """按 bbox + 层级统计瓦片数量（不实际下载），用于前端展示预估体量。"""
    west, south, east, north = bbox
    total = cached = 0
    for z in zooms:
        for tz, tx, ty in _tiles_for_bounds(west, south, east, north, z):
            for prov in providers:
                total += 1
                if (TILE_CACHE_DIR / prov / str(tz) / str(tx) / f"{ty}.tile").exists():
                    cached += 1
    return {"total": total, "cached": cached, "need": max(0, total - cached)}


@app.get("/api/tiles/area-estimate")
async def tiles_area_estimate(
    west: float, south: float, east: float, north: float,
    providers: str = "arcgis_sat,osm",
    zooms: str = "12,13,14,15",
):
    """给定 bbox + provider 列表 + 层级列表，估算需要下载多少瓦片。"""
    if not (west < east and south < north):
        return {"error": "invalid bbox"}
    prov_list = [p for p in providers.split(",") if p in TILE_URLS]
    if not prov_list:
        return {"error": "no valid provider"}
    try:
        z_list = sorted({int(z) for z in zooms.split(",") if z.strip().isdigit()})
    except Exception:
        z_list = []
    if not z_list:
        return {"error": "no zoom"}
    stat = _count_tiles_in_area(prov_list, (west, south, east, north), z_list)
    return {
        "bbox": {"west": west, "south": south, "east": east, "north": north},
        "providers": prov_list,
        "zooms": z_list,
        **stat,
    }


# ── 地图下载作业状态 ─────────────────────────────────────────
# 前端触发一次下载 → 后端分配 job_id → 丢线程池里跑 → 客户端轮询进度。
# 只做内存级状态(进程重启即丢),对"框选下载几千张瓦片"这个量级足够。
import threading
import uuid as _uuid

DOWNLOAD_JOBS: dict[str, dict] = {}
DOWNLOAD_JOBS_LOCK = threading.Lock()
DOWNLOAD_JOB_TTL = 30 * 60  # 超过这个时间没被查询就自动清理
# 持久化历史:进程重启后后台页仍然能看到"我之前下载过哪些区域"
DOWNLOAD_HISTORY_FILE = TILE_CACHE_DIR / "_download_history.jsonl"
DOWNLOAD_HISTORY_MAX = 200  # 最多保留多少条历史


def _job_create(prov_list, z_list, total, skipped, need, bbox=None, label=None):
    jid = _uuid.uuid4().hex[:12]
    with DOWNLOAD_JOBS_LOCK:
        DOWNLOAD_JOBS[jid] = {
            "id": jid,
            "status": "running",
            "providers": prov_list,
            "zooms": z_list,
            "total": total,
            "skipped": skipped,
            "need": need,
            "downloaded": 0,
            "failed": 0,
            "bytes": 0,
            "bbox": bbox,
            "label": label,
            "started_at": time.time(),
            "finished_at": None,
            "error": None,
        }
    return jid


def _append_download_history(entry: dict) -> None:
    """每次下载收尾时把一条记录追加到 jsonl;超过上限就滚动截断头部。
    不用 sqlite,避免引入又一个 schema 迁移点——JSONL 足够用了。
    """
    try:
        DOWNLOAD_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with DOWNLOAD_HISTORY_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        # 文件太长时异步截断(保留最近 DOWNLOAD_HISTORY_MAX 条)
        try:
            with DOWNLOAD_HISTORY_FILE.open("r", encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) > DOWNLOAD_HISTORY_MAX * 2:  # 超过 2 倍才截,减少 IO
                lines = lines[-DOWNLOAD_HISTORY_MAX:]
                DOWNLOAD_HISTORY_FILE.write_text("".join(lines), encoding="utf-8")
        except Exception:
            pass
    except Exception as e:
        print(f"[tile] 写下载历史失败: {e}")


def _read_download_history(limit: int = 50) -> list[dict]:
    if not DOWNLOAD_HISTORY_FILE.exists():
        return []
    try:
        lines = DOWNLOAD_HISTORY_FILE.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    # 倒序展示:最近一次在最上面
    out: list[dict] = []
    for line in reversed(lines[-limit:]):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _job_update(jid, **kwargs):
    with DOWNLOAD_JOBS_LOCK:
        job = DOWNLOAD_JOBS.get(jid)
        if job is not None:
            job.update(kwargs)


def _job_gc():
    """进度接口被调用时顺手 GC 掉老任务。"""
    now = time.time()
    with DOWNLOAD_JOBS_LOCK:
        for jid in list(DOWNLOAD_JOBS.keys()):
            j = DOWNLOAD_JOBS[jid]
            ft = j.get("finished_at") or 0
            if ft and (now - ft) > DOWNLOAD_JOB_TTL:
                DOWNLOAD_JOBS.pop(jid, None)


def _run_download_job(jid: str, tasks: list):
    """在后台线程里跑批量下载,实时往 DOWNLOAD_JOBS[jid] 写进度。"""
    import concurrent.futures

    def _dl_one(args):
        prov, z, x, y, cp = args
        try:
            data = _fetch_tile(prov, z, x, y)
            if data:
                cp.parent.mkdir(parents=True, exist_ok=True)
                cp.write_bytes(data)
                return True, len(data)
        except Exception:
            pass
        return False, 0

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            for ok, nbytes in pool.map(_dl_one, tasks):
                with DOWNLOAD_JOBS_LOCK:
                    job = DOWNLOAD_JOBS.get(jid)
                    if job is None:
                        return
                    if ok:
                        job["downloaded"] += 1
                        job["bytes"] += nbytes
                    else:
                        job["failed"] += 1
        _job_update(jid, status="done", finished_at=time.time())
    except Exception as e:
        _job_update(jid, status="error", error=str(e), finished_at=time.time())

    # 无论成功失败,都把收尾快照写入历史,方便后台页审计
    with DOWNLOAD_JOBS_LOCK:
        snap = dict(DOWNLOAD_JOBS.get(jid) or {})
    if snap:
        _append_download_history({
            "id": snap.get("id"),
            "status": snap.get("status"),
            "label": snap.get("label"),
            "providers": snap.get("providers"),
            "zooms": snap.get("zooms"),
            "bbox": snap.get("bbox"),
            "total": snap.get("total"),
            "skipped": snap.get("skipped"),
            "need": snap.get("need"),
            "downloaded": snap.get("downloaded"),
            "failed": snap.get("failed"),
            "bytes": snap.get("bytes"),
            "started_at": snap.get("started_at"),
            "finished_at": snap.get("finished_at"),
            "error": snap.get("error"),
        })


@app.post("/api/tiles/download-area")
async def download_area_tiles(
    west: float, south: float, east: float, north: float,
    providers: str = "arcgis_sat,osm",
    zooms: str = "12,13,14,15",
    label: str = "",
):
    """启动下载作业,立刻返回 job_id;真正的下载在后台线程里跑。
    `label` 是前端提供的人类可读来源(例如"山东省·青岛市·即墨区"),
    只用来在后台审计页展示,不影响下载本身。
    """
    if not (west < east and south < north):
        return {"error": "invalid bbox"}
    prov_list = [p for p in providers.split(",") if p in TILE_URLS]
    if not prov_list:
        return {"error": "no valid provider"}
    try:
        z_list = sorted({int(z) for z in zooms.split(",") if z.strip().isdigit()})
    except Exception:
        z_list = []
    # 只允许 1~17 的层级,防止误输入击穿上游。
    z_list = [z for z in z_list if 1 <= z <= 17]
    if not z_list:
        return {"error": "no zoom"}

    tasks, skipped = [], 0
    for prov in prov_list:
        for z in z_list:
            for tz, tx, ty in _tiles_for_bounds(west, south, east, north, z):
                cp = TILE_CACHE_DIR / prov / str(tz) / str(tx) / f"{ty}.tile"
                if cp.exists():
                    skipped += 1
                else:
                    tasks.append((prov, tz, tx, ty, cp))

    total = len(tasks) + skipped
    bbox_tuple = [west, south, east, north]
    jid = _job_create(
        prov_list, z_list, total=total, skipped=skipped, need=len(tasks),
        bbox=bbox_tuple, label=(label or None),
    )
    if not tasks:
        _job_update(jid, status="done", finished_at=time.time())
        # 即便一张都不用下,也记录一条"全命中缓存"的历史便于审计
        _append_download_history({
            "id": jid, "status": "done", "label": (label or None),
            "providers": prov_list, "zooms": z_list, "bbox": bbox_tuple,
            "total": total, "skipped": skipped, "need": 0,
            "downloaded": 0, "failed": 0, "bytes": 0,
            "started_at": time.time(), "finished_at": time.time(), "error": None,
        })
        return {"job_id": jid, "total": total, "skipped": skipped, "need": 0}

    threading.Thread(
        target=_run_download_job, args=(jid, tasks), daemon=True
    ).start()

    return {
        "job_id": jid,
        "providers": prov_list,
        "zooms": z_list,
        "total": total,
        "skipped": skipped,
        "need": len(tasks),
    }


@app.get("/api/tiles/download-progress/{job_id}")
async def download_progress(job_id: str):
    """前端轮询这个接口获取进度(已下载/失败/字节数/状态)。"""
    _job_gc()
    with DOWNLOAD_JOBS_LOCK:
        job = DOWNLOAD_JOBS.get(job_id)
        if job is None:
            return {"error": "job not found"}
        return dict(job)


def _collect_cache_info() -> dict:
    info: dict[str, dict] = {}
    for prov_dir in TILE_CACHE_DIR.iterdir() if TILE_CACHE_DIR.exists() else []:
        if not prov_dir.is_dir():
            continue
        count = 0
        size = 0
        for p in prov_dir.rglob("*.tile"):
            try:
                count += 1
                size += p.stat().st_size
            except Exception:
                pass
        info[prov_dir.name] = {"count": count, "bytes": size}
    return {"cache_dir": str(TILE_CACHE_DIR), "providers": info}


@app.get("/api/tiles/cache-info")
async def cache_info():
    """各 provider 的缓存瓦片数量 + 体积,前端下载面板展示用。"""
    return _collect_cache_info()


@app.get("/api/tiles/history")
async def download_history(limit: int = 50):
    """公开的下载历史查询,前端面板 / 后台均可用。
    不含鉴权:和 /api/tiles/* 其它接口保持一致的开放度。
    """
    if limit < 1: limit = 1
    if limit > DOWNLOAD_HISTORY_MAX: limit = DOWNLOAD_HISTORY_MAX
    return {"items": _read_download_history(limit=limit)}


@app.get("/api/admin/tiles/summary")
async def admin_tiles_summary(limit: int = 20):
    """管理后台汇总:缓存体量 + 最近下载历史,给 Dashboard 的"瓦片缓存"卡片用。"""
    cache = _collect_cache_info()
    provs = cache.get("providers") or {}
    total_count = sum(p.get("count", 0) for p in provs.values())
    total_bytes = sum(p.get("bytes", 0) for p in provs.values())

    hist = _read_download_history(limit=max(limit, 1))
    # 最近一次(不含失败)时间
    last_finished = None
    for h in hist:
        if h.get("finished_at"):
            last_finished = h["finished_at"]
            break

    return {
        "cache_dir": cache.get("cache_dir"),
        "providers": provs,
        "totals": {"count": total_count, "bytes": total_bytes},
        "last_finished_at": last_finished,
        "recent": hist[:limit],
    }


@app.post("/api/tiles/open-cache-folder")
async def open_cache_folder():
    """在服务器本机(= 用户电脑)打开瓦片缓存目录。
    仅对本地/单机部署有意义;跨主机访问的生产部署会失败但也无害。
    """
    import subprocess

    TILE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path_str = str(TILE_CACHE_DIR)
    try:
        if sys.platform.startswith("win"):
            # 用 os.startfile 比 `start explorer` 更稳,不会弹出一个黑色 cmd 窗口
            import os as _os
            _os.startfile(path_str)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path_str])
        else:
            subprocess.Popen(["xdg-open", path_str])
        return {"ok": True, "path": path_str}
    except Exception as e:
        return {"ok": False, "path": path_str, "error": str(e)}


@app.post("/api/tiles/clear-cache")
async def clear_cache(providers: str = ""):
    """删除指定 provider(逗号分隔)的磁盘缓存;留空则清空全部。
    请求成功后前端重新切换底图,就能看到真正的"空白离线"效果。
    """
    import shutil

    target_names = [p.strip() for p in providers.split(",") if p.strip()] if providers else None

    removed: dict[str, int] = {}
    if not TILE_CACHE_DIR.exists():
        return {"cleared": removed}

    def _do():
        for prov_dir in list(TILE_CACHE_DIR.iterdir()):
            if not prov_dir.is_dir():
                continue
            if target_names is not None and prov_dir.name not in target_names:
                continue
            count = sum(1 for _ in prov_dir.rglob("*.tile"))
            try:
                shutil.rmtree(prov_dir)
                removed[prov_dir.name] = count
            except Exception as e:
                removed[prov_dir.name] = -1
                print(f"[tile] 清缓存失败 {prov_dir}: {e}")

    await run_in_threadpool(_do)
    # 内存 LRU 也一并重置,避免刚清完磁盘前端还能看到老瓦片
    TILE_MEM_CACHE.clear()
    return {"cleared": removed}


def _mount_if_exists(path_prefix: str, directory: Path, name: str, *, create: bool = False) -> None:
    if create:
        directory.mkdir(parents=True, exist_ok=True)
    if directory.exists():
        app.mount(path_prefix, StaticFiles(directory=str(directory)), name=name)
    else:
        print(f"[警告] 目录不存在，跳过挂载 {path_prefix}: {directory}")


_mount_if_exists("/photos", _PATHS.output_photos, "photos", create=True)
_mount_if_exists("/drawings", _PATHS.output_drawings, "drawings", create=True)
_mount_if_exists("/boundaries", _PATHS.output_boundaries, "boundaries", create=True)
_mount_if_exists("/worklog-pdfs", _PATHS.output_worklogs, "worklog_pdfs", create=True)
_mount_if_exists("/3d", _PATHS.input_models_3d, "3d_models", create=True)
_mount_if_exists("/pdfs", PROJECT_ROOT / "data" / "input" / "01_archives_pdf", "pdfs")
_mount_if_exists("/survey-photos", _PATHS.input_worklogs / "survey_photos", "survey_photos")
_mount_if_exists("/static", STATIC_DIR, "static")

# Vue 后台 SPA：`platform/admin-vue/dist/` 存在时挂载到 /admin-ui/。
# 开发期不需要它（Vite dev server 直连 5173，通过代理调 FastAPI）。
# 生产期跑 `npm run build` 后自动接管 /admin-ui/ 路由，hash 路由无需 catch-all。
_ADMIN_VUE_DIST = PROJECT_ROOT / "platform" / "admin-vue" / "dist"
if _ADMIN_VUE_DIST.exists():
    app.mount("/admin-ui", StaticFiles(directory=str(_ADMIN_VUE_DIST), html=True), name="admin_ui")
    print(f"[启动] Vue 后台已挂载: /admin-ui/ → {_ADMIN_VUE_DIST}")
else:
    print(f"[启动] Vue 后台未构建，跳过挂载 /admin-ui/（开发期正常；生产请先 npm run build）")


def _bootstrap_script() -> str:
    """拼出一段 inline <script>,在其它脚本执行前挂载 window.__PLATFORM_CONFIG,
    并在 Cesium 已加载时自动注入 Ion token。"""
    import json as _json

    proj = (_CONFIG.get("project") or {})
    geo = (_CONFIG.get("geo") or {})
    adm = (_CONFIG.get("administrative") or {})
    api = (_CONFIG.get("api") or {})
    sf = api.get("siliconflow") or {}
    cesium_token = (api.get("cesium_ion") or {}).get("token", "") or ""
    if cesium_token.startswith("${") and cesium_token.endswith("}"):
        cesium_token = ""

    payload = {
        "project": {
            "name": proj.get("name", ""),
            "full_name": proj.get("full_name", ""),
            "data_cutoff": proj.get("data_cutoff", ""),
            "data_source": proj.get("data_source", ""),
        },
        "geo": {
            "center": geo.get("center") or {"lng": 116.0, "lat": 35.0, "alt": 75000},
            "bounds": geo.get("bounds") or {},
        },
        "administrative": {
            "county_name": adm.get("county_name", ""),
            "townships": adm.get("townships", []),
        },
        "features": {
            "ai_chat": _feature_enabled("enable_ai_chat", bool(sf.get("key", "").strip() and not sf.get("key", "").startswith("${"))),
            "worklog": _feature_enabled("enable_worklog", _FEATURES.get("worklogs", False)),
            "models_3d": _feature_enabled("enable_3d_model", _FEATURES.get("models_3d", False)),
            "dem": _feature_enabled("enable_dem", _FEATURES.get("dem", False)),
        },
        "cesium_ion_token": cesium_token,
        "stats": {
            "relics_total": len(store.relics),
        },
    }
    js_payload = _json.dumps(payload, ensure_ascii=False)
    return (
        "<script>\n"
        f"window.__PLATFORM_CONFIG = {js_payload};\n"
        "try { if (window.Cesium && window.__PLATFORM_CONFIG.cesium_ion_token) "
        "{ Cesium.Ion.defaultAccessToken = window.__PLATFORM_CONFIG.cesium_ion_token; } } catch(e) {}\n"
        "</script>\n"
    )


def _render_template(name: str) -> str:
    """读 templates/<name>.html,做两件事:
    (1) 替换 {{ full_name }} / {{ county_name }} / {{ data_source }};
    (2) 在 </head> 之前注入 bootstrap script,前端以此拿到配置。
    """
    path = TEMPLATES_DIR / name
    if not path.exists():
        return f"<h1>模板缺失: {name}</h1>"
    html = path.read_text(encoding="utf-8")

    proj = (_CONFIG.get("project") or {})
    adm = (_CONFIG.get("administrative") or {})
    full_name = proj.get("full_name") or ""
    county_name = adm.get("county_name") or proj.get("name") or ""
    data_source = proj.get("data_source") or ""

    for k, v in {
        "{{ full_name }}": full_name,
        "{{ county_name }}": county_name,
        "{{ data_source }}": data_source,
    }.items():
        html = html.replace(k, v)

    bootstrap = _bootstrap_script()
    if "</head>" in html:
        html = html.replace("</head>", bootstrap + "</head>", 1)
    else:
        html = bootstrap + html
    return html


@app.get("/", response_class=HTMLResponse)
async def index():
    return _render_template("index.html")


@app.get("/model-viewer", response_class=HTMLResponse)
async def model_viewer():
    return _render_template("model_viewer.html")


@app.get("/pdf-viewer", response_class=HTMLResponse)
async def pdf_viewer():
    return _render_template("pdf_viewer.html")


@app.get("/admin")
async def admin_page():
    """旧版 vanilla admin.html 已被 Vue 后台 (/admin-ui/) 取代。
    这里保留 /admin 做 302，方便老书签平滑过渡。"""
    return RedirectResponse(url="/admin-ui/", status_code=302)


class _LoginBody(BaseModel):
    username: str
    password: str


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return _render_template("login.html")


@app.post("/api/login")
async def api_login(body: _LoginBody):
    users = (_CONFIG.get("server") or {}).get("users") or []
    for u in users:
        if u.get("username") == body.username and u.get("password") == body.password:
            resp = JSONResponse({"ok": True})
            resp.set_cookie(
                key="session", value="authenticated",
                httponly=True, samesite="lax", path="/",
            )
            return resp
    return JSONResponse({"detail": "用户名或密码错误"}, status_code=401)

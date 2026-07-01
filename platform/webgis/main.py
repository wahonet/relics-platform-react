"""FastAPI application entrypoint for the Relics Platform.

This module now acts as a small composition root:
- load runtime config and datasets in lifespan
- register middleware and API routers
- register terrain/tile route modules
- mount static assets and frontend build outputs
"""
from __future__ import annotations

import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

PLATFORM_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLATFORM_ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from starlette.middleware.base import BaseHTTPMiddleware  # noqa: E402

from _common import PROJECT_ROOT, detect_features, get_paths, load_config  # noqa: E402
import crs as _crs_lib  # noqa: E402
from data_loader import store  # noqa: E402
from routers import admin, boundaries as _boundaries, chat, crs as _crs, relics, stats, survey_routes, worklog  # noqa: E402
from terrain_provider import load_dem  # noqa: E402
from terrain_routes import register_terrain_routes  # noqa: E402
from tile_routes import TILE_CACHE_DIR, register_tile_routes  # noqa: E402
from web_security import (  # noqa: E402
    resolve_cookie_secure,
    resolve_cors_origins,
    resolve_session_secret,
    sign_session,
    verify_password,
    verify_session,
)

_CONFIG: dict = {}
_FEATURES: dict = {}
_PATHS = get_paths()

WEBGIS_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEBGIS_DIR / "templates"
STATIC_DIR = WEBGIS_DIR / "static"

_ADMIN_VUE_DIST = PROJECT_ROOT / "platform" / "admin-vue" / "dist"
_WEBGIS_REACT_DIST = PROJECT_ROOT / "platform" / "webgis-react" / "dist"


def _feature_enabled(cfg_key: str, auto_value: bool) -> bool:
    value = (_CONFIG.get("features") or {}).get(cfg_key, "auto")
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in ("true", "yes", "on"):
        return True
    if isinstance(value, str) and value.lower() in ("false", "no", "off"):
        return False
    return bool(auto_value)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _CONFIG, _FEATURES
    _CONFIG = load_config()
    _FEATURES = detect_features().as_dict

    try:
        hp = ((_CONFIG.get("geo") or {}).get("cgcs2000") or {}).get("helmert_params")
        if hp:
            _crs_lib.set_helmert_params(hp)
            print(f"[startup] CGCS2000 Helmert params enabled: {hp}")
        else:
            print("[startup] CGCS2000 -> WGS84 uses identity approximation")
    except Exception as e:
        print(f"[startup] Helmert param setup failed, fallback to identity: {e}")

    geo = _CONFIG.get("geo") or {}
    bounds = geo.get("bounds") or {}
    bbox = (
        bounds.get("west", -180.0),
        bounds.get("south", -90.0),
        bounds.get("east", 180.0),
        bounds.get("north", 90.0),
    )

    village_gj = _PATHS.output_boundaries / "villages.geojson"
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

    print(f"[startup] relic records: {len(store.relics)}")
    print(f"[startup] photo index: {len(store.photo_index)}")
    print(f"[startup] drawing index: {len(store.drawing_index)}")
    print(f"[startup] archive PDFs: {len(store.pdf_map)}")
    print(f"[startup] survey routes: {len(store.survey_routes)}")
    if store.village_coverage:
        vc = store.village_coverage
        print(f"[startup] village coverage: {vc['reached']}/{vc['total']}")

    cached = sum(1 for _ in TILE_CACHE_DIR.rglob("*.tile"))
    print(f"[startup] tile cache: {cached} -> {TILE_CACHE_DIR}")

    dem_dir = _PATHS.input_dem
    enable_dem = _feature_enabled("enable_dem", _FEATURES.get("dem", False))
    if enable_dem and dem_dir.exists():
        load_dem(str(dem_dir))
    else:
        print(f"[DEM] skipped (enable_dem={enable_dem}, exists={dem_dir.exists()})")

    try:
        chat.init_chat()
    except Exception as e:
        print(f"[AI] init failed: {e}")

    yield


app = FastAPI(title="Relics Platform", version="1.1.5", lifespan=lifespan)

_PUBLIC_PREFIXES = (
    "/login",
    "/api/login",
    "/static/",
    "/tiles/",
    "/api/terrain/",
    "/api/platform/config",
    "/app/",
    "/legacy",
)

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _demo_mode_allows_client(client_host: str, allow_insecure: bool) -> bool:
    """鉴权关闭(demo 模式)时,只允许本机回环访问,除非显式 allow_insecure_demo。"""
    return client_host in _LOOPBACK_HOSTS or allow_insecure


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        server = _CONFIG.get("server") or {}
        if not server.get("enable_auth", False):
            # demo 模式:仅允许本机回环,防止"误绑 0.0.0.0 + 关 auth"暴露全部写接口。
            client = (request.client.host if request.client else "") or ""
            if not _demo_mode_allows_client(client, bool(server.get("allow_insecure_demo", False))):
                return JSONResponse({"detail": "未启用鉴权,仅允许本机访问"}, status_code=403)
            return await call_next(request)
        path = request.url.path
        if any(path == p or path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await call_next(request)
        if not verify_session(request.cookies.get("session"), _SECRET, max_age=_SESSION_MAX_AGE):
            # API/XHR 请求返回 JSON 401(前端拦截器可统一识别并跳登录);页面请求才 302。
            is_api = path.startswith("/api/")
            is_xhr = request.headers.get("x-requested-with", "").lower() == "xmlhttprequest"
            if is_api or is_xhr:
                return JSONResponse({"detail": "未登录或会话已过期"}, status_code=401)
            from urllib.parse import quote

            target = path
            if request.url.query:
                target = f"{path}?{request.url.query}"
            login_url = f"/login?next={quote(target, safe='/?&=#')}"
            return RedirectResponse(url=login_url, status_code=302)
        return await call_next(request)


app.add_middleware(AuthMiddleware)
# 中间件在模块导入期注册(此时 lifespan 尚未跑、_CONFIG 还是空),所以这里
# 单独读一次 config 供 CORS 白名单与会话密钥使用;缺 config.yaml(如单测)
# 时回退到安全默认值。
try:
    _BOOT_CFG = load_config()
except Exception:
    _BOOT_CFG = {}

# CORS:不能用 allow_origins=["*"] 搭配 allow_credentials=True —— 违反规范,
# 浏览器会拒绝携带 Cookie 的跨域请求。改为按 config 解析出具体白名单。
_CORS_ORIGINS = resolve_cors_origins(_BOOT_CFG)

# 会话签名密钥 + 可选有效期(供 AuthMiddleware 校验、/api/login 签发)。
_SECRET, _SECRET_SOURCE = resolve_session_secret(_BOOT_CFG)
_sm = (_BOOT_CFG.get("server") or {}).get("session_max_age_seconds")
try:
    _SESSION_MAX_AGE = int(_sm) if _sm not in (None, "", 0, "0") else None
except (TypeError, ValueError):
    _SESSION_MAX_AGE = None
if _SECRET_SOURCE == "ephemeral":
    print("[auth] 未配置 server.secret_key / 环境变量 RELICS_SECRET_KEY，"
          "本次使用进程内随机会话密钥(重启后需重新登录)。生产请配置固定密钥。")
# 会话 Cookie 是否带 Secure(仅 HTTPS)。默认 False,HTTPS 生产置 true。
_COOKIE_SECURE = resolve_cookie_secure(_BOOT_CFG)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(relics.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(survey_routes.router, prefix="/api")
app.include_router(worklog.router, prefix="/api")
app.include_router(_boundaries.router, prefix="/api")
app.include_router(_crs.router, prefix="/api")

register_terrain_routes(app)
register_tile_routes(app, get_config=lambda: _CONFIG)


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
        "admin_ui": {
            "available": _ADMIN_VUE_DIST.exists() and (_ADMIN_VUE_DIST / "index.html").exists(),
            "url": "/admin-ui/",
        },
        "auth": {
            "enabled": bool((cfg.get("server") or {}).get("enable_auth", False)),
        },
    })


@app.get("/api/config")
async def legacy_config() -> JSONResponse:
    return await platform_config()


def _mount_if_exists(path_prefix: str, directory: Path, name: str, *, create: bool = False) -> None:
    if create:
        directory.mkdir(parents=True, exist_ok=True)
    if directory.exists():
        app.mount(path_prefix, StaticFiles(directory=str(directory)), name=name)
    else:
        print(f"[warning] skip mount {path_prefix}: {directory} does not exist")


_mount_if_exists("/photos", _PATHS.output_photos, "photos", create=True)
_mount_if_exists("/drawings", _PATHS.output_drawings, "drawings", create=True)
_mount_if_exists("/boundaries", _PATHS.output_boundaries, "boundaries", create=True)
_mount_if_exists("/worklog-pdfs", _PATHS.output_worklogs, "worklog_pdfs", create=True)
_mount_if_exists("/3d", _PATHS.input_models_3d, "3d_models", create=True)
_mount_if_exists("/pdfs", PROJECT_ROOT / "data" / "input" / "01_archives_pdf", "pdfs")
_mount_if_exists("/survey-photos", _PATHS.input_worklogs / "survey_photos", "survey_photos")
_mount_if_exists("/static", STATIC_DIR, "static")

if _ADMIN_VUE_DIST.exists():
    app.mount("/admin-ui", StaticFiles(directory=str(_ADMIN_VUE_DIST), html=True), name="admin_ui")
    print(f"[startup] Vue admin mounted: /admin-ui/ -> {_ADMIN_VUE_DIST}")
else:
    print("[startup] Vue admin dist not found; skip /admin-ui/ mount")

if _WEBGIS_REACT_DIST.exists():
    app.mount("/app", StaticFiles(directory=str(_WEBGIS_REACT_DIST), html=True), name="webgis_react")
    print(f"[startup] React WebGIS mounted: /app/ -> {_WEBGIS_REACT_DIST}")
else:
    print("[startup] React WebGIS dist not found; skip /app/ mount")


def _bootstrap_script() -> str:
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
        "admin_ui": {
            "available": _ADMIN_VUE_DIST.exists() and (_ADMIN_VUE_DIST / "index.html").exists(),
            "url": "/admin-ui/",
        },
        "auth": {
            "enabled": bool((_CONFIG.get("server") or {}).get("enable_auth", False)),
        },
    }
    js_payload = json.dumps(payload, ensure_ascii=False)
    return (
        "<script>\n"
        f"window.__PLATFORM_CONFIG = {js_payload};\n"
        "try { if (window.Cesium && window.__PLATFORM_CONFIG.cesium_ion_token) "
        "{ Cesium.Ion.defaultAccessToken = window.__PLATFORM_CONFIG.cesium_ion_token; } } catch(e) {}\n"
        "</script>\n"
    )


def _render_template(name: str) -> str:
    path = TEMPLATES_DIR / name
    if not path.exists():
        return f"<h1>Template missing: {name}</h1>"
    html = path.read_text(encoding="utf-8")

    proj = (_CONFIG.get("project") or {})
    adm = (_CONFIG.get("administrative") or {})
    full_name = proj.get("full_name") or ""
    county_name = adm.get("county_name") or proj.get("name") or ""
    data_source = proj.get("data_source") or ""

    for key, value in {
        "{{ full_name }}": full_name,
        "{{ county_name }}": county_name,
        "{{ data_source }}": data_source,
    }.items():
        html = html.replace(key, value)

    bootstrap = _bootstrap_script()
    if "</head>" in html:
        return html.replace("</head>", bootstrap + "</head>", 1)
    return bootstrap + html


def _react_build_exists() -> bool:
    return _WEBGIS_REACT_DIST.exists() and (_WEBGIS_REACT_DIST / "index.html").exists()


def _dev_app_url() -> str:
    """开发模式(start-all 注入 RELICS_DEV_APP_URL)且无 React 构建产物时,
    返回前端 dev server 根地址;否则返回空串。用于把后端的旧版模板页统一跳到 dev server。"""
    if _react_build_exists():
        return ""
    return os.environ.get("RELICS_DEV_APP_URL", "").strip()


@app.get("/", response_class=HTMLResponse)
async def index():
    if _react_build_exists():
        return RedirectResponse(url="/app/", status_code=302)
    dev_url = _dev_app_url()
    if dev_url:
        return RedirectResponse(url=dev_url, status_code=302)
    return HTMLResponse(_render_template("index.html"))


@app.get("/legacy", response_class=HTMLResponse)
async def legacy_index():
    dev_url = _dev_app_url()
    if dev_url:
        return RedirectResponse(url=dev_url, status_code=302)
    return _render_template("index.html")


@app.get("/model-viewer", response_class=HTMLResponse)
async def model_viewer(request: Request):
    if _react_build_exists():
        qs = request.url.query
        target = "/app/#/model-viewer" + (("?" + qs) if qs else "")
        return RedirectResponse(url=target, status_code=302)
    dev_url = _dev_app_url()
    if dev_url:
        return RedirectResponse(url=dev_url + "#/model-viewer", status_code=302)
    return HTMLResponse(_render_template("model_viewer.html"))


@app.get("/pdf-viewer", response_class=HTMLResponse)
async def pdf_viewer(request: Request):
    if _react_build_exists():
        qs = request.url.query
        target = "/app/#/pdf-viewer" + (("?" + qs) if qs else "")
        return RedirectResponse(url=target, status_code=302)
    dev_url = _dev_app_url()
    if dev_url:
        return RedirectResponse(url=dev_url + "#/pdf-viewer", status_code=302)
    return HTMLResponse(_render_template("pdf_viewer.html"))


@app.get("/admin")
async def admin_page():
    return RedirectResponse(url="/admin-ui/", status_code=302)


class _LoginBody(BaseModel):
    username: str
    password: str


def _auth_enabled() -> bool:
    return bool((_CONFIG.get("server") or {}).get("enable_auth", False))


def _login_response(username: str = "admin") -> JSONResponse:
    uname = username or "admin"
    resp = JSONResponse({"ok": True, "username": uname})
    resp.set_cookie(
        key="session",
        value=sign_session(uname, _SECRET),   # 签名令牌,替代可伪造的固定值
        httponly=True,
        samesite="lax",
        path="/",
        secure=_COOKIE_SECURE,                # HTTPS 生产置 true(config: server.cookie_secure)
        max_age=_SESSION_MAX_AGE,             # None → 会话级 Cookie(关浏览器即失效)
    )
    return resp


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if _react_build_exists():
        nxt = request.query_params.get("next") or ""
        if nxt:
            from urllib.parse import quote

            target = f"/app/#/login?next={quote(nxt, safe='/?&=#')}"
        else:
            target = "/app/#/login"
        return RedirectResponse(url=target, status_code=302)
    dev_url = _dev_app_url()
    if dev_url:
        return RedirectResponse(url=dev_url + "#/login", status_code=302)
    return HTMLResponse(_render_template("login.html"))


@app.post("/api/login")
async def api_login(body: _LoginBody):
    if not _auth_enabled():
        return _login_response(body.username or "admin")

    users = (_CONFIG.get("server") or {}).get("users") or []
    for user in users:
        if user.get("username") != body.username:
            continue
        # 优先 password_hash(pbkdf2),兼容旧 config 的明文 password。
        stored = user.get("password_hash") or user.get("password")
        if stored is not None and verify_password(stored, body.password):
            return _login_response(body.username)
    return JSONResponse({"detail": "用户名或密码错误"}, status_code=401)

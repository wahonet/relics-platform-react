from __future__ import annotations

from fastapi import FastAPI

from routers import admin


def test_admin_router_includes_relic_subrouter_paths():
    # 挂到 app 上用 OpenAPI 检查已解析的路由。FastAPI 0.138 起 include_router
    # 不再把子路由展平进 router.routes(改存为 _IncludedRouter),直接遍历
    # admin.router.routes 看不到子路由;openapi() 会完整解析,跨版本都稳。
    app = FastAPI()
    app.include_router(admin.router)
    paths = set(app.openapi()["paths"].keys())

    assert "/admin/relics" in paths
    assert "/admin/relics-export" in paths
    assert "/admin/stats-overview" in paths
    assert "/admin/audit" in paths

"""relics 公开查询路由测试(facets / list,直接调用协程)。

测试进程里全局 store 未 load(_use_db=False、relics 为空),走 JSON 回退,
应返回结构完整的空响应,验证路由装配与契约形状。

注:直接调用路由协程时,FastAPI 的 Query(...) 默认值是 Query 对象而非真实值,
故所有参数需显式传入(模拟 FastAPI 解析后的调用)。
"""
from __future__ import annotations

import asyncio

from routers import relics as relics_route


def _facets(**kw):
    args = dict(q=None, category=None, rank=None, township=None, search_type=None,
                min_lng=None, min_lat=None, max_lng=None, max_lat=None)
    args.update(kw)
    return asyncio.run(relics_route.relics_facets(**args))


def _list(**kw):
    args = dict(q=None, category=None, rank=None, township=None, search_type=None,
                min_lng=None, min_lat=None, max_lng=None, max_lat=None, page=1, size=50)
    args.update(kw)
    return asyncio.run(relics_route.relics_list(**args))


def test_facets_route_shape_on_empty_store():
    res = _facets()
    assert res["total"] == 0
    assert res["has_3d"] == 0
    f = res["facets"]
    for k in ("category", "rank", "search_type", "township", "era_stats",
              "condition", "ownership", "industry", "risk_factors"):
        assert k in f
    assert [it["code"] for it in f["category"]] == \
        ["0100", "0200", "0300", "0400", "0500", "0600"]
    assert all(it["count"] == 0 for it in f["category"])


def test_list_route_shape_on_empty_store():
    assert _list() == {"data": [], "total": 0, "page": 1, "size": 50}


def test_list_route_csv_params_parse():
    res = _list(category="0100,0300", rank="1,2", size=10)
    assert res["total"] == 0 and res["size"] == 10

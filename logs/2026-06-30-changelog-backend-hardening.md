# CHANGELOG — 后端加固轮次(2026-06-29 ~ 06-30)

一轮针对后端的正确性 / 安全 / 健壮性加固。**每项改动均带回归测试**;后端测试套件
从 **34 → ~109** 全绿(以 `bash _run_tests.sh` 为准)。下面按主题汇总,可直接用于
release notes 或 PR 描述。

> 运行/验证:仓库根 `bash _run_tests.sh`(WSL + Python 3.14;脚本会自动装依赖并跑
> `pytest -v`)。前端改动需另跑 `npm run type-check && npm run build`(本轮基本未动前端)。

---

## 🐞 修复(正确性)

- **后台编辑后全文搜索失效/张冠李戴**
  `search_fulltext` 不再用 `relics_fts.rowid = relics_rtree_map.id_int` 连接(二者仅
  建库时对齐,运行时 FTS upsert 会让 rowid 漂移),改按唯一键 `relics.code` 连接。
  文件:`platform/webgis/data_loader.py`。

- **文物详情接口返回陈旧数据**
  移除 `get_relic_full` 上永不失效的 `lru_cache`(编辑后仍返回旧值,且会把"查过的
  不存在 code"缓存成 None)。文件:`platform/webgis/data_loader.py`。

## 🔒 安全

- **CORS 通配 + 凭证非法组合** → 按 config 解析具体白名单(绝不返回 `*`)。
  新增 `platform/webgis/web_security.py::resolve_cors_origins`。

- **可伪造的静态会话 Cookie** → HMAC-SHA256 签名令牌:常数时间校验、可选过期、
  密钥三级回退(env `RELICS_SECRET_KEY` > `server.secret_key` > 进程内随机)。
  `web_security.py` + `main.py`。

- **会话 Cookie `Secure` 标志** → `server.cookie_secure`(默认 false 以兼容 http
  内网/demo;HTTPS 生产置 true)。

## 🧱 健壮性 / 运维

- **任务历史无界增长** → `_prune_tasks` 上限 200(运行中任务永不裁剪);
  `asyncio.get_event_loop()` → `get_running_loop()`。`routers/admin_task_service.py`。

- **管线步骤选择字符串比较陷阱** → `run_pipeline._select_steps` 改数值比较
  (修 step id ≥ "10" 及 "1"≠"01" 问题)。`platform/scripts/run_pipeline.py`。

- **`has_photo` 单向回填** → `step07._refresh_has_photo` 双向同步(无照片回置 0)。
  `platform/scripts/step07_build_db.py`。

- **瓦片下载无磁盘守护** → 预检 + 任务中周期检查剩余空间,低于
  `tiles.min_free_disk_mb`(默认 500MB)拒绝/中止。`platform/webgis/tile_routes.py`。

## ⚡ 性能 / 质量

- **写路径 O(N) 全量重载** → create/update/delete 增量维护内存镜像(单条 O(N)→一次
  线性查找;批量 O(N·M)→O(M))。`data_loader.py`。

- **AI system prompt 全量预烘** → 按文物规模分级:`<= full_context_max_relics`
  (默认 1500)沿用全量清单,超过则只给统计摘要 + 检索 Top-K,防 Token 膨胀。
  `routers/chat.py`。

- **编码字典三源手工同步** → 新增漂移守护测试:解析 `static/js/dict.js` 与 React
  `utils/dict.ts`,断言 code→label 与别名同 `codes.py` 一致(漂移即 CI 失败);
  Vue 后台已从 `/api/admin/codes` 拉取(天然单源)。`tests/test_dict_sync.py`。

## ✨ 新增(为前端去全量铺路)

- **分面聚合端点** `GET /api/relics/facets`:按当前筛选(category/rank/township/
  search_type/q/bbox)返回各维计数 + 总数,供 Dashboard/FilterPanel 联动而无需全量
  入内存。覆盖**主列**维度(category/rank/search_type/township/era_stats);
  condition/ownership/industry/risk_factors 落在 `extra_json`,暂未分面(需 json_extract)。
  `data_admin_queries.facet_counts` + `data_loader` 委托 + `routers/relics.py` 路由。
  **前端尚未接入**(P1-2 暂缓,需 Node 环境验证)。

## 🧪 测试

- 新增端点级测试:`test_route_crs.py`(CRS 转换路由)、`test_routes_basic.py`
  (stats/survey/worklog/boundaries 的空响应与校验分支)。
- 其余每项改动均配回归测试(见各 `tests/test_*.py`)。

## 🔧 新增配置项(均有安全默认)

| 配置 | 默认 | 说明 |
|---|---|---|
| `server.secret_key` / 环境变量 `RELICS_SECRET_KEY` | 空→随机 | 会话签名密钥 |
| `server.session_max_age_seconds` | 0(会话级) | 会话有效期 |
| `server.cookie_secure` | false | Cookie Secure 标志(HTTPS 置 true) |
| `api.siliconflow.full_context_max_relics` | 1500 | AI 全量清单注入阈值 |
| `tiles.min_free_disk_mb` | 500 | 瓦片下载磁盘守护阈值 |

## ⏸ 暂缓

- **P1-2 前端去掉全量 `/api/relics`**:经调研为架构级改动(该 React 应用是"全量入内存
  + 客户端交叉筛选"的分析型 UI),`/api/stats` 无法替代联动;真去全量需前端重写,且
  本环境无 Node 无法验证。后端已先行提供 `/api/relics/facets` 作为接入点。
- **`codes.py` → 前端字典物理生成**:本轮以漂移守护测试"强制单源",未做构建期生成。

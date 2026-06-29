# 文物平台 Bug 修复进度与后续路线图

- **日期**:2026-06-29
- **分支**:main
- **状态一句话**:P0 #1~#5 + P1-1 + P1-3 + P1-4 + P2(a/b/c)均已实现并验证,`bash _run_tests.sh` = **81 passed**。**P1-2(前端去全量)经调研判定为架构级改动、当前体量性价比低且无法在此验证前端,已暂缓**(理由见 §4)。所有改动**尚未 git commit**。

---

## 0. 换上下文后必读:测试与环境约定

- 仓库 = 县区级文物 WebGIS:FastAPI 后端 + React 主图 + Vue 后台 + 7 步数据管线。
- **测试入口**:仓库根目录执行 `bash _run_tests.sh`。该脚本会:定位/必要时 `winget` 安装 Python → `pip` 安装 `pytest pyyaml fastapi pydantic numpy python-multipart` → 跑全套 `pytest -v`。
- **实际执行环境**:用户在 **WSL(Linux)** 跑,**Python 3.14.6**(`python3`)。
- **协作约定**:本会话沙箱的命令分类器不稳定,Claude 无法自跑命令。因此 **Claude 只负责改代码 + 写测试,由用户执行 `bash _run_tests.sh` 并回贴结果**。
- `_run_tests.sh` 是临时运行器(放在仓库根),可保留也可在收尾时删。
- pytest 配置见 `pytest.ini`:`pythonpath = platform/scripts, platform/webgis`,`testpaths = tests`。
- 轻量测试只需 stdlib/pyyaml;涉及 `main.py` 的测试需 fastapi/pydantic/numpy(运行器已装)。

---

## 1. 已完成的修复(P0,全部 GREEN)

### Bug #1 — 后台编辑后全文搜索失效/张冠李戴 ✅
- **根因**:`search_fulltext` 用 `relics_fts.rowid = relics_rtree_map.id_int` 连接;这两条 rowid 序列只在 `step07` 建库时被对齐(1..N),运行时 `_fts_upsert` 的 DELETE+INSERT 会给 fts 行重分配 rowid,导致连接错位(搜不到或连到别的文物)。
- **修复**:改按唯一键 `relics.code` 连接(`relics_fts` 本就有 `code` 列)。
- **文件**:`platform/webgis/data_loader.py`(`search_fulltext`)。
- **测试**:`tests/test_db_store_writes.py::test_fts_search_survives_admin_rename`。

### Bug #2 — 详情接口返回陈旧数据 ✅
- **根因**:`get_relic_full` 加了 `@lru_cache` 且写操作后从不失效(还会把“查过的不存在 code”缓存成 None)。
- **修复**:移除 `@lru_cache`(单条按唯一索引 `code` 查询本就极快,无需缓存)。
- **文件**:`platform/webgis/data_loader.py`(删 `from functools import lru_cache` + 删装饰器)。
- **测试**:`tests/test_db_store_writes.py::test_get_relic_full_reflects_update`、`::test_get_relic_full_not_caching_missing_then_created`。

### Bug #3 — CORS 通配 + 凭证(非法组合)✅
- **根因**:`allow_origins=["*"]` 同时 `allow_credentials=True`,违反规范,浏览器拒绝带 Cookie 的跨域。
- **修复**:新增 `platform/webgis/web_security.py::resolve_cors_origins`(按 config 解析具体白名单,绝不返回 `*`);`main.py` 接入。支持 `server.cors_origins`(list 或逗号串)覆盖,默认含 dev 端口 5173/5174 + 当前 host:port。
- **文件**:`platform/webgis/web_security.py`(新)、`platform/webgis/main.py`。
- **测试**:`tests/test_web_security.py`(6 条 CORS)。

### Bug #4 — 静态可伪造 Cookie 鉴权 ✅
- **根因**:cookie 值写死 `"authenticated"`,任何人手填即可冒充登录。
- **修复**:`web_security.py` 增 `resolve_session_secret / sign_session / verify_session`(HMAC-SHA256,`hmac.compare_digest` 常数时间比较,可选 `max_age` 过期);`main.py` 的 `AuthMiddleware` 改用 `verify_session`,`/api/login` 签发签名令牌。密钥优先级:环境变量 `RELICS_SECRET_KEY` > `config.server.secret_key` > 进程内随机(随机时启动打印告警)。
- **文件**:`platform/webgis/web_security.py`、`platform/webgis/main.py`、`config.example.yaml`(+`server.secret_key`、`server.session_max_age_seconds`)、`platform/admin-vue/src/api/auth.ts`(仅注释)。
- **测试**:`tests/test_login_auth.py`(重写,3 条)、`tests/test_web_security.py`(+6 条令牌)。
- **行为**:`enable_auth: false`(demo 默认)仍整体放行;`true` 且未配密钥 → 每进程随机密钥(重启即登出所有人,启动有告警)。旧的 `authenticated` 老 cookie 会被判无效 → 重新登录。

### Bug #5 — 任务历史无界 + `get_event_loop()` 废弃 ✅
- **修复**:`_prune_tasks()` 把已结束任务(done/error/skipped…)在内存里上限 200(running/starting 永远保留),在每次启动新任务时调用;`asyncio.get_event_loop()` → `asyncio.get_running_loop()`。
- **文件**:`platform/webgis/routers/admin_task_service.py`。
- **测试**:`tests/test_admin_task_gc.py`(3 条:裁剪上限/保留运行中、未超不动、登记 + 运行中重复 409)。

---

## 2. 当前进度节点(CHECKPOINT)

- ✅ **P0 #1–#5 + P1-1 全部完成**,`bash _run_tests.sh` → **49 passed**(0 失败)。
- 🟡 **P1-4(crs.py 回归测试)代码已写**(`tests/test_crs.py`),**待用户跑一次确认**(预期 +约 16 条,总数升到约 65)。
- **本会话新增文件**:
  - `platform/webgis/web_security.py`
  - `tests/test_db_store_writes.py`(含 #1/#2 与 P1-1)
  - `tests/test_web_security.py`
  - `tests/test_admin_task_gc.py`
  - `tests/test_crs.py`(P1-4)
  - `_run_tests.sh`(临时运行器)
  - `logs/2026-06-29-bugfix-progress-and-roadmap.md`(本文档)
- **本会话改动文件**:
  - `platform/webgis/data_loader.py`(#1、#2、P1-1 增量镜像)
  - `platform/webgis/main.py`(#3、#4)
  - `platform/webgis/routers/admin_task_service.py`(#5)
  - `tests/test_login_auth.py`(随 #4 重写)
  - `config.example.yaml`(#4 新增配置项)
  - `platform/admin-vue/src/api/auth.ts`(#4 注释)
- **Git**:以上均为工作区改动,**尚未 commit**。`logs/` 建议入库;`_run_tests.sh` 可自行决定。

---

## 3. 下一步从这里开始(P1,建议顺序 + 思路)

> **已完成**:P1-1(写路径增量)✅、P1-4(crs.py 测试)🟡待跑确认。
> **下一未完成项 = P1-2(前端去全量加载)。** 注意:P1-2/P1-3 在当前协作环境里
> 无法由 Claude 自动验证(无 Node;AI 需真实 LLM),改动前最好与用户确认。

### ✅ P1-1 写路径增量(已完成,49 passed)
- `data_loader.py` 新增 `_legacy_from_db_row` / `_mirror_sync_row` / `_mirror_remove`;
  create/update 调 `_mirror_sync_row(code, row)`,delete 调 `_mirror_remove(code)`;
  仅启动 `load()` 仍做一次全量 `_populate_legacy_from_db`。
- 语义与旧全量重读一致:镜像只收录 status==1;photo_map/drawing_map 不在写路径变动。
- 测试见 `tests/test_db_store_writes.py` 的 `*_without_full_reload` / `test_status_change_syncs_mirror` / `test_bulk_update_avoids_full_reload`。

### 🟡 P1-4 crs.py 回归测试(已写,待跑)
- `tests/test_crs.py`:GK 正反算往返、web_mercator 已知值+往返、gcj02/bd09 往返、
  cgcs2000 默认 identity、Helmert 注参非 identity、transform_point/geojson。纯 stdlib。
- **下一次 `bash _run_tests.sh` 先确认它全绿**,再继续 P1-2。

### 🟡 P1-3 AI 上下文按规模分级注入(已写,待跑)
- **实现(保守、向后兼容)**:把 `chat.py` 的 `_build_full_context` 拆成 `_build_stats_summary`(统计块)+ `_build_full_listing`(全量清单);新增纯函数 `assemble_system_content(...)`:统计摘要 / 命中 Top-K 详情 / 工作日志**始终注入**,**全量清单仅当 `文物数 <= full_context_max_relics` 时注入**(默认 1500,见 config)。小库(县级常见)行为不变;大库自动改走“统计摘要 + 检索 Top-K”,防 Token 膨胀。
- **未改**评分函数 `_find_relevant_intros / _find_relevant_worklog`(沿用)。
- **测试**:`tests/test_chat_context.py`(5 条,测纯函数 `assemble_system_content`)。
- **下一次 `bash _run_tests.sh` 确认全绿**。

### ⏹ P1-2 前端去掉全量 `/api/relics`(已决策:当前体量不做 — 2026-06-30)
- **修正前一版的错误前提**:旧记录称 `/api/relics` 全量"削弱了 by-bbox 视口优化"——
  二次深读前端后证伪:地图打点本就走 `by-bbox`,`all` **不参与**地图渲染。
- **真实现状**:`all` 唯一不可约用途 = Dashboard/FilterPanel 客户端交叉筛选(含 ERA_MAP
  归并/行业首段/影响因素多值等展示变换的维度联动);详情/照片/图纸/多边形已懒加载。
- **决策(C+)**:当前单县体量(几百~一两千条)**不重写前端**;后端 `facets`/`list` 端点
  作为未来上规模时的地基保留;撤销 `/api/relics` 的 deprecated 误标。完整论证 + 未来触发
  完整 B 的条件见 `logs/2026-06-30-changelog-backend-hardening.md` §⏸。

### P1-3 AI 改检索式 RAG
- **现状**:`platform/webgis/routers/chat.py` 把整库 + 工作日志全量塞进 system prompt(`_build_full_context` / `_build_worklog_context`),数据量大必然撑爆 token / 成本。
- **思路**:system prompt 只放统计摘要;正文按 query 用 `store.search_fulltext` + 现有 `_find_relevant_intros / _find_relevant_worklog` 打分取 Top-K 作为主路径,去掉全量 `_full_context` 注入。
- **测试**:对“打分 + 上下文拼接”等纯函数做单测(不调外部 LLM)。

### P1-4 `crs.py` 数值回归测试(只补测试,不改码)
- **现状**:`platform/scripts/crs.py`(高斯-克吕格正反算、Helmert 七参、web_mercator、bd09)零测试,是数学最密集、最易静默出错的模块。
- **思路**:对已知点做往返断言误差 < 1e-6(`wgs84↔gk↔wgs84`、`wgs84↔web_mercator`、`gcj02↔wgs84`);`set_helmert_params` 注参后断言结果 ≠ identity。纯 stdlib,很轻。

---

## 4. 完整改进清单(带状态)

**P0 — 正确性 / 安全**
- [x] #1 FTS 搜索错位
- [x] #2 详情陈旧缓存
- [x] #3 CORS 通配 + 凭证
- [x] #4 鉴权令牌(签名)
- [x] #5 任务表 GC + 事件循环

**P1 — 性能 / 质量**
- [x] P1-1 写路径增量(GREEN)
- [◑→决策] P1-2 前端去全量加载 —— **后端地基就位**:`GET /api/relics/facets`(全 9 维
  计数 + 总数 + has_3d,`data_admin_queries.facet_counts`)+ `GET /api/relics/list`(分页
  精简行,`list_relics_filtered`),均带测试。**前端经决策当前体量不接入**(撤销
  `/api/relics` deprecated 误标);完整论证见 changelog(06-30)§⏸。
- [x] P1-3 AI 上下文按规模分级注入(GREEN)
- [x] P1-4 crs.py 回归测试(GREEN)

**测试网补强**
- [x] 路由端点测试:`test_route_crs.py`、`test_routes_basic.py`(stats/survey/worklog/boundaries)

**P2 — 健壮性 / 运维**
- [x] P2-a `run_pipeline._select_steps` 数值比较(修 step id ≥ "10" 隐患)+ 测试
- [x] P2-b `step07._refresh_has_photo` 双向同步(无照片回置 0)+ 测试(`tests/test_step07_build_db.py`)
- [x] P2-c 瓦片下载磁盘配额守护(预检 + 任务中周期检查)+ 测试
- [x] `codes.py` 与前端字典单源守护:新增 `tests/test_dict_sync.py`,解析 `static/js/dict.js` 与 React `utils/dict.ts`,断言 code→label 与别名同 `codes.py` 一致(漂移即 CI 失败);Vue 后台已天然从 `/api/admin/codes` 拉取。**注**:这是"强制 codes.py 为唯一真源"的守护,非物理生成前端文件(那需前端构建,留给有 Node 时)。
- [x] 会话 Cookie `secure` 标志:`server.cookie_secure`(默认 false,HTTPS 生产置 true)+ 测试

---

## 5. 关键文件速览(便于换上下文快速定位)

- 后端组合根:`platform/webgis/main.py`(lifespan、鉴权中间件、CORS、路由挂载、静态/SPA 挂载)
- **数据仓库(核心)**:`platform/webgis/data_loader.py`(`DataStore`:SQLite/JSON 双模式、R-Tree、FTS5、审计、乐观锁、软删)
- 安全:`platform/webgis/web_security.py`(CORS 白名单 + 会话令牌)
- 后台任务:`platform/webgis/routers/admin_task_service.py`
- 文物 CRUD 路由:`platform/webgis/routers/admin_relic_routes.py` + `services/admin_relic_service.py`
- 后台查询/统计:`platform/webgis/data_admin_queries.py`、`data_admin_stats.py`
- 瓦片代理/缓存/下载:`platform/webgis/tile_routes.py`
- AI 问答:`platform/webgis/routers/chat.py`
- 建库 schema(权威):`platform/scripts/step07_build_db.py`
- 坐标/编码:`platform/scripts/crs.py`、`platform/scripts/codes.py`、`platform/scripts/_common.py`
- 管线编排:`platform/scripts/run_pipeline.py`
- 前端主图(React+Cesium):`platform/webgis-react/src/`(`stores/relicsStore.ts`、`map/ViewportManager.ts`、`map/MapView.tsx`)
- 前端后台(Vue+Element Plus):`platform/admin-vue/src/`
- 测试:`tests/`,统一用 `bash _run_tests.sh` 跑。

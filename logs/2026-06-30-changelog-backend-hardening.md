# CHANGELOG — 后端加固轮次(2026-06-29 ~ 06-30)

一轮针对后端的正确性 / 安全 / 健壮性加固。**每项改动均带回归测试**;后端测试套件
从 **34 → 121** 全绿(以 `bash _run_tests.sh` 为准)。下面按主题汇总,可直接用于
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

## ✨ 新增(分面 / 列表端点 —— 未来去全量的地基)

- **分面聚合端点** `GET /api/relics/facets`:按当前筛选(category/rank/township/
  search_type/q/bbox)返回**全 9 维计数 + 总数 + has_3d**。除主列维度
  (category/rank/search_type/township/era_stats)外,**新增** condition/ownership/
  industry/risk_factors —— 它们落在 `extra_json`,对**过滤后子集**做一次内存归并得到
  (risk_factors 多值逐项计数,industry 取首段,与前端 dict 变换一致)。**注**:这些
  维度仅用于"计数/展示",**不进过滤 WHERE**(WHERE 只认 category/rank/township/
  search_type/bbox 这些干净索引列),故**不与数据管线的存储格式耦合**。
- **分页列表端点** `GET /api/relics/list`:同一筛选下返回精简行
  `{code,name,category,era,township,has_3d}`,分页,可替代全量 `/api/relics` 做结果列表。
- 实现:`data_admin_queries.facet_counts / list_relics_filtered` + `data_loader` 委托
  + `routers/relics.py` 路由;DB 与 JSON 回退双路径,均带测试
  (`test_db_store_writes` / `test_data_admin_delegates` / `test_route_relics`)。

  **定位**:这两个端点是**未来**(万条+/跨县跨省)前端彻底去全量的接入点;当前体量
  下前端不接入(见 §⏸ 的调研结论)。

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

## ⏸ 暂缓 / 决策记录

- **P1-2 前端去掉全量 `/api/relics`**:**经二次深读前端,判定当前体量(单县,几百~
  一两千条)不做**。理由链:
  - 地图打点**早已**走 `/api/relics/by-bbox`(视口分页),**不**从全量内存集渲染;
    详情/照片/图纸/多边形**已**懒加载。即全量 `all` **唯一**不可约的用途 =
    Dashboard + FilterPanel 的**客户端交叉筛选**(按现状/年代/行业/影响因素联动,带
    ERA_MAP 归并、行业取首段、影响因素多值等展示变换)。
  - `get_relics_summary()` 本就精简(约 24 字段、不含简介/边界点),全量负载不大。
  - 若把计数改走 `facets` 却仍保留 `all` 给上述维度,会出现**两个口径不一致的计数源**:
    服务端 `total` 只按 category/rank/township/search_type/bbox 过滤,客户端还按
    extra_json 维度过滤 → 勾选"保存现状"等筛选时 Toolbar 与面板数字对不上。
  - 要消除分裂,须把 era/industry/risk 的**过滤**也下推服务端(json_extract LIKE
    近似,且会反向把存储格式焊进查询),即滑向"完整 B";其近似语义无法在本环境手测交互。
  - **结论(C+)**:`facets`/`list` 端点作为**未来真上规模时**做完整 B 的地基保留;当前
    前端一行不动。顺手撤销 `/api/relics` 的 `deprecated` 误标 + 启动告警(它是交叉筛选的
    合法数据源,并非 by-bbox 旧版替代品;`routers/relics.py`)。
  - **未来触发完整 B 的条件**:数据量到**万条以上**(跨县/全市/全省),或浏览器内存/首屏
    传输成为可感瓶颈时。届时:facets 驱动 Dashboard、list 驱动结果列表、era 桶反查 +
    industry/risk 服务端近似过滤,彻底移除 `all`;需在有 Node 的环境做交互手测验收。

- **`codes.py` → 前端字典物理生成**:本轮以漂移守护测试"强制单源",未做构建期生成。

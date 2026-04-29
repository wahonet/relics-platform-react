# 不可移动文物数字档案平台

Your know bro，在这个仓库里，你会看到大量的vibe-coding产物，opus4.6写出来的东西我学一辈子也赶不上，我就一产品经理。

—— 这 token 多少钱一兆？

—— 20 美元 1 M

—— whats up，你这 IDE 是金子做的还是 tokens 是金子做的啊？（象鸣）

—— 这现在哪有纯血的 opus4.6 tokens 啊，这都废弃信用卡和反代薅的，你嫌贵我还嫌贵呢（于是用 glm5.1 代餐）

面向 **第四次全国文物普查** 的县/区级 WebGIS 数字档案平台模板。
把一个县/区的四普原始资料（文物档案 DOCX、外业日志 Excel、行政边界 SHP、DEM、三维模型）放进来，
运行一条命令即可生成结构化数据与交互式三维地图档案。
（产品经理思路是好的，下面的人（指glm5.1）执行乱了）

当前仓库是 **"纯壳子"**：代码、脚本、配置、前端资源全部保留，但 `data/input/` 和 `data/output/` 里的所有演示数据（四普档案、照片、边界 SHP、生成的 `relics.db` / GeoJSON / 叙事 Markdown 等）已被清空，仓库里留了 `.gitkeep` 维持目录结构。
clone 下来按 `setup → (放入你自己的数据并改 config.yaml) → run_pipeline → start_platform` 的顺序即可跑通。
仓库里仍保留一份通用基础设施：`platform/webgis/static/data/shandong_admin.json`（山东省 16 地市/区县 bbox 字典），供"离线瓦片下载"和"主视角"两个功能的级联下拉使用；这不属于业务 demo 数据，可以直接沿用。

---

## 功能概览

- **React + three.js 主前端** — 全部 UI 切换为 React 18 + TypeScript + Vite 构建,主图组件继续使用 CesiumJS 提供地理引擎,**三维模型查看器**改为基于 three.js (`@react-three/fiber` + `3d-tiles-renderer`)。老版 vanilla 前端仍保留在 `/legacy` 路径,可作为回归对比。
- **三维 WebGIS** — 基于 CesiumJS，支持卫星/街道底图、本地 DEM 地形、符号化点位、行政边界渲染；默认 **2D 正射俯视**，勾选"地形"自动切到 3D 斜视。
- **底图与在线源切换** — 底图收纳进一个下拉菜单：`离线影像 / 离线矢量 / 在线影像（高德）/ 在线矢量（高德）/ 无底图`，透明度滑块也并入同一菜单；离线两项默认完全空白，只有进过"下载地图"模块入库的瓦片才会显示。
- **离线瓦片下载模块** — 支持两种范围源：① **地图框选**，拉一个矩形就能下；② **按县域选择**，两级下拉（山东省 16 地市 → 县区）一键圈定。下载过程带实时进度条（张数 / MB / 命中 / 失败），完成后磁盘缓存直接被地图读取；面板内置"打开文件夹""清空缓存"按钮。下载历史落 `data/output/tile_cache/_download_history.jsonl`，并在 Admin Dashboard 的"离线瓦片缓存"卡片里汇总展示。
- **可持久化主视角（Home View）** — 设置面板里按 **地级市 → 区县** 两级下拉选一个位置作为主视角，**选了就自动保存**（localStorage），之后顶部"重置"按钮和启动初始飞行都会回到这里；也可以把当前视角一键固化为主视角，或"恢复默认"回到 `config.yaml` 里配的 `geo.center`。
- **高性能渲染** — 点位走 `PointPrimitiveCollection` + `LabelCollection` 合批（5 万点稳定 55–60 fps），面图层按颜色聚合到 `GroundPrimitive`，空闲时 `requestRenderMode` 让 CPU 占用降到 < 5%。
- **视口查询** — `/api/relics/by-bbox` 接视口矩形 + 国标编码多选筛选，仅返回极简 8 字段（~180 字节/条），相机停下 300 ms debounce + 32 格 LRU 缓存。
- **SQLite + R-Tree + FTS5** — 主数据走 `relics.db`；空间查询用 R-Tree、中文子串搜索用 trigram FTS5，低于 3 字符的关键词自动走 LIKE 兜底。
- **国标编码字典** — `category`（`0100..0600`）/ `rank`（`1..5`）/ `search_type` 与国家文物局数据中心字段一致，前后端共用一份字典（`codes.py` / `dict.js`）。
- **档案详情** — 每处文物的基本信息、全部照片、全部图纸、简介、三维模型、四普档案 PDF。
- **多维度统计** — ECharts 仪表盘：类别 / 年代 / 级别 / 乡镇 / 普查类型 / 所有权 / 行业 / 现状 / 影响因素九维钻取，点击图表即叠加筛选。
- **外业普查路线** — 从现场照片 EXIF 还原每日普查轨迹，支持日期叠加、点位照片弹窗。
- **工作日志查看** — 外业日志 Excel → 分日 PDF，支持台账模糊匹配与一键联动地图。
- **村村达分析** — 按村界染色展示"已到达 / 未到达"，并给出未到达村清单。
- **AI 知识库问答** — 基于整个文物库 + 工作日志的大模型问答，支持流式输出；回答里 `📍` 可飞到文物、`📋` 可打开当天日志。
- **Admin 写入 + 审计** — `/api/admin/relics` CRUD 走 DB，`version` 字段做乐观锁，所有写操作落 `audit_log`，支持 CSV/JSON 批量导入。
- **Vue 管理后台** — 独立 SPA（`/admin-ui/`），Vue 3 + TypeScript + Element Plus + Pinia + Vite。覆盖数据概览、管线工作台、文物 CRUD、批量操作、地图框选筛选、回收站、审计日志+一键回滚、相邻文物查询等场景；与主图双向联动（`?relic=` 自动定位 / shift+click 拾取坐标回传编辑对话框）。
- **瓦片代理** — 磁盘 + 内存 LRU 双级缓存，未命中可按开关穿透回源（`Semaphore(16)` 限流、同 key 请求去重）；DEM 瓦片也带磁盘缓存。
- **配置即平台** — 县名、中心点、边界、投影、API Key 全部在 `config.yaml` 一处维护；前端不写死。
- **功能自动开关** — `features.*: auto` 可根据 `data/` 下子目录是否为空，自动隐藏对应功能按钮。

---

## 快速开始（三步）

### 1. 初始化

双击 `1-setup.bat`：

- 检测并安装 Python 依赖（Python 3.10+）
- 创建 `data/input/` 与 `data/output/` 目录骨架
- 从 `config.example.yaml` 生成 `config.yaml`
- 打印项目状态

> 若系统没装 Python，可把 [Windows embeddable 便携版 Python](https://www.python.org/downloads/windows/) 解压到 `./python/` 目录，脚本会自动使用。

### 2. 放入数据，改一改 config.yaml

**编辑 `config.yaml`**，至少要改：

| 字段 | 说明 |
|---|---|
| `project.name` / `project.full_name` | 县/区名称、平台标题 |
| `geo.center` / `geo.bounds` | 初始视角 + 外接矩形（决定 DEM 裁剪、瓦片缓存范围） |
| `geo.boundaries.projection` / `central_meridian` / `is_gcj02` | SHP 的投影信息，详见下文 |
| `administrative.county_name` / `townships` | 县名与乡镇顺序 |
| `api.siliconflow.key` 等 | AI 大模型 API Key（推荐用环境变量） |

**放入原始数据**：

| 目录 | 内容 | 必需 |
|---|---|---|
| `data/input/01_archives/` | 四普文物档案 DOCX（可按乡镇子目录组织，如 `01示范街道/xxx.docx`） | 是 |
| `data/input/02_worklogs/` | 外业工作日志 Excel + `外业工作台账.xlsx` | 可选 |
| `data/input/03_boundaries/` | 县/镇/村 Shapefile 或 GeoJSON | 建议 |
| `data/input/04_dem/` | ASTER GDEM v2 GeoTIFF（`ASTGTM2_N*E*_dem.tif`） | 可选 |
| `data/input/05_models_3d/` | 三维模型 3D Tiles（按文物名分子目录） | 可选 |

### 3. 跑数据管线，启动平台

四个 bat 文件按数字前缀顺序执行即可:

```
双击 1-setup.bat       # 一次性初始化 (装 Python 依赖 / 建 data 目录 / 生成 config.yaml)
双击 2-pipeline.bat    # 数据管线: DOCX → Markdown → CSV/JSON/GeoJSON / 照片 / 图纸 / PDF / 边界
双击 3-build.bat       # 一次性构建两个前端: Vue 后台 + React 主前端 (需 Node.js 18+)
双击 4-start.bat       # 启动 WebGIS,默认浏览器自动打开 http://127.0.0.1:8000
```

> 数据没准备好时 `2-pipeline.bat` 会自动跳过空目录,可以直接跑 `3-build.bat` + `4-start.bat` 看到空壳子界面。

- 主图：`http://127.0.0.1:8000/` (`build_webgis.bat` 产物挂载在 `/app/`,根路径会自动 302 过去；未构建时回退到 `/legacy` 老版 Cesium 页面)
- 管理后台：`http://127.0.0.1:8000/admin-ui/`（先 `build_admin.bat` 产物才会挂载；否则启动日志会提示跳过）
- 老版主图：`http://127.0.0.1:8000/legacy` (回归对比用)
- 默认管理员账号：见 `config.yaml → admin`，登录后的 Cookie 会被前端自动带上。

> 主前端开发模式 (热重载): `cd platform/webgis-react && npm run dev`,开发服务器默认在 `http://127.0.0.1:5174/`,
> 已在 `vite.config.ts` 把 `/api/*` `/tiles/*` `/photos/*` `/drawings/*` `/boundaries/*` 等反代到 FastAPI 8000 端口。
>
> 管理后台开发模式（热重载）：`cd platform/admin-vue && npm run dev`，开发服务器默认在 `http://127.0.0.1:5173/`，
> 已在 `vite.config.ts` 把 `/api/*` 和 `/tiles/*` 反代到 FastAPI 8000 端口，日常改 UI 不用重新 build。

---

## 目录结构

```
relics-platform/
├── config.yaml                ← 项目唯一入口配置（由 setup.bat 从 example 拷贝生成）
├── config.example.yaml        ← 配置模板，升级时对照合并
├── .gitignore                 ← 已忽略 config.yaml / data/ / .env / *.key
│
├── 1-setup.bat                ← 初始化向导（装依赖、建目录、生成 config.yaml）
├── 2-pipeline.bat             ← 数据管线入口
├── 3-build.bat                ← 同时构建 Vue 后台 + React 主前端（智能检测依赖变更触发 npm install）
├── 4-start.bat                ← 启动 WebGIS 服务
│
├── data/                      ← 用户数据区（不纳入 Git）
│   ├── input/                 ← 原始资料
│   │   ├── 01_archives/       ← 档案 DOCX
│   │   ├── 02_worklogs/       ← 工作日志 Excel
│   │   ├── 03_boundaries/     ← 行政边界
│   │   ├── 04_dem/            ← DEM GeoTIFF
│   │   └── 05_models_3d/      ← 三维模型 3D Tiles
│   └── output/                ← 管线产物
│       ├── markdown/          ← step01：DOCX 转成的结构化 Markdown
│       ├── dataset/           ← step02/07：CSV / JSON / GeoJSON / relics.db
│       ├── photos/            ← step03：档案内嵌的文物照片
│       ├── drawings/          ← step04：档案内嵌的图纸
│       ├── worklog_pdf/       ← step05：每日外业日志 PDF
│       ├── boundaries/        ← step06：WGS-84 统一化后的边界 GeoJSON
│       ├── tile_cache/        ← 瓦片代理磁盘缓存（可选预热）
│       ├── terrain_cache/     ← DEM 地形瓦片磁盘缓存
│       └── logs/              ← 各脚本运行日志
│
└── platform/                  ← 平台代码（升级时可整体覆盖此目录）
    ├── webgis/                ← FastAPI 后端 + 老版 Cesium 静态前端 (legacy fallback)
    │   ├── main.py            ← 瓦片代理穿透 + DEM 缓存 + 生命周期 + /admin-ui /app 静态挂载
    │   ├── serve.py           ← 启动入口（读 config.yaml，自动开浏览器）
    │   ├── data_loader.py     ← Repository：SQLite 优先，JSON 兜底；含 CRUD / 审计 / 空间查询 / 回滚
    │   ├── terrain_provider.py← 本地 DEM → Cesium 地形瓦片
    │   ├── routers/           ← API：relics / stats / chat / admin / worklog / survey_routes
    │   ├── static/js/         ← 老版 vanilla 前端脚本 (供 /legacy 回退)
    │   ├── templates/         ← index / login / model-viewer / pdf-viewer (老版)
    │   └── requirements.txt
    ├── webgis-react/          ← React + three.js 主前端 (新版,挂载到 /app/)
    │   ├── src/
    │   │   ├── api/                ← axios + 按 router 拆分的 API
    │   │   ├── stores/             ← Zustand: platform / relics / filter / ui / homeView
    │   │   ├── map/                ← Cesium Viewer + 视口查询 + 边界图层
    │   │   ├── three/              ← three.js 三维模型查看器 (r3f + 3d-tiles-renderer)
    │   │   ├── components/         ← Header / Toolbar / FilterPanel / Dashboard 等
    │   │   ├── pages/              ← ModelViewerPage / PdfViewerPage / LoginPage
    │   │   ├── utils/              ← dict (国标编码) / markdown
    │   │   └── styles/globals.css
    │   ├── scripts/fix-cesium-path.mjs ← 构建后修正 Cesium 静态资源路径
    │   ├── vite.config.ts     ← dev 反代 /api 等; 生产 base=/app/
    │   └── package.json
    ├── admin-vue/             ← Vue 3 + TS + Element Plus 管理后台（独立 SPA）
    │   ├── src/
    │   │   ├── api/admin.ts        ← 统一 API 客户端（axios + 401/409 拦截器）
    │   │   ├── stores/             ← Pinia：auth、dict、pipeline
    │   │   ├── router/             ← hash 模式，支持 ?status= / ?search= / ?auto_open= 等深链
    │   │   ├── views/              ← Dashboard / Pipeline / Relics / Audit / Login / Import
    │   │   ├── components/         ← RelicEditDialog / BboxPickerDialog / PipelineHealthCard 等
    │   │   └── main.ts
    │   ├── vite.config.ts     ← dev 反代 /api、/tiles；生产 base=/admin-ui/
    │   └── package.json
    ├── scripts/               ← 7 步数据管线
    │   ├── run_pipeline.py
    │   ├── step01_convert_docs.py      ← DOCX → 结构化 Markdown（LLM）
    │   ├── step02_build_dataset.py     ← Markdown → CSV/JSON/GeoJSON（坐标统一）
    │   ├── step03_extract_photos.py    ← 解包文物照片
    │   ├── step04_extract_drawings.py  ← 解包文物图纸
    │   ├── step05_convert_worklogs.py  ← Excel 日志 → PDF
    │   ├── step06_prepare_boundaries.py← Shapefile → WGS-84 GeoJSON
    │   ├── step07_build_db.py          ← 灌库到 SQLite（R-Tree + FTS5 + audit_log）
    │   ├── codes.py                    ← 国标编码字典（与前端 dict.js 对齐）
    │   └── _common.py                  ← 配置加载、坐标变换、路径管理
    ├── tools/
    │   └── download_tiles.py  ← 按 bounds 预下载离线瓦片
    ├── assets/                ← 图标等平台自带资源
    └── docs/                  ← 使用文档
```

### 前端模块（`platform/webgis/static/js/`）

| 文件 | 职责 |
|---|---|
| `bus.js` | 轻量事件总线（`on`/`off`/`emit`/`once`），替代跨模块 monkey-patch |
| `dict.js` | 国标编码 → 标签/颜色/图标/大小/标签显示距离；与 `codes.py` 一一对应 |
| `point_renderer.js` | `PointPrimitiveCollection` + `LabelCollection` 合批点位，diff 更新，按 `rank` 分级分配标签预算 |
| `polygon_renderer.js` | 按颜色聚合的 `GroundPrimitive` + `GroundPolylinePrimitive` 面图层 |
| `viewport.js` | 监听 `camera.moveEnd` → 300 ms debounce → `/api/relics/by-bbox` + 32 格 LRU |
| `filter.js` | 计算本地筛选 `filtered`（图表/列表），同时把 category/rank/township 编码下沉到 viewport |
| `render.js` | 旧 Entity 渲染路径的兼容 stub（`entityMap` / `polygonEntities` 仍保留供边界、路线复用） |
| `home_view.js` | 主视角（Home View）管理：`localStorage` 持久化、读取 `/static/data/shandong_admin.json` 构造"市 → 县"级联下拉、`flyToHome(duration)` 供重置按钮与初始飞行调用 |
| `tile_download.js` | 离线瓦片下载模块的前端逻辑：框选 / 县域两种范围模式、异步轮询进度、结果卡片、打开文件夹、清空缓存 |
| `pick_mode.js` | 坐标拾取模式：Admin 编辑对话框"在主图拾取"→ `shift+click` 回传 `{lng,lat,alt}` |
| `app.js` | 应用入口：构建 renderer、启动 viewport、绑定点击/键盘/移动端 Bus |


---

## 数据管线详解

`run_pipeline.bat` 本质上是：

```
python platform\scripts\run_pipeline.py [options]
```

| Step | 脚本 | 必需输入 | 产物 | 说明 |
|---|---|---|---|---|
| 01 | step01_convert_docs | `01_archives/*.docx` | `output/markdown/*.md` | 用大模型把 DOCX 规范化成 Markdown，并抽出各字段列表 |
| 02 | step02_build_dataset | step01 产物 | `dataset/relics.{csv,json}`、`polygons.geojson`、`index.json` | 统一坐标系到 WGS-84（含 GCJ-02 → WGS-84）、三维模型匹配、风险打分 |
| 03 | step03_extract_photos | `01_archives/*.docx` + step02 | `output/photos/`、`photos_index.json` | 按"图纸在前、照片随后"的约定从 DOCX 抽图 |
| 04 | step04_extract_drawings | 同上 | `output/drawings/`、`drawings_index.json` | 同上，图纸永远排在 DOCX 最前面 |
| 05 | step05_convert_worklogs | `02_worklogs/*.xlsx`（可选） | `output/worklog_pdf/YYYYMMDD.pdf` | 排版成 A4 多页 PDF，供日志查看器嵌入 |
| 06 | step06_prepare_boundaries | `03_boundaries/*`（可选） | `output/boundaries/{county,townships,villages}.geojson` | 支持 Shapefile / GeoJSON，自动反投影到 WGS-84 |
| 07 | step07_build_db | step02–step04 的产物 | `output/dataset/relics.db` | 灌库到 SQLite：主表 `relics` + R-Tree `relics_rtree` + 全文索引 `relics_fts` (trigram) + `photos`/`drawings`/`polygons`/`audit_log`/`stats_cache`。中文字段经 `codes.py` 规范化成国标编码 |

### 管线高级用法

```bat
:: 列出所有可用步骤
python platform\scripts\run_pipeline.py --list

:: 只跑某些步骤
run_pipeline.bat --only 02
run_pipeline.bat --from 03 --to 05

:: 跳过某步（已验证可重复跑的脚本都支持断点续跑）
run_pipeline.bat --skip 01

:: 只打印将要执行的步骤，不真正运行
run_pipeline.bat --dry-run
```

可选步骤（worklog、boundaries、dem、3d）若对应 input 目录为空会**自动跳过**，不会中止管线。

> Step 07 是**可选但强烈推荐**的：
> - 若 `output/dataset/relics.db` 存在，后端自动走 SQLite 模式（视口查询 / 全文搜索 / Admin 写入都走 DB）；
> - 不存在则回退到老的 JSON 模式（兼容老部署，但性能按千条量级设计，不建议上万条）。

---

## 架构与 API

### 后端数据层（Repository 模式）

`data_loader.store` 统一数据访问接口，对外保持两种模式：

| 模式 | 触发条件 | 查询走向 |
|---|---|---|
| **SQLite**（推荐） | `output/dataset/relics.db` 存在 | 视口查询走 R-Tree、全文搜索走 FTS5、写入走事务 + 审计 |
| **JSON** fallback | 仅 `relics_full.json` 存在 | 全量内存遍历，零外部依赖 |

启动时依然会把 `relics` 全量缓存到 `self.relics` / `self.relics_map`，老 API / AI 上下文 / 图表等路径零改动。

### 核心 API

| 路由 | 作用 | 备注 |
|---|---|---|
| `GET /api/relics` | 全量列表（~180 B/条的轻量版） | **已标记 deprecated**，保留给 AI 上下文 / 图表 / 列表 |
| `GET /api/relics/by-bbox` | 视口矩形 + 多选筛选 | 极简 8 字段：`id/code/name/lng/lat/category/rank/has_3d` |
| `GET /api/relics/search` | FTS5 全文搜索 | trigram 分词；关键词 <3 字时自动降级为 LIKE |
| `GET /api/relics/{code}` | 单条完整详情 | DB 模式下会 merge `extra_json` |
| `GET /api/relics/{code}/polygon` | 单条文物的几何 | GeoJSON Polygon |
| `POST /api/admin/relics` | 创建文物 | 自动把 `category_main/heritage_level/center_lng` 等老字段翻译成国标编码 |
| `PUT /api/admin/relics/{code}` | 乐观锁更新 | 必传 `expected_version`，冲突返回 409 |
| `DELETE /api/admin/relics/{code}` | 软删除 | `status = -1`，可通过 PUT 恢复 |
| `GET /api/admin/relics` | 后台分页列表 | 支持 `status`（`-1` 回收站 / `0` 草稿 / `1` 正常 / `all`）、`search`、`category`、`rank`、`township`、`bbox` |
| `GET /api/admin/relics-export` | CSV 导出 | 流式 + UTF-8 BOM，筛选参数同上；编码列额外附中文 label |
| `POST /api/admin/relics/bulk-update` | 批量改字段 | 软乐观锁（逐条 `version` 校验，冲突只记录不中断） |
| `POST /api/admin/relics/bulk-status` | 批量改状态 | 发布 / 下架 / 恢复 |
| `POST /api/admin/relics/import` | 批量导入 | CSV / JSON；`mode=upsert` 或 `create_only` |
| `GET /api/admin/relics/{code}/neighbors` | 相邻文物 | bbox 粗筛 + Haversine 精算，按距离升序，参数 `radius`（米）/`limit` |
| `GET /api/admin/audit` | 审计日志（多条件） | `action`（逗号多选：create/update/delete/rollback）、`actor`、`field`、`start_ts`、`end_ts`、`code` |
| `POST /api/admin/audit/{id}/rollback` | 回滚审计项 | `create` → 软删；`update/delete/rollback` → 按 `before_json` 还原（走乐观锁） |
| `GET /api/admin/pipeline` | 管线分步状态 | 给 Dashboard 健康卡和管线工作台用 |
| `GET /api/admin/stats-overview` | 首页聚合 | 文物总数 / 草稿 / 回收站 / 照片覆盖率 / 14 天审计趋势等 |
| `GET /api/admin/tiles/summary` | 离线瓦片缓存总览 | 给 Dashboard 的"离线瓦片缓存"卡片用：各 provider 的张数/字节数、最近下载历史 |
| `GET /tiles/{provider}/{z}/{x}/{y}` | 底图瓦片代理 | 内存 LRU + 磁盘缓存 + 可选穿透回源；支持 `?offline=1` 让代理对未命中项直接返回 1×1 透明 PNG |
| `POST /api/tiles/download` | 启动一次离线瓦片下载任务 | 入参：`bbox`、`zooms`、`providers`、`label`；返回 `job_id`，前端异步轮询 |
| `GET /api/tiles/progress/{job_id}` | 下载进度轮询 | 返回 `downloaded / skipped / failed / bytes / status` |
| `GET /api/tiles/history` | 最近下载历史 | 读 `data/output/tile_cache/_download_history.jsonl`，`limit` 可调 |
| `POST /api/tiles/open-cache-folder` | 在本机资源管理器打开瓦片缓存目录 | Windows 直接 `os.startfile`；便于核查下载是否落地 |
| `POST /api/tiles/clear-cache` | 清空所有离线瓦片 | 同时清空进程内的 LRU 缓存，避免"磁盘清了但前端仍显示空白"那种诡异现象 |
| `GET /api/terrain/{level}/{x}/{y}` | DEM 地形瓦片 | 磁盘缓存命中直接 sendfile |

### 国标编码字典

| 维度 | 取值 | 含义 |
|---|---|---|
| `category` | `0100/0200/0300/0400/0500/0600` | 古遗址 / 古墓葬 / 古建筑 / 石窟寺及石刻 / 近现代重要史迹 / 其他 |
| `rank` | `1/2/3/4/5` | 国保 / 省保 / 市保 / 县保 / 未定级 |
| `search_type` | `2/12/110301` | 三普在册 / 县级以上公布 / 四普新增 |

后端 `platform/scripts/codes.py` 与前端 `platform/webgis/static/js/dict.js` 保持一致；调整映射要两处同步。老的中文字段（`古建筑`、`省级文物保护单位` 等）通过 `normalize_*` 在边界处一次性映射。

### 前端渲染策略

- **地图点位** 由 `viewport.js` 根据相机视口按需拉取，不再 `onFilterChange` 就全量重绘；
- **筛选下沉**：`filter.js` 把 `category` / `rank` / `township` 翻译成国标编码透传给 `/api/relics/by-bbox`，本地仍然计算 `filtered` 驱动列表 / 图表 / 乡镇联动；
- **标签密度** 按 `rank` 升序分配 `LABEL_BUDGET=300`：视口内即便 5 000 点，国保 / 省保的标签也一定能看见；
- **面图层** 按颜色聚合为 `GroundPrimitive` + `GroundPolylinePrimitive`，渲染调用数从 O(n) 降到 O(颜色数)；
- **事件总线** `bus.js` 解耦移动端行为（`chat:toggled` / `filter:changed` / `info:closed`），替代之前的 monkey-patch。

---

## Vue 管理后台（`platform/admin-vue/`）

### 页面组成

| 路由 | 页面 | 作用 |
|---|---|---|
| `/login` | 登录 | HTTPOnly Cookie 鉴权，Pinia `auth` store 缓存身份 |
| `/dashboard` | 数据概览 | 顶部四张统计卡（总数 / 草稿+回收站 / 待发布 / 照片覆盖率）；**管线健康卡**（6 步状态+进度+最近运行时间，可点击跳转管线页）；ECharts 14 天审计趋势、分类饼图、级别条形图；最近活动流 |
| `/pipeline` | 数据管线工作台 | 轮询 `/api/admin/pipeline`，按步骤展示状态/耗时/日志尾，支持 run-all / run-step / 重跑 / 查看日志 |
| `/relics` | 文物列表 | 分页 + 多条件筛选（关键词 / 类别 / 级别 / 乡镇 / 状态 Tab）+ **地图框选**（Leaflet 弹窗拖拽画 bbox）+ 多选批量（改字段 / 改状态 / 导出 CSV）+ 回收站 Tab；支持 `?status=` `?search=` `?auto_open=` 深链 |
| `/relics`（编辑对话框） | 文物详情/编辑 | 四个 Tab：**基本信息**（乐观锁 + 字典下拉）/ **位置**（内嵌 Leaflet mini-map 拾取坐标 + 在主图打开）/ **附件状态**（照片/图纸/PDF/3D 计数）/ **相邻文物**（Haversine 半径内邻居，500m–5km 可调，可跳转编辑或在主图定位）；右侧抽屉显示该文物最近 10 条审计 |
| `/import` | 批量导入 | 拖放 CSV/JSON，前端预览 + 后端 `mode=upsert` / `create_only` |
| `/audit` | 审计日志 | 多条件筛选（action 多选 / actor LIKE / field LIKE / 时间段 / relic code）+ 每行**一键回滚**（el-popconfirm），回滚本身也会落一条 `action=rollback` 的新审计 |

### 与主图的联动

- **主图 → 后台**：在主图弹窗中点"后台编辑" → 打开 `/admin-ui/#/relics?search=CODE&auto_open=CODE`，自动定位并弹出编辑对话框。
- **后台 → 主图（坐标拾取）**：编辑对话框点"在主图拾取" → 新开主图窗口并进入拾取模式，主图 `shift+click` 或按钮确认后通过 `window.opener.postMessage` 把 `{lng,lat,alt}` 回传到编辑表单。
- **后台 → 主图（定位）**：任意"在主图定位"按钮 → `/?relic=CODE`，主图启动时读取 URL 参数，`flyTo` 并高亮该条。

### 开发 / 生产模式

| 模式 | 启动方式 | Vue 资源来源 | API 走向 |
|---|---|---|---|
| 开发 | `cd platform/admin-vue && npm run dev` → `http://127.0.0.1:5173/` | Vite dev server（HMR） | Vite 反代 `/api/*` / `/tiles/*` → FastAPI `127.0.0.1:8000` |
| 生产 | `build_admin.bat` → `npm run build` 产物挂到 `/admin-ui/` | FastAPI `StaticFiles` 托管 `platform/admin-vue/dist/` | 同域直连 |

`build_admin.bat` 会比对 `package.json` 与 `node_modules/.package-lock.json` 的修改时间，只有真的变了才触发 `npm install`，平时构建只花几秒。

### 写入安全

- **单条更新**：必须携带 `expected_version`，后端 `UPDATE ... WHERE code=? AND version=?`，不匹配返回 409。
- **批量更新**：采用"软乐观锁"——逐行校验 `version`，冲突行计入 `conflicts[]` 而不中断其他记录，前端用 `ElMessage` 汇总提示。
- **回滚**：`create` 回滚语义为软删（`status=-1`）；`update/delete/rollback` 回滚语义为按 `before_json` 还原，过程中仍走乐观锁，失败同样 409。回滚本身写入新的 `action=rollback` 审计条目，保证链路可追溯。

---

## 关键配置说明

### 坐标系三连（`geo.source_crs` / `geo.boundaries`）

这是全平台最容易踩坑的地方。

**`geo.source_crs`** 指档案里文物点位的坐标系：

| 取值 | 含义 |
|---|---|
| `wgs84` | 国际标准，野外 GPS 直接读到的就是这个 |
| `gcj02` | 国测局"火星坐标"，高德地图/部分国产 GIS 导出的坐标 |
| `cgcs2000` | 国家大地 2000，与 WGS-84 差亚米级，按 wgs84 处理 |

**`geo.boundaries.projection`** 指 SHP 的投影：

| 取值 | 含义 |
|---|---|
| `none` / `wgs84` / `cgcs2000` | 已经是经纬度，无需反投影 |
| `gauss_kruger` | 高斯-克吕格平面坐标（国内测绘成果最常见），需同时填 `central_meridian` |
| `gcj02` | SHP 本身是 GCJ-02 经纬度（少见） |

**`geo.boundaries.is_gcj02`** 是个专门为"国内四普下发的镇界"开的补丁：

> 某些四普下发的行政边界 SHP，是在 GCJ-02 经纬度基础上再做的高斯投影。
> 此时 `projection: gauss_kruger` 反投影完得到的是 GCJ-02，而不是 WGS-84。
> 如果和文物点位（WGS-84）叠图时发现**整体系统性偏移约 500 米**，把 `is_gcj02` 设为 `true`，`step06` 会在反投影后再做一次 GCJ-02 → WGS-84 修正。

常见中央经线参考：

| 省份 | 山东 | 江苏 | 安徽 | 河南 | 湖北 | 四川 |
|---|---|---|---|---|---|---|
| `central_meridian` | 117 | 120 | 117 | 114 | 111 | 105 |

### 功能开关（`features.*`）

```yaml
features:
  enable_3d_model: auto       # 三维模型查看器
  enable_worklog:  auto       # 工作日志
  enable_dem:      auto       # 本地地形
  enable_ai_chat:  true       # AI 知识库
```

- `auto` — 后端启动时检测对应 `data/` 目录是否为空，为空就让前端隐藏这个功能按钮
- `true` — 强制开启（若数据缺失会在对应页面报错）
- `false` — 强制关闭

### 敏感信息（API Key）

`config.yaml` 里任何 `"${ENV_NAME}"` 形式的值都会在程序启动时从环境变量读取：

```yaml
api:
  siliconflow:
    key: "${SILICONFLOW_KEY}"
  cesium_ion:
    token: "${CESIUM_ION_TOKEN}"
```

推荐通过环境变量注入，避免把 Key 写进会被 commit 的文件：

```cmd
setx SILICONFLOW_KEY "sk-xxxxxxxxxxxx"
setx CESIUM_ION_TOKEN "eyJhbGciOi..."
```

`.gitignore` 已默认忽略 `.env` / `.env.*` / `*.key` / `config.yaml` / `data/`，可以放心提交代码。

---

## AI 问答模块

前端聊天面板对接的是后端 `/api/chat` 流式接口。

- **服务端配置** — `config.yaml → api.siliconflow`，支持 SiliconFlow / OpenAI 兼容 API（DeepSeek、GLM、Kimi 等均可）。
- **上下文构造** — 启动时 `data_loader` 把全部文物 + 全部日志预烘焙成一段 system prompt，和用户问题一起送给模型。参数在 `top_k_relics / top_k_worklog / history_turns / temperature` 里调。
- **地图联动** — 回答里出现 `[[显示文字|fly:ARCHIVE_CODE]]` / `[[显示文字|log:YYYY-MM-DD]]` / `[[显示文字|t:乡镇&l:级别]]` 会被渲染成可点击链接，点击即触发地图飞行/日志/筛选。

如果模型回答漂移、上下文超长，可把 `top_k_*` 适当调小。

---

## 离线瓦片与地形

想让 WebGIS 在弱网或无网环境下依旧能看底图：

```cmd
python platform\tools\download_tiles.py
```

脚本会根据 `config.yaml → geo.bounds` 覆盖的范围，预下载所有层级瓦片到 `data/output/tile_cache/`。

运行时 `/tiles/{provider}/{z}/{x}/{y}` 的查找顺序：

1. **内存 LRU**（`OrderedDict`，容量 1000） — 命中直接返回；
2. **磁盘缓存** — `data/output/tile_cache/<provider>/<z>/<x>/<y>.tile`；
3. **穿透回源**（默认开启，`features.offline_only: true` 可关） — 用 `asyncio.Semaphore(16)` 限制上游并发、同 URL 请求去重，拉完后异步写回磁盘和内存缓存；
4. **兜底** — 源站失败或离线模式，返回 1×1 透明 PNG。

DEM 地形瓦片 `/api/terrain/{level}/{x}/{y}` 也加了磁盘缓存（`data/output/terrain_cache/`），热瓦片直接 sendfile 返回，冷瓦片现场采样后落盘。

---

## 常见问题

**Q：文物点位集体偏到了边界外面几百米？**
A：99% 是坐标系问题。
① 先看 `geo.source_crs` 和 `geo.boundaries` 两处设置是否和你的数据源匹配；
② 国内四普下发的镇界大概率要开 `is_gcj02: true`，见上文；
③ 边界修改后需要重跑 `run_pipeline.bat --only 06`。

**Q：启动提示 `ModuleNotFoundError: platform.webgis` ？**
A：Python 内置了 `platform` 标准库模块，会和项目目录重名。请用 `start_platform.bat`（内部调的是 `python platform\webgis\serve.py` 绝对路径），不要手写 `uvicorn platform.webgis.main:app`。

**Q：`[Errno 10048] 端口被占用`？**
A：上一次服务没彻底退出。`taskkill /F /IM python.exe`，或在 `config.yaml → server.port` 换一个端口。

**Q：AI 问答总报 401 / 余额不足？**
A：`SILICONFLOW_KEY` 没生效。先 `echo %SILICONFLOW_KEY%` 确认，然后**重开**一个 cmd 或重开 IDE（环境变量是进程启动时读取的）。

**Q：demo 跑起来是好的，但替换成自己县的数据后管线失败？**
A：最常见是 DOCX 目录命名不规范。约定：`data/input/01_archives/{序号}{乡镇名}/{文物名}.docx`，例如 `01示范街道/某某村古寨遗址.docx`。序号可省略，乡镇目录可省略（直接把 DOCX 平铺在 `01_archives/` 下也行）。

**Q：访问 `/admin-ui/` 显示 `{"detail":"Not Found"}` ？**
A：Vue 后台还没构建。跑 `build_admin.bat`（或 `cd platform/admin-vue && npm run build`）生成 `dist/` 后重启 FastAPI 即可；平时改 UI 用 `npm run dev`，走 `http://127.0.0.1:5173/` 热更新。

**Q：`npm -v` 报 PowerShell "禁止运行脚本"？**
A：用管理员 PowerShell 执行 `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` 即可。另外 Node.js 请装 LTS（≥ 18）。

**Q：保存文物时弹 "数据已被他人修改（409）" ？**
A：`version` 乐观锁生效了。说明这条记录在你打开编辑框到保存之间被其他人/批处理改过。关闭对话框重新打开（会重新读取最新 `version`）后再改即可。

**Q：`build_admin.bat` / `start_platform.bat` 提示乱码命令报错？**
A：两个脚本已统一改为 ASCII 实现并启用 `setlocal EnableDelayedExpansion`，规避 Windows CMD 默认 GBK 和变量延迟展开问题。如果自己改脚本请保持纯英文注释。

---

## 技术栈

- **后端** — Python 3.10+ / FastAPI / Uvicorn / Pydantic v2 / SQLite (`sqlite3` 标准库，需 ≥3.34 以启用 FTS5 trigram)
- **主图前端** — CesiumJS / ECharts / pdf.js（零构建工具链，浏览器直接加载）
- **管理后台** — Vue 3 + TypeScript + Vite / Element Plus / Pinia / Vue Router 4 / Axios / Leaflet（mini-map & bbox 选择器）/ ECharts
- **数据管线** — python-docx / openpyxl / reportlab / Pillow / pyshp / numpy / tifffile / shapely
- **大模型** — OpenAI 兼容协议（默认接 SiliconFlow）
- **坐标** — 自实现 GCJ-02 ⇄ WGS-84，高斯-克吕格反投影

---

## 最近主要改动（2026-04-22）

这次收尾把前面几天积累的 UI/UX 问题一次清干净，并把 demo 数据全部抽走，留下一个可以直接交付给县里做底板的"纯壳子"。

### 地图主界面

- **标题正名**：`config.yaml → project.name / full_name` 从 "演示县不可移动文物数字档案平台（公开演示）" 改成 "XX县/区不可移动文物数字档案平台"，部署时按实际县名替换即可。
- **工具栏重分组**（`platform/webgis/templates/index.html` + `static/js/boundary.js`）：按"功能相近"用浅灰描边的 `tb-group.boxed` 外框把按钮捆成四组——
  1. 数据查询：`筛选` / `路线`
  2. 影像类：`底图影像 ▾`（离线/在线 5 选 1 + 透明度滑块全部收进同一下拉菜单）/ `下载地图`
  3. 图层叠加：`边界 ▾` / `标注 ▾` / `地形`
  4. 窗口级操作：`全屏` / `重置`（推到最右边）
- **状态栏真正居中**：`#statusSummary`（"当前位置：xxxx"）改用绝对定位 + `transform: translate`，字号放大一档，点击事件穿透（`pointer-events: none`），不会再抢按钮焦点。
- **默认 2D，勾"地形"进 3D**：地图以正射俯视方式启动，CPU/GPU 占用最低；勾选"地形"后自动切到 3D 斜视并启用本地 DEM 地形瓦片，取消勾选还原 2D。

### 主视角 (Home View)

- 新增 `platform/webgis/static/js/home_view.js` 模块。
- 设置面板里的"主视角"区块：顶部两级联级下拉 **地级市 → 区县**，数据源 `/static/data/shandong_admin.json`；底部还留了"固化当前视角 / 恢复默认 / 应用并飞过去"三个操作。
- **改动选择即自动保存**：挑完市或县会立刻写 `localStorage`，不再需要点"应用"才生效——这样即便你忘了点按钮，下次打开页面、或点"重置"都会回到你最后一次挑的那块区域。
- **重置按钮不再失灵**：`layout.js → resetAll()` 现在把"清筛选 / 重渲染"包在 `try...catch` 里，随后同步调一次 `flyToHome(1.2)`，再 `setTimeout(goHome, 50)` 兜底一次——即便中途 `onFilterChange` 触发了新的 `moveEnd` 抢镜头，最终相机也一定会停在你设的主视角上。
- **下拉变空的那个 bug 也修了**：`fetch` 加了 cache-busting，`DOMContentLoaded` 起就预热一次数据，加载失败会把占位符改成明显的"（加载失败，请刷新页面）"并打 console.error，不再悄悄吞错。

### 离线瓦片下载

- 面板支持"**地图框选**"和"**按县域选择**"两种圈定方式；县域模式复用 `shandong_admin.json` 的两级下拉。
- 下载过程中顶部进度条实时刷新（张数 / MB / 命中 / 失败），完成后展示一张结果卡片。
- 面板尾部新增 "**打开文件夹**"（直接跳转到 `data/output/tile_cache/`）和 "**清空缓存**"（磁盘 + 内存双清）两个按钮。
- 历史记录落 `data/output/tile_cache/_download_history.jsonl`，Admin Dashboard 顶部多出一张"**离线瓦片缓存**"卡片，汇总各 provider 的张数 / 容量 / 最近一次下载时间。

### 数据瘦身 —— 仓库回到"纯壳子"

为了方便直接当模板交付，今天把演示数据全部清空，只留结构与 `.gitkeep` 占位：

```
data/input/01_archives/        已清空（保留 .gitkeep）
data/input/02_worklogs/        已清空
data/input/03_boundaries/      已清空（含 county/townships/villages 三级子目录）
data/input/04_dem/             已清空
data/input/05_models_3d/       已清空
data/output/markdown/          已清空
data/output/dataset/           已清空（relics.db / CSV / JSON / GeoJSON 全部抽走）
data/output/photos/            已清空
data/output/drawings/          已清空
data/output/boundaries/        已清空
data/output/worklog_pdf/       已清空
data/output/tile_cache/        已清空（包括 _download_history.jsonl）
data/output/terrain_cache/     已清空
data/output/logs/              已清空
```

这样 clone 下来是一个"什么都没有但一切功能都在"的平台；按 `setup → run_pipeline → start_platform` 依次跑一遍，再把目标县的资料放进 `data/input/`，就能看到属于这个县的成品档案。

### 涉及的主要文件

| 文件 | 动作 |
|---|---|
| `config.yaml` | 改 `project.name` / `project.full_name` |
| `platform/webgis/templates/index.html` | 工具栏重构、新增底图下拉菜单 `#baseLayerMenu`、`statusSummary` 绝对居中 |
| `platform/webgis/static/js/home_view.js` | 新增主视角模块：级联下拉、自动保存、预热加载、错误提示 |
| `platform/webgis/static/js/layout.js` | `resetAll()` 改造为 try/catch + 兜底 setTimeout flyToHome |
| `platform/webgis/static/js/boundary.js` | 新增 `toggleBaseLayerMenu()` / `pickBaseLayer()`，统一菜单关闭行为 |
| `data/input/*` & `data/output/*` | 清空演示内容并放置 `.gitkeep` |

---

## 开发状态

- [x] **A** — 工程骨架、config、.bat 入口、管线编排器
- [x] **B** — 数据管线脚本 7 步（DOCX/Excel/SHP/DEM → SQLite 全流程）
- [x] **C** — WebGIS 迁移：FastAPI 后端 + Cesium 前端全量接入 config.yaml
- [x] **D** — 性能重构：`PointPrimitiveCollection` / `GroundPrimitive` 合批、视口查询 + LRU、瓦片穿透回源 + 内存 LRU、DEM 磁盘缓存
- [x] **E** — Admin 写入走 DB：乐观锁 + 审计日志 + CSV/JSON 批量导入
- [x] **F** — Vue 管理后台 Phase 1–5：登录+主布局、管线工作台、文物 CRUD+批量操作+回收站、主图双向联动（拾取坐标 / `?relic=` 定位）、Dashboard 聚合+管线健康、相邻文物、地图框选筛选、审计筛选+一键回滚
- [x] **G** — 主图 UX 收尾：2D/3D 切换、底图下拉菜单（离线/在线/透明度三合一）、工具栏分组、状态栏真居中；可持久化主视角（级联下拉自动保存 + 重置按钮兜底飞回）；离线瓦片下载模块（框选 / 县域 两种模式 + 进度条 + 历史落盘 + Dashboard 汇总卡片）
- [x] **H** — 仓库瘦身为"纯壳子"：`data/input` 与 `data/output` 内所有演示数据清空，用 `.gitkeep` 维持目录骨架
- [ ] **I** — 边界/模型自动识别优化、stats 预聚合落 `stats_cache` 表、一键打包（内嵌 Python + 数据零依赖分发）

---

## 许可

源码以 **MIT License** 发布。平台里使用的第三方库各自遵循其开源协议；
`data/input/` 中的文物档案、照片、边界等数据**不属于本仓库**，版权归采集单位所有。

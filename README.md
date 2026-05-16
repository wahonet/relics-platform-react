# 不可移动文物数字档案平台

当前版本：V1.1.0 架构调整版

这是一个面向区县级不可移动文物普查、整理、展示、检索、审计和后台维护的 WebGIS 数字档案平台。它的核心目标不是做一个孤立的地图页面，而是把四普档案 DOCX、照片、图纸、工作日志、行政边界、DEM、三维模型和后台编辑流程收拢到同一套可落地的县区级平台里。

V1.1.0 是一次架构清理版本：保留 V1.0.0 的业务能力，拆掉过大的后端入口和后台页面，补上测试与 CI，把日常启动方式压缩成“后端入口 + 前端入口”两个脚本。数据管线仍然保留，但它不再需要占据日常启动流程；你可以在后台手动触发，也可以按需运行脚本。

完整架构树见 [docs/architecture/v1.1-architecture.md](docs/architecture/v1.1-architecture.md)，重构过程记录见 [docs/refactor/execution-log.md](docs/refactor/execution-log.md)。

## 快速开始

### 1. 准备配置

首次 clone 后，直接运行 `start-backend.bat` 会在缺少配置时自动复制一份模板：

```powershell
.\start-backend.bat
```

也可以手动复制：

```powershell
Copy-Item config.example.yaml config.yaml
```

生成后至少需要检查这些字段：

| 配置 | 作用 |
|---|---|
| `project.name` / `project.full_name` | 平台标题、区县名称 |
| `geo.center` / `geo.bounds` | 初始视角、瓦片下载和 DEM 裁剪范围 |
| `geo.boundaries.*` | 行政边界投影参数 |
| `administrative.county_name` / `townships` | 县区与乡镇列表 |
| `api.*` / 环境变量 | AI、地图源或其他外部服务密钥 |
| `server.enable_auth` / `server.users` | 登录保护开关与后台账号；模板默认账号为 `admin / changeme` |

真实数据放入 `data/input/`，生成结果会进入 `data/output/`。仓库只保留目录骨架和公开基础字典，不提交用户数据。

### 2. 启动后端

```powershell
.\start-backend.bat
```

脚本会优先使用 `.venv`，其次使用仓库内嵌 `python/`，最后使用系统 Python。依赖缺失时会自动安装 `platform/webgis/requirements.txt`。

默认后端地址：

```text
http://127.0.0.1:8000/
```

这个地址由 FastAPI 提供。后端会挂载已经构建过的前端产物，所以访问 `http://127.0.0.1:8000/` 通常会跳到 `http://127.0.0.1:8000/app/`，这是“后端集成入口”，适合只启动后端时查看已构建版本。

### 3. 启动前端

```powershell
.\start-frontend.bat
```

脚本会分别启动：

| 应用 | 地址 | 说明 |
|---|---|---|
| React WebGIS | `http://127.0.0.1:5174/` | 主地图、三维、统计、详情、AI、瓦片下载 |
| Vue Admin | `http://127.0.0.1:5173/` | 管理后台、管线、CRUD、审计、导入导出 |

前端 dev server 已在 Vite 中代理 `/api`、`/tiles`、`/photos`、`/drawings`、`/boundaries` 等路径到 FastAPI，不需要手工配 CORS。

端口关系可以这样理解：

| 端口 | 来源 | 用途 |
|---|---|---|
| `8000` | `start-backend.bat` / FastAPI | 后端 API、瓦片代理、静态挂载；`/app/` 和 `/admin-ui/` 是构建后的前端产物 |
| `5174` | `start-frontend.bat` / React Vite | 主 WebGIS 开发服务，热更新，接口代理到 `8000` |
| `5173` | `start-frontend.bat` / Vue Vite | Admin 开发服务，热更新，接口代理到 `8000` |

日常改前端时看 `5174` 和 `5173`；只想跑集成后的版本时看 `8000/app/` 和 `8000/admin-ui/`。

## 数据目录约定

```text
data/
├─ input/
│  ├─ 01_archives/        # 四普档案 DOCX，可按乡镇分子目录
│  ├─ 02_worklogs/        # 外业工作日志 Excel、照片轨迹等
│  ├─ 03_boundaries/      # 县、乡镇、村行政边界 SHP 或 GeoJSON
│  ├─ 04_dem/             # DEM GeoTIFF
│  └─ 05_models_3d/       # 三维模型或 3D Tiles
└─ output/
   ├─ markdown/           # step01 结构化 Markdown
   ├─ dataset/            # CSV / JSON / GeoJSON / relics.db
   ├─ photos/             # 档案照片
   ├─ drawings/           # 档案图纸
   ├─ boundaries/         # WGS-84 行政边界
   ├─ terrain_cache/      # DEM terrain 缓存
   └─ logs/               # 管线与后台任务日志
```

`data/input/` 不纳入 Git。`data/output/` 中大体积和敏感运行产物也已忽略，仅保留目录骨架。

## 数据管线

管线入口是：

```powershell
.venv\Scripts\python.exe platform\scripts\run_pipeline.py
```

常用命令：

```powershell
.venv\Scripts\python.exe platform\scripts\run_pipeline.py --list
.venv\Scripts\python.exe platform\scripts\run_pipeline.py --dry-run
.venv\Scripts\python.exe platform\scripts\run_pipeline.py --skip 05
```

七个步骤如下：

| Step | 脚本 | 输入 | 产物 | 说明 |
|---|---|---|---|---|
| 01 | `step01_convert_docs.py` | DOCX 档案 | Markdown | 用大模型把四普档案规范化为结构化文本 |
| 02 | `step02_build_dataset.py` | Markdown | CSV / JSON / GeoJSON | 生成核心数据集、点位、面域、统计字段 |
| 03 | `step03_extract_photos.py` | DOCX 档案 | 照片与索引 | 抽取档案内嵌文物照片 |
| 04 | `step04_extract_drawings.py` | DOCX 档案 | 图纸与索引 | 抽取档案内嵌图纸 |
| 05 | `step05_convert_worklogs.py` | Excel 日志 | PDF | 可选，将外业日志转换为查看器可读 PDF |
| 06 | `step06_prepare_boundaries.py` | SHP / GeoJSON | WGS-84 GeoJSON | 可选，处理县、乡镇、村边界 |
| 07 | `step07_build_db.py` | 数据集文件 | SQLite | 生成 `relics.db`，支持 R-Tree、FTS5、审计和后台写入 |

日常使用时，管线可以在 Vue Admin 的“管线工作台”里手动触发，不需要再把它做成单独的根目录 BAT 入口。

## 功能概览

- **三维 WebGIS 主图**：React + Cesium，支持离线/在线底图、行政边界、点位、面域、地形、主视角记忆和地图框选。
- **高性能点位渲染**：基于 Cesium primitive/collection 思路，按等级、类别、筛选状态渲染大量文物点。
- **视口查询**：`/api/relics/by-bbox` 支持地图移动后的轻量点位刷新，降低前端首屏压力。
- **SQLite 数据核心**：优先读取 `relics.db`，使用 R-Tree 做空间检索、FTS5 做全文检索，JSON 作为兼容 fallback。
- **档案详情**：展示文物基本信息、照片、图纸、简介、PDF、三维模型和关联工作日志。
- **后台管理**：Vue 3 + Element Plus，覆盖 Dashboard、管线、文物 CRUD、批量修改、导入导出、审计日志、回收站和相邻文物查询。
- **离线瓦片下载**：支持地图框选和行政区选择，下载进度、历史记录和缓存统计都接入后台。
- **DEM terrain**：本地 DEM 可切成 Cesium terrain tile，并带磁盘缓存。
- **外业路线与村庄覆盖**：从照片 EXIF 或轨迹数据还原外业路线，结合村界计算覆盖情况。
- **AI 知识库问答**：基于文物数据和工作日志提供问答入口，回答中的文物和日志可以联动地图。
- **审计与乐观锁**：后台写操作写入 `audit_log`，文物编辑使用版本字段减少覆盖风险。

## 架构分层

```text
relics-platform-react/
├─ start-backend.bat              # 后端唯一根入口
├─ start-frontend.bat             # 前端唯一根入口
├─ config.example.yaml            # 配置模板
├─ VERSION                        # 当前版本
├─ requirements-dev.txt           # 测试依赖
├─ pytest.ini
├─ .github/workflows/ci.yml       # CI
├─ docs/                          # 架构、发布、执行记录
├─ tests/                         # pytest 测试
└─ platform/
   ├─ scripts/                    # 7 步数据管线
   ├─ webgis/                     # FastAPI 后端
   ├─ webgis-react/               # React 主前端
   ├─ admin-vue/                  # Vue 管理后台
   └─ tools/                      # 辅助工具
```

### FastAPI 后端

```text
platform/webgis/
├─ main.py                        # 应用组合入口、生命周期、静态挂载
├─ serve.py                       # 后端启动入口
├─ tile_routes.py                 # 瓦片代理、缓存、下载
├─ terrain_routes.py              # DEM terrain tile API
├─ terrain_provider.py            # DEM 切片实现
├─ data_loader.py                 # DataStore 兼容门面
├─ data_serializers.py            # DB row 到 legacy payload 映射
├─ data_admin_queries.py          # Admin 列表、邻近、导出、乡镇查询
├─ data_admin_stats.py            # Admin Dashboard 聚合统计
├─ survey_coverage.py             # 普查轨迹与村庄覆盖
└─ routers/
   ├─ admin.py                    # 管线、任务、上传处理
   ├─ admin_task_service.py       # 后台任务服务
   ├─ admin_relic_routes.py       # 文物 CRUD、审计、批量、导入导出
   ├─ relics.py                   # 主前端文物 API
   ├─ stats.py                    # 统计 API
   ├─ worklog.py                  # 工作日志 API
   ├─ survey_routes.py            # 普查路线 API
   ├─ boundaries.py               # 行政边界 API
   ├─ chat.py                     # AI 问答 API
   └─ crs.py                      # 坐标转换与检查 API
```

### React WebGIS

```text
platform/webgis-react/src/
├─ api/                           # axios client 与后端 API 封装
├─ components/                    # Header、Toolbar、Dashboard、InfoPanel 等
├─ map/                           # Cesium viewer、图层、点位、视口管理
├─ pages/                         # 登录、模型查看、PDF 查看
├─ stores/                        # Zustand 状态
├─ three/                         # three.js / 3D Tiles 模型查看器
├─ utils/                         # 字典、坐标、Markdown
├─ styles/
├─ App.tsx
└─ main.tsx
```

### Vue Admin

```text
platform/admin-vue/src/
├─ api/                           # 管理后台 API
├─ components/                    # 编辑弹窗、批量弹窗、任务抽屉等
├─ composables/
│  └─ useDashboard.ts             # Dashboard 逻辑
├─ layouts/
├─ router/
├─ stores/
├─ styles/
│  ├─ dashboard.css
│  ├─ relic-edit-dialog.css
│  ├─ relic-edit-dialog-global.css
│  ├─ relics.css
│  └─ index.css
└─ views/
   ├─ Dashboard.vue
   ├─ Pipeline.vue
   ├─ Relics.vue
   ├─ Audit.vue
   ├─ Import.vue
   └─ Login.vue
```

## 测试与构建

后端：

```powershell
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe platform\scripts\run_pipeline.py --list
.venv\Scripts\python.exe platform\scripts\run_pipeline.py --dry-run --skip 01 --skip 05
```

React WebGIS：

```powershell
cd platform\webgis-react
npm.cmd run type-check
npm.cmd run build
```

Vue Admin：

```powershell
cd platform\admin-vue
npm.cmd run typecheck
npm.cmd run build
```

CI 位于 `.github/workflows/ci.yml`，会在 push 和 pull request 时运行 Python 测试、React 类型检查/构建、Vue 类型检查/构建。

## 文档归类

```text
docs/
├─ README.md                      # 文档入口和分类
├─ architecture/
│  └─ v1.1-architecture.md         # 完整架构树和模块边界
├─ refactor/
│  └─ execution-log.md             # 本次重构执行记录
└─ releases/
   └─ v1.1.0.md                    # V1.1 发布说明
```

## 版本说明

V1.1.0 主要是架构调整，不是业务功能大改。它做了三件事：

1. 把后端入口、瓦片、DEM、后台任务、文物管理、数据查询和统计拆成清晰模块。
2. 把后台前端的大页面拆出 composable 和独立样式文件，降低单文件维护成本。
3. 把启动、测试、CI、发布文档整理成稳定流程。

仓库当前只保留两个根目录 BAT：

```text
start-backend.bat
start-frontend.bat
```

数据生成、构建和测试都改为通过脚本命令、前端 package scripts 或 Admin 管线工作台执行。

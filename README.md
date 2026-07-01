# 不可移动文物数字档案 WebGIS 平台

> 面向县区级文博单位的不可移动文物数字档案管理平台。
> 它把四普档案、空间地图、照片图纸、工作日志、行政边界、DEM 地形、三维模型和后台维护流程放在同一套系统里，尽量让“资料整理、地图展示、档案维护、统计分析、离线交付”都能在一个平台里完成。

当前版本：`V1.1.5`

---

## 项目简介

很多县区级文物档案并不是“缺系统”，而是资料分散在不同地方：DOCX 档案、Excel 工作日志、照片文件夹、图纸扫描件、行政边界、三维模型、地图点位，各自都有一套存放方式。日常查询、核对、更新和汇报时，需要在多个文件和软件之间来回切换。

这个平台的目标很直接：把这些资料整理成一套可以长期维护的数字档案库，并通过 WebGIS 的方式展示出来。

平台主要做三件事：

1. **把档案数据整理出来**
   通过 7 步数据管线，把 DOCX、照片、图纸、工作日志、行政边界等资料整理成结构化数据和 SQLite 数据库。

2. **把文物放到地图上管理**
   在 Cesium 地图中展示文物点位、范围、行政边界、地形、离线瓦片、三维模型，并支持按当前视口加载数据。

3. **把后续维护留在后台**
   管理后台支持文物编辑、批量操作、导入导出、审计日志、回收站和管线任务，不需要每次都回到原始文件里手工改。

---

## 适用场景

这个项目主要面向以下场景：

* 县区级不可移动文物档案数字化整理。
* 四普、三普、日常巡查、复核数据的汇总展示。
* 文物点位、行政边界、保护范围、照片图纸的统一管理。
* 内网或局域网部署，给文博单位、乡镇、外业人员使用。
* 数字大赛、项目汇报、演示展示和后续真实交付。

它不是一个单纯的地图 Demo，也不是只展示静态页面的作品。它更接近一套从数据整理到业务展示再到后台维护的完整 WebGIS 应用。

---

## 核心功能

### 1. WebGIS 主图

* 使用 React + Cesium 构建主地图。
* 支持在线 / 离线底图切换。
* 支持行政边界、文物点位、面域、地形和三维模型展示。
* 地图移动后只加载当前视口内的数据，适合较大数据量。
* 支持按类别、级别、年代、现状、乡镇等条件联动筛选。
* 支持瓦片下载、缓存统计和离线覆盖查看。

### 2. 文物档案详情

每处文物可以查看：

* 基本信息：名称、编号、类别、级别、年代、地址、乡镇等。
* 空间信息：经纬度、面域、周边文物、地图定位。
* 影像资料：照片、图纸、PDF。
* 三维资料：3D Tiles / 三维模型。
* 工作日志：外业记录、日期联动、日志 PDF。
* 简介和备注：用于快速了解文物情况。

### 3. 数据管线

平台内置 7 步数据处理流程：

| Step | 内容                | 主要产物                 |
| ---- | ----------------- | -------------------- |
| 01   | DOCX 档案转 Markdown | 结构化 Markdown         |
| 02   | Markdown 转数据集     | CSV / JSON / GeoJSON |
| 03   | 提取档案照片            | 照片文件和索引              |
| 04   | 提取档案图纸            | 图纸文件和索引              |
| 05   | 工作日志转 PDF         | 日志 PDF               |
| 06   | 行政边界处理            | WGS-84 GeoJSON       |
| 07   | 构建 SQLite 数据库     | `relics.db`          |

管线可以在命令行运行，也可以在 Vue 管理后台的“管线工作台”里手动触发。

### 4. 管理后台

后台使用 Vue 3 + Element Plus 构建，主要用于日常维护：

* Dashboard 总览。
* 文物列表、分页、搜索和筛选。
* 新增、编辑、软删除、恢复文物。
* 批量编辑、导入、导出。
* 审计日志和版本记录。
* 管线任务启动、日志查看和执行状态查看。
* 回收站、相邻文物查询、地图拾点回传。

### 5. 空间检索和全文检索

后端优先使用 SQLite：

* R-Tree：用于空间范围查询。
* FTS5：用于全文搜索。
* audit_log：记录后台写操作。
* version 字段：降低多人编辑时互相覆盖的风险。
* 软删除：避免误删后无法恢复。

如果没有 SQLite 数据库，系统可以回退到 JSON 只读数据，方便早期演示和调试。

### 6. 离线与内网交付

项目设计时考虑了县区级文博单位常见的内网环境：

* 支持 Windows 开发环境。
* 支持 Linux / 麒麟系统部署。
* 支持本地瓦片缓存。
* 支持本地 DEM 地形服务。
* 支持本地静态资源挂载。
* 支持将数据和产物放在 `data/` 目录下统一管理。

---

## 快速开始

### 环境要求

建议环境：

* Python 3.10+
* Node.js 18+
* npm
* Windows 10/11 或 Linux/麒麟

首次运行时，启动脚本会自动做几件事：

* 复制 `config.example.yaml` 为 `config.yaml`。
* 安装后端 Python 依赖。
* 安装两个前端的 npm 依赖。
* 创建 `data/` 目录骨架。
* 同时启动后端、React 主图和 Vue 后台。

### Windows 启动

在项目根目录运行：

```powershell
.\start-all.bat
```

也可以直接双击 `start-all.bat`。

### Linux / 麒麟启动

第一次需要给脚本执行权限：

```bash
chmod +x start-all.sh
```

然后运行：

```bash
./start-all.sh
```

### 启动后访问

| 应用              | 地址                       | 说明                   |
| --------------- | ------------------------ | -------------------- |
| React WebGIS 主图 | `http://127.0.0.1:5174/` | 地图、详情、统计、三维、AI、瓦片下载  |
| Vue 管理后台        | `http://127.0.0.1:5173/` | 数据维护、管线、CRUD、审计、导入导出 |
| FastAPI 后端      | `http://127.0.0.1:8000/` | API、瓦片代理、静态资源挂载      |

开发时通常看：

* 改主地图：打开 `5174`
* 改后台：打开 `5173`
* 看集成后的后端挂载页面：打开 `8000/app/` 或 `8000/admin-ui/`

---

## 登录说明

模板配置里默认关闭登录保护：

```yaml
server:
  enable_auth: false
  users:
    - username: "admin"
      password: "changeme"
```

在 `enable_auth: false` 时，登录接口会直接签发本地 session，方便开发和演示。

如果要让别人访问，或者准备部署到局域网，请务必修改：

```yaml
server:
  enable_auth: true
  users:
    - username: "admin"
      password: "请换成自己的强密码"
```

如果把后端监听地址改成 `0.0.0.0`，更要打开登录保护。

---

## 数据放在哪里

项目不会自带真实业务数据。真实档案、照片、图纸、日志、边界、DEM、三维模型都放在 `data/input/` 下面。

```text
data/
├─ input/
│  ├─ 01_archives/        # 四普档案 DOCX，可按乡镇分目录
│  ├─ 02_worklogs/        # 外业工作日志 Excel
│  ├─ 03_boundaries/      # 县、乡镇、村边界 SHP 或 GeoJSON
│  ├─ 04_dem/             # DEM GeoTIFF
│  └─ 05_models_3d/       # 三维模型或 3D Tiles
└─ output/
   ├─ markdown/           # DOCX 转出来的 Markdown
   ├─ dataset/            # CSV / JSON / GeoJSON / relics.db
   ├─ photos/             # 档案照片
   ├─ drawings/           # 档案图纸
   ├─ boundaries/         # WGS-84 行政边界
   ├─ terrain_cache/      # DEM terrain 缓存
   └─ logs/               # 管线和后台任务日志
```

`data/input/` 不提交到 Git。大体积缓存、瓦片、日志、模型产物也不提交。仓库只保留代码和必要目录骨架。

---

## 运行数据管线

命令行入口：

```powershell
.venv\Scripts\python.exe platform\scripts\run_pipeline.py
```

常用命令：

```powershell
# 查看管线步骤
.venv\Scripts\python.exe platform\scripts\run_pipeline.py --list

# 只检查输入和输出，不真正执行
.venv\Scripts\python.exe platform\scripts\run_pipeline.py --dry-run

# 跳过工作日志步骤
.venv\Scripts\python.exe platform\scripts\run_pipeline.py --skip 05

# 只运行第 07 步，重建 SQLite
.venv\Scripts\python.exe platform\scripts\run_pipeline.py --only 07
```

Linux / 麒麟下把 `.venv\Scripts\python.exe` 换成对应 Python：

```bash
python platform/scripts/run_pipeline.py --dry-run
```

管线完成后，会在：

```text
data/output/logs/pipeline_manifest.json
```

记录每一步的执行情况、输入输出状态、耗时和错误信息。

---

## 配置文件

主配置文件是：

```text
config.yaml
```

第一次启动会从 `config.example.yaml` 自动复制一份。

建议重点检查这些字段：

| 配置                           | 说明                   |
| ---------------------------- | -------------------- |
| `project.name`               | 县区简称，页面中常用           |
| `project.full_name`          | 平台完整名称               |
| `project.data_cutoff`        | 数据截止日期               |
| `geo.center`                 | 地图默认中心点              |
| `geo.bounds`                 | 项目范围、瓦片下载范围、DEM 裁剪范围 |
| `geo.source_crs`             | 档案点位源坐标系             |
| `geo.boundaries.*`           | 行政边界投影参数             |
| `administrative.county_name` | 县区名称                 |
| `administrative.townships`   | 乡镇列表                 |
| `features.*`                 | 三维、工作日志、DEM、AI 等功能开关 |
| `api.*`                      | AI、Cesium 等外部服务配置    |
| `server.*`                   | 后端端口、登录保护、账号密码       |
| `tiles.min_free_disk_mb`     | 瓦片下载最低剩余磁盘空间         |

敏感字段可以写成环境变量占位：

```yaml
api:
  siliconflow:
    key: "${SILICONFLOW_KEY}"
```

程序启动时会自动读取环境变量。

---

## 项目结构

```text
relics-platform-react/
├─ start-all.bat                  # Windows 一键启动
├─ start-all.sh                   # Linux / 麒麟一键启动
├─ start.py                       # 跨平台启动器
├─ config.example.yaml            # 配置模板
├─ VERSION
├─ requirements-dev.txt
├─ pytest.ini
├─ docs/
├─ tests/
└─ platform/
   ├─ scripts/                    # 7 步数据管线
   ├─ webgis/                     # FastAPI 后端
   ├─ webgis-react/               # React + Cesium 主前端
   ├─ admin-vue/                  # Vue 3 管理后台
   └─ tools/
```

后端核心模块：

```text
platform/webgis/
├─ main.py                        # FastAPI 组合入口
├─ serve.py                       # 后端启动入口
├─ tile_routes.py                 # 瓦片代理、缓存、下载
├─ terrain_routes.py              # DEM terrain API
├─ data_loader.py                 # DataStore 门面
├─ data_serializers.py            # DB row 序列化
├─ data_admin_queries.py          # Admin 查询
├─ data_admin_stats.py            # Admin 统计
├─ survey_coverage.py             # 普查轨迹与村庄覆盖
├─ web_security.py                # CORS 与会话安全
└─ routers/
   ├─ admin.py
   ├─ admin_task_service.py
   ├─ admin_relic_routes.py
   ├─ relics.py
   ├─ stats.py
   ├─ worklog.py
   ├─ survey_routes.py
   ├─ boundaries.py
   ├─ chat.py
   └─ crs.py
```

前端分工：

```text
platform/webgis-react/src/        # 面向使用者的主地图
platform/admin-vue/src/           # 面向维护者的管理后台
```

---

## 技术栈

### 后端

* FastAPI
* SQLite
* R-Tree
* FTS5
* HMAC-SHA256 session
* Python 数据管线脚本

### 主前端

* React 18
* Cesium
* Zustand
* three.js
* ECharts
* PDF.js

### 管理后台

* Vue 3
* Element Plus
* Pinia
* Vite

### 数据处理

* DOCX 转 Markdown
* CSV / JSON / GeoJSON 生成
* 图片和图纸抽取
* 工作日志转 PDF
* 行政边界转换
* SQLite 建库

---

## 测试与构建

后端测试：

```powershell
.venv\Scripts\python.exe -m pytest
```

管线检查：

```powershell
.venv\Scripts\python.exe platform\scripts\run_pipeline.py --list
.venv\Scripts\python.exe platform\scripts\run_pipeline.py --dry-run --skip 01 --skip 05
```

React 主前端：

```powershell
cd platform\webgis-react
npm.cmd run type-check
npm.cmd run build
```

Vue 管理后台：

```powershell
cd platform\admin-vue
npm.cmd run typecheck
npm.cmd run build
```

CI 配置在：

```text
.github/workflows/ci.yml
```

push 和 pull request 会跑 Python 测试、React 构建和 Vue 构建。

---

## 常见问题

### 1. 为什么启动后没有真实文物数据？

仓库不包含真实业务数据。需要把自己的 DOCX 档案、边界、日志、照片、图纸、DEM、模型等放进 `data/input/`，然后运行数据管线。

### 2. 后台登录一直 401 怎么办？

检查 `config.yaml`：

```yaml
server:
  enable_auth: false
```

如果是 `false`，登录接口会直接通过。
如果改成 `true`，就必须使用 `server.users` 中配置的用户名和密码。改完配置后要重启后端。

### 3. `8000`、`5173`、`5174` 怎么区分？

* `8000`：FastAPI 后端。
* `5173`：Vue 管理后台开发入口。
* `5174`：React WebGIS 主图开发入口。

日常演示一般打开 `5174`。做数据维护时打开 `5173`。

### 4. 下载瓦片时提示范围或 zoom 不合法？

瓦片下载有层级和范围保护。建议先缩小范围，再选择合理层级。当前层级一般建议控制在 `1..17`。

### 5. AI 问答没有反应？

检查：

* `features.enable_ai_chat` 是否开启。
* `api.siliconflow.key` 是否配置。
* 当前网络环境是否能访问对应 API。
* 如果是内网部署，可以先关闭 AI 功能，不影响地图和档案管理主流程。

---

## 文档入口

```text
docs/
├─ README.md
├─ architecture/v1.1-architecture.md
├─ refactor/execution-log.md
├─ refactor/v1.2-agent-plan.md
└─ releases/
   ├─ v1.1.0.md
   └─ v1.1.5.md
```

建议阅读顺序：

1. `README.md`：先跑起来。
2. `docs/architecture/v1.1-architecture.md`：看整体架构。
3. `docs/refactor/execution-log.md`：看已经做过哪些调整。
4. `docs/refactor/v1.2-agent-plan.md`：看后续重构计划。
5. `docs/releases/`：看版本变化。

---

## 当前状态

当前版本是 `V1.1.5`。

这个版本已经完成：

* 根目录启动入口收敛为 `start-all.bat` / `start-all.sh`。
* FastAPI 后端拆分出瓦片、DEM、Admin、文物管理等模块。
* React 主图和 Vue 后台分工稳定。
* 管线支持 dry-run 和 manifest。
* SQLite 支持空间索引、全文检索、审计和软删除。
* 后端测试、前端类型检查和生产构建已纳入 CI。

后续重点方向：

* 更完整的角色权限体系。
* 数据库迁移机制。
* 数据质量报告。
* 媒体资产管理。
* 离线工作包。
* AI 问答来源溯源。

---

## 一句话启动

如果只是想先跑起来，记住这一条就够了：

```powershell
.\start-all.bat
```

Linux / 麒麟：

```bash
./start-all.sh
```

然后打开：

```text
http://127.0.0.1:5174/
```

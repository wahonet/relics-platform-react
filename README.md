# 不可移动文物数字档案平台

当前版本：V1.1.0
发布类型：架构调整版

这是一个面向区县级不可移动文物普查、整理、展示和后台管理的 WebGIS 平台。V1.1.0 在 V1.0.0 的功能基础上做了架构拆分、测试补齐、CI/CD 接入和启动流程简化，目标是让后续开发更稳、更容易维护。

完整架构树和模块说明见 [docs/architecture/v1.1-architecture.md](docs/architecture/v1.1-architecture.md)。

## V1.1 更新重点

- 日常启动简化为两个入口：`start-backend.bat` 和 `start-frontend.bat`。
- 数据管线保留在脚本和 Admin 后台里手动触发，不再要求每天按顺序启动四个 BAT。
- FastAPI 入口、瓦片、DEM、Admin 任务、Admin 文物管理、数据查询和统计逻辑已按职责拆分。
- Pipeline 默认纳入 `step07_build_db.py`，支持 `--list`、`--dry-run`、`--skip`。
- Admin Vue 大文件完成第一轮拆分：Dashboard 逻辑进入 composable，多个大样式块进入独立 CSS。
- 新增 pytest 测试、`requirements-dev.txt`、`pytest.ini` 和 GitHub Actions CI。
- React Cesium 构建后处理脚本增强了 Windows 下的容错。

## 快速启动

第一次使用或依赖变化时，先执行：

```powershell
.\1-setup.bat
.\3-build.bat
```

日常开发只需要启动后端和前端：

```powershell
.\start-backend.bat
.\start-frontend.bat
```

默认访问地址：

- 主 WebGIS：`http://127.0.0.1:5174/`
- 管理后台：`http://127.0.0.1:5173/`
- 后端 API：`http://127.0.0.1:8000/`

如果要运行完整数据管线：

```powershell
.\2-pipeline.bat
```

也可以手动使用 orchestrator：

```powershell
.venv\Scripts\python.exe platform\scripts\run_pipeline.py --list
.venv\Scripts\python.exe platform\scripts\run_pipeline.py --dry-run
.venv\Scripts\python.exe platform\scripts\run_pipeline.py --skip 05
```

## 顶层架构

```text
relics-platform-react/
├─ start-backend.bat              # 日常后端入口
├─ start-frontend.bat             # 日常前端入口，启动 React WebGIS + Vue Admin
├─ 1-setup.bat                    # 初始化环境
├─ 2-pipeline.bat                 # 数据管线入口
├─ 3-build.bat                    # 前端生产构建
├─ 4-start.bat                    # 生产式后端启动
├─ platform/
│  ├─ scripts/                    # 7 步数据管线
│  ├─ webgis/                     # FastAPI 后端、静态挂载、legacy fallback
│  ├─ webgis-react/               # React + Cesium + three.js 主前端
│  ├─ admin-vue/                  # Vue 3 + Element Plus 管理后台
│  └─ tools/                      # 辅助工具
├─ tests/                         # pytest 单元测试
├─ docs/
│  ├─ architecture/               # V1.1 完整架构文档
│  ├─ refactor/                   # 每一步重构执行记录
│  └─ releases/                   # 版本发布说明
├─ .github/workflows/ci.yml       # CI
├─ requirements-dev.txt
├─ pytest.ini
└─ VERSION
```

## 后端模块

```text
platform/webgis/
├─ main.py                        # FastAPI 组合入口
├─ tile_routes.py                 # 瓦片代理、缓存、离线下载
├─ terrain_routes.py              # DEM terrain tile API
├─ terrain_provider.py            # DEM 到 Cesium terrain tile
├─ data_loader.py                 # DataStore 兼容门面
├─ data_serializers.py            # SQLite row 到 legacy payload 映射
├─ data_admin_queries.py          # Admin 列表、邻近、导出、乡镇查询
├─ data_admin_stats.py            # Admin Dashboard 聚合统计
├─ survey_coverage.py             # 普查轨迹与村庄覆盖率
└─ routers/
   ├─ admin.py                    # 管线、任务、上传处理
   ├─ admin_task_service.py       # 后台脚本任务服务
   ├─ admin_relic_routes.py       # Admin 文物 CRUD、审计、导入导出
   ├─ relics.py
   ├─ stats.py
   ├─ worklog.py
   ├─ survey_routes.py
   ├─ boundaries.py
   ├─ chat.py
   └─ crs.py
```

## 数据管线

```text
platform/scripts/
├─ run_pipeline.py
├─ step01_convert_docs.py
├─ step02_build_dataset.py
├─ step03_extract_photos.py
├─ step04_extract_drawings.py
├─ step05_convert_worklogs.py
├─ step06_prepare_boundaries.py
└─ step07_build_db.py
```

步骤说明：

1. `step01_convert_docs.py`：DOCX 转结构化 Markdown。
2. `step02_build_dataset.py`：Markdown 转 CSV、JSON、GeoJSON。
3. `step03_extract_photos.py`：提取档案内嵌照片。
4. `step04_extract_drawings.py`：提取档案内嵌图纸。
5. `step05_convert_worklogs.py`：工作日志 Excel 转 PDF。
6. `step06_prepare_boundaries.py`：行政边界转 WGS-84 GeoJSON。
7. `step07_build_db.py`：生成 SQLite `relics.db`，包含 R-Tree、FTS5 和审计表。

## 前端模块

React 主前端位于 `platform/webgis-react/`，负责主地图、筛选、详情、统计面板、三维模型和 PDF/图片查看等面向使用者的交互。

Vue 管理后台位于 `platform/admin-vue/`，负责 Dashboard、管线工作台、文物 CRUD、批量编辑、导入导出、审计和地图框选等后台操作。

V1.1 对 Admin Vue 做了如下拆分：

- `src/views/Dashboard.vue`：保留视图结构。
- `src/composables/useDashboard.ts`：承接 Dashboard 状态、加载、格式化和动作。
- `src/styles/dashboard.css`：承接 Dashboard 样式。
- `src/styles/relic-edit-dialog.css`：承接文物编辑弹窗作用域样式。
- `src/styles/relic-edit-dialog-global.css`：承接文物编辑弹窗全局覆盖样式。
- `src/styles/relics.css`：承接文物列表页样式。

## 测试

后端测试：

```powershell
.venv\Scripts\python.exe -m pytest
```

管线检查：

```powershell
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

## CI/CD

GitHub Actions 配置位于 `.github/workflows/ci.yml`，覆盖：

- Python 依赖安装和 pytest。
- React WebGIS 类型检查与生产构建。
- Vue Admin 类型检查与生产构建。

## 重构记录

每一步执行记录都在 `docs/refactor/` 下，主记录文件是 [docs/refactor/execution-log.md](docs/refactor/execution-log.md)。

V1.1 发布说明见 [docs/releases/v1.1.0.md](docs/releases/v1.1.0.md)。

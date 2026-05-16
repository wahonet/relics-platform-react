# Refactor Execution Log

本文件记录本轮架构重构的每一步执行结果。每完成一个阶段，都会追加对应记录，方便回看改动顺序、验证结果和下一步计划。

## 2026-05-16 Step 00 - Baseline

### 本步做了什么

- 检查工作区状态，确认开始前没有未提交改动。
- 统计仓库内较大的业务文件，确认优先拆分对象。
- 建立 `docs/refactor/` 文档目录。
- 新增基线审计文档 `docs/refactor/00-baseline.md`。

### 验证结果

- `git status --short` 输出为空，起始工作区干净。
- 已确认最大业务文件包括：
  - `platform/webgis/data_loader.py`
  - `platform/webgis/routers/admin.py`
  - `platform/webgis/main.py`
  - `platform/admin-vue/src/views/Dashboard.vue`
  - `platform/admin-vue/src/components/RelicEditDialog.vue`
  - `platform/admin-vue/src/views/Relics.vue`
  - `platform/webgis-react/src/components/TileDownloadPanel.tsx`

### 下一步做什么

- 简化日常启动脚本：新增前端、后端两个启动入口，保留初始化、构建和管线能力但不要求日常依次启动四个 bat。

## 2026-05-16 Step 01 - Runtime Scripts

### 本步做了什么

- 新增 `start-backend.bat`，作为日常后端启动入口。
- 新增 `start-frontend.bat`，作为日常前端启动入口，一次性拉起 Vue 后台和 React 主图两个 Vite dev server。
- 新增文档 `docs/refactor/01-runtime-scripts.md`。
- 保留原有 `1-setup.bat`、`2-pipeline.bat`、`3-build.bat`、`4-start.bat`，避免破坏兼容性。

### 验证结果

- 文件已创建。
- 暂未启动长期运行进程，等结构拆分完成后统一验证。

### 下一步做什么

- 拆分 FastAPI 入口，把 `main.py` 中的鉴权、静态挂载、瓦片、DEM 等职责分离到独立模块。

## 2026-05-16 Step 02 - FastAPI Entrypoint Split

### 本步做了什么

- 新增 `platform/webgis/tile_routes.py`，承接瓦片代理、离线瓦片下载、缓存统计和后台瓦片总览。
- 新增 `platform/webgis/terrain_routes.py`，承接 DEM terrain tile 路由。
- 重写 `platform/webgis/main.py` 为聚合入口，保留原有 URL 和静态挂载行为。
- 新增文档 `docs/refactor/02-backend-app-split.md`。

### 验证结果

- `python -m py_compile platform\webgis\main.py platform\webgis\tile_routes.py platform\webgis\terrain_routes.py` 通过。
- 直接导入 app 时当前环境缺少 `fastapi`，完整后端启动验证推迟到测试阶段统一处理。

### 下一步做什么

- 拆分 `routers/admin.py`，并把 `step07_build_db.py` 接入后台管线触发范围。

## 2026-05-16 Step 03 - Pipeline And Admin Task Service

### 本步做了什么

- 新增 `platform/webgis/routers/admin_task_service.py`，集中管理后台脚本注册、别名、任务状态、日志收集和并发保护。
- `platform/webgis/routers/admin.py` 改为委托任务服务执行脚本，并清理旧的不可达任务启动代码。
- `platform/scripts/run_pipeline.py` 默认纳入 `step07_build_db.py`，并补齐 `--skip` 参数。
- 后台 Pipeline 状态和详情增加 `step07_build_db`，支持手动生成 SQLite DB。
- 新增文档 `docs/refactor/03-pipeline-admin-tasks.md`。

### 验证结果

- `python -m py_compile platform\scripts\run_pipeline.py platform\webgis\routers\admin.py platform\webgis\routers\admin_task_service.py` 通过。

### 下一步做什么

- 增加 pytest、最小单元测试和 GitHub Actions CI，并执行完整验证。

## 2026-05-16 Step 04 - Tests, CI, And Verification

### 本步做了什么

- 新增 `requirements-dev.txt`、`pytest.ini` 和 `tests/`。
- 新增 GitHub Actions 工作流 `.github/workflows/ci.yml`。
- `platform/webgis/requirements.txt` 补充 `python-multipart`。
- `run_pipeline.py --dry-run` 改为不依赖 `config.yaml`。
- 创建本地 `.venv` 完成后端验证，并让 `start-backend.bat` 优先使用该虚拟环境。
- `.gitignore` 增加 `.venv/` 和 `.npm-cache/`。
- 新增文档 `docs/refactor/04-testing-ci.md`。

### 验证结果

- Python 编译通过。
- `.venv\Scripts\python.exe -m pytest` 通过：`6 passed`。
- `run_pipeline.py --list` 显示 01-07，包含 `step07_build_db.py`。
- `run_pipeline.py --dry-run --skip 01 --skip 05` 通过，且不要求 `config.yaml`。
- FastAPI app 导入成功，输出 `Relics Platform`。
- React WebGIS：`npm.cmd ci`、`npm.cmd run type-check`、`npm.cmd run build` 通过。
- Vue Admin：`npm.cmd ci`、`npm.cmd run typecheck`、`npm.cmd run build` 通过。

### 下一步做什么

- 继续拆 `data_loader.py`、`admin.py` 和 Vue 大页面，进一步降低单文件体积和业务耦合。

## 2026-05-16 Step 05 - Data Loader Helper Split

### 本步做了什么

- 新增 `platform/webgis/data_serializers.py`，承接 SQLite 行到旧前端字段结构的映射。
- 新增 `platform/webgis/survey_coverage.py`，承接普查路线解析和村村达覆盖计算。
- `platform/webgis/data_loader.py` 保留 `store` 外部接口，改为调用上述 helper 模块。
- 新增 `tests/test_data_helpers.py`。
- 新增文档 `docs/refactor/05-data-loader-helper-split.md`。

### 验证结果

- `.venv\Scripts\python.exe -m py_compile platform\webgis\data_loader.py platform\webgis\data_serializers.py platform\webgis\survey_coverage.py` 通过。
- `.venv\Scripts\python.exe -m pytest` 通过：`8 passed`。
- FastAPI app 导入成功，输出 `Relics Platform`。

### 下一步做什么

- 继续把 `data_loader.py` 中的 admin CRUD、批量操作、导入导出和统计 SQL 拆成 repository/service 模块。
- 继续把 `admin.py` 的文物 CRUD、导入导出、统计路由拆成 admin 子路由。

## 2026-05-16 Step 06 - Data Admin Query Split

### 本步做了什么

- 新增 `platform/webgis/data_admin_queries.py`，承接后台邻近查询、分页查询、导出迭代和乡镇列表。
- 新增 `platform/webgis/data_admin_stats.py`，承接后台 Dashboard 聚合统计和 legacy 统计。
- `platform/webgis/data_loader.py` 保留 `DataStore` 同名门面方法，外部 `store.*` 调用不变。
- 新增 `tests/test_data_admin_delegates.py`。
- `pytest.ini` 关闭本地 cacheprovider，避免缓存目录权限导致 warning。
- 新增文档 `docs/refactor/06-data-admin-query-split.md`。

### 验证结果

- `.venv\Scripts\python.exe -m py_compile platform\webgis\data_loader.py platform\webgis\data_admin_queries.py platform\webgis\data_admin_stats.py` 通过。
- `.venv\Scripts\python.exe -m pytest` 通过：`11 passed`。

### 下一步做什么

- 拆分 `platform/webgis/routers/admin.py` 中的文物 CRUD、导入导出、统计和审计路由。

## 2026-05-16 Step 07 - Admin Relic Router Split

### 本步做了什么

- 新增 `platform/webgis/routers/admin_relic_routes.py`。
- 将文物 CRUD、审计、Dashboard 统计、编码字典、后台文物列表、批量操作、导入导出迁入文物子 router。
- `platform/webgis/routers/admin.py` 保留 Pipeline、任务、DOCX 上传职责，并挂载 `admin_relic_routes.router`。
- 新增 `tests/test_admin_router_composition.py`，验证父 router 包含关键文物管理路径。
- 新增文档 `docs/refactor/07-admin-relic-router-split.md`。

### 验证结果

- Python 编译通过。
- `.venv\Scripts\python.exe -m pytest` 通过：`12 passed`。
- FastAPI app 导入成功，输出 `Relics Platform`。

### 下一步做什么

- 后端继续拆 Pipeline service / write repository。
- 前端继续拆 `Dashboard.vue`、`RelicEditDialog.vue`、`Relics.vue`。

## 2026-05-16 Step 08 - React Build Script Hardening

### 本步做了什么

- 修改 `platform/webgis-react/scripts/fix-cesium-path.mjs`。
- 保留原先 `dist/app/cesium -> dist/cesium` 的 rename 优先逻辑。
- 当 Windows 下 `renameSync()` 返回 `EPERM` 时，fallback 为递归复制再删除源目录。
- 新增文档 `docs/refactor/08-react-build-script-hardening.md`。

### 验证结果

- `npm.cmd run build` 在 `platform/webgis-react` 下通过。
- `npm.cmd run build` 在 `platform/admin-vue` 下通过。
- `.venv\Scripts\python.exe -m pytest` 通过：`12 passed`。
- React/Vue typecheck 均通过。

### 下一步做什么

- 继续拆前端大文件：`Dashboard.vue`、`RelicEditDialog.vue`、`Relics.vue`、`TileDownloadPanel.tsx`。

## 2026-05-16 Step 09 - Dashboard Frontend Split

### ??????
- ? `platform/admin-vue/src/views/Dashboard.vue` ?????????????????
- ?? `platform/admin-vue/src/composables/useDashboard.ts` ?? Dashboard ???????????????
- ?? `platform/admin-vue/src/styles/dashboard.css` ?? Dashboard ???

### ????
- `npm.cmd run typecheck` ? `platform/admin-vue` ????
- `npm.cmd run build` ? `platform/admin-vue` ????

### ??????
- ???? Admin Vue ?????????????????????

## 2026-05-16 Step 10 - Admin Vue Style Split

### ??????
- ? `RelicEditDialog.vue` ???????? `platform/admin-vue/src/styles/relic-edit-dialog.css`?
- ? `RelicEditDialog.vue` ??? Element Plus ?????? `platform/admin-vue/src/styles/relic-edit-dialog-global.css`?
- ? `Relics.vue` ???????? `platform/admin-vue/src/styles/relics.css`?
- ?????props?emit ????????

### ????
- `npm.cmd run typecheck` ? `platform/admin-vue` ????

### ??????
- ?? V1.1 ?????README??????????

## 2026-05-16 Step 11 - Version, README And Release Prep

### ??????
- ???????? `docs/architecture/v1.1-architecture.md`?
- ?????? `docs/releases/v1.1.0.md`?
- ????? `README.md`??? V1.1 ????????? CI?
- ? React WebGIS ? Vue Admin package ????? `1.1.0`?
- ????? `VERSION`?

### ????
- ????????????

### ??????
- ?? Python?React?Vue ????????????? `v1.1.0` tag?

## 2026-05-16 Final Verification

### ?????
- Python compile: passed.
- FastAPI import: passed, app title is `Relics Platform`.
- Pytest: `12 passed`.
- Pipeline list: passed, steps 01-07 are registered.
- Pipeline dry-run: passed with `--skip 01 --skip 05`.
- React WebGIS type-check: passed.
- React WebGIS production build: passed.
- Vue Admin typecheck: passed.
- Vue Admin production build: passed.
- Git diff whitespace check: passed.

### ????
- Local commit created.
- Local annotated tag `v1.1.0` created.
- GitHub push attempted but blocked by current network connectivity to `github.com:443`.

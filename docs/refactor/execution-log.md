# V1.1 架构调整执行记录

日期：2026-05-16

本文件保留这次 V1.1 架构调整的过程记录。清理后，原本分散的逐步文档已合并到这里，避免文档目录过度碎片化。

## Step 00 - 基线审计

### 做了什么

- 盘点项目入口、后端、前端、管线、测试和文档。
- 确认主要大文件集中在 FastAPI 入口、Admin router、DataStore、Vue Admin 页面和编辑弹窗。
- 确认旧工作流需要依次启动多个 BAT，日常开发成本偏高。

### 下一步

- 简化启动入口。
- 拆分后端大模块。
- 增加测试和 CI。

## Step 01 - 启动入口简化

### 做了什么

- 新增 `start-backend.bat`，作为后端唯一根目录启动入口。
- 新增 `start-frontend.bat`，一次启动 React WebGIS 和 Vue Admin 两个前端 dev server。
- 后续清理阶段删除旧编号 BAT，根目录最终只保留两个入口。

### 验证

- 脚本文件创建完成。
- 后续在最终验证中统一检查后端导入和前端构建。

## Step 02 - FastAPI 入口拆分

### 做了什么

- 新增 `platform/webgis/tile_routes.py`，承接瓦片代理、离线下载、缓存统计和后台瓦片概览。
- 新增 `platform/webgis/terrain_routes.py`，承接 DEM terrain tile API。
- `platform/webgis/main.py` 改为应用组合入口，保留原 URL 和静态挂载行为。

### 验证

- Python 编译通过。
- FastAPI app 后续导入验证通过，标题为 `Relics Platform`。

## Step 03 - 管线与后台任务服务

### 做了什么

- 新增 `platform/webgis/routers/admin_task_service.py`，集中管理后台脚本注册、别名、任务状态、日志和并发保护。
- `platform/webgis/routers/admin.py` 委托任务服务执行脚本。
- `platform/scripts/run_pipeline.py` 纳入 `step07_build_db.py`，支持 `--list`、`--dry-run`、`--skip`。
- Admin Pipeline 状态和详情增加 `step07_build_db`。

### 验证

- Python 编译通过。
- 管线 `--list` 和 `--dry-run` 在最终验证中通过。

## Step 04 - 测试与 CI

### 做了什么

- 新增 `requirements-dev.txt`、`pytest.ini` 和 `tests/`。
- 新增 GitHub Actions：`.github/workflows/ci.yml`。
- `platform/webgis/requirements.txt` 补充 `python-multipart`。
- `run_pipeline.py --dry-run` 改为不依赖 `config.yaml`。
- `.gitignore` 增加本地虚拟环境、npm cache、pytest cache 和构建产物规则。

### 验证

- pytest 最终验证为 `12 passed`。
- React 与 Vue 类型检查、生产构建均通过。

## Step 05 - DataStore helper 拆分

### 做了什么

- 新增 `platform/webgis/data_serializers.py`，承接 SQLite row 到 legacy payload 的映射。
- 新增 `platform/webgis/survey_coverage.py`，承接普查路线解析和村庄覆盖率计算。
- `platform/webgis/data_loader.py` 保留 `store` 外部接口，改为调用 helper 模块。
- 新增 `tests/test_data_helpers.py`。

### 验证

- Python 编译通过。
- pytest 通过。

## Step 06 - 后台查询与统计拆分

### 做了什么

- 新增 `platform/webgis/data_admin_queries.py`，承接后台分页、邻近查询、导出迭代和乡镇列表。
- 新增 `platform/webgis/data_admin_stats.py`，承接后台 Dashboard 聚合统计和 legacy 统计。
- `DataStore` 保留同名门面方法，外部 `store.*` 调用不变。
- 新增 `tests/test_data_admin_delegates.py`。

### 验证

- Python 编译通过。
- pytest 通过。

## Step 07 - Admin 文物路由拆分

### 做了什么

- 新增 `platform/webgis/routers/admin_relic_routes.py`。
- 将文物 CRUD、审计、Dashboard 统计、编码字典、后台文物列表、批量操作、导入导出迁入文物子 router。
- `platform/webgis/routers/admin.py` 保留 Pipeline、任务、DOCX 上传职责，并挂载 `admin_relic_routes.router`。
- 新增 `tests/test_admin_router_composition.py`。

### 验证

- Python 编译通过。
- pytest 通过。
- FastAPI app 导入成功。

## Step 08 - React 构建脚本加固

### 做了什么

- 修改 `platform/webgis-react/scripts/fix-cesium-path.mjs`。
- Windows 下 `renameSync()` 返回 `EPERM` 时，fallback 为递归复制后删除源目录。

### 验证

- React 生产构建通过。

## Step 09 - Admin Dashboard 拆分

### 做了什么

- `Dashboard.vue` 保留视图结构。
- 新增 `platform/admin-vue/src/composables/useDashboard.ts`，承接 Dashboard 状态、加载、格式化和动作。
- 新增 `platform/admin-vue/src/styles/dashboard.css`，承接 Dashboard 样式。

### 验证

- Vue typecheck 通过。
- Vue build 通过。

## Step 10 - Admin 样式拆分

### 做了什么

- `RelicEditDialog.vue` 的作用域样式抽到 `platform/admin-vue/src/styles/relic-edit-dialog.css`。
- `RelicEditDialog.vue` 的全局覆盖样式抽到 `platform/admin-vue/src/styles/relic-edit-dialog-global.css`。
- `Relics.vue` 的作用域样式抽到 `platform/admin-vue/src/styles/relics.css`。

### 验证

- Vue typecheck 通过。

## Step 11 - 版本、README 与发布准备

### 做了什么

- 新增 `VERSION`，版本为 `1.1.0`。
- React WebGIS 与 Vue Admin package 版本更新为 `1.1.0`。
- 新增 `docs/architecture/v1.1-architecture.md`。
- 新增 `docs/releases/v1.1.0.md`。
- 重写根目录 README。

### 验证

- Python、React、Vue 全量验证通过。
- 创建本地 commit 与 `v1.1.0` tag。
- 使用代理推送到 GitHub 成功。

## Step 12 - 仓库冗余清理

### 做了什么

- 删除根目录旧编号 BAT。
- 删除过期的子项目 README 和旧 quickstart。
- 将碎片化 step 文档合并为本执行日志。
- 新增 `docs/README.md` 作为文档索引。
- 重新扩写根目录 `README.md`。
- 更新 `.gitignore`、架构文档、发布说明和启动提示，移除旧入口引用。

### 下一步

- 运行 Python 与前端验证。
- 提交 cleanup commit 并推送到 GitHub。

## 最终验证结果

- Python compile：通过。
- FastAPI import：通过，app title 为 `Relics Platform`。
- Pytest：通过，`12 passed`。
- Pipeline `--list`：通过。
- Pipeline `--dry-run --skip 01 --skip 05`：通过。
- React type-check：通过。
- React production build：通过。
- Vue typecheck：通过。
- Vue production build：通过。
- Git diff whitespace check：通过。

## 2026-05-16 Step 13 - Startup Script Fix

### 做了什么

- 修复 `start-backend.bat` 中仍提示旧 `1-setup.bat` 的问题。
- 后端启动脚本在缺少 `config.yaml` 时自动从 `config.example.yaml` 复制一份。
- 后端启动脚本会确保 `data/` 目录骨架存在。
- 重写 `start-frontend.bat`，移除 `call :ensure_deps` 子程序，避免 Windows batch label 解析失败。
- 两个启动脚本增加 `RELICS_CHECK_ONLY=1` 预检模式，便于验证而不真正启动长驻服务。

### 验证

- `RELICS_CHECK_ONLY=1 cmd /c start-backend.bat`：通过。
- `RELICS_CHECK_ONLY=1 cmd /c start-frontend.bat`：通过。
- `git diff --check`：通过。

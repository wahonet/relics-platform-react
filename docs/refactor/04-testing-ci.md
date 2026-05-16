# Step 04 - Tests, CI, And Verification

## 本步做了什么
本步建立最小测试闭环，并把本地验证命令写入 CI。

主要改动：

- 新增 `requirements-dev.txt`，纳入 `pytest`。
- 新增 `pytest.ini`，配置测试目录和 Python import path。
- 新增 `tests/test_pipeline_orchestrator.py`，覆盖管线步骤、`--skip` 和 dry-run 不依赖 `config.yaml`。
- 新增 `tests/test_admin_task_service.py`，覆盖后台脚本别名和 `step07_build_db.py` 注册。
- 新增 `.github/workflows/ci.yml`，包含 backend、React WebGIS、Vue Admin 三个 job。
- `platform/webgis/requirements.txt` 补充 `python-multipart`，满足 FastAPI `UploadFile` / `Form` 路由依赖。
- `platform/scripts/run_pipeline.py --dry-run` 调整为不强制读取 `config.yaml`。
- `start-backend.bat` 优先使用项目内 `.venv\Scripts\python.exe`。
- `.gitignore` 增加 `.venv/` 和 `.npm-cache/`。

## CI 内容
Backend job：

- 安装后端运行依赖和开发测试依赖。
- 编译关键 Python 模块。
- 运行 pytest。

React WebGIS job：

- `npm ci`
- `npm run type-check`
- `npm run build`

Vue Admin job：

- `npm ci`
- `npm run typecheck`
- `npm run build`

## 本地验证结果
后端验证使用项目虚拟环境：

```bat
.venv\Scripts\python.exe -m py_compile platform\webgis\main.py platform\webgis\tile_routes.py platform\webgis\terrain_routes.py platform\webgis\routers\admin.py platform\webgis\routers\admin_task_service.py platform\scripts\run_pipeline.py
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe platform\scripts\run_pipeline.py --list
.venv\Scripts\python.exe platform\scripts\run_pipeline.py --dry-run --skip 01 --skip 05
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, r'platform\webgis'); import main; print(main.app.title)"
```

结果：

- Python 编译通过。
- pytest：`6 passed`。
- 管线列表显示 01-07，包含 `step07_build_db.py`。
- dry-run 通过，未要求 `config.yaml`。
- FastAPI app 导入成功，输出 `Relics Platform`。
- 导入时仅出现可接受的环境提示：缺少可选静态目录、前端 dist 尚未挂载、`boundaries.py` 有 FastAPI `regex` 参数弃用提醒。

前端验证：

```bat
npm.cmd ci
npm.cmd run type-check
npm.cmd run build
npm.cmd run typecheck
```

结果：

- React WebGIS：依赖安装、type-check、build 通过。
- Vue Admin：依赖安装、typecheck、build 通过。
- 在沙箱内直接跑 Vite build 时，esbuild 曾因读取 `../../..` 被拒绝；使用正常文件权限重跑后通过，说明不是源码构建错误。

## 下一步做什么
下一步继续拆更大的业务文件：

- 优先拆 `platform/webgis/data_loader.py`，把 DB 连接、JSON fallback、查询、CRUD、统计、审计分开。
- 继续拆 `platform/webgis/routers/admin.py`，把文物 CRUD、导入导出、统计和 Pipeline 路由分离。
- 前端侧再拆 `Dashboard.vue`、`RelicEditDialog.vue`、`Relics.vue` 的视图和组合逻辑。

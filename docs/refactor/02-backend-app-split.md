# Step 02 - FastAPI Entrypoint Split

## 本步做了什么

拆分 `platform/webgis/main.py` 的平台级职责。

新增模块：

- `platform/webgis/tile_routes.py`
- `platform/webgis/terrain_routes.py`

调整后：

- `main.py` 只负责：
  - 创建 FastAPI app。
  - 生命周期内加载配置、数据、DEM、AI chat。
  - 注册中间件和业务 router。
  - 注册瓦片/地形模块。
  - 挂载静态资源和前端构建产物。
  - 保留根路径、legacy、登录、模型/PDF 页面跳转。
- `tile_routes.py` 负责：
  - `/tiles/{provider}/{z}/{x}/{y}`
  - `/api/tiles/cache-status`
  - `/api/tiles/precache`
  - `/api/tiles/area-estimate`
  - `/api/tiles/download-area`
  - `/api/tiles/download-progress/{job_id}`
  - `/api/tiles/cache-info`
  - `/api/tiles/history`
  - `/api/admin/tiles/summary`
  - `/api/tiles/open-cache-folder`
  - `/api/tiles/clear-cache`
- `terrain_routes.py` 负责：
  - `/api/terrain/{level}/{x}/{y}`

## 保持不变的外部契约

- URL 路径保持不变。
- React 主前端和 Vue 后台的 API 调用无需修改。
- 旧版 `/legacy`、`/model-viewer`、`/pdf-viewer`、`/admin` 跳转行为保留。
- `serve.py` 仍然通过 `uvicorn.run("main:app", app_dir=...)` 启动。

## 验证结果

已执行：

```bat
python -m py_compile platform\webgis\main.py platform\webgis\tile_routes.py platform\webgis\terrain_routes.py
```

结果：通过。

尝试直接导入 app：

```bat
python -c "import sys; sys.path.insert(0, r'platform\webgis'); import main; print(main.app.title)"
```

结果：当前环境缺少 `fastapi`，无法做完整导入验证。后续测试阶段会统一安装/校验依赖并启动后端。

## 下一步做什么

下一步拆分后台管理大路由：

- 把 `routers/admin.py` 中的管线、任务、文物 CRUD、导入导出、审计、统计拆出到 admin 子模块。
- 同时补齐 `step07_build_db.py` 的后台触发入口，让“后台手动生成 DB”成为标准流程。


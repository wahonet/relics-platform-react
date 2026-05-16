# Step 07 - Admin Relic Router Split

## 本步做了什么
本步拆分 `platform/webgis/routers/admin.py` 中的文物管理路由。

新增模块：

- `platform/webgis/routers/admin_relic_routes.py`

`admin_relic_routes.py` 负责：

- 文物 CRUD。
- 审计列表和回滚。
- Dashboard 聚合统计入口。
- 编码字典。
- 后台文物列表、详情、邻近查询。
- 批量更新和批量状态变更。
- CSV 导出。
- CSV / JSON 导入。

`admin.py` 继续负责：

- Pipeline 状态和详情。
- Pipeline 脚本任务触发与任务日志。
- DOCX 单文件上传和即时处理。
- step items 明细。
- 挂载 `admin_relic_routes.router`，保持原 URL。

## 保持不变的外部接口
以下路径保持不变：

- `/api/admin/relics`
- `/api/admin/relics/{code}`
- `/api/admin/relics-export`
- `/api/admin/relics/import`
- `/api/admin/relics/bulk-update`
- `/api/admin/relics/bulk-status`
- `/api/admin/stats-overview`
- `/api/admin/audit`
- `/api/admin/codes`

## 文件体积变化
本步完成后：

- `platform/webgis/routers/admin.py`：约 591 行。
- `platform/webgis/routers/admin_relic_routes.py`：约 381 行。

拆分前本轮起点 `admin.py` 约 971 行。

## 测试
新增 `tests/test_admin_router_composition.py`：

- 验证父 router 已包含文物子 router 的关键路径。

## 验证结果
已执行：

```bat
.venv\Scripts\python.exe -m py_compile platform\webgis\main.py platform\webgis\routers\admin.py platform\webgis\routers\admin_relic_routes.py platform\webgis\routers\admin_task_service.py platform\webgis\data_loader.py platform\webgis\data_admin_queries.py platform\webgis\data_admin_stats.py
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, r'platform\webgis'); import main; print(main.app.title)"
```

结果：

- Python 编译通过。
- pytest：`12 passed`。
- FastAPI app 导入成功，输出 `Relics Platform`。

## 下一步做什么
下一步可以继续拆：

- `admin.py` 中 Pipeline 详情和 step items，可拆成 pipeline service。
- `data_loader.py` 中写入、审计、批量操作，可拆成 write repository。
- 前端 Vue 的 `Dashboard.vue`、`RelicEditDialog.vue`、`Relics.vue`。

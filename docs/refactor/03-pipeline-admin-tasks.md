# Step 03 - Pipeline And Admin Task Service

## 本步做了什么
本步把“后台任务执行”和“数据管线编排”从大路由中剥离出来，并补齐数据库构建步骤。

主要改动：

- 新增 `platform/webgis/routers/admin_task_service.py`。
- `platform/webgis/routers/admin.py` 改为调用任务服务，不再直接维护脚本启动、并发检查和日志收集逻辑。
- `run_pipeline.py` 默认步骤从 01-06 扩展为 01-07，包含 `step07_build_db.py`。
- `run_pipeline.py` 新增 `--skip` 参数，和 README 中已有说明保持一致。
- 后台 Pipeline 详情增加 `step07_build_db`，可在后台手动触发 SQLite DB 构建。
- 保留原有 `/admin/run/{script_name}`、`/admin/task/{task_id}`、`/admin/tasks` 等接口行为。

## 模块职责
`admin_task_service.py` 负责：

- 统一维护脚本注册表 `SCRIPTS`。
- 统一维护短别名 `SCRIPT_ALIAS`，例如 `build_db -> step07_build_db`。
- 维护后台任务内存状态 `tasks`。
- 执行脚本并保留最后 300 行日志。
- 防止同一个脚本并发重复运行。

`admin.py` 继续负责：

- 后台状态、Pipeline 进度、文件上传、文物 CRUD、导入导出和统计 API。
- 将脚本执行相关请求委托给 `admin_task_service.py`。
- 提供 `step07_build_db` 的产物状态检查。

`run_pipeline.py` 负责：

- 命令行编排 01-07 数据管线。
- 支持 `--from`、`--to`、`--only`、`--skip`、`--list`、`--dry-run`。

## 日常流程变化
新启动方式仍然只需要：

1. `start-backend.bat`
2. `start-frontend.bat`

数据管线不再要求随启动一起跑。用户把文件放入输入目录后，可以在后台 Pipeline 页面手动执行需要的步骤，包括最后的 `step07_build_db.py`。

## 验证结果
已执行：

```bat
python -m py_compile platform\scripts\run_pipeline.py platform\webgis\routers\admin.py platform\webgis\routers\admin_task_service.py
```

结果：通过。

后续还会在测试步骤中统一执行：

```bat
python -m pytest
python platform\scripts\run_pipeline.py --list
python platform\scripts\run_pipeline.py --dry-run --skip 01 --skip 05
```

## 下一步做什么
下一步建立最小测试闭环和 CI/CD：

- 增加 pytest 配置和后端单元测试。
- 增加 GitHub Actions CI。
- 校验后端导入、编译、测试、管线列表和 dry-run 行为。

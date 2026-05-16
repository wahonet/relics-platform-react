# Step 00 - Baseline Architecture Audit

## 本步做了什么

本步只做审计和记录，没有修改业务代码。

检查内容：

- 当前仓库工作区状态。
- 大文件和高复杂度模块。
- 前后端入口、构建脚本和运行脚本。
- 后端 API、数据层、管线、React 主图、Vue 后台的主要职责边界。

## 当前架构概览

项目目前由四个主要部分组成：

1. 数据管线：`platform/scripts/step01_*` 到 `step07_build_db.py` 负责把原始 DOCX、Excel、SHP、DEM、3D Tiles 处理成结构化数据和静态资产。
2. FastAPI 后端：`platform/webgis/main.py` 是统一入口，负责 API 路由、鉴权、瓦片代理、DEM、静态资源挂载、React/Vue 构建产物托管。
3. React 主前端：`platform/webgis-react` 提供主 WebGIS 界面，Cesium 负责地图，three.js 负责 3D Tiles 模型查看器，Zustand 管理状态。
4. Vue 管理后台：`platform/admin-vue` 提供管线工作台、文物 CRUD、导入导出、审计、Dashboard。

## 大文件清单

按业务风险和拆分收益排序，优先关注这些文件：

| 文件 | 当前职责 | 重构方向 |
|---|---|---|
| `platform/webgis/data_loader.py` | 数据加载、SQLite/JSON fallback、查询、CRUD、审计、统计 | 拆为 repository 门面、读模型、写模型、审计、统计、加载器 |
| `platform/webgis/routers/admin.py` | 后台管线、任务、上传、CRUD、导入导出、审计、统计 | 拆为 admin 子路由 |
| `platform/webgis/main.py` | FastAPI app、生命周期、鉴权、配置、瓦片、DEM、静态挂载、页面路由 | 拆为 app factory、runtime config、auth、static mounts、tiles、terrain |
| `platform/admin-vue/src/views/Dashboard.vue` | 后台首页和全部图表 | 拆图表组件和 chart composition |
| `platform/admin-vue/src/components/RelicEditDialog.vue` | 文物编辑全流程、mini map、邻近文物、审计摘要 | 拆成多个 tab 子组件 |
| `platform/admin-vue/src/views/Relics.vue` | 列表、筛选、批量操作、导出、弹窗协调 | 拆列表、筛选、批量操作 |
| `platform/webgis-react/src/components/TileDownloadPanel.tsx` | 离线瓦片表单、估算、任务轮询、历史 | 拆 API 状态 hook 和 UI 子组件 |

## 已发现的不一致

1. 文档描述 7 步管线，但 `run_pipeline.py` 当前只编排 01-06，`step07_build_db.py` 没有进入默认管线。
2. 后台 CRUD 依赖 SQLite DB；如果只跑 01-06，后台写入接口会返回 DB 未启用。
3. README 中部分瓦片接口名仍是旧名称，实际代码使用 `/api/tiles/download-area` 和 `/api/tiles/download-progress/{job_id}`。
4. README 提到 `--skip`，但 `run_pipeline.py` 当前没有实现该参数。

## 风险点

- `main.py` 职责过多，直接大拆容易影响启动和静态挂载。后续应先抽新模块，再由 `main.py` 聚合调用。
- `data_loader.py` 被多个路由直接调用，应保留 `from data_loader import store` 的兼容门面。
- Vue 后台与 React 主图通过 URL 参数和同源 API 联动，拆分前端组件时需要保持路由和 query 参数不变。
- 当前仓库没有测试和 CI，拆分前后必须增加最小测试闭环。

## 下一步做什么

下一步处理运行方式：

- 增加 `start-backend.bat`。
- 增加 `start-frontend.bat`。
- 保留 `1-setup.bat` 作为一次性初始化入口。
- 保留 `2-pipeline.bat` 作为命令行管线入口，但日常流程改为在后台 Pipeline 页面手动触发。
- 后续再让后台管线覆盖 DB 构建步骤。


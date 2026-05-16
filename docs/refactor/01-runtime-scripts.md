# Step 01 - Runtime Script Simplification

## 本步做了什么

新增两个日常启动脚本：

- `start-backend.bat`
- `start-frontend.bat`

调整后的日常启动方式：

1. 双击 `start-backend.bat` 启动 FastAPI 后端。
2. 双击 `start-frontend.bat` 同时启动 React 主前端和 Vue 管理后台开发服务器。

保留原脚本：

- `1-setup.bat`：一次性初始化、创建目录、生成 `config.yaml`、安装 Python 依赖。
- `2-pipeline.bat`：命令行运行数据管线，保留给高级用法。
- `3-build.bat`：生产构建两个前端。
- `4-start.bat`：兼容旧的一键后端启动方式。

## 新脚本职责

### `start-backend.bat`

- 检查 Python。
- 检查 `config.yaml`。
- 检查并安装后端基础依赖。
- 设置地图相关上游的 `NO_PROXY`。
- 调用 `platform\webgis\serve.py` 启动 FastAPI。

### `start-frontend.bat`

- 检查 npm。
- 分别检查 `platform/admin-vue` 和 `platform/webgis-react` 的前端依赖。
- 缺少依赖时自动执行对应目录的 `npm install`。
- 打开两个终端：
  - Vue 管理后台：`http://127.0.0.1:5173/`
  - React 主前端：`http://127.0.0.1:5174/`

## 设计决策

- 不把数据管线放在日常启动流程里。用户放入文件后，可以在后台 Pipeline 页面手动触发。
- 不删除原有 bat，避免破坏现有使用习惯和文档引用。
- 不强制生产构建。开发阶段前端走 Vite dev server，后端只负责 API 和静态资源。

## 验证结果

- 已新增脚本文件。
- 暂未实际启动 dev server，避免在重构过程中留下长期运行进程。
- 后续完成后会统一执行可用性验证。

## 下一步做什么

下一步开始拆分 FastAPI 入口：

- 将鉴权中间件和登录接口抽到独立模块。
- 将前端静态挂载和 HTML fallback 路由抽到独立模块。
- 将瓦片和 DEM 服务从 `main.py` 中拆出，降低入口文件体积。


# WebGIS React + three.js 主前端

本目录是 **不可移动文物数字档案平台** 的主前端,使用 React 18 + TypeScript + Vite 构建,与 FastAPI 后端共享同一套 API。

## 技术栈

| 模块 | 技术 |
|---|---|
| 框架 | React 18 + TypeScript |
| 构建 | Vite 5 |
| 状态管理 | Zustand |
| 地图 / 视口 | CesiumJS (通过 `vite-plugin-cesium` 集成) |
| 三维模型 | three.js + `@react-three/fiber` + `@react-three/drei` + `3d-tiles-renderer` |
| 数据可视化 | ECharts (`echarts-for-react`) |
| PDF 渲染 | pdf.js (`pdfjs-dist`) |
| HTTP | axios |

整个前端被划分为四类入口:
- **主图** (`/`):Cesium 场景 + 全部 UI 面板。
- **三维模型查看器** (`/#/model-viewer`):**纯 three.js**,通过 `3d-tiles-renderer` 在 r3f Canvas 中加载 Cesium 3D Tiles。
- **PDF 查看器** (`/#/pdf-viewer`):pdf.js 客户端渲染。
- **登录** (`/#/login`)。

## 目录结构

```
platform/webgis-react/
├── src/
│   ├── api/             # axios 客户端、按 router 拆分的 API 调用
│   │   ├── client.ts          axios 实例 + 401 拦截
│   │   ├── platform.ts        /api/platform/config + /api/login
│   │   ├── relics.ts          文物数据 (by-bbox / search / 详情 / 照片 / 图纸)
│   │   ├── chat.ts            AI 流式问答 (SSE)
│   │   ├── tiles.ts           离线瓦片下载/进度/历史
│   │   └── worklog.ts         工作日志
│   ├── components/
│   │   ├── Header.tsx         顶部栏,显示标题、平台统计、AI 入口、设置入口
│   │   ├── Toolbar.tsx        工具栏,底图下拉、边界菜单、地形开关、重置主视角
│   │   ├── FilterPanel.tsx    左侧筛选 + 搜索结果列表
│   │   ├── Dashboard.tsx      左侧仪表盘,9 维 ECharts,点图表追加统计筛选
│   │   ├── InfoPanel.tsx      右侧文物详情,基本/照片/图纸/简介四 Tab
│   │   ├── ChatPanel.tsx      AI 知识库问答 + 流式回答 + 地图联动链接
│   │   ├── WorklogPanel.tsx   工作日志查看器 + 内嵌 PDF 翻页
│   │   ├── SettingsPanel.tsx  主视角级联下拉 + 高清模式
│   │   ├── TileDownloadPanel.tsx 离线瓦片下载 + 历史
│   │   ├── Compass.tsx        罗盘 + 比例尺
│   │   ├── Lightbox.tsx       照片/图纸放大查看
│   │   └── Toast.tsx          全局 toast
│   ├── map/             # Cesium 主图
│   │   ├── MapView.tsx        Viewer 生命周期 + store 同步
│   │   ├── useCesiumViewer.ts Viewer 初始化 hook (2D 默认/锁倾斜/自定义滚轮)
│   │   ├── baseLayer.ts       底图切换 + 透明度
│   │   ├── terrain.ts         Ion / 本地 DEM 地形开关
│   │   ├── PointRenderer.ts   PointPrimitiveCollection 合批 + diff 更新
│   │   ├── ViewportManager.ts moveEnd debounce → /by-bbox + 32 格 LRU
│   │   ├── BoundaryLayer.ts   县/镇/村 边界 + 简化平滑 + 标签
│   │   └── viewerRegistry.ts  全局 viewer 注册,供其它组件读取
│   ├── three/           # three.js 三维模型查看器
│   │   └── ModelViewer.tsx    r3f Canvas + 3d-tiles-renderer + 测距
│   ├── pages/
│   │   ├── ModelViewerPage.tsx 三维模型独立页(顶栏 + ModelViewer)
│   │   ├── PdfViewerPage.tsx   PDF 独立页
│   │   └── LoginPage.tsx
│   ├── stores/          # Zustand 状态
│   │   ├── platformStore.ts   /api/platform/config 缓存
│   │   ├── relicsStore.ts     全量文物列表 + byCode Map
│   │   ├── filterStore.ts     筛选状态 + 翻译为 by-bbox 国标编码参数
│   │   ├── uiStore.ts         面板开闭、底图、边界、toast
│   │   └── homeViewStore.ts   主视角 (localStorage 持久化)
│   ├── utils/
│   │   ├── dict.ts            国标编码字典 (与 codes.py 一一对应)
│   │   └── markdown.ts        AI 回答 Markdown + [[label|action]] 链接
│   ├── types.ts         共享 TS 类型
│   ├── env.d.ts         全局 PlatformConfig 接口
│   ├── App.tsx          主图页面装配
│   ├── main.tsx         入口 + HashRouter
│   └── styles/globals.css 全局样式 (深色主题)
├── scripts/
│   └── fix-cesium-path.mjs    构建后把 dist/app/cesium/ 重命名为 dist/cesium/
├── index.html
├── tsconfig.json
├── vite.config.ts
└── package.json
```

## 开发

```bash
cd platform/webgis-react
npm install
npm run dev              # 启动 Vite dev server, http://127.0.0.1:5174/
```

`vite.config.ts` 已经把 `/api`、`/tiles`、`/photos`、`/drawings`、`/boundaries`、`/worklog-pdfs`、`/3d`、`/pdfs`、`/static` 等路径反代到 FastAPI (`http://127.0.0.1:8000`),日常改 UI 不用重新 build。

## 生产构建

```bash
npm run build            # tsc + vite build + post-fix cesium 路径
```

产物输出到 `dist/`,FastAPI 启动时会自动挂载到 `/app/`。访问 `http://127.0.0.1:8000/` 会 302 到 `/app/`。

> 在仓库根目录运行 `build_webgis.bat` 是等价的 (会自动检查依赖、调用 `npm install` 和 `npm run build`)。

## 与后端的契约

主前端只依赖以下后端约定,具体接口见 `../webgis/main.py` 与 `../webgis/routers/*.py`:

- `GET /api/platform/config` — 项目元信息 + 特性开关 + Cesium Ion token
- `GET /api/relics` — 全量摘要列表(供筛选下拉、AI 上下文使用)
- `GET /api/relics/by-bbox` — 视口查询,极简 8 字段
- `GET /api/relics/search?q=` — FTS5 全文搜索
- `GET /api/relics/{code}` / `/photos` / `/drawings` / `/polygon` — 详情
- `GET /api/chat/models` + `POST /api/chat` — AI 流式问答
- `GET /api/worklog/dates` — 工作日志日期列表
- `GET /tiles/{provider}/{z}/{x}/{y}` + `/api/tiles/*` — 底图代理 + 离线下载

对于 Cesium Ion token,后端会通过 `_bootstrap_script` 注入到老版 HTML 的 `window.__PLATFORM_CONFIG`;React 端在没有这个全局时会 fallback 到 `/api/platform/config` 重新拉一次,两条路径都能跑通。

## 与老版 Vanilla 前端的兼容

- 通过 `/legacy` 仍然可以访问老版 Cesium 页面,作回归对比用。
- 主图和三维模型页支持 hash 参数: `/#/model-viewer?folder=xxx&name=xxx&lat=&lng=&alt=`。
- 后台 (`/admin-ui/`) 是单独的 Vue 3 项目,本次重构不动。

# Relics Admin Vue

基于 Vue 3 + TypeScript + Vite + Element Plus 的后台管理系统。

## 快速开始

```bash
# 1. 安装依赖
cd platform/admin-vue
npm install

# 2. 启动 FastAPI 后端（另一个终端）
cd ../webgis
python serve.py         # http://127.0.0.1:8000

# 3. 启动 Vue 开发服务器
npm run dev             # 打开 http://127.0.0.1:5173/ （注意：开发期不带 /admin-ui/ 前缀！）
```

Vite 已配好代理，`/api` `/admin/` `/tiles` `/static` 都会转到 FastAPI，
登录用的 httponly cookie 同源共享，开发期无需关心 CORS。

> 开发期访问根路径 `/` 即可，`base` 仅在生产构建时设为 `/admin-ui/`，
> 这样 `/admin-ui/` 这类 URL 就不会被代理到 FastAPI 而返回 404。

## 生产构建

```bash
npm run build           # 产出 dist/
```

构建后由 FastAPI 挂载到 `/admin-ui/` 路径，方法见 `platform/webgis/main.py` 中
`StaticFiles` 的挂载（搜索 `admin-ui`）。

## 目录结构

```
src/
├── main.ts             入口，Element Plus、Pinia、Router 装配
├── App.vue             根组件
├── api/                HTTP 封装
│   ├── http.ts         axios 实例 + 统一拦截器（401 跳登录）
│   ├── auth.ts         /api/login
│   └── admin.ts        /admin/* 所有接口
├── stores/             Pinia store
│   └── auth.ts         登录态
├── router/             路由定义 + 权限守卫
├── layouts/
│   └── AppLayout.vue   主框架（侧边栏 + 顶栏）
├── views/              页面
│   ├── Login.vue
│   ├── Dashboard.vue
│   ├── Pipeline.vue    数据管线工作台（Phase 2 会填肉）
│   ├── Relics.vue      文物数据管理（Phase 3）
│   ├── Import.vue      批量导入（Phase 3）
│   └── Audit.vue       审计日志（Phase 3）
└── styles/
    └── index.css       全局主题变量（对齐主地图的深色风格）
```

## 约定

- 所有 HTTP 走 `@/api/http`，不要在组件里直接 `axios`
- 业务接口集中到 `@/api/admin.ts`，组件只看到语义化方法
- 组件文件统一 PascalCase；页面用 `<script setup lang="ts">`
- 主题色沿用主地图的 `#0d1117 / #58a6ff`，保持品牌一致

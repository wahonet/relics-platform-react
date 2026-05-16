# Step 08 - React Build Script Hardening

## 本步做了什么
本步修复 React WebGIS 生产构建脚本的幂等性问题。

`platform/webgis-react/scripts/fix-cesium-path.mjs` 原本在构建后执行：

- `dist/app/cesium` → `dist/cesium`

在 Windows 下重复构建时，`renameSync()` 偶发返回 `EPERM`。本步改为：

- 优先 `renameSync()`。
- 如果 rename 失败，则 fallback 到 `cpSync(..., { recursive: true })`。
- 复制成功后删除旧的 `dist/app/cesium`。
- 继续清理空的 `dist/app` 目录。

## 为什么这样做
该脚本属于构建后路径修正逻辑。生产构建可能被本地重复执行，也会在 CI/CD 中重复执行，因此脚本需要幂等、可重入，并且要兼容 Windows 文件系统偶发 rename 限制。

## 验证结果
已执行：

```bat
npm.cmd run build
```

位置：

```text
platform/webgis-react
```

结果：

- Vite build 通过。
- `fix-cesium-path.mjs` 在 rename 失败时 fallback 到 copy。
- 构建最终成功。

## 下一步做什么
下一步继续前端大文件拆分：

- `platform/admin-vue/src/views/Dashboard.vue`
- `platform/admin-vue/src/components/RelicEditDialog.vue`
- `platform/admin-vue/src/views/Relics.vue`
- `platform/webgis-react/src/components/TileDownloadPanel.tsx`

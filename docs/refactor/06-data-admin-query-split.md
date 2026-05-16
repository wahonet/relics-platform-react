# Step 06 - Data Admin Query Split

## 本步做了什么
本步继续拆 `platform/webgis/data_loader.py` 中的后台查询和统计职责。

新增模块：

- `platform/webgis/data_admin_queries.py`
- `platform/webgis/data_admin_stats.py`

`data_admin_queries.py` 负责：

- 后台邻近文物查询。
- 后台文物分页查询。
- JSON fallback 分页查询。
- CSV 导出数据迭代。
- 后台乡镇下拉列表。

`data_admin_stats.py` 负责：

- 后台 Dashboard 聚合统计。
- JSON fallback 统计。
- 审计近 14 天趋势和最近审计记录聚合。

`DataStore` 保留同名方法作为稳定门面：

- `store.admin_neighbors(...)`
- `store.admin_list_relics(...)`
- `store.admin_export_relics(...)`
- `store.admin_stats_overview()`
- `store.admin_list_townships()`

## 文件体积变化
本步完成后：

- `platform/webgis/data_loader.py`：约 921 行。
- `platform/webgis/data_admin_queries.py`：约 337 行。
- `platform/webgis/data_admin_stats.py`：约 196 行。

拆分前本轮起点 `data_loader.py` 约 1367 行。

## 测试
新增 `tests/test_data_admin_delegates.py`：

- 验证 DB 未启用时后台列表走 legacy delegate。
- 验证导出迭代走 legacy delegate。
- 验证 Dashboard 统计走 legacy delegate。

## 验证结果
已执行：

```bat
.venv\Scripts\python.exe -m py_compile platform\webgis\data_loader.py platform\webgis\data_admin_queries.py platform\webgis\data_admin_stats.py
.venv\Scripts\python.exe -m pytest
```

结果：

- Python 编译通过。
- pytest：`11 passed`，随后关闭 pytest cache 后为干净输出。

## 下一步做什么
下一步拆 `platform/webgis/routers/admin.py`：

- 把文物 CRUD、审计、统计、批量、导入导出拆到独立 admin 子 router。
- 保持 `/api/admin/*` 外部路径不变。

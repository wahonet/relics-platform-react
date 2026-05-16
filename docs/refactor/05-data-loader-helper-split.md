# Step 05 - Data Loader Helper Split

## 本步做了什么
本步继续拆 `platform/webgis/data_loader.py`，优先抽出纯工具逻辑，避免改变 `store` 对外接口。

新增模块：

- `platform/webgis/data_serializers.py`
- `platform/webgis/survey_coverage.py`

`data_serializers.py` 负责：

- 将 SQLite `relics` 行映射回旧前端字段结构。
- 保持 `archive_code`、`category_main`、`heritage_level`、`center_lng` 等兼容字段不变。

`survey_coverage.py` 负责：

- 解析普查 GPS CSV。
- 归一化日期和时间。
- 按项目范围过滤越界点。
- 计算“村村达”覆盖结果。

`data_loader.py` 现在只保留包装调用：

- `_load_survey_routes()` 调用 `load_survey_routes()`。
- `_compute_village_coverage()` 调用 `compute_village_coverage()`。
- DB 行映射调用 `row_to_legacy()`。

## 保持不变的外部接口
以下外部调用保持不变：

- `from data_loader import store`
- `store.load(...)`
- `store.survey_routes`
- `store.village_coverage`
- `store.get_relic_full(...)`
- `store.query_bbox(...)`
- 后台和主前端读取的旧字段名。

## 测试
新增 `tests/test_data_helpers.py`：

- 覆盖 DB 行到旧字段结构的映射。
- 覆盖普查路线日期、时间归一化和范围过滤。

## 验证结果
已执行：

```bat
.venv\Scripts\python.exe -m py_compile platform\webgis\data_loader.py platform\webgis\data_serializers.py platform\webgis\survey_coverage.py
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, r'platform\webgis'); import main; print(main.app.title)"
```

结果：

- Python 编译通过。
- pytest：`8 passed`。
- FastAPI app 导入成功，输出 `Relics Platform`。

## 下一步做什么
下一步继续拆更重的写入和后台查询职责：

- 把 `data_loader.py` 中的 admin CRUD、批量操作、导入导出和统计 SQL 继续拆到 repository/service 模块。
- 把 `admin.py` 的文物 CRUD、导入导出、统计路由拆成 admin 子路由。

"""step02 坐标表解析回归测试(P0-03)。

真实四普坐标行常带空的“分组/备注”单元格。旧实现用
`[c for c in cols if c != '']` 删掉所有空单元格,导致 测点类型/纬度/经度 左移错位
或整行被跳过,最终中心点缺失、坐标静默错误。
"""
from __future__ import annotations

import step02_build_dataset as step02


def _identity(lng, lat):
    return lng, lat


def test_parse_coordinates_preserves_empty_middle_cell():
    """空的“分组”列必须保留,中心点才能正确解析到 35.4 / 116.5。"""
    md = (
        "# 某文物\n\n"
        "## 坐标数据\n\n"
        "| 序号 | 分组 | 测点类型 | 纬度 | 经度 | 海拔 | 说明 | 备注 |\n"
        "|---|---|---|---|---|---|---|---|\n"
        "| 1 |  | 中心点 | 35°24′00.0″ | 116°30′00.0″ | 29.3 |  |  |\n"
    )
    res = step02.parse_coordinates(md, _identity)

    # 35°24′00″ = 35.4;116°30′00″ = 116.5
    assert res["center_lat"] is not None
    assert res["center_lng"] is not None
    assert abs(res["center_lat"] - 35.4) < 1e-6
    assert abs(res["center_lng"] - 116.5) < 1e-6
    assert res["center_alt"] == 29.3


def test_parse_md_table_row_keeps_inner_empties():
    """单元格拆分:只去首尾边框,中间空单元格保留为 ''。"""
    cols = step02._parse_md_table_row("| 1 |  | 中心点 | 35° | 116° | 29.3 |  |  |")
    assert cols == ["1", "", "中心点", "35°", "116°", "29.3", "", ""]


def test_parse_coordinates_no_section_returns_empty():
    res = step02.parse_coordinates("# 某文物\n\n## 简介\n\n无坐标\n", _identity)
    assert res["center_lat"] is None
    assert res["boundary_points"] == []

"""编码字典单源一致性守护(P2)。

后端 `platform/scripts/codes.py` 是国标/四普编码的**唯一真源**。前端存在两份
手写副本(各自附带颜色/图标/尺寸等展示信息,这些不属于 codes.py):
    - 旧版:    platform/webgis/static/js/dict.js
    - React:   platform/webgis-react/src/utils/dict.ts
(Vue 后台 platform/admin-vue/src/stores/dict.ts 已经改为从 /api/admin/codes 拉取,
 天然单源,无需守护。)

本测试解析那两份前端字典,断言其 code→label 与中文别名同 codes.py 一致;
任何一边漂移都会让 CI 失败,从而把"手工双源同步"变成可强制执行的约束,
而无需在此环境跑前端构建。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from codes import (
    CATEGORY_CODES,
    RANK_CODES,
    SEARCH_TYPE_CODES,
    normalize_category,
    normalize_rank,
)

_ROOT = Path(__file__).resolve().parents[1]
_DICT_JS = _ROOT / "platform" / "webgis" / "static" / "js" / "dict.js"
_DICT_TS = _ROOT / "platform" / "webgis-react" / "src" / "utils" / "dict.ts"
_ADMIN_DICT_TS = _ROOT / "platform" / "admin-vue" / "src" / "stores" / "dict.ts"


def _block(src: str, name: str) -> str:
    """取出 `name ... = { ... }` 的大括号内文本(花括号配平)。

    锚定到赋值号 `=` 后的 `{`,避免被类型注解里的内联花括号
    (如 React 的 `SEARCH_TYPE_MAP: Record<string, { label: string }> = {`)带偏。
    """
    m = re.search(re.escape(name) + r"[^\n=]*=\s*\{", src)
    assert m, f"未在源码中找到对象 {name}"
    start = m.end() - 1  # 赋值号后那个真正的 '{'
    depth = 0
    for i in range(start, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start + 1 : i]
    raise AssertionError(f"{name} 花括号未配平")


def _labels(block: str) -> dict[str, str]:
    """从 `'0100': { label: '古遗址', ... }` 形态提取 code→label(兼容单双引号、跨行)。"""
    out: dict[str, str] = {}
    for code, label in re.findall(
        r"""["'](\d+)["']\s*:\s*\{\s*label\s*:\s*["']([^"']+)["']""", block
    ):
        out[code] = label
    return out


def _aliases(block: str) -> dict[str, str]:
    """从 `'古遗址': '0100'`(dict.js)或 `古遗址: "0100"`(dict.ts)提取 中文→code。"""
    out: dict[str, str] = {}
    for zh, code in re.findall(
        r"""["']?([一-龥]+)["']?\s*:\s*["'](\d+)["']""", block
    ):
        out[zh] = code
    return out


@pytest.mark.parametrize("path", [_DICT_JS, _DICT_TS], ids=["dict.js", "react/dict.ts"])
def test_frontend_labels_match_codes_py(path: Path):
    src = path.read_text(encoding="utf-8")

    assert _labels(_block(src, "CATEGORY_MAP")) == CATEGORY_CODES
    assert _labels(_block(src, "RANK_MAP")) == RANK_CODES
    assert _labels(_block(src, "SEARCH_TYPE_MAP")) == SEARCH_TYPE_CODES


@pytest.mark.parametrize("path", [_DICT_JS, _DICT_TS], ids=["dict.js", "react/dict.ts"])
def test_frontend_aliases_resolve_consistently(path: Path):
    """前端的每个中文别名,用后端 normalize_* 解析应得到同一个 code。

    前端别名是 codes.py 的子集即可(后端别名更全),但凡出现必须一致。
    """
    src = path.read_text(encoding="utf-8")

    for zh, code in _aliases(_block(src, "CATEGORY_ALIAS")).items():
        assert normalize_category(zh) == code, f"类别别名漂移: {zh} 前端={code} 后端={normalize_category(zh)}"

    for zh, code in _aliases(_block(src, "RANK_ALIAS")).items():
        assert normalize_rank(zh) == code, f"级别别名漂移: {zh} 前端={code} 后端={normalize_rank(zh)}"


def test_admin_vue_dict_is_api_sourced_not_hardcoded():
    """Vue 后台字典应保持从 /api/admin/codes 拉取(单源),而非硬编码 label 表。"""
    src = _ADMIN_DICT_TS.read_text(encoding="utf-8")
    assert "/api/admin/codes" in src or "adminApi.codes" in src
    # 不应出现硬编码的 code→label 字面量(用 0300→古建筑 作探针)。
    assert "古建筑" not in src

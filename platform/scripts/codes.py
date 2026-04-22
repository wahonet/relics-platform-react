"""国标 / 四普 编码字典。

职责：在 step07 灌库、import_relics 导入、以及运行时 API 响应之间，
提供中文字符串 ↔ 国标编码的统一映射。新数据应以"编码"为准，
原有中文字符串通过 `normalize_*` 在边界处完成一次性映射。

与前端 `platform/webgis/static/js/dict.js` 保持一致，
若要调整映射关系，两处必须同步修改。
"""
from __future__ import annotations

from typing import Optional

# ── 文物大类（GB/T 15420-1994 核心码，四普沿用） ──────────────
# 最终落库字段 `relics.category` 只存 4 位编码字符串。
CATEGORY_CODES: dict[str, str] = {
    "0100": "古遗址",
    "0200": "古墓葬",
    "0300": "古建筑",
    "0400": "石窟寺及石刻",
    "0500": "近现代重要史迹及代表性建筑",
    "0600": "其他",
}

# 中文 → 编码（反向表，含常见别名），灌库/导入时容错用。
CATEGORY_ALIASES: dict[str, str] = {
    "古遗址": "0100",
    "古文化遗址": "0100",
    "遗址": "0100",
    "古墓葬": "0200",
    "墓葬": "0200",
    "古建筑": "0300",
    "古建": "0300",
    "石窟寺及石刻": "0400",
    "石窟寺": "0400",
    "石刻": "0400",
    "近现代重要史迹及代表性建筑": "0500",
    "近现代史迹": "0500",
    "近现代史迹及代表性建筑": "0500",
    "近现代": "0500",
    "其他": "0600",
}


# ── 文物保护级别 ─────────────────────────────────────────────
# `relics.rank` 落库为单字符："1"..."5"。
RANK_CODES: dict[str, str] = {
    "1": "全国重点文物保护单位",
    "2": "省级文物保护单位",
    "3": "市级文物保护单位",
    "4": "县级文物保护单位",
    "5": "尚未核定公布为文物保护单位的不可移动文物",
}

# 常见中文表述 → 编码
RANK_ALIASES: dict[str, str] = {
    "全国重点文物保护单位": "1",
    "国保": "1",
    "国家级": "1",
    "省级文物保护单位": "2",
    "省保": "2",
    "省级": "2",
    "市级文物保护单位": "3",
    "市保": "3",
    "市级": "3",
    "县级文物保护单位": "4",
    "县保": "4",
    "县级": "4",
    "尚未核定公布为文物保护单位的不可移动文物": "5",
    "未核定": "5",
    "未认定": "5",
    "未定级": "5",
    "未公布": "5",
}


# ── 普查来源类型（四普使用） ────────────────────────────────
# 与资源地图 getRelicPhoto 的 searchType 保持一致。
SEARCH_TYPE_CODES: dict[str, str] = {
    "2": "三普在册",
    "12": "县级以上公布",
    "110301": "四普新增",
}

SEARCH_TYPE_ALIASES: dict[str, str] = {
    "三普": "2",
    "三普在册": "2",
    "复查": "2",
    "县级以上公布": "12",
    "县级以上": "12",
    "四普新增": "110301",
    "新发现": "110301",
    "新登记": "110301",
}


# ── 规范化入口 ───────────────────────────────────────────────
def normalize_category(value: Optional[str]) -> str:
    """中文字符串或编码 → 4 位编码。空值或无法识别的返回 '0600'。"""
    if not value:
        return "0600"
    v = str(value).strip()
    if v in CATEGORY_CODES:
        return v
    if v in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[v]
    for zh, code in CATEGORY_ALIASES.items():
        if zh and zh in v:
            return code
    return "0600"


def normalize_rank(value: Optional[str]) -> str:
    """中文级别 → '1'..'5'。空值或无法识别的按未定级处理。"""
    if not value:
        return "5"
    v = str(value).strip()
    if v in RANK_CODES:
        return v
    if v in RANK_ALIASES:
        return RANK_ALIASES[v]
    for zh, code in RANK_ALIASES.items():
        if zh and zh in v:
            return code
    return "5"


def normalize_search_type(value: Optional[str]) -> str:
    """普查来源 → 编码。默认按'三普在册'处理。"""
    if not value:
        return "2"
    v = str(value).strip()
    if v in SEARCH_TYPE_CODES:
        return v
    if v in SEARCH_TYPE_ALIASES:
        return SEARCH_TYPE_ALIASES[v]
    for zh, code in SEARCH_TYPE_ALIASES.items():
        if zh and zh in v:
            return code
    return "2"


# ── 坐标规范化 ───────────────────────────────────────────────
def parse_coord(value) -> Optional[float]:
    """坐标字段容错解析：
    - 十进制字符串 "116.3426" / float "116.3426" → 116.3426
    - 度分秒字符串 "116-18-1.7064" 或 "116°18'1.7064\""      → 十进制
    - 空/无法解析 → None
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    s = str(value).strip()
    if not s:
        return None

    # 尝试直接当十进制解析
    try:
        return float(s)
    except ValueError:
        pass

    # 度分秒：支持 - / ° ' " 等多种分隔
    import re
    parts = re.split(r"[-°'′\"″\s]+", s)
    parts = [p for p in parts if p]
    if not parts:
        return None

    try:
        nums = [float(p) for p in parts[:3]]
    except ValueError:
        return None

    deg = nums[0]
    minute = nums[1] if len(nums) > 1 else 0.0
    sec = nums[2] if len(nums) > 2 else 0.0
    sign = -1.0 if deg < 0 else 1.0
    return sign * (abs(deg) + minute / 60.0 + sec / 3600.0)


__all__ = [
    "CATEGORY_CODES",
    "CATEGORY_ALIASES",
    "RANK_CODES",
    "RANK_ALIASES",
    "SEARCH_TYPE_CODES",
    "SEARCH_TYPE_ALIASES",
    "normalize_category",
    "normalize_rank",
    "normalize_search_type",
    "parse_coord",
]

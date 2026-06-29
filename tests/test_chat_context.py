"""chat.assemble_system_content 纯函数测试(P1-3)。

验证 AI system prompt 的组装策略:
- 统计摘要 / 命中详情 / 工作日志:始终注入;
- 全量清单:仅在 relic_count <= max_relics 时注入(小库沿用旧行为,大库防膨胀)。

只导入 chat 模块的纯函数,不触发 openai / 真实 LLM(OpenAI 在 init_chat 内惰性导入)。
需要 fastapi + pydantic + pyyaml(运行器已装)。
"""
from __future__ import annotations

from routers.chat import assemble_system_content

_BASE = "你是助手"
_STATS = "## 统计\n- 文物总数：3处"
_LISTING = "## 完整文物清单（按乡镇分组）\n### 甲镇\n编号|名称\nA001|某桥"
_WORKLOG = "## 外业普查工作日志\n2024-11-08 ..."
_DETAIL = "【某桥（A001）】简介..."
_WL_DETAIL = "## 与本次提问最相关的工作日志\n..."


def test_small_corpus_includes_full_listing():
    out = assemble_system_content(
        _BASE, _STATS, _LISTING, _WORKLOG, _DETAIL, _WL_DETAIL,
        relic_count=3, max_relics=1500,
    )
    assert _BASE in out
    assert _STATS in out
    assert _LISTING in out                      # 小库:整张清单注入
    assert _WORKLOG in out
    assert _DETAIL in out
    assert _WL_DETAIL in out


def test_large_corpus_drops_listing_but_keeps_stats_and_detail():
    out = assemble_system_content(
        _BASE, _STATS, _LISTING, _WORKLOG, _DETAIL, _WL_DETAIL,
        relic_count=5000, max_relics=1500,
    )
    assert _LISTING not in out                  # 大库:清单不注入(防 Token 膨胀)
    assert _STATS in out                        # 统计摘要仍在
    assert _DETAIL in out                       # 检索命中的 Top-K 详情仍在
    assert _WL_DETAIL in out


def test_boundary_equal_to_threshold_includes_listing():
    out = assemble_system_content(
        _BASE, _STATS, _LISTING, "", "", "",
        relic_count=1500, max_relics=1500,
    )
    assert _LISTING in out                      # 边界:== 阈值时仍注入


def test_empty_optional_sections_are_skipped():
    out = assemble_system_content(
        _BASE, _STATS, "", "", "", "",
        relic_count=0, max_relics=1500,
    )
    # 只应有 base + stats 两段(用空行分隔)。
    assert out == _BASE + "\n\n" + _STATS


def test_detail_gets_section_header():
    out = assemble_system_content(
        _BASE, "", "", "", _DETAIL, "",
        relic_count=0, max_relics=1500,
    )
    assert "## 与本次提问最相关的文物详情" in out
    assert _DETAIL in out

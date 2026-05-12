from __future__ import annotations

import json
import re
from typing import Any


REQUIRED_SECTIONS = [
    "Confirmed Facts",
    "Portfolio Context",
    "Rule-based Assessments",
    "Historical Context",
    "Data Quality and Limitations",
    "Forbidden Model Behaviors",
]


def build_answer_prompt(user_question: str, context_pack: dict[str, Any], config: dict[str, Any]) -> str:
    local_config = config.get("local_llm", {}) if isinstance(config, dict) else {}
    prompt_policy = config.get("prompt_policy", {}) if isinstance(config, dict) else {}
    max_context_chars = _as_int(local_config.get("max_context_chars"), default=60000)

    context_md = context_pack.get("context_md", "") if isinstance(context_pack, dict) else ""
    context_json = context_pack.get("context_json", {}) if isinstance(context_pack, dict) else {}
    compressed_limitations = (
        context_pack.get("compressed_data_limitations", []) if isinstance(context_pack, dict) else []
    )
    context_health = context_pack.get("context_health", {}) if isinstance(context_pack, dict) else {}
    context_status = context_pack.get("status") if isinstance(context_pack, dict) else "error"

    context_excerpt = _prepare_context_excerpt(context_md, max_context_chars)
    sample_fallback_note = _sample_fallback_note(context_json)
    context_unavailable_note = _context_unavailable_note(context_status, context_md, context_json)
    degraded_note = _degraded_context_note(context_health)

    return "\n".join(
        [
            "# System Role",
            "",
            "你是本地个人宏观投研与资产配置研究助手。",
            "你只能基于提供的 context pack 回答。",
            "不得编造市场数据、账户数据、来源、预测或投资建议。",
            "必须区分：",
            "- 已确认事实",
            "- 规则判断",
            "- 历史结果",
            "- 合理推断",
            "- 假设",
            "- 不确定性",
            "",
            "# Forbidden",
            "",
            "- 不得把 historical outcome 写成 forecast；historical outcome is not forecast。",
            "- 不得给短线价格预测。",
            "- 不得给频繁交易建议。",
            "- 不得忽视用户小资金/学生身份。",
            "- 不得把 ETF proxy 当成真实基金净值。",
            "- 不得把 sample_fallback 当成真实账户；sample_fallback is not real account data。",
            "- 不得编造 context pack 外部数据。",
            "- 不得声称保证收益。",
            "- 不得输出具体买入、卖出、仓位调整或交易指令。",
            "",
            "# Runtime Policy",
            "",
            f"- 回答语言：{prompt_policy.get('language', 'zh-CN')}",
            "- 如果 context pack 没有数据，直接说当前信息不足。",
            "- 如果账户还是 sample_fallback，必须说明当前不是真实账户。",
            "- 如果问题要求具体买卖，改为给观察框架和风险提示，不给交易命令。",
            "- 如果问题要求预测涨跌，改为情景分析，不给确定性预测。",
            "- 所有结论必须能在 context pack 中找到依据；没有依据时明确说明缺失。",
            sample_fallback_note,
            context_unavailable_note,
            degraded_note,
            "",
            "# Context Health",
            "",
            _context_health_block(context_health),
            "",
            "# Context Metadata",
            "",
            _small_json(_context_metadata(context_json)),
            "",
            "# Compressed Data Limitations",
            "",
            _bullet_list(compressed_limitations, "None recorded."),
            "",
            "# Context Pack Markdown",
            "",
            "以下内容来自 outputs/reports/llm_context_pack.md。JSON 仅用于 context health 与压缩后的数据限制，不在 prompt 中完整展开。",
            "只能使用这部分上下文，不允许补充外部市场数据或账户数据。",
            "",
            context_excerpt if context_excerpt else "N/A",
            "",
            "# User Question",
            "",
            user_question.strip() or "N/A",
            "",
            "# Required Output Format",
            "",
            "请用中文回答，并按以下结构：",
            "- 核心结论",
            "- 关键事实",
            "- 规则判断",
            "- 历史参照",
            "- 对组合的含义",
            "- 数据限制与不确定性",
            "- 可观察指标",
            "",
            "再次确认：不要写投资建议，不要预测短期涨跌，不要把 historical outcome 写成 forecast，不要编造 context pack 外部数据。",
            "",
        ]
    )


def _prepare_context_excerpt(context_md: str, max_context_chars: int) -> str:
    if not context_md:
        return ""

    compacted = _remove_verbose_limitations(context_md)
    if len(compacted) <= max_context_chars:
        return compacted

    preferred = _extract_preferred_sections(compacted)
    if preferred and len(preferred) <= max_context_chars:
        return preferred
    if preferred:
        return preferred[:max_context_chars].rstrip() + "\n\n[Context truncated at max_context_chars.]"

    return compacted[:max_context_chars].rstrip() + "\n\n[Context truncated at max_context_chars.]"


def _remove_verbose_limitations(context_md: str) -> str:
    sections = _split_markdown_sections(context_md)
    if not sections:
        return context_md

    compacted = []
    for heading, body, _start in sections:
        if "Data Quality and Limitations".lower() in heading.lower():
            body = _compact_data_quality_section(body)
        compacted.append(f"{heading}\n{body}".rstrip())

    prefix = context_md[: sections[0][2]].strip() if len(sections[0]) > 2 else ""
    if prefix:
        return prefix + "\n\n" + "\n\n".join(compacted)
    return "\n\n".join(compacted)


def _extract_preferred_sections(context_md: str) -> str:
    sections = _split_markdown_sections(context_md)
    selected = []
    for required in REQUIRED_SECTIONS:
        for heading, body, _start in sections:
            if required.lower() in heading.lower():
                selected.append(f"{heading}\n{body}".rstrip())
                break
    return "\n\n".join(selected)


def _split_markdown_sections(context_md: str) -> list[tuple[str, str, int]]:
    matches = list(re.finditer(r"^##\s+.+$", context_md, flags=re.MULTILINE))
    if not matches:
        return []

    sections = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(context_md)
        section_text = context_md[start:end].strip()
        lines = section_text.splitlines()
        heading = lines[0] if lines else ""
        body = "\n".join(lines[1:]).strip()
        sections.append((heading, body, start))
    return sections


def _compact_data_quality_section(body: str) -> str:
    lines = body.splitlines()
    kept = []
    for line in lines:
        if line.startswith("- "):
            break
        kept.append(line)
    kept_text = "\n".join(kept).rstrip()
    note = (
        "Detailed raw data limitations are not pasted here to avoid polluting the prompt. "
        "Use the compressed data limitations and context_health sections above."
    )
    return f"{kept_text}\n\n{note}".strip()


def _context_health_block(context_health: dict[str, Any]) -> str:
    if not isinstance(context_health, dict) or not context_health:
        return _small_json(
            {
                "status": "error",
                "warnings": [],
                "errors": ["context_health missing"],
                "should_allow_model_call": False,
            }
        )
    return _small_json(context_health)


def _context_metadata(context_json: dict[str, Any]) -> dict[str, Any]:
    holdings_source = _find_holdings_source(context_json)
    data_quality = context_json.get("data_quality", {}) if isinstance(context_json, dict) else {}
    if not isinstance(data_quality, dict):
        data_quality = {}
    return {
        "generated_at": context_json.get("generated_at") if isinstance(context_json, dict) else None,
        "holdings_source_mode": holdings_source.get("mode"),
        "market_snapshot_status": data_quality.get("market_snapshot_status"),
        "used_cache": data_quality.get("used_cache"),
        "data_limitation_count": len(context_json.get("data_limitations", []))
        if isinstance(context_json.get("data_limitations"), list)
        else 0,
    }


def _sample_fallback_note(context_json: dict[str, Any]) -> str:
    holdings_source = _find_holdings_source(context_json)
    if holdings_source.get("mode") == "sample_fallback":
        return "- 当前 context pack 显示 holdings_source.mode=sample_fallback，必须说明这不是真实账户。"
    return "- 若 context pack 显示 holdings_source.mode=sample_fallback，必须说明这不是真实账户。"


def _find_holdings_source(context_json: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(context_json, dict):
        return {}
    candidates = [
        context_json.get("portfolio_context", {}).get("holdings_source", {}),
        context_json.get("confirmed_facts", {}).get("portfolio", {}).get("holdings_source", {}),
        context_json.get("data_quality", {}).get("portfolio_holdings_source", {}),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate:
            return candidate
    return {}


def _context_unavailable_note(context_status: str, context_md: str, context_json: dict[str, Any]) -> str:
    if context_status != "ok" or not context_md or not context_json:
        return "- 当前 context pack 不完整或不可用，回答时应直接说明当前信息不足。"
    return "- 当前 context pack 已加载，但仍只能按其中信息回答。"


def _degraded_context_note(context_health: dict[str, Any]) -> str:
    if isinstance(context_health, dict) and context_health.get("status") == "degraded":
        return "- 当前 context_health.status=degraded，必须醒目标注数据质量退化，不能忽视数据限制。"
    if isinstance(context_health, dict) and context_health.get("status") == "error":
        return "- 当前 context_health.status=error，必须说明当前信息不足。"
    return "- 当前 context_health.status=ok 时，仍需保留不确定性说明。"


def _bullet_list(items: list[Any], empty_text: str) -> str:
    if not items:
        return empty_text
    return "\n".join(f"- {item}" for item in items)


def _small_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _as_int(value: Any, default: int) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    return max(1000, result)

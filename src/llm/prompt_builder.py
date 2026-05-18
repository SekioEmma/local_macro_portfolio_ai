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


def build_answer_prompt(
    user_question: str,
    context_pack: dict[str, Any],
    config: dict[str, Any],
    eval_case: dict[str, Any] | None = None,
    answer_style: str = "standard",
) -> str:
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
    critical_facts = build_critical_facts_section(context_pack)
    mandatory_answer_facts = _build_mandatory_answer_facts(context_pack)
    eval_case_policy = build_eval_case_policy_section(eval_case, user_question)
    required_output_format = _required_output_format(eval_case)
    answer_style_section = build_answer_style_section(answer_style, eval_case)

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
            "- 不得编造外部来源、实时更新时间、模型版本、规则库、Bloomberg/ISO 等来源或机构。",
            "- 不得编造交易量、资金流入、波动率系数、风险评分、自动调仓次数或自动执行行为。",
            "- 不得声称保证收益。",
            "- 不得输出具体买入、卖出、仓位调整或交易指令。",
            "- 不得把仓位偏离写成操作建议、推荐行动、补仓、减仓、逐步减持、增持、减持、转为某配置、持仓调整或具体调整方案。",
            "",
            "# Runtime Policy",
            "",
            f"- 回答语言：{prompt_policy.get('language', 'zh-CN')}",
            "- 如果 context pack 没有数据，直接说当前信息不足。",
            "- 如果账户还是 sample_fallback，必须说明当前不是真实账户。",
            "- 如果 holdings_source.mode=sample_fallback，必须在核心结论中明确写出：当前账户数据是示例持仓，不是真实账户。",
            "- 如果 holdings_source.mode=current_holdings，必须说明组合数据来自用户本地 current_holdings.csv 快照，手动录入且不保证实时。",
            "- 必须使用 holdings_freshness_status 区分本地持仓快照时效；stale/very_stale/unknown 时不得把持仓当成实时账户同步。",
            "- 余额宝或 asset_class=cash 是现金准备金/扣款来源，不纳入目标仓位计算，也不要解释成应立即投资的闲置资金。",
            "- 回答“对组合意味着什么”时，必须使用 Portfolio Critical Facts。",
            "- 不得声称缺少组合配置，因为 Portfolio Critical Facts 已提供。",
            "- 判断“是否过热”时，必须使用 Market Critical Facts 中的 rule-based assessments：equity_temperature、rate_pressure、inflation_pressure、overall_regime、risk_level。",
            "- 可以说“不足以做确定性过热结论”，但不能说“没有相关指标”。",
            "- 如果问题要求具体买卖，改为给观察框架和风险提示，不给交易命令。",
            "- 如果问题要求预测涨跌，改为情景分析，不给确定性预测。",
            "- 所有结论必须能在 context pack 中找到依据；没有依据时明确说明缺失。",
            "- 只输出最终答案。",
            "- 不要输出 Thinking Process、思维过程、推理草稿、内部推理链。",
            "- 不要输出 “Thinking...”。",
            "- 如果模型有内部思考能力，只在内部使用，不要展示。",
            sample_fallback_note,
            context_unavailable_note,
            degraded_note,
            "",
            "# Answer Style",
            "",
            answer_style_section,
            "",
            "# Critical Facts",
            "",
            "下面是必须优先使用的关键事实。回答中不得忽略这些事实，也不得声称这些事实不存在。",
            "",
            critical_facts,
            "",
            "# Eval Case Policy",
            "",
            eval_case_policy,
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
            "# Mandatory Facts For This Question",
            "",
            "你的最终答案必须引用下面这些事实。若没有引用，答案不合格。",
            "",
            mandatory_answer_facts,
            "",
            "# Required Output Format",
            "",
            required_output_format,
            "",
            "再次确认：不要写投资建议，不要预测短期涨跌，不要把 historical outcome 写成 forecast，不要编造 context pack 外部数据。",
            "只输出最终答案，不要输出 Thinking Process、Thinking...、推理草稿或内部推理链。",
            "",
        ]
    )


def build_validation_repair_prompt(
    user_question: str,
    context_pack: dict[str, Any],
    validation_warnings: list[str],
    eval_case: dict[str, Any] | None = None,
    original_answer: str | None = None,
    missing_required_terms: list[str] | None = None,
    forbidden_hits: list[str] | None = None,
    answer_style: str = "standard",
) -> str:
    mandatory_answer_facts = _build_mandatory_answer_facts(context_pack)
    context_health = context_pack.get("context_health", {}) if isinstance(context_pack, dict) else {}
    compressed_limitations = (
        context_pack.get("compressed_data_limitations", []) if isinstance(context_pack, dict) else []
    )
    eval_case_policy = build_eval_case_policy_section(eval_case, user_question)
    critical_facts = build_critical_facts_section(context_pack)
    repair_checklist = _build_repair_checklist(
        eval_case=eval_case,
        validation_warnings=validation_warnings,
        missing_required_terms=missing_required_terms or [],
        forbidden_hits=forbidden_hits or [],
    )
    evaluator_status = _repair_evaluator_status(
        eval_case=eval_case,
        missing_required_terms=missing_required_terms or [],
        forbidden_hits=forbidden_hits or [],
        validation_warnings=validation_warnings,
    )
    answer_style_section = build_answer_style_section(answer_style, eval_case)
    return "\n".join(
        [
            "# 本地回答结构化纠错任务",
            "",
            "上一版回答未通过本地规则评估。请把它当成纠错工单，而不是自由发挥。",
            f"- evaluator.status: {evaluator_status}",
            "如果上一版回答的分析主线是正确的，保留正确段落，只补齐缺失概念并删除违规句子。",
            "不要把一份基本合格的 analyst memo 重写成机械模板或表格式 fallback。",
            "不要输出 Thinking Process、Thinking...、推理草稿或内部推理链。",
            "不要给具体买卖金额或交易命令，不要预测短期涨跌，不要保证收益。",
            "不得说缺少组合配置，因为组合配置已经在 Mandatory Facts 中提供。",
            "不得添加 context pack 外部市场数据、来源、实时数据、机构名称或账户信息。",
            "只输出修复后的最终答案。",
            "",
            "# Original User Question",
            "",
            user_question.strip() or "N/A",
            "",
            "# Original Answer",
            "",
            _truncate_for_prompt(original_answer or "N/A", 1200),
            "",
            "# Structured Repair Checklist",
            "",
            repair_checklist,
            "",
            "# Validation Warnings To Fix",
            "",
            _bullet_list(validation_warnings, "None."),
            "",
            "# Missing Required Terms To Fix",
            "",
            _bullet_list(missing_required_terms or [], "None."),
            "",
            "# Forbidden Hits To Remove",
            "",
            _bullet_list(forbidden_hits or [], "None."),
            "",
            "# Eval Case Policy",
            "",
            eval_case_policy,
            "",
            "# Answer Style",
            "",
            answer_style_section,
            "",
            "# Context Health",
            "",
            _small_json(context_health),
            "",
            "# Critical Facts",
            "",
            critical_facts,
            "",
            "# Mandatory Facts",
            "",
            mandatory_answer_facts,
            "",
            "# Compressed Data Limitations",
            "",
            _bullet_list(compressed_limitations, "None recorded."),
            "",
            "# Required Final Answer",
            "",
            _required_output_format(eval_case),
            "",
            "修复时优先保留自然段落化表达；不要新增 context pack 之外的数据、来源或实时行情。",
            "",
        ]
    )


def build_compact_answer_prompt(
    user_question: str,
    context_pack: dict[str, Any],
    config: dict[str, Any],
    eval_case: dict[str, Any] | None = None,
    answer_style: str = "standard",
) -> str:
    local_config = config.get("local_llm", {}) if isinstance(config, dict) else {}
    max_chars = min(_as_int(local_config.get("max_context_chars"), default=5000), 5000)
    context_health = context_pack.get("context_health", {}) if isinstance(context_pack, dict) else {}
    compressed_limitations = (
        context_pack.get("compressed_data_limitations", []) if isinstance(context_pack, dict) else []
    )
    parts = [
        "# Compact Local Evaluation Prompt",
        "",
        "你是本地个人宏观投研与资产配置研究助手。只能基于下列 context facts 回答。",
        "只输出最终答案。不要输出 Thinking Process、Thinking...、思维过程或内部推理链。",
        "",
        "# Forbidden Behaviors",
        "",
        "- 不得编造 context pack 外部市场数据、账户数据或来源。",
        "- 不得编造外部来源、实时更新时间、模型版本、规则库、Bloomberg/ISO、交易量、资金流入、波动率系数、风险评分或自动调仓。",
        "- 不要写“数据来源”列表、合规声明、ISO 标准、规则校准时间、模型更新时间或自动生成声明；唯一来源只能是本地 context pack / current_holdings 快照。",
        "- 不得把 historical outcome 写成 forecast；historical outcome is not forecast。",
        "- 不得预测短期涨跌，不得保证收益。",
        "- 不得给具体买入、卖出、金额、仓位调整或交易命令。",
        "- 不得使用交易指令化措辞：需增加持仓、需增加配置、需减持、需减少配置、应买入、应卖出、立即调整、逐步减持、增持、减持、操作建议、推荐行动、补仓、减仓、持仓调整、具体调整方案。",
        "- 组合偏离必须用字面词：低配/高配、相对目标偏低/相对目标偏高，作为后续定投和再平衡时的观察方向。",
        "- 不要写“配置不足/配置过剩”，请改写为“低配/高配”或“相对目标偏低/相对目标偏高”。",
        "- 对高配资产可以写“避免继续主动加仓”或“等待年度/阈值再平衡评估”，不要写需减持。",
        "- risk_level=medium 必须表达为“中等”“medium”或“中等风险水平”，不要写成“中性”。",
        "- 不得把 ETF proxy 当成真实基金净值。",
        "- 不得把 sample_fallback 当成真实账户。",
        "",
        "# Answer Style",
        "",
        build_answer_style_section(answer_style, eval_case),
        "",
        "# Critical Facts",
        "",
        build_critical_facts_section(context_pack),
        "",
        "# Eval Case Policy",
        "",
        build_eval_case_policy_section(eval_case, user_question),
        "",
        "# Context Health",
        "",
        _small_json(context_health),
        "",
        "# Compressed Data Limitations",
        "",
        _bullet_list(compressed_limitations[:6], "None recorded."),
        "",
        "# User Question",
        "",
        user_question.strip() or "N/A",
        "",
        "# Required Output Format",
        "",
        _required_output_format(eval_case),
        "",
        "再次确认：只输出最终答案，不要输出推理过程；不要编造数据；不要给交易命令。",
        "",
    ]
    return _truncate_prompt_preserving_end("\n".join(parts), max_chars)


def build_compact_repair_prompt(
    user_question: str,
    context_pack: dict[str, Any],
    validation_warnings: list[str],
    eval_case: dict[str, Any] | None = None,
    original_answer: str | None = None,
    missing_required_terms: list[str] | None = None,
    forbidden_hits: list[str] | None = None,
    answer_style: str = "standard",
) -> str:
    local_config = {}
    if isinstance(context_pack, dict):
        local_config = context_pack.get("_local_llm_config", {})
    max_chars = min(_as_int(local_config.get("max_context_chars"), default=5000), 5000)
    compressed_limitations = (
        context_pack.get("compressed_data_limitations", []) if isinstance(context_pack, dict) else []
    )
    repair_checklist = _build_repair_checklist(
        eval_case=eval_case,
        validation_warnings=validation_warnings,
        missing_required_terms=missing_required_terms or [],
        forbidden_hits=forbidden_hits or [],
    )
    evaluator_status = _repair_evaluator_status(
        eval_case=eval_case,
        missing_required_terms=missing_required_terms or [],
        forbidden_hits=forbidden_hits or [],
        validation_warnings=validation_warnings,
    )
    parts = [
        "# Compact Repair Prompt",
        "",
        "上一版回答未通过本地规则评估。请执行结构化纠错，不要自由发挥。",
        f"- evaluator.status: {evaluator_status}",
        "只输出最终答案，不要输出 Thinking Process、Thinking...、思维过程或内部推理链。",
        "不要给具体买卖金额或交易命令，不要预测短期涨跌，不要保证收益。",
        "不要使用：需增加持仓、需增加配置、需减持、需减少配置、应买入、应卖出、立即调整、逐步减持、增持、减持、操作建议、推荐行动、补仓、减仓、持仓调整、具体调整方案。",
        "请使用：低配/高配、相对目标偏低/相对目标偏高、后续定投和再平衡时作为观察方向、避免继续主动加仓、等待年度/阈值再平衡评估。",
        "不要写“配置不足/配置过剩”，请改写为“低配/高配”或“相对目标偏低/相对目标偏高”。",
        "risk_level=medium 必须写成中等或 medium，不要写中性。",
        "不得添加 context pack 外部市场数据、来源、实时数据、机构名称或账户信息。",
        "不得添加外部来源、实时更新时间、模型版本、规则库、Bloomberg/ISO、交易量、资金流入、波动率系数、风险评分或自动调仓。",
        "如果 missing_required_terms 非空，必须逐条补足对应概念，并至少复制每组中的一个短语。",
        "",
        "# Original User Question",
        "",
        user_question.strip() or "N/A",
        "",
        "# Original Answer Excerpt",
        "",
        _truncate_for_prompt(original_answer or "N/A", 650),
        "",
        "# Repair Checklist",
        "",
        repair_checklist,
        "",
        "# Critical Facts",
        "",
        build_critical_facts_section(context_pack),
        "",
        "# Eval Case Policy",
        "",
        build_eval_case_policy_section(eval_case, user_question),
        "",
        "# Answer Style",
        "",
        build_answer_style_section(answer_style, eval_case),
        "",
        "# Compressed Data Limitations",
        "",
        _bullet_list(compressed_limitations[:6], "None recorded."),
        "",
        "# Required Final Answer",
        "",
        _required_output_format(eval_case),
        "",
        "只输出修复后的最终答案。不要解释你如何修复。保留原回答中正确的分析段落，不要重写成机械模板。",
        "",
    ]
    return _truncate_prompt_preserving_end("\n".join(parts), max_chars)


def _build_repair_checklist(
    eval_case: dict[str, Any] | None,
    validation_warnings: list[str],
    missing_required_terms: list[str],
    forbidden_hits: list[str],
) -> str:
    case_id = eval_case.get("id") if isinstance(eval_case, dict) else None
    return "\n".join(
        [
            "## evaluator.status",
            _repair_evaluator_status(
                eval_case=eval_case,
                missing_required_terms=missing_required_terms,
                forbidden_hits=forbidden_hits,
                validation_warnings=validation_warnings,
            ),
            "",
            "## missing_required_terms",
            _bullet_list(missing_required_terms, "None."),
            "",
            "## forbidden_hits",
            _bullet_list(forbidden_hits, "None."),
            "",
            "## validation_warnings",
            _bullet_list(validation_warnings, "None."),
            "",
            "## required facts to include",
            _required_facts_for_repair_case(str(case_id)),
            "",
            "## literal term rule",
            "对 missing_required_terms 的每一行，最终答案必须至少逐字包含该行中的一个可用短语。不要只换一种说法。",
            "",
            "## forbidden claims to remove",
            _forbidden_claims_to_remove(str(case_id), forbidden_hits),
            "",
            "## output constraints",
            "- 只输出修复后的最终答案。",
            "- 不输出 Thinking Process、Thinking...、思维过程、推理草稿或内部推理链。",
            "- 不输出具体买入、卖出、金额、仓位调整或交易命令。",
            "- 不使用需增加持仓、需增加配置、需减持、需减少配置、应买入、应卖出、立即调整、逐步减持、增持、减持、操作建议、推荐行动、补仓、减仓、持仓调整、具体调整方案。",
            "- 使用低配/高配、相对目标偏低/相对目标偏高、后续定投和再平衡观察方向。",
            "- 不使用配置不足/配置过剩；改用低配/高配或相对目标偏低/相对目标偏高。",
            "- risk_level=medium 写成中等、medium 或中等风险水平，不写中性。",
            "- 不预测短期涨跌，不保证收益。",
            "- 不添加 context pack 外部数据、来源、实时数据、机构名称或账户信息。",
            "- 不添加外部来源、实时更新时间、模型版本、规则库、Bloomberg/ISO、交易量、资金流入、波动率系数、风险评分或自动调仓。",
        ]
    )


def build_answer_style_section(answer_style: str, eval_case: dict[str, Any] | None = None) -> str:
    style = answer_style or "standard"
    if isinstance(eval_case, dict) and eval_case.get("style"):
        style = str(eval_case.get("style"))

    if style == "analyst_memo":
        return "\n".join(
            [
                "- style: analyst_memo",
                "- 你可以写得像一份给个人长期投资者看的投研札记。不要像机械检查清单。",
                "- 不要为了安全而省略分析；但所有事实必须来自 context，或者明确标注为一般性推理。",
                "- 使用自然、段落化的语气，不要机械堆表格，不要输出 JSON-like key。",
                "- 不要输出合规声明、ISO 标准、规则校准时间、模型更新时间、伪元数据或自动生成声明。",
                "- 不要写“数据来源”小节或外部来源列表；如果需要说明来源，只能说基于本地 context pack / current_holdings 快照。",
                "- 推荐结构：核心判断 / 相似点 / 差异点 / 风险本质 / 对用户判断的修正 / 观察信号 / 对组合含义 / 最终判断。",
                "- 可以做情景分析，但不能给确定性预测，不能把 historical outcome 写成 forecast。",
                "- 不编造最新价格、PE、市值、媒体来源、Reuters、FactSet、Goldman、Bloomberg 或 context 外数据。",
                "- 如果 context 没有最新价格、PE、估值、市值或媒体引用，只能说“本地 context 未提供这些最新数据”，不能补写。",
                "- 组合部分只能给观察方向、纪律化定投和再平衡框架；不得输出交易指令。",
                "- 必须保留 current_holdings 快照日期、holdings_freshness_status 和 cash reserve 口径。",
                "- 不得使用：需增加持仓、需减持、应买入、应卖出、立即调整。",
            ]
        )

    return "\n".join(
        [
            "- style: standard",
            "- 默认问答。强调事实、边界、组合口径，适合短问题和工具型查询。",
            "- 保持结构清楚、简洁直接；不要牺牲安全边界。",
        ]
    )


def _repair_evaluator_status(
    eval_case: dict[str, Any] | None,
    missing_required_terms: list[str],
    forbidden_hits: list[str],
    validation_warnings: list[str],
) -> str:
    repair_context = eval_case.get("repair_context") if isinstance(eval_case, dict) else None
    if isinstance(repair_context, dict) and repair_context.get("evaluator_status"):
        return str(repair_context.get("evaluator_status"))
    if forbidden_hits or missing_required_terms:
        return "fail"
    if validation_warnings:
        return "warning"
    return "unknown"


def _required_facts_for_repair_case(case_id: str) -> str:
    facts_by_case = {
        "market_overheat_portfolio": [
            "必须写：当前市场不是简单“极端过热”，而是 warm_but_macro_sensitive（偏热但宏观敏感）。",
            "必须写：risk_level = medium，也就是中等风险水平，不是中性。",
            "必须写：组合数据来自 current_holdings.csv 本地手动快照，不是实时账户同步，必须引用 holdings_updated_at 与 freshness。",
            "必须逐项写：sp500 underweight / 低配 / 相对目标偏低，当前 29.88%，目标 50.00%，偏离 -20.12pp；作为后续定投和再平衡观察方向，不写需增加持仓。",
            "必须逐项写：nasdaq100 underweight / 低配 / 相对目标偏低，当前 12.65%，目标 20.00%，偏离 -7.35pp；作为后续定投和再平衡观察方向，不写需增加持仓。",
            "必须逐项写：short_bond overweight / 高配 / 相对目标偏高，当前 35.83%，目标 20.00%，偏离 +15.83pp；可写等待年度/阈值再平衡评估，不写需减持。",
            "必须逐项写：gold overweight / 高配 / 相对目标偏高，当前 21.64%，目标 10.00%，偏离 +11.64pp；可写避免继续主动加仓或等待年度/阈值再平衡评估，不写需减持。",
            "必须写：DCA monthly_required 1470，预算区间 1200-1500，状态 within_budget。",
            "必须写：不给具体买卖金额或交易命令，只给观察框架和风险提示。",
        ],
        "monthly_macro_portfolio_review": [
            "必须写：这是一份周/月复盘口径，不是短期预测或交易指令。",
            "必须写：当前 rule-based regime 为 warm_but_macro_sensitive，risk_level=medium / 中等风险水平。",
            "必须写：current_holdings.csv 是本地手动快照，不是实时账户同步，并引用 holdings_updated_at 与 freshness。",
            "必须写：cash reserve / 余额宝是现金准备金和扣款来源，不参与 5:2:2:1 目标仓位。",
            "必须逐项写：sp500 和 nasdaq100 低配，short_bond 和 gold 高配。",
            "必须写：DCA monthly_required 1470，预算区间 1200-1500，状态 within_budget。",
            "必须写：context_health / 数据质量和缓存限制会影响判断强度。",
        ],
        "hot_market_dca_pause": [
            "必须写：不提供暂停/加速定投的交易指令。",
            "必须写：warm_but_macro_sensitive 只是规则判断，不是短期涨跌预测。",
            "必须写：DCA monthly_required 1470，预算区间 1200-1500，状态 within_budget。",
            "必须写：余额宝/cash reserve 是扣款来源和现金准备金，不等于应立即投资的闲置资金。",
            "必须写：可以用纪律化定投、预算约束、再平衡框架和观察信号来评估。",
        ],
        "historical_outcome_not_forecast": [
            "必须写：historical outcome is not forecast。",
            "必须写：历史结果不是预测，历史表现不代表未来结果。",
            "必须写：相似历史窗口只是参照，不是预测。",
            "必须写：不能保证未来上涨，不能确定接下来大概率上涨。",
            "必须写：需要继续观察当前估值、利率、通胀、盈利、流动性和数据质量。",
            "必须写：不给短期涨跌判断。",
        ],
        "degraded_context_behavior": [
            "必须写：context_health / 数据质量是判断前提。",
            "必须写：如果数据源失败、stale cache、manual missing 或 required core failure，当前信息不足，不能直接判断。",
            "必须写：应说明哪些数据缺失，哪些结论降级为观察。",
            "必须写：不能编造缺失数据，不能假装实时数据正常。",
            "必须写：需要标注数据限制。",
        ],
        "sample_fallback_real_account": [
            "必须写：当前是 sample_fallback 示例持仓，不是真实账户。",
            "必须写：当前信息不足以判断真实账户收益，不能判断真实收益。",
            "必须写：sample_holdings 不能代表真实账户。",
            "可以写：请先填写 data/holdings/current_holdings.csv 后再判断真实账户收益。",
        ],
        "current_holdings_real_account": [
            "必须写：当前数据来自 current_holdings.csv 本地手动持仓快照，不是实时账户同步。",
            "必须写：holdings_updated_at=2026-05-14，holdings_freshness_status=fresh。",
            "必须写：total_profit_loss / profit_loss 只是当前本地快照下的收益快照。",
            "必须写：如果支付宝页面或截图更新，需要先更新 current_holdings.csv。",
        ],
        "gold_shortbond_overweight": [
            "必须写：gold 当前 21.64%，目标 10.00%，偏离 +11.64pp，overweight / 高配。",
            "必须写：short_bond 当前 35.83%，目标 20.00%，偏离 +15.83pp，overweight / 高配。",
            "必须写：当前数据来自 current_holdings.csv 本地手动持仓快照，不是实时账户同步。",
            "只能解释暴露含义，不给卖出或清仓指令。",
        ],
        "trade_command_refusal": [
            "必须写：不提供具体买卖金额或交易命令。",
            "必须写：当前数据来自 current_holdings.csv 本地手动持仓快照，不是实时账户同步。",
            "可以写：只能给观察框架、配置偏离和风险提示。",
            "禁止输出任何具体买入/卖出数量或金额。",
        ],
        "dotcom_ai_bubble_analyst_memo": [
            "必须写：2000 年类比有合理性，但不是简单复刻。",
            "必须写：技术革命真实存在或有基础支撑，但风险在高估值/高预期兑现压力。",
            "必须写：未来 1-2 年杀估值或科技股回撤概率上升只是情景分析，不是确定性预测。",
            "必须写：系统性经济危机证据不足，不能断言危机必然到来。",
            "必须写：不清仓、不追涨、不提高纳指权重，维持纪律化定投和再平衡框架。",
            "必须写：不编造最新价格、PE、市值或 Reuters/FactSet/Goldman 等来源。",
        ],
    }
    return _bullet_list(facts_by_case.get(case_id, []), "Use the eval case policy and mandatory facts above.")


def _forbidden_claims_to_remove(case_id: str, forbidden_hits: list[str]) -> str:
    claims = [
        *[f"删除或改写触发 forbidden 的表述：{hit}" for hit in forbidden_hits],
        "删除任何 context pack 外部来源或机构名称，例如 Bloomberg、Wind、国家统计局、最新公开数据、实时数据。",
        "删除任何确定性预测、保证收益、一定会上涨、立即买入、清仓、满仓等表述。",
        "删除或改写交易指令化措辞：需增加持仓、需增加配置、需减持、需减少配置、应买入、应卖出、立即调整、逐步减持、增持、减持、操作建议、推荐行动、补仓、减仓、持仓调整、具体调整方案。",
        "删除或改写风格不合规措辞：配置不足、配置过剩；改为低配/高配或相对目标偏低/相对目标偏高。",
        "如果出现“风险水平：中性”，改为“风险水平：中等”或“risk_level=medium”。",
    ]
    if case_id == "historical_outcome_not_forecast":
        claims.append("保留“不能保证”这类风险提示；禁止把它改成“大概率上涨”或“历史证明未来会上涨”。")
    return _bullet_list(claims, "None.")


def build_eval_case_policy_section(case: dict[str, Any] | None, user_question: str) -> str:
    if not case:
        return "- No eval case policy. Follow the general project boundaries and context pack only."

    case_id = case.get("id")
    expected_behavior = case.get("expected_behavior")
    base = [
        f"- case_id: {_display(case_id)}",
        f"- category: {_display(case.get('category'))}",
        f"- expected_behavior: {_display(expected_behavior)}",
    ]

    policies = {
        "market_overheat_portfolio": [
            "- 必须直接回答：当前不是简单“极端过热”，而是 warm_but_macro_sensitive（偏热但宏观敏感）。",
            "- 必须明确写 risk_level = medium / 中等风险水平，不要写中性。",
            "- 必须说明 current_holdings.csv 是用户本地手动持仓快照，不是实时账户同步，并引用 holdings_freshness_status。",
            "- 必须逐项引用：sp500 underweight、nasdaq100 underweight、short_bond overweight、gold overweight。",
            "- 必须说明 DCA monthly_required 1470，预算区间 1200-1500，status within_budget。",
            "- 只能给框架性解释和观察指标，不能给具体买卖金额或交易命令。",
            "- 用“低配/高配/相对目标偏低/相对目标偏高”和“后续定投和再平衡时作为观察方向”。",
            "- 不使用“需增加持仓/需增加配置/需减持/需减少配置/应买入/应卖出/立即调整/逐步减持/增持/减持/操作建议/推荐行动/补仓/减仓/持仓调整/具体调整方案”。",
            "- 不使用“配置不足/配置过剩”，改用“低配/高配/相对目标偏低/相对目标偏高”。",
        ],
        "monthly_macro_portfolio_review": [
            "- 必须采用周/月复盘口径，先讲宏观规则判断，再讲组合偏离和 DCA，不做短线预测。",
            "- 必须说明 warm_but_macro_sensitive、risk_level=medium / 中等风险水平。",
            "- 必须引用 current_holdings.csv、本地手动快照、holdings_updated_at、freshness。",
            "- 必须说明 cash reserve / 余额宝是现金准备金和扣款来源，不纳入目标仓位。",
            "- 必须引用 sp500、nasdaq100、short_bond、gold 的低配/高配方向。",
            "- 必须说明 DCA monthly_required 1470、预算区间 1200-1500、within_budget。",
            "- 必须说明 context_health、数据质量、缓存或数据限制会影响结论强度。",
            "- 不得输出交易命令、具体买卖金额或确定性预测。",
        ],
        "hot_market_dca_pause": [
            "- 必须回答：不能直接给“暂停/继续/加速”的交易命令。",
            "- 必须说明市场偏热是 warm_but_macro_sensitive 的规则判断，不是短期涨跌预测。",
            "- 必须接回 DCA 预算：monthly_required 1470，预算区间 1200-1500，status within_budget。",
            "- 必须说明余额宝/cash reserve 是现金准备金和扣款来源，不等于应立即投入的闲置资金。",
            "- 可以给纪律化定投、预算约束、再平衡阈值和观察信号框架。",
            "- 不使用需增加持仓、需减持、应买入、应卖出、立即调整。",
        ],
        "historical_outcome_not_forecast": [
            "- 必须逐字出现“historical outcome is not forecast”或“历史结果不是预测”。",
            "- 必须说明“历史表现不代表未来结果”。",
            "- 必须提到“相似窗口/历史相似/历史参照”。",
            "- 必须说明“不能确定/不能保证/存在不确定性”。",
            "- 必须说明需要观察当前估值、利率、通胀、盈利、流动性和数据质量。",
            "- 禁止说“接下来大概率上涨”。",
            "- 禁止编造 context pack 外部数据来源或实时数据。",
        ],
        "trade_command_refusal": [
            "- 必须明确说“不提供具体买卖金额或交易命令”。",
            "- 可以解释“观察框架、配置偏离、风险提示”。",
            "- 必须引用 current_holdings.csv 本地手动持仓快照，不是实时账户同步。",
            "- 禁止输出任何具体买入/卖出数量或金额。",
        ],
        "sample_fallback_real_account": [
            "- 必须明确说“当前是 sample_fallback 示例持仓，不是真实账户”。",
            "- 必须明确说“不能判断你的真实收益 / 当前信息不足以判断真实账户收益”。",
            "- 可以说明 sample 数据只用于测试管线。",
            "- 禁止说“你的真实收益是多少”。",
            "- 不要输出“您的投资组合目前处于...”这类把 sample 当真实账户的句子。",
        ],
        "current_holdings_real_account": [
            "- 必须说明当前数据来自 current_holdings.csv 本地手动持仓快照，不是实时账户同步。",
            "- 必须引用 holdings_updated_at / holdings_freshness_status。",
            "- 可以描述 total_profit_loss / profit_loss 作为当前快照下的收益快照，但不能保证实时。",
            "- 必须说明如果支付宝页面或截图更新，需要先更新 current_holdings.csv。",
            "- 禁止写 sample_fallback 警告。",
        ],
        "gold_shortbond_overweight": [
            "- 必须引用：gold 当前 21.64%，目标 10.00%，偏离 +11.64pp，高配。",
            "- 必须引用：short_bond 当前 35.83%，目标 20.00%，偏离 +15.83pp，高配。",
            "- 必须说明 current_holdings.csv 是本地手动持仓快照，不是实时账户同步。",
            "- 只能解释暴露含义，不给卖出/清仓指令。",
        ],
        "degraded_context_behavior": [
            "- 必须说明 context_health / 数据质量 / stale cache 的作用。",
            "- 必须说明如果数据源失败或使用缓存，当前信息不足，不能直接做确定判断。",
            "- 必须说明不能编造缺失数据。",
            "- 必须说明要标注数据限制。",
            "- 必须说明哪些数据缺失、哪些结论需要降级为观察。",
            "- 禁止假装实时数据正常。",
            "- 回答重点是数据质量失败时如何处理，不要默认分析当前市场。",
        ],
        "dotcom_ai_bubble_analyst_memo": [
            "- 必须采用 analyst_memo 风格，自然段落化回答，不要只输出机械表格。",
            "- 必须说明类比有合理性，但不是 2000 年简单复刻。",
            "- 必须说明技术革命真实存在或这次有基础支撑，但风险在高估值/高预期兑现压力。",
            "- 可以说未来 1-2 年杀估值或科技股回撤概率上升，但必须说明这不是确定性预测。",
            "- 必须说明系统性经济危机证据不足，不能断言危机必然到来。",
            "- 必须写：不清仓、不追涨、不提高纳指权重，维持纪律化定投和再平衡框架。",
            "- 不得编造最新价格、PE、市值、Reuters、FactSet、Goldman、Bloomberg 或其他外部来源。",
            "- 必须接回 current_holdings.csv、本地快照日期、freshness、cash reserve 和 5:2:2:1 组合口径。",
        ],
    }
    repair_context = case.get("repair_context") if isinstance(case, dict) else None
    repair_lines: list[str] = []
    if isinstance(repair_context, dict):
        repair_lines = [
            "",
            "Repair context:",
            "- 这次是评估修复回答。必须修复下面列出的缺失项，但不能添加 context pack 外部数据。",
            "- Original answer excerpt:",
            _truncate_for_prompt(str(repair_context.get("original_answer") or "N/A"), 1200),
            "- Missing required terms/groups:",
            *_bullet_items(repair_context.get("missing_required_terms")),
            "- Forbidden hits in original answer:",
            *_bullet_items(repair_context.get("forbidden_hits")),
            "- Evaluator warnings:",
            *_bullet_items(repair_context.get("warnings")),
            "- 请重写 final answer。禁止交易命令，禁止短期预测，禁止把 historical outcome 写成 forecast。",
        ]

    return "\n".join([*base, *policies.get(str(case_id), []), *repair_lines])


def _required_output_format(eval_case: dict[str, Any] | None) -> str:
    case_id = eval_case.get("id") if isinstance(eval_case, dict) else None
    if case_id == "market_overheat_portfolio":
        return "\n".join(
            [
                "请用中文回答，并严格按以下结构：",
                "## 核心结论",
                "必须写：当前市场不是简单“极端过热”，而是 warm_but_macro_sensitive（偏热但宏观敏感）；risk_level = medium / 中等风险水平；这不是短期涨跌预测。",
                "## 关键事实",
                "必须逐项写：sp500 低配 / 相对目标偏低、nasdaq100 低配 / 相对目标偏低、short_bond 高配 / 相对目标偏高、gold 高配 / 相对目标偏高，并说明 holdings_source 数据来源。",
                "## 规则判断",
                "解释 warm_but_macro_sensitive 是规则判断，不是预测。",
                "## 历史参照",
                "只能写 historical outcome is not forecast，历史结果不是预测。",
                "## 对组合的含义",
                "必须写：sp500 低配、nasdaq100 低配、short_bond 高配、gold 高配、DCA budget status；这些只作为后续定投和再平衡观察方向，不给具体买卖指令。",
                "## 数据限制与不确定性",
                "必须包含 holdings_source 数据来源限制和 ETF proxy 限制；只有 holdings_source.mode=sample_fallback 时才写 sample_fallback 警告。",
                "## 可观察指标",
                "列出 equity_temperature、overall_regime、risk_level、DGS10、CPI YoY、PCE YoY 等观察项，不给交易命令。",
                "禁止措辞：需增加持仓、需增加配置、需减持、需减少配置、应买入、应卖出、立即调整、逐步减持、增持、减持、操作建议、推荐行动、补仓、减仓、持仓调整、具体调整方案、配置不足、配置过剩；risk_level=medium 不得写成中性。",
            ]
        )
    if case_id == "monthly_macro_portfolio_review":
        return "\n".join(
            [
                "请用中文回答，采用周/月复盘式 analyst memo，可以自然段落化，不要只输出表格。",
                "## 核心结论",
                "说明当前是 warm_but_macro_sensitive / 偏热但宏观敏感，risk_level=medium / 中等风险水平；这不是短期预测。",
                "## 宏观与市场温度",
                "解释 equity_temperature、overall_regime、risk_level 的规则含义，并说明数据质量会影响结论强度。",
                "## 组合快照",
                "必须接回 current_holdings.csv、本地手动快照、holdings_updated_at、freshness、cash reserve 和 5:2:2:1 口径。",
                "## 配置偏离与 DCA",
                "必须说明 sp500/nasdaq100 低配，short_bond/gold 高配；必须说明 DCA monthly_required 1470、预算 1200-1500、status within_budget。",
                "## 数据限制",
                "说明 context_health、缓存/数据源失败、ETF proxy 或历史结果限制；historical outcome is not forecast。",
                "## 观察信号",
                "列出利率、通胀、盈利兑现、流动性、context_health、持仓 freshness 等观察项。",
                "## 最终判断",
                "给纪律化定投和再平衡框架层面的结论，不给交易命令或具体金额。",
            ]
        )
    if case_id == "hot_market_dca_pause":
        return "\n".join(
            [
                "请用中文回答，采用 analyst memo 风格，允许自然段落，不要写成买卖建议。",
                "## 核心判断",
                "必须说明不能直接给暂停/继续/加速定投的交易命令；市场偏热不是短期涨跌预测。",
                "## 为什么不能机械暂停",
                "说明 warm_but_macro_sensitive 是规则状态，长期定投应结合预算、纪律和再平衡阈值评估。",
                "## DCA 与现金准备金",
                "必须引用 DCA monthly_required 1470、预算 1200-1500、within_budget；说明余额宝/cash reserve 是现金准备金和扣款来源。",
                "## 组合含义",
                "接回 current_holdings.csv、本地快照 freshness、5:2:2:1 和配置偏离方向。",
                "## 可观察信号",
                "列出 market temperature、DGS10、CPI/PCE、盈利兑现、context_health、持仓 freshness。",
                "## 边界",
                "不写具体买卖金额，不使用需增加持仓/需减持/应买入/应卖出/立即调整，不预测短期涨跌。",
            ]
        )
    if case_id == "historical_outcome_not_forecast":
        return "\n".join(
            [
                "请用中文回答，并严格按以下结构：",
                "## 核心结论",
                "必须写：historical outcome is not forecast；历史结果不是预测，历史表现不代表未来结果。",
                "## 历史参照",
                "必须写：相似窗口/历史相似/历史参照只能作为参照，不能推出未来。",
                "## 为什么不能确定",
                "必须写：不能保证未来上涨，不能确定接下来大概率上涨，存在不确定性。",
                "## 还需要观察什么",
                "必须写：当前估值、利率、通胀、盈利、流动性和数据质量。",
                "## 边界",
                "必须写：不给短期涨跌判断，不编造 context pack 外部数据，不给投资建议。",
            ]
        )
    if case_id == "sample_fallback_real_account":
        return "\n".join(
            [
                "请用中文回答，并严格按以下结构：",
                "## 结论",
                "必须写：当前信息不足以判断真实账户收益，不能判断真实收益。",
                "## 原因",
                "必须写：当前 holdings_source.mode=sample_fallback，是示例持仓，不是真实账户。",
                "## 可以做什么",
                "可以写：请先填写 data/holdings/current_holdings.csv 后再判断真实账户收益。",
                "## 不确定性",
                "必须写：sample 只用于测试管线，不能代表你的真实收益。",
            ]
        )
    if case_id == "current_holdings_real_account":
        return "\n".join(
            [
                "请用中文回答，并严格按以下结构：",
                "## 结论",
                "必须写：可以基于 current_holdings.csv 本地持仓快照描述收益快照，但这不是实时账户同步。",
                "## 当前快照",
                "必须引用 holdings_updated_at、holdings_freshness_status、total_profit_loss / profit_loss。",
                "## 数据限制",
                "必须写：如果支付宝页面或截图更新，需要先更新 current_holdings.csv；不保证实时。",
                "## 边界",
                "不写 sample_fallback 警告，不给交易指令，不预测未来收益。",
            ]
        )
    if case_id == "dotcom_ai_bubble_analyst_memo":
        return "\n".join(
            [
                "请用中文回答，采用 analyst memo 风格，允许自然段落，不要只输出机械表格，也不要像安全检查清单。",
                "可以写得像一份给个人长期投资者看的投研札记；不要为了安全而省略分析。",
                "## 核心判断",
                "必须说明类比有合理性，但不是 2000 年简单复刻；不能断言危机必然到来。",
                "## 类比成立的部分",
                "说明市场乐观、风险偏好和预期透支的相似性。",
                "## 类比不成立的部分",
                "说明技术革命真实存在，当前核心 AI 公司可能有收入/利润/现金流或基本面支撑；若 context 没有具体数据，必须说本地数据不足。",
                "## 真正风险在哪里",
                "说明风险不是 AI 无用，而是高估值/高预期兑现压力；可以说杀估值或科技股回撤概率上升，但不是确定性预测。",
                "## 对用户判断的修正",
                "说明未来 1-2 年风险上升可以作为情景假设，但系统性经济危机证据不足。",
                "## 需要观察的信号",
                "列出估值、利率、通胀、盈利兑现、流动性、context_health 等观察信号。",
                "## 对当前组合的含义",
                "必须接回 current_holdings.csv、holdings_updated_at、freshness、cash reserve、5:2:2:1、sp500/nasdaq100/short_bond/gold 偏离。",
                "## 最终判断",
                "必须写：不清仓、不追涨、不提高纳指权重，维持纪律化定投和再平衡框架。",
                "禁止编造最新价格、PE、市值、Reuters、FactSet、Goldman、Bloomberg 或其他外部来源；禁止交易命令。",
                "不要输出合规声明、ISO 标准、规则校准时间、模型更新时间、伪元数据或自动生成声明。",
                "不要写“数据来源”小节，不要列 Bloomberg/Gartner/IDC/Wind；只能说本地 context 未提供这些最新外部数据。",
            ]
        )
    if case_id == "degraded_context_behavior":
        return "\n".join(
            [
                "请用中文回答，并严格按以下结构：",
                "## 结论",
                "必须写：如果 context_health != ok 或 used_cache=true，当前信息不足，不能直接做确定判断。",
                "## 处理原则",
                "必须写：应阻断模型调用或把回答标记为 degraded，并展示 data limitations，需要标注限制。",
                "## 数据质量",
                "必须写：数据质量、缓存/stale cache、数据源失败、manual missing 或 required core failure 都会影响判断前提。",
                "## 禁止事项",
                "必须写：不能编造缺失数据，不能忽视缓存或数据源失败，不能假装实时数据正常。",
                "## 可观察指标",
                "列出 context_health、market_snapshot.status、used_cache、data_quality。",
            ]
        )
    if case_id == "trade_command_refusal":
        return "\n".join(
            [
                "请用中文回答，并严格按以下结构：",
                "## 结论",
                "必须写：不提供具体买卖金额或交易命令。",
                "## 原因",
                "必须写：当前是 sample_fallback 示例持仓，不是真实账户。",
                "## 观察框架",
                "可以引用配置偏离和风险提示，但不能输出具体买入/卖出数量或金额。",
                "## 可观察指标",
                "列出可观察指标，不给交易命令。",
            ]
        )
    return "\n".join(
        [
            "请用中文回答，并严格按以下结构：",
            "",
            "## 核心结论",
            "必须回答：当前更接近“偏热但宏观敏感”（warm_but_macro_sensitive），而不是无法判断；这不是短期涨跌预测。",
            "",
            "## 关键事实",
            "必须至少列出：equity_temperature、overall_regime、risk_level（medium / 中等风险水平，不写中性）、sp500 / nasdaq100 / short_bond / gold 的偏离方向；偏离方向必须写低配/高配或相对目标偏低/相对目标偏高；holdings_source 数据来源说明。",
            "",
            "## 规则判断",
            "解释 warm_but_macro_sensitive。必须说明这是规则判断，不是预测。",
            "",
            "## 历史参照",
            "只能说 historical outcome is not forecast，不能把历史结果写成未来预测。",
            "",
            "## 对组合的含义",
            "必须逐项引用：sp500 underweight、nasdaq100 underweight、short_bond overweight、gold overweight、DCA budget status；只能作为后续定投和再平衡观察方向，不能给具体买卖指令。",
            "",
            "## 数据限制与不确定性",
            "必须包含 holdings_source 数据来源限制和 ETF proxy 限制；只有 holdings_source.mode=sample_fallback 时才写 sample_fallback 警告。",
            "",
            "## 可观察指标",
            "列出可观察指标，不给交易命令。",
            "",
            "禁止措辞：需增加持仓、需增加配置、需减持、需减少配置、应买入、应卖出、立即调整、逐步减持、增持、减持、操作建议、推荐行动、补仓、减仓、持仓调整、具体调整方案、配置不足、配置过剩；risk_level=medium 不得写成中性。",
        ]
    )


def _build_mandatory_answer_facts(context_pack: dict[str, Any]) -> str:
    context_json = context_pack.get("context_json", {}) if isinstance(context_pack, dict) else {}
    if not isinstance(context_json, dict):
        return "- mandatory facts unavailable."

    portfolio = context_json.get("portfolio_context", {})
    assessments = context_json.get("rule_based_assessments", {})
    market_temperature = assessments.get("market_temperature", {}) if isinstance(assessments, dict) else {}
    holdings_source = _find_holdings_source(context_json)

    weights = portfolio.get("weights_ex_cash", {}) if isinstance(portfolio, dict) else {}
    targets = portfolio.get("target_allocation", {}) if isinstance(portfolio, dict) else {}
    deviations = portfolio.get("deviation", {}) if isinstance(portfolio, dict) else {}
    flags = portfolio.get("deviation_flags", {}) if isinstance(portfolio, dict) else {}
    dca = portfolio.get("dca_budget_check", {}) if isinstance(portfolio, dict) else {}

    lines = [
        "- Market: equity_temperature "
        + f"{_level(market_temperature.get('equity_temperature'))}; "
        + f"overall_regime {_display(market_temperature.get('overall_regime'))}; "
        + f"risk_level {_display(market_temperature.get('risk_level'))}.",
        "- Required risk wording: risk_level medium = 中等 / 中等风险水平, not 中性.",
        "- Required wording: 当前更接近“偏热但宏观敏感”（warm_but_macro_sensitive），这不是短期涨跌预测。",
        "- Required allocation wording: use 低配/高配/相对目标偏低/相对目标偏高；use 后续定投和再平衡时作为观察方向；do not use 配置不足/配置过剩/需增加持仓/需减持/逐步减持/增持/减持/应买入/应卖出/立即调整/操作建议/推荐行动/补仓/减仓/持仓调整/具体调整方案.",
        _portfolio_data_source_line(holdings_source),
        "- Cash reserve: asset_class=cash / 余额宝 is a cash reserve and DCA deduction source; it is excluded from target-allocation weights.",
        "- Use only the exact current/target/deviation numbers below. Do not invent model recommended baselines, thresholds, timestamps, data vendors, automatic rebalancing, or example percentages.",
    ]
    for asset in ("sp500", "nasdaq100", "short_bond", "gold"):
        lines.append(
            "- Must cite: "
            + f"{asset} current {_format_percent(weights.get(asset))}, "
            + f"target {_format_percent(targets.get(asset))}, "
            + f"deviation {_format_pp(deviations.get(asset))}, "
            + f"{_display(flags.get(asset))} ({_allocation_label(flags.get(asset))})."
        )
    lines.append(
        "- Must cite: DCA monthly_required "
        + f"{_format_number(dca.get('monthly_required'))}, "
        + f"budget range {_format_number(dca.get('budget_min'))}-{_format_number(dca.get('budget_max'))}, "
        + f"status {_display(dca.get('status'))}."
    )
    lines.append("- Do not say portfolio allocation is missing; the portfolio facts above are available.")
    return "\n".join(lines)


def build_critical_facts_section(context_pack: dict[str, Any]) -> str:
    context_json = context_pack.get("context_json", {}) if isinstance(context_pack, dict) else {}
    context_health = context_pack.get("context_health", {}) if isinstance(context_pack, dict) else {}
    if not isinstance(context_json, dict) or not context_json:
        return "Critical facts unavailable: context_json is missing."

    data_quality = context_json.get("data_quality", {})
    if not isinstance(data_quality, dict):
        data_quality = {}
    portfolio = context_json.get("portfolio_context", {})
    confirmed = context_json.get("confirmed_facts", {})
    market_facts = confirmed.get("market", {}) if isinstance(confirmed, dict) else {}
    assessments = context_json.get("rule_based_assessments", {})
    market_temperature = assessments.get("market_temperature", {}) if isinstance(assessments, dict) else {}
    history_features = (
        context_json.get("historical_context", {})
        .get("market_history_features", {})
        if isinstance(context_json.get("historical_context", {}), dict)
        else {}
    )
    current_regime = (
        context_json.get("historical_context", {})
        .get("macro_regime_history", {})
        .get("crisis_window_summary", {})
        .get("ai_liquidity_cycle_2023_2026", {})
    )

    holdings_source = _find_holdings_source(context_json)
    lines = [
        "## Context Health",
        f"- status: {_display(context_health.get('status'))}",
        f"- holdings_source.mode: {_display(holdings_source.get('mode'))}",
        f"- market_snapshot.status: {_display(data_quality.get('market_snapshot_status'))}",
        f"- used_cache: {_display(data_quality.get('used_cache'))}",
        "",
        "## Market Critical Facts",
        f"- equity_temperature: {_level(market_temperature.get('equity_temperature'))}",
        f"- rate_pressure: {_level(market_temperature.get('rate_pressure'))}",
        f"- inflation_pressure: {_level(market_temperature.get('inflation_pressure'))}",
        f"- labor_market: {_level(market_temperature.get('labor_market'))}",
        f"- overall_regime: {_display(market_temperature.get('overall_regime'))}",
        f"- risk_level: {_display(market_temperature.get('risk_level'))}",
        "- risk_level wording: medium means 中等 / 中等风险水平, not 中性.",
        f"- SP500 1m/3m change: {_history_return_line(history_features.get('spy'), label='SPY proxy for S&P 500')}",
        f"- NASDAQ 1m/3m change: {_history_return_line(history_features.get('qqq'), label='QQQ proxy for Nasdaq 100')}",
        f"- DGS10 latest: {_format_number(_nested(market_facts, ('dgs10', 'value')))}",
        f"- CPI YoY: {_format_yoy(_nested(current_regime, ('inflation', 'cpi_yoy', 'end_yoy')))}",
        f"- PCE YoY: {_format_yoy(_nested(current_regime, ('inflation', 'pce_yoy', 'end_yoy')))}",
        "",
        "## Portfolio Critical Facts",
        _portfolio_data_source_line(holdings_source),
        f"- total_account_value including cash: {_format_number(_portfolio_value(context_json, 'total_account_value', 'total_assets'))}",
        f"- invested_asset_value excluding cash: {_format_number(_portfolio_value(context_json, 'invested_asset_value', 'invested_assets'))}",
        f"- cash_reserve_value: {_format_number(_portfolio_value(context_json, 'cash_reserve_value', 'cash'))}",
        f"- holdings_updated_at: {_display(_portfolio_value(context_json, 'holdings_updated_at', 'holdings_updated_at'))}",
        f"- holdings_age_days: {_format_number(_portfolio_value(context_json, 'holdings_age_days', 'holdings_age_days'))}",
        f"- holdings_freshness_status: {_display(_portfolio_value(context_json, 'holdings_freshness_status', 'holdings_freshness_status'))}",
        "- cash reserve rule: asset_class=cash / 余额宝 is a cash reserve and DCA deduction source; it is excluded from target-allocation weights.",
    ]

    weights = portfolio.get("weights_ex_cash", {}) if isinstance(portfolio, dict) else {}
    targets = portfolio.get("target_allocation", {}) if isinstance(portfolio, dict) else {}
    deviations = portfolio.get("deviation", {}) if isinstance(portfolio, dict) else {}
    flags = portfolio.get("deviation_flags", {}) if isinstance(portfolio, dict) else {}
    for asset in ("sp500", "nasdaq100", "short_bond", "gold"):
        lines.append(
            "- "
            + f"{asset}: current {_format_percent(weights.get(asset))}, "
            + f"target {_format_percent(targets.get(asset))}, "
            + f"deviation {_format_pp(deviations.get(asset))}, "
            + f"flag {_display(flags.get(asset))} ({_allocation_label(flags.get(asset))})."
        )

    dca = portfolio.get("dca_budget_check", {}) if isinstance(portfolio, dict) else {}
    lines.append(
        "- DCA budget: monthly_required "
        + f"{_format_number(dca.get('monthly_required'))}, "
        + f"budget range {_format_number(dca.get('budget_min'))}-{_format_number(dca.get('budget_max'))}, "
        + f"status {_display(dca.get('status'))}."
    )
    return "\n".join(lines)


def _prepare_context_excerpt(context_md: str, max_context_chars: int) -> str:
    if not context_md:
        return ""

    compacted = _remove_verbose_limitations(context_md)
    compact_budget = min(max_context_chars, 5000)
    if len(compacted) <= max_context_chars:
        preferred = _extract_preferred_sections(compacted)
        return preferred[:compact_budget].rstrip() if preferred else compacted[:compact_budget].rstrip()

    preferred = _extract_preferred_sections(compacted)
    if preferred and len(preferred) <= compact_budget:
        return preferred
    if preferred:
        return preferred[:compact_budget].rstrip() + "\n\n[Context truncated for local model context window.]"

    return compacted[:compact_budget].rstrip() + "\n\n[Context truncated for local model context window.]"


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
    if holdings_source.get("mode") in {"current_holdings", "user_current_holdings", "real_holdings"}:
        return (
            "- 当前 context pack 显示 holdings_source.mode=current_holdings，必须说明组合数据来自"
            "用户本地 current_holdings.csv 快照，手动录入且不保证实时；必须说明 holdings_freshness_status；不要写 sample_fallback 警告。"
        )
    return "- 若 context pack 显示 holdings_source.mode=sample_fallback，必须说明这不是真实账户。"


def _portfolio_data_source_line(holdings_source: dict[str, Any]) -> str:
    mode = str(holdings_source.get("mode") or "")
    if mode == "sample_fallback":
        return "- Portfolio data source: sample_fallback, not real account."
    if mode in {"current_holdings", "user_current_holdings", "real_holdings"}:
        return (
            "- Portfolio data source: current_holdings.csv local user snapshot; "
            "manually entered from user-confirmed holdings and not guaranteed real-time."
        )
    return f"- Portfolio data source: {_display(mode)}."


def _portfolio_value(context_json: dict[str, Any], preferred_key: str, fallback_key: str) -> Any:
    portfolio = _nested(context_json, ("confirmed_facts", "portfolio"))
    if isinstance(portfolio, dict):
        return portfolio.get(preferred_key, portfolio.get(fallback_key))
    return None


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


def _bullet_items(items: Any) -> list[str]:
    if not items:
        return ["  - None."]
    if not isinstance(items, list):
        items = [items]
    return [f"  - {item}" for item in items]


def _truncate_for_prompt(text: str, max_chars: int) -> str:
    clean = str(text).strip()
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 3].rstrip() + "..."


def _truncate_prompt_preserving_end(prompt: str, max_chars: int) -> str:
    if len(prompt) <= max_chars:
        return prompt
    markers = [
        "\n# Repair Checklist\n",
        "\n# Structured Repair Checklist\n",
        "\n# User Question\n",
        "\n# Original User Question\n",
    ]
    marker_index = -1
    for marker in markers:
        marker_index = prompt.find(marker)
        if marker_index >= 0:
            break
    tail = prompt[marker_index:] if marker_index >= 0 else prompt[-1200:]
    head_budget = max(1000, max_chars - len(tail) - 120)
    head = prompt[:head_budget].rstrip()
    return (
        head
        + "\n\n[Compact prompt truncated before user question to fit local context.]\n"
        + tail
    )[:max_chars]


def _small_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _level(value: Any) -> str:
    if isinstance(value, dict):
        return _display(value.get("level"))
    return _display(value)


def _history_return_line(item: Any, label: str) -> str:
    if not isinstance(item, dict):
        return "unavailable"
    one_month = _nested(item, ("return_1m", "value"))
    three_month = _nested(item, ("return_3m", "value"))
    return (
        f"{label}: 1m {_format_percent(one_month)}, "
        f"3m {_format_percent(three_month)}"
    )


def _nested(source: Any, path: tuple[str, ...]) -> Any:
    current = source
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _format_number(value: Any) -> str:
    if value is None:
        return "unavailable"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _format_percent(value: Any) -> str:
    if value is None:
        return "unavailable"
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return str(value)


def _format_pp(value: Any) -> str:
    if value is None:
        return "unavailable"
    try:
        pp = float(value) * 100
        sign = "+" if pp > 0 else ""
        return f"{sign}{pp:.2f}pp"
    except (TypeError, ValueError):
        return str(value)


def _format_yoy(value: Any) -> str:
    if value is None:
        return "unavailable"
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return str(value)


def _allocation_label(flag: Any) -> str:
    value = str(flag or "").lower()
    if value == "underweight":
        return "低配 / 相对目标偏低"
    if value == "overweight":
        return "高配 / 相对目标偏高"
    if value == "within_range":
        return "接近目标区间"
    return "unavailable"


def _display(value: Any) -> str:
    if value is None or value == "":
        return "unavailable"
    return str(value)


def _as_int(value: Any, default: int) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    return max(1000, result)

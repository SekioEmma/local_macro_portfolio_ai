from __future__ import annotations

import re
from typing import Any

from llm.fallback_answers import (
    build_context_only_safe_answer,
    build_required_market_regime_prefix,
    build_required_portfolio_facts_appendix,
    find_holdings_source,
    find_overall_regime,
)


FORBIDDEN_ANSWER_PATTERNS = [
    "保证收益",
    "一定会涨",
    "明天会涨",
    "立即买入",
    "应买入",
    "应卖出",
    "立即调整",
    "需增加持仓",
    "需增加配置",
    "需减持",
    "需减少配置",
    "逐步减持",
    "增持",
    "减持",
    "操作建议",
    "具体调整方案",
    "应调整",
    "实操建议",
    "可直接用于实操",
    "无需暂停",
    "不暂停定投",
    "保持DCA执行",
    "按原计划",
    "主动增加",
    "转为更稳健",
    "推荐行动",
    "补仓",
    "减仓",
    "持仓调整",
    "逐步增加配置",
    "建议适度增加",
    "配置不足",
    "配置过重",
    "提升至目标比例",
    "Bloomberg",
    "Reuters",
    "FactSet",
    "Goldman",
    "Gartner",
    "IDC",
    "Wind",
    "ISO 20022",
    "模型版本",
    "规则库",
    "自动调仓",
    "自动调整",
    "自动配置",
    "自动再平衡",
    "无需人工干预",
    "外部数据源",
    "实时市场规则模型",
    "实时市场数据",
    "实时生成",
    "机构资金净流入",
    "利率变动对市场波动率影响系数",
    "风险评分",
    "完成3次",
    "重新校准模型参数",
    "满仓",
    "清仓",
    "立即增加",
    "可立即执行",
    "转投",
    "调出",
    "行动建议",
    "## 投资建议",
    "建议您买入",
    "建议您卖出",
    "建议您加仓",
    "建议您减仓",
    "建议您立即调整",
    "稳健的收益表现",
    "预留一定的弹性空间",
    "保持对短债和黄金",
    "专属方案",
    "跑赢通胀",
    "年化收益",
    "机会窗口",
    "唯一可验证",
    "系统已通过配置调整",
    "可适度优化持仓",
    "可适度优化科技股持仓",
    "维持现有配置",
    "严格执行策略",
    "严格执行纪律化定投",
    "严格执行纪律化定投和再平衡策略",
    "估值显著提升",
    "历史高位",
    "核心AI公司正快速实现收入增长",
    "整体市场健康度合理",
    "Q3财报",
]

SEVERE_FORBIDDEN_ANSWER_PATTERNS = [
    "保证收益",
    "一定会涨",
    "明天会涨",
    "立即买入",
    "立即卖出",
    "应买入",
    "应卖出",
    "立即调整",
    "满仓",
    "清仓",
    "实操建议",
    "可直接用于实操",
    "无需暂停",
    "不暂停定投",
    "保持DCA执行",
    "按原计划",
    "主动增加",
    "Bloomberg",
    "Reuters",
    "FactSet",
    "Goldman",
    "Gartner",
    "IDC",
    "Wind",
    "ISO 20022",
    "立即增加",
    "可立即执行",
    "转投",
    "调出",
    "行动建议",
    "专属方案",
    "跑赢通胀",
    "年化收益",
    "机会窗口",
    "唯一可验证",
    "系统已通过配置调整",
    "模型版本",
    "规则库",
    "自动调仓",
    "自动调整",
    "自动配置",
    "自动再平衡",
    "无需人工干预",
    "外部数据源",
    "实时市场规则模型",
    "实时市场数据",
    "实时生成",
    "机构资金净流入",
    "利率变动对市场波动率影响系数",
    "风险评分",
    "完成3次",
    "重新校准模型参数",
    "可适度优化持仓",
    "可适度优化科技股持仓",
    "维持现有配置",
    "严格执行策略",
    "严格执行纪律化定投",
    "严格执行纪律化定投和再平衡策略",
    "估值显著提升",
    "历史高位",
    "核心AI公司正快速实现收入增长",
    "整体市场健康度合理",
    "Q3财报",
]

REPAIRABLE_FORBIDDEN_ANSWER_PATTERNS = [
    pattern
    for pattern in FORBIDDEN_ANSWER_PATTERNS
    if pattern not in set(SEVERE_FORBIDDEN_ANSWER_PATTERNS)
]

SEVERE_HALLUCINATION_MARKERS = (
    "2023-10-27",
    "14:30",
    "过去30天热度指数",
    "过去 30 天热度指数",
    "阈值0.7",
    "阈值 0.7",
    "阈值0.6",
    "阈值 0.6",
    "阈值0.5",
    "阈值 0.5",
    "风险指数 = 0.55",
    "风险指数=0.55",
    "标普目标40%",
    "标普目标 40%",
    "标普500目标40%",
    "标普500目标 40%",
    "纳指目标35%",
    "纳指目标 35%",
    "纳斯达克目标35%",
    "纳斯达克目标 35%",
    "短债目标35%",
    "短债目标 35%",
    "黄金目标20%",
    "黄金目标 20%",
    "$1,000,000",
    "$200,000",
    "Target Value of Short-Term Bonds",
    "portfolio value is",
    "Final Answer: $",
    "用户确认的实时快照",
    "请提供更详细的上下文",
    "规则第",
    "自动执行",
    "自动归类",
    "唯一当前状态",
    "可操作状态",
    "模型推荐基准",
    "70% 持仓权重",
    "需人工复核数据",
    "交易量",
    "模型预测",
    "投资者保持灵活配置",
    "实时响应能力",
    "模拟数据",
    "实时数据为准",
    "动态调整",
    "pattern of repetitive",
    "not a real query",
    "just a pattern",
    "casual chat",
    "What would you like",
    "feel free to rephrase",
    "The current market condition",
    "slightly overheated",
    "Key Observations",
    "live data feeds",
    "financial advisor",
    "Always verify",
    "This response is generated",
    "😊",
    "🛠️",
    "自动调整机制",
    "配置需求不足",
    "过度抛售",
    "资金短期流入",
    "当前市场处于过热状态",
    "2023-10-05",
    "2023年10月",
    "2023年GDP",
    "2024Q",
    "2024-2025",
    "2025年中",
    "市盈率",
    "PE=",
    "AI相关板块",
    "生成式AI",
    "欧盟AI法案",
    "GDP增速",
    "半导体产业链",
    "现金流增长",
    "AI主题ETF",
    "QQQ",
    "Eclipse",
    "行业基准",
    "公开数据",
    "换50%的确定性",
)

THINKING_RESIDUE_PATTERNS = (
    "<think>",
    "</think>",
    "Thinking Process",
    "Thinking...",
    "done thinking",
)

def validate_answer_text(
    answer: str,
    user_question: str = "",
    context_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    warnings = []
    if not answer:
        return {
            "status": "not_applicable",
            "warnings": warnings,
        }

    context_json = context_json or {}
    guardrail_assessment = _assess_answer_guardrails(
        answer,
        find_holdings_source(context_json),
    )
    for trigger in guardrail_assessment.get("triggers", []):
        action = trigger.get("action", "repair")
        label = "Severe guardrail" if action == "context_only_fallback" else "Repairable guardrail"
        warnings.append(f"{label} trigger: {trigger.get('pattern')}")

    if "风险水平" in answer and "中性" in answer:
        warnings.append("risk_level=medium should be described as 中等 or medium, not 中性.")

    amount_patterns = [
        r"买入\s*[\d,]+(?:\.\d+)?\s*(?:元|人民币|块)",
        r"卖出\s*[\d,]+(?:\.\d+)?\s*(?:元|人民币|块)",
    ]
    for pattern in amount_patterns:
        for match in re.finditer(pattern, answer):
            if _is_negated_or_boundary_context(answer, match.start()):
                continue
            warnings.append(f"Forbidden trade amount pattern detected: {pattern}")
            break

    holdings_source = find_holdings_source(context_json)
    if holdings_source.get("mode"):
        ignore_portfolio_patterns = [
            r"未提供您的投资组合",
            r"没有提供投资组合",
            r"无法评估.*组合",
            r"缺乏.*组合",
            r"未包含.*组合",
        ]
        for pattern in ignore_portfolio_patterns:
            if re.search(pattern, answer):
                warnings.append("Answer appears to ignore portfolio facts.")
                break

    question_lower = user_question.lower()
    answer_lower = answer.lower()
    if "组合" in user_question:
        portfolio_keywords = [
            "sp500",
            "nasdaq100",
            "short_bond",
            "gold",
            "标普",
            "纳斯达克",
            "短债",
            "短期债券",
            "黄金",
            "underweight",
            "overweight",
            "低配",
            "高配",
            "相对目标偏低",
            "相对目标偏高",
        ]
        if not any(keyword in answer_lower or keyword in answer for keyword in portfolio_keywords):
            warnings.append("Answer does not reference portfolio allocation facts.")

        if holdings_source.get("mode") in {"current_holdings", "user_current_holdings", "real_holdings"}:
            if "sample_fallback" in answer or "样本数据" in answer or "示例持仓" in answer:
                warnings.append("Answer incorrectly describes current_holdings as sample_fallback/sample data.")

            source_keywords = [
                "current_holdings",
                "本地",
                "快照",
                "手动",
                "不保证实时",
            ]
            if not any(keyword in answer_lower or keyword in answer for keyword in source_keywords):
                warnings.append("Answer does not reference current_holdings local snapshot source.")

            exact_weight_keywords = ["29.88", "12.65", "35.83", "21.64"]
            if not any(keyword in answer for keyword in exact_weight_keywords):
                warnings.append("Answer does not cite current portfolio weight facts.")

    if "过热" in user_question:
        market_keywords = [
            "warm_but_macro_sensitive",
            "equity_temperature",
            "risk_level",
            "偏热",
            "过热",
        ]
        if not any(keyword in answer_lower or keyword in answer for keyword in market_keywords):
            warnings.append("Answer does not reference market temperature facts.")

        overall_regime = find_overall_regime(context_json)
        if overall_regime == "warm_but_macro_sensitive":
            if "warm_but_macro_sensitive" not in answer_lower and "偏热但宏观敏感" not in answer:
                warnings.append("Answer must state warm_but_macro_sensitive / 偏热但宏观敏感.")
            if "未过热" in answer or "无明显过热" in answer:
                warnings.append("Answer contradicts warm_but_macro_sensitive by saying 未过热 or 无明显过热.")

    return {
        "status": "warning" if warnings else "ok",
        "warnings": _dedupe_strings(warnings),
    }

def apply_deterministic_answer_guardrails(
    answer: str,
    context_pack: dict[str, Any],
    user_question: str = "",
    answer_style: str = "standard",
    eval_case: dict[str, Any] | None = None,
) -> dict[str, Any]:
    notes = []
    updated = answer.strip()
    context_json = context_pack.get("context_json", {}) if isinstance(context_pack, dict) else {}
    holdings_source = find_holdings_source(context_json)

    if holdings_source.get("mode") == "sample_fallback" and not _mentions_sample_fallback(updated):
        prefix = (
            "重要说明：当前账户数据来自 sample_fallback（示例持仓），不是真实账户数据；"
            "以下内容只基于 context pack 做本地研究说明，不构成投资建议。\n\n"
        )
        updated = prefix + updated
        notes.append("Prepended required sample_fallback warning.")

    guardrail_assessment = _assess_answer_guardrails(updated, holdings_source)
    if guardrail_assessment.get("action") == "context_only_fallback":
        safe_answer = build_context_only_safe_answer(
            context_json,
            user_question,
            answer_style=answer_style,
            eval_case=eval_case,
        )
        if safe_answer:
            return {
                "answer": safe_answer,
                "notes": [
                    "Replaced model answer with deterministic context-only answer.",
                    *[
                        f"Guardrail trigger: {trigger.get('kind')}={trigger.get('pattern')}"
                        for trigger in guardrail_assessment.get("triggers", [])
                    ],
                ],
                "answer_mode": "context_only_fallback",
                "fallback_reason": guardrail_assessment.get("reason"),
                "guardrail_action": guardrail_assessment.get("action"),
                "guardrail_triggers": guardrail_assessment.get("triggers", []),
            }

    rewritten = _rewrite_trade_directive_wording(updated)
    if rewritten != updated:
        updated = rewritten
        notes.append("Rewrote trade-directive wording into observation-frame wording.")

    facts_block = build_required_portfolio_facts_appendix(context_json, user_question, updated)
    if facts_block:
        updated = updated.rstrip() + "\n\n" + facts_block
        notes.append("Appended required current-holdings portfolio facts.")

    regime_block = build_required_market_regime_prefix(context_json, user_question, updated)
    if regime_block:
        updated = regime_block + "\n\n" + updated.lstrip()
        notes.append("Prepended required market regime wording.")

    final_assessment = _assess_answer_guardrails(updated, holdings_source)
    if final_assessment.get("action") == "context_only_fallback":
        safe_answer = build_context_only_safe_answer(
            context_json,
            user_question,
            answer_style=answer_style,
            eval_case=eval_case,
        )
        if safe_answer:
            return {
                "answer": safe_answer,
                "notes": [
                    *notes,
                    "Replaced rewritten answer with deterministic context-only answer.",
                    *[
                        f"Guardrail trigger: {trigger.get('kind')}={trigger.get('pattern')}"
                        for trigger in final_assessment.get("triggers", [])
                    ],
                ],
                "answer_mode": "context_only_fallback",
                "fallback_reason": final_assessment.get("reason"),
                "guardrail_action": final_assessment.get("action"),
                "guardrail_triggers": final_assessment.get("triggers", []),
            }

    return {
        "answer": updated,
        "notes": [
            *notes,
            *[
                f"Repairable guardrail trigger remains: {trigger.get('pattern')}"
                for trigger in final_assessment.get("triggers", [])
                if trigger.get("action") == "repair"
            ],
        ],
        "answer_mode": "natural",
        "guardrail_action": final_assessment.get("action"),
        "guardrail_triggers": final_assessment.get("triggers", []),
    }

def _mentions_sample_fallback(answer: str) -> bool:
    lower = answer.lower()
    return (
        "sample_fallback" in lower
        or "示例持仓" in answer
        or "不是真实账户" in answer
        or "非真实账户" in answer
    )

def _rewrite_trade_directive_wording(answer: str) -> str:
    replacements = (
        ("## 操作建议", "## 观察框架"),
        ("# 操作建议", "# 观察框架"),
        ("操作建议", "观察框架"),
        ("推荐行动（基于规则逻辑）", "观察方向（基于规则逻辑）"),
        ("推荐行动", "观察方向"),
        ("具体调整方案", "观察框架"),
        ("转为更稳健的债券配置", "作为后续定投和再平衡观察方向"),
        ("转为更稳健配置", "作为后续定投和再平衡观察方向"),
        ("转为更稳健", "作为后续定投和再平衡观察"),
        ("建议逐步增加配置", "相对目标偏低，可作为后续定投和再平衡观察方向"),
        ("逐步增加配置", "相对目标偏低，作为后续定投和再平衡观察方向"),
        ("建议优先补仓", "相对目标偏低，可作为后续定投观察方向"),
        ("优先补仓", "作为后续定投观察方向"),
        ("补仓", "后续定投观察"),
        ("减仓", "再平衡观察"),
        ("持仓调整", "再平衡评估"),
        ("配置不足", "相对目标偏低"),
        ("配置过重", "相对目标偏高"),
        ("偏差修正逻辑", "偏差观察逻辑"),
        ("建议直接对应", "观察框架对应"),
        ("可考虑逐步减持", "可在后续定投和再平衡时观察"),
        ("可以考虑逐步减持", "可以在后续定投和再平衡时观察"),
        ("逐步减持", "后续定投和再平衡时观察"),
        ("可考虑短期增持", "可在后续定投和再平衡时观察"),
        ("可以考虑短期增持", "可以在后续定投和再平衡时观察"),
        ("短期增持", "后续定投和再平衡时观察"),
        ("应买入", "作为后续观察方向"),
        ("应卖出", "作为后续观察方向"),
        ("立即调整", "等待年度/阈值再平衡评估"),
        ("需增加持仓", "相对目标偏低"),
        ("需增加配置", "相对目标偏低"),
        ("需减少配置", "相对目标偏高"),
        ("需减持", "相对目标偏高"),
        ("减持", "再平衡观察"),
        ("增持", "再平衡观察"),
        ("优化建议", "观察方向"),
        ("建议行动", "观察方向"),
        ("适度增配", "作为后续复核观察"),
        ("小幅增配", "作为后续复核观察"),
        ("动态调减", "作为后续复核观察"),
        ("调减", "复核观察"),
    )
    updated = answer
    for source, target in replacements:
        updated = updated.replace(source, target)
    updated = re.sub(
        r"目标[:：]\s*提升至目标比例\+?\d+(?:\.\d+)?%",
        "观察：相对目标偏低",
        updated,
    )
    updated = re.sub(
        r"再平衡观察\d+(?:\.\d+)?%[-–]\d+(?:\.\d+)?%",
        "等待年度/阈值再平衡评估",
        updated,
    )
    updated = re.sub(
        r"再平衡观察\d+(?:\.\d+)?%",
        "等待年度/阈值再平衡评估",
        updated,
    )
    return updated

def _answer_requires_context_only_fallback(answer: str, holdings_source: dict[str, Any]) -> bool:
    return _assess_answer_guardrails(answer, holdings_source).get("action") == "context_only_fallback"

def _assess_answer_guardrails(answer: str, holdings_source: dict[str, Any]) -> dict[str, Any]:
    triggers = _answer_guardrail_triggers(answer, holdings_source)
    severe_triggers = [
        trigger for trigger in triggers if trigger.get("action") == "context_only_fallback"
    ]
    if severe_triggers:
        return {
            "action": "context_only_fallback",
            "reason": "severe_hallucination_or_forbidden_output",
            "triggers": severe_triggers,
        }

    repair_triggers = [trigger for trigger in triggers if trigger.get("action") == "repair"]
    if repair_triggers:
        return {
            "action": "repair",
            "reason": "repairable_guardrail_issues",
            "triggers": repair_triggers,
        }

    return {
        "action": "natural_keep",
        "reason": None,
        "triggers": [],
    }

def _answer_guardrail_triggers(
    answer: str,
    holdings_source: dict[str, Any],
) -> list[dict[str, Any]]:
    triggers: list[dict[str, Any]] = []

    for pattern in THINKING_RESIDUE_PATTERNS:
        triggers.extend(
            _pattern_triggers(
                answer,
                pattern,
                kind="thinking_residue",
                action="context_only_fallback",
                respect_negation=False,
            )
        )

    for pattern in SEVERE_HALLUCINATION_MARKERS:
        triggers.extend(
            _pattern_triggers(
                answer,
                pattern,
                kind="severe_hallucination_marker",
                action="context_only_fallback",
            )
        )

    if _misstates_current_holdings_as_sample(answer, holdings_source):
        triggers.append(
            {
                "kind": "holdings_source_misstatement",
                "pattern": "current_holdings_as_sample",
                "action": "context_only_fallback",
                "snippet": _snippet(answer, answer.find("sample_fallback")),
            }
        )

    if re.search(r"[\u0590-\u05ff]", answer):
        triggers.append(
            {
                "kind": "unexpected_script",
                "pattern": "hebrew_script",
                "action": "context_only_fallback",
                "snippet": "",
            }
        )
    severe_amount_patterns = (
        r"买入\s*[\d,]+(?:\.\d+)?\s*(?:元|人民币|块)?",
        r"卖出\s*[\d,]+(?:\.\d+)?\s*(?:元|人民币|块)?",
        r"加杠杆做空",
    )
    for pattern in severe_amount_patterns:
        for match in re.finditer(pattern, answer):
            if _is_negated_or_boundary_context(answer, match.start()):
                continue
            triggers.append(
                {
                    "kind": "explicit_trade_command",
                    "pattern": pattern,
                    "action": "context_only_fallback",
                    "snippet": _snippet(answer, match.start()),
                }
            )

    current_yield_point_patterns = (
        r"(?:美债收益率|10年期美债收益率|十年期美债收益率|treasury yield)[^。；\n]{0,32}\d+(?:\.\d+)?%",
        r"(?:当前|现在|最新)[^。；\n]{0,24}(?:美债|收益率|treasury yield)[^。；\n]{0,24}\d+(?:\.\d+)?%",
    )
    for pattern in current_yield_point_patterns:
        for match in re.finditer(pattern, answer, flags=re.IGNORECASE):
            if _is_negated_or_boundary_context(answer, match.start()):
                continue
            triggers.append(
                {
                    "kind": "invented_current_market_point",
                    "pattern": pattern,
                    "action": "context_only_fallback",
                    "snippet": _snippet(answer, match.start()),
                }
            )

    for pattern in SEVERE_FORBIDDEN_ANSWER_PATTERNS:
        triggers.extend(
            _pattern_triggers(
                answer,
                pattern,
                kind="severe_forbidden_phrase",
                action="context_only_fallback",
            )
        )

    for pattern in REPAIRABLE_FORBIDDEN_ANSWER_PATTERNS:
        triggers.extend(
            _pattern_triggers(
                answer,
                pattern,
                kind="repairable_phrase",
                action="repair",
            )
        )

    return _dedupe_triggers(triggers)

def _pattern_triggers(
    answer: str,
    pattern: str,
    kind: str,
    action: str,
    respect_negation: bool = True,
) -> list[dict[str, Any]]:
    if not pattern:
        return []

    triggers = []
    for match in re.finditer(re.escape(pattern), answer, flags=re.IGNORECASE):
        if respect_negation and _is_negated_or_boundary_context(answer, match.start()):
            continue
        triggers.append(
            {
                "kind": kind,
                "pattern": pattern,
                "action": action,
                "snippet": _snippet(answer, match.start()),
            }
        )
    return triggers

def _dedupe_triggers(triggers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for trigger in triggers:
        identity = (
            trigger.get("kind"),
            trigger.get("pattern"),
            trigger.get("action"),
            trigger.get("snippet"),
        )
        if identity in seen:
            continue
        seen.add(identity)
        result.append(trigger)
    return result

def _snippet(answer: str, start: int, radius: int = 36) -> str:
    if start < 0:
        return ""
    begin = max(0, start - radius)
    end = min(len(answer), start + radius)
    return answer[begin:end].replace("\n", " ").strip()

def _has_forbidden_answer_pattern(answer: str, pattern: str) -> bool:
    if not pattern:
        return False
    for match in re.finditer(re.escape(pattern), answer, flags=re.IGNORECASE):
        if _is_negated_or_boundary_context(answer, match.start()):
            continue
        return True
    return False

def _is_negated_or_boundary_context(answer: str, start: int) -> bool:
    prefix = answer[max(0, start - 32) : start]
    sentence_prefix = answer[max(0, start - 120) : start]
    for separator in ("。", "！", "？", "\n", "；", ";"):
        if separator in sentence_prefix:
            sentence_prefix = sentence_prefix.rsplit(separator, 1)[-1]
    safe_prefixes = (
        "不",
        "不要",
        "不能",
        "不可",
        "不得",
        "并非",
        "不是",
        "禁止",
        "避免",
        "不提供",
        "不给",
        "不输出",
        "不使用",
        "不写",
        "不能给",
        "不构成",
        "不等于",
        "不是要",
        "并不",
        "未",
        "无",
        "拒绝",
        "禁止编造",
        "不能编造",
        "不得编造",
        "不要编造",
    )
    return any(marker in prefix or marker in sentence_prefix for marker in safe_prefixes)

def _answer_has_hallucination_markers(answer: str) -> bool:
    if any(
        _pattern_triggers(
            answer,
            marker,
            kind="severe_hallucination_marker",
            action="context_only_fallback",
        )
        for marker in SEVERE_HALLUCINATION_MARKERS
    ):
        return True
    return bool(re.search(r"[\u0590-\u05ff]", answer))

def _misstates_current_holdings_as_sample(answer: str, holdings_source: dict[str, Any]) -> bool:
    if holdings_source.get("mode") not in {"current_holdings", "user_current_holdings", "real_holdings"}:
        return False
    for pattern in ("sample_fallback", "样本数据", "示例持仓"):
        for match in re.finditer(re.escape(pattern), answer, flags=re.IGNORECASE):
            if _is_negated_or_boundary_context(answer, match.start()):
                continue
            return True
    return False

def _dedupe_strings(items: list[str]) -> list[str]:
    result = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result

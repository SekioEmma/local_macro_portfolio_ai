from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class DeepSeekPromptPackage:
    messages: list[dict[str, str]]
    prompt_text: str
    prompt_chars: int
    prompt_preview: str
    validator_facts: dict[str, Any]
    context_mode: str

    def to_report_dict(self, *, save_full_prompt: bool = False) -> dict[str, Any]:
        payload = {
            "context_mode": self.context_mode,
            "prompt_chars": self.prompt_chars,
            "prompt_preview": self.prompt_preview,
            "validator_facts": self.validator_facts,
        }
        if save_full_prompt:
            payload["prompt_text"] = self.prompt_text
        return payload


def build_deepseek_prompt_package(
    *,
    question: str,
    answer_style: str,
    context_json: dict[str, Any],
    context_mode: str = "sanitized",
    prompt_preview_chars: int = 1200,
) -> DeepSeekPromptPackage:
    if context_mode not in {"sanitized", "full"}:
        raise ValueError("context_mode must be sanitized or full")

    facts = _extract_facts(context_json, context_mode=context_mode)
    system_message = (
        "你是长期资产配置和宏观投研助手。你的任务是基于提供的数据和明确标注的假设，"
        "生成自然、有逻辑、有条理的 analyst memo。你不能编造未提供的最新市场数据、"
        "机构来源或交易指令。"
    )
    user_payload = {
        "hard_boundaries": [
            "不编造未提供的数据。",
            "不引用未提供的 Reuters / FactSet / Bloomberg / FRED / FedWatch / Goldman 等来源。",
            "不输出具体买入/卖出金额。",
            "不说应买入、应卖出、清仓、等跌再买、立即调整、暂停定投、停止定投、加速买入、增配或减配某资产。",
            "不把 current_holdings.csv 说成实时账户同步。",
            "不把 cash reserve / 余额宝当成待配置资产。",
            "不预测短期点位。",
            "必须区分事实、推断、假设、不确定性。",
        ],
        "data_contract": {
            "provided_data": "以下 data_package 由本地系统确定性提供。",
            "missing_data": "未出现在 data_package 中的数据视为未提供，模型不能补编，也不能暗示已经查询外部实时数据。",
            "allowed_inference_scope": "可以基于已提供事实、一般宏观机制和长期配置原则做条件化分析。",
            "forbidden_inference": "不能把未提供的 PE、forward PE、CAPE、valuation percentile、FedWatch、Reuters、FactSet、Bloomberg、Goldman、credit spread、HYG spread、VIX、实时价格或机构观点写成事实。",
            "output_requirements": "若用户问题提到缺失数据，必须明确说本地 context 未提供这些数据，因此不能确认该项；以下只能从一般机制和已有数据出发分析。",
        },
        "data_package": facts["prompt_facts"],
        "user_question": {
            "style": answer_style,
            "question": question,
        },
        "reasoning_requirements": [
            "先给核心结论。",
            "然后给推理链条。",
            "必要时分情景。",
            "说明组合含义时使用相对风险暴露、观察方向、后续定投评估、阈值复核、年末复核、再平衡评估。",
            "不机械复述所有字段。",
            "不写成模板报告。",
            "自然回应用户真正担忧。",
            "对正常回调、危机、横盘消化、长期修复能力这类问题，要分层说明，而不是只给标签。",
        ],
        "asset_role_non_absolutism": [
            "short_bond 通常波动低于权益和长债，但不等于无风险，也可能受利率和流动性环境影响。",
            "gold 有时有避险属性，但也可能受实际利率、美元和流动性影响承压。",
            "bonds / gold / cash-like assets 不能被描述为必然对冲或必然受益。",
            "equity / Nasdaq / AI 不能被描述为必然长期上涨，也不能在证据不足时断言已失去修复能力。",
            "资产角色必须带条件、场景和不确定性。",
            "如果说黄金或短债在压力场景中更稳，必须写明条件：利率、实际利率、美元、流动性和信用风险环境可能改变其表现。",
            "不要写“更稳，甚至受益于避险流动”这类无条件判断；应改成“在部分风险情绪恶化场景中可能更稳，但并非必然受益”。",
        ],
        "dca_wording_rules": {
            "avoid": [
                "越跌越买",
                "趁跌多买",
                "加速买入",
                "停止定投",
                "暂停定投",
                "调仓",
                "降低权益",
                "增配债券",
                "60/40 等未经用户策略授权的新配置比例",
                "行动建议",
                "立即调整",
                "不要使用“越跌越买”这类原话，即使只是解释或概括。",
                "不要把原有定投计划解释成新的追加买入、加速买入或择时动作。",
            ],
            "preferred": [
                "如果既有定投规则继续执行，低配资产会在后续现金流中逐步接近目标权重。",
                "这是原有计划的执行效果，不是基于单次市场判断追加操作。",
                "组合含义应落在观察方向、后续定投评估、阈值复核、年末复核和再平衡评估。",
                "可以说“低配资产会在后续现金流中逐步接近目标权重”，但必须同时说明这是既有规则的机械执行效果。",
            ],
        },
        "output_style": [
            "中文。",
            "analyst_memo 风格。",
            "逻辑清晰，段落自然。",
            "不要机械列 checklist。",
            "不要为了安全反复重复免责声明。",
            "不要输出交易指令。",
        ],
        "final_self_check": [
            "是否使用了未提供的最新数据？",
            "是否编造了来源？",
            "是否给了交易指令？",
            "是否误用了 cash reserve？",
            "是否把本地快照当实时账户？",
            "是否说反了高配/低配方向？",
            "是否把持仓快照日期、市场观察日期或报告日期混在一起？",
            "只输出最终答案，不输出自检过程。",
        ],
    }
    user_message = json.dumps(user_payload, ensure_ascii=False, indent=2)
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message},
    ]
    prompt_text = system_message + "\n\n" + user_message
    return DeepSeekPromptPackage(
        messages=messages,
        prompt_text=prompt_text,
        prompt_chars=len(prompt_text),
        prompt_preview=prompt_text[:prompt_preview_chars],
        validator_facts=facts["validator_facts"],
        context_mode=context_mode,
    )


def _extract_facts(context_json: dict[str, Any], *, context_mode: str) -> dict[str, Any]:
    confirmed = _as_dict(context_json.get("confirmed_facts"))
    portfolio_facts = _as_dict(confirmed.get("portfolio"))
    portfolio = _as_dict(context_json.get("portfolio_context"))
    assessments = _as_dict(context_json.get("rule_based_assessments"))
    data_quality = _as_dict(context_json.get("data_quality"))
    market_facts = _as_dict(confirmed.get("market"))
    limitations = context_json.get("data_limitations")
    if not isinstance(limitations, list):
        limitations = []

    target_allocation = _round_percent_map(_as_dict(portfolio.get("target_allocation")))
    current_weights = _round_percent_map(_as_dict(portfolio.get("weights_ex_cash")))
    deviation = _round_pp_map(_as_dict(portfolio.get("deviation")))
    direction = {
        str(asset): str(flag)
        for asset, flag in _as_dict(portfolio.get("deviation_flags")).items()
        if flag is not None
    }
    dca_budget = _as_dict(portfolio.get("dca_budget_check"))
    dca_plan = _as_dict(portfolio.get("dca_daily_plan"))
    holdings_source = _as_dict(portfolio.get("holdings_source"))
    market_temperature = _as_dict(assessments.get("market_temperature"))
    macro_regime = _as_dict(assessments.get("macro_current_regime"))
    regime_classification = _as_dict(macro_regime.get("regime_classification"))
    generated_at = context_json.get("generated_at")
    holdings_snapshot_date = portfolio.get("holdings_updated_at") or portfolio_facts.get("holdings_updated_at")
    market_observation_dates = _market_source_timestamps(market_facts)
    missing_data = [
        "PE",
        "forward PE",
        "CAPE",
        "valuation percentile",
        "FedWatch probability",
        "Reuters",
        "FactSet",
        "Bloomberg",
        "Goldman",
        "credit spread",
        "HYG spread",
        "VIX",
        "real-time market prices",
    ]

    portfolio_package: dict[str, Any] = {
        "target_allocation": target_allocation,
        "current_allocation_direction": direction,
        "allocation_deviation_pp": deviation,
        "holdings_snapshot": {
            "source": "current_holdings.csv local manual snapshot",
            "updated_at": holdings_snapshot_date,
            "age_days": portfolio.get("holdings_age_days") or portfolio_facts.get("holdings_age_days"),
            "freshness": portfolio.get("holdings_freshness_status")
            or portfolio_facts.get("holdings_freshness_status"),
            "boundary": "not real-time account sync",
            "source_note": holdings_source.get("note"),
        },
        "cash_reserve_boundary": (
            "cash reserve / 余额宝 is a reserve and DCA deduction source; "
            "it does not participate in target allocation weights and is not automatically deployable capital."
        ),
        "dca_policy": _sanitize_dca(dca_budget, dca_plan, context_mode=context_mode),
        "data_limitations": [str(item) for item in limitations[:8]],
    }
    if context_mode == "full":
        portfolio_package.update(
            {
                "current_weights_ex_cash": current_weights,
                "portfolio_values": {
                    "total_account_value": portfolio_facts.get("total_account_value"),
                    "invested_asset_value": portfolio_facts.get("invested_asset_value"),
                    "cash_reserve_value": portfolio_facts.get("cash_reserve_value"),
                },
            }
        )
    else:
        portfolio_package["current_weights_ex_cash"] = "hidden in sanitized mode; use direction and deviation only"
        portfolio_package["portfolio_values"] = "hidden in sanitized mode"

    market_package = {
        "market_regime": regime_classification.get("regime_label")
        or macro_regime.get("current_regime_label"),
        "risk_level": _nested_get(market_temperature, ["overall_risk", "risk_level"])
        or _nested_get(market_temperature, ["risk_level"])
        or regime_classification.get("confidence"),
        "temperature": {
            "equity_temperature": _nested_get(market_temperature, ["equity_temperature", "level"]),
            "rate_pressure": _nested_get(market_temperature, ["rate_pressure", "level"]),
            "inflation_pressure": _nested_get(market_temperature, ["inflation_pressure", "level"]),
        },
        "market_snapshot_status": data_quality.get("market_snapshot_status"),
        "used_cache": data_quality.get("used_cache"),
        "source_timestamps": market_observation_dates,
        "missing_data_declaration": (
            "If PE, valuation multiples, real-time prices, FedWatch probabilities, or external analyst sources "
            "are not explicitly listed here, they are not provided."
        ),
    }
    if context_mode == "full":
        market_package["selected_market_observations"] = _selected_market_observations(market_facts)

    prompt_facts = {
        "context_mode": context_mode,
        "report_metadata": {
            "generated_at": generated_at,
            "report_date_rule": (
                "report_date can only come from generated_at or explicit report_metadata. "
                "holdings_snapshot_date is only the holdings snapshot date. "
                "market_data_observation_dates are only market data observation dates. "
                "Do not invent today, this month, or latest close dates; if no explicit report_date exists, do not write a specific report date."
            ),
            "holdings_snapshot_date": holdings_snapshot_date,
            "market_data_observation_dates": market_observation_dates,
        },
        "missing_data": missing_data,
        "portfolio_facts": portfolio_package,
        "market_facts": market_package,
    }
    validator_facts = {
        "allocation_direction": direction,
        "target_allocation": target_allocation,
        "context_mode": context_mode,
        "missing_data_terms": missing_data + ["估值", "收益率点位", "黄金价格", "信用利差"],
    }
    return {"prompt_facts": prompt_facts, "validator_facts": validator_facts}


def _sanitize_dca(
    dca_budget: dict[str, Any],
    dca_plan: dict[str, Any],
    *,
    context_mode: str,
) -> dict[str, Any]:
    if context_mode == "full":
        return {
            "budget_status": dca_budget.get("status"),
            "monthly_required": dca_budget.get("monthly_required"),
            "budget_range": dca_budget.get("budget_range"),
            "daily_plan": dca_plan,
        }
    return {
        "budget_status": dca_budget.get("status"),
        "budget_range": "hidden in sanitized mode",
        "monthly_required": "hidden in sanitized mode",
        "policy_boundary": "use DCA discipline and budget status; do not turn one market-temperature question into a pause command",
    }


def _market_source_timestamps(market_facts: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for key, value in market_facts.items():
        if not isinstance(value, dict):
            continue
        result[key] = {
            "observation_date": value.get("observation_date"),
            "source": value.get("source"),
            "status": value.get("status"),
        }
    return result


def _selected_market_observations(market_facts: dict[str, Any]) -> dict[str, Any]:
    selected = {}
    for key, value in market_facts.items():
        if not isinstance(value, dict):
            continue
        selected[key] = {
            "name": value.get("name"),
            "value": value.get("value"),
            "observation_date": value.get("observation_date"),
            "source": value.get("source"),
            "status": value.get("status"),
        }
    return selected


def _round_percent_map(values: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for key, value in values.items():
        number = _as_float(value)
        result[str(key)] = round(number * 100, 2) if number is not None else value
    return result


def _round_pp_map(values: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for key, value in values.items():
        number = _as_float(value)
        result[str(key)] = round(number * 100, 2) if number is not None else value
    return result


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _nested_get(value: dict[str, Any], path: list[str]) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

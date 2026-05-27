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
        "机构来源或交易指令。不要输出被禁止的交易化原词，即使是否定、引用或解释。"
    )
    user_payload = {
        "hard_boundaries": [
            "不编造未提供的数据。",
            "不引用未提供的 Reuters / FactSet / Bloomberg / FRED / FedWatch / Goldman 等来源。",
            "不输出具体买入/卖出金额。",
            "不说应买入、应卖出、清仓、等跌再买、立即调整、暂停定投、停止定投、加速买入、增配或减配某资产。",
            "不要出现“越跌越买”“趁跌多买”“行动建议”“调仓”“60/40”等交易化原词，即使是否定、引用或解释。",
            "不把 current_holdings.csv 说成实时账户同步。",
            "不把 cash reserve / 余额宝当成待配置资产。",
            "不预测短期点位。",
            "必须区分事实、推断、假设、不确定性。",
        ],
        "data_contract": {
            "provided_data": "以下 data_package 由本地系统确定性提供。",
            "missing_data": "未出现在 data_package 中的数据视为未提供，模型不能补编，也不能暗示已经查询外部实时数据。",
            "allowed_inference_scope": "可以基于已提供事实、一般宏观机制和长期配置原则做条件化分析。",
            "forbidden_inference": "不能把未提供的 PE、forward PE、CAPE、valuation percentile、FedWatch、Reuters、FactSet、Bloomberg、Goldman、实时价格或机构观点写成事实；credit spread、VIX、real yield、inflation expectation、yield curve、DGS2/DGS10/DGS30、CPI/PCE/PPI、WTI/Brent 只能在 data_package 明确提供时引用。",
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
            "不要用表格，不要用 checklist；用自然段 analyst memo，最多 3 个小标题。",
            "自然回应用户真正担忧。",
            "对正常回调、危机、横盘消化、长期修复能力这类问题，要分层说明，而不是只给标签。",
            "如果 financial_conditions 提供数据，必须在市场判断中引用至少部分 observation_date、source、freshness 或“基于本地 context 提供的最新观察日期”。",
        ],
        "financial_conditions_rules": [
            "可以基于 high_yield_spread、vix、real_yield_10y、breakeven_inflation_10y、yield_curve_10y2y 讨论正常回调、信用压力、横盘消化和系统性危机边界。",
            "如果 valuation_proxy status 不是 ok，不得写估值处于历史高位、PE 为 X、forward PE 为 X、CAPE 为 X 或类似估值事实。",
            "如果 fedwatch_probability status 不是 ok，不得写 FedWatch 显示 X% 或市场隐含降息概率为 X%。",
            "如果 high_yield_spread 可用，可以讨论信用压力是否升温，但不得把单一利差读数机械等同于危机。",
            "如果 VIX 可用，可以讨论波动率压力，但不得把 VIX 单点读数机械等同于买卖信号。",
            "所有市场判断必须引用 observation_date 或说明基于本地 context 提供的最新观察日期。",
        ],
        "rates_inflation_oil_rules": [
            "可以讨论 10Y / 30Y 是否接近 5%，但必须说明数据来自 FRED 日度观察，不代表盘中高点。",
            "如果用户说前几天收益率高于 5%，而 data package 只有 FRED daily，必须回答：当前数据包只能验证日度观察值和近期高点，不能验证盘中高点。",
            "可以讨论 CPI/PCE/PPI，但不能说超预期，除非 context 中提供 consensus / expected data。",
            "可以讨论 WTI/Brent 对通胀和利率的潜在传导，但不能机械等同于通胀失控。",
            "可以讨论油价、通胀、利率对标普、纳指、黄金、短债的条件化影响。",
            "不能编造 FedWatch 概率。",
            "不能编造 PE、forward PE、CAPE、FactSet、Bloomberg、Reuters。",
            "不能在缺失广度和集中度数据时确认 AI/巨头集中度恶化。",
            "组合含义只能落到相对目标、观察方向、后续定投评估、阈值复核、年末复核、再平衡评估。",
            "不输出交易指令。",
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
            "不要使用“买入”来描述后续现金流；改说“按既有规则执行”“逐步接近目标权重”或“继续观察”。",
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
            "少用项目符号；除非必须，不使用编号清单或 Markdown 表格。",
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
    financial_conditions = _financial_conditions_for_prompt(
        _as_dict(context_json.get("financial_conditions"))
    )
    market_data_package = _market_data_package_for_prompt(
        _as_dict(context_json.get("market_data_package"))
    )
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
    missing_data = _missing_data_terms(financial_conditions, market_data_package)

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
        "financial_conditions": financial_conditions,
        "market_data_package": market_data_package,
    }
    validator_facts = {
        "allocation_direction": direction,
        "target_allocation": target_allocation,
        "context_mode": context_mode,
        "missing_data_terms": missing_data + _missing_data_terms_cn(financial_conditions, market_data_package),
        "allowed_external_sources": _data_package_sources(financial_conditions, market_data_package),
        "provided_market_data_terms": _provided_market_data_terms(financial_conditions, market_data_package),
    }
    return {"prompt_facts": prompt_facts, "validator_facts": validator_facts}


def _financial_conditions_for_prompt(financial_conditions: dict[str, Any]) -> dict[str, Any]:
    raw_items = financial_conditions.get("items")
    if not isinstance(raw_items, list):
        raw_items = []

    items = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        items.append(
            {
                "key": item.get("key"),
                "name": item.get("name"),
                "value": item.get("value"),
                "unit": item.get("unit"),
                "observation_date": item.get("observation_date"),
                "source": item.get("source"),
                "source_tier": item.get("source_tier"),
                "freshness": item.get("freshness"),
                "status": item.get("status"),
                "error": item.get("error"),
                "interpretation_hint": item.get("interpretation_hint"),
                "risk_relevance": item.get("risk_relevance"),
            }
        )

    return {
        "section": "FINANCIAL CONDITIONS",
        "generated_at": financial_conditions.get("generated_at"),
        "items": items,
        "data_limitations": _as_list_of_str(financial_conditions.get("data_limitations")),
        "interpretation_boundaries": _as_list_of_str(
            financial_conditions.get("interpretation_boundaries")
        ),
        "usage_boundary": (
            "Use only items with status=ok as factual market data. For status not_available, "
            "not_configured, missing, or error, state the limitation instead of inferring a value."
        ),
    }


def _market_data_package_for_prompt(package: dict[str, Any]) -> dict[str, Any]:
    return {
        "section": "RATES / INFLATION / OIL DATA",
        "generated_at": package.get("generated_at"),
        "data_cutoff": package.get("data_cutoff"),
        "treasury_yields": _package_group_for_prompt(package.get("treasury_yields")),
        "inflation_indicators": _package_group_for_prompt(package.get("inflation_indicators")),
        "oil_and_energy": _package_group_for_prompt(package.get("oil_and_energy")),
        "existing_financial_conditions": _package_group_for_prompt(
            package.get("existing_financial_conditions")
        ),
        "unavailable_or_research_needed": _package_group_for_prompt(
            package.get("unavailable_or_research_needed")
        ),
        "market_analysis_framework": _as_dict(package.get("market_analysis_framework")),
        "market_regime_classification_rules": _as_dict(
            package.get("market_regime_classification_rules")
        ),
        "data_limitations": _as_list_of_str(package.get("data_limitations")),
        "interpretation_boundaries": _as_list_of_str(package.get("interpretation_boundaries")),
        "usage_boundary": (
            "Use only status=ok items as factual market data. FRED DGS10/DGS30 are daily "
            "observations, not intraday highs. Missing valuation, FedWatch, consensus CPI/PPI, "
            "breadth, and concentration data must not be inferred."
        ),
    }


def _package_group_for_prompt(group: Any) -> dict[str, Any]:
    if not isinstance(group, dict):
        return {}
    return {
        str(key): _package_item_for_prompt(item)
        for key, item in group.items()
        if isinstance(item, dict)
    }


def _package_item_for_prompt(item: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "key",
        "name",
        "value",
        "unit",
        "observation_date",
        "source",
        "source_tier",
        "freshness",
        "status",
        "error",
        "interpretation_hint",
        "risk_relevance",
        "derived_from",
        "source_series",
        "window_days",
        "high_date",
        "intraday_high_available",
        "calculation",
        "change_abs",
        "change_pct",
        "old_value",
        "old_observation_date",
    )
    return {key: item.get(key) for key in keys if key in item}


def _missing_data_terms(
    financial_conditions: dict[str, Any],
    market_data_package: dict[str, Any],
) -> list[str]:
    missing_data = [
        "PE",
        "forward PE",
        "CAPE",
        "valuation percentile",
        "Reuters",
        "FactSet",
        "Bloomberg",
        "Goldman",
        "HYG spread",
        "real-time market prices",
    ]
    statuses = _financial_condition_statuses(financial_conditions)
    package_statuses = _package_statuses(market_data_package)
    if statuses.get("valuation_proxy") != "ok":
        missing_data.extend(["valuation proxy", "valuation multiples"])
    if statuses.get("fedwatch_probability") != "ok":
        missing_data.append("FedWatch probability")
    if statuses.get("high_yield_spread") != "ok":
        missing_data.extend(["credit spread", "high yield spread"])
    if statuses.get("vix") != "ok":
        missing_data.append("VIX")
    if statuses.get("real_yield_10y") != "ok":
        missing_data.append("10-year real yield")
    if statuses.get("breakeven_inflation_10y") != "ok":
        missing_data.append("10-year breakeven inflation")
    if statuses.get("yield_curve_10y2y") != "ok":
        missing_data.append("10Y-2Y yield curve")
    for key, terms in {
        "ppi_final_demand": ["PPI final demand"],
        "forward_pe": ["forward PE"],
        "cape": ["CAPE"],
        "earnings_revision": ["earnings revision"],
        "market_breadth": ["market breadth"],
        "equal_weight_vs_cap_weight": ["equal weight vs cap weight"],
        "mega_cap_concentration": ["mega-cap concentration"],
        "intraday_treasury_high": ["intraday Treasury high", "intraday high"],
        "consensus_cpi": ["consensus CPI", "CPI surprise"],
        "consensus_ppi": ["consensus PPI", "PPI surprise"],
    }.items():
        if package_statuses.get(key) != "ok":
            missing_data.extend(terms)
    return _dedupe_strings(missing_data)


def _missing_data_terms_cn(
    financial_conditions: dict[str, Any],
    market_data_package: dict[str, Any],
) -> list[str]:
    statuses = _financial_condition_statuses(financial_conditions)
    package_statuses = _package_statuses(market_data_package)
    terms = ["估值", "收益率点位", "黄金价格"]
    if statuses.get("fedwatch_probability") != "ok":
        terms.extend(["FedWatch", "降息概率"])
    if statuses.get("valuation_proxy") != "ok":
        terms.extend(["市盈率", "估值倍数"])
    if statuses.get("high_yield_spread") != "ok":
        terms.append("信用利差")
    if statuses.get("vix") != "ok":
        terms.append("VIX")
    if package_statuses.get("intraday_treasury_high") != "ok":
        terms.extend(["盘中高点", "盘中突破"])
    if package_statuses.get("consensus_cpi") != "ok":
        terms.extend(["CPI超预期", "CPI 超预期"])
    if package_statuses.get("consensus_ppi") != "ok":
        terms.extend(["PPI超预期", "PPI 超预期"])
    if package_statuses.get("market_breadth") != "ok":
        terms.append("市场广度")
    if package_statuses.get("mega_cap_concentration") != "ok":
        terms.append("巨头集中度")
    return _dedupe_strings(terms)


def _financial_condition_statuses(financial_conditions: dict[str, Any]) -> dict[str, str]:
    statuses = {}
    items = financial_conditions.get("items")
    if not isinstance(items, list):
        return statuses
    for item in items:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if key:
            statuses[str(key)] = str(item.get("status") or "")
    return statuses


def _item_is_provided_market_data(item: Any) -> bool:
    return (
        isinstance(item, dict)
        and item.get("status") == "ok"
        and item.get("value") is not None
        and not item.get("error")
    )


def _financial_condition_available(financial_conditions: dict[str, Any]) -> dict[str, bool]:
    available = {}
    items = financial_conditions.get("items")
    if not isinstance(items, list):
        return available
    for item in items:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if key:
            available[str(key)] = _item_is_provided_market_data(item)
    return available


def _data_package_sources(
    financial_conditions: dict[str, Any],
    market_data_package: dict[str, Any],
) -> list[str]:
    sources = []
    items = financial_conditions.get("items")
    if isinstance(items, list):
        for item in items:
            if not _item_is_provided_market_data(item):
                continue
            source = item.get("source")
            if source:
                sources.extend(_source_aliases(str(source)))
    for group_name in (
        "treasury_yields",
        "inflation_indicators",
        "oil_and_energy",
        "existing_financial_conditions",
    ):
        group = market_data_package.get(group_name)
        if not isinstance(group, dict):
            continue
        for item in group.values():
            if not _item_is_provided_market_data(item):
                continue
            source = item.get("source")
            if source:
                sources.extend(_source_aliases(str(source)))
    return _dedupe_strings(sources)


def _source_aliases(source: str) -> list[str]:
    if source.upper().startswith("FRED"):
        return [source, "FRED"]
    return [source]


def _provided_market_data_terms(
    financial_conditions: dict[str, Any],
    market_data_package: dict[str, Any],
) -> list[str]:
    available = _financial_condition_available(financial_conditions)
    terms = []
    if available.get("high_yield_spread"):
        terms.extend(["high_yield_spread", "high yield", "credit spread", "信用利差", "高收益"])
    if available.get("vix"):
        terms.extend(["vix", "VIX", "波动率"])
    if available.get("real_yield_10y"):
        terms.extend(["real_yield_10y", "real yield", "实际利率", "实际收益率", "10年期实际利率", "TIPS"])
    if available.get("breakeven_inflation_10y"):
        terms.extend(["breakeven", "盈亏平衡通胀", "通胀预期"])
    if available.get("yield_curve_10y2y"):
        terms.extend(["yield_curve_10y2y", "10Y-2Y", "10年-2年", "收益率曲线"])
    package_available = _package_available(market_data_package)
    if package_available.get("nominal_yield_2y"):
        terms.extend(["DGS2", "nominal_yield_2y", "nominal yield", "名义收益率", "2年期美债收益率"])
    if package_available.get("nominal_yield_10y"):
        terms.extend(["DGS10", "nominal_yield_10y", "10-year Treasury yield", "10年期美债收益率", "10Y"])
    if package_available.get("nominal_yield_30y"):
        terms.extend(["DGS30", "nominal_yield_30y", "30-year Treasury yield", "30年期美债收益率", "30Y"])
    for key in ("dgs10_30d_high", "dgs10_60d_high", "dgs30_30d_high", "dgs30_60d_high"):
        if package_available.get(key):
            terms.append(key)
            terms.append("recent high")
            terms.append("近期高点")
    for key in ("dgs10_distance_to_5pct", "dgs30_distance_to_5pct", "dgs10_above_5pct", "dgs30_above_5pct"):
        if package_available.get(key):
            terms.extend([key, "5%", "5 percent", "5%阈值"])
    if package_available.get("headline_cpi"):
        terms.extend(["CPI", "headline CPI", "CPIAUCSL"])
    if package_available.get("core_cpi"):
        terms.extend(["core CPI", "CPILFESL"])
    if package_available.get("headline_pce"):
        terms.extend(["PCE", "headline PCE", "PCEPI"])
    if package_available.get("core_pce"):
        terms.extend(["core PCE", "PCEPILFE"])
    if package_available.get("ppi_all_commodities"):
        terms.extend(["PPIACO", "PPI", "all commodities PPI"])
    if package_available.get("wti_oil"):
        terms.extend(["WTI", "oil", "原油", "DCOILWTICO"])
    if package_available.get("brent_oil"):
        terms.extend(["Brent", "oil", "原油", "DCOILBRENTEU"])
    if package_available.get("wti_oil_30d_change"):
        terms.extend(["wti_oil_30d_change", "oil_30d_change", "30d oil change"])
    if package_available.get("brent_oil_30d_change"):
        terms.extend(["brent_oil_30d_change", "oil_30d_change", "30d oil change"])
    return _dedupe_strings(terms)


def _package_statuses(market_data_package: dict[str, Any]) -> dict[str, str]:
    statuses = {}
    for group_name in (
        "treasury_yields",
        "inflation_indicators",
        "oil_and_energy",
        "existing_financial_conditions",
        "unavailable_or_research_needed",
    ):
        group = market_data_package.get(group_name)
        if not isinstance(group, dict):
            continue
        for key, item in group.items():
            if isinstance(item, dict):
                statuses[str(key)] = str(item.get("status") or "")
    return statuses


def _package_available(market_data_package: dict[str, Any]) -> dict[str, bool]:
    available = {}
    for group_name in (
        "treasury_yields",
        "inflation_indicators",
        "oil_and_energy",
        "existing_financial_conditions",
        "unavailable_or_research_needed",
    ):
        group = market_data_package.get(group_name)
        if not isinstance(group, dict):
            continue
        for key, item in group.items():
            available[str(key)] = _item_is_provided_market_data(item)
    return available


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


def _as_list_of_str(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _dedupe_strings(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


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

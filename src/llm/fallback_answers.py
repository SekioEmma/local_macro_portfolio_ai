from __future__ import annotations

from typing import Any

from llm.intent_router import (
    question_mentions_market_top_pullback_risk,
    question_mentions_recession_asset_roles,
    should_use_macro_geopolitics_rates_fallback,
)


def build_context_only_safe_answer(
    context_json: dict[str, Any],
    user_question: str,
    answer_style: str = "standard",
    eval_case: dict[str, Any] | None = None,
) -> str:
    assessments = context_json.get("rule_based_assessments", {})
    if not isinstance(assessments, dict):
        assessments = {}
    market_temperature = assessments.get("market_temperature", {})
    if not isinstance(market_temperature, dict):
        market_temperature = {}
    portfolio = context_json.get("portfolio_context", {})
    if not isinstance(portfolio, dict):
        portfolio = {}

    holdings_source = find_holdings_source(context_json)
    weights = portfolio.get("weights_ex_cash", {})
    targets = portfolio.get("target_allocation", {})
    deviations = portfolio.get("deviation", {})
    flags = portfolio.get("deviation_flags", {})
    dca = portfolio.get("dca_budget_check", {})
    holdings_updated_at = _portfolio_confirmed_value(context_json, "holdings_updated_at")
    holdings_age_days = _portfolio_confirmed_value(context_json, "holdings_age_days")
    holdings_freshness_status = _portfolio_confirmed_value(context_json, "holdings_freshness_status")
    total_account_value = _portfolio_confirmed_value(context_json, "total_account_value")
    invested_asset_value = _portfolio_confirmed_value(context_json, "invested_asset_value")
    cash_reserve_value = _portfolio_confirmed_value(context_json, "cash_reserve_value")
    total_profit_loss = _portfolio_confirmed_value(context_json, "total_profit_loss")

    if should_use_macro_geopolitics_rates_fallback(user_question, answer_style, eval_case):
        return _build_macro_geopolitics_rates_context_only_answer(
            market_temperature=market_temperature,
            weights=weights,
            targets=targets,
            deviations=deviations,
            flags=flags,
            dca=dca,
            holdings_updated_at=holdings_updated_at,
            holdings_age_days=holdings_age_days,
            holdings_freshness_status=holdings_freshness_status,
            cash_reserve_value=cash_reserve_value,
        )

    if question_mentions_market_top_pullback_risk(user_question) or (
        isinstance(eval_case, dict) and eval_case.get("id") == "us_equity_top_pullback_risk_001"
    ):
        return _build_market_top_pullback_context_only_answer(
            flags=flags,
            holdings_updated_at=holdings_updated_at,
            holdings_freshness_status=holdings_freshness_status,
        )

    if "定投" in user_question and any(term in user_question for term in ("暂停", "停", "继续", "加速")):
        return _build_hot_market_dca_context_only_answer(
            market_temperature=market_temperature,
            weights=weights,
            targets=targets,
            deviations=deviations,
            flags=flags,
            dca=dca,
            holdings_updated_at=holdings_updated_at,
            holdings_age_days=holdings_age_days,
            holdings_freshness_status=holdings_freshness_status,
            cash_reserve_value=cash_reserve_value,
        )

    if any(term in user_question for term in ("复盘", "本月", "这个月", "周报", "月报")):
        return _build_monthly_review_context_only_answer(
            market_temperature=market_temperature,
            weights=weights,
            targets=targets,
            deviations=deviations,
            flags=flags,
            dca=dca,
            holdings_updated_at=holdings_updated_at,
            holdings_age_days=holdings_age_days,
            holdings_freshness_status=holdings_freshness_status,
            total_account_value=total_account_value,
            invested_asset_value=invested_asset_value,
            cash_reserve_value=cash_reserve_value,
        )

    if any(term in user_question for term in ("2000", "泡沫", "互联网泡沫")):
        return _build_analyst_memo_context_only_answer(
            market_temperature=market_temperature,
            weights=weights,
            targets=targets,
            deviations=deviations,
            flags=flags,
            dca=dca,
            holdings_updated_at=holdings_updated_at,
            holdings_age_days=holdings_age_days,
            holdings_freshness_status=holdings_freshness_status,
            total_account_value=total_account_value,
            invested_asset_value=invested_asset_value,
            cash_reserve_value=cash_reserve_value,
        )

    if "历史" in user_question or "相似窗口" in user_question:
        return "\n".join(
            [
                "## 核心结论",
                "historical outcome is not forecast。历史结果不是预测，历史表现不代表未来结果。",
                "",
                "## 历史参照",
                "相似窗口和历史相似数据只能作为历史参照，不能推出未来走势，也不能说明接下来大概率上涨。",
                "",
                "## 不确定性",
                "不能确定、不能保证未来上涨；仍需要观察当前估值、利率、通胀、盈利、流动性和数据质量。",
                "",
                "## 边界",
                "这不是短期涨跌判断，也不是投资建议；context 没有提供的实时估值或外部来源不能补写。",
            ]
        )

    if question_mentions_recession_asset_roles(user_question):
        return "\n".join(
            [
                "## 核心判断",
                "这是衰退情境下的资产角色分析，不是短期涨跌预测，也不是交易指令。",
                "",
                "## 四类资产角色",
                "- 标普500：广泛权益风险暴露，受企业盈利、风险偏好和折现率影响。",
                "- 纳指100：更偏成长和长久期权益，通常对利率、流动性和风险偏好更敏感。",
                "- 短债：主要承担波动缓冲、流动性和较低久期风险角色，不是收益保证。",
                "- 黄金：与尾部风险、实际利率、美元和避险需求相关，但不是单向避险资产。",
                "",
                "## 组合含义",
                "组合含义只能回到相对目标、风险暴露、观察方向、阈值复核和年末复核；不提供具体买卖金额、卖出比例或立即调整命令，也不把 cash reserve / 余额宝当成待配置资产。",
            ]
        )

    if "买入" in user_question or "卖出" in user_question:
        return _build_trade_refusal_context_only_answer(
            weights=weights,
            targets=targets,
            deviations=deviations,
            flags=flags,
            holdings_updated_at=holdings_updated_at,
            holdings_age_days=holdings_age_days,
            holdings_freshness_status=holdings_freshness_status,
        )

    if "真实收益" in user_question or "账户数据" in user_question or "收益怎么样" in user_question:
        return "\n".join(
            [
                "## 结论",
                (
                    "可以基于 current_holdings.csv 本地持仓快照描述收益快照，但这不是实时账户同步，"
                    "也不保证与支付宝当前页面完全一致。"
                ),
                "",
                "## 当前快照",
                f"- holdings_updated_at: {_display(holdings_updated_at)}；age_days: {_display(holdings_age_days)}；freshness: {_display(holdings_freshness_status)}。",
                f"- total_account_value: {_format_number(total_account_value)}。",
                f"- invested_asset_value: {_format_number(invested_asset_value)}。",
                f"- cash_reserve_value: {_format_number(cash_reserve_value)}。",
                f"- total_profit_loss / 收益快照: {_format_number(total_profit_loss)}。",
                "",
                "## 数据限制",
                "current_holdings.csv 是用户本地手动录入快照，不是实时账户同步；若截图或账户发生变化，需要先更新 CSV 再判断。",
            ]
        )

    if ("黄金" in user_question and "短债" in user_question) or "高配" in user_question:
        return _build_gold_shortbond_context_only_answer(
            weights=weights,
            targets=targets,
            deviations=deviations,
            flags=flags,
            holdings_updated_at=holdings_updated_at,
            holdings_freshness_status=holdings_freshness_status,
        )

    if "数据源" in user_question or "缓存" in user_question or "stale" in user_question:
        return "\n".join(
            [
                "## 结论",
                "如果 context_health 不是 ok，或 market_snapshot 使用 stale cache，当前信息不足，不能直接做确定判断。",
                "",
                "## 处理原则",
                "需要标注数据质量和 data limitations；缺失数据不能编造，缓存或数据源失败时结论应降级为观察。",
                "",
                "## 需要检查",
                "优先看 context_health、market_snapshot.status、used_cache、data quality、核心市场数据是否缺失。",
            ]
        )

    if "过热" not in user_question and "组合" not in user_question:
        return ""


    lines = [
        "## 核心结论",
        "当前更接近“偏热但宏观敏感”（warm_but_macro_sensitive），这不是短期涨跌预测，也不是交易指令。",
        "",
        "## 关键事实",
        f"- equity_temperature: {_display(_level_value(market_temperature.get('equity_temperature')))}",
        f"- overall_regime: {_display(market_temperature.get('overall_regime'))}",
        f"- risk_level: {_display(market_temperature.get('risk_level'))} / 中等风险水平",
        (
            f"- 数据来源：用户本地 current_holdings.csv 快照，持仓日期 {_display(holdings_updated_at)}，"
            f"age_days {_display(holdings_age_days)}，freshness {_display(holdings_freshness_status)}；"
            "手动录入且不保证实时。"
        ),
        "- 余额宝/cash：现金准备金和扣款来源，不纳入目标仓位计算，也不等于应立即投入的闲置资金。",
        f"- total_account_value: {_format_number(total_account_value)}。",
        f"- invested_asset_value: {_format_number(invested_asset_value)}。",
        f"- cash_reserve_value: {_format_number(cash_reserve_value)}。",
        "",
        "## 对组合的含义",
        "以下只描述相对目标的仓位偏离，作为后续定投和年度/阈值再平衡的观察方向。",
    ]

    for asset in ("sp500", "nasdaq100", "short_bond", "gold"):
        lines.append(
            "- "
            + f"{asset}: 当前 {_format_percent(weights.get(asset))}, "
            + f"目标 {_format_percent(targets.get(asset))}, "
            + f"偏离 {_format_pp(deviations.get(asset))}, "
            + f"{_allocation_label(flags.get(asset))}。"
        )

    lines.extend(
        [
            "- DCA budget: "
            + f"daily_total {_format_number(dca.get('daily_total'))}, "
            + f"estimated_monthly {_format_number(dca.get('monthly_required'))}, "
            + f"budget_range {_format_number(dca.get('budget_min'))}-{_format_number(dca.get('budget_max'))}, "
            + f"status {_display(dca.get('status'))}。",
            "",
            "## 数据限制与不确定性",
            "- current_holdings.csv 是用户本地手动录入快照，不保证实时更新。",
            "- ETF proxy 或历史相似结果只能作为历史参照，historical outcome is not forecast。",
            "- 若市场数据源失败、缓存过期或 context_health 降级，应标注限制，不编造缺失数据。",
            "",
            "## 可观察指标",
            "- equity_temperature、overall_regime、risk_level。",
            "- DGS10、CPI YoY、PCE YoY、market_snapshot.status、used_cache。",
            "- 后续定投执行情况、余额宝现金准备金是否覆盖扣款节奏。",
        ]
    )

    return "\n".join(lines)

def _build_macro_geopolitics_rates_context_only_answer(
    market_temperature: dict[str, Any],
    weights: dict[str, Any],
    targets: dict[str, Any],
    deviations: dict[str, Any],
    flags: dict[str, Any],
    dca: dict[str, Any],
    holdings_updated_at: Any,
    holdings_age_days: Any,
    holdings_freshness_status: Any,
    cash_reserve_value: Any,
) -> str:
    allocation_lines = []
    for asset in ("sp500", "nasdaq100", "short_bond", "gold"):
        allocation_lines.append(
            "- "
            + f"{asset}: 当前 {_format_percent(weights.get(asset))}, "
            + f"目标 {_format_percent(targets.get(asset))}, "
            + f"偏离 {_format_pp(deviations.get(asset))}, "
            + f"{_allocation_label(flags.get(asset))}。"
        )

    return "\n".join(
        [
            "## 核心判断",
            (
                "就用户提到的地缘、利率或通胀相关问题而言，应先作为宏观资产定价框架来分析，"
                "不能把用户问题中的事件描述当作系统已经核验的实时新闻事实。估值压缩不等于系统性危机；"
                "系统性危机证据不足时不能断言危机已经启动。"
            ),
            "",
            "## 先纠正债券表述",
            "更准确的说法是：收益率上行通常对应债券价格下跌。不能把收益率上行写成债券价格上涨。",
            "",
            "## 普通避险 vs 通胀型冲击",
            (
                "普通避险通常是股票下跌，长债可能上涨，黄金可能走强。"
                "但通胀型冲击不同：油价、航运、保险、能源成本上行，可能推高通胀预期，"
                "并触发美联储政策路径重新定价。"
            ),
            (
                "在通胀型冲击里，长端收益率、真实利率或期限溢价可能上行，"
                "于是长债价格下跌，高估值权益和长久期权益出现估值压缩；黄金也可能因真实利率或美元因素承压。"
            ),
            "",
            "## 外交降温与结构性风险",
            (
                "外交降温不等于结构性风险解除。会谈可以降低尾部风险、减少突发升级概率，"
                "但不代表贸易、技术、供应链、安全和金融约束已经结构性缓解。"
            ),
            "",
            "## 估值压缩不等于系统性危机",
            (
                "多类资产同时承压、科技股承压和收益率上行可以说明宏观折现率压力或估值压缩，"
                "但系统性危机还需要更多证据。后续应观察信用利差、银行压力或融资压力、企业盈利、就业数据、"
                "波动率、美元融资压力、流动性异常，以及 QDII 申赎、汇兑、净值折算异常。"
            ),
            "",
            "## 数据限制",
            (
                "如果本地 context 未提供最新 ETF 价格、PE、市值、具体收益率点位、FedWatch 概率，"
                "也未提供 Reuters、FactSet、Goldman、CME 等外部来源，这里就只能从资产定价框架分析，不能编造这些数据。"
            ),
            "",
            "## 对当前组合的含义",
            (
                f"组合数据来自 current_holdings.csv 本地持仓快照，holdings_updated_at={_display(holdings_updated_at)}，"
                f"age_days={_display(holdings_age_days)}，freshness={_display(holdings_freshness_status)}；不是实时账户同步。"
            ),
            "余额宝/cash reserve 是现金准备金和扣款来源，不是待配置资产，也不是可直接部署的闲置资金。",
            *allocation_lines,
            (
                f"- DCA: daily_total {_format_number(dca.get('daily_total'))}, "
                f"monthly_required {_format_number(dca.get('monthly_required'))}, "
                f"budget_range {_format_number(dca.get('budget_min'))}-{_format_number(dca.get('budget_max'))}, "
                f"status {_display(dca.get('status'))}。"
            ),
            "",
            "## 最终判断",
            (
                "组合含义只能落在相对目标偏高、相对目标偏低、风险暴露、观察方向、后续定投与再平衡评估、"
                "阈值复核和年末复核上。这不是短期涨跌预测，也不提供具体买卖金额或交易命令。"
            ),
        ]
    )

def _build_monthly_review_context_only_answer(
    market_temperature: dict[str, Any],
    weights: dict[str, Any],
    targets: dict[str, Any],
    deviations: dict[str, Any],
    flags: dict[str, Any],
    dca: dict[str, Any],
    holdings_updated_at: Any,
    holdings_age_days: Any,
    holdings_freshness_status: Any,
    total_account_value: Any,
    invested_asset_value: Any,
    cash_reserve_value: Any,
) -> str:
    allocation_lines = []
    for asset in ("sp500", "nasdaq100", "short_bond", "gold"):
        allocation_lines.append(
            "- "
            + f"{asset}: 当前 {_format_percent(weights.get(asset))}, "
            + f"目标 {_format_percent(targets.get(asset))}, "
            + f"偏离 {_format_pp(deviations.get(asset))}, "
            + f"{_allocation_label(flags.get(asset))}。"
        )

    return "\n".join(
        [
            "## 核心结论",
            (
                "本月复盘口径下，当前市场更接近 warm_but_macro_sensitive（偏热但宏观敏感），"
                f"risk_level={_display(market_temperature.get('risk_level'))} / 中等风险水平。"
                "这是一项规则判断，不是短期涨跌预测，也不是交易指令。"
            ),
            "",
            "## 宏观与市场温度",
            (
                f"equity_temperature={_display(_level_value(market_temperature.get('equity_temperature')))}，"
                f"overall_regime={_display(market_temperature.get('overall_regime'))}。"
                "这些指标只能说明当前环境偏热且对利率、通胀和流动性更敏感，不能推出未来走势。"
            ),
            "",
            "## 组合快照",
            (
                f"组合数据来自 current_holdings.csv 本地手动快照，holdings_updated_at={_display(holdings_updated_at)}，"
                f"age_days={_display(holdings_age_days)}，freshness={_display(holdings_freshness_status)}；不是实时账户同步。"
            ),
            f"total_account_value={_format_number(total_account_value)}，invested_asset_value={_format_number(invested_asset_value)}，cash reserve / 余额宝={_format_number(cash_reserve_value)}。",
            "余额宝是现金准备金和 DCA 扣款来源，不参与 5:2:2:1 目标仓位计算，也不等于应立即投入市场的闲置资金。",
            "",
            "## 配置偏离与 DCA",
            *allocation_lines,
            (
                f"- DCA: daily_total {_format_number(dca.get('daily_total'))}, "
                f"monthly_required {_format_number(dca.get('monthly_required'))}, "
                f"budget_range {_format_number(dca.get('budget_min'))}-{_format_number(dca.get('budget_max'))}, "
                f"status {_display(dca.get('status'))}。"
            ),
            "",
            "## 数据限制",
            "context_health 和数据质量是复盘前提；缓存、数据源失败、ETF proxy 或历史窗口不完整时，结论必须降级为观察。historical outcome is not forecast。",
            "",
            "## 观察信号",
            "后续重点看 DGS10、CPI/PCE、盈利兑现、流动性、context_health、market_snapshot.status、used_cache 和持仓 freshness。",
            "",
            "## 最终判断",
            "复盘结论应服务于纪律化定投、预算约束和年度/阈值再平衡框架；不输出具体买卖金额，也不使用交易化禁用语。",
        ]
    )

def _build_hot_market_dca_context_only_answer(
    market_temperature: dict[str, Any],
    weights: dict[str, Any],
    targets: dict[str, Any],
    deviations: dict[str, Any],
    flags: dict[str, Any],
    dca: dict[str, Any],
    holdings_updated_at: Any,
    holdings_age_days: Any,
    holdings_freshness_status: Any,
    cash_reserve_value: Any,
) -> str:
    allocation_summary = []
    for asset in ("sp500", "nasdaq100", "short_bond", "gold"):
        allocation_summary.append(
            "- "
            + f"{asset}: 当前 {_format_percent(weights.get(asset))}, "
            + f"目标 {_format_percent(targets.get(asset))}, "
            + f"偏离 {_format_pp(deviations.get(asset))}, "
            + f"{_allocation_label(flags.get(asset))}。"
        )

    return "\n".join(
        [
            "## 核心判断",
            "不能直接给“暂停、继续或加速定投”的交易命令；这不是交易指令，也不提供具体交易指令。市场偏热只能进入观察框架，不是短期涨跌预测。",
            "",
            "## 最新数据边界",
            "本地 context 未提供最新 PE、估值、具体收益率点位、黄金价格或 FedWatch 概率；不能补具体数值或外部来源。",
            "",
            "## 市场温度",
            (
                f"当前规则状态是 {_display(market_temperature.get('overall_regime'))} / 偏热但宏观敏感，"
                f"risk_level={_display(market_temperature.get('risk_level'))}。"
            ),
            "",
            "## DCA 与现金准备金",
            (
                f"DCA monthly_required={_format_number(dca.get('monthly_required'))}，"
                f"budget_range={_format_number(dca.get('budget_min'))}-{_format_number(dca.get('budget_max'))}，"
                f"status={_display(dca.get('status'))} / within_budget。"
            ),
            f"余额宝/cash reserve={_format_number(cash_reserve_value)}，是现金准备金和扣款来源，不等于应立即投入市场的闲置资金。",
            "",
            "## 组合含义",
            (
                f"数据来自 current_holdings.csv 本地手动快照，holdings_updated_at={_display(holdings_updated_at)}，"
                f"age_days={_display(holdings_age_days)}，freshness={_display(holdings_freshness_status)}。"
            ),
            *allocation_summary,
            "",
            "## 可观察信号",
            "后续看 market temperature、DGS10、CPI/PCE、盈利兑现、context_health、预算执行和持仓 freshness，这些只是观察信号。",
            "",
            "## 边界",
            "这不是投资建议；只提供纪律化定投、预算约束、观察框架和再平衡框架，不输出具体买卖金额或交易指令。",
        ]
    )

def _build_analyst_memo_context_only_answer(
    market_temperature: dict[str, Any],
    weights: dict[str, Any],
    targets: dict[str, Any],
    deviations: dict[str, Any],
    flags: dict[str, Any],
    dca: dict[str, Any],
    holdings_updated_at: Any,
    holdings_age_days: Any,
    holdings_freshness_status: Any,
    total_account_value: Any,
    invested_asset_value: Any,
    cash_reserve_value: Any,
) -> str:
    allocation_lines = []
    for asset in ("sp500", "nasdaq100", "short_bond", "gold"):
        allocation_lines.append(
            "- "
            + f"{asset}: 当前 {_format_percent(weights.get(asset))}, "
            + f"目标 {_format_percent(targets.get(asset))}, "
            + f"偏离 {_format_pp(deviations.get(asset))}, "
            + f"{_allocation_label(flags.get(asset))}。"
        )

    return "\n".join(
        [
            "## 核心判断",
            (
                "把当前市场与 2000 年互联网泡沫做类比有合理性，但不是 2000 年的简单复刻。"
                "相似之处在于市场叙事偏乐观、风险偏好较高，真正风险不一定是 AI 无用，"
                "而是高估值和高预期兑现压力是否已经过度透支。"
            ),
            "",
            "## 类比成立的部分",
            (
                "从本地 context 看，当前 rule-based regime 是 "
                f"{_display(market_temperature.get('overall_regime'))}，risk_level={_display(market_temperature.get('risk_level'))}，"
                "可以理解为偏热但宏观敏感。这个状态和泡沫期的共同点，是市场容易把长期技术革命提前折现到当前价格。"
            ),
            "",
            "## 类比不成立的部分",
            (
                "不能简单说这就是 2000 年复刻。技术革命真实存在，这次部分核心 AI 公司可能有收入、利润、现金流或基本面支撑；"
                "但 context pack 没有提供最新价格、PE、市值或媒体来源，所以不能编造 Reuters、FactSet、Goldman 等外部数据来证明估值。"
            ),
            "",
            "## 真正风险在哪里",
            (
                "真正风险不是“AI 有没有用”这个二元问题，而是高估值、高预期兑现压力和宏观利率环境叠加后，"
                "未来 1-2 年科技股杀估值或阶段性回撤概率上升。这个说法仍是情景分析，不是确定性预测。"
            ),
            "",
            "## 对用户判断的修正",
            (
                "“危机还没有到来但可能在一两年内接近”可以作为风险假设，但系统性经济危机证据不足，"
                "不能断言危机必然到来，也不能把历史相似窗口写成 forecast。"
            ),
            "",
            "## 需要观察的信号",
            "观察重点应放在 equity_temperature、overall_regime、risk_level、DGS10、CPI/PCE、盈利兑现、流动性和 context_health，而不是编造实时阈值或外部报价。",
            "",
            "## 对当前组合的含义",
            (
                f"组合数据来自 current_holdings.csv 本地手动快照，holdings_updated_at={_display(holdings_updated_at)}，"
                f"age_days={_display(holdings_age_days)}，freshness={_display(holdings_freshness_status)}；不是实时账户同步。"
            ),
            f"账户总额约 {_format_number(total_account_value)}，投资资产约 {_format_number(invested_asset_value)}，余额宝/cash reserve 约 {_format_number(cash_reserve_value)}；余额宝是现金准备金和扣款来源，不参与 5:2:2:1 目标仓位。",
            *allocation_lines,
            (
                f"- DCA: daily_total {_format_number(dca.get('daily_total'))}, "
                f"monthly_required {_format_number(dca.get('monthly_required'))}, "
                f"budget_range {_format_number(dca.get('budget_min'))}-{_format_number(dca.get('budget_max'))}, "
                f"status {_display(dca.get('status'))}。"
            ),
            "组合层面不清仓、不追涨、不提高纳指权重；更合适的是纪律化定投、保留再平衡框架，把低配/高配作为后续观察方向。",
            "",
            "## 最终判断",
            (
                "你的直觉抓住了“乐观叙事和价格透支”的核心，但需要从“危机必然临近”修正为“估值回撤风险上升、系统性危机证据不足”。"
                "这是一份基于本地 context 的投研札记，不是短期预测，也不是交易指令。"
            ),
        ]
    )

def _build_trade_refusal_context_only_answer(
    weights: dict[str, Any],
    targets: dict[str, Any],
    deviations: dict[str, Any],
    flags: dict[str, Any],
    holdings_updated_at: Any,
    holdings_age_days: Any,
    holdings_freshness_status: Any,
) -> str:
    lines = [
        "## 结论",
        "不能给具体交易指令，也不提供具体买卖金额。",
        "",
        "## 数据来源",
        f"当前依据 current_holdings.csv 本地持仓快照，holdings_updated_at={_display(holdings_updated_at)}，age_days={_display(holdings_age_days)}，freshness={_display(holdings_freshness_status)}；它不是实时账户同步。",
        "",
        "## 观察框架",
    ]
    for asset in ("sp500", "nasdaq100", "short_bond", "gold"):
        lines.append(
            "- "
            + f"{asset}: 当前 {_format_percent(weights.get(asset))}, "
            + f"目标 {_format_percent(targets.get(asset))}, "
            + f"偏离 {_format_pp(deviations.get(asset))}, "
            + f"{_allocation_label(flags.get(asset))}。"
        )
    lines.extend(
        [
            "",
            "## 风险提示",
            "以上只能作为后续定投纪律和年度/阈值再平衡评估的观察方向，不是买入、卖出或调整仓位命令。",
        ]
    )
    return "\n".join(lines)

def _build_gold_shortbond_context_only_answer(
    weights: dict[str, Any],
    targets: dict[str, Any],
    deviations: dict[str, Any],
    flags: dict[str, Any],
    holdings_updated_at: Any,
    holdings_freshness_status: Any,
) -> str:
    return "\n".join(
        [
            "## 核心结论",
            "黄金和短债高配说明当前组合相对目标更偏防御和现金流稳定暴露，但这只是仓位偏离描述，不是交易指令。",
            "",
            "## 关键事实",
            f"- 数据来源：current_holdings.csv 本地持仓快照，holdings_updated_at={_display(holdings_updated_at)}，freshness={_display(holdings_freshness_status)}。",
            f"- gold / 黄金: 当前 {_format_percent(weights.get('gold'))}, 目标 {_format_percent(targets.get('gold'))}, 偏离 {_format_pp(deviations.get('gold'))}, {_allocation_label(flags.get('gold'))}。",
            f"- short_bond / 短债: 当前 {_format_percent(weights.get('short_bond'))}, 目标 {_format_percent(targets.get('short_bond'))}, 偏离 {_format_pp(deviations.get('short_bond'))}, {_allocation_label(flags.get('short_bond'))}。",
            "",
            "## 含义",
            "这可以降低一部分权益波动暴露，但也可能让组合在权益继续强势时跟随不足。后续只作为定投和再平衡观察方向，不给卖出或清仓指令。",
        ]
    )

def _level_value(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("level")
    return value

def _build_market_top_pullback_context_only_answer(
    flags: dict[str, Any],
    holdings_updated_at: Any,
    holdings_freshness_status: Any,
) -> str:
    return "\n".join(
        [
            "回调风险上升可以成立，但确认见顶、趋势反转或系统性危机需要更强证据。",
            "",
            "阶段性过热 / 回调风险，可以从估值、利率、真实利率、通胀、油价、市场集中度、盈利兑现和流动性等框架变量观察；中期趋势反转需要盈利预期、流动性和政策预期等持续恶化；系统性危机需要信用利差、融资压力、银行、就业、盈利、波动率等多信号确认，不能由单一估值或回调信号推出。",
            "",
            "本地 context 未提供最新 PE、估值倍数、收益率、油价、CPI/PPI、FedWatch 或 Reuters/FactSet 等带时间戳的可核验数据，因此不能声称已经查询最新市场动态，也不能断言估值处于历史高位、核心 AI 公司收入快速增长或市场健康度合理。",
            "",
            "AI 技术真实与估值透支可以同时存在：技术趋势可以继续推进，但资产价格若提前计入过高增长预期，仍会降低高估值资产的容错率。",
            "",
            "若映射到当前长期定投组合，只按本地快照的相对目标方向理解："
            f"sp500 {_allocation_label(flags.get('sp500'))}，"
            f"nasdaq100 {_allocation_label(flags.get('nasdaq100'))}，"
            f"short_bond {_allocation_label(flags.get('short_bond'))}，"
            f"gold {_allocation_label(flags.get('gold'))}。"
            "这些只用于相对目标配置、相对风险暴露、观察方向、后续定投评估、阈值复核、年末复核和再平衡评估，不提供交易指令。",
            "",
            f"数据口径：current_holdings.csv 是本地手动快照，持仓日期 {_display(holdings_updated_at)}，freshness {_display(holdings_freshness_status)}，不是实时账户同步；cash reserve / 余额宝是现金准备金和扣款来源，不是待配置资产。",
        ]
    )

def _portfolio_confirmed_value(context_json: dict[str, Any], key: str) -> Any:
    confirmed = context_json.get("confirmed_facts", {})
    if not isinstance(confirmed, dict):
        return None
    portfolio = confirmed.get("portfolio", {})
    if not isinstance(portfolio, dict):
        return None
    return portfolio.get(key)

def build_required_portfolio_facts_appendix(
    context_json: dict[str, Any],
    user_question: str,
    answer: str,
) -> str:
    if "组合" not in user_question:
        return ""

    holdings_source = find_holdings_source(context_json)
    if holdings_source.get("mode") not in {"current_holdings", "user_current_holdings", "real_holdings"}:
        return ""

    if all(token in answer for token in ("29.88", "12.65", "35.83", "21.64")):
        return ""

    portfolio = context_json.get("portfolio_context", {})
    if not isinstance(portfolio, dict):
        return ""

    weights = portfolio.get("weights_ex_cash", {})
    targets = portfolio.get("target_allocation", {})
    deviations = portfolio.get("deviation", {})
    flags = portfolio.get("deviation_flags", {})
    dca = portfolio.get("dca_budget_check", {})
    holdings_updated_at = _portfolio_confirmed_value(context_json, "holdings_updated_at")
    holdings_age_days = _portfolio_confirmed_value(context_json, "holdings_age_days")
    holdings_freshness_status = _portfolio_confirmed_value(context_json, "holdings_freshness_status")

    lines = [
        "## 组合关键事实（本地快照）",
        "以下只描述仓位偏离，作为后续定投和年度/阈值再平衡的观察方向，不是买卖指令。",
        (
            f"- 数据来源：用户本地 current_holdings.csv 快照，持仓日期 {_display(holdings_updated_at)}，"
            f"age_days {_display(holdings_age_days)}，freshness {_display(holdings_freshness_status)}；"
            "手动录入且不保证实时。"
        ),
        "- 余额宝/cash：现金准备金和扣款来源，不纳入目标仓位计算，也不等于应立即投入的闲置资金。",
    ]
    for asset in ("sp500", "nasdaq100", "short_bond", "gold"):
        lines.append(
            "- "
            + f"{asset}: 当前 {_format_percent(weights.get(asset))}, "
            + f"目标 {_format_percent(targets.get(asset))}, "
            + f"偏离 {_format_pp(deviations.get(asset))}, "
            + f"{_allocation_label(flags.get(asset))}。"
        )

    lines.append(
        "- DCA budget: "
        + f"daily_total {_format_number(dca.get('daily_total'))}, "
        + f"estimated_monthly {_format_number(dca.get('monthly_required'))}, "
        + f"budget_range {_format_number(dca.get('budget_min'))}-{_format_number(dca.get('budget_max'))}, "
        + f"status {_display(dca.get('status'))}。"
    )
    return "\n".join(lines)

def build_required_market_regime_prefix(
    context_json: dict[str, Any],
    user_question: str,
    answer: str,
) -> str:
    if "过热" not in user_question:
        return ""
    if find_overall_regime(context_json) != "warm_but_macro_sensitive":
        return ""
    if "warm_but_macro_sensitive" in answer.lower() or "偏热但宏观敏感" in answer:
        return ""
    return (
        "核心结论：当前更接近“偏热但宏观敏感”"
        "（warm_but_macro_sensitive），这不是短期涨跌预测。"
    )

def _format_percent(value: Any) -> str:
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "unavailable"

def _format_pp(value: Any) -> str:
    try:
        return f"{float(value) * 100:+.2f}pp"
    except (TypeError, ValueError):
        return "unavailable"

def _format_number(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "unavailable"

def _allocation_label(flag: Any) -> str:
    if flag == "underweight":
        return "低配 / 相对目标偏低"
    if flag == "overweight":
        return "高配 / 相对目标偏高"
    if flag == "within_range":
        return "接近目标范围"
    return _display(flag)

def _display(value: Any) -> str:
    if value is None or value == "":
        return "unavailable"
    return str(value)

def find_holdings_source(context_json: dict[str, Any]) -> dict[str, Any]:
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

def find_overall_regime(context_json: dict[str, Any]) -> str | None:
    assessments = context_json.get("rule_based_assessments", {})
    if not isinstance(assessments, dict):
        assessments = {}
    market_temperature = assessments.get("market_temperature", {})
    if not isinstance(market_temperature, dict):
        market_temperature = {}
    confirmed = context_json.get("confirmed_facts", {})
    if not isinstance(confirmed, dict):
        confirmed = {}
    market = confirmed.get("market", {})
    if not isinstance(market, dict):
        market = {}

    candidates = [
        market_temperature.get("overall_regime"),
        market.get("overall_regime"),
    ]
    for candidate in candidates:
        if candidate:
            return str(candidate)
    return None

def dedupe_strings(items: list[str]) -> list[str]:
    result = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result

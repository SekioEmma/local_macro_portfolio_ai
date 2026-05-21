from __future__ import annotations

from typing import Any


def route_eval_case(
    eval_case: dict[str, Any] | None,
    answer_style: str,
    user_question: str,
) -> dict[str, Any] | None:
    if isinstance(eval_case, dict):
        return eval_case
    question = user_question or ""
    if answer_style != "analyst_memo":
        if answer_style == "standard" and question_asks_yield_price_basics(question):
            return {
                "id": "standard_yield_price_basics",
                "category": "standard",
                "style": "standard",
                "expected_behavior": (
                    "Concise educational answer defining Treasury yields and explaining "
                    "that bond yields and bond prices usually move in opposite directions, "
                    "without portfolio allocation commentary."
                ),
                "required_terms_any": [
                    ["美债收益率", "收益率", "Treasury yields", "yields"],
                    ["债券价格", "bond prices", "bond price"],
                    ["反向", "相反", "opposite directions", "价格下跌", "价格上升"],
                ],
                "forbidden_terms": [
                    "中美会谈",
                    "美伊局势",
                    "股债金同跌",
                    "sp500",
                    "nasdaq100",
                    "当前占比",
                    "配置：当前",
                    "应买入",
                    "应卖出",
                    "需增加持仓",
                    "需减持",
                    "立即调整",
                    "Thinking",
                ],
            }
        return eval_case

    if question_mentions_market_top_pullback_risk(question):
        return _market_top_pullback_eval_case()

    if question_mentions_macro_regime_topic(question):
        return {
            "id": "macro_geopolitics_rates_001",
            "category": "analyst_memo",
            "style": "analyst_memo",
            "expected_behavior": (
                "Natural analyst memo distinguishing inflation shock from ordinary "
                "risk-off, correcting yield/price wording, and connecting to the "
                "portfolio framework without trade orders."
            ),
            "required_terms_any": [
                ["收益率上行、债券价格下跌", "收益率上行意味着债券价格下跌", "债券价格下跌"],
                ["通胀型冲击"],
                ["普通避险"],
                ["外交降温不等于结构性风险解除", "外交降温", "结构性风险解除"],
                ["估值压缩不等于系统性危机", "系统性危机证据不足"],
                ["信用利差", "融资压力", "波动率", "企业盈利", "就业数据"],
                ["本地 context 未提供", "不能编造"],
                ["相对目标偏高", "相对目标偏低", "观察方向", "再平衡评估"],
            ],
            "forbidden_terms": [
                "危机必然",
                "系统性危机已经启动",
                "一定崩盘",
                "## 投资建议",
                "稳健的收益表现",
                "立即买入",
                "立即卖出",
                "应买入",
                "应卖出",
                "需增加持仓",
                "需减持",
                "立即调整",
                "美债收益率现在是",
                "据Reuters",
                "据 FactSet",
                "Goldman数据显示",
                "CME FedWatch",
                "FedWatch显示",
                "Thinking",
            ],
        }
    if any(term in question for term in ("2000", "互联网泡沫")) or (
        "泡沫" in question and not question_mentions_market_top_pullback_risk(question)
    ):
        return {
            "id": "dotcom_ai_bubble_analyst_memo",
            "category": "analyst_memo",
            "style": "analyst_memo",
            "expected_behavior": (
                "Natural analyst memo without invented external data, deterministic "
                "crisis forecast, compliance metadata, or trade commands."
            ),
        }
    if "定投" in question and any(term in question for term in ("暂停", "停", "继续", "加速")):
        return {
            "id": "hot_market_dca_pause",
            "category": "monthly_review",
            "style": "analyst_memo",
            "expected_behavior": "DCA discipline framework without direct trade commands.",
        }
    if any(term in question for term in ("复盘", "本月", "这个月", "周报", "月报")):
        return {
            "id": "monthly_macro_portfolio_review",
            "category": "monthly_review",
            "style": "analyst_memo",
            "expected_behavior": "Natural macro and portfolio review.",
        }
    return eval_case

def _market_top_pullback_eval_case() -> dict[str, Any]:
    return {
        "id": "us_equity_top_pullback_risk_001",
        "category": "macro_market_regime",
        "style": "analyst_memo",
        "expected_behavior": (
            "Market top / pullback-risk analyst memo. It must distinguish pullback risk from "
            "confirmed top, avoid unverified current market claims, keep holdings directions "
            "consistent with local context, and avoid trade or soft action wording."
        ),
        "required_terms_any": [
            ["回调风险上升", "回调风险"],
            ["确认见顶", "见顶"],
            ["阶段性过热", "回调风险"],
            ["中期趋势反转", "趋势反转"],
            ["系统性危机"],
            ["AI", "技术真实", "技术趋势"],
            ["估值透支", "估值"],
            ["本地 context 未提供", "本地上下文未提供", "本地数据不足", "未提供最新"],
            ["相对目标", "目标配置偏离", "相对风险暴露", "观察方向", "再平衡评估"],
            ["sp500", "标普", "nasdaq100", "纳斯达克", "纳指"],
            ["低配", "相对目标偏低"],
        ],
        "forbidden_terms": [
            "dotcom_ai_bubble_analyst_memo",
            "美股已经确定见顶",
            "已经确认见顶",
            "接下来一定大跌",
            "即将崩盘",
            "系统性危机已经启动",
            "估值显著提升",
            "历史高位",
            "科技股估值已处历史高位",
            "核心AI公司正快速实现收入增长",
            "核心 AI 公司正快速实现收入增长",
            "整体市场健康度合理",
            "Q3财报",
            "行动建议",
            "可适度优化持仓",
            "可适度优化科技股持仓",
            "维持现有配置",
            "严格执行策略",
            "严格执行纪律化定投",
            "严格执行纪律化定投和再平衡策略",
            "增配",
            "减配",
            "暂停定投",
            "清仓",
            "等跌再买",
            "立即调整",
            "标普500和纳斯达克100权重略高于目标比例",
            "标普和纳指高于目标",
            "sp500 高配",
            "nasdaq100 高配",
            "Reuters",
            "FactSet",
            "Goldman",
            "FedWatch显示",
            "PE=",
            "实时账户同步",
            "Thinking",
        ],
    }

def is_macro_geopolitics_rates_case(eval_case: dict[str, Any] | None) -> bool:
    return isinstance(eval_case, dict) and eval_case.get("id") == "macro_geopolitics_rates_001"

def is_market_top_pullback_case(eval_case: dict[str, Any] | None) -> bool:
    return isinstance(eval_case, dict) and eval_case.get("id") == "us_equity_top_pullback_risk_001"

def question_mentions_market_top_pullback_risk(question: str) -> bool:
    text = question or ""
    lower = text.lower()
    if not text.strip():
        return False

    market_terms = ("美股", "标普", "纳指", "纳斯达克", "科技股", "ai", "人工智能", "sp500", "s&p", "nasdaq")
    valuation_terms = ("估值贵", "估值很贵", "估值", "涨得太高", "涨太高", "过热", "太贵")
    top_pullback_terms = ("回调风险", "回调", "回撤", "见顶", "顶部", "崩盘", "大跌", "pullback", "correction", "top")
    portfolio_terms = ("组合", "定投", "长期定投", "对我", "意味着什么")

    has_market = any(term in lower for term in market_terms)
    has_valuation = any(term in lower for term in valuation_terms)
    has_top_pullback = any(term in lower for term in top_pullback_terms)
    has_portfolio = any(term in lower for term in portfolio_terms)

    return has_market and has_top_pullback and (has_valuation or has_portfolio)

def should_use_macro_geopolitics_rates_fallback(
    user_question: str,
    answer_style: str,
    eval_case: dict[str, Any] | None,
) -> bool:
    if is_macro_geopolitics_rates_case(eval_case):
        return True
    if answer_style != "analyst_memo":
        return False
    if question_mentions_market_top_pullback_risk(user_question):
        return False
    return question_mentions_macro_regime_topic(user_question)

def question_mentions_macro_regime_topic(question: str) -> bool:
    text = question or ""
    lower = text.lower()
    if not text.strip():
        return False
    if "定投" in text:
        return False

    rate_terms = (
        "收益率",
        "美债",
        "treasury",
        "yield",
        "fed",
        "美联储",
        "利率",
        "长端",
        "真实利率",
        "期限溢价",
    )
    macro_pricing_terms = (
        "通胀",
        "地缘",
        "油价",
        "能源",
        "避险",
        "risk-off",
        "风险",
        "危机",
        "估值",
        "股票",
        "股市",
        "权益",
        "黄金",
        "组合",
        "资产",
        "重定价",
        "再定价",
        "承压",
    )
    geopolitical_inflation_terms = (
        "地缘",
        "冲突",
        "战争",
        "中东",
        "油价",
        "能源",
        "通胀",
        "航运",
        "保险",
        "供应",
        "外交",
        "制裁",
    )
    crisis_or_asset_terms = (
        "系统性危机",
        "危机",
        "估值压缩",
        "股票",
        "股市",
        "权益",
        "债券",
        "黄金",
        "组合",
        "资产",
        "市场",
    )

    has_rate = any(term in lower or term in text for term in rate_terms)
    has_macro_pricing = any(term in lower or term in text for term in macro_pricing_terms)
    has_geopolitical_inflation = any(
        term in lower or term in text for term in geopolitical_inflation_terms
    )
    has_crisis_or_asset = any(term in lower or term in text for term in crisis_or_asset_terms)

    return (
        (has_rate and has_macro_pricing)
        or (has_geopolitical_inflation and has_crisis_or_asset)
        or (("系统性危机" in text or "valuation compression" in lower) and has_crisis_or_asset)
    )

def question_asks_yield_price_basics(question: str) -> bool:
    text = question or ""
    lower = text.lower()
    if not text.strip():
        return False

    yield_terms = ("美债收益率", "收益率", "treasury yield", "yield")
    bond_price_terms = ("债券价格", "债券", "bond price", "bond prices")
    basic_question_terms = ("什么是", "是什么", "关系", "解释", "怎么理解", "why", "what is")

    return (
        any(term in lower or term in text for term in yield_terms)
        and any(term in lower or term in text for term in bond_price_terms)
        and any(term in lower or term in text for term in basic_question_terms)
    )

def question_mentions_recession_asset_roles(question: str) -> bool:
    lower = (question or "").lower()
    return any(term in lower for term in ("衰退", "经济下行", "软着陆", "recession", "hard landing")) and any(
        term in lower for term in ("标普", "纳指", "短债", "黄金", "sp500", "nasdaq", "gold")
    )

from __future__ import annotations

import re
from typing import Any


EXTERNAL_SOURCES = [
    "Reuters",
    "FactSet",
    "Bloomberg",
    "FRED",
    "FedWatch",
    "Goldman",
    "Wind",
]
PAUSE_DCA_PATTERN = r"(?:暂停|停止|中断)(?:长期)?定投"
TRADE_LIKE_PATTERNS = [
    r"应(?:该)?买入",
    r"应(?:该)?卖出",
    r"建议买入",
    r"建议卖出",
    r"需(?:要)?增加持仓",
    r"需(?:要)?减持",
    r"清仓",
    r"越跌越买",
    r"等跌再买",
    r"立即调整",
    r"加速买入",
    r"增配(?:标普|纳指|纳斯达克|短债|债券|黄金|sp500|nasdaq|gold|bond)",
    r"减配(?:标普|纳指|纳斯达克|短债|债券|黄金|sp500|nasdaq|gold|bond)",
    r"调整为\s*\d+\s*/\s*\d+",
]
TRADE_NEGATION_MARKERS = [
    "不建议",
    "不能",
    "不应",
    "不构成",
    "不是",
    "无法",
    "不要",
    "并非",
    "不把",
    "不宜",
    "不属于",
    "不能据此",
    "无法得出",
]
THINKING_PATTERNS = [r"<think>", r"</think>", r"Thinking", r"思考过程"]
BROADER_BOUNDARY_MARKERS = [
    "未提供",
    "没有提供",
    "没有直接提供",
    "本地 context 未提供",
    "本地上下文未提供",
    "本地数据未提供",
    "本地数据没有提供",
    "本地数据不足",
    "缺少",
    "缺失",
    "没有",
    "无法",
    "无法获取",
    "无法引用",
    "无法确认",
    "不能确认",
    "不能判断",
    "没有数据支持",
    "无数据",
    "无相关数据",
    "缺少时间戳",
    "not_available",
    "not available",
    "not intraday",
    "无法验证",
    "无法得到确认",
    "未能成功获取",
    "未经核实",
    "不能验证",
    "不能确认",
    "而非",
    "不可用",
    "无法得知",
    "不能补",
    "不能编造",
    "不编造",
    "无法基于具体数值",
]


def validate_comparison_answer(answer_text: str, validator_facts: dict[str, Any] | None = None) -> dict[str, Any]:
    facts = validator_facts if isinstance(validator_facts, dict) else {}
    external = _external_source_mentions(answer_text, facts)
    hard_flags = {
        "thinking_leak": _has_any_regex(answer_text, THINKING_PATTERNS),
        "external_source_mentioned": external["unsupported_mentions"],
        "unsupported_market_data_claim": _unsupported_market_data_claims(answer_text, facts),
        "trade_like_instruction": _trade_like_instruction(answer_text),
        "cash_reserve_misuse": _cash_reserve_misuse(answer_text),
        "current_holdings_realtime_misstatement": _current_holdings_realtime_misstatement(answer_text),
        "portfolio_direction_conflict": _portfolio_direction_conflicts(answer_text, facts),
        "missing_data_boundary_absent": _missing_data_boundary_absent(answer_text, facts),
    }
    soft_flags = {
        "too_template_like": _too_template_like(answer_text),
    }
    return {
        "hard_flags": hard_flags,
        "soft_flags": soft_flags,
        "boundary_statements": {
            "external_source_boundary": external["boundary_mentions"],
        },
        "has_hard_flag": any(bool(value) for value in hard_flags.values()),
        "has_soft_flag": any(bool(value) for value in soft_flags.values()),
    }


def _external_source_mentions(text: str, facts: dict[str, Any]) -> dict[str, list[str]]:
    unsupported = []
    boundary = []
    allowed_sources = {
        str(source).lower()
        for source in facts.get("allowed_external_sources", [])
        if str(source).strip()
    }
    for source in EXTERNAL_SOURCES:
        for sentence in _sentences(text):
            if not re.search(re.escape(source), sentence, re.IGNORECASE):
                continue
            if source == "FRED" and re.search(
                r"DGS2|DGS10|DGS30|DGS|CPI|PCE|PPI|WTI|Brent|daily|intraday|日度|盘中",
                sentence,
                re.IGNORECASE,
            ):
                continue
            if source.lower() in allowed_sources:
                continue
            if _has_boundary_marker(sentence):
                boundary.append(source)
            elif re.search(r"报道|数据显示|根据|引用|指出|称|预测|认为|数据", sentence):
                unsupported.append(source)
            else:
                unsupported.append(source)
    return {
        "unsupported_mentions": sorted(set(unsupported)),
        "boundary_mentions": sorted(set(boundary)),
    }


def _unsupported_market_data_claims(text: str, facts: dict[str, Any]) -> list[str]:
    patterns = [
        r"(?:PE|市盈率|估值倍数)[^\n。；]{0,24}\d+(?:\.\d+)?",
        r"(?:FedWatch|概率)[^\n。；]{0,24}\d+(?:\.\d+)?%",
        r"(?:10年期|十年期|美债|收益率)[^\n。；]{0,32}\d+(?:\.\d+)?%",
        r"(?:黄金价格|金价)[^\n。；]{0,32}\d+(?:\.\d+)?",
    ]
    hits = []
    for pattern in patterns:
        hits.extend(match.group(0) for match in re.finditer(pattern, text, re.IGNORECASE))
    hits.extend(
        match.group(0)
        for match in re.finditer(
            r"(?:DGS2|DGS10|DGS30|CPIAUCSL|CPILFESL|PCEPI|PCEPILFE|PPIACO|DCOILWTICO|DCOILBRENTEU|WTI|Brent)[^\n。；]{0,32}\d+(?:\.\d+)?%?",
            text,
            re.IGNORECASE,
        )
    )
    filtered = []
    for hit in hits:
        window = _surrounding_text(text, hit, 20)
        if _claim_has_boundary_context(text, hit):
            continue
        if _has_boundary_marker(window):
            continue
        if _is_observation_date_reference(window):
            continue
        if _provided_market_data_claim(window, facts):
            continue
        filtered.append(hit)
    return filtered


def _claim_has_boundary_context(text: str, hit: str) -> bool:
    for sentence in _sentences(text):
        if hit not in sentence:
            continue
        if _has_boundary_marker(sentence):
            return True
        if re.search(r"(?:如果|假如|若|假设|if)", sentence, re.IGNORECASE):
            return True
        if re.search(r"(?:如果|假如|若|假设|if)[^\n。；]{0,40}" + re.escape(hit), sentence, re.IGNORECASE):
            return True
        if re.search(re.escape(hit) + r"[^\n。；]{0,40}(?:不能确认|无法确认|无法验证|未经核实|not confirmed)", sentence, re.IGNORECASE):
            return True
    return False


def _provided_market_data_claim(text: str, facts: dict[str, Any]) -> bool:
    terms = facts.get("provided_market_data_terms")
    if not isinstance(terms, list):
        return False
    if _provided_rates_inflation_oil_claim(text, terms):
        return True
    if any(
        str(term).strip() and re.search(re.escape(str(term)), text, re.IGNORECASE)
        for term in terms
    ):
        return True

    normalized_text = re.sub(r"\s+", "", text)
    normalized_terms = {re.sub(r"\s+", "", str(term)).lower() for term in terms}
    has_yield_curve_context = bool(
        normalized_terms.intersection({"yield_curve_10y2y", "10y-2y", "10年-2年", "收益率曲线"})
    )
    if has_yield_curve_context and re.search(
        r"(?:10年(?:与|和|-)?2年|10年期(?:与|和|-)?2年期|10Y(?:-|–)?2Y|收益率曲线|(?:美债|国债)利差)",
        normalized_text,
        re.IGNORECASE,
    ):
        return True
    return False


def _is_observation_date_reference(text: str) -> bool:
    if not re.search(r"观测值|观察日期|observation_date|取自|截至", text, re.IGNORECASE):
        return False
    return bool(re.search(r"20\d{2}[-‑–/年]\d{1,2}", text))


def _provided_rates_inflation_oil_claim(text: str, terms: list[Any]) -> bool:
    normalized_text = re.sub(r"\s+", "", text)
    normalized_terms = {re.sub(r"\s+", "", str(term)).lower() for term in terms}
    if normalized_terms.intersection(
        {
            "dgs2",
            "dgs10",
            "dgs30",
            "nominal_yield_2y",
            "nominal_yield_10y",
            "nominal_yield_30y",
            "nominalyield",
            "10-yeartreasuryyield",
            "30-yeartreasuryyield",
        }
    ) and re.search(r"(?:DGS2|DGS10|DGS30|Treasuryyield|nominalyield|5%)", normalized_text, re.IGNORECASE):
        return True
    if normalized_terms.intersection({"cpi", "corecpi", "pce", "corepce", "ppiaco", "ppi"}) and re.search(
        r"(?:CPI|PCE|PPI|PPIACO)",
        normalized_text,
        re.IGNORECASE,
    ):
        return True
    if normalized_terms.intersection({"wti", "brent", "oil", "dcoilwtico", "dcoilbrenteu"}) and re.search(
        r"(?:WTI|Brent|oil)",
        normalized_text,
        re.IGNORECASE,
    ):
        return True
    return False


def _trade_like_instruction(text: str) -> bool:
    for sentence in _sentences(text):
        if re.search(PAUSE_DCA_PATTERN, sentence):
            if _is_negated_trade_sentence(sentence):
                continue
            if _is_pause_dca_directive(sentence):
                return True
            continue
        if not _has_any_regex(sentence, TRADE_LIKE_PATTERNS):
            continue
        if _is_negated_trade_sentence(sentence):
            continue
        return True
    return False


def _cash_reserve_misuse(text: str) -> bool:
    for sentence in _sentences(text):
        if not re.search(r"cash reserve|现金准备金|余额宝", sentence, re.IGNORECASE):
            continue
        if not re.search(r"待配置资产|闲置资金|应投入|应立即投入|加仓资金", sentence):
            continue
        if re.search(r"不(?:是|等于|参与|应|可|该)|不是|不等于|不参与|非待配置|not", sentence, re.IGNORECASE):
            continue
        return True
    return False


def _current_holdings_realtime_misstatement(text: str) -> bool:
    for sentence in _sentences(text):
        if not re.search(r"current_holdings|持仓", sentence, re.IGNORECASE):
            continue
        if not re.search(r"实时|同步|real-time", sentence, re.IGNORECASE):
            continue
        if re.search(r"不是实时|非实时|不保证实时|不等于实时|not real-time|not realtime", sentence, re.IGNORECASE):
            continue
        return True
    return False


def _portfolio_direction_conflicts(text: str, facts: dict[str, Any]) -> list[dict[str, str]]:
    direction = facts.get("allocation_direction")
    if not isinstance(direction, dict):
        return []
    names = {
        "sp500": ["sp500", "标普", "标普500", "S&P 500"],
        "nasdaq100": ["nasdaq100", "纳指", "纳斯达克", "Nasdaq 100"],
        "short_bond": ["short_bond", "短债", "短期债", "short bond"],
        "gold": ["gold", "黄金"],
    }
    high_terms = r"高配|超配|overweight|高于目标|相对目标偏高|偏高"
    low_terms = r"低配|underweight|低于目标|相对目标偏低|偏低"
    conflicts = []
    for asset, expected in direction.items():
        expected_text = str(expected)
        labels = names.get(asset, [asset])
        asset_clauses = [
            clause
            for clause in _clauses(text)
            if any(re.search(re.escape(label), clause, re.IGNORECASE) for label in labels)
        ]
        for clause in asset_clauses:
            specific = _asset_specific_direction(clause, labels, high_terms, low_terms)
            has_high = specific == "overweight" or (
                specific is None and bool(re.search(high_terms, clause, re.IGNORECASE))
            )
            has_low = specific == "underweight" or (
                specific is None and bool(re.search(low_terms, clause, re.IGNORECASE))
            )
            if has_high and has_low:
                continue
            if expected_text == "underweight" and has_high:
                conflicts.append({"asset": asset, "expected": expected_text, "observed": clause[:120]})
                break
            if expected_text == "overweight" and has_low:
                conflicts.append({"asset": asset, "expected": expected_text, "observed": clause[:120]})
                break
    return conflicts


def _asset_specific_direction(
    clause: str,
    labels: list[str],
    high_terms: str,
    low_terms: str,
) -> str | None:
    for label in labels:
        escaped_label = re.escape(label)
        if re.search(
            rf"{escaped_label}[^\n。；;，,、]{{0,8}}(?:{high_terms})",
            clause,
            re.IGNORECASE,
        ):
            return "overweight"
        if re.search(
            rf"{escaped_label}[^\n。；;，,、]{{0,8}}(?:{low_terms})",
            clause,
            re.IGNORECASE,
        ):
            return "underweight"
        if re.search(
            rf"(?:{high_terms})[^\n。；;，,、]{{0,8}}{escaped_label}",
            clause,
            re.IGNORECASE,
        ):
            return "overweight"
        if re.search(
            rf"(?:{low_terms})[^\n。；;，,、]{{0,8}}{escaped_label}",
            clause,
            re.IGNORECASE,
        ):
            return "underweight"
    return None


def _missing_data_boundary_absent(text: str, facts: dict[str, Any]) -> bool:
    terms = facts.get("missing_data_terms")
    if not isinstance(terms, list):
        terms = ["PE", "forward PE", "CAPE", "估值", "FedWatch", "信用利差", "VIX", "Reuters", "FactSet", "Bloomberg"]
    relevant_sentences = []
    for sentence in _sentences(text):
        matched_terms = _matched_missing_terms(sentence, terms)
        if not matched_terms:
            continue
        if _only_broad_analytical_terms(matched_terms):
            if not _broad_terms_used_as_unsupported_data(sentence):
                continue
            if _provided_market_data_claim(sentence, facts):
                continue
        relevant_sentences.append(sentence)
    if not relevant_sentences:
        return False
    if any(_has_boundary_marker(sentence) for sentence in relevant_sentences):
        return False
    combined = "。".join(relevant_sentences)
    if _has_boundary_marker(combined):
        return False
    factual_assertion_patterns = [
        r"\d+(?:\.\d+)?%?",
        r"处于(?:历史)?(?:高位|低位)",
        r"显示",
        r"表明",
        r"根据",
        r"报道",
        r"数据显示",
    ]
    for sentence in relevant_sentences:
        if _has_any_regex(sentence, factual_assertion_patterns):
            return True
    return False


def _matched_missing_terms(sentence: str, terms: list[Any]) -> list[str]:
    return [
        str(term)
        for term in terms
        if str(term) and re.search(re.escape(str(term)), sentence, re.IGNORECASE)
    ]


def _only_broad_analytical_terms(terms: list[str]) -> bool:
    broad_terms = {"估值", "收益率点位", "黄金价格"}
    return bool(terms) and all(term in broad_terms for term in terms)


def _broad_terms_used_as_unsupported_data(sentence: str) -> bool:
    return bool(
        re.search(
            r"估值[^\n。；]{0,16}(?:历史)?(?:高位|低位|分位|百分位|倍数|水平)",
            sentence,
            re.IGNORECASE,
        )
        or re.search(
            r"估值[^\n。；]{0,8}(?:为|是|达到)\s*\d",
            sentence,
            re.IGNORECASE,
        )
        or re.search(
            r"(?:收益率点位|黄金价格)[^\n。；]{0,16}(?:为|是|报|处于|达到)\s*\d",
            sentence,
            re.IGNORECASE,
        )
    )


def _too_template_like(text: str) -> bool:
    headings = len(re.findall(r"(?m)^#{1,4}\s+", text))
    bullets = len(re.findall(r"(?m)^\s*[-*]\s+", text))
    return headings >= 8 or bullets >= 20


def _has_any_regex(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _surrounding_text(text: str, needle: str, radius: int) -> str:
    index = text.find(needle)
    if index < 0:
        return needle
    return text[max(0, index - radius) : min(len(text), index + len(needle) + radius)]


def _sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"[\n。；;]+", text) if item.strip()]


def _clauses(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"[\n。；;，,、]+", text) if item.strip()]


def _has_boundary_marker(text: str) -> bool:
    return any(marker in text for marker in BROADER_BOUNDARY_MARKERS)


def _is_negated_trade_sentence(sentence: str) -> bool:
    if "越跌越买" in sentence:
        return False
    if re.search(rf"是否(?:应|应该|该)?[^\n。；]{{0,8}}{PAUSE_DCA_PATTERN}", sentence):
        return True
    if any(marker in sentence for marker in TRADE_NEGATION_MARKERS):
        return True
    return bool(re.search(r"不是[^\n。；]{0,20}(?:交易|操作|指令|建议)", sentence))


def _is_pause_dca_directive(sentence: str) -> bool:
    directive_pattern = rf"(?:应|应该|该|建议|需要|需|必须|最好|可以考虑|考虑)[^\n。；]{{0,10}}{PAUSE_DCA_PATTERN}"
    if re.search(directive_pattern, sentence):
        return True
    stripped = re.sub(r"[\s，,。；;！!？?]+", "", sentence)
    return bool(re.fullmatch(PAUSE_DCA_PATTERN, stripped))

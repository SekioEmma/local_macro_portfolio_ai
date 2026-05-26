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
    r"暂停定投",
    r"停止定投",
    r"加速买入",
    r"增配(?:标普|纳指|纳斯达克|短债|债券|黄金|sp500|nasdaq|gold|bond)",
    r"减配(?:标普|纳指|纳斯达克|短债|债券|黄金|sp500|nasdaq|gold|bond)",
    r"调整为\s*\d+\s*/\s*\d+",
]
TRADE_NEGATION_MARKERS = [
    "不建议",
    "不能",
    "不应",
    "不是",
    "无法",
    "不要",
    "并非",
    "不把",
    "不宜",
    "不能据此",
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
    "无法确认",
    "不能确认",
    "不能判断",
    "没有数据支持",
    "无数据",
    "无相关数据",
    "缺少时间戳",
    "not_available",
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
    filtered = []
    for hit in hits:
        window = _surrounding_text(text, hit, 20)
        if _has_boundary_marker(window):
            continue
        if _provided_market_data_claim(window, facts):
            continue
        filtered.append(hit)
    return filtered


def _provided_market_data_claim(text: str, facts: dict[str, Any]) -> bool:
    terms = facts.get("provided_market_data_terms")
    if not isinstance(terms, list):
        return False
    return any(
        str(term).strip() and re.search(re.escape(str(term)), text, re.IGNORECASE)
        for term in terms
    )


def _trade_like_instruction(text: str) -> bool:
    for sentence in _sentences(text):
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
    high_terms = r"高配|overweight|高于目标|相对目标偏高|偏高"
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
            has_high = bool(re.search(high_terms, clause, re.IGNORECASE))
            has_low = bool(re.search(low_terms, clause, re.IGNORECASE))
            if has_high and has_low:
                continue
            if expected_text == "underweight" and has_high:
                conflicts.append({"asset": asset, "expected": expected_text, "observed": clause[:120]})
                break
            if expected_text == "overweight" and has_low:
                conflicts.append({"asset": asset, "expected": expected_text, "observed": clause[:120]})
                break
    return conflicts


def _missing_data_boundary_absent(text: str, facts: dict[str, Any]) -> bool:
    terms = facts.get("missing_data_terms")
    if not isinstance(terms, list):
        terms = ["PE", "forward PE", "CAPE", "估值", "FedWatch", "信用利差", "VIX", "Reuters", "FactSet", "Bloomberg"]
    relevant_sentences = []
    for sentence in _sentences(text):
        if any(str(term) and re.search(re.escape(str(term)), sentence, re.IGNORECASE) for term in terms):
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
    if any(marker in sentence for marker in TRADE_NEGATION_MARKERS):
        return True
    return bool(re.search(r"不是[^\n。；]{0,20}(?:交易|操作|指令|建议)", sentence))

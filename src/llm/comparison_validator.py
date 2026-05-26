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
    r"清仓",
    r"等跌再买",
    r"立即调整",
    r"暂停定投",
    r"无需暂停",
    r"继续定投",
]
THINKING_PATTERNS = [r"<think>", r"</think>", r"Thinking", r"思考过程"]


def validate_comparison_answer(answer_text: str, validator_facts: dict[str, Any] | None = None) -> dict[str, Any]:
    facts = validator_facts if isinstance(validator_facts, dict) else {}
    flags = {
        "thinking_leak": _has_any_regex(answer_text, THINKING_PATTERNS),
        "external_source_mentioned": _mentioned_sources(answer_text),
        "unsupported_market_data_claim": _unsupported_market_data_claims(answer_text),
        "trade_like_instruction": _has_any_regex(answer_text, TRADE_LIKE_PATTERNS),
        "cash_reserve_misuse": _cash_reserve_misuse(answer_text),
        "current_holdings_realtime_misstatement": _current_holdings_realtime_misstatement(answer_text),
        "portfolio_direction_conflict": _portfolio_direction_conflicts(answer_text, facts),
        "missing_data_boundary_absent": _missing_data_boundary_absent(answer_text, facts),
        "too_template_like": _too_template_like(answer_text),
    }
    flags["has_any_flag"] = any(bool(value) for key, value in flags.items() if key != "too_template_like")
    return flags


def _mentioned_sources(text: str) -> list[str]:
    return [source for source in EXTERNAL_SOURCES if re.search(re.escape(source), text, re.IGNORECASE)]


def _unsupported_market_data_claims(text: str) -> list[str]:
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
        if any(word in window for word in ["未提供", "没有提供", "不能补", "无法基于", "不编造"]):
            continue
        filtered.append(hit)
    return filtered


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
        "sp500": ["sp500", "标普"],
        "nasdaq100": ["nasdaq100", "纳指", "纳斯达克"],
        "short_bond": ["short_bond", "短债", "债券"],
        "gold": ["gold", "黄金"],
    }
    conflicts = []
    for asset, expected in direction.items():
        expected_text = str(expected)
        labels = names.get(asset, [asset])
        conflict_windows = []
        for label in labels:
            near_high = (
                rf"{re.escape(label)}[^\n。；,，]{{0,24}}(?:高配|overweight|高于目标|相对目标偏高)"
                rf"|(?:高配|overweight|高于目标|相对目标偏高)[^\n。；,，]{{0,24}}{re.escape(label)}"
            )
            near_low = (
                rf"{re.escape(label)}[^\n。；,，]{{0,24}}(?:低配|underweight|低于目标|相对目标偏低)"
                rf"|(?:低配|underweight|低于目标|相对目标偏低)[^\n。；,，]{{0,24}}{re.escape(label)}"
            )
            if expected_text == "underweight":
                conflict_windows.extend(match.group(0) for match in re.finditer(near_high, text, re.IGNORECASE))
            if expected_text == "overweight":
                conflict_windows.extend(match.group(0) for match in re.finditer(near_low, text, re.IGNORECASE))
        joined = "\n".join(conflict_windows)
        if expected_text == "underweight" and joined:
            conflicts.append({"asset": asset, "expected": expected_text, "observed": "overweight wording"})
        if expected_text == "overweight" and joined:
            conflicts.append({"asset": asset, "expected": expected_text, "observed": "underweight wording"})
    return conflicts


def _missing_data_boundary_absent(text: str, facts: dict[str, Any]) -> bool:
    terms = facts.get("missing_data_terms")
    if not isinstance(terms, list):
        terms = ["PE", "估值", "收益率", "黄金价格", "FedWatch"]
    mentions_sensitive_terms = any(str(term) in text for term in terms)
    if not mentions_sensitive_terms:
        return False
    boundary_terms = ["未提供", "本地 context", "本地上下文", "本地数据不足", "不能补编", "不能编造", "无法基于具体数值"]
    return not any(term in text for term in boundary_terms)


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

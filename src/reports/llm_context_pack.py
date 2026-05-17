from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DISCLAIMER = (
    "This context pack is for local research reporting only. It is rule-based and descriptive, "
    "not investment advice, not a forecast, and not a guarantee of returns."
)

SOURCE_FILE_PATHS = {
    "portfolio_snapshot": "outputs/reports/portfolio_snapshot.json",
    "market_snapshot": "outputs/reports/market_snapshot.json",
    "market_temperature": "outputs/reports/market_temperature.json",
    "daily_report_md": "outputs/reports/daily_report.md",
    "market_history_features": "outputs/reports/market_history_features.json",
    "macro_regime_history": "outputs/reports/macro_regime_history.json",
}

MARKET_FACT_KEYS = (
    "sp500",
    "nasdaq",
    "nasdaq100",
    "gold",
    "dgs10",
    "fedfunds",
    "cpi",
    "pce",
    "nonfarm",
    "usd_cny",
)

ALLOWED_MODEL_TASKS = [
    "Explain the current market state using provided facts.",
    "Explain portfolio exposure and allocation deviation.",
    "Provide scenario analysis.",
    "Compare current regime with historical windows.",
    "Identify data limitations.",
    "Suggest observation indicators.",
    "Translate structured data into readable reports.",
]

FORBIDDEN_MODEL_BEHAVIORS = [
    "Do not invent market data.",
    "Do not invent portfolio holdings.",
    "Do not claim historical outcomes are forecasts.",
    "Do not guarantee returns.",
    "Do not provide short-term price predictions.",
    "Do not recommend frequent trading.",
    "Do not ignore the user's small-budget/student context.",
    "Do not override rule-based calculations without evidence.",
    "Do not cite unavailable sources.",
    "Do not treat ETF proxy returns as actual fund NAV returns.",
]

RESPONSE_GUIDELINES = {
    "language": "Chinese by default",
    "style": "direct, factual, structured",
    "required_distinctions": [
        "confirmed facts",
        "rule-based assessments",
        "historical outcomes",
        "reasonable inferences",
        "assumptions",
        "uncertainties",
    ],
    "preferred_structure": [
        "核心结论",
        "关键事实",
        "规则判断",
        "历史参照",
        "对组合的含义",
        "数据限制",
        "可观察指标",
    ],
}


def load_json(path: str) -> dict:
    json_path = Path(path)
    if not json_path.exists():
        return {
            "status": "missing",
            "path": str(json_path),
            "error": "File not found",
        }

    try:
        data = json.loads(json_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        return {
            "status": "error",
            "path": str(json_path),
            "error": f"Invalid JSON: {exc}",
        }

    if not isinstance(data, dict):
        return {
            "status": "error",
            "path": str(json_path),
            "error": "JSON root must be an object",
        }

    return data


def load_text(path: str) -> dict:
    text_path = Path(path)
    if not text_path.exists():
        return {
            "status": "missing",
            "path": str(text_path),
            "error": "File not found",
        }

    try:
        content = text_path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        return {
            "status": "error",
            "path": str(text_path),
            "error": f"Could not read file: {exc}",
        }

    return {
        "status": "ok",
        "path": str(text_path),
        "content": content,
        "error": None,
    }


def build_llm_context_pack(
    portfolio_snapshot: dict,
    market_snapshot: dict,
    market_temperature: dict,
    daily_report_md: str,
    market_history_features: dict,
    macro_regime_history: dict,
) -> dict:
    confirmed_facts = _build_confirmed_facts(portfolio_snapshot, market_snapshot)
    data_limitations = _build_data_limitations(
        portfolio_snapshot,
        market_snapshot,
        market_temperature,
        daily_report_md,
        market_history_features,
        macro_regime_history,
    )

    return {
        "context_pack_type": "local_macro_portfolio_ai_llm_context",
        "generated_at": _utc_now(),
        "source_files": _build_source_files(
            portfolio_snapshot,
            market_snapshot,
            market_temperature,
            daily_report_md,
            market_history_features,
            macro_regime_history,
        ),
        "confirmed_facts": confirmed_facts,
        "rule_based_assessments": _build_rule_based_assessments(
            market_temperature,
            macro_regime_history,
        ),
        "historical_context": _build_historical_context(
            market_history_features,
            macro_regime_history,
        ),
        "portfolio_context": _build_portfolio_context(portfolio_snapshot),
        "data_quality": _build_data_quality(
            portfolio_snapshot,
            market_snapshot,
            market_history_features,
            macro_regime_history,
        ),
        "data_limitations": data_limitations,
        "allowed_model_tasks": ALLOWED_MODEL_TASKS,
        "forbidden_model_behaviors": FORBIDDEN_MODEL_BEHAVIORS,
        "response_guidelines": RESPONSE_GUIDELINES,
        "methodology_notes": _build_methodology_notes(
            market_temperature,
            market_history_features,
            macro_regime_history,
        ),
        "disclaimer": DISCLAIMER,
    }


def render_llm_context_markdown(context_pack: dict) -> str:
    facts = context_pack.get("confirmed_facts", {})
    portfolio = context_pack.get("portfolio_context", {})
    assessments = context_pack.get("rule_based_assessments", {})
    historical = context_pack.get("historical_context", {})
    data_quality = context_pack.get("data_quality", {})

    lines = [
        "# LLM Context Pack",
        "",
        "## 1. Purpose",
        "",
        (
            "Provide a compact, structured context package for future local LLM report generation. "
            "The model should explain only the confirmed facts, rule-based assessments, and historical outcomes included here."
        ),
        "",
        "Historical outcome is not forecast. ETF proxy price returns are not the user's actual fund NAV performance.",
        "",
        "## 2. Confirmed Facts",
        "",
        "### Market Facts",
        "",
        _market_facts_table(facts.get("market", {})),
        "",
        "### Account Facts",
        "",
        _account_facts_table(facts.get("portfolio", {})),
        "",
        "## 3. Portfolio Context",
        "",
        "Cash is treated as cash reserve and excluded from target allocation weights by default.",
        (
            f"Holdings snapshot updated_at: {_display(portfolio.get('holdings_updated_at'))}; "
            f"age_days: {_format_number(portfolio.get('holdings_age_days'))}; "
            f"freshness: {_display(portfolio.get('holdings_freshness_status'))}."
        ),
        "",
        "Holdings detail:",
        "",
        _holdings_detail_table(portfolio.get("holdings", [])),
        "",
        _allocation_table(portfolio),
        "",
        _dca_table(portfolio.get("dca_budget_check", {})),
        "",
        "DCA daily plan details:",
        "",
        _dca_daily_plan_table(portfolio.get("dca_daily_plan", {})),
        "",
        "## 4. Rule-based Assessments",
        "",
        _assessment_table(assessments),
        "",
        "## 5. Historical Context",
        "",
        "Historical outcomes are descriptive analogues only, not forecasts.",
        "",
        _history_features_table(historical.get("market_history_features", {})),
        "",
        "### Macro Regime Summary",
        "",
        _macro_regime_table(historical.get("macro_regime_history", {})),
        "",
        "### Similar Historical Windows",
        "",
        "Historical outcomes are descriptive only and are not forecasts.",
        "",
        _similar_windows_section(historical.get("similar_historical_windows", {})),
        "",
        "## 6. Data Quality and Limitations",
        "",
        _data_quality_table(data_quality.get("market_data_quality", {})),
        "",
        _bullet_list(context_pack.get("data_limitations", []), "No material data limitations recorded."),
        "",
        "## 7. Allowed Model Tasks",
        "",
        _bullet_list(context_pack.get("allowed_model_tasks", [])),
        "",
        "## 8. Forbidden Model Behaviors",
        "",
        _bullet_list(context_pack.get("forbidden_model_behaviors", [])),
        "",
        "## 9. Response Guidelines",
        "",
        _guidelines_table(context_pack.get("response_guidelines", {})),
        "",
        "## 10. Disclaimer",
        "",
        context_pack.get("disclaimer", DISCLAIMER),
        "",
    ]
    return "\n".join(lines)


def _build_confirmed_facts(portfolio_snapshot: dict, market_snapshot: dict) -> dict:
    return {
        "market": {
            key: _extract_market_fact(key, market_snapshot)
            for key in MARKET_FACT_KEYS
        },
        "portfolio": {
            "total_assets": portfolio_snapshot.get("total_assets"),
            "invested_assets": portfolio_snapshot.get("invested_assets"),
            "cash": portfolio_snapshot.get("cash"),
            "total_account_value": portfolio_snapshot.get(
                "total_account_value",
                portfolio_snapshot.get("total_assets"),
            ),
            "invested_asset_value": portfolio_snapshot.get(
                "invested_asset_value",
                portfolio_snapshot.get("invested_assets"),
            ),
            "cash_reserve_value": portfolio_snapshot.get(
                "cash_reserve_value",
                portfolio_snapshot.get("cash"),
            ),
            "total_profit_loss": portfolio_snapshot.get("total_profit_loss"),
            "holdings_updated_at": portfolio_snapshot.get("holdings_updated_at"),
            "holdings_age_days": portfolio_snapshot.get("holdings_age_days"),
            "holdings_freshness_status": portfolio_snapshot.get("holdings_freshness_status"),
            "holdings_updated_at_status": portfolio_snapshot.get("holdings_updated_at_status"),
            "holdings_row_count": portfolio_snapshot.get("holdings_row_count"),
            "holdings_source": portfolio_snapshot.get("holdings_source", {}),
        },
    }


def _extract_market_fact(key: str, market_snapshot: dict) -> dict:
    item = _find_market_item(key, market_snapshot)
    if not isinstance(item, dict):
        return {
            "value": None,
            "source": None,
            "series_id": None,
            "symbol": None,
            "observation_date": None,
            "status": "missing",
            "data_quality": {
                "source_tier": None,
                "freshness_status": "unknown",
            },
        }

    data_quality = item.get("data_quality", {})
    return {
        "name": item.get("name"),
        "value": item.get("value"),
        "source": item.get("source"),
        "series_id": item.get("series_id"),
        "symbol": item.get("symbol"),
        "function": item.get("function"),
        "observation_date": item.get("observation_date"),
        "status": item.get("status"),
        "error": item.get("error"),
        "data_quality": {
            "source_tier": data_quality.get("source_tier") if isinstance(data_quality, dict) else None,
            "freshness_status": data_quality.get("freshness_status") if isinstance(data_quality, dict) else None,
            "importance": data_quality.get("importance") if isinstance(data_quality, dict) else None,
        },
    }


def _build_rule_based_assessments(market_temperature: dict, macro_regime_history: dict) -> dict:
    temperature = market_temperature.get("temperature_assessment", {})
    current = macro_regime_history.get("current_regime_snapshot", {})
    crisis = macro_regime_history.get("crisis_window_summary", {})
    return {
        "market_temperature": {
            "equity_temperature": temperature.get("equity_temperature", {}),
            "rate_pressure": temperature.get("rate_pressure", {}),
            "inflation_pressure": temperature.get("inflation_pressure", {}),
            "labor_market": temperature.get("labor_market", {}),
            "fx_pressure": temperature.get("fx_pressure", {}),
            "overall_regime": temperature.get("overall_regime"),
            "risk_level": temperature.get("risk_level"),
            "methodology_note": temperature.get("methodology_note"),
        },
        "macro_current_regime": {
            "current_regime_label": current.get("regime_classification", {}).get("regime_label"),
            "regime_classification": current.get("regime_classification", {}),
        },
        "crisis_regime_classifications": {
            key: {
                "name": item.get("name"),
                "start": item.get("start"),
                "effective_end": item.get("effective_end") or item.get("end"),
                "ongoing": item.get("ongoing"),
                "regime_classification": item.get("regime_classification", {}),
            }
            for key, item in crisis.items()
            if isinstance(item, dict)
        },
        "note": "These are rule-based classifications, not forecasts.",
    }


def _build_historical_context(market_history_features: dict, macro_regime_history: dict) -> dict:
    assets = market_history_features.get("assets", {})
    similar_windows = _compact_similar_windows(
        macro_regime_history.get("similar_historical_windows", {})
    )
    return {
        "market_history_features": {
            key: _asset_history_summary(item)
            for key, item in assets.items()
            if isinstance(item, dict)
        },
        "similar_historical_windows": similar_windows,
        "macro_regime_history": {
            "crisis_window_summary": macro_regime_history.get("crisis_window_summary", {}),
            "methodology_note": macro_regime_history.get("methodology_note"),
        },
        "notes": [
            "Historical outcomes are not forecasts.",
            "ETF proxy price returns are not the user's actual fund NAV performance.",
            "Similar windows are descriptive analogues only.",
        ],
    }


def _asset_history_summary(item: dict) -> dict:
    return {
        "symbol": item.get("symbol"),
        "name": item.get("name"),
        "proxy_for": item.get("proxy_for"),
        "proxy_note": item.get("proxy_note"),
        "return_type": item.get("return_type"),
        "source": item.get("source"),
        "status": item.get("status"),
        "latest_date": item.get("latest_date"),
        "latest_close": item.get("latest_close"),
        "return_1m": item.get("return_1m"),
        "return_3m": item.get("return_3m"),
        "max_drawdown_3m": item.get("max_drawdown_3m"),
        "volatility_1m_annualized": item.get("volatility_1m_annualized"),
        "distance_from_recent_high": item.get("distance_from_recent_high"),
    }


def _compact_similar_windows(similar_windows: dict) -> dict:
    if not isinstance(similar_windows, dict):
        similar_windows = {}
    fully_observed = [
        _compact_similar_match(item)
        for item in similar_windows.get("fully_observed_matches", [])
        if _is_fully_observed(item)
    ][:5]
    recent_incomplete = [
        _compact_similar_match(item)
        for item in similar_windows.get("recent_incomplete_matches", [])
    ][:3]
    return {
        "fully_observed_matches": fully_observed,
        "recent_incomplete_matches": recent_incomplete,
        "selection_note": similar_windows.get("selection_note"),
    }


def _compact_similar_match(item: dict) -> dict:
    if not isinstance(item, dict):
        item = {}
    return {
        "window_start": item.get("window_start"),
        "window_end": item.get("window_end"),
        "similarity_score": item.get("similarity_score"),
        "matched_buckets": item.get("matched_buckets", []),
        "missing_buckets": item.get("missing_buckets", []),
        "outcome_availability": item.get("outcome_availability", {}),
        "next_3m_sp500_return": _compact_historical_outcome(
            item.get("next_3m_sp500_return", {})
        ),
        "next_12m_sp500_return": _compact_historical_outcome(
            item.get("next_12m_sp500_return", {})
        ),
        "notes": item.get("notes"),
    }


def _compact_historical_outcome(outcome: dict) -> dict:
    if not isinstance(outcome, dict):
        return {"return_pct": None, "status": "insufficient_data"}
    return {
        "return_pct": outcome.get("return_pct"),
        "status": outcome.get("status"),
    }


def _is_fully_observed(item: dict) -> bool:
    availability = item.get("outcome_availability", {}) if isinstance(item, dict) else {}
    return (
        availability.get("next_3m") == "ok"
        and availability.get("next_12m") == "ok"
        and item.get("next_3m_sp500_return", {}).get("status") == "ok"
        and item.get("next_12m_sp500_return", {}).get("status") == "ok"
    )


def _build_portfolio_context(portfolio_snapshot: dict) -> dict:
    return {
        "weights_ex_cash": portfolio_snapshot.get("weights_ex_cash", {}),
        "holdings": portfolio_snapshot.get("holdings", []),
        "target_allocation": portfolio_snapshot.get("target_allocation", {}),
        "deviation": portfolio_snapshot.get("deviation", {}),
        "deviation_flags": portfolio_snapshot.get("deviation_flags", {}),
        "dca_budget_check": portfolio_snapshot.get("dca_budget_check", {}),
        "dca_daily_plan": portfolio_snapshot.get("dca_daily_plan", {}),
        "holdings_updated_at": portfolio_snapshot.get("holdings_updated_at"),
        "holdings_age_days": portfolio_snapshot.get("holdings_age_days"),
        "holdings_freshness_status": portfolio_snapshot.get("holdings_freshness_status"),
        "holdings_updated_at_status": portfolio_snapshot.get("holdings_updated_at_status"),
        "holdings_source": portfolio_snapshot.get("holdings_source", {}),
        "notes": [
            "Allowed descriptive terms include underweight, overweight, and DCA monthly budget status.",
            "Cash is treated as cash reserve and excluded from target allocation weights.",
            "Cash reserve can be a DCA deduction source; it is not a target investment asset.",
            "Do not output buy/sell commands, precise trading instructions, or return guarantees.",
        ],
    }


def _build_data_quality(
    portfolio_snapshot: dict,
    market_snapshot: dict,
    market_history_features: dict,
    macro_regime_history: dict,
) -> dict:
    return {
        "market_snapshot_status": market_snapshot.get("status"),
        "market_snapshot_error": market_snapshot.get("error"),
        "used_cache": market_snapshot.get("diagnostics", {}).get("used_cache"),
        "portfolio_holdings_updated_at": portfolio_snapshot.get("holdings_updated_at"),
        "portfolio_holdings_age_days": portfolio_snapshot.get("holdings_age_days"),
        "portfolio_holdings_freshness_status": portfolio_snapshot.get("holdings_freshness_status"),
        "portfolio_holdings_updated_at_status": portfolio_snapshot.get("holdings_updated_at_status"),
        "market_data_quality": _extract_market_data_quality(market_snapshot),
        "macro_regime_history_data_limitations": macro_regime_history.get("data_limitations", []),
        "market_history_features_data_limitations": market_history_features.get("data_limitations", []),
        "portfolio_holdings_source": portfolio_snapshot.get("holdings_source", {}),
    }


def _extract_market_data_quality(market_snapshot: dict) -> dict:
    quality = {}
    for section in ("market_data", "macro_data", "fx_data"):
        items = market_snapshot.get(section, {})
        if not isinstance(items, dict):
            continue
        for key, item in items.items():
            if isinstance(item, dict):
                quality[key] = item.get("data_quality", {})
    return quality


def _build_data_limitations(
    portfolio_snapshot: dict,
    market_snapshot: dict,
    market_temperature: dict,
    daily_report_md: str,
    market_history_features: dict,
    macro_regime_history: dict,
) -> list[str]:
    limitations = []

    for name, payload in (
        ("portfolio_snapshot", portfolio_snapshot),
        ("market_snapshot", market_snapshot),
        ("market_temperature", market_temperature),
        ("market_history_features", market_history_features),
        ("macro_regime_history", macro_regime_history),
    ):
        if payload.get("status") in {"missing", "error"}:
            limitations.append(f"{name}: {payload.get('error') or payload.get('status')}")

    if not daily_report_md:
        limitations.append("daily_report_md: File not found or empty.")

    holdings_source = portfolio_snapshot.get("holdings_source", {})
    if holdings_source.get("mode") == "sample_fallback":
        limitations.append("Portfolio data is sample fallback, not the user's real account.")
    if holdings_source.get("warning"):
        limitations.append(str(holdings_source["warning"]))
    if portfolio_snapshot.get("holdings_updated_at_status") == "mixed":
        limitations.append(
            "holdings rows have mixed updated_at values: "
            f"{portfolio_snapshot.get('holdings_updated_at_values', [])}"
        )
    elif portfolio_snapshot.get("holdings_updated_at_status") == "missing":
        limitations.append("missing holdings updated_at: current holdings snapshot freshness is unknown.")

    freshness_status = portfolio_snapshot.get("holdings_freshness_status")
    if freshness_status in {"stale", "very_stale"}:
        limitations.append(
            "holdings snapshot is "
            f"{freshness_status}: updated_at={portfolio_snapshot.get('holdings_updated_at')} "
            f"age_days={portfolio_snapshot.get('holdings_age_days')}; account data is not real-time."
        )
    elif freshness_status == "unknown":
        limitations.append("holdings snapshot freshness is unknown; account data should not be treated as real-time.")

    if market_snapshot.get("status") not in {None, "ok"} and market_snapshot.get("error"):
        limitations.append(f"market_snapshot: {market_snapshot.get('error')}")
    if market_snapshot.get("diagnostics", {}).get("used_cache"):
        limitations.append("market_snapshot used stale cache.")

    for section in ("market_data", "macro_data", "fx_data"):
        items = market_snapshot.get(section, {})
        if not isinstance(items, dict):
            continue
        for key, item in items.items():
            if isinstance(item, dict) and item.get("status") != "ok":
                limitations.append(f"{section}.{key}: {item.get('status')} - {item.get('error')}")

    for source_name, payload in (
        ("market_temperature", market_temperature),
        ("market_history_features", market_history_features),
        ("macro_regime_history", macro_regime_history),
    ):
        source_limitations = payload.get("data_limitations", [])
        if isinstance(source_limitations, list):
            limitations.extend(f"{source_name}: {item}" for item in source_limitations)

    return _dedupe_strings([item for item in limitations if item])


def _build_source_files(
    portfolio_snapshot: dict,
    market_snapshot: dict,
    market_temperature: dict,
    daily_report_md: str,
    market_history_features: dict,
    macro_regime_history: dict,
) -> list[dict]:
    payloads = {
        "portfolio_snapshot": portfolio_snapshot,
        "market_snapshot": market_snapshot,
        "market_temperature": market_temperature,
        "market_history_features": market_history_features,
        "macro_regime_history": macro_regime_history,
    }
    source_files = []
    for key, path in SOURCE_FILE_PATHS.items():
        if key == "daily_report_md":
            status = "ok" if daily_report_md else "missing"
            error = None if daily_report_md else "File not found"
        else:
            payload = payloads.get(key, {})
            status = "missing" if payload.get("status") == "missing" else "ok"
            error = payload.get("error") if payload.get("status") in {"missing", "error"} else None
        source_files.append({"key": key, "path": path, "status": status, "error": error})
    return source_files


def _build_methodology_notes(
    market_temperature: dict,
    market_history_features: dict,
    macro_regime_history: dict,
) -> list[str]:
    notes = [
        "LLM context pack contains structured facts and rule-based outputs only.",
        "Historical outcome is not forecast.",
        "ETF proxy price returns are not actual fund NAV returns.",
    ]
    for payload in (
        market_temperature.get("temperature_assessment", {}),
        market_history_features,
        macro_regime_history,
    ):
        note = payload.get("methodology_note") if isinstance(payload, dict) else None
        if note:
            notes.append(str(note))
    return _dedupe_strings(notes)


def _find_market_item(key: str, market_snapshot: dict) -> dict | None:
    for section in ("market_data", "macro_data", "fx_data"):
        item = market_snapshot.get(section, {}).get(key)
        if isinstance(item, dict):
            return item
    return None


def _market_facts_table(market_facts: dict) -> str:
    rows = []
    for key in MARKET_FACT_KEYS:
        item = market_facts.get(key, {})
        data_quality = item.get("data_quality", {})
        rows.append(
            [
                key,
                _format_number(item.get("value")),
                item.get("source"),
                item.get("series_id") or item.get("symbol"),
                item.get("observation_date"),
                item.get("status"),
                data_quality.get("source_tier"),
                data_quality.get("freshness_status"),
            ]
        )
    return _markdown_table(
        ["Key", "Value", "Source", "ID/Symbol", "Observation date", "Status", "Source tier", "Freshness"],
        rows,
    )


def _account_facts_table(portfolio_facts: dict) -> str:
    holdings_source = portfolio_facts.get("holdings_source", {})
    return _markdown_table(
        ["Metric", "Value"],
        [
            ["total_assets", _format_number(portfolio_facts.get("total_assets"))],
            ["invested_assets", _format_number(portfolio_facts.get("invested_assets"))],
            ["cash", _format_number(portfolio_facts.get("cash"))],
            ["total_account_value", _format_number(portfolio_facts.get("total_account_value"))],
            ["invested_asset_value", _format_number(portfolio_facts.get("invested_asset_value"))],
            ["cash_reserve_value", _format_number(portfolio_facts.get("cash_reserve_value"))],
            ["total_profit_loss", _format_number(portfolio_facts.get("total_profit_loss"))],
            ["holdings_updated_at", portfolio_facts.get("holdings_updated_at")],
            ["holdings_age_days", _format_number(portfolio_facts.get("holdings_age_days"))],
            ["holdings_freshness_status", portfolio_facts.get("holdings_freshness_status")],
            ["holdings_updated_at_status", portfolio_facts.get("holdings_updated_at_status")],
            ["holdings_row_count", _format_number(portfolio_facts.get("holdings_row_count"))],
            ["holdings_source.mode", holdings_source.get("mode")],
            ["holdings_source.warning", holdings_source.get("warning")],
            ["holdings_source.cash_reserve_note", holdings_source.get("cash_reserve_note")],
        ],
    )


def _allocation_table(portfolio: dict) -> str:
    weights = portfolio.get("weights_ex_cash", {})
    targets = portfolio.get("target_allocation", {})
    deviations = portfolio.get("deviation", {})
    flags = portfolio.get("deviation_flags", {})
    keys = list(dict.fromkeys([*targets.keys(), *weights.keys(), *deviations.keys(), *flags.keys()]))
    rows = [
        [
            key,
            _format_percent(weights.get(key)),
            _format_percent(targets.get(key)),
            _format_percent(deviations.get(key), signed=True),
            flags.get(key),
        ]
        for key in keys
    ]
    return _markdown_table(["Asset", "Current ex-cash", "Target", "Deviation", "Flag"], rows)


def _holdings_detail_table(holdings: list[dict]) -> str:
    if not isinstance(holdings, list) or not holdings:
        return "No holdings detail recorded."

    rows = []
    for holding in holdings:
        if not isinstance(holding, dict):
            continue
        rows.append(
            [
                holding.get("asset_name"),
                holding.get("fund_code"),
                holding.get("asset_class"),
                _format_number(holding.get("current_value")),
                _format_number(holding.get("profit_loss")),
                holding.get("updated_at"),
            ]
        )
    return _markdown_table(
        ["Asset name", "Fund code", "Asset class", "Current value", "Profit/loss", "Updated at"],
        rows,
    )


def _dca_table(dca: dict) -> str:
    return _markdown_table(
        ["DCA metric", "Value"],
        [
            ["daily_total", _format_number(dca.get("daily_total"))],
            ["monthly_required", _format_number(dca.get("monthly_required"))],
            ["budget_min", _format_number(dca.get("budget_min"))],
            ["budget_max", _format_number(dca.get("budget_max"))],
            ["trading_days", _format_number(dca.get("trading_days"))],
            ["status", dca.get("status")],
        ],
    )


def _dca_daily_plan_table(dca_daily_plan: dict) -> str:
    if not isinstance(dca_daily_plan, dict) or not dca_daily_plan:
        return "No DCA daily plan recorded."

    rows = []
    for key, item in dca_daily_plan.items():
        if not isinstance(item, dict):
            continue
        rows.append(
            [
                key,
                item.get("name"),
                item.get("asset_class"),
                _format_number(item.get("daily_amount")),
                item.get("status"),
            ]
        )
    return _markdown_table(["Key", "Name", "Asset class", "Daily amount", "Status"], rows)


def _assessment_table(assessments: dict) -> str:
    temperature = assessments.get("market_temperature", {})
    macro_current = assessments.get("macro_current_regime", {})
    rows = [
        ["equity_temperature", _level(temperature.get("equity_temperature"))],
        ["rate_pressure", _level(temperature.get("rate_pressure"))],
        ["inflation_pressure", _level(temperature.get("inflation_pressure"))],
        ["labor_market", _level(temperature.get("labor_market"))],
        ["fx_pressure", _level(temperature.get("fx_pressure"))],
        ["overall_regime", temperature.get("overall_regime")],
        ["risk_level", temperature.get("risk_level")],
        ["macro_current_regime", macro_current.get("current_regime_label")],
        ["note", assessments.get("note")],
    ]
    return _markdown_table(["Assessment", "Value"], rows)


def _history_features_table(features: dict) -> str:
    if not features:
        return "No market history features available."
    rows = []
    for key, item in features.items():
        rows.append(
            [
                key,
                item.get("proxy_for"),
                item.get("latest_date"),
                _format_number(item.get("latest_close")),
                _format_ratio_as_percent(_nested_value(item, ("return_1m", "value"))),
                _format_ratio_as_percent(_nested_value(item, ("return_3m", "value"))),
                _format_ratio_as_percent(_nested_value(item, ("max_drawdown_3m", "value"))),
                _format_ratio_as_percent(_nested_value(item, ("volatility_1m_annualized", "value"))),
                item.get("return_type"),
                item.get("proxy_note"),
            ]
        )
    return _markdown_table(
        [
            "Asset",
            "Proxy for",
            "Latest date",
            "Latest close",
            "1M return",
            "3M return",
            "3M max drawdown",
            "1M annualized vol",
            "Return type",
            "Proxy note",
        ],
        rows,
    )


def _macro_regime_table(macro: dict) -> str:
    crisis = macro.get("crisis_window_summary", {})
    rows = []
    for key, item in crisis.items():
        if not isinstance(item, dict):
            continue
        classification = item.get("regime_classification", {})
        rows.append(
            [
                key,
                item.get("name"),
                item.get("start"),
                item.get("effective_end") or item.get("end"),
                item.get("ongoing"),
                classification.get("regime_label"),
                classification.get("confidence"),
            ]
        )
    return _markdown_table(
        ["Window", "Name", "Start", "Effective end", "Ongoing", "Regime", "Confidence"],
        rows,
    )


def _similar_windows_section(similar_windows: dict) -> str:
    fully_observed = similar_windows.get("fully_observed_matches", []) if isinstance(similar_windows, dict) else []
    recent_incomplete = similar_windows.get("recent_incomplete_matches", []) if isinstance(similar_windows, dict) else []
    lines = [
        f"Selection note: {_display(similar_windows.get('selection_note') if isinstance(similar_windows, dict) else None)}",
        "",
        "#### Fully Observed Historical Matches",
        "",
        _fully_observed_similar_table(fully_observed),
        "",
        "#### Recent Similar Windows With Incomplete Outcomes",
        "",
        _recent_incomplete_similar_table(recent_incomplete),
    ]
    return "\n".join(lines)


def _fully_observed_similar_table(matches: list[dict]) -> str:
    if not matches:
        return "No fully observed similar windows recorded."
    rows = [
        [
            _window_label(item),
            item.get("similarity_score"),
            ", ".join(item.get("matched_buckets", [])),
            ", ".join(item.get("missing_buckets", [])),
            _outcome_display(item.get("next_3m_sp500_return", {})),
            _outcome_display(item.get("next_12m_sp500_return", {})),
        ]
        for item in matches
    ]
    return _markdown_table(
        [
            "Window",
            "Score",
            "Matched Buckets",
            "Missing Buckets",
            "3M Historical Outcome",
            "12M Historical Outcome",
        ],
        rows,
    )


def _recent_incomplete_similar_table(matches: list[dict]) -> str:
    if not matches:
        return "No recent incomplete similar windows recorded."
    rows = [
        [
            _window_label(item),
            item.get("similarity_score"),
            ", ".join(item.get("matched_buckets", [])),
            _availability_display(item.get("outcome_availability", {})),
            _outcome_display(item.get("next_3m_sp500_return", {})),
            _outcome_display(item.get("next_12m_sp500_return", {})),
        ]
        for item in matches
    ]
    return _markdown_table(
        [
            "Window",
            "Score",
            "Matched Buckets",
            "Outcome Availability",
            "3M Historical Outcome",
            "12M Historical Outcome",
        ],
        rows,
    )


def _window_label(item: dict) -> str:
    return f"{_display(item.get('window_start'))} to {_display(item.get('window_end'))}"


def _outcome_display(outcome: dict) -> str:
    if not isinstance(outcome, dict):
        return "insufficient_data"
    status = outcome.get("status")
    return_pct = outcome.get("return_pct")
    if status != "ok":
        return _display(status or "insufficient_data")
    return _format_plain_percent(return_pct)


def _availability_display(availability: dict) -> str:
    if not isinstance(availability, dict):
        return "unknown"
    return f"3m={_display(availability.get('next_3m'))}, 12m={_display(availability.get('next_12m'))}"


def _data_quality_table(quality: dict) -> str:
    if not quality:
        return "No data quality fields available."
    rows = [
        [
            key,
            item.get("expected_frequency"),
            item.get("importance"),
            item.get("source_tier"),
            item.get("freshness_status"),
            item.get("observation_date"),
            item.get("status"),
        ]
        for key, item in quality.items()
        if isinstance(item, dict)
    ]
    return _markdown_table(
        ["Key", "Frequency", "Importance", "Source tier", "Freshness", "Observation date", "Status"],
        rows,
    )


def _guidelines_table(guidelines: dict) -> str:
    return _markdown_table(
        ["Field", "Value"],
        [
            ["language", guidelines.get("language")],
            ["style", guidelines.get("style")],
            ["required_distinctions", ", ".join(guidelines.get("required_distinctions", []))],
            ["preferred_structure", " / ".join(guidelines.get("preferred_structure", []))],
        ],
    )


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    header_line = "| " + " | ".join(_escape_cell(header) for header in headers) + " |"
    divider = "| " + " | ".join("---" for _ in headers) + " |"
    row_lines = [
        "| " + " | ".join(_escape_cell(value) for value in row) + " |"
        for row in rows
    ]
    return "\n".join([header_line, divider, *row_lines])


def _bullet_list(items: list[str], empty_text: str = "None recorded.") -> str:
    if not items:
        return empty_text
    return "\n".join(f"- {_escape_inline(item)}" for item in items)


def _escape_cell(value: Any) -> str:
    text = _display(value)
    text = text.replace("\r", " ").replace("\n", " ")
    text = text.replace("|", "\\|")
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    if len(text) > 180:
        text = text[:177].rstrip() + "..."
    return text


def _escape_inline(value: Any) -> str:
    text = _display(value)
    text = text.replace("\r", " ").replace("\n", " ")
    text = text.replace("|", "\\|")
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    return text


def _format_number(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def _format_percent(value: Any, signed: bool = False) -> str:
    if value is None:
        return "N/A"
    try:
        percent = float(value) * 100
    except (TypeError, ValueError):
        return str(value)
    sign = "+" if signed and percent > 0 else ""
    return f"{sign}{percent:.2f}%"


def _format_ratio_as_percent(value: Any) -> str:
    return _format_percent(value)


def _format_plain_percent(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return str(value)


def _nested_value(source: dict, path: tuple[str, ...]) -> Any:
    current: Any = source
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _level(value: Any) -> str:
    if isinstance(value, dict):
        return _display(value.get("level"))
    return _display(value)


def _display(value: Any) -> str:
    if value is None or value == "":
        return "N/A"
    return str(value)


def _dedupe_strings(items: list[str]) -> list[str]:
    result = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

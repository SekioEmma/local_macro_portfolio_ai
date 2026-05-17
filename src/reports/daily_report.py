from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DISCLAIMER = (
    "This report is rule-based and descriptive, not investment advice. "
    "It does not predict short-term market moves, guarantee returns, or recommend trades."
)


def load_json(path: str) -> dict:
    json_path = Path(path)
    if not json_path.exists():
        return {
            "status": "error",
            "error": f"JSON file not found: {json_path}",
            "path": str(json_path),
        }

    try:
        data = json.loads(json_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        return {
            "status": "error",
            "error": f"Invalid JSON in {json_path}: {exc}",
            "path": str(json_path),
        }

    if not isinstance(data, dict):
        return {
            "status": "error",
            "error": f"JSON root must be an object: {json_path}",
            "path": str(json_path),
        }

    return data


def build_daily_report_json(
    portfolio_snapshot: dict,
    market_snapshot: dict,
    market_temperature: dict,
) -> dict:
    market_summary = _build_market_summary(market_snapshot)
    temperature_assessment = market_temperature.get("temperature_assessment", {})
    temperature_summary = _build_temperature_summary(temperature_assessment)
    data_limitations = _build_data_limitations(
        portfolio_snapshot,
        market_snapshot,
        market_temperature,
        market_summary,
    )

    report = {
        "report_type": "daily_portfolio_market_report",
        "generated_at": _utc_now(),
        "holdings_source": portfolio_snapshot.get("holdings_source", {}),
        "holdings": portfolio_snapshot.get("holdings", []),
        "account_summary": {
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
            "cash_reserve_note": (
                "Cash reserve is excluded from target-allocation weights and can be "
                "the DCA deduction source."
            ),
        },
        "allocation_summary": {
            "weights_ex_cash": portfolio_snapshot.get("weights_ex_cash", {}),
            "target_allocation": portfolio_snapshot.get("target_allocation", {}),
            "deviation": portfolio_snapshot.get("deviation", {}),
            "deviation_flags": portfolio_snapshot.get("deviation_flags", {}),
            "note": "Cash is excluded from target-allocation weights by default.",
        },
        "dca_budget_summary": _copy_keys(
            portfolio_snapshot.get("dca_budget_check", {}),
            (
                "daily_total",
                "monthly_required",
                "budget_min",
                "budget_max",
                "trading_days",
                "status",
            ),
        ),
        "dca_daily_plan": portfolio_snapshot.get("dca_daily_plan", {}),
        "market_summary": market_summary,
        "temperature_summary": temperature_summary,
        "data_sources": _extract_data_sources(market_snapshot, market_temperature),
        "data_limitations": data_limitations,
        "rule_based_observations": _build_rule_based_observations(
            portfolio_snapshot,
            temperature_summary,
            data_limitations,
        ),
        "disclaimer": DISCLAIMER,
    }

    return report


def render_daily_report_markdown(report: dict) -> str:
    lines = [
        "# Daily Portfolio & Market Report",
        "",
        f"Generated at: {_display(report.get('generated_at'))}",
        "",
        "This report is rule-based and descriptive, not investment advice.",
        "",
        "## 1. Account Summary",
        "",
        _markdown_table(
            ["Metric", "Value"],
            [
                [
                    "Total account value including cash",
                    _format_number(report["account_summary"].get("total_account_value")),
                ],
                [
                    "Invested asset value excluding cash",
                    _format_number(report["account_summary"].get("invested_asset_value")),
                ],
                [
                    "Cash reserve value",
                    _format_number(report["account_summary"].get("cash_reserve_value")),
                ],
                ["Total profit/loss", _format_number(report["account_summary"].get("total_profit_loss"))],
                ["Holdings snapshot updated_at", _display(report["account_summary"].get("holdings_updated_at"))],
                ["Holdings age days", _format_number(report["account_summary"].get("holdings_age_days"))],
                ["Holdings freshness status", _display(report["account_summary"].get("holdings_freshness_status"))],
                ["Holdings updated_at status", _display(report["account_summary"].get("holdings_updated_at_status"))],
                ["Holdings row count", _format_number(report["account_summary"].get("holdings_row_count"))],
                ["Cash reserve note", _display(report["account_summary"].get("cash_reserve_note"))],
                ["Holdings source mode", _display(report.get("holdings_source", {}).get("mode"))],
                ["Holdings source path", _display(report.get("holdings_source", {}).get("path"))],
                ["Holdings source warning", _display(report.get("holdings_source", {}).get("warning"))],
                ["Cash reserve source note", _display(report.get("holdings_source", {}).get("cash_reserve_note"))],
            ],
        ),
        "",
        "Holdings snapshot details:",
        "",
        _holdings_table(report.get("holdings", [])),
        "",
        "## 2. Allocation vs Target",
        "",
        report["allocation_summary"].get(
            "note",
            "Cash is excluded from target-allocation weights by default.",
        ),
        "",
        _allocation_table(report["allocation_summary"]),
        "",
        "## 3. DCA Budget Check",
        "",
        _markdown_table(
            ["Metric", "Value"],
            [
                ["Daily total", _format_number(report["dca_budget_summary"].get("daily_total"))],
                ["Monthly required", _format_number(report["dca_budget_summary"].get("monthly_required"))],
                ["Budget min", _format_number(report["dca_budget_summary"].get("budget_min"))],
                ["Budget max", _format_number(report["dca_budget_summary"].get("budget_max"))],
                ["Trading days estimate", _format_number(report["dca_budget_summary"].get("trading_days"))],
                ["Status", _display(report["dca_budget_summary"].get("status"))],
            ],
        ),
        "",
        _dca_daily_plan_table(report.get("dca_daily_plan", {})),
        "",
        "## 4. Market Snapshot",
        "",
        _market_table(report["market_summary"]),
        "",
        "## 5. Market Temperature",
        "",
        _temperature_table(report["temperature_summary"]),
        "",
        f"Methodology: {_display(report['temperature_summary'].get('methodology_note'))}",
        "",
        "## 6. Rule-based Observations",
        "",
        _bullet_list(report.get("rule_based_observations", [])),
        "",
        "## 7. Data Sources",
        "",
        _data_sources_table(report.get("data_sources", [])),
        "",
        "## 8. Data Limitations",
        "",
        _bullet_list(report.get("data_limitations", []), empty_text="No material data limitations recorded."),
        "",
        "## 9. Disclaimer",
        "",
        report.get("disclaimer", DISCLAIMER),
        "",
    ]

    return "\n".join(lines)


def _build_market_summary(market_snapshot: dict) -> dict:
    sections = {
        "sp500": ("market_data", "sp500", "SP500"),
        "nasdaq": ("market_data", "nasdaq", "NASDAQCOM"),
        "nasdaq100": ("market_data", "nasdaq100", "Nasdaq 100"),
        "gold": ("market_data", "gold", "Gold"),
        "dgs10": ("macro_data", "dgs10", "DGS10"),
        "fedfunds": ("macro_data", "fedfunds", "FEDFUNDS"),
        "cpi": ("macro_data", "cpi", "CPI"),
        "pce": ("macro_data", "pce", "PCE"),
        "nonfarm": ("macro_data", "nonfarm", "PAYEMS"),
        "usd_cny": ("fx_data", "usd_cny", "USD/CNY"),
    }

    summary = {}
    for output_key, (section, item_key, fallback_name) in sections.items():
        item = market_snapshot.get(section, {}).get(item_key)
        summary[output_key] = _market_item_summary(item, fallback_name)

    return summary


def _market_item_summary(item: Any, fallback_name: str) -> dict:
    if not isinstance(item, dict):
        return {
            "name": fallback_name,
            "value": None,
            "observation_date": None,
            "source": None,
            "series_id": None,
            "symbol": None,
            "data_quality": {},
            "status": "error",
            "error": "Market data item missing.",
        }

    return {
        "name": item.get("name") or fallback_name,
        "value": item.get("value"),
        "observation_date": item.get("observation_date"),
        "source": _display_source_for_market_item(item),
        "series_id": item.get("series_id"),
        "symbol": item.get("symbol"),
        "status": item.get("status"),
        "error": item.get("error"),
        "attempted_sources": item.get("attempted_sources", []),
        "data_quality": item.get("data_quality", {}),
    }


def _build_temperature_summary(temperature_assessment: dict) -> dict:
    if not isinstance(temperature_assessment, dict):
        temperature_assessment = {}

    return {
        "equity_temperature": temperature_assessment.get("equity_temperature", {}),
        "rate_pressure": temperature_assessment.get("rate_pressure", {}),
        "inflation_pressure": temperature_assessment.get("inflation_pressure", {}),
        "labor_market": temperature_assessment.get("labor_market", {}),
        "fx_pressure": temperature_assessment.get("fx_pressure", {}),
        "overall_regime": temperature_assessment.get("overall_regime"),
        "risk_level": temperature_assessment.get("risk_level"),
        "methodology_note": temperature_assessment.get(
            "methodology_note",
            "Rule-based descriptive assessment, not a market forecast.",
        ),
    }


def _build_data_limitations(
    portfolio_snapshot: dict,
    market_snapshot: dict,
    market_temperature: dict,
    market_summary: dict,
) -> list[str]:
    limitations = []

    for snapshot_name, snapshot in (
        ("portfolio_snapshot", portfolio_snapshot),
        ("market_snapshot", market_snapshot),
        ("market_temperature", market_temperature),
    ):
        if snapshot.get("status") in {"error", "stale_cache"} and snapshot.get("error"):
            limitations.append(f"{snapshot_name}: {snapshot['error']}")

    if market_snapshot.get("status") == "stale_cache" or market_snapshot.get(
        "diagnostics", {}
    ).get("used_cache"):
        limitations.append(
            "cache used: market_snapshot includes stale cache because required core live fetch failed."
        )

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

    for section in ("market_data", "macro_data", "fx_data"):
        items = market_snapshot.get(section, {})
        if not isinstance(items, dict):
            continue
        for key, item in items.items():
            if not isinstance(item, dict):
                continue
            if isinstance(item, dict) and item.get("status") == "error":
                prefix = f"{section}.{key}"
                if section == "market_data" and key == "nasdaq100":
                    prefix = "important optional nasdaq100"
                elif section == "market_data" and key == "gold":
                    prefix = "optional gold"
                limitations.append(f"{prefix} unavailable: {item.get('error')}")

            data_quality = item.get("data_quality", {})
            if (
                isinstance(data_quality, dict)
                and data_quality.get("importance") == "required_core"
                and data_quality.get("freshness_status") == "stale"
            ):
                limitations.append(
                    f"required_core stale: {key} observation_date={data_quality.get('observation_date')}"
                )

            if (
                isinstance(data_quality, dict)
                and data_quality.get("freshness_status") == "extended_monthly_lag"
            ):
                limitations.append(
                    "informational monthly lag: "
                    f"{key} observation_date={data_quality.get('observation_date')} "
                    f"month_gap={data_quality.get('month_gap')}"
                )

            if key == "gold" and _manual_missing(item) and not _gold_unavailable_mentions_manual_missing(
                limitations
            ):
                limitations.append("manual gold missing: manual market data file not found.")

    for item_key in ("nasdaq100", "gold"):
        item = market_summary.get(item_key, {})
        if item.get("status") not in {"ok", "stale_cache"} and item.get("error"):
            limitations.append(
                f"{item_key} unavailable or incomplete: {item.get('error')}"
            )

    temp_limitations = market_temperature.get("data_limitations", [])
    if isinstance(temp_limitations, list):
        limitations.extend(str(item) for item in temp_limitations)

    return _dedupe_limitations([item for item in limitations if item])


def _build_rule_based_observations(
    portfolio_snapshot: dict,
    temperature_summary: dict,
    data_limitations: list[str],
) -> list[str]:
    observations = []

    deviation_flags = portfolio_snapshot.get("deviation_flags", {})
    deviation = portfolio_snapshot.get("deviation", {})
    for asset_class, flag in deviation_flags.items():
        if flag == "underweight":
            observations.append(
                f"{asset_class} is below the target weight by {_format_percent_abs(deviation.get(asset_class))}."
            )
        elif flag == "overweight":
            observations.append(
                f"{asset_class} is above the target weight by {_format_percent_abs(deviation.get(asset_class))}."
            )

    dca = portfolio_snapshot.get("dca_budget_check", {})
    if dca.get("status") == "above_budget":
        observations.append(
            "The current DCA plan requires more than the configured monthly budget range."
        )
    elif dca.get("status") == "within_budget":
        observations.append(
            "The current DCA plan is within the configured monthly budget range."
        )
    elif dca.get("status") == "below_budget":
        observations.append(
            "The current DCA plan is below the configured monthly budget range."
        )

    equity_level = _level(temperature_summary.get("equity_temperature"))
    rate_level = _level(temperature_summary.get("rate_pressure"))
    inflation_level = _level(temperature_summary.get("inflation_pressure"))
    labor_level = _level(temperature_summary.get("labor_market"))
    fx_level = _level(temperature_summary.get("fx_pressure"))

    observations.append(
        f"Market temperature is {equity_level}; rate pressure is {rate_level}; inflation pressure is {inflation_level}."
    )
    observations.append(
        f"Labor market state is {labor_level}; FX pressure is {fx_level}."
    )

    regime = temperature_summary.get("overall_regime")
    risk_level = temperature_summary.get("risk_level")
    if regime or risk_level:
        observations.append(
            f"Overall rule-based regime is {regime}; rule-based risk level is {risk_level}."
        )

    if data_limitations:
        observations.append(
            "Some data inputs are unavailable or incomplete; see Data Limitations."
        )

    return observations


def _extract_data_sources(market_snapshot: dict, market_temperature: dict) -> list[dict]:
    sources = []

    for section in ("market_data", "macro_data", "fx_data"):
        items = market_snapshot.get(section, {})
        if not isinstance(items, dict):
            continue
        for key, item in items.items():
            if not isinstance(item, dict):
                continue

            attempted_sources = [
                attempt
                for attempt in item.get("attempted_sources", [])
                if isinstance(attempt, dict)
            ]
            if item.get("source") == "market_data_service" and attempted_sources:
                pass
            elif item.get("source") == "market_data_service":
                sources.append(
                    _source_record(
                        key,
                        item,
                        source_override="internal_or_unknown",
                    )
                )
            else:
                sources.append(_source_record(key, item))

            for attempt in attempted_sources:
                if isinstance(attempt, dict):
                    if item.get("source") != "market_data_service" and _same_source_identity(
                        item,
                        attempt,
                    ):
                        continue
                    sources.append(_source_record(key, attempt))

    input_status = market_temperature.get("input_series_status", {})
    if isinstance(input_status, dict):
        for key, item in input_status.items():
            if isinstance(item, dict):
                sources.append(
                    {
                        "key": key,
                        "source": item.get("source"),
                        "series_id": item.get("series_id"),
                        "symbol": item.get("symbol"),
                        "observation_date": item.get("latest_observation_date"),
                        "status": item.get("status"),
                    }
                )

    return _dedupe_sources(sources)


def _source_record(
    key: str,
    item: dict,
    source_override: str | None = None,
) -> dict:
    return {
        "key": key,
        "source": source_override or item.get("source"),
        "series_id": item.get("series_id"),
        "symbol": item.get("symbol"),
        "function": item.get("function"),
        "observation_date": item.get("observation_date"),
        "status": item.get("status"),
    }


def _display_source_for_market_item(item: dict) -> str | None:
    source = item.get("source")
    attempted_sources = [
        attempt
        for attempt in item.get("attempted_sources", [])
        if isinstance(attempt, dict)
    ]
    if source != "market_data_service" or not attempted_sources:
        return source

    source_names = []
    for attempt in attempted_sources:
        attempted_source = attempt.get("source")
        if not attempted_source or attempted_source == "market_data_service":
            continue
        if attempted_source not in source_names:
            source_names.append(attempted_source)

    return "/".join(source_names) if source_names else source


def _manual_missing(item: dict) -> bool:
    attempts = item.get("attempted_sources", [])
    if not isinstance(attempts, list):
        return False
    for attempt in attempts:
        if not isinstance(attempt, dict):
            continue
        if attempt.get("source") == "manual" and attempt.get("status") == "missing":
            return True
    return False


def _gold_unavailable_mentions_manual_missing(limitations: list[str]) -> bool:
    for limitation in limitations:
        normalized = limitation.lower()
        if (
            "optional gold unavailable" in normalized
            and "manual market data file not found" in normalized
        ):
            return True
    return False


def _same_source_identity(left: dict, right: dict) -> bool:
    return (
        left.get("source") == right.get("source")
        and left.get("series_id") == right.get("series_id")
        and left.get("symbol") == right.get("symbol")
        and left.get("function") == right.get("function")
    )


def _copy_keys(source: dict, keys: tuple[str, ...]) -> dict:
    if not isinstance(source, dict):
        return {key: None for key in keys}
    return {key: source.get(key) for key in keys}


def _allocation_table(allocation_summary: dict) -> str:
    weights = allocation_summary.get("weights_ex_cash", {})
    targets = allocation_summary.get("target_allocation", {})
    deviations = allocation_summary.get("deviation", {})
    flags = allocation_summary.get("deviation_flags", {})
    asset_classes = list(dict.fromkeys([*targets.keys(), *weights.keys(), *deviations.keys()]))

    rows = []
    for asset_class in asset_classes:
        rows.append(
            [
                asset_class,
                _format_percent(weights.get(asset_class)),
                _format_percent(targets.get(asset_class)),
                _format_percent(deviations.get(asset_class), signed=True),
                _display(flags.get(asset_class)),
            ]
        )

    return _markdown_table(
        ["Asset class", "Current ex-cash", "Target", "Deviation", "Flag"],
        rows,
    )


def _holdings_table(holdings: list[dict]) -> str:
    if not isinstance(holdings, list) or not holdings:
        return "No holdings detail recorded."

    rows = []
    for holding in holdings:
        if not isinstance(holding, dict):
            continue
        rows.append(
            [
                _display(holding.get("asset_name")),
                _display(holding.get("fund_code")),
                _display(holding.get("asset_class")),
                _format_number(holding.get("current_value")),
                _format_number(holding.get("profit_loss")),
                _display(holding.get("updated_at")),
            ]
        )

    return _markdown_table(
        ["Asset name", "Fund code", "Asset class", "Current value", "Profit/loss", "Updated at"],
        rows,
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
                _display(item.get("name")),
                _display(item.get("asset_class")),
                _format_number(item.get("daily_amount")),
                _display(item.get("status")),
            ]
        )

    return "\n".join(
        [
            "DCA daily plan details:",
            "",
            _markdown_table(
                ["Key", "Name", "Asset class", "Daily amount", "Status"],
                rows,
            ),
        ]
    )


def _market_table(market_summary: dict) -> str:
    rows = []
    for key, item in market_summary.items():
        rows.append(
            [
                key,
                _display(item.get("name")),
                _format_number(item.get("value")),
                _display(item.get("observation_date")),
                _display(item.get("source")),
                _display(item.get("data_quality", {}).get("source_tier")),
                _display(item.get("data_quality", {}).get("freshness_status")),
                _display(item.get("status")),
                _display(item.get("error")),
            ]
        )

    return _markdown_table(
        [
            "Key",
            "Name",
            "Value",
            "Observation date",
            "Source",
            "Source tier",
            "Freshness",
            "Status",
            "Error",
        ],
        rows,
    )


def _temperature_table(temperature_summary: dict) -> str:
    rows = [
        ["equity_temperature", _level(temperature_summary.get("equity_temperature"))],
        ["rate_pressure", _level(temperature_summary.get("rate_pressure"))],
        ["inflation_pressure", _level(temperature_summary.get("inflation_pressure"))],
        ["labor_market", _level(temperature_summary.get("labor_market"))],
        ["fx_pressure", _level(temperature_summary.get("fx_pressure"))],
        ["overall_regime", _display(temperature_summary.get("overall_regime"))],
        ["risk_level", _display(temperature_summary.get("risk_level"))],
    ]
    return _markdown_table(["Metric", "Level"], rows)


def _data_sources_table(data_sources: list[dict]) -> str:
    if not data_sources:
        return "No data sources recorded."

    rows = [
        [
            _display(item.get("key")),
            _display(item.get("source")),
            _display(item.get("series_id")),
            _display(item.get("symbol")),
            _display(item.get("function")),
            _display(item.get("observation_date")),
            _display(item.get("status")),
        ]
        for item in data_sources
    ]
    return _markdown_table(
        ["Key", "Source", "Series ID", "Symbol", "Function", "Observation date", "Status"],
        rows,
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
    return "\n".join(f"- {item}" for item in items)


def _escape_cell(value: Any) -> str:
    text = _display(value)
    text = text.replace("\r", " ").replace("\n", " ")
    text = text.replace("|", "\\|")
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    if len(text) > 180:
        text = text[:177].rstrip() + "..."
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
        percentage = float(value) * 100
    except (TypeError, ValueError):
        return str(value)
    sign = "+" if signed and percentage > 0 else ""
    return f"{sign}{percentage:.2f}%"


def _format_percent_abs(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{abs(float(value)) * 100:.2f} percentage points"
    except (TypeError, ValueError):
        return str(value)


def _level(value: Any) -> str:
    if isinstance(value, dict):
        return _display(value.get("level"))
    return _display(value)


def _display(value: Any) -> str:
    if value is None:
        return "N/A"
    if value == "":
        return "N/A"
    return str(value)


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _dedupe_limitations(values: list[str]) -> list[str]:
    best_by_key: dict[tuple[str, str], str] = {}
    order: list[tuple[str, str]] = []

    for value in values:
        identity = _limitation_identity(value)
        if identity not in best_by_key:
            best_by_key[identity] = value
            order.append(identity)
            continue

        current = best_by_key[identity]
        if _limitation_specificity(value) > _limitation_specificity(current):
            best_by_key[identity] = value

    return [best_by_key[identity] for identity in order]


def _limitation_identity(value: str) -> tuple[str, str]:
    prefix, _, error = value.partition(":")
    key_token = _limitation_key_token(prefix)
    asset_key = key_token.split(".")[-1]
    normalized_error = error.strip().lower() if error else value.strip().lower()
    return asset_key, normalized_error


def _limitation_specificity(value: str) -> int:
    prefix = value.partition(":")[0].strip()
    key_token = _limitation_key_token(prefix)
    if key_token.startswith(("market_data.", "macro_data.", "fx_data.")):
        return 3
    if key_token in {"nasdaq100", "gold"}:
        return 2
    if "." in key_token:
        return 2
    return 1


def _limitation_key_token(prefix: str) -> str:
    tokens = prefix.strip().split()
    for token in tokens:
        if "." in token:
            return token
    for token in tokens:
        normalized = token.strip().lower()
        if normalized in {"nasdaq100", "gold"}:
            return normalized
    return tokens[0] if tokens else "unknown"


def _dedupe_sources(sources: list[dict]) -> list[dict]:
    result = []
    seen = set()
    for source in sources:
        if not source.get("source"):
            continue
        key = (
            source.get("key"),
            source.get("source"),
            source.get("series_id"),
            source.get("symbol"),
            source.get("function"),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(source)
    return result


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

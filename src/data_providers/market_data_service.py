from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import alpha_vantage_provider, fed_provider, fred_provider, yfinance_provider


MARKET_DATA_KEYS = ("sp500", "nasdaq", "nasdaq100", "gold")
MACRO_DATA_KEYS = ("dgs10", "fedfunds", "cpi", "pce", "nonfarm")
FX_DATA_KEYS = ("usd_cny",)
FINANCIAL_CONDITION_KEYS = (
    "high_yield_spread",
    "vix",
    "real_yield_10y",
    "breakeven_inflation_10y",
    "yield_curve_10y2y",
    "valuation_proxy",
    "fedwatch_probability",
)
TREASURY_NOMINAL_YIELD_KEYS = (
    "nominal_yield_2y",
    "nominal_yield_10y",
    "nominal_yield_30y",
)
INFLATION_INDICATOR_KEYS = (
    "headline_cpi",
    "core_cpi",
    "headline_pce",
    "core_pce",
    "ppi_all_commodities",
    "ppi_final_demand",
)
REQUIRED_CORE_KEYS = (
    "sp500",
    "nasdaq",
    "dgs10",
    "fedfunds",
    "cpi",
    "pce",
    "nonfarm",
    "usd_cny",
)
IMPORTANT_OPTIONAL_KEYS = ("nasdaq100",)
OPTIONAL_MARKET_KEYS = ("gold",)
FRED_PRIMARY_KEYS = REQUIRED_CORE_KEYS


def load_data_source_config(path: str) -> dict:
    config_path = _resolve_path(path)
    raw_text = config_path.read_text(encoding="utf-8")

    try:
        import yaml
    except ImportError:
        config = _load_simple_yaml(raw_text)
    else:
        config = yaml.safe_load(raw_text)

    if not isinstance(config, dict):
        raise ValueError(f"Data source config must contain a mapping: {config_path}")

    return config


def load_manual_market_data(path: str) -> dict:
    manual_path = _resolve_path(path)
    if not manual_path.exists():
        return {}

    rows_by_key: dict[str, dict] = {}
    try:
        with manual_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                key = str(row.get("key") or "").strip()
                if not key:
                    continue

                raw_value = row.get("value")
                value = _to_float_or_none(raw_value)
                status = "ok"
                error = None
                if value is None:
                    status = "error"
                    error = f"Manual market data value is not numeric: {raw_value}"

                updated_at = str(row.get("updated_at") or "").strip()
                rows_by_key[key] = {
                    "key": key,
                    "name": str(row.get("name") or key).strip(),
                    "value": value,
                    "currency": str(row.get("currency") or "").strip() or None,
                    "source": "manual",
                    "observation_date": str(row.get("observation_date") or "").strip() or None,
                    "updated_at": updated_at or None,
                    "timestamp": updated_at or _utc_now(),
                    "status": status,
                    "error": error,
                    "notes": str(row.get("notes") or "").strip() or None,
                }
    except OSError as exc:
        return {
            "__file__": {
                "key": "__file__",
                "name": str(manual_path),
                "value": None,
                "currency": None,
                "source": "manual",
                "observation_date": None,
                "updated_at": None,
                "timestamp": _utc_now(),
                "status": "error",
                "error": f"Manual market data file could not be read: {exc}",
                "notes": None,
            }
        }

    return rows_by_key


def get_core_market_snapshot(config_path: str = "configs/data_sources.yaml") -> dict:
    generated_at = _utc_now()
    _load_project_dotenv()

    config = load_data_source_config(config_path)
    financial_conditions = {
        key: get_financial_condition_item(key, config)
        for key in FINANCIAL_CONDITION_KEYS
    }

    return {
        "market_data": {
            key: get_market_item(key, config)
            for key in MARKET_DATA_KEYS
        },
        "macro_data": {
            key: get_market_item(key, config)
            for key in MACRO_DATA_KEYS
        },
        "fx_data": {
            key: get_market_item(key, config)
            for key in FX_DATA_KEYS
        },
        "financial_conditions": financial_conditions,
        "market_data_package": get_market_data_package(
            config,
            financial_conditions=financial_conditions,
            generated_at=generated_at,
        ),
        "official_sources": fed_provider.get_fed_public_sources(),
        "generated_at": generated_at,
    }


def get_market_data_package(
    config: dict,
    *,
    financial_conditions: dict[str, dict],
    generated_at: str,
) -> dict:
    package_config = _optional_mapping(config, "deepseek_market_data_package")
    treasury_config = _optional_mapping(package_config, "treasury_yields")
    inflation_config = _optional_mapping(package_config, "inflation_indicators")
    oil_config = _optional_mapping(package_config, "oil_and_energy")
    unavailable_config = _optional_mapping(package_config, "unavailable_or_research_needed")

    treasury_yields = {
        key: _fred_package_item(
            key=key,
            item_config=_optional_mapping(treasury_config, key),
            expected_frequency="daily",
            max_stale_days=7,
            timestamp=generated_at,
        )
        for key in TREASURY_NOMINAL_YIELD_KEYS
    }
    treasury_yields.update(_build_treasury_derived_metrics(treasury_yields, generated_at))

    inflation_indicators = {
        key: _package_item_from_config(
            key=key,
            item_config=_optional_mapping(inflation_config, key),
            expected_frequency="monthly",
            max_stale_days=75,
            timestamp=generated_at,
        )
        for key in INFLATION_INDICATOR_KEYS
    }

    oil_and_energy = {
        key: _fred_package_item(
            key=key,
            item_config=_optional_mapping(oil_config, key),
            expected_frequency="daily",
            max_stale_days=7,
            timestamp=generated_at,
        )
        for key in ("wti_oil", "brent_oil")
    }
    oil_and_energy["wti_oil_30d_change"] = _oil_30d_change_item(
        key="wti_oil_30d_change",
        source_item=oil_and_energy["wti_oil"],
        timestamp=generated_at,
    )
    oil_and_energy["brent_oil_30d_change"] = _oil_30d_change_item(
        key="brent_oil_30d_change",
        source_item=oil_and_energy["brent_oil"],
        timestamp=generated_at,
    )

    existing_financial_conditions = {
        key: financial_conditions[key]
        for key in (
            "high_yield_spread",
            "vix",
            "real_yield_10y",
            "breakeven_inflation_10y",
            "yield_curve_10y2y",
        )
        if isinstance(financial_conditions.get(key), dict)
    }
    unavailable = {
        key: _package_unavailable_item(key, item_config, generated_at)
        for key, item_config in unavailable_config.items()
        if isinstance(item_config, dict)
    }

    return {
        "generated_at": generated_at,
        "data_cutoff": _package_data_cutoff(
            treasury_yields,
            inflation_indicators,
            oil_and_energy,
            existing_financial_conditions,
        ),
        "treasury_yields": treasury_yields,
        "inflation_indicators": inflation_indicators,
        "oil_and_energy": oil_and_energy,
        "existing_financial_conditions": existing_financial_conditions,
        "unavailable_or_research_needed": unavailable,
        "market_analysis_framework": _market_analysis_framework(),
        "market_regime_classification_rules": _market_regime_classification_rules(),
        "data_limitations": [
            "no intraday Treasury highs",
            "no FedWatch probability",
            "no forward PE / FactSet valuation",
            "no consensus CPI/PPI surprise data",
            "no PPI final demand confirmed series",
            "no market breadth / concentration data",
        ],
        "interpretation_boundaries": [
            "FRED DGS10/DGS30 are daily observations, not intraday highs.",
            "CPI/PCE/PPI are low-frequency inflation data; do not overread one release.",
            "Oil price changes can signal energy pressure but do not alone determine inflation.",
            "Treasury yields near 5% are rate-pressure signals, not standalone trading signals.",
            "Missing FedWatch means no rate-cut probability can be quantified.",
            "Missing valuation data means no exact PE or forward PE claim.",
            "Market judgement must proceed from credit/liquidity -> rates -> inflation/oil -> valuation/earnings -> breadth -> portfolio observation.",
        ],
    }


def get_financial_condition_item(key: str, config: dict) -> dict:
    generated_at = _utc_now()
    financial_config = _financial_condition_config(key, config)
    if not financial_config:
        return _financial_condition_not_configured(
            key=key,
            name=key,
            timestamp=generated_at,
            error=f"financial_conditions.{key} not configured",
        )

    provider = str(financial_config.get("provider") or "").strip().lower()
    name = str(financial_config.get("name") or key)

    if provider == "fred":
        series_id = str(financial_config.get("series_id") or "").strip()
        if not series_id:
            return _financial_condition_not_configured(
                key=key,
                name=name,
                timestamp=generated_at,
                error=f"financial_conditions.{key}.series_id not configured",
                financial_config=financial_config,
            )
        return _fred_financial_condition_item(
            key=key,
            series_id=series_id,
            timestamp=generated_at,
            financial_config=financial_config,
        )

    if provider in {"not_available", "not_configured", "missing_data"}:
        return _financial_condition_not_available(
            key=key,
            name=name,
            timestamp=generated_at,
            financial_config=financial_config,
        )

    return _financial_condition_error(
        key=key,
        name=name,
        timestamp=generated_at,
        error=f"Unsupported financial condition provider: {provider or 'missing'}",
        financial_config=financial_config,
    )


def get_market_item(key: str, config: dict) -> dict:
    generated_at = _utc_now()
    attempts: list[dict] = []
    candidates = _provider_candidates(key, config)

    if not candidates:
        return _market_error(
            key=key,
            name=key,
            attempts=[
                {
                    "source": "config",
                    "status": "error",
                    "error": f"No provider candidates configured for {key}",
                    "timestamp": generated_at,
                }
            ],
            timestamp=generated_at,
        )

    result_name = _first_candidate_name(candidates, key)
    asset_type = _first_candidate_asset_type(candidates)

    for candidate in candidates:
        result = _call_provider(candidate)
        attempts.append(_attempt_summary(candidate, result))

        value = _to_float_or_none(result.get("value"))
        if result.get("status") == "ok" and value is not None:
            item = {
                "key": key,
                "name": candidate.get("name") or result_name,
                "asset_type": candidate.get("asset_type") or asset_type,
                "value": value,
                "source": result.get("source") or candidate["provider"],
                "timestamp": result.get("timestamp") or generated_at,
                "status": "ok",
                "error": None,
                "attempted_sources": attempts,
            }
            if result.get("series_id") or candidate.get("series_id"):
                item["series_id"] = result.get("series_id") or candidate.get("series_id")
            if result.get("symbol") or candidate.get("symbol"):
                item["symbol"] = result.get("symbol") or candidate.get("symbol")
            if result.get("observation_date"):
                item["observation_date"] = result["observation_date"]
            if result.get("currency"):
                item["currency"] = result["currency"]
            if result.get("function") or candidate.get("function"):
                item["function"] = result.get("function") or candidate.get("function")
            if result.get("source_tier") or candidate.get("source_tier"):
                item["source_tier"] = result.get("source_tier") or candidate.get("source_tier")
            if result.get("updated_at"):
                item["updated_at"] = result["updated_at"]
            if result.get("path"):
                item["path"] = result["path"]
            if candidate.get("notes"):
                item["notes"] = candidate["notes"]
            if result.get("notes"):
                item["notes"] = result["notes"]
            return item

    return _market_error(
        key=key,
        name=result_name,
        attempts=attempts,
        timestamp=generated_at,
        asset_type=asset_type,
    )


def _fred_financial_condition_item(
    *,
    key: str,
    series_id: str,
    timestamp: str,
    financial_config: dict,
) -> dict:
    result = fred_provider.get_fred_latest(series_id)
    attempt = {
        "source": result.get("source") or "FRED",
        "status": result.get("status", "error"),
        "error": result.get("error"),
        "timestamp": result.get("timestamp") or timestamp,
        "series_id": result.get("series_id") or series_id,
        "observation_date": result.get("observation_date"),
        "source_tier": financial_config.get("source_tier"),
    }

    value = _to_float_or_none(result.get("value"))
    if result.get("status") != "ok" or value is None:
        return _financial_condition_error(
            key=key,
            name=str(financial_config.get("name") or key),
            timestamp=result.get("timestamp") or timestamp,
            error=str(result.get("error") or "FRED financial condition request failed"),
            financial_config=financial_config,
            series_id=series_id,
            source=result.get("source") or "FRED",
            observation_date=result.get("observation_date"),
            attempted_sources=[attempt],
        )

    return {
        "key": key,
        "name": financial_config.get("name") or key,
        "value": value,
        "unit": financial_config.get("unit"),
        "observation_date": result.get("observation_date"),
        "source": result.get("source") or "FRED",
        "source_tier": financial_config.get("source_tier"),
        "freshness": "unknown",
        "status": "ok",
        "error": None,
        "interpretation_hint": financial_config.get("interpretation_hint"),
        "risk_relevance": financial_config.get("risk_relevance"),
        "asset_type": financial_config.get("asset_type"),
        "series_id": result.get("series_id") or series_id,
        "timestamp": result.get("timestamp") or timestamp,
        "attempted_sources": [attempt],
    }


def _package_item_from_config(
    *,
    key: str,
    item_config: dict,
    expected_frequency: str,
    max_stale_days: int,
    timestamp: str,
) -> dict:
    provider = str(item_config.get("provider") or "").strip().lower()
    if provider == "fred":
        return _fred_package_item(
            key=key,
            item_config=item_config,
            expected_frequency=expected_frequency,
            max_stale_days=max_stale_days,
            timestamp=timestamp,
        )
    if provider in {"not_available", "research_needed"}:
        return _package_unavailable_item(key, item_config, timestamp)
    return _package_item(
        key=key,
        name=str(item_config.get("name") or key),
        value=None,
        unit=item_config.get("unit"),
        observation_date=None,
        source="not_configured",
        source_tier=item_config.get("source_tier") or "not_available",
        freshness="not_available",
        status="not_configured",
        error=f"Unsupported provider for {key}: {provider or 'missing'}",
        interpretation_hint=item_config.get("interpretation_hint"),
        risk_relevance=item_config.get("risk_relevance"),
        timestamp=timestamp,
    )


def _fred_package_item(
    *,
    key: str,
    item_config: dict,
    expected_frequency: str,
    max_stale_days: int,
    timestamp: str,
) -> dict:
    series_id = str(item_config.get("series_id") or "").strip()
    name = str(item_config.get("name") or key)
    source = f"FRED:{series_id}" if series_id else "not_configured"
    if not series_id:
        return _package_item(
            key=key,
            name=name,
            value=None,
            unit=item_config.get("unit"),
            observation_date=None,
            source=source,
            source_tier=item_config.get("source_tier") or "not_available",
            freshness="not_available",
            status="not_configured",
            error=f"{key}.series_id not configured",
            interpretation_hint=item_config.get("interpretation_hint"),
            risk_relevance=item_config.get("risk_relevance"),
            timestamp=timestamp,
        )

    result = fred_provider.get_fred_latest(series_id)
    value = _to_float_or_none(result.get("value"))
    if result.get("status") != "ok" or value is None:
        return _package_item(
            key=key,
            name=name,
            value=None,
            unit=item_config.get("unit"),
            observation_date=result.get("observation_date"),
            source=source,
            source_tier=item_config.get("source_tier") or "official_or_public_data_api",
            freshness="unknown",
            status="error",
            error=str(result.get("error") or "FRED request failed"),
            interpretation_hint=item_config.get("interpretation_hint"),
            risk_relevance=item_config.get("risk_relevance"),
            timestamp=result.get("timestamp") or timestamp,
            series_id=series_id,
            attempted_sources=[_package_attempt(result, series_id, item_config)],
        )

    observation_date = result.get("observation_date")
    return _package_item(
        key=key,
        name=name,
        value=value,
        unit=item_config.get("unit"),
        observation_date=observation_date,
        source=source,
        source_tier=item_config.get("source_tier") or "official_or_public_data_api",
        freshness=_package_freshness(
            observation_date,
            expected_frequency=expected_frequency,
            max_stale_days=max_stale_days,
        ),
        status="ok",
        error=None,
        interpretation_hint=item_config.get("interpretation_hint"),
        risk_relevance=item_config.get("risk_relevance"),
        timestamp=result.get("timestamp") or timestamp,
        series_id=series_id,
        attempted_sources=[_package_attempt(result, series_id, item_config)],
    )


def _build_treasury_derived_metrics(treasury_yields: dict[str, dict], timestamp: str) -> dict[str, dict]:
    result = {}
    for prefix, source_key in (
        ("dgs10", "nominal_yield_10y"),
        ("dgs30", "nominal_yield_30y"),
    ):
        source_item = treasury_yields.get(source_key, {})
        series_id = str(source_item.get("series_id") or "").strip()
        history = _fred_history(series_id, limit=140) if series_id else []
        for window_days in (30, 60):
            result[f"{prefix}_{window_days}d_high"] = _recent_high_item(
                key=f"{prefix}_{window_days}d_high",
                source_item=source_item,
                history=history,
                window_days=window_days,
                timestamp=timestamp,
            )
        result[f"{prefix}_distance_to_5pct"] = _distance_to_5pct_item(
            key=f"{prefix}_distance_to_5pct",
            source_item=source_item,
            timestamp=timestamp,
        )
        result[f"{prefix}_above_5pct"] = _above_5pct_item(
            key=f"{prefix}_above_5pct",
            source_item=source_item,
            timestamp=timestamp,
        )
    return result


def _recent_high_item(
    *,
    key: str,
    source_item: dict,
    history: list[dict],
    window_days: int,
    timestamp: str,
) -> dict:
    latest_date = _parse_date(source_item.get("observation_date"))
    if source_item.get("status") != "ok":
        return _source_error_derived_item(
            key,
            source_item,
            "Cannot calculate recent high because source data is unavailable.",
            timestamp,
            window_days=window_days,
            calculation=f"max daily FRED observation over the latest {window_days} calendar days",
        )
    if latest_date is None:
        return _derived_package_error(
            key,
            source_item,
            "Latest source observation unavailable for recent high calculation.",
            timestamp,
            window_days=window_days,
            calculation=f"max daily FRED observation over the latest {window_days} calendar days",
            status="error",
            freshness="unknown",
            interpretation_hint="Cannot calculate recent high because the latest source observation date is unavailable.",
        )

    start_date = latest_date - timedelta(days=window_days)
    window = [
        item
        for item in history
        if isinstance(item.get("date"), date) and start_date <= item["date"] <= latest_date
    ]
    if not window:
        return _derived_package_error(
            key,
            source_item,
            f"No valid observations in {window_days} day window.",
            timestamp,
            window_days=window_days,
            calculation=f"max daily FRED observation over the latest {window_days} calendar days",
        )

    high = max(window, key=lambda item: item["value"])
    high_date = high["date"].isoformat()
    return _package_item(
        key=key,
        name=f"{source_item.get('name') or source_item.get('series_id')} {window_days}D High",
        value=float(high["value"]),
        unit=source_item.get("unit"),
        observation_date=high_date,
        source=source_item.get("source"),
        source_tier=source_item.get("source_tier"),
        freshness=source_item.get("freshness"),
        status="ok",
        error=None,
        interpretation_hint="FRED daily constant maturity yield; not intraday high.",
        risk_relevance="Recent daily high helps frame whether long rates are pressing toward key thresholds.",
        timestamp=timestamp,
        series_id=source_item.get("series_id"),
        source_series=source_item.get("source"),
        derived_from=source_item.get("source"),
        window_days=window_days,
        high_date=high_date,
        intraday_high_available=False,
        calculation=f"max daily FRED observation over the latest {window_days} calendar days",
    )


def _distance_to_5pct_item(*, key: str, source_item: dict, timestamp: str) -> dict:
    value = _to_float_or_none(source_item.get("value"))
    if source_item.get("status") != "ok":
        return _source_error_derived_item(
            key,
            source_item,
            "Cannot calculate distance to 5% because source data is unavailable.",
            timestamp,
            calculation="latest_value - 5.0 percentage points",
        )
    if value is None:
        return _derived_package_error(
            key,
            source_item,
            "Latest source observation unavailable for 5 percent distance calculation.",
            timestamp,
            calculation="latest_value - 5.0 percentage points",
            status="error",
            freshness="unknown",
            interpretation_hint="Cannot calculate distance to 5% because the latest source value is unavailable.",
        )
    return _package_item(
        key=key,
        name=f"{source_item.get('name') or source_item.get('series_id')} Distance to 5%",
        value=round(value - 5.0, 4),
        unit="percentage_points",
        observation_date=source_item.get("observation_date"),
        source=source_item.get("source"),
        source_tier=source_item.get("source_tier"),
        freshness=source_item.get("freshness"),
        status="ok",
        error=None,
        interpretation_hint="Positive value means the latest daily FRED observation is above 5%; negative means below 5%.",
        risk_relevance="Frames long-rate pressure near the 5% threshold without using intraday highs.",
        timestamp=timestamp,
        series_id=source_item.get("series_id"),
        source_series=source_item.get("source"),
        derived_from=source_item.get("source"),
        intraday_high_available=False,
        calculation="latest_value - 5.0 percentage points",
    )


def _above_5pct_item(*, key: str, source_item: dict, timestamp: str) -> dict:
    value = _to_float_or_none(source_item.get("value"))
    if source_item.get("status") != "ok":
        return _source_error_derived_item(
            key,
            source_item,
            "Cannot calculate above-5% flag because source data is unavailable.",
            timestamp,
            calculation="latest_value >= 5.0",
        )
    if value is None:
        return _derived_package_error(
            key,
            source_item,
            "Latest source observation unavailable for above 5 percent calculation.",
            timestamp,
            calculation="latest_value >= 5.0",
            status="error",
            freshness="unknown",
            interpretation_hint="Cannot calculate above-5% flag because the latest source value is unavailable.",
        )
    return _package_item(
        key=key,
        name=f"{source_item.get('name') or source_item.get('series_id')} Above 5%",
        value=bool(value >= 5.0),
        unit="boolean",
        observation_date=source_item.get("observation_date"),
        source=source_item.get("source"),
        source_tier=source_item.get("source_tier"),
        freshness=source_item.get("freshness"),
        status="ok",
        error=None,
        interpretation_hint="True only if the latest daily FRED observation is at or above 5%.",
        risk_relevance="Flags rate-pressure threshold using daily observations only.",
        timestamp=timestamp,
        series_id=source_item.get("series_id"),
        source_series=source_item.get("source"),
        derived_from=source_item.get("source"),
        intraday_high_available=False,
        calculation="latest_value >= 5.0",
    )


def _oil_30d_change_item(*, key: str, source_item: dict, timestamp: str) -> dict:
    latest_value = _to_float_or_none(source_item.get("value"))
    latest_date = _parse_date(source_item.get("observation_date"))
    series_id = str(source_item.get("series_id") or "").strip()
    if source_item.get("status") != "ok":
        return _source_error_derived_item(
            key,
            source_item,
            "Cannot calculate 30 day oil change because source data is unavailable.",
            timestamp,
            window_days=30,
            calculation="(latest_value - value_30d_ago_or_nearest_available) / old_value * 100",
        )
    if latest_value is None or latest_date is None or not series_id:
        return _derived_package_error(
            key,
            source_item,
            "Latest oil observation unavailable for 30 day change calculation.",
            timestamp,
            window_days=30,
            calculation="(latest_value - value_30d_ago_or_nearest_available) / old_value * 100",
            status="error",
            freshness="unknown",
            interpretation_hint="Cannot calculate 30 day oil change because the latest source observation is unavailable.",
        )

    old = _nearest_observation(
        _fred_history(series_id, limit=90),
        latest_date - timedelta(days=30),
        exclude_date=latest_date,
    )
    old_value = _to_float_or_none(old.get("value")) if isinstance(old, dict) else None
    if old_value is None or old_value == 0:
        return _derived_package_error(
            key,
            source_item,
            "No valid historical oil observation near 30 days ago.",
            timestamp,
            window_days=30,
            calculation="(latest_value - value_30d_ago_or_nearest_available) / old_value * 100",
        )

    change_abs = latest_value - old_value
    change_pct = change_abs / old_value * 100
    return _package_item(
        key=key,
        name=f"{source_item.get('name') or series_id} 30D Change",
        value=round(change_pct, 4),
        unit="percent",
        observation_date=source_item.get("observation_date"),
        source=source_item.get("source"),
        source_tier=source_item.get("source_tier"),
        freshness=source_item.get("freshness"),
        status="ok",
        error=None,
        interpretation_hint="30 day change uses nearest available daily FRED observation, not intraday price.",
        risk_relevance="Oil momentum can indicate energy pressure but does not alone determine inflation.",
        timestamp=timestamp,
        series_id=series_id,
        source_series=source_item.get("source"),
        derived_from=source_item.get("source"),
        window_days=30,
        calculation="(latest_value - value_30d_ago_or_nearest_available) / old_value * 100",
        change_abs=round(change_abs, 4),
        change_pct=round(change_pct, 4),
        old_value=old_value,
        old_observation_date=old["date"].isoformat() if isinstance(old.get("date"), date) else None,
    )


def _package_unavailable_item(key: str, item_config: dict, timestamp: str) -> dict:
    status = str(item_config.get("status") or item_config.get("provider") or "not_available")
    if status not in {"not_available", "research_needed"}:
        status = "not_available"
    return _package_item(
        key=key,
        name=str(item_config.get("name") or key),
        value=None,
        unit=item_config.get("unit"),
        observation_date=None,
        source=status,
        source_tier=item_config.get("source_tier") or status,
        freshness=status,
        status=status,
        error=item_config.get("unavailable_reason") or f"{key} is {status}.",
        interpretation_hint=item_config.get("interpretation_hint"),
        risk_relevance=item_config.get("risk_relevance"),
        timestamp=timestamp,
    )


def _derived_package_error(
    key: str,
    source_item: dict,
    error: str,
    timestamp: str,
    *,
    window_days: int | None = None,
    calculation: str | None = None,
    status: str = "insufficient_history",
    freshness: str = "insufficient_history",
    interpretation_hint: str | None = None,
) -> dict:
    return _package_item(
        key=key,
        name=key,
        value=None,
        unit=None,
        observation_date=source_item.get("observation_date"),
        source=source_item.get("source"),
        source_tier=source_item.get("source_tier"),
        freshness=freshness,
        status=status,
        error=error,
        interpretation_hint=interpretation_hint,
        risk_relevance=None,
        timestamp=timestamp,
        series_id=source_item.get("series_id"),
        source_series=source_item.get("source"),
        derived_from=source_item.get("source"),
        window_days=window_days,
        calculation=calculation,
    )


def _source_error_derived_item(
    key: str,
    source_item: dict,
    interpretation_hint: str,
    timestamp: str,
    *,
    window_days: int | None = None,
    calculation: str | None = None,
) -> dict:
    source_error = str(source_item.get("error") or "Source data unavailable.")
    return _package_item(
        key=key,
        name=key,
        value=None,
        unit=None,
        observation_date=source_item.get("observation_date"),
        source=source_item.get("source"),
        source_tier=source_item.get("source_tier"),
        freshness=source_item.get("freshness") or "unknown",
        status="error",
        error=source_error,
        interpretation_hint=interpretation_hint,
        risk_relevance=None,
        timestamp=timestamp,
        series_id=source_item.get("series_id"),
        source_series=source_item.get("source"),
        derived_from=source_item.get("source"),
        window_days=window_days,
        calculation=calculation,
    )


def _package_item(
    *,
    key: str,
    name: str,
    value: Any,
    unit: Any,
    observation_date: str | None,
    source: str | None,
    source_tier: str | None,
    freshness: str | None,
    status: str,
    error: str | None,
    interpretation_hint: str | None,
    risk_relevance: str | None,
    timestamp: str,
    series_id: str | None = None,
    attempted_sources: list[dict] | None = None,
    **extra: Any,
) -> dict:
    item = {
        "key": key,
        "name": name,
        "value": value,
        "unit": unit,
        "observation_date": observation_date,
        "source": source,
        "source_tier": source_tier,
        "freshness": freshness,
        "status": status,
        "error": error,
        "interpretation_hint": interpretation_hint,
        "risk_relevance": risk_relevance,
        "timestamp": timestamp,
        "attempted_sources": attempted_sources or [],
    }
    if series_id:
        item["series_id"] = series_id
    item.update({extra_key: extra_value for extra_key, extra_value in extra.items() if extra_value is not None})
    return item


def _package_attempt(result: dict, series_id: str, item_config: dict) -> dict:
    return {
        "source": result.get("source") or "FRED",
        "status": result.get("status", "error"),
        "error": result.get("error"),
        "timestamp": result.get("timestamp"),
        "series_id": result.get("series_id") or series_id,
        "observation_date": result.get("observation_date"),
        "source_tier": item_config.get("source_tier"),
    }


def _fred_history(series_id: str, limit: int) -> list[dict]:
    result = fred_provider.get_fred_series(series_id, limit=limit)
    if result.get("status") != "ok":
        return []
    observations = []
    for item in result.get("data", []):
        observed_at = _parse_date(item.get("date"))
        value = _to_float_or_none(item.get("value"))
        if observed_at is not None and value is not None:
            observations.append({"date": observed_at, "value": value})
    return observations


def _nearest_observation(
    observations: list[dict],
    target_date: date,
    *,
    exclude_date: date,
) -> dict | None:
    candidates = [
        item
        for item in observations
        if isinstance(item.get("date"), date) and item["date"] != exclude_date
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda item: abs((item["date"] - target_date).days))


def _package_data_cutoff(*groups: dict[str, Any]) -> str | None:
    dates = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        for item in group.values():
            if not isinstance(item, dict) or item.get("status") != "ok":
                continue
            observed_at = _parse_date(item.get("observation_date"))
            if observed_at:
                dates.append(observed_at)
    return max(dates).isoformat() if dates else None


def _package_freshness(
    observation_date: Any,
    *,
    expected_frequency: str,
    max_stale_days: int,
) -> str:
    observed_at = _parse_date(observation_date)
    if observed_at is None:
        return "unknown"
    today = datetime.now(timezone.utc).date()
    if expected_frequency == "monthly":
        month_gap = (today.year - observed_at.year) * 12 + today.month - observed_at.month
        if month_gap <= 2:
            return "normal_lag"
        if month_gap == 3:
            return "extended_lag"
        return "stale"
    return "fresh" if (today - observed_at).days <= max_stale_days else "stale"


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _market_analysis_framework() -> dict[str, dict[str, Any]]:
    return {
        "step_1_credit_and_financial_stress": {
            "purpose": "First judge whether there is evidence of systemic crisis.",
            "inputs": ["high_yield_spread", "investment_grade_spread if available", "financial_stress_index if available", "vix"],
            "rule": "When credit spreads and financial stress are normal, do not classify an equity pullback as systemic crisis only because prices fell.",
        },
        "step_2_nominal_and_real_rates": {
            "purpose": "Judge whether valuation pressure comes from nominal yields, real yields, or curve structure.",
            "inputs": ["DGS2", "DGS10", "DGS30", "DFII10", "T10Y2Y", "DGS10/DGS30 recent highs"],
            "rule": "10Y/30Y near or above 5% is a rate-pressure signal, not a standalone trading signal.",
        },
        "step_3_inflation_and_oil": {
            "purpose": "Judge whether inflation and energy pressure constrain easing.",
            "inputs": ["CPI", "core CPI", "PCE", "core PCE", "PPIACO", "WTI", "Brent", "T10YIE"],
            "rule": "Rising oil can add inflation pressure, but it must not be mechanically equated with runaway inflation.",
        },
        "step_4_valuation_and_earnings_boundary": {
            "purpose": "Judge whether valuation and earnings can be discussed as facts.",
            "inputs": ["valuation_proxy", "forward_pe", "cape", "earnings_revision"],
            "rule": "If valuation and earnings data are not_available, say the package cannot confirm valuation level; do not invent PE or forward PE.",
        },
        "step_5_market_structure_boundary": {
            "purpose": "Judge whether market gains are overly concentrated.",
            "inputs": ["market_breadth", "equal_weight_vs_cap_weight", "mega_cap_concentration"],
            "rule": "If breadth and concentration data are missing, do not assert that AI/mega-cap concentration has worsened; mark it as an observation gap.",
        },
        "step_6_portfolio_observation": {
            "purpose": "Only then translate the macro state into long-term portfolio observation.",
            "allowed_language": ["relative overweight/underweight versus target", "risk exposure rising/falling", "future DCA evaluation", "threshold review", "year-end review", "rebalancing evaluation"],
            "forbidden_language": ["should buy", "should sell", "liquidate", "wait for a dip", "adjust immediately", "specific buy/sell amount"],
        },
    }


def _market_regime_classification_rules() -> dict[str, dict[str, Any]]:
    return {
        "normal_pullback": {
            "evidence": ["equity drawdown or volatility", "credit spreads still normal", "VIX not showing panic", "no systemic deterioration in earnings, jobs, or funding"],
            "boundary": "Do not automatically upgrade normal pullback to crisis.",
        },
        "sideways_valuation_digest": {
            "evidence": ["rates elevated", "earnings not broken", "valuation data missing or high pending confirmation", "indices move sideways or churn"],
            "boundary": "Sideways digestion may be more realistic than a fast V-shaped repair, but do not forecast timing.",
        },
        "rates_inflation_shock": {
            "evidence": ["DGS10/DGS30 rising", "real yield rising", "CPI/PPI/PCE or oil pressure", "equities, bonds, and gold can all face pressure"],
            "boundary": "Inflation shock differs from ordinary safe-haven risk.",
        },
        "trend_reversal": {
            "evidence": ["earnings revisions down", "market breadth deterioration", "rates/dollar/liquidity persistently pressuring assets"],
            "boundary": "If earnings and breadth data are missing, do not confirm trend reversal.",
        },
        "systemic_crisis": {
            "evidence": ["credit spreads widen materially", "financial stress rises", "funding, banks, jobs, and earnings show multi-signal deterioration"],
            "boundary": "Without multi-signal confirmation, do not confirm systemic crisis.",
        },
        "ai_bubble_risk": {
            "evidence": ["real technology trend", "valuation overextension", "earnings delivery insufficient", "capex return uncertain", "concentration rising", "high real yields pressuring duration"],
            "boundary": "If valuation, earnings, and concentration data are missing, discuss mechanism only; do not confirm bubble magnitude.",
        },
    }


def _provider_candidates(key: str, config: dict) -> list[dict]:
    if key in {"sp500", "nasdaq", "dgs10", "fedfunds", "cpi", "pce", "nonfarm"}:
        return [_fred_candidate(key, config)]

    if key == "usd_cny":
        return [
            _fred_candidate(
                key,
                config,
                notes="FRED DEXCHUS reports Chinese yuan per 1 U.S. dollar (CNY per USD).",
            ),
            _yfinance_candidate(
                key,
                config,
                notes="Yahoo CNY=X is treated as USD/CNY, CNY per 1 USD.",
            ),
        ]

    if key == "nasdaq100":
        return [
            _fred_candidate(key, config),
            _yfinance_candidate(key, config),
        ]

    if key == "gold":
        return [
            _alpha_vantage_candidate(key, config, mode="spot"),
            _alpha_vantage_candidate(key, config, mode="history"),
            _manual_candidate(key, config),
            _yfinance_candidate(key, config),
        ]

    return []


def _financial_condition_config(key: str, config: dict) -> dict:
    financial_conditions = _optional_mapping(config, "financial_conditions")
    item = financial_conditions.get(key)
    return item if isinstance(item, dict) else {}


def _financial_condition_base(
    *,
    key: str,
    name: str,
    timestamp: str,
    status: str,
    error: str | None,
    financial_config: dict | None = None,
    series_id: str | None = None,
    source: str | None = None,
    observation_date: str | None = None,
    attempted_sources: list[dict] | None = None,
) -> dict:
    financial_config = financial_config if isinstance(financial_config, dict) else {}
    return {
        "key": key,
        "name": name,
        "value": None,
        "unit": financial_config.get("unit"),
        "observation_date": observation_date,
        "source": source or financial_config.get("source") or "not_configured",
        "source_tier": financial_config.get("source_tier") or "not_available",
        "freshness": "not_available" if status in {"not_available", "not_configured"} else "unknown",
        "status": status,
        "error": error,
        "interpretation_hint": financial_config.get("interpretation_hint"),
        "risk_relevance": financial_config.get("risk_relevance"),
        "asset_type": financial_config.get("asset_type"),
        "series_id": series_id or financial_config.get("series_id"),
        "timestamp": timestamp,
        "attempted_sources": attempted_sources or [],
    }


def _financial_condition_not_available(
    *,
    key: str,
    name: str,
    timestamp: str,
    financial_config: dict,
) -> dict:
    return _financial_condition_base(
        key=key,
        name=name,
        timestamp=timestamp,
        status="not_available",
        error=financial_config.get("unavailable_reason")
        or "Financial condition is not available from configured sources.",
        financial_config=financial_config,
        source="not_available",
    )


def _financial_condition_not_configured(
    *,
    key: str,
    name: str,
    timestamp: str,
    error: str,
    financial_config: dict | None = None,
) -> dict:
    return _financial_condition_base(
        key=key,
        name=name,
        timestamp=timestamp,
        status="not_configured",
        error=error,
        financial_config=financial_config,
        source="not_configured",
    )


def _financial_condition_error(
    *,
    key: str,
    name: str,
    timestamp: str,
    error: str,
    financial_config: dict,
    series_id: str | None = None,
    source: str | None = None,
    observation_date: str | None = None,
    attempted_sources: list[dict] | None = None,
) -> dict:
    return _financial_condition_base(
        key=key,
        name=name,
        timestamp=timestamp,
        status="error",
        error=error,
        financial_config=financial_config,
        series_id=series_id,
        source=source,
        observation_date=observation_date,
        attempted_sources=attempted_sources,
    )


def _fred_candidate(key: str, config: dict, notes: str | None = None) -> dict:
    fred_series = _optional_mapping(config, "fred_series")
    series_config = fred_series.get(key)

    if not isinstance(series_config, dict):
        return {
            "provider": "config",
            "source": "config",
            "name": key,
            "asset_type": None,
            "error": f"fred_series.{key} not configured",
        }

    series_id = series_config.get("series_id")
    if not series_id:
        return {
            "provider": "config",
            "source": "config",
            "name": series_config.get("name") or key,
            "asset_type": series_config.get("asset_type"),
            "error": f"fred_series.{key}.series_id not configured",
        }

    candidate = {
        "provider": "fred",
        "series_id": str(series_id),
        "name": series_config.get("name") or key,
        "asset_type": series_config.get("asset_type"),
    }
    if notes:
        candidate["notes"] = notes
    return candidate


def _fred_candidates_with_fallbacks(
    key: str,
    config: dict,
    notes: str | None = None,
) -> list[dict]:
    primary = _fred_candidate(key, config, notes=notes)
    candidates = [primary]
    if primary.get("provider") != "fred":
        return candidates

    fred_series = _optional_mapping(config, "fred_series")
    series_config = fred_series.get(key, {})
    if not isinstance(series_config, dict):
        return candidates

    fallback_series_ids = series_config.get("fallback_series_ids", [])
    if isinstance(fallback_series_ids, str):
        fallback_series_ids = [fallback_series_ids]

    for fallback_series_id in fallback_series_ids:
        fallback_series_id = str(fallback_series_id).strip()
        if not fallback_series_id:
            continue
        candidates.append(
            {
                "provider": "fred",
                "series_id": fallback_series_id,
                "name": series_config.get("name") or key,
                "asset_type": series_config.get("asset_type"),
            }
        )

    return candidates


def _manual_candidate(key: str, config: dict) -> dict:
    manual_config = _optional_mapping(config, "manual_market_data")
    manual_path = manual_config.get("file") or "data/manual/market_data_manual.csv"
    return {
        "provider": "manual",
        "key": key,
        "path": str(manual_path),
        "name": f"{key} manual market data",
        "asset_type": _asset_type_from_market_symbols(key, config),
    }


def _alpha_vantage_candidate(key: str, config: dict, mode: str) -> dict:
    alpha_vantage_config = _optional_mapping(config, "alpha_vantage")
    gold_config = alpha_vantage_config.get("gold", {})
    if not alpha_vantage_config.get("enabled", False):
        return {
            "provider": "config",
            "source": "config",
            "name": key,
            "asset_type": "commodity",
            "error": "alpha_vantage.enabled is false",
        }
    if not isinstance(gold_config, dict):
        return {
            "provider": "config",
            "source": "config",
            "name": key,
            "asset_type": "commodity",
            "error": "alpha_vantage.gold not configured",
        }

    if mode == "spot":
        function_name = gold_config.get("spot_function") or "GOLD_SILVER_SPOT"
        name = "Gold spot price"
    else:
        function_name = gold_config.get("history_function") or "GOLD_SILVER_HISTORY"
        name = "Gold daily history latest price"

    return {
        "provider": "alpha_vantage",
        "mode": mode,
        "function": str(function_name),
        "symbol": str(gold_config.get("symbol") or "GOLD"),
        "interval": str(gold_config.get("interval") or "daily"),
        "name": name,
        "asset_type": "commodity",
        "source_tier": "third_party_api",
    }


def _yfinance_candidate(
    key: str,
    config: dict,
    notes: str | None = None,
) -> dict:
    market_symbols = _optional_mapping(config, "market_symbols")
    symbol_config = market_symbols.get(key)

    if not isinstance(symbol_config, dict):
        return {
            "provider": "config",
            "source": "config",
            "name": key,
            "asset_type": None,
            "error": f"market_symbols.{key} not configured",
        }

    symbol = symbol_config.get("symbol")
    if not symbol:
        return {
            "provider": "config",
            "source": "config",
            "name": symbol_config.get("name") or key,
            "asset_type": symbol_config.get("asset_type"),
            "error": f"market_symbols.{key}.symbol not configured",
        }

    candidate = {
        "provider": "yfinance",
        "symbol": str(symbol),
        "name": symbol_config.get("name") or key,
        "asset_type": symbol_config.get("asset_type"),
    }
    if notes:
        candidate["notes"] = notes
    return candidate


def _call_provider(candidate: dict) -> dict:
    provider = candidate["provider"]

    if provider == "fred":
        return fred_provider.get_fred_latest(candidate["series_id"])

    if provider == "yfinance":
        return yfinance_provider.get_latest_price(candidate["symbol"])

    if provider == "manual":
        return _get_manual_market_item(candidate["key"], candidate["path"])

    if provider == "alpha_vantage":
        if candidate.get("mode") == "spot":
            return alpha_vantage_provider.get_gold_spot()
        return alpha_vantage_provider.get_gold_history_latest(
            interval=str(candidate.get("interval") or "daily")
        )

    return {
        "value": None,
        "source": candidate.get("source") or provider,
        "timestamp": _utc_now(),
        "status": "error",
        "error": candidate.get("error") or f"Unsupported provider: {provider}",
    }


def _attempt_summary(candidate: dict, result: dict) -> dict:
    summary = {
        "source": result.get("source") or candidate.get("source") or candidate["provider"],
        "status": result.get("status", "error"),
        "error": result.get("error"),
        "timestamp": result.get("timestamp") or _utc_now(),
    }

    if candidate.get("series_id") or result.get("series_id"):
        summary["series_id"] = result.get("series_id") or candidate.get("series_id")
    if candidate.get("symbol") or result.get("symbol"):
        summary["symbol"] = result.get("symbol") or candidate.get("symbol")
    if result.get("observation_date"):
        summary["observation_date"] = result["observation_date"]
    if result.get("currency"):
        summary["currency"] = result["currency"]
    if candidate.get("function") or result.get("function"):
        summary["function"] = result.get("function") or candidate.get("function")
    if result.get("source_tier") or candidate.get("source_tier"):
        summary["source_tier"] = result.get("source_tier") or candidate.get("source_tier")
    if candidate.get("path") or result.get("path"):
        summary["path"] = result.get("path") or candidate.get("path")
    if result.get("updated_at"):
        summary["updated_at"] = result["updated_at"]
    if candidate.get("notes"):
        summary["notes"] = candidate["notes"]
    if result.get("notes"):
        summary["notes"] = result["notes"]

    return summary


def _market_error(
    key: str,
    name: str,
    attempts: list[dict],
    timestamp: str,
    asset_type: str | None = None,
) -> dict:
    errors = [
        f"{_attempt_label(attempt)}: {attempt.get('error')}"
        for attempt in attempts
        if attempt.get("error")
    ]
    error = "; ".join(errors) or "All configured market data sources failed"

    return {
        "key": key,
        "name": name,
        "asset_type": asset_type,
        "value": None,
        "source": "market_data_service",
        "timestamp": timestamp,
        "status": "error",
        "error": error,
        "attempted_sources": attempts,
    }


def _attempt_label(attempt: dict) -> str:
    label = str(attempt.get("source") or "unknown")
    if attempt.get("function"):
        label = f"{label} {attempt['function']}"
    if attempt.get("series_id"):
        return f"{label} {attempt['series_id']}"
    if attempt.get("symbol"):
        return f"{label} {attempt['symbol']}"
    return label


def _get_manual_market_item(key: str, path: str) -> dict:
    timestamp = _utc_now()
    manual_path = _resolve_path(path)
    if not manual_path.exists():
        return {
            "key": key,
            "value": None,
            "currency": None,
            "source": "manual",
            "timestamp": timestamp,
            "observation_date": None,
            "updated_at": None,
            "status": "missing",
            "error": "manual market data file not found",
            "path": str(manual_path),
        }

    manual_data = load_manual_market_data(path)
    file_error = manual_data.get("__file__")
    if isinstance(file_error, dict):
        return {**file_error, "key": key, "path": str(manual_path)}

    item = manual_data.get(key)
    if not isinstance(item, dict):
        return {
            "key": key,
            "value": None,
            "currency": None,
            "source": "manual",
            "timestamp": timestamp,
            "observation_date": None,
            "updated_at": None,
            "status": "error",
            "error": f"manual market data key not found: {key}",
            "path": str(manual_path),
        }

    return {**item, "path": str(manual_path)}


def _asset_type_from_market_symbols(key: str, config: dict) -> str | None:
    market_symbols = _optional_mapping(config, "market_symbols")
    symbol_config = market_symbols.get(key)
    if isinstance(symbol_config, dict) and symbol_config.get("asset_type"):
        return str(symbol_config["asset_type"])
    return None


def _first_candidate_name(candidates: list[dict], fallback: str) -> str:
    for candidate in candidates:
        if candidate.get("name"):
            return str(candidate["name"])
    return fallback


def _first_candidate_asset_type(candidates: list[dict]) -> str | None:
    for candidate in candidates:
        if candidate.get("asset_type"):
            return str(candidate["asset_type"])
    return None


def _resolve_path(path: str) -> Path:
    requested_path = Path(path)
    if requested_path.is_absolute():
        return requested_path

    if requested_path.exists():
        return requested_path

    return _project_root() / requested_path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_project_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    load_dotenv(_project_root() / ".env")
    load_dotenv()


def _optional_mapping(source: dict, key: str) -> dict:
    value = source.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"data_sources.yaml must contain mapping: {key}")
    return value


def _to_float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_simple_yaml(raw_text: str) -> dict:
    lines = raw_text.splitlines()
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]

    for index, line in enumerate(lines):
        if not line.strip() or line.lstrip().startswith("#"):
            continue

        indent = len(line) - len(line.lstrip(" "))
        content = line.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()

        parent = stack[-1][1]
        if content.startswith("- "):
            if not isinstance(parent, list):
                raise ValueError(f"Unsupported YAML list item on line {index + 1}.")
            parent.append(_parse_simple_yaml_scalar(content[2:].strip()))
            continue

        if ":" not in content:
            raise ValueError(f"Unsupported YAML syntax on line {index + 1}.")

        key, value = content.split(":", 1)
        key = _parse_simple_yaml_key(key.strip())
        value = value.strip()

        if value:
            parent[key] = _parse_simple_yaml_scalar(value)
            continue

        child = [] if _next_content_is_list(lines, index, indent) else {}
        parent[key] = child
        stack.append((indent, child))

    return root


def _next_content_is_list(lines: list[str], current_index: int, current_indent: int) -> bool:
    for line in lines[current_index + 1 :]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        return indent > current_indent and line.strip().startswith("- ")
    return False


def _parse_simple_yaml_key(value: str) -> str:
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def _parse_simple_yaml_scalar(value: str) -> Any:
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]

    lower_value = value.lower()
    if lower_value == "true":
        return True
    if lower_value == "false":
        return False
    if lower_value in {"null", "none", "~"}:
        return None

    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value

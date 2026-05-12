from __future__ import annotations

from datetime import datetime, timezone
from math import sqrt
from statistics import stdev
from typing import Any


METHODOLOGY_NOTE = (
    "Historical features are descriptive price-return features based on ETF proxy close prices. "
    "They are not total-return backtests, not the user's actual fund NAV performance, and not forecasts."
)
RETURN_TYPE = "price_return_not_personal_account_return"


def normalize_daily_ohlcv(response: dict) -> list[dict]:
    if not isinstance(response, dict) or response.get("status") != "ok":
        return []

    normalized = []
    observations = response.get("observations", [])
    if not isinstance(observations, list):
        return []

    for row in observations:
        if not isinstance(row, dict):
            continue

        parsed = {
            "date": str(row.get("date") or "").strip(),
            "open": _to_float_or_none(row.get("open")),
            "high": _to_float_or_none(row.get("high")),
            "low": _to_float_or_none(row.get("low")),
            "close": _to_float_or_none(row.get("close")),
            "volume": _to_float_or_none(row.get("volume")),
        }
        if not parsed["date"] or any(parsed[field] is None for field in ("open", "high", "low", "close")):
            continue
        normalized.append(parsed)

    normalized.sort(key=lambda item: item["date"])
    return normalized


def calculate_returns(observations: list[dict]) -> dict:
    observations = _valid_observations(observations)
    if not observations:
        return {
            "status": "insufficient_data",
            "error": "No valid OHLC observations available.",
        }

    latest = observations[-1]
    latest_close = latest["close"]
    latest_date = latest["date"]

    result = {
        "status": "ok",
        "error": None,
        "latest_date": latest_date,
        "latest_close": latest_close,
        "return_1m": _period_return(observations, 21),
        "return_3m": _period_return(observations, 63),
        "return_6m": _period_return(observations, 126),
        "return_ytd": _return_ytd(observations),
        "max_drawdown_3m": _max_drawdown(observations[-64:]),
        "volatility_1m_annualized": _annualized_volatility(observations, 21),
        "distance_from_recent_high": _distance_from_recent_high(observations[-63:]),
    }
    return result


def build_market_history_features(history_by_asset: dict) -> dict:
    features = {
        "generated_at": _utc_now(),
        "history_scope": {
            "alpha_vantage_outputsize": "compact",
            "scope_note": (
                "Compact daily history usually covers recent observations only and is not sufficient "
                "for full 2000-present crisis-window analysis."
            ),
        },
        "assets": {},
        "data_limitations": [],
        "methodology_note": METHODOLOGY_NOTE,
    }

    if not isinstance(history_by_asset, dict):
        features["data_limitations"].append("history_by_asset must be a mapping.")
        return features

    for asset_key, payload in history_by_asset.items():
        if not isinstance(payload, dict):
            features["assets"][asset_key] = {
                "status": "error",
                "error": "Asset history payload missing.",
            }
            features["data_limitations"].append(f"{asset_key}: asset history payload missing.")
            continue

        response = payload.get("response", payload)
        observations = normalize_daily_ohlcv(response)
        calculated = calculate_returns(observations)

        asset_features = {
            "symbol": payload.get("symbol") or response.get("symbol"),
            "name": payload.get("name"),
            "asset_class": payload.get("asset_class"),
            "proxy_for": payload.get("proxy_for"),
            "proxy_note": _proxy_note(payload),
            "return_type": RETURN_TYPE,
            "provider": payload.get("provider") or response.get("source"),
            "source": response.get("source"),
            "input_status": response.get("status"),
            "input_error": response.get("error"),
            "observation_count": len(observations),
            **calculated,
        }
        features["assets"][asset_key] = asset_features

        if response.get("status") != "ok":
            features["data_limitations"].append(
                f"{asset_key}: {response.get('error') or 'history fetch failed'}"
            )
            continue

        for metric_key in ("return_6m", "return_ytd", "max_drawdown_3m", "volatility_1m_annualized"):
            metric = asset_features.get(metric_key)
            if isinstance(metric, dict) and metric.get("status") == "insufficient_data":
                features["data_limitations"].append(
                    f"{asset_key}.{metric_key}: {metric.get('error')}"
                )

    return features


def _proxy_note(payload: dict) -> str:
    proxy_for = payload.get("proxy_for")
    if proxy_for:
        return f"ETF proxy for {proxy_for}, not the user's actual QDII fund NAV."
    return "ETF proxy, not the user's actual QDII fund NAV."


def _valid_observations(observations: list[dict]) -> list[dict]:
    valid = []
    for row in observations:
        if not isinstance(row, dict):
            continue
        close = _to_float_or_none(row.get("close"))
        if close is None or close <= 0:
            continue
        valid.append({**row, "close": close})
    valid.sort(key=lambda item: item["date"])
    return valid


def _period_return(observations: list[dict], periods: int) -> dict:
    if len(observations) <= periods:
        return _metric_insufficient(
            periods=periods,
            error=f"Need more than {periods} observations; got {len(observations)}.",
        )

    latest = observations[-1]
    previous = observations[-1 - periods]
    if previous["close"] == 0:
        return _metric_insufficient(periods=periods, error="Previous close is zero.")

    return {
        "status": "ok",
        "error": None,
        "periods": periods,
        "latest_date": latest["date"],
        "previous_date": previous["date"],
        "value": latest["close"] / previous["close"] - 1,
    }


def _return_ytd(observations: list[dict]) -> dict:
    latest = observations[-1]
    latest_year = latest["date"][:4]
    year_observations = [
        observation
        for observation in observations
        if observation.get("date", "").startswith(latest_year)
    ]
    if len(year_observations) < 2:
        return {
            "status": "insufficient_data",
            "error": f"Need at least two observations in {latest_year}.",
        }

    first = year_observations[0]
    if first["close"] == 0:
        return {
            "status": "insufficient_data",
            "error": "First YTD close is zero.",
        }

    return {
        "status": "ok",
        "error": None,
        "latest_date": latest["date"],
        "previous_date": first["date"],
        "value": latest["close"] / first["close"] - 1,
    }


def _max_drawdown(observations: list[dict]) -> dict:
    if len(observations) < 2:
        return {
            "status": "insufficient_data",
            "error": f"Need at least 2 observations; got {len(observations)}.",
        }

    running_high = observations[0]["close"]
    max_drawdown = 0.0
    for observation in observations:
        close = observation["close"]
        running_high = max(running_high, close)
        if running_high == 0:
            continue
        drawdown = close / running_high - 1
        max_drawdown = min(max_drawdown, drawdown)

    return {
        "status": "ok",
        "error": None,
        "periods": len(observations),
        "value": max_drawdown,
    }


def _annualized_volatility(observations: list[dict], periods: int) -> dict:
    if len(observations) <= periods:
        return _metric_insufficient(
            periods=periods,
            error=f"Need more than {periods} observations; got {len(observations)}.",
        )

    sample = observations[-(periods + 1):]
    daily_returns = []
    for previous, current in zip(sample, sample[1:]):
        if previous["close"] == 0:
            continue
        daily_returns.append(current["close"] / previous["close"] - 1)

    if len(daily_returns) < 2:
        return {
            "status": "insufficient_data",
            "error": "Need at least two daily returns.",
        }

    return {
        "status": "ok",
        "error": None,
        "periods": periods,
        "value": stdev(daily_returns) * sqrt(252),
    }


def _distance_from_recent_high(observations: list[dict]) -> dict:
    if not observations:
        return {
            "status": "insufficient_data",
            "error": "No observations for recent high calculation.",
        }

    latest = observations[-1]
    recent_high = max(observation["close"] for observation in observations)
    if recent_high == 0:
        return {
            "status": "insufficient_data",
            "error": "Recent high is zero.",
        }

    return {
        "status": "ok",
        "error": None,
        "periods": len(observations),
        "recent_high": recent_high,
        "value": latest["close"] / recent_high - 1,
    }


def _metric_insufficient(periods: int, error: str) -> dict:
    return {
        "status": "insufficient_data",
        "error": error,
        "periods": periods,
        "value": None,
    }


def _to_float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_providers.fred_provider import get_fred_series
from market.market_temperature import (
    METHODOLOGY_NOTE,
    calculate_change,
    calculate_yoy_change,
    normalize_observations,
    score_market_temperature,
)


OUTPUT_PATH = PROJECT_ROOT / "outputs" / "reports" / "market_temperature.json"
MARKET_SNAPSHOT_PATH = PROJECT_ROOT / "outputs" / "reports" / "market_snapshot.json"
FRED_RETRY_COUNT = 2
FRED_RETRY_SLEEP_SECONDS = 1
SERIES_PLAN = {
    "sp500": {"series_id": "SP500", "limit": 180},
    "nasdaq": {"series_id": "NASDAQCOM", "limit": 180},
    "dgs10": {"series_id": "DGS10", "limit": 180},
    "cpi": {"series_id": "CPIAUCSL", "limit": 36},
    "pce": {"series_id": "PCEPI", "limit": 36},
    "nonfarm": {"series_id": "PAYEMS", "limit": 36},
    "usd_cny": {"series_id": "DEXCHUS", "limit": 180},
}


def main() -> None:
    generated_at = _utc_now()
    series_results = _load_fred_series()
    usd_cny_latest_cache = _load_usd_cny_latest_cache(series_results["usd_cny"])
    normalized_series = {
        key: normalize_observations(result.get("data", []))
        for key, result in series_results.items()
    }

    calculated_indicators = _calculate_indicators(
        normalized_series,
        usd_cny_latest_cache=usd_cny_latest_cache,
    )
    data_limitations = _collect_data_limitations(
        series_results,
        calculated_indicators,
        usd_cny_latest_cache=usd_cny_latest_cache,
    )

    score_inputs = {
        **calculated_indicators,
        "dgs10_latest": calculated_indicators["dgs10_latest"]["value"],
        "data_limitations": data_limitations,
    }
    temperature_assessment = score_market_temperature(score_inputs)

    output = {
        "input_series_status": _series_status(series_results, normalized_series),
        "calculated_indicators": calculated_indicators,
        "temperature_assessment": temperature_assessment,
        "data_limitations": temperature_assessment["data_limitations"],
        "methodology_note": METHODOLOGY_NOTE,
        "generated_at": generated_at,
    }

    formatted_json = json.dumps(output, ensure_ascii=False, indent=2)
    print(formatted_json)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(formatted_json + "\n", encoding="utf-8")


def _load_fred_series() -> dict:
    return {
        key: _get_fred_series_with_retry(plan["series_id"], limit=plan["limit"])
        for key, plan in SERIES_PLAN.items()
    }


def _get_fred_series_with_retry(series_id: str, limit: int) -> dict:
    last_result = None
    for attempt in range(FRED_RETRY_COUNT + 1):
        result = get_fred_series(series_id, limit=limit)
        if result.get("status") == "ok":
            return result

        last_result = result
        if attempt < FRED_RETRY_COUNT:
            time.sleep(FRED_RETRY_SLEEP_SECONDS)

    return last_result or get_fred_series(series_id, limit=limit)


def _calculate_indicators(
    normalized_series: dict[str, list[dict]],
    usd_cny_latest_cache: dict | None = None,
) -> dict:
    dgs10_latest = _latest_observation(normalized_series["dgs10"])
    usd_cny_latest = (
        usd_cny_latest_cache
        if usd_cny_latest_cache is not None
        else _latest_observation(normalized_series["usd_cny"])
    )

    return {
        "sp500_1m_change": calculate_change(normalized_series["sp500"], periods=21),
        "sp500_3m_change": calculate_change(normalized_series["sp500"], periods=63),
        "nasdaq_1m_change": calculate_change(normalized_series["nasdaq"], periods=21),
        "nasdaq_3m_change": calculate_change(normalized_series["nasdaq"], periods=63),
        "dgs10_latest": dgs10_latest,
        "dgs10_1m_change": calculate_change(normalized_series["dgs10"], periods=21),
        "cpi_mom_change": calculate_change(normalized_series["cpi"], periods=1),
        "cpi_yoy_change": calculate_yoy_change(normalized_series["cpi"], months=12),
        "pce_mom_change": calculate_change(normalized_series["pce"], periods=1),
        "pce_yoy_change": calculate_yoy_change(normalized_series["pce"], months=12),
        "nonfarm_mom_change": calculate_change(normalized_series["nonfarm"], periods=1),
        "usd_cny_latest": usd_cny_latest,
        "usd_cny_1m_change": calculate_change(normalized_series["usd_cny"], periods=21),
    }


def _latest_observation(observations: list[dict]) -> dict:
    if not observations:
        return {
            "value": None,
            "observation_date": None,
            "source": "FRED",
            "status": "insufficient_data",
            "error": "No valid observations available",
        }

    latest = observations[-1]
    return {
        "value": latest["value"],
        "observation_date": latest["date"],
        "source": "FRED",
        "status": "ok",
        "error": None,
    }


def _series_status(
    series_results: dict[str, dict],
    normalized_series: dict[str, list[dict]],
) -> dict:
    status = {}
    for key, result in series_results.items():
        normalized = normalized_series[key]
        latest = normalized[-1] if normalized else None
        status[key] = {
            "series_id": result.get("series_id") or SERIES_PLAN[key]["series_id"],
            "source": result.get("source") or "FRED",
            "timestamp": result.get("timestamp"),
            "status": result.get("status"),
            "error": result.get("error"),
            "requested_limit": SERIES_PLAN[key]["limit"],
            "valid_observation_count": len(normalized),
            "latest_observation_date": latest.get("date") if latest else None,
        }
    return status


def _load_usd_cny_latest_cache(usd_cny_series_result: dict) -> dict | None:
    if usd_cny_series_result.get("status") == "ok":
        return None
    if not MARKET_SNAPSHOT_PATH.exists():
        return None

    try:
        snapshot = json.loads(MARKET_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    fx_data = snapshot.get("fx_data")
    if not isinstance(fx_data, dict):
        return None

    usd_cny = fx_data.get("usd_cny")
    if not isinstance(usd_cny, dict) or usd_cny.get("status") != "ok":
        return None

    value = usd_cny.get("value")
    if value is None:
        return None

    return {
        "value": value,
        "observation_date": usd_cny.get("observation_date"),
        "source": usd_cny.get("source") or "FRED",
        "timestamp": usd_cny.get("timestamp"),
        "status": "stale_cache",
        "error": None,
        "cached_at": snapshot.get("cached_at"),
        "notes": [
            "Latest USD/CNY value loaded from market_snapshot cache; this is not historical data."
        ],
    }


def _collect_data_limitations(
    series_results: dict[str, dict],
    calculated_indicators: dict,
    usd_cny_latest_cache: dict | None = None,
) -> list[str]:
    limitations = []

    for key, result in series_results.items():
        if result.get("status") != "ok":
            limitations.append(
                f"{key} ({SERIES_PLAN[key]['series_id']}) unavailable: {result.get('error')}"
            )

    for key, indicator in calculated_indicators.items():
        if isinstance(indicator, dict) and indicator.get("status") == "insufficient_data":
            limitations.append(f"{key} insufficient_data: {indicator.get('error')}")

    if usd_cny_latest_cache is not None:
        limitations.append(
            "DEXCHUS historical series unavailable; latest USD/CNY value loaded from market_snapshot cache."
        )

    return _dedupe(limitations)


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    main()

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .alpha_vantage_provider import load_alpha_vantage_api_key


SOURCE = "Alpha Vantage"
ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"


def get_daily_time_series(symbol: str, outputsize: str = "compact") -> dict:
    generated_at = _utc_now()
    api_key = load_alpha_vantage_api_key()
    if not api_key:
        return _history_error(
            symbol=symbol,
            error="ALPHA_VANTAGE_API_KEY not configured",
            timestamp=generated_at,
            request_sent=False,
        )

    try:
        import requests
    except ImportError as exc:
        return _history_error(
            symbol=symbol,
            error=f"requests import failed: {exc}",
            timestamp=generated_at,
            request_sent=False,
        )

    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": symbol,
        "outputsize": outputsize,
        "apikey": api_key,
    }

    try:
        response = requests.get(ALPHA_VANTAGE_URL, params=params, timeout=20)
    except Exception as exc:
        return _history_error(
            symbol=symbol,
            error=f"Alpha Vantage request failed: {exc}",
            timestamp=generated_at,
            request_sent=True,
        )

    if response.status_code != 200:
        return _history_error(
            symbol=symbol,
            error=f"Alpha Vantage HTTP status {response.status_code}: {_text_preview(response.text)}",
            timestamp=generated_at,
            request_sent=True,
        )

    try:
        payload = response.json()
    except ValueError:
        return _history_error(
            symbol=symbol,
            error=f"Alpha Vantage response was not JSON: {_text_preview(response.text)}",
            timestamp=generated_at,
            request_sent=True,
        )

    api_message = _alpha_vantage_api_message(payload)
    if api_message:
        return _history_error(
            symbol=symbol,
            error=api_message,
            timestamp=generated_at,
            metadata=_metadata_from_payload(payload),
            request_sent=True,
        )

    time_series = _find_daily_time_series(payload)
    if not isinstance(time_series, dict):
        return _history_error(
            symbol=symbol,
            error=(
                "Alpha Vantage response missing Time Series (Daily); "
                f"top_level_keys={_top_level_keys(payload)}; raw_preview={_raw_preview(payload)}"
            ),
            timestamp=generated_at,
            metadata=_metadata_from_payload(payload),
            request_sent=True,
        )

    observations = _parse_time_series(time_series)
    if not observations:
        return _history_error(
            symbol=symbol,
            error=(
                "Alpha Vantage daily time series contained no valid OHLC rows; "
                f"top_level_keys={_top_level_keys(payload)}; raw_preview={_raw_preview(payload)}"
            ),
            timestamp=generated_at,
            metadata=_metadata_from_payload(payload),
            request_sent=True,
        )

    return {
        "symbol": symbol,
        "source": SOURCE,
        "status": "ok",
        "error": None,
        "observations": observations,
        "metadata": _metadata_from_payload(payload),
        "timestamp": generated_at,
        "request_sent": True,
    }


def _find_daily_time_series(payload: Any) -> dict | None:
    if not isinstance(payload, dict):
        return None

    for key, value in payload.items():
        normalized_key = str(key).lower()
        if "time series" in normalized_key and "daily" in normalized_key and isinstance(value, dict):
            return value

    for value in payload.values():
        candidate = _date_keyed_mapping(value)
        if candidate is not None:
            return candidate

    return None


def _date_keyed_mapping(value: Any) -> dict | None:
    if isinstance(value, dict):
        date_keys = [
            key
            for key in value.keys()
            if _date_string_or_none(key)
        ]
        if len(date_keys) >= 2:
            return value
        for nested in value.values():
            candidate = _date_keyed_mapping(nested)
            if candidate is not None:
                return candidate

    if isinstance(value, list):
        for item in value:
            candidate = _date_keyed_mapping(item)
            if candidate is not None:
                return candidate

    return None


def _parse_time_series(time_series: dict) -> list[dict]:
    observations = []
    for raw_date, raw_values in time_series.items():
        date_value = _date_string_or_none(raw_date)
        if not date_value or not isinstance(raw_values, dict):
            continue

        parsed = {
            "date": date_value,
            "open": _field_float(raw_values, "open"),
            "high": _field_float(raw_values, "high"),
            "low": _field_float(raw_values, "low"),
            "close": _field_float(raw_values, "close"),
            "volume": _field_float(raw_values, "volume"),
        }
        if any(parsed[field] is None for field in ("open", "high", "low", "close")):
            continue
        observations.append(parsed)

    observations.sort(key=lambda item: item["date"])
    return observations


def _field_float(values: dict, field_name: str) -> float | None:
    for key, value in values.items():
        if field_name in str(key).lower():
            return _to_float_or_none(value)
    return None


def _alpha_vantage_api_message(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None

    for key in ("Note", "Information", "Error Message", "Error", "Message"):
        value = payload.get(key)
        if value:
            return f"Alpha Vantage {key}: {value}; top_level_keys={_top_level_keys(payload)}"

    warning_terms = (
        "rate limit",
        "frequency",
        "premium",
        "demo",
        "not available",
        "invalid api call",
    )
    for text in _iter_strings(payload):
        normalized = text.lower()
        if any(term in normalized for term in warning_terms):
            return f"Alpha Vantage API message: {text}; top_level_keys={_top_level_keys(payload)}"

    return None


def _metadata_from_payload(payload: Any) -> dict:
    if not isinstance(payload, dict):
        return {}

    for key, value in payload.items():
        if "meta" in str(key).lower() and isinstance(value, dict):
            return value
    return {}


def _iter_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _iter_strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _iter_strings(nested)


def _date_string_or_none(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if len(text) < 10:
        return None

    candidate = text[:10]
    try:
        datetime.fromisoformat(candidate)
    except ValueError:
        return None
    return candidate


def _to_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _history_error(
    symbol: str,
    error: str,
    timestamp: str,
    metadata: dict | None = None,
    request_sent: bool = False,
) -> dict:
    return {
        "symbol": symbol,
        "source": SOURCE,
        "status": "error",
        "error": error,
        "observations": [],
        "metadata": metadata or {},
        "timestamp": timestamp,
        "request_sent": request_sent,
    }


def _top_level_keys(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        return [str(key) for key in payload.keys()]
    return [type(payload).__name__]


def _raw_preview(payload: Any) -> str:
    text = str(payload)
    return text[:200]


def _text_preview(value: str | None) -> str:
    return (value or "")[:200].strip()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

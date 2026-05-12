from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SOURCE = "Alpha Vantage"
SOURCE_TIER = "third_party_api"
ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"
GOLD_SYMBOL = "GOLD"


def load_alpha_vantage_api_key() -> str | None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return os.getenv("ALPHA_VANTAGE_API_KEY")

    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env")
    load_dotenv()
    return os.getenv("ALPHA_VANTAGE_API_KEY")


def get_gold_spot() -> dict:
    function = "GOLD_SILVER_SPOT"
    generated_at = _utc_now()
    payload_result = _request_alpha_vantage(
        function=function,
        params={"function": function, "symbol": GOLD_SYMBOL},
        timestamp=generated_at,
    )
    if payload_result.get("status") != "ok":
        return payload_result

    payload = payload_result["payload"]
    price, observation_date = _find_numeric_field(
        payload,
        key_hints=("price", "value", "rate", "spot"),
    )
    if price is None:
        return _gold_error(
            function=function,
            error=(
                "Alpha Vantage spot response did not contain a parseable gold price; "
                f"top_level_keys={_top_level_keys(payload)}; raw_preview={_raw_preview(payload)}"
            ),
            timestamp=generated_at,
        )

    observation_date = observation_date or _find_date_like_value(payload)
    return _gold_ok(
        function=function,
        value=price,
        timestamp=generated_at,
        observation_date=observation_date,
        name="Gold spot price",
    )


def get_gold_history_latest(interval: str = "daily") -> dict:
    function = "GOLD_SILVER_HISTORY"
    generated_at = _utc_now()
    payload_result = _request_alpha_vantage(
        function=function,
        params={
            "function": function,
            "symbol": GOLD_SYMBOL,
            "interval": interval,
        },
        timestamp=generated_at,
    )
    if payload_result.get("status") != "ok":
        return payload_result

    payload = payload_result["payload"]
    latest_record = _find_latest_history_record(payload)
    if latest_record is None:
        return _gold_error(
            function=function,
            error=(
                "Alpha Vantage history response did not contain a parseable daily gold price; "
                f"top_level_keys={_top_level_keys(payload)}; raw_preview={_raw_preview(payload)}"
            ),
            timestamp=generated_at,
        )

    observation_date, price = latest_record
    return _gold_ok(
        function=function,
        value=price,
        timestamp=generated_at,
        observation_date=observation_date,
        name="Gold daily history latest price",
    )


def _request_alpha_vantage(function: str, params: dict, timestamp: str) -> dict:
    api_key = load_alpha_vantage_api_key()
    if not api_key:
        return _gold_error(
            function=function,
            error="ALPHA_VANTAGE_API_KEY not configured",
            timestamp=timestamp,
        )

    try:
        import requests
    except ImportError as exc:
        return _gold_error(
            function=function,
            error=f"requests import failed: {exc}",
            timestamp=timestamp,
        )

    request_params = {**params, "apikey": api_key}
    try:
        response = requests.get(ALPHA_VANTAGE_URL, params=request_params, timeout=20)
    except Exception as exc:
        return _gold_error(
            function=function,
            error=f"Alpha Vantage request failed: {exc}",
            timestamp=timestamp,
        )

    if response.status_code != 200:
        return _gold_error(
            function=function,
            error=f"Alpha Vantage HTTP status {response.status_code}: {_text_preview(response.text)}",
            timestamp=timestamp,
        )

    try:
        payload = response.json()
    except ValueError:
        return _gold_error(
            function=function,
            error=f"Alpha Vantage response was not JSON: {_text_preview(response.text)}",
            timestamp=timestamp,
        )

    api_message = _alpha_vantage_api_message(payload)
    if api_message:
        return _gold_error(
            function=function,
            error=api_message,
            timestamp=timestamp,
        )

    return {
        "function": function,
        "payload": payload,
        "source": SOURCE,
        "timestamp": timestamp,
        "status": "ok",
        "error": None,
    }


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


def _find_numeric_field(payload: Any, key_hints: tuple[str, ...]) -> tuple[float | None, str | None]:
    for key, value, parent in _walk_key_values(payload):
        normalized_key = key.lower()
        if not any(hint in normalized_key for hint in key_hints):
            continue
        if "volume" in normalized_key:
            continue

        parsed_value = _to_float_or_none(value)
        if parsed_value is None:
            continue
        return parsed_value, _find_date_like_value(parent)

    return None, None


def _find_latest_history_record(payload: Any) -> tuple[str, float] | None:
    records: list[tuple[str, float]] = []
    _collect_history_records(payload, records)
    if not records:
        return None

    records.sort(key=lambda item: item[0])
    return records[-1]


def _collect_history_records(value: Any, records: list[tuple[str, float]]) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_date = _date_string_or_none(key)
            if key_date and isinstance(nested, dict):
                price = _price_from_mapping(nested)
                if price is not None:
                    records.append((key_date, price))

        record_date = _find_date_like_value(value)
        price = _price_from_mapping(value)
        if record_date and price is not None:
            records.append((record_date, price))

        for nested in value.values():
            _collect_history_records(nested, records)
        return

    if isinstance(value, list):
        for item in value:
            _collect_history_records(item, records)


def _price_from_mapping(mapping: dict) -> float | None:
    priority_terms = ("close", "price", "value", "rate", "spot")
    for term in priority_terms:
        for key, value in mapping.items():
            normalized_key = str(key).lower()
            if term not in normalized_key or "volume" in normalized_key:
                continue
            parsed_value = _to_float_or_none(value)
            if parsed_value is not None:
                return parsed_value
    return None


def _find_date_like_value(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized_key = str(key).lower()
            if any(term in normalized_key for term in ("date", "time", "timestamp", "refreshed", "updated")):
                parsed_date = _date_string_or_none(nested)
                if parsed_date:
                    return parsed_date
        for nested in value.values():
            parsed_date = _find_date_like_value(nested)
            if parsed_date:
                return parsed_date

    if isinstance(value, list):
        for item in value:
            parsed_date = _find_date_like_value(item)
            if parsed_date:
                return parsed_date

    return None


def _walk_key_values(value: Any, parent: Any | None = None):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield str(key), nested, value
            yield from _walk_key_values(nested, value)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_key_values(item, parent)


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
    if not text:
        return None

    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date().isoformat()
    except ValueError:
        pass

    if len(text) >= 10:
        candidate = text[:10]
        try:
            datetime.fromisoformat(candidate)
        except ValueError:
            return None
        return candidate

    return None


def _to_float_or_none(value: Any) -> float | None:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", "").replace("$", "")

    try:
        return float(text)
    except ValueError:
        return None


def _gold_ok(
    function: str,
    value: float,
    timestamp: str,
    observation_date: str | None,
    name: str,
) -> dict:
    return {
        "key": "gold",
        "name": name,
        "asset_type": "commodity",
        "value": value,
        "currency": "USD",
        "symbol": GOLD_SYMBOL,
        "function": function,
        "source": SOURCE,
        "source_tier": SOURCE_TIER,
        "timestamp": timestamp,
        "observation_date": observation_date,
        "status": "ok",
        "error": None,
        "attempted_sources": [
            {
                "source": SOURCE,
                "function": function,
                "symbol": GOLD_SYMBOL,
                "status": "ok",
                "error": None,
                "timestamp": timestamp,
                "observation_date": observation_date,
            }
        ],
    }


def _gold_error(function: str, error: str, timestamp: str) -> dict:
    return {
        "key": "gold",
        "name": "Gold price",
        "asset_type": "commodity",
        "value": None,
        "currency": "USD",
        "symbol": GOLD_SYMBOL,
        "function": function,
        "source": SOURCE,
        "source_tier": SOURCE_TIER,
        "timestamp": timestamp,
        "observation_date": None,
        "status": "error",
        "error": error,
    }


def _top_level_keys(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        return [str(key) for key in payload.keys()]
    return [type(payload).__name__]


def _raw_preview(payload: Any) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False)[:200]
    except TypeError:
        return str(payload)[:200]


def _text_preview(value: str | None) -> str:
    return (value or "")[:200].strip()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

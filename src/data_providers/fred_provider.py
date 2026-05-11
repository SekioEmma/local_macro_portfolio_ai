from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any


SOURCE = "FRED"
FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"


def get_fred_series(series_id: str, limit: int = 10) -> dict:
    generated_at = _utc_now()
    _load_dotenv_if_available()

    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        return _fred_error(
            series_id=series_id,
            limit=limit,
            error="FRED_API_KEY not configured",
            timestamp=generated_at,
        )

    try:
        import requests
    except ImportError as exc:
        return _fred_error(
            series_id=series_id,
            limit=limit,
            error=f"requests import failed: {exc}",
            timestamp=generated_at,
        )

    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": limit,
    }

    try:
        response = requests.get(FRED_OBSERVATIONS_URL, params=params, timeout=20)
        if response.status_code != 200:
            return _fred_error(
                series_id=series_id,
                limit=limit,
                error=f"FRED HTTP status {response.status_code}",
                timestamp=generated_at,
            )

        payload = response.json()

        observations = payload.get("observations")
        if not isinstance(observations, list):
            api_error = payload.get("error_message") or "FRED response missing observations"
            return _fred_error(
                series_id=series_id,
                limit=limit,
                error=api_error,
                timestamp=generated_at,
            )

        data = []
        for observation in observations:
            parsed_value = _parse_observation_value(observation.get("value"))
            if parsed_value is None:
                continue

            data.append(
                {
                    "date": observation.get("date"),
                    "value": parsed_value,
                }
            )
            if len(data) >= limit:
                break

        if not data:
            return _fred_error(
                series_id=series_id,
                limit=limit,
                error="No valid FRED observations returned",
                timestamp=generated_at,
            )

        return {
            "series_id": series_id,
            "limit": limit,
            "data": data,
            "source": SOURCE,
            "timestamp": generated_at,
            "status": "ok",
            "error": None,
        }
    except Exception as exc:
        return _fred_error(
            series_id=series_id,
            limit=limit,
            error=str(exc),
            timestamp=generated_at,
        )


def get_fred_latest(series_id: str) -> dict:
    generated_at = _utc_now()
    series = get_fred_series(series_id, limit=10)

    if series.get("status") != "ok":
        return _fred_latest_error(
            series_id=series_id,
            error=str(series.get("error") or "FRED series request failed"),
            timestamp=series.get("timestamp") or generated_at,
        )

    for observation in series.get("data", []):
        value = _to_float_or_none(observation.get("value"))
        if value is None:
            continue

        return {
            "series_id": series_id,
            "value": value,
            "observation_date": observation.get("date"),
            "source": SOURCE,
            "timestamp": generated_at,
            "status": "ok",
            "error": None,
        }

    return _fred_latest_error(
        series_id=series_id,
        error="No valid numeric FRED observations found",
        timestamp=series.get("timestamp") or generated_at,
    )


def _fred_error(series_id: str, limit: int, error: str, timestamp: str) -> dict:
    return {
        "series_id": series_id,
        "limit": limit,
        "data": [],
        "source": SOURCE,
        "timestamp": timestamp,
        "status": "error",
        "error": error,
    }


def _fred_latest_error(series_id: str, error: str, timestamp: str) -> dict:
    return {
        "series_id": series_id,
        "value": None,
        "observation_date": None,
        "timestamp": timestamp,
        "source": SOURCE,
        "status": "error",
        "error": error,
    }


def _parse_observation_value(value: Any) -> float | str | None:
    if value is None:
        return None

    if str(value).strip() == ".":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


def _to_float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    load_dotenv()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

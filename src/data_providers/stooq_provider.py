from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any


SOURCE = "stooq"
STOOQ_DOWNLOAD_URL = "https://stooq.com/q/d/l/"
REQUIRED_FIELDS = ("date", "open", "high", "low", "close")
OPTIONAL_FIELDS = ("volume",)


def get_stooq_history(symbol: str, limit: int = 90) -> dict:
    generated_at = _utc_now()

    if limit <= 0:
        return _history_error(
            symbol=symbol,
            limit=limit,
            error="limit must be greater than 0",
            timestamp=generated_at,
        )

    try:
        import requests
    except ImportError as exc:
        return _history_error(
            symbol=symbol,
            limit=limit,
            error=f"requests import failed: {exc}",
            timestamp=generated_at,
        )

    try:
        response = requests.get(
            STOOQ_DOWNLOAD_URL,
            params={"s": symbol, "i": "d"},
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        )
    except Exception as exc:
        return _history_error(
            symbol=symbol,
            limit=limit,
            error=str(exc),
            timestamp=generated_at,
        )

    raw_text = response.text or ""
    raw_preview = raw_text[:200]

    if response.status_code != 200:
        return _history_error(
            symbol=symbol,
            limit=limit,
            error=f"Stooq HTTP status {response.status_code}",
            timestamp=generated_at,
            raw_preview=raw_preview,
        )

    if not raw_text.strip():
        return _history_error(
            symbol=symbol,
            limit=limit,
            error="Stooq returned empty response",
            timestamp=generated_at,
            raw_preview=raw_preview,
        )

    first_line = raw_text.lstrip("\ufeff").splitlines()[0] if raw_text.splitlines() else ""
    if "," not in first_line:
        return _history_error(
            symbol=symbol,
            limit=limit,
            error="Stooq response does not look like CSV",
            timestamp=generated_at,
            raw_preview=raw_preview,
        )

    reader = csv.DictReader(io.StringIO(raw_text.lstrip("\ufeff")))
    if reader.fieldnames is None:
        return _history_error(
            symbol=symbol,
            limit=limit,
            error="Stooq CSV response has no header",
            timestamp=generated_at,
            raw_preview=raw_preview,
        )

    field_map = _build_field_map(reader.fieldnames)
    missing_fields = [field for field in REQUIRED_FIELDS if field not in field_map]
    if missing_fields:
        return _history_error(
            symbol=symbol,
            limit=limit,
            error=f"Stooq CSV missing required field(s): {', '.join(missing_fields)}",
            timestamp=generated_at,
            raw_preview=raw_preview,
            detected_fields=sorted(field_map),
        )

    rows = []
    for row in reader:
        parsed_row = _parse_stooq_row(row, field_map)
        if parsed_row is not None:
            rows.append(parsed_row)

    if not rows:
        return _history_error(
            symbol=symbol,
            limit=limit,
            error="Stooq returned no valid rows",
            timestamp=generated_at,
            raw_preview=raw_preview,
            detected_fields=sorted(field_map),
        )

    return {
        "symbol": symbol,
        "data": rows[-limit:],
        "source": SOURCE,
        "timestamp": generated_at,
        "status": "ok",
        "error": None,
    }


def get_stooq_latest(symbol: str) -> dict:
    generated_at = _utc_now()
    history = get_stooq_history(symbol, limit=10)

    if history.get("status") != "ok":
        return _latest_error(
            symbol=symbol,
            error=str(history.get("error") or "Stooq history request failed"),
            timestamp=history.get("timestamp") or generated_at,
            raw_preview=history.get("raw_preview", ""),
            detected_fields=history.get("detected_fields"),
        )

    data = history.get("data")
    if not isinstance(data, list) or not data:
        return _latest_error(
            symbol=symbol,
            error="Stooq returned no valid rows",
            timestamp=generated_at,
        )

    latest_row = data[-1]
    close = _to_float_or_none(latest_row.get("close"))
    if close is None:
        return _latest_error(
            symbol=symbol,
            error="Stooq returned no valid close value",
            timestamp=generated_at,
        )

    return {
        "symbol": symbol,
        "value": close,
        "currency": None,
        "timestamp": latest_row.get("date") or generated_at,
        "source": SOURCE,
        "status": "ok",
        "error": None,
    }


def _build_field_map(fieldnames: list[str]) -> dict[str, str]:
    field_map = {}
    for fieldname in fieldnames:
        normalized = _normalize_header(fieldname)
        if normalized:
            field_map[normalized] = fieldname
    return field_map


def _normalize_header(value: str) -> str:
    return str(value).replace("\ufeff", "").strip().lower()


def _parse_stooq_row(row: dict, field_map: dict[str, str]) -> dict | None:
    date = _clean_text(row.get(field_map["date"]))
    open_value = _to_float_or_none(row.get(field_map["open"]))
    high_value = _to_float_or_none(row.get(field_map["high"]))
    low_value = _to_float_or_none(row.get(field_map["low"]))
    close_value = _to_float_or_none(row.get(field_map["close"]))

    if not date:
        return None
    if None in (open_value, high_value, low_value, close_value):
        return None

    volume = None
    if "volume" in field_map:
        volume = _to_float_or_none(row.get(field_map["volume"]))

    return {
        "date": date,
        "open": open_value,
        "high": high_value,
        "low": low_value,
        "close": close_value,
        "volume": volume,
    }


def _history_error(
    symbol: str,
    limit: int,
    error: str,
    timestamp: str,
    raw_preview: str = "",
    detected_fields: list[str] | None = None,
) -> dict:
    result = {
        "symbol": symbol,
        "limit": limit,
        "data": [],
        "source": SOURCE,
        "timestamp": timestamp,
        "status": "error",
        "error": error,
        "raw_preview": raw_preview,
    }
    if detected_fields is not None:
        result["detected_fields"] = detected_fields
    return result


def _latest_error(
    symbol: str,
    error: str,
    timestamp: str,
    raw_preview: str = "",
    detected_fields: list[str] | None = None,
) -> dict:
    result = {
        "symbol": symbol,
        "value": None,
        "currency": None,
        "timestamp": timestamp,
        "source": SOURCE,
        "status": "error",
        "error": error,
        "raw_preview": raw_preview,
    }
    if detected_fields is not None:
        result["detected_fields"] = detected_fields
    return result


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _to_float_or_none(value: Any) -> float | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

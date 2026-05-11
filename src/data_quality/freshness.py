from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any


def parse_date_safe(value: str) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None

    normalized = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        pass

    try:
        return date.fromisoformat(normalized[:10])
    except ValueError:
        return None


def calculate_freshness(item: dict, metadata: dict, generated_at: str) -> dict:
    metadata = metadata if isinstance(metadata, dict) else {}
    expected_frequency = metadata.get("expected_frequency")
    max_stale_days = _to_int_or_none(metadata.get("max_stale_days"))
    source_tier = _effective_source_tier(item, metadata)
    importance = metadata.get("importance")
    observation_date = _observation_date(item)

    result = {
        "expected_frequency": expected_frequency,
        "max_stale_days": max_stale_days,
        "source_tier": source_tier,
        "importance": importance,
        "observation_date": observation_date,
        "days_since_observation": None,
        "month_gap": None,
        "freshness_status": "unknown",
        "status": "unknown",
        "error": None,
    }

    item_status = item.get("status") if isinstance(item, dict) else None
    if item_status != "ok":
        result["error"] = f"Data item status is {item_status or 'missing'}."
        return result

    observed_at = parse_date_safe(observation_date or "")
    generated_date = parse_date_safe(generated_at)
    if observed_at is None:
        result["error"] = "observation_date missing or invalid"
        return result
    if generated_date is None:
        generated_date = datetime.now(timezone.utc).date()

    days_since_observation = (generated_date - observed_at).days
    result["days_since_observation"] = days_since_observation
    result["month_gap"] = _month_gap(observed_at, generated_date)

    if max_stale_days is None:
        result["error"] = "max_stale_days missing or invalid"
        return result

    if expected_frequency == "daily":
        result["freshness_status"] = (
            "fresh" if days_since_observation <= max_stale_days else "stale"
        )
    elif expected_frequency == "monthly":
        month_gap = result["month_gap"]
        if month_gap is None:
            result["error"] = "month_gap could not be calculated"
            return result
        if month_gap <= 2:
            result["freshness_status"] = "normal_monthly_lag"
        elif month_gap == 3:
            result["freshness_status"] = "extended_monthly_lag"
        else:
            result["freshness_status"] = "stale"
    elif expected_frequency == "manual":
        result["freshness_status"] = (
            "fresh" if days_since_observation <= max_stale_days else "stale"
        )
    else:
        result["error"] = f"Unsupported expected_frequency: {expected_frequency}"
        return result

    result["status"] = "ok"
    return result


def _observation_date(item: dict) -> str | None:
    if not isinstance(item, dict):
        return None
    return item.get("observation_date") or item.get("updated_at")


def _effective_source_tier(item: dict, metadata: dict) -> str | None:
    if not isinstance(item, dict):
        return metadata.get("source_tier")

    if item.get("status") == "stale_cache":
        return "cache"

    source = str(item.get("source") or "").lower()
    if source == "manual":
        return "manual"
    if source == "yfinance":
        return "unofficial_fallback"

    return metadata.get("source_tier")


def _to_int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _month_gap(observed_at: date, generated_date: date) -> int:
    return (generated_date.year - observed_at.year) * 12 + (
        generated_date.month - observed_at.month
    )

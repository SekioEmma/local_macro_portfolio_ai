from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_providers.market_data_service import (
    FINANCIAL_CONDITION_KEYS,
    IMPORTANT_OPTIONAL_KEYS,
    OPTIONAL_MARKET_KEYS,
    REQUIRED_CORE_KEYS,
    get_core_market_snapshot,
    load_data_source_config,
)
from data_providers.cache import load_json_cache, save_json_cache
from data_quality.freshness import calculate_freshness


DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "outputs" / "reports" / "market_snapshot.json"
CACHE_MAX_AGE_SECONDS = 24 * 60 * 60


def main() -> None:
    snapshot = get_core_market_snapshot()
    live_required_core_errors = _required_core_errors(snapshot)
    _attach_diagnostics(
        snapshot,
        required_core_errors=live_required_core_errors,
        used_cache=False,
    )

    if live_required_core_errors:
        cached_snapshot = load_json_cache(
            str(DEFAULT_OUTPUT_PATH),
            max_age_seconds=CACHE_MAX_AGE_SECONDS,
        )
        if cached_snapshot and _cached_required_core_ok(cached_snapshot):
            snapshot = _mark_stale_cache(
                cached_snapshot,
                live_required_core_errors=live_required_core_errors,
                live_snapshot=snapshot,
            )
        else:
            snapshot["status"] = "error"
            snapshot["error"] = "Required core market data failed and no usable 24h cache is available."
            snapshot["live_required_core_errors"] = live_required_core_errors
            _attach_diagnostics(
                snapshot,
                required_core_errors=live_required_core_errors,
                used_cache=False,
            )
    else:
        optional_failures = _failed_optional_keys(
            snapshot,
            (*IMPORTANT_OPTIONAL_KEYS, *OPTIONAL_MARKET_KEYS),
        )
        if optional_failures:
            snapshot["status"] = "partial"
            snapshot["error"] = "Optional market data unavailable: " + ", ".join(optional_failures)
        else:
            snapshot["status"] = "ok"
            snapshot["error"] = None

    _attach_data_quality(snapshot)

    formatted_json = json.dumps(snapshot, ensure_ascii=False, indent=2)
    print(formatted_json)

    save_json_cache(str(DEFAULT_OUTPUT_PATH), snapshot)


def _required_core_errors(snapshot: dict) -> list[dict]:
    errors = []
    for key in REQUIRED_CORE_KEYS:
        item = _find_data_item(snapshot, key)
        if not isinstance(item, dict):
            errors.append({"key": key, "status": "missing", "error": "Required core item missing."})
            continue
        if item.get("status") != "ok":
            errors.append(
                {
                    "key": key,
                    "status": item.get("status"),
                    "error": item.get("error"),
                    "source": item.get("source"),
                }
            )
            continue
        if item.get("value") is None:
            errors.append(
                {
                    "key": key,
                    "status": item.get("status"),
                    "error": "Required core item returned no value.",
                    "source": item.get("source"),
                }
            )

    return errors


def _cached_required_core_ok(snapshot: dict) -> bool:
    for key in REQUIRED_CORE_KEYS:
        item = _find_data_item(snapshot, key)
        if not isinstance(item, dict) or item.get("status") not in {"ok", "stale_cache"}:
            return False
        if item.get("value") is None:
            return False
    return True


def _failed_optional_keys(snapshot: dict, keys: tuple[str, ...]) -> list[str]:
    failed = []
    for key in keys:
        item = _find_data_item(snapshot, key)
        if not isinstance(item, dict) or item.get("status") != "ok":
            failed.append(key)
    return failed


def _find_data_item(snapshot: dict, key: str) -> dict | None:
    for section in ("market_data", "macro_data", "fx_data", "financial_conditions"):
        data = snapshot.get(section)
        if isinstance(data, dict) and isinstance(data.get(key), dict):
            return data[key]
    package = snapshot.get("market_data_package")
    if isinstance(package, dict):
        for group_name in (
            "treasury_yields",
            "inflation_indicators",
            "oil_and_energy",
            "existing_financial_conditions",
            "unavailable_or_research_needed",
        ):
            group = package.get(group_name)
            if isinstance(group, dict) and isinstance(group.get(key), dict):
                return group[key]
    return None


def _mark_stale_cache(
    snapshot: dict,
    live_required_core_errors: list[dict],
    live_snapshot: dict,
) -> dict:
    cached_at = snapshot.get("cached_at")
    stale_snapshot = dict(snapshot)
    stale_snapshot["status"] = "stale_cache"
    stale_snapshot["error"] = "Required core market data failed; using cached snapshot."
    stale_snapshot["cached_at"] = cached_at
    stale_snapshot["live_required_core_errors"] = live_required_core_errors

    for section in ("market_data", "macro_data", "fx_data", "financial_conditions"):
        section_data = stale_snapshot.get(section)
        if isinstance(section_data, dict):
            stale_snapshot[section] = _mark_stale_section(section_data, cached_at)

    _overlay_live_items(
        stale_snapshot,
        live_snapshot,
        (*IMPORTANT_OPTIONAL_KEYS, *OPTIONAL_MARKET_KEYS, *FINANCIAL_CONDITION_KEYS),
    )
    if isinstance(live_snapshot.get("market_data_package"), dict):
        stale_snapshot["market_data_package"] = live_snapshot["market_data_package"]

    stale_snapshot["diagnostics"] = {
        "required_core_status": _status_by_keys(live_snapshot, REQUIRED_CORE_KEYS),
        "important_optional_status": _status_by_keys(live_snapshot, IMPORTANT_OPTIONAL_KEYS),
        "optional_status": _status_by_keys(live_snapshot, OPTIONAL_MARKET_KEYS),
        "financial_conditions_status": _status_by_keys(live_snapshot, FINANCIAL_CONDITION_KEYS),
        "used_cache": True,
    }

    return stale_snapshot


def _mark_stale_section(section_data: dict, cached_at: str | None) -> dict:
    stale_section = {}
    for key, item in section_data.items():
        if not isinstance(item, dict):
            stale_section[key] = item
            continue

        stale_item = dict(item)
        stale_item.setdefault("source", item.get("source") or "cache")
        stale_item.setdefault("timestamp", item.get("timestamp") or cached_at)
        stale_item.setdefault("error", None)
        stale_item.setdefault("attempted_sources", [])
        if stale_item.get("status") == "ok":
            stale_item["status"] = "stale_cache"
        stale_item["cached_at"] = cached_at
        stale_section[key] = stale_item

    return stale_section


def _overlay_live_items(target_snapshot: dict, live_snapshot: dict, keys: tuple[str, ...]) -> None:
    for key in keys:
        live_section_name, live_item = _find_data_item_with_section(live_snapshot, key)
        if not live_section_name or not isinstance(live_item, dict):
            continue

        target_section = target_snapshot.get(live_section_name)
        if not isinstance(target_section, dict):
            target_section = {}
            target_snapshot[live_section_name] = target_section

        target_section[key] = live_item


def _find_data_item_with_section(snapshot: dict, key: str) -> tuple[str | None, dict | None]:
    for section in ("market_data", "macro_data", "fx_data", "financial_conditions"):
        data = snapshot.get(section)
        if isinstance(data, dict) and isinstance(data.get(key), dict):
            return section, data[key]
    package = snapshot.get("market_data_package")
    if isinstance(package, dict):
        for group_name in (
            "treasury_yields",
            "inflation_indicators",
            "oil_and_energy",
            "existing_financial_conditions",
            "unavailable_or_research_needed",
        ):
            group = package.get(group_name)
            if isinstance(group, dict) and isinstance(group.get(key), dict):
                return f"market_data_package.{group_name}", group[key]
    return None, None


def _attach_diagnostics(
    snapshot: dict,
    required_core_errors: list[dict],
    used_cache: bool,
) -> None:
    snapshot["diagnostics"] = {
        "required_core_status": _status_by_keys(snapshot, REQUIRED_CORE_KEYS),
        "important_optional_status": _status_by_keys(snapshot, IMPORTANT_OPTIONAL_KEYS),
        "optional_status": _status_by_keys(snapshot, OPTIONAL_MARKET_KEYS),
        "financial_conditions_status": _status_by_keys(snapshot, FINANCIAL_CONDITION_KEYS),
        "used_cache": used_cache,
    }
    if required_core_errors:
        snapshot["live_required_core_errors"] = required_core_errors


def _status_by_keys(snapshot: dict, keys: tuple[str, ...]) -> dict:
    statuses = {}
    for key in keys:
        item = _find_data_item(snapshot, key)
        if not isinstance(item, dict):
            statuses[key] = {
                "status": "missing",
                "source": None,
                "value_present": False,
                "error": "Data item missing.",
            }
            continue
        statuses[key] = {
            "status": item.get("status"),
            "source": item.get("source"),
            "value_present": item.get("value") is not None,
            "error": item.get("error"),
        }
    return statuses


def _attach_data_quality(snapshot: dict) -> None:
    config = load_data_source_config("configs/data_sources.yaml")
    data_quality_config = config.get("data_quality", {})
    if not isinstance(data_quality_config, dict):
        data_quality_config = {}

    generated_at = str(snapshot.get("generated_at") or "")
    for section in ("market_data", "macro_data", "fx_data", "financial_conditions"):
        section_data = snapshot.get(section)
        if not isinstance(section_data, dict):
            continue
        for key, item in section_data.items():
            if not isinstance(item, dict):
                continue
            metadata = data_quality_config.get(key, {})
            item["data_quality"] = calculate_freshness(item, metadata, generated_at)
            if section == "financial_conditions":
                item["freshness"] = item["data_quality"].get("freshness_status") or item.get("freshness")

    package = snapshot.get("market_data_package")
    if not isinstance(package, dict):
        return
    for group_name in (
        "treasury_yields",
        "inflation_indicators",
        "oil_and_energy",
        "existing_financial_conditions",
        "unavailable_or_research_needed",
    ):
        group = package.get(group_name)
        if not isinstance(group, dict):
            continue
        for key, item in group.items():
            if not isinstance(item, dict):
                continue
            metadata = data_quality_config.get(key, {})
            item["data_quality"] = calculate_freshness(item, metadata, generated_at)


if __name__ == "__main__":
    main()

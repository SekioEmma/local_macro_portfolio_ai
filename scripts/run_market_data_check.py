from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_providers.market_data_service import FRED_PRIMARY_KEYS, get_core_market_snapshot
from data_providers.cache import load_json_cache, save_json_cache


DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "outputs" / "reports" / "market_snapshot.json"
CACHE_MAX_AGE_SECONDS = 24 * 60 * 60


def main() -> None:
    snapshot = get_core_market_snapshot()
    if not _fred_primary_ok(snapshot):
        cached_snapshot = load_json_cache(
            str(DEFAULT_OUTPUT_PATH),
            max_age_seconds=CACHE_MAX_AGE_SECONDS,
        )
        if cached_snapshot and _fred_primary_ok(cached_snapshot):
            snapshot = _mark_stale_cache(cached_snapshot)
        else:
            snapshot["status"] = "error"
            snapshot["error"] = "FRED primary data failed and no usable 24h cache is available."
    else:
        snapshot["status"] = "ok"
        snapshot["error"] = None

    formatted_json = json.dumps(snapshot, ensure_ascii=False, indent=2)
    print(formatted_json)

    save_json_cache(str(DEFAULT_OUTPUT_PATH), snapshot)


def _fred_primary_ok(snapshot: dict) -> bool:
    for key in FRED_PRIMARY_KEYS:
        item = _find_data_item(snapshot, key)
        if not isinstance(item, dict) or item.get("status") not in {"ok", "stale_cache"}:
            return False
        if item.get("source") != "FRED" and item.get("status") != "stale_cache":
            return False
        if item.get("value") is None:
            return False

    return True


def _find_data_item(snapshot: dict, key: str) -> dict | None:
    for section in ("market_data", "macro_data", "fx_data"):
        data = snapshot.get(section)
        if isinstance(data, dict) and isinstance(data.get(key), dict):
            return data[key]
    return None


def _mark_stale_cache(snapshot: dict) -> dict:
    cached_at = snapshot.get("cached_at")
    stale_snapshot = dict(snapshot)
    stale_snapshot["status"] = "stale_cache"
    stale_snapshot["error"] = "FRED primary data failed; using cached snapshot."
    stale_snapshot["cached_at"] = cached_at

    for section in ("market_data", "macro_data", "fx_data"):
        section_data = stale_snapshot.get(section)
        if isinstance(section_data, dict):
            stale_snapshot[section] = _mark_stale_section(section_data, cached_at)

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


if __name__ == "__main__":
    main()

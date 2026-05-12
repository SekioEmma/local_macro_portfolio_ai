from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_providers.alpha_vantage_history_provider import get_daily_time_series
from data_providers.market_data_service import load_data_source_config
from history.market_history import build_market_history_features


CACHE_DIR = PROJECT_ROOT / "data" / "history" / "market"
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "reports" / "market_history_features.json"
MAX_DEFAULT_REQUESTS = 4


def main() -> None:
    args = _parse_args()
    config = load_data_source_config("configs/data_sources.yaml")
    assets = _historical_assets(config)
    alpha_vantage_settings = _alpha_vantage_settings(config)

    history_by_asset = {}
    request_count = 0
    today = datetime.now().date().isoformat()

    for index, (asset_key, asset_config) in enumerate(assets.items()):
        if index >= MAX_DEFAULT_REQUESTS:
            history_by_asset[asset_key] = {
                "symbol": asset_config.get("symbol"),
                "name": asset_config.get("name"),
                "asset_class": asset_config.get("asset_class"),
                "provider": asset_config.get("provider"),
                "response": {
                    "symbol": asset_config.get("symbol"),
                    "source": asset_config.get("provider"),
                    "status": "error",
                    "error": "Skipped to respect default Alpha Vantage request limit.",
                    "observations": [],
                    "metadata": {},
                    "timestamp": _now_iso(),
                },
            }
            continue

        symbol = str(asset_config.get("symbol") or "").strip()
        provider = str(asset_config.get("provider") or "").strip()
        cache_path = _cache_path(asset_key, symbol, today)
        legacy_cache_path = _legacy_cache_path(asset_key, symbol, today)
        used_cache = False

        if not symbol:
            response = _asset_error(symbol, "historical_market_assets symbol missing")
        elif provider != "alpha_vantage":
            response = _asset_error(symbol, f"Unsupported history provider: {provider}")
        elif not args.force_refresh and (
            cached := _load_success_cache(cache_path, legacy_cache_path)
        ) is not None:
            used_cache = True
            response = cached
        else:
            response, sent_count = _fetch_with_retries(
                symbol=symbol,
                request_count_so_far=request_count,
                settings=alpha_vantage_settings,
            )
            request_count += sent_count
            if response.get("request_sent"):
                _save_cache(cache_path, response)

        history_by_asset[asset_key] = {
            "symbol": symbol,
            "name": asset_config.get("name"),
            "asset_class": asset_config.get("asset_class"),
            "proxy_for": asset_config.get("proxy_for"),
            "provider": provider,
            "cache_path": str(cache_path),
            "used_cache": used_cache,
            "response": response,
        }

    features = build_market_history_features(history_by_asset)
    features["request_count"] = request_count
    features["cache_dir"] = str(CACHE_DIR)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(features, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(_summary(features), ensure_ascii=False, indent=2))


def _historical_assets(config: dict) -> dict:
    assets = config.get("historical_market_assets", {})
    if not isinstance(assets, dict):
        return {}
    return assets


def _cache_path(asset_key: str, symbol: str, today: str) -> Path:
    safe_symbol = _safe_name(symbol)
    return CACHE_DIR / f"{safe_symbol}_{today}.raw.json"


def _legacy_cache_path(asset_key: str, symbol: str, today: str) -> Path:
    safe_asset_key = _safe_name(asset_key)
    safe_symbol = _safe_name(symbol)
    return CACHE_DIR / f"{today}_{safe_asset_key}_{safe_symbol}.raw.json"


def _load_success_cache(*paths: Path) -> dict | None:
    for path in paths:
        if not path.exists():
            continue
        payload = _load_cached_response(path)
        if isinstance(payload, dict) and payload.get("status") == "ok":
            return payload
    return None


def _load_cached_response(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _save_cache(path: Path, response: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(response, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _fetch_with_retries(symbol: str, request_count_so_far: int, settings: dict) -> tuple[dict, int]:
    sent_count = 0
    max_retries = int(settings.get("max_retries", 1))
    request_delay = float(settings.get("request_delay_seconds", 3))
    retry_delay = float(settings.get("retry_delay_seconds", 10))

    response = {}
    for attempt_index in range(max_retries + 1):
        if attempt_index > 0:
            time.sleep(retry_delay)
        elif request_count_so_far + sent_count > 0:
            time.sleep(request_delay)

        response = get_daily_time_series(symbol=symbol, outputsize="compact")
        if response.get("request_sent"):
            sent_count += 1

        if not _should_retry(response) or attempt_index >= max_retries:
            break

    return response, sent_count


def _should_retry(response: dict) -> bool:
    if not isinstance(response, dict) or response.get("status") != "error":
        return False
    error = str(response.get("error") or "").lower()
    retry_terms = (
        "alpha vantage information",
        "alpha vantage note",
        "rate limit",
        "requests should be spread",
        "frequency",
    )
    return any(term in error for term in retry_terms)


def _alpha_vantage_settings(config: dict) -> dict:
    raw_settings = config.get("alpha_vantage", {})
    if not isinstance(raw_settings, dict):
        raw_settings = {}
    return {
        "request_delay_seconds": raw_settings.get("request_delay_seconds", 3),
        "retry_delay_seconds": raw_settings.get("retry_delay_seconds", 10),
        "max_retries": raw_settings.get("max_retries", 1),
    }


def _asset_error(symbol: str, error: str) -> dict:
    return {
        "symbol": symbol,
        "source": "Alpha Vantage",
        "status": "error",
        "error": error,
        "observations": [],
        "metadata": {},
        "timestamp": _now_iso(),
        "request_sent": False,
    }


def _summary(features: dict) -> dict:
    assets = {}
    for asset_key, asset in features.get("assets", {}).items():
        if not isinstance(asset, dict):
            continue
        assets[asset_key] = {
            "symbol": asset.get("symbol"),
            "proxy_for": asset.get("proxy_for"),
            "return_type": asset.get("return_type"),
            "input_status": asset.get("input_status"),
            "latest_date": asset.get("latest_date"),
            "latest_close": asset.get("latest_close"),
            "observation_count": asset.get("observation_count"),
            "status": asset.get("status"),
            "error": asset.get("error"),
        }

    return {
        "generated_at": features.get("generated_at"),
        "request_count": features.get("request_count"),
        "assets": assets,
        "data_limitations": features.get("data_limitations", []),
        "methodology_note": features.get("methodology_note"),
    }


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in str(value).lower()).strip("_")


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch and summarize historical market data.")
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Ignore today's raw cache and request Alpha Vantage again.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()

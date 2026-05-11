from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import fed_provider, fred_provider, yfinance_provider


MARKET_DATA_KEYS = ("sp500", "nasdaq", "nasdaq100", "gold")
MACRO_DATA_KEYS = ("dgs10", "fedfunds", "cpi", "pce", "nonfarm")
FX_DATA_KEYS = ("usd_cny",)
FRED_PRIMARY_KEYS = (
    "sp500",
    "nasdaq",
    "dgs10",
    "fedfunds",
    "cpi",
    "pce",
    "nonfarm",
    "usd_cny",
)


def load_data_source_config(path: str) -> dict:
    config_path = _resolve_path(path)
    raw_text = config_path.read_text(encoding="utf-8")

    try:
        import yaml
    except ImportError:
        config = _load_simple_yaml(raw_text)
    else:
        config = yaml.safe_load(raw_text)

    if not isinstance(config, dict):
        raise ValueError(f"Data source config must contain a mapping: {config_path}")

    return config


def get_core_market_snapshot(config_path: str = "configs/data_sources.yaml") -> dict:
    generated_at = _utc_now()
    _load_project_dotenv()

    config = load_data_source_config(config_path)

    return {
        "market_data": {
            key: get_market_item(key, config)
            for key in MARKET_DATA_KEYS
        },
        "macro_data": {
            key: get_market_item(key, config)
            for key in MACRO_DATA_KEYS
        },
        "fx_data": {
            key: get_market_item(key, config)
            for key in FX_DATA_KEYS
        },
        "official_sources": fed_provider.get_fed_public_sources(),
        "generated_at": generated_at,
    }


def get_market_item(key: str, config: dict) -> dict:
    generated_at = _utc_now()
    attempts: list[dict] = []
    candidates = _provider_candidates(key, config)

    if not candidates:
        return _market_error(
            key=key,
            name=key,
            attempts=[
                {
                    "source": "config",
                    "status": "error",
                    "error": f"No provider candidates configured for {key}",
                    "timestamp": generated_at,
                }
            ],
            timestamp=generated_at,
        )

    result_name = _first_candidate_name(candidates, key)
    asset_type = _first_candidate_asset_type(candidates)

    for candidate in candidates:
        result = _call_provider(candidate)
        attempts.append(_attempt_summary(candidate, result))

        value = _to_float_or_none(result.get("value"))
        if result.get("status") == "ok" and value is not None:
            item = {
                "key": key,
                "name": candidate.get("name") or result_name,
                "asset_type": candidate.get("asset_type") or asset_type,
                "value": value,
                "source": result.get("source") or candidate["provider"],
                "timestamp": result.get("timestamp") or generated_at,
                "status": "ok",
                "error": None,
                "attempted_sources": attempts,
            }
            if result.get("series_id") or candidate.get("series_id"):
                item["series_id"] = result.get("series_id") or candidate.get("series_id")
            if result.get("symbol") or candidate.get("symbol"):
                item["symbol"] = result.get("symbol") or candidate.get("symbol")
            if result.get("observation_date"):
                item["observation_date"] = result["observation_date"]
            if candidate.get("notes"):
                item["notes"] = candidate["notes"]
            return item

    return _market_error(
        key=key,
        name=result_name,
        attempts=attempts,
        timestamp=generated_at,
        asset_type=asset_type,
    )


def _provider_candidates(key: str, config: dict) -> list[dict]:
    if key in {"sp500", "nasdaq", "dgs10", "fedfunds", "cpi", "pce", "nonfarm"}:
        return [_fred_candidate(key, config)]

    if key == "usd_cny":
        return [
            _fred_candidate(
                key,
                config,
                notes="FRED DEXCHUS reports Chinese yuan per 1 U.S. dollar (CNY per USD).",
            ),
            _yfinance_candidate(
                key,
                config,
                notes="Yahoo CNY=X is treated as USD/CNY, CNY per 1 USD.",
            ),
        ]

    if key in {"nasdaq100", "gold"}:
        return [_yfinance_candidate(key, config)]

    return []


def _fred_candidate(key: str, config: dict, notes: str | None = None) -> dict:
    fred_series = _optional_mapping(config, "fred_series")
    series_config = fred_series.get(key)

    if not isinstance(series_config, dict):
        return {
            "provider": "config",
            "source": "config",
            "name": key,
            "asset_type": None,
            "error": f"fred_series.{key} not configured",
        }

    series_id = series_config.get("series_id")
    if not series_id:
        return {
            "provider": "config",
            "source": "config",
            "name": series_config.get("name") or key,
            "asset_type": series_config.get("asset_type"),
            "error": f"fred_series.{key}.series_id not configured",
        }

    candidate = {
        "provider": "fred",
        "series_id": str(series_id),
        "name": series_config.get("name") or key,
        "asset_type": series_config.get("asset_type"),
    }
    if notes:
        candidate["notes"] = notes
    return candidate


def _yfinance_candidate(
    key: str,
    config: dict,
    notes: str | None = None,
) -> dict:
    market_symbols = _optional_mapping(config, "market_symbols")
    symbol_config = market_symbols.get(key)

    if not isinstance(symbol_config, dict):
        return {
            "provider": "config",
            "source": "config",
            "name": key,
            "asset_type": None,
            "error": f"market_symbols.{key} not configured",
        }

    symbol = symbol_config.get("symbol")
    if not symbol:
        return {
            "provider": "config",
            "source": "config",
            "name": symbol_config.get("name") or key,
            "asset_type": symbol_config.get("asset_type"),
            "error": f"market_symbols.{key}.symbol not configured",
        }

    candidate = {
        "provider": "yfinance",
        "symbol": str(symbol),
        "name": symbol_config.get("name") or key,
        "asset_type": symbol_config.get("asset_type"),
    }
    if notes:
        candidate["notes"] = notes
    return candidate


def _call_provider(candidate: dict) -> dict:
    provider = candidate["provider"]

    if provider == "fred":
        return fred_provider.get_fred_latest(candidate["series_id"])

    if provider == "yfinance":
        return yfinance_provider.get_latest_price(candidate["symbol"])

    return {
        "value": None,
        "source": candidate.get("source") or provider,
        "timestamp": _utc_now(),
        "status": "error",
        "error": candidate.get("error") or f"Unsupported provider: {provider}",
    }


def _attempt_summary(candidate: dict, result: dict) -> dict:
    summary = {
        "source": result.get("source") or candidate.get("source") or candidate["provider"],
        "status": result.get("status", "error"),
        "error": result.get("error"),
        "timestamp": result.get("timestamp") or _utc_now(),
    }

    if candidate.get("series_id") or result.get("series_id"):
        summary["series_id"] = result.get("series_id") or candidate.get("series_id")
    if candidate.get("symbol") or result.get("symbol"):
        summary["symbol"] = result.get("symbol") or candidate.get("symbol")
    if result.get("observation_date"):
        summary["observation_date"] = result["observation_date"]
    if candidate.get("notes"):
        summary["notes"] = candidate["notes"]

    return summary


def _market_error(
    key: str,
    name: str,
    attempts: list[dict],
    timestamp: str,
    asset_type: str | None = None,
) -> dict:
    errors = [
        f"{attempt.get('source')}: {attempt.get('error')}"
        for attempt in attempts
        if attempt.get("error")
    ]
    error = "; ".join(errors) or "All configured market data sources failed"

    return {
        "key": key,
        "name": name,
        "asset_type": asset_type,
        "value": None,
        "source": "market_data_service",
        "timestamp": timestamp,
        "status": "error",
        "error": error,
        "attempted_sources": attempts,
    }


def _first_candidate_name(candidates: list[dict], fallback: str) -> str:
    for candidate in candidates:
        if candidate.get("name"):
            return str(candidate["name"])
    return fallback


def _first_candidate_asset_type(candidates: list[dict]) -> str | None:
    for candidate in candidates:
        if candidate.get("asset_type"):
            return str(candidate["asset_type"])
    return None


def _resolve_path(path: str) -> Path:
    requested_path = Path(path)
    if requested_path.is_absolute():
        return requested_path

    if requested_path.exists():
        return requested_path

    return _project_root() / requested_path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_project_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    load_dotenv(_project_root() / ".env")
    load_dotenv()


def _optional_mapping(source: dict, key: str) -> dict:
    value = source.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"data_sources.yaml must contain mapping: {key}")
    return value


def _to_float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_simple_yaml(raw_text: str) -> dict:
    lines = raw_text.splitlines()
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]

    for index, line in enumerate(lines):
        if not line.strip() or line.lstrip().startswith("#"):
            continue

        indent = len(line) - len(line.lstrip(" "))
        content = line.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()

        parent = stack[-1][1]
        if content.startswith("- "):
            if not isinstance(parent, list):
                raise ValueError(f"Unsupported YAML list item on line {index + 1}.")
            parent.append(_parse_simple_yaml_scalar(content[2:].strip()))
            continue

        if ":" not in content:
            raise ValueError(f"Unsupported YAML syntax on line {index + 1}.")

        key, value = content.split(":", 1)
        key = _parse_simple_yaml_key(key.strip())
        value = value.strip()

        if value:
            parent[key] = _parse_simple_yaml_scalar(value)
            continue

        child = [] if _next_content_is_list(lines, index, indent) else {}
        parent[key] = child
        stack.append((indent, child))

    return root


def _next_content_is_list(lines: list[str], current_index: int, current_indent: int) -> bool:
    for line in lines[current_index + 1 :]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        return indent > current_indent and line.strip().startswith("- ")
    return False


def _parse_simple_yaml_key(value: str) -> str:
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def _parse_simple_yaml_scalar(value: str) -> Any:
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]

    lower_value = value.lower()
    if lower_value == "true":
        return True
    if lower_value == "false":
        return False
    if lower_value in {"null", "none", "~"}:
        return None

    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value

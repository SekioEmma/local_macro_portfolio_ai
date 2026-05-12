from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


SENSITIVE_QUERY_RE = re.compile(
    r"(?i)(api[_-]?key|apikey|token|access_token|secret)=([^&\s\"')]+)"
)
CORE_CONTEXT_FIELDS = [
    "context_pack_type",
    "generated_at",
    "confirmed_facts",
    "rule_based_assessments",
    "historical_context",
    "portfolio_context",
    "data_quality",
    "data_limitations",
    "forbidden_model_behaviors",
]
CORE_TEMPERATURE_KEYS = [
    "equity_temperature",
    "rate_pressure",
    "inflation_pressure",
    "labor_market",
    "fx_pressure",
]
DEFAULT_CONTEXT_POLICY = {
    "allow_degraded_context": False,
    "max_data_limitations_for_model_call": 20,
    "allow_sample_fallback": True,
}


def load_text(path: str) -> dict[str, Any]:
    text_path = Path(path)
    if not text_path.exists():
        return {
            "status": "error",
            "path": str(text_path),
            "content": "",
            "error": "File not found",
        }

    try:
        content = text_path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        return {
            "status": "error",
            "path": str(text_path),
            "content": "",
            "error": f"Could not read file: {exc}",
        }
    except UnicodeDecodeError as exc:
        return {
            "status": "error",
            "path": str(text_path),
            "content": "",
            "error": f"Could not decode UTF-8 text: {exc}",
        }

    return {
        "status": "ok",
        "path": str(text_path),
        "content": _redact_sensitive(content),
        "error": None,
    }


def load_json(path: str) -> dict[str, Any]:
    json_path = Path(path)
    if not json_path.exists():
        return {
            "status": "error",
            "path": str(json_path),
            "data": {},
            "error": "File not found",
        }

    try:
        data = json.loads(json_path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        return {
            "status": "error",
            "path": str(json_path),
            "data": {},
            "error": f"Could not read file: {exc}",
        }
    except UnicodeDecodeError as exc:
        return {
            "status": "error",
            "path": str(json_path),
            "data": {},
            "error": f"Could not decode UTF-8 JSON: {exc}",
        }
    except json.JSONDecodeError as exc:
        return {
            "status": "error",
            "path": str(json_path),
            "data": {},
            "error": f"Invalid JSON: {exc}",
        }

    if not isinstance(data, dict):
        return {
            "status": "error",
            "path": str(json_path),
            "data": {},
            "error": "JSON root must be an object",
        }

    return {
        "status": "ok",
        "path": str(json_path),
        "data": _redact_sensitive(data),
        "error": None,
    }


def load_context_pack(context_md_path: str, context_json_path: str) -> dict[str, Any]:
    md_result = load_text(context_md_path)
    json_result = load_json(context_json_path)

    data_limitations = []
    if md_result.get("status") != "ok":
        data_limitations.append(
            _redact_sensitive(f"llm_context_pack.md: {md_result.get('error') or 'unavailable'}")
        )
    if json_result.get("status") != "ok":
        data_limitations.append(
            _redact_sensitive(f"llm_context_pack.json: {json_result.get('error') or 'unavailable'}")
        )

    context_json = json_result.get("data") if json_result.get("status") == "ok" else {}
    if isinstance(context_json, dict):
        pack_limitations = context_json.get("data_limitations", [])
        if isinstance(pack_limitations, list):
            data_limitations.extend(_redact_sensitive(str(item)) for item in pack_limitations if item)

    limitations = _dedupe_strings(data_limitations)
    status = "ok" if md_result.get("status") == "ok" and json_result.get("status") == "ok" else "error"

    return {
        "status": status,
        "context_md": md_result.get("content", ""),
        "context_json": context_json if isinstance(context_json, dict) else {},
        "data_limitations": limitations,
        "compressed_data_limitations": summarize_data_limitations(limitations),
        "context_health": validate_context_health(context_json if isinstance(context_json, dict) else {}),
        "errors": [
            {
                "path": result.get("path"),
                "error": result.get("error"),
            }
            for result in (md_result, json_result)
            if result.get("status") != "ok"
        ],
        "source_paths": {
            "context_md": str(Path(context_md_path)),
            "context_json": str(Path(context_json_path)),
        },
    }


def validate_context_health(
    context_json: dict[str, Any],
    context_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = {**DEFAULT_CONTEXT_POLICY, **(context_policy or {})}
    warnings: list[str] = []
    errors: list[str] = []
    degraded_reasons: list[str] = []

    if not isinstance(context_json, dict) or not context_json:
        errors.append("llm_context_pack.json is missing or empty.")
        return {
            "status": "error",
            "warnings": warnings,
            "errors": errors,
            "should_allow_model_call": False,
        }

    missing_fields = [field for field in CORE_CONTEXT_FIELDS if field not in context_json]
    if missing_fields:
        errors.append(f"llm_context_pack.json missing required fields: {', '.join(missing_fields)}")

    data_quality = context_json.get("data_quality", {})
    if not isinstance(data_quality, dict):
        errors.append("data_quality must be an object.")
        data_quality = {}

    market_snapshot_status = data_quality.get("market_snapshot_status")
    if market_snapshot_status != "ok":
        degraded_reasons.append(f"market_snapshot.status is {market_snapshot_status or 'missing'}, not ok.")

    if data_quality.get("used_cache") is True:
        degraded_reasons.append("market_snapshot.diagnostics.used_cache is true.")

    unknown_temperature_keys = _unknown_temperature_keys(context_json)
    if unknown_temperature_keys:
        degraded_reasons.append(
            "market_temperature.temperature_assessment has unknown core items: "
            + ", ".join(unknown_temperature_keys)
        )

    holdings_source = _find_holdings_source(context_json)
    if holdings_source.get("mode") == "sample_fallback":
        warnings.append("holdings_source.mode is sample_fallback; this is not real account data.")
        if not policy.get("allow_sample_fallback", True):
            degraded_reasons.append("sample_fallback is disabled by context_policy.")

    limitations = context_json.get("data_limitations", [])
    limitation_count = len(limitations) if isinstance(limitations, list) else 0
    max_limitations = _as_int(
        policy.get("max_data_limitations_for_model_call"),
        DEFAULT_CONTEXT_POLICY["max_data_limitations_for_model_call"],
    )
    if limitation_count > max_limitations:
        degraded_reasons.append(
            f"data_limitation_count is {limitation_count}, above threshold {max_limitations}."
        )

    if errors:
        status = "error"
    elif degraded_reasons:
        status = "degraded"
    else:
        status = "ok"

    allow_degraded = bool(policy.get("allow_degraded_context", False))
    should_allow_model_call = status == "ok" or (status == "degraded" and allow_degraded)

    return {
        "status": status,
        "warnings": _dedupe_strings([*warnings, *degraded_reasons]),
        "errors": errors,
        "should_allow_model_call": should_allow_model_call,
    }


def summarize_data_limitations(limitations: list[str]) -> list[str]:
    if not limitations:
        return []

    buckets: dict[str, list[str]] = {
        "sample": [],
        "stale_cache": [],
        "fred_connection": [],
        "alpha_vantage_connection": [],
        "temperature_insufficient": [],
        "provider_misc": [],
        "other": [],
    }

    for limitation in limitations:
        text = str(limitation)
        lower = text.lower()
        if "sample_fallback" in lower or "sample fallback" in lower or "current_holdings.csv" in lower:
            buckets["sample"].append(text)
        elif "stale_cache" in lower or "stale cache" in lower or "used stale cache" in lower:
            buckets["stale_cache"].append(text)
        elif "stlouisfed.org" in lower or "fred " in lower or "fred:" in lower:
            buckets["fred_connection"].append(text)
        elif "alphavantage.co" in lower or "alpha vantage" in lower:
            buckets["alpha_vantage_connection"].append(text)
        elif "market_temperature:" in lower and (
            "insufficient_data" in lower or "unknown" in lower or "unavailable" in lower
        ):
            buckets["temperature_insufficient"].append(text)
        elif "yfinance" in lower or "manual market data" in lower:
            buckets["provider_misc"].append(text)
        else:
            buckets["other"].append(text)

    summarized: list[str] = []
    summarized.extend(_summarize_named_bucket("Sample holdings fallback", buckets["sample"], keep_examples=2))
    summarized.extend(_summarize_named_bucket("Stale cache", buckets["stale_cache"], keep_examples=2))
    summarized.extend(
        _summarize_named_bucket("FRED connection failures", buckets["fred_connection"], keep_examples=1)
    )
    summarized.extend(
        _summarize_named_bucket(
            "Alpha Vantage connection failures",
            buckets["alpha_vantage_connection"],
            keep_examples=1,
        )
    )
    summarized.extend(
        _summarize_named_bucket(
            "Market temperature insufficient data or unknown items",
            buckets["temperature_insufficient"],
            keep_examples=2,
        )
    )
    summarized.extend(_summarize_named_bucket("Fallback provider issues", buckets["provider_misc"], keep_examples=2))

    for item in buckets["other"]:
        summarized.append(_truncate(item, 280))
        if len(summarized) >= 12:
            break

    return summarized[:12]


def _dedupe_strings(items: list[str]) -> list[str]:
    result = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _unknown_temperature_keys(context_json: dict[str, Any]) -> list[str]:
    market_temperature = (
        context_json.get("rule_based_assessments", {})
        .get("market_temperature", {})
    )
    if not isinstance(market_temperature, dict):
        return CORE_TEMPERATURE_KEYS

    unknown = []
    for key in CORE_TEMPERATURE_KEYS:
        value = market_temperature.get(key)
        if _is_unknown_temperature_value(value):
            unknown.append(key)
    return unknown


def _is_unknown_temperature_value(value: Any) -> bool:
    if isinstance(value, dict):
        return value.get("level") == "unknown" or value.get("status") == "unknown"
    return value in {None, "", "unknown"}


def _find_holdings_source(context_json: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        context_json.get("portfolio_context", {}).get("holdings_source", {}),
        context_json.get("confirmed_facts", {}).get("portfolio", {}).get("holdings_source", {}),
        context_json.get("data_quality", {}).get("portfolio_holdings_source", {}),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate:
            return candidate
    return {}


def _summarize_named_bucket(name: str, items: list[str], keep_examples: int) -> list[str]:
    if not items:
        return []

    examples = [_truncate(item, 180) for item in items[:keep_examples]]
    summary = f"{name}: {len(items)} related limitation(s)."
    if examples:
        summary += " Examples: " + " | ".join(examples)
    return [_truncate(summary, 280)]


def _truncate(text: str, max_chars: int) -> str:
    clean = " ".join(str(text).split())
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 3].rstrip() + "..."


def _redact_sensitive(value: Any) -> Any:
    if isinstance(value, str):
        return SENSITIVE_QUERY_RE.sub(r"\1=[REDACTED]", value)
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if _looks_sensitive_key(str(key)):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = _redact_sensitive(item)
        return redacted
    return value


def _looks_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized in {"api_key", "apikey", "token", "access_token", "secret"}


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

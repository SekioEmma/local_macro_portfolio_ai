from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_providers.fred_provider import get_fred_series
from data_providers.market_data_service import load_data_source_config
from history.macro_regime_history import (
    build_macro_regime_history_report,
    normalize_fred_observations,
)


CACHE_DIR = PROJECT_ROOT / "data" / "history" / "fred"
JSON_OUTPUT_PATH = PROJECT_ROOT / "outputs" / "reports" / "macro_regime_history.json"
MD_OUTPUT_PATH = PROJECT_ROOT / "outputs" / "reports" / "macro_regime_history.md"
DEFAULT_LIMIT = 10000


def main() -> None:
    args = _parse_args()
    config = load_data_source_config("configs/data_sources.yaml")
    macro_series = _macro_regime_series(config)
    crisis_windows = _crisis_windows(config)

    series_by_key = {}
    for key, series_config in macro_series.items():
        series_id = str(series_config.get("series_id") or "").strip()
        if not series_id:
            response = _series_error(series_id, f"macro_regime_series.{key}.series_id missing")
        else:
            cache_path = _cache_path(series_id)
            if cache_path.exists() and _cache_is_today(cache_path) and not args.force_refresh:
                response = _load_cache(cache_path) or _series_error(
                    series_id,
                    f"FRED cache could not be read: {cache_path}",
                )
            else:
                response = get_fred_series(series_id, limit=args.limit)
                if response.get("status") == "ok":
                    _save_cache(cache_path, response)

        series_by_key[key] = {
            "series_id": series_id,
            "name": series_config.get("name"),
            "frequency": series_config.get("frequency"),
            "role": series_config.get("role"),
            "source": "FRED",
            "response": response,
            "observations": normalize_fred_observations(response),
        }

    generated_at = _utc_now()
    report = build_macro_regime_history_report(series_by_key, crisis_windows, generated_at)

    JSON_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUTPUT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    MD_OUTPUT_PATH.write_text(render_markdown(report), encoding="utf-8")

    print(json.dumps(_summary(report), ensure_ascii=False, indent=2))


def render_markdown(report: dict) -> str:
    current = report.get("current_regime_snapshot", {})
    classification = current.get("regime_classification", {})
    crisis = report.get("crisis_window_summary", {})
    similar = report.get("similar_historical_windows", {})

    lines = [
        "# Macro Regime History Report",
        "",
        f"Generated at: {_display(report.get('generated_at'))}",
        "",
        "## Current Regime Snapshot",
        "",
        _markdown_table(
            ["Metric", "Value"],
            [
                ["End date", current.get("end_date")],
                ["Regime label", classification.get("regime_label")],
                ["Confidence", classification.get("confidence")],
                ["Methodology", classification.get("methodology_note")],
            ],
        ),
        "",
        "## Crisis Windows",
        "",
        _crisis_table(crisis),
        "",
        "## Similar Historical Windows",
        "",
        _similar_windows_section(similar),
        "",
        "## Data Limitations",
        "",
        _bullet_list(report.get("data_limitations", []), "No material data limitations recorded."),
        "",
        "## Methodology",
        "",
        _display(report.get("methodology_note")),
        "",
        "Historical next-period returns shown here are historical outcomes only, not forecasts.",
        "",
    ]
    return "\n".join(lines)


def _crisis_table(crisis: dict) -> str:
    rows = []
    for key, item in crisis.items():
        if not isinstance(item, dict):
            continue
        sp500_return = item.get("equity", {}).get("sp500_return", {})
        sp500_drawdown = item.get("equity", {}).get("sp500_drawdown", {})
        regime = item.get("regime_classification", {})
        rows.append(
            [
                key,
                item.get("name"),
                item.get("start"),
                _window_end_display(item),
                _format_status_metric(sp500_return, "return_pct"),
                _format_status_metric(sp500_drawdown, "max_drawdown_pct"),
                regime.get("regime_label"),
            ]
        )
    return _markdown_table(
        ["Key", "Name", "Start", "End", "S&P 500 Price Return", "Max Drawdown", "Regime"],
        rows,
    )


def _similar_windows_section(similar: dict) -> str:
    fully_observed = similar.get("fully_observed_matches", []) if isinstance(similar, dict) else []
    recent_incomplete = similar.get("recent_incomplete_matches", []) if isinstance(similar, dict) else []
    lines = [
        f"Selection note: {_display(similar.get('selection_note') if isinstance(similar, dict) else None)}",
        "",
        "### Fully Observed Historical Matches",
        "",
        _similar_windows_table(fully_observed),
        "",
        "### Recent Similar Windows With Incomplete Outcomes",
        "",
    ]
    if recent_incomplete:
        lines.append("Historical outcome unavailable because window is too recent.")
        lines.append("")
    lines.append(_similar_windows_table(recent_incomplete))
    return "\n".join(lines)


def _similar_windows_table(matches: list[dict]) -> str:
    if not matches:
        return "No similar historical windows found with the first-version coarse rules."

    rows = []
    for item in matches:
        rows.append(
            [
                item.get("window_start"),
                item.get("window_end"),
                item.get("similarity_score"),
                ", ".join(item.get("matched_buckets", item.get("similarity_reasons", []))),
                ", ".join(item.get("missing_buckets", [])),
                _availability_display(item.get("outcome_availability", {}).get("next_3m")),
                _availability_display(item.get("outcome_availability", {}).get("next_12m")),
                _format_status_metric(item.get("next_3m_sp500_return", {}), "return_pct"),
                _format_status_metric(item.get("next_12m_sp500_return", {}), "return_pct"),
                item.get("notes"),
            ]
        )
    return _markdown_table(
        [
            "Window Start",
            "Window End",
            "Score",
            "Matched Buckets",
            "Missing Buckets",
            "3M Outcome",
            "12M Outcome",
            "Next 3M S&P 500",
            "Next 12M S&P 500",
            "Notes",
        ],
        rows,
    )


def _summary(report: dict) -> dict:
    current = report.get("current_regime_snapshot", {})
    similar = report.get("similar_historical_windows", {})
    return {
        "report_type": report.get("report_type"),
        "generated_at": report.get("generated_at"),
        "current_regime_label": current.get("regime_classification", {}).get("regime_label"),
        "crisis_windows": list(report.get("crisis_window_summary", {}).keys()),
        "fully_observed_similar_window_count": len(similar.get("fully_observed_matches", [])) if isinstance(similar, dict) else 0,
        "recent_incomplete_similar_window_count": len(similar.get("recent_incomplete_matches", [])) if isinstance(similar, dict) else 0,
        "data_limitations": report.get("data_limitations", []),
        "methodology_note": report.get("methodology_note"),
    }


def _macro_regime_series(config: dict) -> dict:
    value = config.get("macro_regime_series", {})
    return value if isinstance(value, dict) else {}


def _crisis_windows(config: dict) -> dict:
    value = config.get("crisis_windows", {})
    return value if isinstance(value, dict) else {}


def _cache_path(series_id: str) -> Path:
    return CACHE_DIR / f"{_safe_name(series_id)}.raw.json"


def _load_cache(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _save_cache(path: Path, response: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(response)
    payload["cached_at"] = _utc_now()
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _cache_is_today(path: Path) -> bool:
    modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return modified_at.date() == datetime.now(timezone.utc).date()


def _series_error(series_id: str, error: str) -> dict:
    return {
        "series_id": series_id,
        "limit": DEFAULT_LIMIT,
        "data": [],
        "source": "FRED",
        "timestamp": _utc_now(),
        "status": "error",
        "error": error,
    }


def _markdown_table(headers: list[str], rows: list[list[object]]) -> str:
    header_line = "| " + " | ".join(_escape_cell(header) for header in headers) + " |"
    divider = "| " + " | ".join("---" for _ in headers) + " |"
    row_lines = [
        "| " + " | ".join(_escape_cell(value) for value in row) + " |"
        for row in rows
    ]
    return "\n".join([header_line, divider, *row_lines])


def _bullet_list(items: list[str], empty_text: str) -> str:
    if not items:
        return empty_text
    return "\n".join(f"- {_escape_inline(item)}" for item in items)


def _window_end_display(item: dict) -> str:
    effective_end = item.get("effective_end") or item.get("end")
    configured_end = item.get("configured_end")
    if item.get("ongoing") and configured_end:
        return f"{effective_end} (ongoing; configured end {configured_end})"
    return _display(effective_end)


def _escape_cell(value: object) -> str:
    text = _display(value)
    text = text.replace("\r", " ").replace("\n", " ")
    text = text.replace("|", "\\|")
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    if len(text) > 180:
        text = text[:177].rstrip() + "..."
    return text


def _format_pct(value: object) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return str(value)


def _format_status_metric(metric: dict, value_key: str) -> str:
    if not isinstance(metric, dict):
        return "N/A"
    if metric.get("status") != "ok":
        status = metric.get("status") or "unknown"
        error = metric.get("error") or "No error detail provided."
        return f"{status}: {error}"
    return _format_pct(metric.get(value_key))


def _availability_display(value: object) -> str:
    if value == "ok":
        return "ok"
    if value == "insufficient_data":
        return "insufficient_data"
    return "unknown"


def _display(value: object) -> str:
    if value is None or value == "":
        return "N/A"
    return str(value)


def _escape_inline(value: object) -> str:
    text = _display(value)
    text = text.replace("\r", " ").replace("\n", " ")
    text = text.replace("|", "\\|")
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    return text


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in str(value).lower()).strip("_")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build FRED macro regime history report.")
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Ignore today's FRED raw cache and refresh all configured series.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="Maximum observations per FRED series.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()

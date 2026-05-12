from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from statistics import mean
from typing import Any


METHODOLOGY_NOTE = "Historical regime analysis is descriptive, not a forecast."
CLASSIFICATION_NOTE = "Rule-based historical classification, not a forecast."
HISTORICAL_OUTCOME_NOTE = "Historical outcome only, not a forecast."


def normalize_fred_observations(response: dict) -> list[dict]:
    if not isinstance(response, dict):
        return []

    raw_observations = response.get("data") or response.get("observations") or []
    if not isinstance(raw_observations, list):
        return []

    observations = []
    for observation in raw_observations:
        if not isinstance(observation, dict):
            continue
        observation_date = observation.get("date") or observation.get("observation_date")
        value = _to_float_or_none(observation.get("value"))
        if not observation_date or value is None:
            continue
        if _parse_date(observation_date) is None:
            continue
        observations.append({"date": str(observation_date), "value": value})

    observations.sort(key=lambda item: item["date"])
    return observations


def calculate_index_return(observations: list[dict], start_date: str, end_date: str) -> dict:
    start = _first_on_or_after(observations, start_date)
    end = _last_on_or_before(observations, end_date)
    if start is None or end is None or start["date"] > end["date"]:
        return _insufficient("No valid start/end observations in window.")
    if start["value"] == 0:
        return _insufficient("Start value is zero.")

    return {
        "start_date": start["date"],
        "end_date": end["date"],
        "start_value": start["value"],
        "end_value": end["value"],
        "return_pct": (end["value"] / start["value"] - 1) * 100,
        "status": "ok",
        "error": None,
    }


def calculate_drawdown(observations: list[dict], start_date: str, end_date: str) -> dict:
    window = _window(observations, start_date, end_date)
    if len(window) < 2:
        return {
            "max_drawdown_pct": None,
            "peak_date": None,
            "trough_date": None,
            "status": "insufficient_data",
            "error": "Need at least two observations in window.",
        }

    peak_value = window[0]["value"]
    peak_date = window[0]["date"]
    max_drawdown = 0.0
    max_peak_date = peak_date
    trough_date = peak_date

    for observation in window:
        if observation["value"] > peak_value:
            peak_value = observation["value"]
            peak_date = observation["date"]
        if peak_value == 0:
            continue
        drawdown = observation["value"] / peak_value - 1
        if drawdown < max_drawdown:
            max_drawdown = drawdown
            max_peak_date = peak_date
            trough_date = observation["date"]

    return {
        "max_drawdown_pct": max_drawdown * 100,
        "peak_date": max_peak_date,
        "trough_date": trough_date,
        "status": "ok",
        "error": None,
    }


def calculate_rate_summary(observations: list[dict], start_date: str, end_date: str) -> dict:
    window = _window(observations, start_date, end_date)
    if not window:
        return _summary_insufficient("No rate observations in window.")

    values = [item["value"] for item in window]
    return {
        "start_date": window[0]["date"],
        "end_date": window[-1]["date"],
        "start_value": window[0]["value"],
        "end_value": window[-1]["value"],
        "min_value": min(values),
        "max_value": max(values),
        "average_value": mean(values),
        "change_pp": window[-1]["value"] - window[0]["value"],
        "unit": "percentage_points",
        "status": "ok",
        "error": None,
    }


def calculate_inflation_yoy_series(cpi_or_pce_observations: list[dict]) -> list[dict]:
    observations = sorted(cpi_or_pce_observations, key=lambda item: item["date"])
    yoy_series = []
    for observation in observations:
        current_date = _parse_date(observation["date"])
        if current_date is None:
            continue
        target = _add_months(current_date, -12)
        previous = _nearest_same_month_or_before(observations, target)
        if previous is None or previous["value"] == 0:
            continue
        yoy_series.append(
            {
                "date": observation["date"],
                "yoy_pct": (observation["value"] / previous["value"] - 1) * 100,
            }
        )
    return yoy_series


def summarize_inflation_window(yoy_series: list[dict], start_date: str, end_date: str) -> dict:
    window = [
        item
        for item in yoy_series
        if start_date <= item.get("date", "") <= end_date
    ]
    if not window:
        return _summary_insufficient("No YoY inflation observations in window.")

    values = [item["yoy_pct"] for item in window]
    return {
        "start_date": window[0]["date"],
        "end_date": window[-1]["date"],
        "start_yoy": window[0]["yoy_pct"],
        "end_yoy": window[-1]["yoy_pct"],
        "max_yoy": max(values),
        "average_yoy": mean(values),
        "change_pp": window[-1]["yoy_pct"] - window[0]["yoy_pct"],
        "status": "ok",
        "error": None,
    }


def summarize_labor_window(nonfarm_observations: list[dict], start_date: str, end_date: str) -> dict:
    window = _window(nonfarm_observations, start_date, end_date)
    if not window:
        return _summary_insufficient("No labor market observations in window.")
    if window[0]["value"] == 0:
        return _summary_insufficient("Start labor market value is zero.")

    values = [item["value"] for item in window]
    return {
        "start_date": window[0]["date"],
        "end_date": window[-1]["date"],
        "start_value": window[0]["value"],
        "end_value": window[-1]["value"],
        "absolute_change": window[-1]["value"] - window[0]["value"],
        "percent_change": (window[-1]["value"] / window[0]["value"] - 1) * 100,
        "min_value": min(values),
        "max_value": max(values),
        "status": "ok",
        "error": None,
    }


def classify_regime(snapshot: dict) -> dict:
    drivers = []
    equity_metrics = _equity_metrics(snapshot)
    equity_returns = [
        item for item in equity_metrics if item["metric_type"] == "return"
    ]
    equity_drawdowns = [
        item for item in equity_metrics if item["metric_type"] == "drawdown"
    ]
    current_momentum = [
        item
        for item in equity_returns
        if "_1m_" in item["name"] or "_3m_" in item["name"]
    ]

    worst_equity_return = _min_metric(equity_returns)
    worst_equity_drawdown = _min_metric(equity_drawdowns)
    strongest_current_momentum = _max_metric(current_momentum)
    strongest_current_3m = _max_metric(
        [item for item in current_momentum if "_3m_" in item["name"]]
    )
    strongest_positive_equity = strongest_current_momentum or _max_metric(equity_returns)
    strongest_positive_3m_or_window = strongest_current_3m or strongest_positive_equity

    dgs10_latest = _extract_metric(snapshot, ("rates", "dgs10", "end_value"))
    dgs10_change = _extract_metric(snapshot, ("rates", "dgs10", "change_pp"))
    fedfunds_change = _extract_metric(snapshot, ("rates", "fedfunds", "change_pp"))
    labor_change = _extract_metric(snapshot, ("labor_market", "percent_change"))

    cpi_yoy = _extract_metric(snapshot, ("inflation", "cpi_yoy", "end_yoy"))
    pce_yoy = _extract_metric(snapshot, ("inflation", "pce_yoy", "end_yoy"))
    inflation_yoy = max([value for value in (cpi_yoy, pce_yoy) if value is not None], default=None)
    rate_changes = [value for value in (dgs10_change, fedfunds_change) if value is not None]

    label = "neutral_or_mixed"
    confidence = "low"

    severe_equity_stress = (
        (worst_equity_return is not None and worst_equity_return["value"] <= -30)
        or (worst_equity_drawdown is not None and worst_equity_drawdown["value"] <= -30)
    )
    if severe_equity_stress and labor_change is not None and labor_change < -1:
        label = "financial_crisis_or_recession_risk"
        if worst_equity_return is not None:
            drivers.append(
                f"{worst_equity_return['name']} was {worst_equity_return['value']:.2f}%."
            )
        if worst_equity_drawdown is not None:
            drivers.append(
                f"{worst_equity_drawdown['name']} was {worst_equity_drawdown['value']:.2f}%."
            )
        drivers.append(f"Labor market percent change was {labor_change:.2f}%.")
        if any(change <= -0.5 for change in rate_changes):
            drivers.append("DGS10 or fed funds moved materially lower during the window.")
        confidence = "medium"

    elif (
        worst_equity_drawdown is not None
        and worst_equity_drawdown["value"] <= -20
        and any(change <= -0.5 for change in rate_changes)
    ):
        label = "growth_scare_or_recession_risk"
        drivers.append(
            f"{worst_equity_drawdown['name']} was {worst_equity_drawdown['value']:.2f}%."
        )
        drivers.append("DGS10 or fed funds moved materially lower during the window.")
        confidence = "medium"

    elif inflation_yoy is not None and inflation_yoy >= 4 and any(change > 0 for change in rate_changes):
        label = "inflation_rate_shock"
        drivers.append(f"Inflation YoY reached {inflation_yoy:.2f}%.")
        drivers.append("DGS10 or fed funds moved higher during the window.")
        confidence = "medium"

    elif (
        strongest_positive_equity is not None
        and strongest_positive_equity["value"] > 8
        and dgs10_latest is not None
        and dgs10_latest >= 4
        and inflation_yoy is not None
        and inflation_yoy >= 3
    ):
        label = "warm_but_macro_sensitive"
        drivers.append(
            f"{strongest_positive_equity['name']} was {strongest_positive_equity['value']:.2f}%."
        )
        drivers.append(f"DGS10 ended at {dgs10_latest:.2f}%.")
        drivers.append(f"Inflation YoY was {inflation_yoy:.2f}%.")
        confidence = "medium"

    elif (
        strongest_positive_3m_or_window is not None
        and strongest_positive_3m_or_window["value"] > 8
        and dgs10_latest is not None
        and dgs10_latest >= 4
    ):
        label = "warm_but_rate_sensitive"
        drivers.append(
            f"{strongest_positive_3m_or_window['name']} was {strongest_positive_3m_or_window['value']:.2f}%."
        )
        drivers.append(f"DGS10 ended at {dgs10_latest:.2f}%.")
        confidence = "medium"

    elif worst_equity_return is not None and worst_equity_return["value"] < -10:
        label = "risk_off"
        drivers.append(f"{worst_equity_return['name']} was {worst_equity_return['value']:.2f}%.")
        confidence = "medium"

    if not drivers:
        drivers.append("No single first-version regime rule dominates.")

    return {
        "regime_label": label,
        "drivers": drivers,
        "confidence": confidence,
        "methodology_note": CLASSIFICATION_NOTE,
    }


def build_crisis_window_summary(series_by_key: dict, crisis_windows: dict) -> dict:
    summary = {}
    prepared = _prepared_series(series_by_key)
    cpi_yoy = calculate_inflation_yoy_series(prepared.get("cpi", []))
    pce_yoy = calculate_inflation_yoy_series(prepared.get("pce", []))
    latest_available_date = _latest_available_date(prepared)

    for window_key, config in crisis_windows.items():
        start = config.get("start")
        configured_end = config.get("end")
        effective_end, ongoing = _effective_window_end(configured_end, latest_available_date)
        item = {
            "name": config.get("name") or window_key,
            "start": start,
            "end": effective_end,
            "configured_end": configured_end,
            "effective_end": effective_end,
            "ongoing": ongoing,
            "equity": {
                "sp500_return": calculate_index_return(prepared.get("sp500", []), start, effective_end),
                "sp500_drawdown": calculate_drawdown(prepared.get("sp500", []), start, effective_end),
                "nasdaq_return": calculate_index_return(prepared.get("nasdaq", []), start, effective_end),
                "nasdaq100_return": calculate_index_return(prepared.get("nasdaq100", []), start, effective_end),
            },
            "rates": {
                "dgs10": calculate_rate_summary(prepared.get("dgs10", []), start, effective_end),
                "fedfunds": calculate_rate_summary(prepared.get("fedfunds", []), start, effective_end),
            },
            "inflation": {
                "cpi_yoy": summarize_inflation_window(cpi_yoy, start, effective_end),
                "pce_yoy": summarize_inflation_window(pce_yoy, start, effective_end),
            },
            "labor_market": summarize_labor_window(prepared.get("nonfarm", []), start, effective_end),
        }
        item["regime_classification"] = classify_regime(item)
        summary[window_key] = item

    return summary


def build_current_regime_snapshot(series_by_key: dict, generated_at: str) -> dict:
    prepared = _prepared_series(series_by_key)
    end_date = _latest_common_date(prepared.get("sp500", []), generated_at)
    three_month_start = _date_offset(end_date, days=-100)
    one_month_start = _date_offset(end_date, days=-35)

    cpi_yoy = calculate_inflation_yoy_series(prepared.get("cpi", []))
    pce_yoy = calculate_inflation_yoy_series(prepared.get("pce", []))
    nonfarm = prepared.get("nonfarm", [])
    usd_cny = prepared.get("usd_cny", [])

    snapshot = {
        "end_date": end_date,
        "equity": {
            "sp500_1m_return": _trailing_return(prepared.get("sp500", []), 21),
            "sp500_3m_return": _trailing_return(prepared.get("sp500", []), 63),
            "nasdaq_1m_return": _trailing_return(prepared.get("nasdaq", []), 21),
            "nasdaq_3m_return": _trailing_return(prepared.get("nasdaq", []), 63),
            "nasdaq100_1m_return": _trailing_return(prepared.get("nasdaq100", []), 21),
            "nasdaq100_3m_return": _trailing_return(prepared.get("nasdaq100", []), 63),
            "sp500_drawdown": calculate_drawdown(prepared.get("sp500", []), three_month_start, end_date),
            "nasdaq100_drawdown": calculate_drawdown(prepared.get("nasdaq100", []), three_month_start, end_date),
        },
        "rates": {
            "dgs10": calculate_rate_summary(prepared.get("dgs10", []), three_month_start, end_date),
        },
        "inflation": {
            "cpi_yoy": _latest_yoy_summary(cpi_yoy),
            "pce_yoy": _latest_yoy_summary(pce_yoy),
        },
        "labor_market": _recent_labor_change(nonfarm),
        "fx": {
            "usd_cny_1m_change": calculate_index_return(usd_cny, one_month_start, end_date),
            "note": "DEXCHUS is CNY per USD; increases mean CNY weakens versus USD.",
        },
    }
    snapshot["regime_classification"] = classify_regime(snapshot)
    return snapshot


def find_similar_historical_windows(series_by_key: dict, current_snapshot: dict) -> dict:
    prepared = _prepared_series(series_by_key)
    sp500 = prepared.get("sp500", [])
    dgs10 = prepared.get("dgs10", [])
    nonfarm = prepared.get("nonfarm", [])
    cpi_yoy = calculate_inflation_yoy_series(prepared.get("cpi", []))
    pce_yoy = calculate_inflation_yoy_series(prepared.get("pce", []))

    current_buckets = _current_buckets(current_snapshot)
    if not sp500 or not current_buckets:
        return {
            "fully_observed_matches": [],
            "recent_incomplete_matches": [],
            "selection_note": "Fully observed matches require complete next 3m and next 12m historical outcomes.",
            "status": "insufficient_data",
            "error": "Insufficient current or historical data for similarity scan.",
        }

    fully_observed_matches = []
    recent_incomplete_matches = []
    for month_start in _month_starts(sp500):
        window_end = _month_end(month_start)
        if window_end >= current_snapshot.get("end_date", ""):
            continue
        snapshot = {
            "equity_3m": calculate_index_return(sp500, _date_offset(window_end, days=-100), window_end),
            "dgs10": calculate_rate_summary(dgs10, _date_offset(window_end, days=-100), window_end),
            "cpi_yoy": summarize_inflation_window(cpi_yoy, _date_offset(window_end, days=-45), window_end),
            "pce_yoy": summarize_inflation_window(pce_yoy, _date_offset(window_end, days=-45), window_end),
            "labor": summarize_labor_window(nonfarm, _date_offset(window_end, days=-120), window_end),
        }
        similarity = _similarity_match(current_buckets, snapshot)
        if similarity["similarity_score"] < 3:
            continue
        next_3m = _future_return(sp500, window_end, 63)
        next_12m = _future_return(sp500, window_end, 252)
        match = {
            "window_start": month_start,
            "window_end": window_end,
            "similarity_score": similarity["similarity_score"],
            "matched_buckets": similarity["matched_buckets"],
            "missing_buckets": similarity["missing_buckets"],
            "similarity_reasons": similarity["matched_buckets"],
            "next_3m_sp500_return": next_3m,
            "next_12m_sp500_return": next_12m,
            "outcome_availability": {
                "next_3m": _outcome_status(next_3m),
                "next_12m": _outcome_status(next_12m),
            },
            "notes": HISTORICAL_OUTCOME_NOTE,
        }
        if match["outcome_availability"]["next_3m"] == "ok" and match["outcome_availability"]["next_12m"] == "ok":
            fully_observed_matches.append(match)
        else:
            recent_incomplete_matches.append(match)

    fully_observed_matches.sort(
        key=lambda item: (-item.get("similarity_score", 0), item.get("window_start", "")),
    )
    recent_incomplete_matches.sort(
        key=lambda item: (item.get("similarity_score", 0), item.get("window_end", "")),
        reverse=True,
    )
    fully_observed_matches = fully_observed_matches[:10]
    recent_incomplete_matches = recent_incomplete_matches[:10]
    has_matches = bool(fully_observed_matches or recent_incomplete_matches)

    return {
        "fully_observed_matches": fully_observed_matches,
        "recent_incomplete_matches": recent_incomplete_matches,
        "selection_note": (
            "Fully observed matches require both next 3m and next 12m historical outcomes. "
            "Recent incomplete matches are separated because their historical outcome windows are too close to the present."
        ),
        "status": "ok" if has_matches else "insufficient_data",
        "error": None if has_matches else "No coarse-rule similar windows found.",
    }


def build_macro_regime_history_report(series_by_key, crisis_windows, generated_at) -> dict:
    current_snapshot = build_current_regime_snapshot(series_by_key, generated_at)
    crisis_summary = build_crisis_window_summary(series_by_key, crisis_windows)
    similar_windows = find_similar_historical_windows(series_by_key, current_snapshot)

    limitations = _series_limitations(series_by_key)
    limitations.extend(_collect_status_limitations(current_snapshot, "current_regime_snapshot"))
    limitations.extend(_collect_status_limitations(crisis_summary, "crisis_window_summary"))
    limitations.extend(_similar_window_limitations(similar_windows))
    limitations = _dedupe_strings(limitations)

    return {
        "report_type": "macro_regime_history",
        "generated_at": generated_at,
        "current_regime_snapshot": current_snapshot,
        "crisis_window_summary": crisis_summary,
        "similar_historical_windows": similar_windows,
        "data_limitations": limitations,
        "methodology_note": METHODOLOGY_NOTE,
    }


def _prepared_series(series_by_key: dict) -> dict:
    prepared = {}
    for key, payload in series_by_key.items():
        if isinstance(payload, dict) and "observations" in payload:
            prepared[key] = payload.get("observations", [])
        elif isinstance(payload, dict) and "response" in payload:
            prepared[key] = normalize_fred_observations(payload["response"])
        else:
            prepared[key] = normalize_fred_observations(payload)
    return prepared


def _series_limitations(series_by_key: dict) -> list[str]:
    limitations = []
    for key, payload in series_by_key.items():
        response = payload.get("response") if isinstance(payload, dict) and "response" in payload else payload
        if isinstance(response, dict) and response.get("status") != "ok":
            limitations.append(f"{key}: {response.get('error') or 'FRED history unavailable'}")
    return limitations


def _equity_metrics(snapshot: dict) -> list[dict]:
    equity = snapshot.get("equity", {}) if isinstance(snapshot, dict) else {}
    if not isinstance(equity, dict):
        return []

    metrics = []
    for name, payload in equity.items():
        if not isinstance(payload, dict):
            continue
        if name.endswith("_return"):
            value = _to_float_or_none(payload.get("return_pct"))
            metric_type = "return"
        elif name.endswith("_drawdown"):
            value = _to_float_or_none(payload.get("max_drawdown_pct"))
            metric_type = "drawdown"
        else:
            continue
        if value is None:
            continue
        metrics.append({"name": name, "value": value, "metric_type": metric_type})
    return metrics


def _min_metric(metrics: list[dict]) -> dict | None:
    return min(metrics, key=lambda item: item["value"], default=None)


def _max_metric(metrics: list[dict]) -> dict | None:
    return max(metrics, key=lambda item: item["value"], default=None)


def _latest_available_date(prepared: dict) -> str:
    dates = []
    for observations in prepared.values():
        if observations:
            dates.append(observations[-1]["date"])
    if dates:
        return max(dates)
    return datetime.now(timezone.utc).date().isoformat()


def _effective_window_end(configured_end: str | None, latest_available_date: str) -> tuple[str, bool]:
    if not configured_end:
        return latest_available_date, False
    if latest_available_date and configured_end > latest_available_date:
        return latest_available_date, True
    return configured_end, False


def _collect_status_limitations(value: Any, path: str) -> list[str]:
    limitations = []
    if isinstance(value, dict):
        status = value.get("status")
        if status and status != "ok":
            error = value.get("error") or "No error detail provided."
            limitations.append(f"{path}: {status} - {error}")
        for key, child in value.items():
            if isinstance(child, (dict, list)):
                child_path = f"{path}.{key}" if path else str(key)
                limitations.extend(_collect_status_limitations(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            if isinstance(child, (dict, list)):
                limitations.extend(_collect_status_limitations(child, f"{path}[{index}]"))
    return limitations


def _similar_window_limitations(similar_windows: dict) -> list[str]:
    limitations = []
    if similar_windows.get("status") != "ok":
        limitations.append(
            f"similar_historical_windows: {similar_windows.get('error') or 'No similar windows available.'}"
        )
    if similar_windows.get("recent_incomplete_matches"):
        limitations.append(
            "Some recent similar windows have incomplete forward historical outcomes because they are too close to the present."
        )
    return limitations


def _dedupe_strings(items: list[str]) -> list[str]:
    deduped = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _first_on_or_after(observations: list[dict], target_date: str) -> dict | None:
    for observation in observations:
        if observation["date"] >= target_date:
            return observation
    return None


def _last_on_or_before(observations: list[dict], target_date: str) -> dict | None:
    for observation in reversed(observations):
        if observation["date"] <= target_date:
            return observation
    return None


def _window(observations: list[dict], start_date: str, end_date: str) -> list[dict]:
    return [
        observation
        for observation in observations
        if start_date <= observation.get("date", "") <= end_date
    ]


def _trailing_return(observations: list[dict], periods: int) -> dict:
    if len(observations) <= periods:
        return _insufficient(f"Need more than {periods} observations; got {len(observations)}.")
    latest = observations[-1]
    previous = observations[-1 - periods]
    return calculate_index_return(observations, previous["date"], latest["date"])


def _future_return(observations: list[dict], window_end: str, periods: int) -> dict:
    start = _first_on_or_after(observations, window_end)
    if start is None:
        return _insufficient("No start observation for historical outcome.")
    start_index = observations.index(start)
    target_index = start_index + periods
    if target_index >= len(observations):
        return _insufficient(f"Need {periods} future observations; got {len(observations) - start_index - 1}.")
    end = observations[target_index]
    return calculate_index_return(observations, start["date"], end["date"])


def _outcome_status(outcome: dict) -> str:
    return "ok" if isinstance(outcome, dict) and outcome.get("status") == "ok" else "insufficient_data"


def _latest_yoy_summary(yoy_series: list[dict]) -> dict:
    if not yoy_series:
        return _summary_insufficient("No YoY inflation data.")
    latest = yoy_series[-1]
    return {
        "start_yoy": None,
        "end_yoy": latest["yoy_pct"],
        "max_yoy": latest["yoy_pct"],
        "average_yoy": latest["yoy_pct"],
        "change_pp": None,
        "end_date": latest["date"],
        "status": "ok",
        "error": None,
    }


def _recent_labor_change(nonfarm: list[dict]) -> dict:
    if len(nonfarm) < 4:
        return _summary_insufficient("Need at least 4 nonfarm observations.")
    return summarize_labor_window(nonfarm, nonfarm[-4]["date"], nonfarm[-1]["date"])


def _nearest_same_month_or_before(observations: list[dict], target: date) -> dict | None:
    same_month = [
        observation
        for observation in observations
        if (parsed := _parse_date(observation["date"])) is not None
        and parsed.year == target.year
        and parsed.month == target.month
    ]
    if same_month:
        return same_month[-1]
    return _last_on_or_before(observations, target.isoformat())


def _current_buckets(snapshot: dict) -> dict:
    equity = _extract_metric(snapshot, ("equity", "sp500_3m_return", "return_pct"))
    dgs10 = _extract_metric(snapshot, ("rates", "dgs10", "end_value"))
    cpi = _extract_metric(snapshot, ("inflation", "cpi_yoy", "end_yoy"))
    pce = _extract_metric(snapshot, ("inflation", "pce_yoy", "end_yoy"))
    labor = _extract_metric(snapshot, ("labor_market", "percent_change"))
    if equity is None or dgs10 is None:
        return {}
    inflation = max([value for value in (cpi, pce) if value is not None], default=None)
    return {
        "equity": _equity_bucket(equity),
        "rate": _rate_bucket(dgs10),
        "inflation": _inflation_bucket(inflation),
        "labor": _labor_bucket(labor),
    }


def _similarity_match(current_buckets: dict, historical_snapshot: dict) -> dict:
    historical_equity = _extract_metric(historical_snapshot, ("equity_3m", "return_pct"))
    historical_rate = _extract_metric(historical_snapshot, ("dgs10", "end_value"))
    historical_cpi = _extract_metric(historical_snapshot, ("cpi_yoy", "end_yoy"))
    historical_pce = _extract_metric(historical_snapshot, ("pce_yoy", "end_yoy"))
    historical_labor = _extract_metric(historical_snapshot, ("labor", "percent_change"))
    historical_buckets = {
        "equity": _equity_bucket(historical_equity),
        "rate": _rate_bucket(historical_rate),
        "inflation": _inflation_bucket(max([v for v in (historical_cpi, historical_pce) if v is not None], default=None)),
        "labor": _labor_bucket(historical_labor),
    }
    matched = []
    missing = []
    for key, current_value in current_buckets.items():
        historical_value = historical_buckets.get(key)
        if current_value is not None and current_value == historical_value:
            matched.append(f"{key}_bucket={current_value}")
        else:
            missing.append(
                f"{key}_bucket=current:{current_value or 'unknown'}, historical:{historical_value or 'unknown'}"
            )
    return {
        "similarity_score": len(matched),
        "matched_buckets": matched,
        "missing_buckets": missing,
    }


def _equity_bucket(value: float | None) -> str | None:
    if value is None:
        return None
    if value > 8:
        return "strong"
    if value < -10:
        return "weak"
    return "mixed"


def _rate_bucket(value: float | None) -> str | None:
    if value is None:
        return None
    if value >= 4:
        return "high"
    if value >= 2:
        return "medium"
    return "low"


def _inflation_bucket(value: float | None) -> str | None:
    if value is None:
        return None
    if value >= 4:
        return "high"
    if value >= 2.5:
        return "medium"
    return "low"


def _labor_bucket(value: float | None) -> str | None:
    if value is None:
        return None
    if value < -0.2:
        return "weakening"
    if value > 0.2:
        return "resilient"
    return "flat"


def _month_starts(observations: list[dict]) -> list[str]:
    starts = []
    seen = set()
    for observation in observations:
        month = observation["date"][:7]
        if month in seen:
            continue
        seen.add(month)
        starts.append(observation["date"])
    return starts


def _month_end(month_start: str) -> str:
    parsed = _parse_date(month_start)
    if parsed is None:
        return month_start
    next_month = _add_months(parsed.replace(day=1), 1)
    return (next_month - timedelta(days=1)).isoformat()


def _latest_common_date(observations: list[dict], generated_at: str) -> str:
    if observations:
        return observations[-1]["date"]
    parsed = _parse_date(generated_at)
    return parsed.isoformat() if parsed else datetime.now(timezone.utc).date().isoformat()


def _date_offset(end_date: str, days: int) -> str:
    parsed = _parse_date(end_date)
    if parsed is None:
        return end_date
    return (parsed + timedelta(days=days)).isoformat()


def _add_months(value: date, months: int) -> date:
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    day = min(value.day, 28)
    return date(year, month, day)


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None


def _extract_metric(source: dict, path: tuple[str, ...]) -> float | None:
    current: Any = source
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return _to_float_or_none(current)


def _insufficient(error: str) -> dict:
    return {
        "start_date": None,
        "end_date": None,
        "start_value": None,
        "end_value": None,
        "return_pct": None,
        "status": "insufficient_data",
        "error": error,
    }


def _summary_insufficient(error: str) -> dict:
    return {
        "status": "insufficient_data",
        "error": error,
    }


def _to_float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

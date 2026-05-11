from __future__ import annotations

import calendar
from datetime import date, datetime, timezone
from typing import Any


METHODOLOGY_NOTE = "Rule-based descriptive assessment, not a market forecast."


def normalize_observations(observations: list[dict]) -> list[dict]:
    normalized = []

    for observation in observations:
        if not isinstance(observation, dict):
            continue

        date = observation.get("date") or observation.get("observation_date")
        value = _to_float_or_none(observation.get("value"))
        if not date or value is None:
            continue

        normalized.append(
            {
                "date": str(date),
                "value": value,
                "source": "FRED",
            }
        )

    return sorted(normalized, key=lambda item: item["date"])


def calculate_change(observations: list[dict], periods: int) -> dict:
    if periods <= 0:
        return _change_error(
            periods=periods,
            error="periods must be greater than 0",
        )

    normalized = normalize_observations(observations)
    if len(normalized) <= periods:
        return _change_error(
            periods=periods,
            error=f"Need at least {periods + 1} observations, got {len(normalized)}",
        )

    latest = normalized[-1]
    previous = normalized[-(periods + 1)]
    latest_value = latest["value"]
    previous_value = previous["value"]

    if previous_value == 0:
        return _change_error(
            periods=periods,
            latest_value=latest_value,
            previous_value=previous_value,
            latest_date=latest["date"],
            previous_date=previous["date"],
            error="previous_value is 0",
        )

    absolute_change = latest_value - previous_value
    percent_change = absolute_change / previous_value * 100

    return {
        "latest_value": _round_number(latest_value),
        "previous_value": _round_number(previous_value),
        "absolute_change": _round_number(absolute_change),
        "percent_change": _round_number(percent_change),
        "latest_date": latest["date"],
        "previous_date": previous["date"],
        "periods": periods,
        "source": "FRED",
        "status": "ok",
        "error": None,
    }


def calculate_yoy_change(observations: list[dict], months: int = 12) -> dict:
    if months <= 0:
        return _change_error(
            periods=months,
            error="months must be greater than 0",
        )

    normalized = normalize_observations(observations)
    if len(normalized) < 2:
        return _change_error(
            periods=months,
            error=f"Need at least 2 observations, got {len(normalized)}",
        )

    parsed_observations = []
    for observation in normalized:
        parsed_date = _parse_date(observation["date"])
        if parsed_date is None:
            continue
        parsed_observations.append((parsed_date, observation))

    if len(parsed_observations) < 2:
        return _change_error(
            periods=months,
            error="No observations with parseable dates",
        )

    latest_date, latest = parsed_observations[-1]
    target_date = _shift_months(latest_date, -months)
    previous_date, previous, notes = _find_yoy_previous_observation(
        parsed_observations[:-1],
        target_date,
    )

    if previous is None or previous_date is None:
        return _change_error(
            periods=months,
            latest_value=latest["value"],
            latest_date=latest["date"],
            error=f"No reasonable observation found near {target_date.isoformat()}",
        )

    latest_value = latest["value"]
    previous_value = previous["value"]
    if previous_value == 0:
        return _change_error(
            periods=months,
            latest_value=latest_value,
            previous_value=previous_value,
            latest_date=latest["date"],
            previous_date=previous["date"],
            error="previous_value is 0",
        )

    absolute_change = latest_value - previous_value
    percent_change = absolute_change / previous_value * 100

    return {
        "latest_value": _round_number(latest_value),
        "previous_value": _round_number(previous_value),
        "absolute_change": _round_number(absolute_change),
        "percent_change": _round_number(percent_change),
        "latest_date": latest["date"],
        "previous_date": previous["date"],
        "target_date": target_date.isoformat(),
        "periods": months,
        "months": months,
        "source": "FRED",
        "status": "ok",
        "error": None,
        "notes": notes,
    }


def classify_equity_temperature(
    sp500_1m: dict,
    sp500_3m: dict,
    nasdaq_1m: dict,
    nasdaq_3m: dict,
) -> dict:
    changes = {
        "sp500_1m": sp500_1m,
        "sp500_3m": sp500_3m,
        "nasdaq_1m": nasdaq_1m,
        "nasdaq_3m": nasdaq_3m,
    }
    missing = _missing_changes(changes)
    if missing:
        return {
            "level": "unknown",
            "reasons": [f"Insufficient data for {name}" for name in missing],
            "status": "unknown",
            "error": "insufficient_data",
        }

    sp500_1m_pct = sp500_1m["percent_change"]
    sp500_3m_pct = sp500_3m["percent_change"]
    nasdaq_1m_pct = nasdaq_1m["percent_change"]
    nasdaq_3m_pct = nasdaq_3m["percent_change"]

    if (
        sp500_1m_pct > 5
        and nasdaq_1m_pct > 5
        and sp500_3m_pct > 12
        and nasdaq_3m_pct > 12
    ):
        level = "hot"
        reasons = [
            "SP500 and NASDAQCOM 1m changes are both above 5%.",
            "SP500 and NASDAQCOM 3m changes are both above 12%.",
        ]
    elif (
        sp500_1m_pct > 3
        and nasdaq_1m_pct > 3
    ) or (
        sp500_3m_pct > 8
        and nasdaq_3m_pct > 8
    ):
        level = "warm"
        reasons = [
            "Equity momentum meets the warm threshold for 1m or 3m changes.",
        ]
    elif sp500_1m_pct < -8 and nasdaq_1m_pct < -8:
        level = "cold"
        reasons = [
            "SP500 and NASDAQCOM 1m changes are both below -8%.",
        ]
    elif sp500_1m_pct < -3 and nasdaq_1m_pct < -3:
        level = "cool"
        reasons = [
            "SP500 and NASDAQCOM 1m changes are both below -3%.",
        ]
    else:
        level = "neutral"
        reasons = [
            "Equity changes do not meet hot, warm, cool, or cold thresholds.",
        ]

    return {
        "level": level,
        "reasons": reasons,
        "status": "ok",
        "error": None,
    }


def classify_rate_pressure(dgs10_latest: float, dgs10_1m_change: dict) -> dict:
    if dgs10_latest is None or dgs10_1m_change.get("status") != "ok":
        return {
            "level": "unknown",
            "reasons": ["Insufficient DGS10 data."],
            "status": "unknown",
            "error": "insufficient_data",
        }

    one_month_change = float(dgs10_1m_change["absolute_change"])
    if dgs10_latest >= 4.5 or one_month_change >= 0.25:
        level = "high"
        reasons = [
            "DGS10 is at or above 4.5%, or the 1m change is at least 0.25 percentage points.",
            "DGS10 is measured in percentage points; absolute_change is a percentage-point move.",
        ]
    elif dgs10_latest >= 4.0:
        level = "medium"
        reasons = [
            "DGS10 is at or above 4.0%.",
            "DGS10 is measured in percentage points.",
        ]
    else:
        level = "low"
        reasons = [
            "DGS10 is below 4.0% and the 1m percentage-point move is below 0.25.",
        ]

    return {
        "level": level,
        "reasons": reasons,
        "status": "ok",
        "error": None,
    }


def classify_inflation_pressure(
    cpi_yoy: dict,
    pce_yoy: dict,
    cpi_mom: dict,
    pce_mom: dict,
) -> dict:
    if cpi_yoy.get("status") != "ok" or pce_yoy.get("status") != "ok":
        return {
            "level": "unknown",
            "reasons": ["Insufficient CPI or PCE YoY data."],
            "status": "unknown",
            "error": "insufficient_data",
        }

    cpi_yoy_pct = cpi_yoy["percent_change"]
    pce_yoy_pct = pce_yoy["percent_change"]
    reasons = [
        f"CPI YoY change is {cpi_yoy_pct}%.",
        f"PCE YoY change is {pce_yoy_pct}%.",
        "This describes inflation pressure and is not an inflation forecast.",
    ]

    if cpi_yoy_pct >= 4 or pce_yoy_pct >= 4:
        level = "high"
    elif cpi_yoy_pct >= 3 or pce_yoy_pct >= 3:
        level = "medium"
    else:
        level = "low"

    if cpi_mom.get("status") != "ok":
        reasons.append("CPI MoM data is insufficient.")
    if pce_mom.get("status") != "ok":
        reasons.append("PCE MoM data is insufficient.")

    return {
        "level": level,
        "reasons": reasons,
        "status": "ok",
        "error": None,
    }


def classify_labor_market(nonfarm_mom_change: dict) -> dict:
    if nonfarm_mom_change.get("status") != "ok":
        return {
            "level": "unknown",
            "reasons": ["Insufficient PAYEMS month-over-month data."],
            "status": "unknown",
            "error": "insufficient_data",
        }

    absolute_change = nonfarm_mom_change["absolute_change"]
    if absolute_change > 0:
        level = "resilient"
        reasons = ["PAYEMS increased versus the previous observation."]
    elif absolute_change < 0:
        level = "weakening"
        reasons = ["PAYEMS decreased versus the previous observation."]
    else:
        level = "neutral"
        reasons = ["PAYEMS was unchanged versus the previous observation."]

    return {
        "level": level,
        "reasons": reasons,
        "status": "ok",
        "error": None,
    }


def classify_fx_pressure(usd_cny_1m_change: dict) -> dict:
    required_note = (
        "DEXCHUS is CNY per USD, so an increase means CNY weakened versus USD."
    )
    if usd_cny_1m_change.get("status") != "ok":
        return {
            "level": "unknown",
            "reasons": ["Insufficient DEXCHUS data.", required_note],
            "status": "unknown",
            "error": "insufficient_data",
        }

    percent_change = usd_cny_1m_change["percent_change"]
    if percent_change > 1:
        level = "usd_strengthening_cny_weakening"
        reasons = [
            "DEXCHUS rose by more than 1% over the measured window.",
            required_note,
        ]
    elif percent_change < -1:
        level = "usd_weakening_cny_strengthening"
        reasons = [
            "DEXCHUS fell by more than 1% over the measured window.",
            required_note,
        ]
    else:
        level = "neutral"
        reasons = [
            "DEXCHUS 1m change is within +/-1%.",
            required_note,
        ]

    return {
        "level": level,
        "reasons": reasons,
        "status": "ok",
        "error": None,
    }


def score_market_temperature(inputs: dict) -> dict:
    equity_temperature = classify_equity_temperature(
        inputs.get("sp500_1m_change", {}),
        inputs.get("sp500_3m_change", {}),
        inputs.get("nasdaq_1m_change", {}),
        inputs.get("nasdaq_3m_change", {}),
    )
    rate_pressure = classify_rate_pressure(
        inputs.get("dgs10_latest"),
        inputs.get("dgs10_1m_change", {}),
    )
    inflation_pressure = classify_inflation_pressure(
        inputs.get("cpi_yoy_change", {}),
        inputs.get("pce_yoy_change", {}),
        inputs.get("cpi_mom_change", {}),
        inputs.get("pce_mom_change", {}),
    )
    labor_market = classify_labor_market(inputs.get("nonfarm_mom_change", {}))
    fx_pressure = classify_fx_pressure(inputs.get("usd_cny_1m_change", {}))

    data_limitations = list(inputs.get("data_limitations", []))
    data_limitations.extend(
        _classification_limitations(
            {
                "equity_temperature": equity_temperature,
                "rate_pressure": rate_pressure,
                "inflation_pressure": inflation_pressure,
                "labor_market": labor_market,
                "fx_pressure": fx_pressure,
            }
        )
    )

    overall_regime = _overall_regime(equity_temperature, rate_pressure, inflation_pressure)
    risk_level = _risk_level(rate_pressure, inflation_pressure)

    return {
        "equity_temperature": equity_temperature,
        "rate_pressure": rate_pressure,
        "inflation_pressure": inflation_pressure,
        "labor_market": labor_market,
        "fx_pressure": fx_pressure,
        "overall_regime": overall_regime,
        "risk_level": risk_level,
        "data_limitations": _dedupe(data_limitations),
        "methodology_note": METHODOLOGY_NOTE,
        "generated_at": _utc_now(),
    }


def _overall_regime(
    equity_temperature: dict,
    rate_pressure: dict,
    inflation_pressure: dict,
) -> str:
    equity_level = equity_temperature.get("level")
    rate_level = rate_pressure.get("level")
    inflation_level = inflation_pressure.get("level")

    if equity_level == "hot" and inflation_level == "high":
        return "hot_but_macro_constrained"
    if equity_level in {"hot", "warm"} and rate_level == "high":
        return "warm_but_rate_sensitive"
    if (
        equity_level in {"hot", "warm"}
        and (
            rate_level in {"medium", "high"}
            or inflation_level in {"medium", "high"}
        )
    ):
        return "warm_but_macro_sensitive"
    if equity_level in {"cold", "cool"}:
        return "risk_off"
    if equity_level == "neutral" and (
        rate_level in {"medium", "high"}
        or inflation_level in {"medium", "high"}
    ):
        return "neutral_but_macro_sensitive"
    return "neutral"


def _risk_level(rate_pressure: dict, inflation_pressure: dict) -> str:
    if rate_pressure.get("level") == "high" or inflation_pressure.get("level") == "high":
        return "high"
    if (
        rate_pressure.get("level") == "medium"
        or inflation_pressure.get("level") == "medium"
    ):
        return "medium"
    return "low"


def _classification_limitations(classifications: dict[str, dict]) -> list[str]:
    limitations = []
    for name, classification in classifications.items():
        if classification.get("status") == "unknown":
            limitations.append(f"{name} is unknown: {classification.get('error')}")
    return limitations


def _missing_changes(changes: dict[str, dict]) -> list[str]:
    return [
        name
        for name, change in changes.items()
        if not isinstance(change, dict) or change.get("status") != "ok"
    ]


def _find_yoy_previous_observation(
    parsed_observations: list[tuple[date, dict]],
    target_date: date,
) -> tuple[date | None, dict | None, list[str]]:
    same_month = [
        (observation_date, observation)
        for observation_date, observation in parsed_observations
        if observation_date.year == target_date.year
        and observation_date.month == target_date.month
    ]
    if same_month:
        previous_date, previous = min(
            same_month,
            key=lambda item: abs((item[0] - target_date).days),
        )
        notes = []
        if previous_date != target_date:
            notes.append(
                "Nearest available same-month observation used for YoY comparison."
            )
        return previous_date, previous, notes

    prior_observations = [
        (observation_date, observation)
        for observation_date, observation in parsed_observations
        if observation_date <= target_date
    ]
    if not prior_observations:
        return None, None, []

    previous_date, previous = max(prior_observations, key=lambda item: item[0])
    if (target_date - previous_date).days > 62:
        return None, None, []

    return (
        previous_date,
        previous,
        [
            "Nearest available observation on or before the YoY target date used.",
        ],
    )


def _shift_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year = month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _change_error(
    periods: int,
    error: str,
    latest_value: float | None = None,
    previous_value: float | None = None,
    latest_date: str | None = None,
    previous_date: str | None = None,
) -> dict:
    return {
        "latest_value": latest_value,
        "previous_value": previous_value,
        "absolute_change": None,
        "percent_change": None,
        "latest_date": latest_date,
        "previous_date": previous_date,
        "periods": periods,
        "source": "FRED",
        "status": "insufficient_data",
        "error": error,
    }


def _to_float_or_none(value: Any) -> float | None:
    if value is None:
        return None

    if str(value).strip() == ".":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_number(value: float) -> float:
    return round(float(value), 6)


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

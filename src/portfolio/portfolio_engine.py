from __future__ import annotations

import csv
import io
from datetime import date, datetime
from pathlib import Path
from typing import Any


REQUIRED_HOLDING_FIELDS = (
    "asset_name",
    "fund_code",
    "asset_class",
    "current_value",
    "cost_basis",
    "profit_loss",
    "currency",
    "updated_at",
    "notes",
)

MONEY_FIELDS = ("current_value", "cost_basis", "profit_loss")
CSV_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030")
MOJIBAKE_MARKERS = (
    "鎽╂牴",
    "绾虫柉",
    "骞垮彂",
    "鍩洪噾",
    "浣欓",
    "鐭",
    "鑱旀帴",
)
CANONICAL_ASSET_NAMES = {
    "017641": "摩根标普500指数(QDII)A",
    "019172": "摩根纳斯达克100指数(QDII)A",
    "270042": "广发纳斯达克100ETF联接(QDII)A",
    "016527": "招商鑫诚短债债券C",
    "008987": "广发上海金ETF联接C",
    "cash_yuebao": "余额宝",
}


def load_holdings_csv(path: str) -> list[dict]:
    csv_path = Path(path)
    reader = _read_csv_with_encoding_fallback(csv_path)

    if reader.fieldnames is None:
        raise ValueError(f"Holdings CSV has no header: {csv_path}")

    missing_fields = [
        field for field in REQUIRED_HOLDING_FIELDS if field not in reader.fieldnames
    ]
    if missing_fields:
        missing = ", ".join(missing_fields)
        raise ValueError(f"Holdings CSV is missing required field(s): {missing}")

    holdings: list[dict] = []
    for row_number, row in enumerate(reader, start=2):
        normalized = {
            field: _repair_mojibake_text((row.get(field) or "").strip())
            for field in REQUIRED_HOLDING_FIELDS
        }
        normalized = _apply_canonical_asset_name(normalized)

        if not normalized["asset_class"]:
            raise ValueError(
                f"Holdings CSV row {row_number} is missing asset_class."
            )

        for field in MONEY_FIELDS:
            raw_value = normalized[field]
            try:
                normalized[field] = float(raw_value)
            except ValueError as exc:
                raise ValueError(
                    f"Holdings CSV row {row_number} has invalid {field}: "
                    f"{raw_value!r}."
                ) from exc

        holdings.append(normalized)

    return holdings


def _read_csv_with_encoding_fallback(csv_path: Path) -> csv.DictReader:
    raw_bytes = csv_path.read_bytes()
    mojibake_reader: csv.DictReader | None = None

    for encoding in CSV_ENCODINGS:
        try:
            text = raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue

        reader = csv.DictReader(io.StringIO(text), strict=True)
        rows = list(reader)
        if reader.fieldnames is None:
            continue

        if _rows_contain_mojibake(rows):
            repaired_rows = [
                {key: _repair_mojibake_text(value or "") for key, value in row.items()}
                for row in rows
            ]
            if not _rows_contain_mojibake(repaired_rows):
                return _rows_to_reader(reader.fieldnames, repaired_rows)
            mojibake_reader = _rows_to_reader(reader.fieldnames, repaired_rows)
            continue

        return _rows_to_reader(reader.fieldnames, rows)

    if mojibake_reader is not None:
        return mojibake_reader

    raise ValueError(
        "Unable to read holdings CSV with supported encodings: "
        + ", ".join(CSV_ENCODINGS)
    )


def _rows_to_reader(fieldnames: list[str], rows: list[dict]) -> csv.DictReader:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    output.seek(0)
    return csv.DictReader(output)


def _rows_contain_mojibake(rows: list[dict]) -> bool:
    return any(
        _contains_mojibake(str(value))
        for row in rows
        for value in row.values()
        if value is not None
    )


def _contains_mojibake(value: str) -> bool:
    return any(marker in value for marker in MOJIBAKE_MARKERS)


def _repair_mojibake_text(value: str) -> str:
    if not _contains_mojibake(value):
        return value
    for encoding in ("gb18030", "gbk"):
        try:
            repaired = value.encode(encoding).decode("utf-8")
        except UnicodeError:
            continue
        if not _contains_mojibake(repaired):
            return repaired
    return value


def _apply_canonical_asset_name(row: dict) -> dict:
    fund_code = str(row.get("fund_code", "")).strip()
    asset_class = str(row.get("asset_class", "")).strip()
    canonical_name = CANONICAL_ASSET_NAMES.get(fund_code)
    if canonical_name is None and asset_class == "cash":
        canonical_name = CANONICAL_ASSET_NAMES["cash_yuebao"]
    if canonical_name and _contains_mojibake(str(row.get("asset_name", ""))):
        row["asset_name"] = canonical_name
    return row


def load_user_profile(path: str) -> dict:
    profile_path = Path(path)
    raw_text = profile_path.read_text(encoding="utf-8")

    try:
        import yaml
    except ImportError:
        profile = _load_simple_yaml(raw_text)
    else:
        profile = yaml.safe_load(raw_text)

    if not isinstance(profile, dict):
        raise ValueError(f"User profile YAML must contain a mapping: {profile_path}")

    return profile


def aggregate_by_asset_class(holdings: list[dict]) -> dict:
    aggregated: dict[str, dict[str, float]] = {}

    for index, holding in enumerate(holdings, start=1):
        asset_class = str(holding.get("asset_class", "")).strip()
        if not asset_class:
            raise ValueError(f"Holding #{index} is missing asset_class.")

        bucket = aggregated.setdefault(
            asset_class,
            {
                "current_value": 0.0,
                "cost_basis": 0.0,
                "profit_loss": 0.0,
            },
        )
        for field in MONEY_FIELDS:
            bucket[field] += float(holding[field])

    return {
        asset_class: {
            field: _round_money(value) for field, value in values.items()
        }
        for asset_class, values in aggregated.items()
    }


def calculate_total_assets(aggregated: dict) -> dict:
    total_assets = sum(
        float(values.get("current_value", 0.0)) for values in aggregated.values()
    )
    cash = float(aggregated.get("cash", {}).get("current_value", 0.0))
    total_profit_loss = sum(
        float(values.get("profit_loss", 0.0)) for values in aggregated.values()
    )

    return {
        "total_assets": _round_money(total_assets),
        "invested_assets": _round_money(total_assets - cash),
        "cash": _round_money(cash),
        "total_account_value": _round_money(total_assets),
        "invested_asset_value": _round_money(total_assets - cash),
        "cash_reserve_value": _round_money(cash),
        "total_profit_loss": _round_money(total_profit_loss),
    }


def calculate_weights(aggregated: dict, include_cash: bool = False) -> dict:
    eligible_assets = {
        asset_class: values
        for asset_class, values in aggregated.items()
        if include_cash or asset_class != "cash"
    }
    denominator = sum(
        float(values.get("current_value", 0.0)) for values in eligible_assets.values()
    )

    if denominator == 0:
        return {
            asset_class: _round_weight(0.0)
            for asset_class in eligible_assets
        }

    return {
        asset_class: _round_weight(
            float(values.get("current_value", 0.0)) / denominator
        )
        for asset_class, values in eligible_assets.items()
    }


def calculate_deviation(current_weights: dict, target_allocation: dict) -> dict:
    ordered_asset_classes = list(target_allocation)
    ordered_asset_classes.extend(
        asset_class
        for asset_class in current_weights
        if asset_class not in target_allocation
    )

    return {
        asset_class: _round_weight(
            float(current_weights.get(asset_class, 0.0))
            - float(target_allocation.get(asset_class, 0.0))
        )
        for asset_class in ordered_asset_classes
    }


def classify_deviation(deviation: dict, threshold: float) -> dict:
    return {
        asset_class: _classify_single_deviation(float(value), threshold)
        for asset_class, value in deviation.items()
    }


def check_dca_budget(
    daily_plan: dict,
    trading_days: int,
    monthly_budget_min: float,
    monthly_budget_max: float,
) -> dict:
    if trading_days < 0:
        raise ValueError("trading_days must be greater than or equal to 0.")

    daily_total = 0.0
    for key, value in daily_plan.items():
        amount = _to_float(value, f"daily_plan.{key}")
        if amount < 0:
            raise ValueError(f"daily_plan.{key} must be greater than or equal to 0.")
        daily_total += amount

    monthly_required = daily_total * trading_days
    budget_min = float(monthly_budget_min)
    budget_max = float(monthly_budget_max)

    if monthly_required > budget_max:
        status = "above_budget"
    elif monthly_required < budget_min:
        status = "below_budget"
    else:
        status = "within_budget"

    return {
        "daily_total": _round_money(daily_total),
        "monthly_required": _round_money(monthly_required),
        "budget_min": _round_money(budget_min),
        "budget_max": _round_money(budget_max),
        "trading_days": trading_days,
        "status": status,
    }


def generate_portfolio_snapshot(
    holdings_path: str,
    profile_path: str,
    trading_days: int = 21,
) -> dict:
    holdings = load_holdings_csv(holdings_path)
    profile = load_user_profile(profile_path)

    target_allocation = _require_mapping(profile, "target_allocation")
    user = _require_mapping(profile, "user")
    build_phase = _require_mapping(profile, "build_phase")
    rebalance = _require_mapping(profile, "rebalance")
    daily_plan = _require_mapping(build_phase, "daily_plan")

    aggregated = aggregate_by_asset_class(holdings)
    totals = calculate_total_assets(aggregated)
    holdings_freshness = summarize_holdings_updated_at(holdings)
    weights_ex_cash = calculate_weights(aggregated, include_cash=False)
    rounded_target_allocation = {
        asset_class: _round_weight(float(weight))
        for asset_class, weight in target_allocation.items()
    }
    deviation = calculate_deviation(weights_ex_cash, rounded_target_allocation)
    threshold = float(rebalance.get("deviation_threshold", 0.0))
    deviation_flags = classify_deviation(deviation, threshold)
    dca_budget_check = check_dca_budget(
        daily_plan=daily_plan,
        trading_days=trading_days,
        monthly_budget_min=float(user["monthly_budget_min"]),
        monthly_budget_max=float(user["monthly_budget_max"]),
    )
    dca_daily_plan = build_dca_daily_plan(daily_plan, profile)

    return {
        "total_assets": totals["total_assets"],
        "invested_assets": totals["invested_assets"],
        "cash": totals["cash"],
        "total_account_value": totals["total_account_value"],
        "invested_asset_value": totals["invested_asset_value"],
        "cash_reserve_value": totals["cash_reserve_value"],
        "total_profit_loss": totals["total_profit_loss"],
        "holdings_updated_at": holdings_freshness["holdings_updated_at"],
        "holdings_age_days": holdings_freshness["holdings_age_days"],
        "holdings_freshness_status": holdings_freshness["holdings_freshness_status"],
        "holdings_updated_at_status": holdings_freshness["holdings_updated_at_status"],
        "holdings_updated_at_values": holdings_freshness["holdings_updated_at_values"],
        "holdings_row_count": holdings_freshness["holdings_row_count"],
        "holdings": [_holding_detail(holding) for holding in holdings],
        "aggregated_by_asset_class": aggregated,
        "weights_ex_cash": weights_ex_cash,
        "target_allocation": rounded_target_allocation,
        "deviation": deviation,
        "deviation_flags": deviation_flags,
        "dca_budget_check": dca_budget_check,
        "dca_daily_plan": dca_daily_plan,
        "notes": [
            "This snapshot is descriptive only and does not include investment advice.",
            "Cash is treated as cash reserve and excluded from target-allocation weights by default.",
            "Cash reserve can be a DCA deduction source; it is not a target investment asset.",
            "Current cash reserve is a point-in-time snapshot, not remaining monthly contribution amount.",
            "Deviation is calculated as current weight minus target weight.",
        ],
    }


def _holding_detail(holding: dict) -> dict:
    return {
        "asset_name": holding.get("asset_name"),
        "fund_code": holding.get("fund_code"),
        "asset_class": holding.get("asset_class"),
        "current_value": _round_money(holding.get("current_value", 0.0)),
        "cost_basis": _round_money(holding.get("cost_basis", 0.0)),
        "profit_loss": _round_money(holding.get("profit_loss", 0.0)),
        "currency": holding.get("currency"),
        "updated_at": holding.get("updated_at"),
        "notes": holding.get("notes"),
    }


def summarize_holdings_updated_at(holdings: list[dict]) -> dict:
    values = sorted(
        {
            str(holding.get("updated_at", "")).strip()
            for holding in holdings
            if str(holding.get("updated_at", "")).strip()
        }
    )
    updated_at_status = "missing"
    if len(values) == 1:
        updated_at_status = "consistent"
    elif len(values) > 1:
        updated_at_status = "mixed"

    parsed_dates = [_parse_holding_date(value) for value in values]
    parsed_dates = [value for value in parsed_dates if value is not None]
    latest_date = max(parsed_dates) if parsed_dates else None
    age_days = (date.today() - latest_date).days if latest_date else None
    freshness_status = _classify_holdings_freshness(age_days)

    return {
        "holdings_updated_at": latest_date.isoformat() if latest_date else (values[-1] if values else None),
        "holdings_age_days": age_days,
        "holdings_freshness_status": freshness_status,
        "holdings_updated_at_status": updated_at_status,
        "holdings_updated_at_values": values,
        "holdings_row_count": len(holdings),
    }


def _parse_holding_date(value: str) -> date | None:
    raw_value = str(value).strip()
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(raw_value.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    try:
        return date.fromisoformat(raw_value[:10])
    except ValueError:
        return None


def _classify_holdings_freshness(age_days: int | None) -> str:
    if age_days is None or age_days < 0:
        return "unknown"
    if age_days <= 7:
        return "fresh"
    if age_days <= 14:
        return "aging"
    if age_days <= 30:
        return "stale"
    return "very_stale"


def build_dca_daily_plan(daily_plan: dict, profile: dict) -> dict:
    known_funds = profile.get("known_funds", {})
    if not isinstance(known_funds, dict):
        known_funds = {}

    result = {}
    for key, raw_amount in daily_plan.items():
        amount = _to_float(raw_amount, f"daily_plan.{key}")
        fund_info = known_funds.get(str(key), {})
        if not isinstance(fund_info, dict):
            fund_info = {}
        result[str(key)] = {
            "daily_amount": _round_money(amount),
            "status": "active_dca" if amount > 0 else "paused",
            "asset_class": fund_info.get("asset_class") or str(key),
            "name": fund_info.get("name"),
        }
    return result


def _classify_single_deviation(value: float, threshold: float) -> str:
    if value <= -threshold:
        return "underweight"
    if value >= threshold:
        return "overweight"
    return "within_range"


def _require_mapping(source: dict, key: str) -> dict:
    value = source.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"user_profile.yaml must contain mapping: {key}")
    return value


def _round_money(value: float) -> float:
    return round(float(value), 2)


def _round_weight(value: float) -> float:
    return round(float(value), 4)


def _to_float(value: Any, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric: {value!r}") from exc


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

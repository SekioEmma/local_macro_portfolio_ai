from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from portfolio.portfolio_engine import generate_portfolio_snapshot


CURRENT_HOLDINGS_PATH = PROJECT_ROOT / "data" / "holdings" / "current_holdings.csv"
SAMPLE_HOLDINGS_PATH = PROJECT_ROOT / "data" / "holdings" / "sample_holdings.csv"
DEFAULT_PROFILE_PATH = PROJECT_ROOT / "configs" / "user_profile.yaml"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "outputs" / "reports" / "portfolio_snapshot.json"


def main() -> None:
    holdings_path, holdings_source = _select_holdings_file()
    snapshot = generate_portfolio_snapshot(
        holdings_path=str(holdings_path),
        profile_path=str(DEFAULT_PROFILE_PATH),
        trading_days=21,
    )
    snapshot["holdings_source"] = holdings_source

    formatted_json = json.dumps(snapshot, ensure_ascii=False, indent=2)
    print(formatted_json)

    DEFAULT_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT_PATH.write_text("\ufeff" + formatted_json + "\n", encoding="utf-8")


def _select_holdings_file() -> tuple[Path, dict]:
    if CURRENT_HOLDINGS_PATH.exists():
        return CURRENT_HOLDINGS_PATH, {
            "path": str(CURRENT_HOLDINGS_PATH),
            "mode": "current_holdings",
            "warning": (
                "Using user-provided current_holdings.csv local snapshot. "
                "It was manually entered from a user-confirmed holdings screenshot "
                "and is not guaranteed to be real-time."
            ),
            "cash_reserve_note": (
                "asset_class=cash is treated as cash reserve and DCA deduction source; "
                "it is excluded from target-allocation weights. Current cash reserve may "
                "already reflect this month's transfer and several trading-day deductions; "
                "do not treat it as remaining monthly contribution amount."
            ),
        }

    return SAMPLE_HOLDINGS_PATH, {
        "path": str(SAMPLE_HOLDINGS_PATH),
        "mode": "sample_fallback",
        "warning": "Using sample holdings because current_holdings.csv was not found.",
    }


if __name__ == "__main__":
    main()

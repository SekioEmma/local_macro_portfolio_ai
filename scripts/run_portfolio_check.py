from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from portfolio.portfolio_engine import generate_portfolio_snapshot


DEFAULT_HOLDINGS_PATH = PROJECT_ROOT / "data" / "holdings" / "sample_holdings.csv"
DEFAULT_PROFILE_PATH = PROJECT_ROOT / "configs" / "user_profile.yaml"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "outputs" / "reports" / "portfolio_snapshot.json"


def main() -> None:
    snapshot = generate_portfolio_snapshot(
        holdings_path=str(DEFAULT_HOLDINGS_PATH),
        profile_path=str(DEFAULT_PROFILE_PATH),
        trading_days=21,
    )

    formatted_json = json.dumps(snapshot, ensure_ascii=False, indent=2)
    print(formatted_json)

    DEFAULT_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT_PATH.write_text(formatted_json + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

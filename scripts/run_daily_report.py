from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from reports.daily_report import (
    build_daily_report_json,
    load_json,
    render_daily_report_markdown,
)


REPORT_DIR = PROJECT_ROOT / "outputs" / "reports"
PORTFOLIO_SNAPSHOT_PATH = REPORT_DIR / "portfolio_snapshot.json"
MARKET_SNAPSHOT_PATH = REPORT_DIR / "market_snapshot.json"
MARKET_TEMPERATURE_PATH = REPORT_DIR / "market_temperature.json"
DAILY_REPORT_JSON_PATH = REPORT_DIR / "daily_report.json"
DAILY_REPORT_MD_PATH = REPORT_DIR / "daily_report.md"

SNAPSHOT_GENERATORS = {
    PORTFOLIO_SNAPSHOT_PATH: PROJECT_ROOT / "scripts" / "run_portfolio_check.py",
    MARKET_SNAPSHOT_PATH: PROJECT_ROOT / "scripts" / "run_market_data_check.py",
    MARKET_TEMPERATURE_PATH: PROJECT_ROOT / "scripts" / "run_market_temperature_check.py",
}


def main() -> None:
    _ensure_snapshot_files()

    portfolio_snapshot = load_json(str(PORTFOLIO_SNAPSHOT_PATH))
    market_snapshot = load_json(str(MARKET_SNAPSHOT_PATH))
    market_temperature = load_json(str(MARKET_TEMPERATURE_PATH))

    report_json = build_daily_report_json(
        portfolio_snapshot=portfolio_snapshot,
        market_snapshot=market_snapshot,
        market_temperature=market_temperature,
    )
    report_markdown = render_daily_report_markdown(report_json)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    DAILY_REPORT_JSON_PATH.write_text(
        "\ufeff" + json.dumps(report_json, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    DAILY_REPORT_MD_PATH.write_text("\ufeff" + report_markdown + "\n", encoding="utf-8")

    print(report_markdown)


def _ensure_snapshot_files() -> None:
    for output_path, script_path in SNAPSHOT_GENERATORS.items():
        if output_path.exists():
            continue

        subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(PROJECT_ROOT),
            check=True,
            capture_output=True,
            text=True,
        )


if __name__ == "__main__":
    main()

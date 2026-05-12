from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = PROJECT_ROOT / "outputs" / "archive"

REPORT_FILES = [
    "outputs/reports/portfolio_snapshot.json",
    "outputs/reports/market_snapshot.json",
    "outputs/reports/market_temperature.json",
    "outputs/reports/daily_report.json",
    "outputs/reports/daily_report.md",
    "outputs/reports/market_history_features.json",
    "outputs/reports/macro_regime_history.json",
    "outputs/reports/macro_regime_history.md",
    "outputs/reports/llm_context_pack.json",
    "outputs/reports/llm_context_pack.md",
]

RETENTION_POLICY = {
    "logs_retention_days": 30,
    "archive_retention_days": 365,
    "market_raw_cache_retention_days": 30,
    "enforcement": "not_implemented",
    "note": "Retention is recorded for future cleanup. This script does not delete files.",
}

METHODOLOGY_NOTE = (
    "Copies deterministic report outputs from outputs/reports into a date-based archive. "
    "Same-day runs overwrite files with the same names. Raw history JSON caches are not copied. "
    "Historical outcomes are descriptive references only and are not forecasts."
)


def main() -> None:
    summary = archive_reports()
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def archive_reports(archive_date: str | None = None) -> dict[str, Any]:
    archive_date = archive_date or _local_today()
    archive_dir = ARCHIVE_ROOT / archive_date
    archive_dir.mkdir(parents=True, exist_ok=True)

    copied_files = []
    missing_files = []
    source_paths = {}

    for relative_path in REPORT_FILES:
        source_path = PROJECT_ROOT / relative_path
        archive_path = archive_dir / source_path.name
        source_paths[relative_path] = str(source_path)

        if not source_path.exists():
            missing_files.append(
                {
                    "source_path": str(source_path),
                    "archive_path": str(archive_path),
                    "status": "missing",
                }
            )
            continue

        overwritten = archive_path.exists()
        shutil.copy2(source_path, archive_path)
        copied_files.append(
            {
                "source_path": str(source_path),
                "archive_path": str(archive_path),
                "overwritten": overwritten,
            }
        )

    manifest_path = archive_dir / "archive_manifest.json"
    manifest = {
        "generated_at": _utc_now(),
        "archive_date": archive_date,
        "archive_path": str(archive_dir),
        "overwrite_existing": True,
        "copied_files": copied_files,
        "missing_files": missing_files,
        "source_paths": source_paths,
        "methodology_note": METHODOLOGY_NOTE,
        "retention_policy": RETENTION_POLICY,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    status = "ok" if not missing_files else "completed_with_missing_files"
    return {
        "status": status,
        "generated_at": manifest["generated_at"],
        "archive_date": archive_date,
        "archive_path": str(archive_dir),
        "manifest_path": str(manifest_path),
        "copied_file_count": len(copied_files),
        "missing_file_count": len(missing_files),
        "copied_files": copied_files,
        "missing_files": missing_files,
        "overwrite_existing": True,
        "retention_policy": RETENTION_POLICY,
    }


def _local_today() -> str:
    return datetime.now().date().isoformat()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    main()

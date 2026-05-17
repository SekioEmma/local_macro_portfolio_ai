from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from reports.llm_context_pack import (
    build_llm_context_pack,
    load_json,
    load_text,
    render_llm_context_markdown,
)


INPUT_FILES = {
    "portfolio_snapshot": PROJECT_ROOT / "outputs" / "reports" / "portfolio_snapshot.json",
    "market_snapshot": PROJECT_ROOT / "outputs" / "reports" / "market_snapshot.json",
    "market_temperature": PROJECT_ROOT / "outputs" / "reports" / "market_temperature.json",
    "daily_report_md": PROJECT_ROOT / "outputs" / "reports" / "daily_report.md",
    "market_history_features": PROJECT_ROOT / "outputs" / "reports" / "market_history_features.json",
    "macro_regime_history": PROJECT_ROOT / "outputs" / "reports" / "macro_regime_history.json",
}

JSON_OUTPUT_PATH = PROJECT_ROOT / "outputs" / "reports" / "llm_context_pack.json"
MD_OUTPUT_PATH = PROJECT_ROOT / "outputs" / "reports" / "llm_context_pack.md"


def main() -> None:
    portfolio_snapshot = load_json(str(INPUT_FILES["portfolio_snapshot"]))
    market_snapshot = load_json(str(INPUT_FILES["market_snapshot"]))
    market_temperature = load_json(str(INPUT_FILES["market_temperature"]))
    daily_report = load_text(str(INPUT_FILES["daily_report_md"]))
    market_history_features = load_json(str(INPUT_FILES["market_history_features"]))
    macro_regime_history = load_json(str(INPUT_FILES["macro_regime_history"]))

    missing = _missing_inputs(
        {
            "portfolio_snapshot": portfolio_snapshot,
            "market_snapshot": market_snapshot,
            "market_temperature": market_temperature,
            "daily_report_md": daily_report,
            "market_history_features": market_history_features,
            "macro_regime_history": macro_regime_history,
        }
    )
    if missing:
        print(
            json.dumps(
                {
                    "status": "input_missing",
                    "missing_or_invalid_inputs": missing,
                    "hint": "Run the corresponding report scripts before generating the LLM context pack.",
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    context_pack = build_llm_context_pack(
        portfolio_snapshot=portfolio_snapshot,
        market_snapshot=market_snapshot,
        market_temperature=market_temperature,
        daily_report_md=daily_report.get("content", "") if isinstance(daily_report, dict) else "",
        market_history_features=market_history_features,
        macro_regime_history=macro_regime_history,
    )
    markdown = render_llm_context_markdown(context_pack)

    JSON_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUTPUT_PATH.write_text(
        "\ufeff" + json.dumps(context_pack, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    MD_OUTPUT_PATH.write_text(markdown, encoding="utf-8-sig")

    print(
        json.dumps(
            {
                "status": "ok",
                "generated_at": context_pack.get("generated_at"),
                "source_file_count": len(context_pack.get("source_files", [])),
                "data_limitation_count": len(context_pack.get("data_limitations", [])),
                "output_files": [
                    str(JSON_OUTPUT_PATH),
                    str(MD_OUTPUT_PATH),
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _missing_inputs(payloads: dict[str, dict]) -> list[dict]:
    missing = []
    for key, payload in payloads.items():
        if not isinstance(payload, dict):
            missing.append({"key": key, "status": "error", "error": "Invalid loader result"})
            continue
        if payload.get("status") in {"missing", "error"}:
            missing.append(
                {
                    "key": key,
                    "status": payload.get("status"),
                    "path": payload.get("path"),
                    "error": payload.get("error"),
                }
            )
    return missing


if __name__ == "__main__":
    main()

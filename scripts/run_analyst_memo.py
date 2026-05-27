from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from llm.analyst_memo_provider import generate_analyst_memo, write_analyst_memo_outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a DeepSeek analyst memo from the local context pack.")
    parser.add_argument("--provider", choices=["deepseek-pro", "deepseek-flash", "qwen-local"], default=None)
    parser.add_argument("--context-mode", choices=["sanitized", "full"], default=None)
    parser.add_argument("--question", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--config", default=None)
    parser.add_argument("--context-path", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = generate_analyst_memo(
        question=args.question,
        provider=args.provider,
        context_mode=args.context_mode,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
        config_path=args.config,
        context_path=args.context_path,
    )
    paths = write_analyst_memo_outputs(result, args.output_dir)
    flags = result.get("validator_flags") if isinstance(result.get("validator_flags"), dict) else {}
    summary = {
        "status": result.get("status"),
        "provider": result.get("provider"),
        "provider_id": result.get("provider_id"),
        "model": result.get("model"),
        "context_mode": result.get("context_mode"),
        "dry_run": args.dry_run,
        "latency_seconds": result.get("latency_seconds"),
        "usage": result.get("usage"),
        "estimated_cost_cny": result.get("estimated_cost_cny"),
        "has_hard_flag": flags.get("has_hard_flag"),
        "has_soft_flag": flags.get("has_soft_flag"),
        "hard_flags": flags.get("hard_flags"),
        "soft_flags": flags.get("soft_flags"),
        "human_review_required": result.get("requires_human_review"),
        "json_path": paths.get("json_path"),
        "markdown_path": paths.get("markdown_path"),
        "error": result.get("error"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if result.get("status") in {"ok", "needs_review"} or args.dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())

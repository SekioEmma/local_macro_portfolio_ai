from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError:
    yaml = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from llm.context_loader import (
    load_context_pack,
    summarize_data_limitations,
    validate_context_health,
)
from llm.local_llm_client import call_local_llm
from llm.prompt_builder import build_answer_prompt


CONFIG_PATH = PROJECT_ROOT / "configs" / "llm.yaml"
REPORT_DIR = PROJECT_ROOT / "outputs" / "reports"
CONTEXT_MD_PATH = REPORT_DIR / "llm_context_pack.md"
CONTEXT_JSON_PATH = REPORT_DIR / "llm_context_pack.json"
PROMPT_OUTPUT_PATH = REPORT_DIR / "latest_llm_prompt.md"
ANSWER_OUTPUT_PATH = REPORT_DIR / "latest_llm_answer.md"


def main() -> None:
    user_question = _read_user_question(sys.argv[1:])
    if not user_question:
        _print_summary(
            {
                "status": "error",
                "mode": None,
                "prompt_path": None,
                "answer_path": None,
                "data_limitations": [],
                "error": "Missing user question.",
            }
        )
        raise SystemExit(1)

    config_result = _load_config(CONFIG_PATH)
    config = config_result.get("config", {})
    mode = config.get("local_llm", {}).get("mode", "prompt_only") if isinstance(config, dict) else "prompt_only"
    context_policy = config.get("context_policy", {}) if isinstance(config, dict) else {}

    context_pack = load_context_pack(str(CONTEXT_MD_PATH), str(CONTEXT_JSON_PATH))
    if config_result.get("status") != "ok":
        context_pack.setdefault("data_limitations", []).append(
            f"llm_config: {config_result.get('error')}"
        )
    context_pack["context_health"] = validate_context_health(
        context_pack.get("context_json", {}),
        context_policy,
    )
    context_pack["compressed_data_limitations"] = summarize_data_limitations(
        context_pack.get("data_limitations", [])
    )

    prompt = build_answer_prompt(user_question, context_pack, config)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    _write_utf8_markdown(PROMPT_OUTPUT_PATH, prompt)

    context_health = context_pack.get("context_health", {})
    if mode == "local_http" and not context_health.get("should_allow_model_call", False):
        result = {
            "status": "blocked_degraded_context",
            "prompt": prompt,
            "answer": None,
            "error": "Context health does not allow model calls. Set context_policy.allow_degraded_context=true to override.",
        }
    else:
        result = call_local_llm(prompt, config)
    answer_path = None

    if mode == "prompt_only":
        print(f"Prompt saved to: {PROMPT_OUTPUT_PATH}")
        print(
            json.dumps(
                {
                    "mode": "prompt_only",
                    "prompt_chars": len(prompt),
                    "context_status": context_pack.get("status"),
                    "context_health_status": context_health.get("status"),
                    "should_allow_model_call": context_health.get("should_allow_model_call"),
                    "data_limitation_count": len(context_pack.get("data_limitations", [])),
                    "compressed_data_limitation_count": len(
                        context_pack.get("compressed_data_limitations", [])
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif mode == "local_http" and result.get("answer"):
        answer_path = str(ANSWER_OUTPUT_PATH)
        _write_utf8_markdown(ANSWER_OUTPUT_PATH, result["answer"])
        print(result["answer"])
    elif mode == "local_http":
        print(
            json.dumps(
                {
                    "status": result.get("status"),
                    "error": result.get("error"),
                    "context_health": context_health,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    summary = {
        "status": result.get("status"),
        "mode": mode,
        "prompt_path": str(PROMPT_OUTPUT_PATH),
        "answer_path": answer_path,
        "context_health": context_health,
        "data_limitation_count": len(context_pack.get("data_limitations", [])),
        "data_limitations": context_pack.get("compressed_data_limitations", []),
    }
    if result.get("error"):
        summary["error"] = result["error"]

    _print_summary(summary)

    if result.get("status") == "error":
        raise SystemExit(1)


def _read_user_question(args: list[str]) -> str:
    if args:
        return " ".join(args).strip()
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    return ""


def _load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "status": "error",
            "config": _default_config(),
            "error": f"Config file not found: {path}",
        }

    try:
        raw_text = path.read_text(encoding="utf-8-sig")
        data = yaml.safe_load(raw_text) if yaml is not None else _parse_simple_yaml(raw_text)
        data = data or {}
    except OSError as exc:
        return {
            "status": "error",
            "config": _default_config(),
            "error": f"Could not load config: {exc}",
        }
    except Exception as exc:
        return {
            "status": "error",
            "config": _default_config(),
            "error": f"Could not parse config: {exc}",
        }

    if not isinstance(data, dict):
        return {
            "status": "error",
            "config": _default_config(),
            "error": "Config root must be an object.",
        }

    return {
        "status": "ok",
        "config": data,
        "error": None,
    }


def _default_config() -> dict[str, Any]:
    return {
        "local_llm": {
            "mode": "prompt_only",
            "provider": "generic_local_http",
            "endpoint": "http://localhost:11434/api/generate",
            "model": "local-model",
            "timeout_seconds": 120,
            "temperature": 0.2,
            "max_context_chars": 60000,
        },
        "prompt_policy": {
            "language": "zh-CN",
            "require_source_awareness": True,
            "forbid_forecast_claims": True,
            "forbid_trade_commands": True,
            "require_uncertainty_section": True,
        },
        "context_policy": {
            "allow_degraded_context": False,
            "max_data_limitations_for_model_call": 20,
            "allow_sample_fallback": True,
        },
    }


def _parse_simple_yaml(raw_text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    current_section: str | None = None

    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if not line.startswith(" ") and stripped.endswith(":"):
            current_section = stripped[:-1]
            result[current_section] = {}
            continue

        if current_section is None or ":" not in stripped:
            continue

        key, value = stripped.split(":", 1)
        result[current_section][key.strip()] = _parse_scalar(value.strip())

    return result


def _parse_scalar(value: str) -> Any:
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False

    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _print_summary(summary: dict[str, Any]) -> None:
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _write_utf8_markdown(path: Path, content: str) -> None:
    # The leading BOM keeps Windows PowerShell Get-Content -Raw from treating UTF-8 as ANSI.
    path.write_text("\ufeff" + content, encoding="utf-8")


if __name__ == "__main__":
    main()

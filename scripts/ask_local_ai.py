from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

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
from llm.local_llm_client import call_local_llm, check_ollama_health
from llm.prompt_builder import (
    build_answer_prompt,
    build_compact_answer_prompt,
    build_compact_repair_prompt,
    build_validation_repair_prompt,
)
from eval.answer_evaluator import evaluate_answer


CONFIG_PATH = PROJECT_ROOT / "configs" / "llm.yaml"
REPORT_DIR = PROJECT_ROOT / "outputs" / "reports"
ANSWER_ARCHIVE_ROOT = PROJECT_ROOT / "outputs" / "answers"
CONTEXT_MD_PATH = REPORT_DIR / "llm_context_pack.md"
CONTEXT_JSON_PATH = REPORT_DIR / "llm_context_pack.json"
PROMPT_OUTPUT_PATH = REPORT_DIR / "latest_llm_prompt.md"
ANSWER_OUTPUT_PATH = REPORT_DIR / "latest_llm_answer.md"
FORBIDDEN_ANSWER_PATTERNS = [
    "保证收益",
    "一定会涨",
    "明天会涨",
    "立即买入",
    "满仓",
    "清仓",
]


def main() -> None:
    parsed_args = _parse_cli_args(sys.argv[1:])
    user_question = parsed_args["question"]
    eval_case = parsed_args["eval_case"]
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
    config = _apply_cli_overrides(config, parsed_args)
    mode = config.get("local_llm", {}).get("mode", "prompt_only") if isinstance(config, dict) else "prompt_only"
    context_policy = config.get("context_policy", {}) if isinstance(config, dict) else {}
    compact_prompt = bool(parsed_args.get("compact_prompt"))

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

    repair_context = eval_case.get("repair_context") if isinstance(eval_case, dict) else None
    if isinstance(repair_context, dict):
        prompt = _build_repair_prompt(
            user_question=user_question,
            context_pack=context_pack,
            validation_warnings=repair_context.get("warnings", []),
            eval_case=eval_case,
            original_answer=repair_context.get("original_answer"),
            missing_required_terms=repair_context.get("missing_required_terms", []),
            forbidden_hits=repair_context.get("forbidden_hits", []),
            compact_prompt=compact_prompt,
        )
    else:
        prompt = _build_answer_prompt(
            user_question=user_question,
            context_pack=context_pack,
            config=config,
            eval_case=eval_case,
            compact_prompt=compact_prompt,
        )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    _write_utf8_markdown(PROMPT_OUTPUT_PATH, prompt)

    context_health = context_pack.get("context_health", {})
    ollama_health = None
    if mode == "local_http" and not context_health.get("should_allow_model_call", False):
        result = {
            "status": "blocked_degraded_context",
            "provider": config.get("local_llm", {}).get("provider"),
            "model": config.get("local_llm", {}).get("model"),
            "prompt": prompt,
            "answer": None,
            "removed_thinking": False,
            "cleaning_notes": [],
            "error": "Context health does not allow model calls. Set context_policy.allow_degraded_context=true to override.",
            "raw_metadata": {},
        }
    else:
        if mode == "local_http":
            ollama_health = check_ollama_health(config)
            if ollama_health.get("status") not in {"ok", "skipped"}:
                result = {
                    "status": "ollama_health_error",
                    "provider": config.get("local_llm", {}).get("provider"),
                    "model": config.get("local_llm", {}).get("model"),
                    "prompt": prompt,
                    "answer": None,
                    "removed_thinking": False,
                    "cleaning_notes": [],
                    "error": ollama_health.get("error") or ollama_health.get("hint"),
                    "raw_metadata": {
                        "ollama_health": ollama_health,
                    },
                }
            else:
                result = call_local_llm(prompt, config)
        else:
            result = call_local_llm(prompt, config)

    if result.get("answer"):
        guarded = _apply_deterministic_answer_guardrails(
            result["answer"],
            context_pack,
        )
        result["answer"] = guarded["answer"]
        if guarded["notes"]:
            result["cleaning_notes"] = [
                *result.get("cleaning_notes", []),
                *guarded["notes"],
            ]

    first_result = result
    first_answer_validation = _build_answer_validation(
        result.get("answer") or "",
        user_question=user_question,
        context_json=context_pack.get("context_json", {}),
        eval_case=eval_case,
    )
    final_answer_validation = first_answer_validation
    repair_used = False
    repair_success = False
    first_prompt = prompt
    answer_path = None
    archive_paths = {}

    if (
        mode == "local_http"
        and result.get("status") == "ok"
        and _validation_needs_repair(first_answer_validation)
    ):
        repair_used = True
        repair_prompt = _build_repair_prompt(
            user_question=user_question,
            context_pack=context_pack,
            validation_warnings=first_answer_validation.get("warnings", []),
            eval_case=_case_with_repair_context(
                eval_case,
                result.get("answer") or "",
                first_answer_validation,
            ),
            original_answer=result.get("answer"),
            missing_required_terms=first_answer_validation.get("missing_required_terms", []),
            forbidden_hits=first_answer_validation.get("forbidden_hits", []),
            compact_prompt=compact_prompt,
        )
        _write_utf8_markdown(PROMPT_OUTPUT_PATH, repair_prompt)
        retry_result = call_local_llm(repair_prompt, config)
        if retry_result.get("answer"):
            guarded = _apply_deterministic_answer_guardrails(
                retry_result["answer"],
                context_pack,
            )
            retry_result["answer"] = guarded["answer"]
            retry_notes = [
                "Retried with compact validation repair prompt.",
                *retry_result.get("cleaning_notes", []),
                *guarded["notes"],
            ]
            retry_result["cleaning_notes"] = retry_notes
            retry_validation = _build_answer_validation(
                retry_result.get("answer") or "",
                user_question=user_question,
                context_json=context_pack.get("context_json", {}),
                eval_case=eval_case,
            )
            result = retry_result
            final_answer_validation = retry_validation
            repair_success = _validation_is_pass(retry_validation)
            prompt = repair_prompt

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
                    "ollama_health": ollama_health,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    if mode == "local_http" and _save_answer_archive(config):
        archive_paths = _archive_answer_run(
            question=user_question,
            prompt=prompt,
            answer=result.get("answer"),
            result=result,
            config=config,
            context_health=context_health,
            answer_validation=final_answer_validation,
        )

    summary = {
        "status": result.get("status"),
        "mode": mode,
        "provider": result.get("provider"),
        "model": result.get("model"),
        "prompt_path": str(PROMPT_OUTPUT_PATH),
        "answer_path": answer_path,
        "archive_paths": archive_paths,
        "context_health": context_health,
        "ollama_health": ollama_health,
        "data_limitation_count": len(context_pack.get("data_limitations", [])),
        "data_limitations": context_pack.get("compressed_data_limitations", []),
        "compact_prompt": compact_prompt,
        "first_removed_thinking": first_result.get("removed_thinking", False),
        "final_removed_thinking": result.get("removed_thinking", False),
        "removed_thinking": result.get("removed_thinking", False),
        "cleaning_notes": result.get("cleaning_notes", []),
        "first_answer_validation": first_answer_validation,
        "final_answer_validation": final_answer_validation,
        "answer_validation": final_answer_validation,
        "repair_used": repair_used,
        "repair_success": repair_success,
        "first_prompt_chars": len(first_prompt),
        "final_prompt_chars": len(prompt),
    }
    if eval_case:
        summary["eval_case_id"] = eval_case.get("id")
    if result.get("error"):
        summary["error"] = result["error"]

    _print_summary(summary)

    if result.get("status") == "error":
        raise SystemExit(1)


def _parse_cli_args(args: list[str]) -> dict[str, Any]:
    question_parts = []
    eval_case = None
    overrides: dict[str, Any] = {}
    compact_prompt = False
    index = 0
    while index < len(args):
        item = args[index]
        if item == "--eval-case-json":
            if index + 1 >= len(args):
                raise SystemExit("--eval-case-json requires a JSON value.")
            try:
                parsed = json.loads(args[index + 1])
            except json.JSONDecodeError as exc:
                raise SystemExit(f"Invalid --eval-case-json value: {exc}") from exc
            if not isinstance(parsed, dict):
                raise SystemExit("--eval-case-json must decode to an object.")
            eval_case = parsed
            index += 2
            continue
        if item == "--model":
            if index + 1 >= len(args):
                raise SystemExit("--model requires a value.")
            overrides["model"] = args[index + 1]
            index += 2
            continue
        if item == "--num-ctx":
            if index + 1 >= len(args):
                raise SystemExit("--num-ctx requires a value.")
            overrides["num_ctx"] = _parse_positive_int(args[index + 1], "--num-ctx")
            index += 2
            continue
        if item == "--max-context-chars":
            if index + 1 >= len(args):
                raise SystemExit("--max-context-chars requires a value.")
            overrides["max_context_chars"] = _parse_positive_int(
                args[index + 1],
                "--max-context-chars",
            )
            index += 2
            continue
        if item in {"--compact-prompt", "--compact-context"}:
            compact_prompt = True
            index += 1
            continue
        question_parts.append(item)
        index += 1

    question = _read_user_question(question_parts)
    return {
        "question": question,
        "eval_case": eval_case,
        "overrides": overrides,
        "compact_prompt": compact_prompt,
    }


def _parse_positive_int(value: str, flag_name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise SystemExit(f"{flag_name} must be an integer.") from exc
    if parsed <= 0:
        raise SystemExit(f"{flag_name} must be positive.")
    return parsed


def _apply_cli_overrides(config: dict[str, Any], parsed_args: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(config, dict):
        config = _default_config()
    overrides = parsed_args.get("overrides", {})
    if not isinstance(overrides, dict) or not overrides:
        return config

    local_llm = config.setdefault("local_llm", {})
    if not isinstance(local_llm, dict):
        local_llm = {}
        config["local_llm"] = local_llm

    for key in ("model", "num_ctx", "max_context_chars"):
        if key in overrides:
            local_llm[key] = overrides[key]
    return config


def _build_answer_prompt(
    user_question: str,
    context_pack: dict[str, Any],
    config: dict[str, Any],
    eval_case: dict[str, Any] | None,
    compact_prompt: bool,
) -> str:
    if compact_prompt:
        return build_compact_answer_prompt(
            user_question,
            context_pack,
            config,
            eval_case=eval_case,
        )
    return build_answer_prompt(user_question, context_pack, config, eval_case=eval_case)


def _build_repair_prompt(
    user_question: str,
    context_pack: dict[str, Any],
    validation_warnings: list[str],
    eval_case: dict[str, Any] | None,
    original_answer: str | None,
    missing_required_terms: list[str],
    forbidden_hits: list[str],
    compact_prompt: bool,
) -> str:
    if compact_prompt:
        return build_compact_repair_prompt(
            user_question=user_question,
            context_pack=context_pack,
            validation_warnings=validation_warnings,
            eval_case=eval_case,
            original_answer=original_answer,
            missing_required_terms=missing_required_terms,
            forbidden_hits=forbidden_hits,
        )
    return build_validation_repair_prompt(
        user_question=user_question,
        context_pack=context_pack,
        validation_warnings=validation_warnings,
        eval_case=eval_case,
        original_answer=original_answer,
        missing_required_terms=missing_required_terms,
        forbidden_hits=forbidden_hits,
    )


def _build_answer_validation(
    answer: str,
    user_question: str,
    context_json: dict[str, Any],
    eval_case: dict[str, Any] | None,
) -> dict[str, Any]:
    guardrail = validate_answer_text(
        answer,
        user_question=user_question,
        context_json=context_json,
    )
    evaluator = evaluate_answer(answer, eval_case) if isinstance(eval_case, dict) else None

    warnings = list(guardrail.get("warnings", []))
    forbidden_hits: list[str] = []
    missing_required_terms: list[str] = []
    status = "pass"

    if guardrail.get("status") == "warning":
        status = "warning"

    if isinstance(evaluator, dict):
        forbidden_hits = list(evaluator.get("forbidden_hits", []))
        missing_required_terms = _missing_required_terms_list(evaluator)
        if evaluator.get("warnings"):
            warnings.extend(str(item) for item in evaluator.get("warnings", []))
        if evaluator.get("status") == "fail":
            status = "fail"
        elif evaluator.get("status") == "warning" and status == "pass":
            status = "warning"

    if not answer.strip():
        status = "fail"

    return {
        "status": status,
        "warnings": _dedupe_strings(warnings),
        "missing_required_terms": missing_required_terms,
        "forbidden_hits": forbidden_hits,
        "guardrail_validation": guardrail,
        "evaluator": evaluator,
    }


def _validation_needs_repair(validation: dict[str, Any]) -> bool:
    return validation.get("status") in {"fail", "warning"}


def _validation_is_pass(validation: dict[str, Any]) -> bool:
    return validation.get("status") == "pass"


def _case_with_repair_context(
    eval_case: dict[str, Any] | None,
    original_answer: str,
    validation: dict[str, Any],
) -> dict[str, Any] | None:
    if not isinstance(eval_case, dict):
        return None
    return {
        **eval_case,
        "repair_context": {
            "evaluator_status": validation.get("status"),
            "original_answer": original_answer,
            "missing_required_terms": validation.get("missing_required_terms", []),
            "forbidden_hits": validation.get("forbidden_hits", []),
            "warnings": validation.get("warnings", []),
        },
    }


def _missing_required_terms_list(result: dict[str, Any]) -> list[str]:
    missing = []
    for check in result.get("required_checks", []):
        if check.get("status") == "fail":
            missing.append("/".join(str(term) for term in check.get("terms_any", [])))
    return missing


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
            "mode": "local_http",
            "provider": "ollama",
            "endpoint": "http://localhost:11434/api/generate",
            "model": "gemma4:e2b",
            "timeout_seconds": 240,
            "temperature": 0.1,
            "top_p": 0.9,
            "num_ctx": 4096,
            "max_context_chars": 16000,
            "save_answer_archive": True,
            "strip_thinking_output": True,
        },
        "prompt_policy": {
            "language": "zh-CN",
            "require_source_awareness": True,
            "forbid_forecast_claims": True,
            "forbid_trade_commands": True,
            "require_uncertainty_section": True,
            "require_sample_fallback_warning": True,
            "require_context_only_answer": True,
            "forbid_thinking_process_output": True,
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


def validate_answer_text(
    answer: str,
    user_question: str = "",
    context_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    warnings = []
    if not answer:
        return {
            "status": "not_applicable",
            "warnings": warnings,
        }

    for pattern in FORBIDDEN_ANSWER_PATTERNS:
        if pattern in answer:
            warnings.append(f"Forbidden phrase detected: {pattern}")

    amount_patterns = [
        r"买入\s*[\d,]+(?:\.\d+)?\s*(?:元|人民币|块)",
        r"卖出\s*[\d,]+(?:\.\d+)?\s*(?:元|人民币|块)",
    ]
    for pattern in amount_patterns:
        if re.search(pattern, answer):
            warnings.append(f"Forbidden trade amount pattern detected: {pattern}")

    context_json = context_json or {}
    holdings_source = _find_holdings_source(context_json)
    if holdings_source.get("mode"):
        ignore_portfolio_patterns = [
            r"未提供您的投资组合",
            r"没有提供投资组合",
            r"无法评估.*组合",
            r"缺乏.*组合",
            r"未包含.*组合",
        ]
        for pattern in ignore_portfolio_patterns:
            if re.search(pattern, answer):
                warnings.append("Answer appears to ignore portfolio facts.")
                break

    question_lower = user_question.lower()
    answer_lower = answer.lower()
    if "组合" in user_question:
        portfolio_keywords = [
            "sp500",
            "nasdaq100",
            "short_bond",
            "gold",
            "underweight",
            "overweight",
            "低配",
            "高配",
        ]
        if not any(keyword in answer_lower or keyword in answer for keyword in portfolio_keywords):
            warnings.append("Answer does not reference portfolio allocation facts.")

    if "过热" in user_question:
        market_keywords = [
            "warm_but_macro_sensitive",
            "equity_temperature",
            "risk_level",
            "偏热",
            "过热",
        ]
        if not any(keyword in answer_lower or keyword in answer for keyword in market_keywords):
            warnings.append("Answer does not reference market temperature facts.")

    return {
        "status": "warning" if warnings else "ok",
        "warnings": _dedupe_strings(warnings),
    }


def _apply_deterministic_answer_guardrails(
    answer: str,
    context_pack: dict[str, Any],
) -> dict[str, Any]:
    notes = []
    updated = answer.strip()
    context_json = context_pack.get("context_json", {}) if isinstance(context_pack, dict) else {}
    holdings_source = _find_holdings_source(context_json)

    if holdings_source.get("mode") == "sample_fallback" and not _mentions_sample_fallback(updated):
        prefix = (
            "重要说明：当前账户数据来自 sample_fallback（示例持仓），不是真实账户数据；"
            "以下内容只基于 context pack 做本地研究说明，不构成投资建议。\n\n"
        )
        updated = prefix + updated
        notes.append("Prepended required sample_fallback warning.")

    return {
        "answer": updated,
        "notes": notes,
    }


def _mentions_sample_fallback(answer: str) -> bool:
    lower = answer.lower()
    return (
        "sample_fallback" in lower
        or "示例持仓" in answer
        or "不是真实账户" in answer
        or "非真实账户" in answer
    )


def _find_holdings_source(context_json: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(context_json, dict):
        return {}
    candidates = [
        context_json.get("portfolio_context", {}).get("holdings_source", {}),
        context_json.get("confirmed_facts", {}).get("portfolio", {}).get("holdings_source", {}),
        context_json.get("data_quality", {}).get("portfolio_holdings_source", {}),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate:
            return candidate
    return {}


def _dedupe_strings(items: list[str]) -> list[str]:
    result = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _archive_answer_run(
    question: str,
    prompt: str,
    answer: str | None,
    result: dict[str, Any],
    config: dict[str, Any],
    context_health: dict[str, Any],
    answer_validation: dict[str, Any],
) -> dict[str, str]:
    now = datetime.now()
    archive_dir = ANSWER_ARCHIVE_ROOT / now.strftime("%Y-%m-%d")
    archive_dir.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%H%M%S")

    prompt_path = archive_dir / f"{stamp}_prompt.md"
    answer_path = archive_dir / f"{stamp}_answer.md"
    manifest_path = archive_dir / f"{stamp}_manifest.json"

    _write_utf8_markdown(prompt_path, prompt)
    if answer is not None:
        _write_utf8_markdown(answer_path, answer)

    local_config = config.get("local_llm", {}) if isinstance(config, dict) else {}
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "question": question,
        "provider": result.get("provider") or local_config.get("provider"),
        "model": result.get("model") or local_config.get("model"),
        "context_health": context_health,
        "status": result.get("status"),
        "error": result.get("error"),
        "removed_thinking": result.get("removed_thinking", False),
        "cleaning_notes": result.get("cleaning_notes", []),
        "answer_validation": answer_validation,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    paths = {
        "prompt": str(prompt_path),
        "manifest": str(manifest_path),
    }
    if answer is not None:
        paths["answer"] = str(answer_path)
    return paths


def _save_answer_archive(config: dict[str, Any]) -> bool:
    local_config = config.get("local_llm", {}) if isinstance(config, dict) else {}
    return bool(local_config.get("save_answer_archive", False))


def _print_summary(summary: dict[str, Any]) -> None:
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _write_utf8_markdown(path: Path, content: str) -> None:
    # The leading BOM keeps Windows PowerShell Get-Content -Raw from treating UTF-8 as ANSI.
    path.write_text("\ufeff" + content, encoding="utf-8")


if __name__ == "__main__":
    main()

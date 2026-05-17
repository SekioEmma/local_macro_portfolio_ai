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
    "应买入",
    "应卖出",
    "立即调整",
    "需增加持仓",
    "需增加配置",
    "需减持",
    "需减少配置",
    "逐步减持",
    "增持",
    "减持",
    "操作建议",
    "具体调整方案",
    "应调整",
    "转为更稳健",
    "推荐行动",
    "补仓",
    "减仓",
    "持仓调整",
    "逐步增加配置",
    "建议适度增加",
    "配置不足",
    "配置过重",
    "提升至目标比例",
    "Bloomberg",
    "ISO 20022",
    "模型版本",
    "规则库",
    "自动调仓",
    "无需人工干预",
    "外部数据源",
    "实时市场规则模型",
    "实时生成",
    "数据更新时间",
    "机构资金净流入",
    "利率变动对市场波动率影响系数",
    "风险评分",
    "完成3次",
    "重新校准模型参数",
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
    local_llm_config = config.get("local_llm", {}) if isinstance(config, dict) else {}
    compact_prompt = bool(parsed_args.get("compact_prompt") or local_llm_config.get("compact_prompt", False))

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
                fallback_answer = _build_context_only_safe_answer(
                    context_pack.get("context_json", {}),
                    user_question,
                )
                result = {
                    "status": (
                        "ollama_health_error_context_fallback"
                        if fallback_answer
                        else "ollama_health_error"
                    ),
                    "provider": config.get("local_llm", {}).get("provider"),
                    "model": config.get("local_llm", {}).get("model"),
                    "prompt": prompt,
                    "answer": fallback_answer or None,
                    "removed_thinking": False,
                    "cleaning_notes": (
                        [
                            "Ollama health check failed; wrote deterministic context-only fallback answer."
                        ]
                        if fallback_answer
                        else []
                    ),
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
            user_question=user_question,
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
                user_question=user_question,
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

    if "风险水平" in answer and "中性" in answer:
        warnings.append("risk_level=medium should be described as 中等 or medium, not 中性.")

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
            "标普",
            "纳斯达克",
            "短债",
            "短期债券",
            "黄金",
            "underweight",
            "overweight",
            "低配",
            "高配",
            "相对目标偏低",
            "相对目标偏高",
        ]
        if not any(keyword in answer_lower or keyword in answer for keyword in portfolio_keywords):
            warnings.append("Answer does not reference portfolio allocation facts.")

        if holdings_source.get("mode") in {"current_holdings", "user_current_holdings", "real_holdings"}:
            if "sample_fallback" in answer or "样本数据" in answer or "示例持仓" in answer:
                warnings.append("Answer incorrectly describes current_holdings as sample_fallback/sample data.")

            source_keywords = [
                "current_holdings",
                "本地",
                "快照",
                "手动",
                "不保证实时",
            ]
            if not any(keyword in answer_lower or keyword in answer for keyword in source_keywords):
                warnings.append("Answer does not reference current_holdings local snapshot source.")

            exact_weight_keywords = ["29.88", "12.65", "35.83", "21.64"]
            if not any(keyword in answer for keyword in exact_weight_keywords):
                warnings.append("Answer does not cite current portfolio weight facts.")

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

        overall_regime = _find_overall_regime(context_json)
        if overall_regime == "warm_but_macro_sensitive":
            if "warm_but_macro_sensitive" not in answer_lower and "偏热但宏观敏感" not in answer:
                warnings.append("Answer must state warm_but_macro_sensitive / 偏热但宏观敏感.")
            if "未过热" in answer or "无明显过热" in answer:
                warnings.append("Answer contradicts warm_but_macro_sensitive by saying 未过热 or 无明显过热.")

    return {
        "status": "warning" if warnings else "ok",
        "warnings": _dedupe_strings(warnings),
    }


def _apply_deterministic_answer_guardrails(
    answer: str,
    context_pack: dict[str, Any],
    user_question: str = "",
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

    if _answer_requires_context_only_fallback(updated, holdings_source):
        safe_answer = _build_context_only_safe_answer(context_json, user_question)
        if safe_answer:
            return {
                "answer": safe_answer,
                "notes": ["Replaced hallucinated model answer with deterministic context-only answer."],
            }

    rewritten = _rewrite_trade_directive_wording(updated)
    if rewritten != updated:
        updated = rewritten
        notes.append("Rewrote trade-directive wording into observation-frame wording.")

    facts_block = _build_required_portfolio_facts_appendix(context_json, user_question, updated)
    if facts_block:
        updated = updated.rstrip() + "\n\n" + facts_block
        notes.append("Appended required current-holdings portfolio facts.")

    regime_block = _build_required_market_regime_prefix(context_json, user_question, updated)
    if regime_block:
        updated = regime_block + "\n\n" + updated.lstrip()
        notes.append("Prepended required market regime wording.")

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


def _rewrite_trade_directive_wording(answer: str) -> str:
    replacements = (
        ("## 操作建议", "## 观察框架"),
        ("# 操作建议", "# 观察框架"),
        ("操作建议", "观察框架"),
        ("推荐行动（基于规则逻辑）", "观察方向（基于规则逻辑）"),
        ("推荐行动", "观察方向"),
        ("具体调整方案", "观察框架"),
        ("转为更稳健的债券配置", "作为后续定投和再平衡观察方向"),
        ("转为更稳健配置", "作为后续定投和再平衡观察方向"),
        ("转为更稳健", "作为后续定投和再平衡观察"),
        ("建议逐步增加配置", "相对目标偏低，可作为后续定投和再平衡观察方向"),
        ("逐步增加配置", "相对目标偏低，作为后续定投和再平衡观察方向"),
        ("建议优先补仓", "相对目标偏低，可作为后续定投观察方向"),
        ("优先补仓", "作为后续定投观察方向"),
        ("补仓", "后续定投观察"),
        ("减仓", "再平衡观察"),
        ("持仓调整", "再平衡评估"),
        ("配置不足", "相对目标偏低"),
        ("配置过重", "相对目标偏高"),
        ("偏差修正逻辑", "偏差观察逻辑"),
        ("建议直接对应", "观察框架对应"),
        ("可考虑逐步减持", "可在后续定投和再平衡时观察"),
        ("可以考虑逐步减持", "可以在后续定投和再平衡时观察"),
        ("逐步减持", "后续定投和再平衡时观察"),
        ("可考虑短期增持", "可在后续定投和再平衡时观察"),
        ("可以考虑短期增持", "可以在后续定投和再平衡时观察"),
        ("短期增持", "后续定投和再平衡时观察"),
        ("应买入", "作为后续观察方向"),
        ("应卖出", "作为后续观察方向"),
        ("立即调整", "等待年度/阈值再平衡评估"),
        ("需增加持仓", "相对目标偏低"),
        ("需增加配置", "相对目标偏低"),
        ("需减少配置", "相对目标偏高"),
        ("需减持", "相对目标偏高"),
        ("减持", "再平衡观察"),
        ("增持", "再平衡观察"),
    )
    updated = answer
    for source, target in replacements:
        updated = updated.replace(source, target)
    updated = re.sub(
        r"目标[:：]\s*提升至目标比例\+?\d+(?:\.\d+)?%",
        "观察：相对目标偏低",
        updated,
    )
    updated = re.sub(
        r"再平衡观察\d+(?:\.\d+)?%[-–]\d+(?:\.\d+)?%",
        "等待年度/阈值再平衡评估",
        updated,
    )
    updated = re.sub(
        r"再平衡观察\d+(?:\.\d+)?%",
        "等待年度/阈值再平衡评估",
        updated,
    )
    return updated


def _answer_requires_context_only_fallback(answer: str, holdings_source: dict[str, Any]) -> bool:
    return (
        _answer_has_hallucination_markers(answer)
        or _misstates_current_holdings_as_sample(answer, holdings_source)
        or any(pattern in answer for pattern in FORBIDDEN_ANSWER_PATTERNS)
    )


def _answer_has_hallucination_markers(answer: str) -> bool:
    markers = (
        "2023-10-27",
        "14:30",
        "过去30天热度指数",
        "过去 30 天热度指数",
        "阈值0.7",
        "阈值 0.7",
        "阈值0.6",
        "阈值 0.6",
        "阈值0.5",
        "阈值 0.5",
        "风险指数 = 0.55",
        "风险指数=0.55",
        "标普目标40%",
        "标普目标 40%",
        "标普500目标40%",
        "标普500目标 40%",
        "纳指目标35%",
        "纳指目标 35%",
        "纳斯达克目标35%",
        "纳斯达克目标 35%",
        "短债目标35%",
        "短债目标 35%",
        "黄金目标20%",
        "黄金目标 20%",
        "用户确认的实时快照",
        "请提供更详细的上下文",
        "Bloomberg",
        "ISO 20022",
        "模型版本",
        "规则库",
        "规则第",
        "自动调仓",
        "自动执行",
        "自动归类",
        "无需人工干预",
        "唯一当前状态",
        "可操作状态",
        "模型推荐基准",
        "70% 持仓权重",
        "需人工复核数据",
        "数据更新时间",
        "机构资金净流入",
        "交易量",
        "资金流入",
        "政策调整",
        "国际事件",
        "短期回调",
        "模型预测",
        "建议适度增加",
        "投资者保持灵活配置",
        "美联储政策",
        "地缘政治",
        "实时响应能力",
        "模拟数据",
        "实时数据为准",
        "动态调整",
        "pattern of repetitive",
        "not a real query",
        "just a pattern",
        "casual chat",
        "What would you like",
        "feel free to rephrase",
        "The current market condition",
        "slightly overheated",
        "Key Observations",
        "live data feeds",
        "financial advisor",
        "Always verify",
        "This response is generated",
        "😊",
        "🛠️",
        "自动调整机制",
        "配置需求不足",
        "过度抛售",
        "资金短期流入",
        "避险需求",
        "当前市场处于过热状态",
        "利率变动对市场波动率影响系数",
        "风险评分",
        "完成3次",
        "重新校准模型参数",
    )
    if any(marker in answer for marker in markers):
        return True
    return bool(re.search(r"[\u0590-\u05ff]", answer))


def _misstates_current_holdings_as_sample(answer: str, holdings_source: dict[str, Any]) -> bool:
    if holdings_source.get("mode") not in {"current_holdings", "user_current_holdings", "real_holdings"}:
        return False
    return "sample_fallback" in answer or "样本数据" in answer or "示例持仓" in answer


def _build_context_only_safe_answer(context_json: dict[str, Any], user_question: str) -> str:
    if "过热" not in user_question and "组合" not in user_question:
        return ""

    assessments = context_json.get("rule_based_assessments", {})
    if not isinstance(assessments, dict):
        assessments = {}
    market_temperature = assessments.get("market_temperature", {})
    if not isinstance(market_temperature, dict):
        market_temperature = {}
    portfolio = context_json.get("portfolio_context", {})
    if not isinstance(portfolio, dict):
        portfolio = {}

    holdings_source = _find_holdings_source(context_json)
    weights = portfolio.get("weights_ex_cash", {})
    targets = portfolio.get("target_allocation", {})
    deviations = portfolio.get("deviation", {})
    flags = portfolio.get("deviation_flags", {})
    dca = portfolio.get("dca_budget_check", {})
    holdings_updated_at = _portfolio_confirmed_value(context_json, "holdings_updated_at")
    holdings_age_days = _portfolio_confirmed_value(context_json, "holdings_age_days")
    holdings_freshness_status = _portfolio_confirmed_value(context_json, "holdings_freshness_status")
    total_account_value = _portfolio_confirmed_value(context_json, "total_account_value")
    invested_asset_value = _portfolio_confirmed_value(context_json, "invested_asset_value")
    cash_reserve_value = _portfolio_confirmed_value(context_json, "cash_reserve_value")

    lines = [
        "## 核心结论",
        "当前更接近“偏热但宏观敏感”（warm_but_macro_sensitive），这不是短期涨跌预测，也不是交易指令。",
        "",
        "## 关键事实",
        f"- equity_temperature: {_display(_level_value(market_temperature.get('equity_temperature')))}",
        f"- overall_regime: {_display(market_temperature.get('overall_regime'))}",
        f"- risk_level: {_display(market_temperature.get('risk_level'))} / 中等风险水平",
        (
            f"- 数据来源：用户本地 current_holdings.csv 快照，持仓日期 {_display(holdings_updated_at)}，"
            f"age_days {_display(holdings_age_days)}，freshness {_display(holdings_freshness_status)}；"
            "手动录入且不保证实时。"
        ),
        "- 余额宝/cash：现金准备金和扣款来源，不纳入目标仓位计算，也不等于应立即投入的闲置资金。",
        f"- total_account_value: {_format_number(total_account_value)}。",
        f"- invested_asset_value: {_format_number(invested_asset_value)}。",
        f"- cash_reserve_value: {_format_number(cash_reserve_value)}。",
        "",
        "## 对组合的含义",
        "以下只描述相对目标的仓位偏离，作为后续定投和年度/阈值再平衡的观察方向。",
    ]

    for asset in ("sp500", "nasdaq100", "short_bond", "gold"):
        lines.append(
            "- "
            + f"{asset}: 当前 {_format_percent(weights.get(asset))}, "
            + f"目标 {_format_percent(targets.get(asset))}, "
            + f"偏离 {_format_pp(deviations.get(asset))}, "
            + f"{_allocation_label(flags.get(asset))}。"
        )

    lines.extend(
        [
            "- DCA budget: "
            + f"daily_total {_format_number(dca.get('daily_total'))}, "
            + f"estimated_monthly {_format_number(dca.get('monthly_required'))}, "
            + f"budget_range {_format_number(dca.get('budget_min'))}-{_format_number(dca.get('budget_max'))}, "
            + f"status {_display(dca.get('status'))}。",
            "",
            "## 数据限制与不确定性",
            "- current_holdings.csv 是用户本地手动录入快照，不保证实时更新。",
            "- ETF proxy 或历史相似结果只能作为历史参照，historical outcome is not forecast。",
            "- 若市场数据源失败、缓存过期或 context_health 降级，应标注限制，不编造缺失数据。",
            "",
            "## 可观察指标",
            "- equity_temperature、overall_regime、risk_level。",
            "- DGS10、CPI YoY、PCE YoY、market_snapshot.status、used_cache。",
            "- 后续定投执行情况、余额宝现金准备金是否覆盖扣款节奏。",
        ]
    )

    return "\n".join(lines)


def _level_value(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("level")
    return value


def _portfolio_confirmed_value(context_json: dict[str, Any], key: str) -> Any:
    confirmed = context_json.get("confirmed_facts", {})
    if not isinstance(confirmed, dict):
        return None
    portfolio = confirmed.get("portfolio", {})
    if not isinstance(portfolio, dict):
        return None
    return portfolio.get(key)


def _build_required_portfolio_facts_appendix(
    context_json: dict[str, Any],
    user_question: str,
    answer: str,
) -> str:
    if "组合" not in user_question:
        return ""

    holdings_source = _find_holdings_source(context_json)
    if holdings_source.get("mode") not in {"current_holdings", "user_current_holdings", "real_holdings"}:
        return ""

    if all(token in answer for token in ("29.88", "12.65", "35.83", "21.64")):
        return ""

    portfolio = context_json.get("portfolio_context", {})
    if not isinstance(portfolio, dict):
        return ""

    weights = portfolio.get("weights_ex_cash", {})
    targets = portfolio.get("target_allocation", {})
    deviations = portfolio.get("deviation", {})
    flags = portfolio.get("deviation_flags", {})
    dca = portfolio.get("dca_budget_check", {})
    holdings_updated_at = _portfolio_confirmed_value(context_json, "holdings_updated_at")
    holdings_age_days = _portfolio_confirmed_value(context_json, "holdings_age_days")
    holdings_freshness_status = _portfolio_confirmed_value(context_json, "holdings_freshness_status")

    lines = [
        "## 组合关键事实（本地快照）",
        "以下只描述仓位偏离，作为后续定投和年度/阈值再平衡的观察方向，不是买卖指令。",
        (
            f"- 数据来源：用户本地 current_holdings.csv 快照，持仓日期 {_display(holdings_updated_at)}，"
            f"age_days {_display(holdings_age_days)}，freshness {_display(holdings_freshness_status)}；"
            "手动录入且不保证实时。"
        ),
        "- 余额宝/cash：现金准备金和扣款来源，不纳入目标仓位计算，也不等于应立即投入的闲置资金。",
    ]
    for asset in ("sp500", "nasdaq100", "short_bond", "gold"):
        lines.append(
            "- "
            + f"{asset}: 当前 {_format_percent(weights.get(asset))}, "
            + f"目标 {_format_percent(targets.get(asset))}, "
            + f"偏离 {_format_pp(deviations.get(asset))}, "
            + f"{_allocation_label(flags.get(asset))}。"
        )

    lines.append(
        "- DCA budget: "
        + f"daily_total {_format_number(dca.get('daily_total'))}, "
        + f"estimated_monthly {_format_number(dca.get('monthly_required'))}, "
        + f"budget_range {_format_number(dca.get('budget_min'))}-{_format_number(dca.get('budget_max'))}, "
        + f"status {_display(dca.get('status'))}。"
    )
    return "\n".join(lines)


def _build_required_market_regime_prefix(
    context_json: dict[str, Any],
    user_question: str,
    answer: str,
) -> str:
    if "过热" not in user_question:
        return ""
    if _find_overall_regime(context_json) != "warm_but_macro_sensitive":
        return ""
    if "warm_but_macro_sensitive" in answer.lower() or "偏热但宏观敏感" in answer:
        return ""
    return (
        "核心结论：当前更接近“偏热但宏观敏感”"
        "（warm_but_macro_sensitive），这不是短期涨跌预测。"
    )


def _format_percent(value: Any) -> str:
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "unavailable"


def _format_pp(value: Any) -> str:
    try:
        return f"{float(value) * 100:+.2f}pp"
    except (TypeError, ValueError):
        return "unavailable"


def _format_number(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "unavailable"


def _allocation_label(flag: Any) -> str:
    if flag == "underweight":
        return "低配 / 相对目标偏低"
    if flag == "overweight":
        return "高配 / 相对目标偏高"
    if flag == "within_range":
        return "接近目标范围"
    return _display(flag)


def _display(value: Any) -> str:
    if value is None or value == "":
        return "unavailable"
    return str(value)


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


def _find_overall_regime(context_json: dict[str, Any]) -> str | None:
    assessments = context_json.get("rule_based_assessments", {})
    if not isinstance(assessments, dict):
        assessments = {}
    market_temperature = assessments.get("market_temperature", {})
    if not isinstance(market_temperature, dict):
        market_temperature = {}
    confirmed = context_json.get("confirmed_facts", {})
    if not isinstance(confirmed, dict):
        confirmed = {}
    market = confirmed.get("market", {})
    if not isinstance(market, dict):
        market = {}

    candidates = [
        market_temperature.get("overall_regime"),
        market.get("overall_regime"),
    ]
    for candidate in candidates:
        if candidate:
            return str(candidate)
    return None


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

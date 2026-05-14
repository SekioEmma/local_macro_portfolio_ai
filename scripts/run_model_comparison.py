from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
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

from eval.answer_evaluator import evaluate_answer, load_eval_cases
from eval.model_comparison import (
    build_model_specific_llm_config,
    load_model_eval_config,
    render_model_comparison_markdown,
    summarize_model_results,
)
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


MODEL_EVAL_CONFIG_PATH = PROJECT_ROOT / "configs" / "model_eval.yaml"
BASE_LLM_CONFIG_PATH = PROJECT_ROOT / "configs" / "llm.yaml"
CONTEXT_MD_PATH = PROJECT_ROOT / "outputs" / "reports" / "llm_context_pack.md"
CONTEXT_JSON_PATH = PROJECT_ROOT / "outputs" / "reports" / "llm_context_pack.json"


def main() -> None:
    loaded_model_config = load_model_eval_config(str(MODEL_EVAL_CONFIG_PATH))
    if loaded_model_config.get("status") != "ok":
        print(json.dumps(loaded_model_config, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    base_config = _load_structured_config(BASE_LLM_CONFIG_PATH)
    comparison = loaded_model_config.get("comparison", {})
    eval_questions_path = PROJECT_ROOT / comparison.get(
        "eval_questions_path",
        "configs/eval_questions.yaml",
    )
    loaded_cases = load_eval_cases(str(eval_questions_path))
    if loaded_cases.get("status") != "ok":
        print(json.dumps(loaded_cases, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    output_root = PROJECT_ROOT / comparison.get("output_dir", "outputs/model_eval")
    output_dir = output_root / datetime.now().strftime("%Y-%m-%d")
    output_dir.mkdir(parents=True, exist_ok=True)

    context_pack = _load_context_pack(base_config)
    models = loaded_model_config.get("models", [])
    run_repair = bool(comparison.get("run_repair", True))
    continue_on_model_error = bool(comparison.get("continue_on_model_error", True))
    compact_prompt = bool(comparison.get("compact_prompt", False))
    preflight_prompt = str(comparison.get("preflight_prompt") or "").strip()
    max_cases_per_model = _as_optional_int(comparison.get("max_cases_per_model"))
    all_cases = loaded_cases.get("cases", [])
    selected_cases = all_cases[:max_cases_per_model] if max_cases_per_model else all_cases

    model_summaries = []
    all_case_results: dict[str, list[dict[str, Any]]] = {}

    for model_config in models:
        model_id = str(model_config.get("id", model_config.get("model", "unknown_model")))
        model_name = str(model_config.get("model", "local-model"))
        model_dir = output_dir / model_id
        model_dir.mkdir(parents=True, exist_ok=True)

        llm_config = build_model_specific_llm_config(base_config, model_config)
        no_think_hint = bool(model_config.get("no_think_hint", False))
        model_error = None
        case_results: list[dict[str, Any]] = []
        preflight = {
            "status": "skipped",
            "error": None,
            "raw_answer_has_thinking": False,
            "final_answer_has_thinking": False,
            "thinking_removed": False,
            "removed_thinking": False,
            "cleaning_notes": [],
        }

        health = check_ollama_health(llm_config)
        if health.get("status") not in {"ok", "skipped"}:
            model_error = _health_to_model_error(health)
        elif not context_pack.get("context_health", {}).get("should_allow_model_call", False):
            model_error = {
                "status": "context_blocked",
                "provider": model_config.get("provider"),
                "model": model_name,
                "error": "Context health does not allow model calls.",
                "context_health": context_pack.get("context_health", {}),
            }
        else:
            if preflight_prompt:
                preflight = _run_preflight(llm_config, preflight_prompt, no_think_hint)
                if preflight.get("status") != "ok":
                    model_error = {
                        "status": "preflight_error",
                        "provider": model_config.get("provider"),
                        "model": model_name,
                        "error": preflight.get("error") or preflight.get("status"),
                        "preflight": preflight,
                    }

            for case in selected_cases if model_error is None else []:
                record = _run_case(
                    case=case,
                    model_id=model_id,
                    model_config=model_config,
                    llm_config=llm_config,
                    context_pack=context_pack,
                    output_dir=model_dir,
                    run_repair=run_repair,
                    no_think_hint=no_think_hint,
                    compact_prompt=compact_prompt,
                )
                case_results.append(record)
                fatal_error = record.get("model_error")
                if fatal_error:
                    model_error = fatal_error
                    break

        model_summary = summarize_model_results(
            model_id=model_id,
            model=model_name,
            case_results=case_results,
            model_error=model_error,
        )
        model_summary["preflight_status"] = preflight.get("status")
        model_summary["preflight_error"] = preflight.get("error")
        model_summary["preflight_thinking_removed"] = preflight.get("thinking_removed", False)
        model_summaries.append(model_summary)
        all_case_results[model_id] = case_results

        model_summary_path = model_dir / "model_summary.json"
        model_summary_path.write_text(
            json.dumps(
                {
                    "model_config": model_config,
                    "ollama_health": health,
                    "preflight": preflight,
                    "model_error": model_error,
                    "summary": model_summary,
                    "case_results": case_results,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        if model_error and not continue_on_model_error:
            break

    generated_at = datetime.now(timezone.utc).isoformat()
    summary_payload = {
        "generated_at": generated_at,
        "model_eval_config_path": str(MODEL_EVAL_CONFIG_PATH),
        "base_llm_config_path": str(BASE_LLM_CONFIG_PATH),
        "eval_questions_path": str(eval_questions_path),
        "output_dir": str(output_dir),
        "comparison_scope": {
            "total_eval_cases": len(all_cases),
            "selected_cases": len(selected_cases),
            "max_cases_per_model": max_cases_per_model,
            "compact_prompt": compact_prompt,
            "preflight_prompt_enabled": bool(preflight_prompt),
            "mode": "smoke" if max_cases_per_model and max_cases_per_model < len(all_cases) else "full",
        },
        "model_summaries": model_summaries,
        "case_results": all_case_results,
    }

    summary_path = output_dir / "model_comparison_summary.json"
    report_path = output_dir / "model_comparison_report.md"
    summary_path.write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_utf8_markdown(report_path, render_model_comparison_markdown(summary_payload))

    print(
        json.dumps(
            {
                "generated_at": generated_at,
                "output_dir": str(output_dir),
                "summary_path": str(summary_path),
                "report_path": str(report_path),
                "model_summaries": model_summaries,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _run_case(
    case: dict[str, Any],
    model_id: str,
    model_config: dict[str, Any],
    llm_config: dict[str, Any],
    context_pack: dict[str, Any],
    output_dir: Path,
    run_repair: bool,
    no_think_hint: bool,
    compact_prompt: bool,
) -> dict[str, Any]:
    case_id = str(case.get("id", "unknown"))
    question = str(case.get("question", ""))
    provider = str(model_config.get("provider", "ollama"))
    model_name = str(model_config.get("model", "local-model"))

    prompt_context = _context_with_llm_config(context_pack, llm_config)
    first_prompt = _build_case_prompt(
        question=question,
        context_pack=prompt_context,
        llm_config=llm_config,
        case=case,
        compact_prompt=compact_prompt,
    )
    first_result = call_local_llm(_with_no_think(first_prompt, no_think_hint), llm_config)
    first_answer, first_guardrail_notes = _answer_from_llm_result(first_result, context_pack)
    model_error = _llm_result_to_model_error(first_result)
    first_eval_result = _evaluate_or_mark_model_error(first_answer, case, model_error)
    first_thinking = _thinking_record(first_result, first_answer)
    first_eval_result = _with_thinking_failure(first_eval_result, first_thinking)

    repair_used = False
    repair_success = False
    final_answer = first_answer
    final_result = first_result
    final_guardrail_notes = first_guardrail_notes
    final_eval_result = first_eval_result

    if (
        not model_error
        and first_result.get("status") == "ok"
        and first_eval_result.get("status") == "fail"
        and run_repair
    ):
        repair_used = True
        repair_case = _case_with_repair_context(case, first_answer, first_eval_result)
        repair_prompt = _build_repair_prompt(
            question=question,
            context_pack=prompt_context,
            validation_warnings=first_eval_result.get("warnings", []),
            repair_case=repair_case,
            original_answer=first_answer,
            missing_required_terms=_missing_required_terms_list(first_eval_result),
            compact_prompt=compact_prompt,
        )
        final_result = call_local_llm(_with_no_think(repair_prompt, no_think_hint), llm_config)
        final_answer, final_guardrail_notes = _answer_from_llm_result(final_result, context_pack)
        model_error = _llm_result_to_model_error(final_result)
        final_eval_result = _evaluate_or_mark_model_error(final_answer, case, model_error)
    final_thinking = _thinking_record(final_result, final_answer)
    final_eval_result = _with_thinking_failure(final_eval_result, final_thinking)
    repair_success = repair_used and final_eval_result.get("status") == "pass"

    first_answer_path = output_dir / f"{case_id}_first_answer.md"
    final_answer_path = output_dir / f"{case_id}_final_answer.md"
    eval_path = output_dir / f"{case_id}_eval.json"
    _write_utf8_markdown(first_answer_path, first_answer)
    _write_utf8_markdown(final_answer_path, final_answer)

    record = {
        "model_id": model_id,
        "provider": provider,
        "model": model_name,
        "case_id": case_id,
        "category": case.get("category"),
        "question": question,
        "first_eval_result": first_eval_result,
        "final_eval_result": final_eval_result,
        "repair_used": repair_used,
        "repair_success": repair_success,
        "first_llm_status": first_result.get("status"),
        "final_llm_status": final_result.get("status"),
        "first_removed_thinking": first_result.get("removed_thinking", False),
        "final_removed_thinking": final_result.get("removed_thinking", False),
        "first_cleaning_notes": first_result.get("cleaning_notes", []),
        "final_cleaning_notes": final_result.get("cleaning_notes", []),
        "first_raw_answer_has_thinking": first_thinking["raw_answer_has_thinking"],
        "first_answer_has_thinking": first_thinking["final_answer_has_thinking"],
        "first_thinking_removed": first_thinking["thinking_removed"],
        "raw_answer_has_thinking": final_thinking["raw_answer_has_thinking"],
        "final_answer_has_thinking": final_thinking["final_answer_has_thinking"],
        "thinking_removed": final_thinking["thinking_removed"],
        "removed_thinking": final_result.get("removed_thinking", False),
        "cleaning_notes": final_result.get("cleaning_notes", []),
        "first_guardrail_notes": first_guardrail_notes,
        "final_guardrail_notes": final_guardrail_notes,
        "model_error": model_error,
        "answer_paths": {
            "first": str(first_answer_path),
            "final": str(final_answer_path),
        },
    }
    eval_path.write_text(
        json.dumps(
            {
                "case": case,
                "record": record,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    record["eval_path"] = str(eval_path)
    return record


def _run_preflight(
    llm_config: dict[str, Any],
    preflight_prompt: str,
    no_think_hint: bool,
) -> dict[str, Any]:
    result = call_local_llm(_with_no_think(preflight_prompt, no_think_hint), llm_config)
    answer = str(result.get("answer") or "")
    thinking = _thinking_record(result, answer)
    model_error = _llm_result_to_model_error(result)
    return {
        "status": "ok" if model_error is None else model_error.get("status", "model_error"),
        "error": model_error.get("error") if model_error else None,
        "answer_preview": answer[:200],
        "raw_answer_has_thinking": thinking["raw_answer_has_thinking"],
        "final_answer_has_thinking": thinking["final_answer_has_thinking"],
        "thinking_removed": thinking["thinking_removed"],
        "removed_thinking": result.get("removed_thinking", False),
        "cleaning_notes": result.get("cleaning_notes", []),
    }


def _build_case_prompt(
    question: str,
    context_pack: dict[str, Any],
    llm_config: dict[str, Any],
    case: dict[str, Any],
    compact_prompt: bool,
) -> str:
    if compact_prompt:
        return build_compact_answer_prompt(question, context_pack, llm_config, eval_case=case)
    return build_answer_prompt(question, context_pack, llm_config, eval_case=case)


def _build_repair_prompt(
    question: str,
    context_pack: dict[str, Any],
    validation_warnings: list[str],
    repair_case: dict[str, Any],
    original_answer: str,
    missing_required_terms: list[str],
    compact_prompt: bool,
) -> str:
    if compact_prompt:
        return build_compact_repair_prompt(
            user_question=question,
            context_pack=context_pack,
            validation_warnings=validation_warnings,
            eval_case=repair_case,
            original_answer=original_answer,
            missing_required_terms=missing_required_terms,
            forbidden_hits=repair_case.get("repair_context", {}).get("forbidden_hits", []),
        )
    return build_validation_repair_prompt(
        user_question=question,
        context_pack=context_pack,
        validation_warnings=validation_warnings,
        eval_case=repair_case,
        original_answer=original_answer,
        missing_required_terms=missing_required_terms,
        forbidden_hits=repair_case.get("repair_context", {}).get("forbidden_hits", []),
    )


def _context_with_llm_config(
    context_pack: dict[str, Any],
    llm_config: dict[str, Any],
) -> dict[str, Any]:
    return {
        **context_pack,
        "_local_llm_config": llm_config.get("local_llm", {}) if isinstance(llm_config, dict) else {},
    }


def _thinking_record(result: dict[str, Any], final_answer: str) -> dict[str, bool]:
    raw_preview = str(result.get("raw_answer_preview") or "")
    removed = bool(result.get("removed_thinking", False))
    raw_has = removed or _has_thinking_text(raw_preview)
    final_has = _has_thinking_text(final_answer)
    return {
        "raw_answer_has_thinking": raw_has,
        "final_answer_has_thinking": final_has,
        "thinking_removed": bool(raw_has and not final_has),
    }


def _with_thinking_failure(
    eval_result: dict[str, Any],
    thinking: dict[str, bool],
) -> dict[str, Any]:
    if not thinking.get("final_answer_has_thinking"):
        return eval_result
    if eval_result.get("status") == "model_error":
        return eval_result
    updated = {
        **eval_result,
        "status": "fail",
        "score": min(int(eval_result.get("score", 0)), 40),
        "forbidden_hits": [
            *eval_result.get("forbidden_hits", []),
            "Thinking output remained in final answer.",
        ],
    }
    return updated


def _has_thinking_text(text: str) -> bool:
    lower = str(text).lower()
    markers = [
        "thinking process",
        "thinking...",
        "done thinking",
        "<think>",
        "</think>",
        "思维过程",
        "推理过程",
        "内部推理",
    ]
    return any(marker in lower for marker in markers)


def _load_context_pack(base_config: dict[str, Any]) -> dict[str, Any]:
    context_pack = load_context_pack(str(CONTEXT_MD_PATH), str(CONTEXT_JSON_PATH))
    context_policy = base_config.get("context_policy", {}) if isinstance(base_config, dict) else {}
    context_pack["context_health"] = validate_context_health(
        context_pack.get("context_json", {}),
        context_policy,
    )
    context_pack["compressed_data_limitations"] = summarize_data_limitations(
        context_pack.get("data_limitations", [])
    )
    return context_pack


def _answer_from_llm_result(
    result: dict[str, Any],
    context_pack: dict[str, Any],
) -> tuple[str, list[str]]:
    if result.get("status") != "ok":
        return (
            "MODEL_CALL_ERROR: "
            + str(result.get("status"))
            + ": "
            + str(result.get("error") or "unknown error"),
            [],
        )

    answer = str(result.get("answer") or "").strip()
    guarded = _apply_sample_fallback_guardrail(answer, context_pack)
    return guarded["answer"], guarded["notes"]


def _evaluate_or_mark_model_error(
    answer: str,
    case: dict[str, Any],
    model_error: dict[str, Any] | None,
) -> dict[str, Any]:
    if model_error:
        return {
            "case_id": case.get("id", "unknown"),
            "status": "model_error",
            "required_checks": [],
            "forbidden_hits": [],
            "warnings": [model_error.get("error") or model_error.get("status") or "model error"],
            "score": 0,
        }
    return evaluate_answer(answer, case)


def _apply_sample_fallback_guardrail(
    answer: str,
    context_pack: dict[str, Any],
) -> dict[str, Any]:
    context_json = context_pack.get("context_json", {}) if isinstance(context_pack, dict) else {}
    holdings_source = _find_holdings_source(context_json)
    if holdings_source.get("mode") != "sample_fallback" or _mentions_sample_fallback(answer):
        return {
            "answer": answer,
            "notes": [],
        }

    prefix = (
        "重要说明：当前账户数据来自 sample_fallback（示例持仓），不是真实账户数据；"
        "以下内容只基于 context pack 做本地研究说明，不构成投资建议。\n\n"
    )
    return {
        "answer": prefix + answer,
        "notes": ["Prepended required sample_fallback warning."],
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


def _case_with_repair_context(
    case: dict[str, Any],
    original_answer: str,
    eval_result: dict[str, Any],
) -> dict[str, Any]:
    return {
        **case,
        "repair_context": {
            "original_answer": original_answer,
            "missing_required_terms": _missing_required_terms_list(eval_result),
            "forbidden_hits": eval_result.get("forbidden_hits", []),
            "warnings": eval_result.get("warnings", []),
        },
    }


def _missing_required_terms_list(result: dict[str, Any]) -> list[str]:
    missing = []
    for check in result.get("required_checks", []):
        if check.get("status") == "fail":
            missing.append("/".join(str(term) for term in check.get("terms_any", [])))
    return missing


def _with_no_think(prompt: str, no_think_hint: bool) -> str:
    if not no_think_hint:
        return prompt
    return "/no_think\n只输出最终答案，不输出思考过程。\n\n" + prompt


def _llm_result_to_model_error(result: dict[str, Any]) -> dict[str, Any] | None:
    status = result.get("status")
    if status in {"ok", "prompt_only"}:
        return None
    if status == "model_memory_layout_error":
        return {
            "status": "model_memory_layout_error",
            "provider": result.get("provider"),
            "model": result.get("model"),
            "error": result.get("error"),
        }
    return {
        "status": "model_call_error",
        "provider": result.get("provider"),
        "model": result.get("model"),
        "error": result.get("error") or status or "unknown model call error",
    }


def _health_to_model_error(health: dict[str, Any]) -> dict[str, Any]:
    status = "model_not_found" if health.get("status") == "model_missing" else "model_health_error"
    return {
        "status": status,
        "provider": health.get("provider"),
        "model": health.get("model"),
        "error": health.get("error"),
        "hint": health.get("hint"),
        "ollama_health": health,
    }


def _load_structured_config(path: Path) -> dict[str, Any]:
    raw_text = path.read_text(encoding="utf-8-sig")
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        data = yaml.safe_load(raw_text) if yaml is not None else _parse_section_yaml(raw_text)
    return data or {}


def _parse_section_yaml(raw_text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    current_section: str | None = None

    for raw_line in raw_text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if not raw_line.startswith(" ") and stripped.endswith(":"):
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
    if value.lower() == "null":
        return None

    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _as_optional_int(value: Any) -> int | None:
    if value in {None, "", 0, "0"}:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _write_utf8_markdown(path: Path, content: str) -> None:
    # The BOM keeps Windows PowerShell Get-Content -Raw from treating UTF-8 as ANSI.
    path.write_text("\ufeff" + content, encoding="utf-8")


if __name__ == "__main__":
    main()

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError:
    yaml = None


def load_model_eval_config(path: str) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        return {
            "status": "error",
            "config": {},
            "models": [],
            "comparison": {},
            "error": f"File not found: {config_path}",
        }

    try:
        raw_text = config_path.read_text(encoding="utf-8-sig")
        data = _load_structured_text(raw_text)
    except (OSError, ValueError) as exc:
        return {
            "status": "error",
            "config": {},
            "models": [],
            "comparison": {},
            "error": str(exc),
        }

    if not isinstance(data, dict):
        return {
            "status": "error",
            "config": {},
            "models": [],
            "comparison": {},
            "error": "Model eval config root must be an object.",
        }

    models = data.get("models", [])
    comparison = data.get("comparison", {})
    if not isinstance(models, list):
        return {
            "status": "error",
            "config": data,
            "models": [],
            "comparison": comparison if isinstance(comparison, dict) else {},
            "error": "models must be a list.",
        }
    if not isinstance(comparison, dict):
        return {
            "status": "error",
            "config": data,
            "models": models,
            "comparison": {},
            "error": "comparison must be an object.",
        }

    return {
        "status": "ok",
        "config": data,
        "models": models,
        "comparison": comparison,
        "error": None,
    }


def build_model_specific_llm_config(
    base_llm_config: dict[str, Any],
    model_config: dict[str, Any],
) -> dict[str, Any]:
    config = copy.deepcopy(base_llm_config) if isinstance(base_llm_config, dict) else {}
    local_llm = config.setdefault("local_llm", {})
    if not isinstance(local_llm, dict):
        local_llm = {}
        config["local_llm"] = local_llm

    local_llm["mode"] = "local_http"
    local_llm["provider"] = model_config.get("provider", local_llm.get("provider", "ollama"))
    local_llm["model"] = model_config.get("model", local_llm.get("model", "local-model"))
    local_llm["temperature"] = model_config.get("temperature", local_llm.get("temperature", 0.1))
    local_llm["top_p"] = model_config.get("top_p", local_llm.get("top_p", 0.9))
    local_llm["num_ctx"] = model_config.get("num_ctx", local_llm.get("num_ctx", 4096))
    local_llm["max_context_chars"] = model_config.get(
        "max_context_chars",
        local_llm.get("max_context_chars", 16000),
    )
    local_llm["save_answer_archive"] = False
    local_llm["strip_thinking_output"] = bool(local_llm.get("strip_thinking_output", True))
    local_llm["no_think_hint"] = bool(model_config.get("no_think_hint", False))
    return config


def summarize_model_results(
    model_id: str,
    model: str,
    case_results: list[dict[str, Any]],
    model_error: dict[str, Any] | None,
) -> dict[str, Any]:
    total_cases = len(case_results)
    first_pass_passed = sum(
        1 for result in case_results if result.get("first_eval_result", {}).get("status") == "pass"
    )
    final_passed = sum(
        1 for result in case_results if result.get("final_eval_result", {}).get("status") == "pass"
    )
    repair_used_count = sum(1 for result in case_results if result.get("repair_used"))
    repair_success_count = sum(1 for result in case_results if result.get("repair_success"))
    failed_case_ids = [
        result.get("case_id")
        for result in case_results
        if result.get("final_eval_result", {}).get("status") != "pass"
    ]
    provider = _first_non_empty(
        [result.get("provider") for result in case_results],
        model_error.get("provider") if isinstance(model_error, dict) else None,
        "unknown",
    )

    if model_error:
        status = model_error.get("status") or "model_error"
    elif failed_case_ids:
        status = "completed_with_failures"
    else:
        status = "ok"

    return {
        "model_id": model_id,
        "model": model,
        "provider": provider,
        "status": status,
        "total_cases": total_cases,
        "first_pass_passed": first_pass_passed,
        "first_pass_pass_rate": _rate(first_pass_passed, total_cases),
        "final_passed": final_passed,
        "final_pass_rate": _rate(final_passed, total_cases),
        "repair_used_count": repair_used_count,
        "repair_success_count": repair_success_count,
        "average_first_score": _average_score(case_results, "first_eval_result"),
        "average_final_score": _average_score(case_results, "final_eval_result"),
        "failed_case_ids": [case_id for case_id in failed_case_ids if case_id],
        "model_errors": [model_error] if model_error else [],
    }


def render_model_comparison_markdown(summary: dict[str, Any]) -> str:
    model_summaries = summary.get("model_summaries", [])
    case_results = summary.get("case_results", {})
    lines = [
        "# Local Model Comparison Report",
        "",
        f"Generated at: {summary.get('generated_at', 'unavailable')}",
        "",
        "## Comparison Scope",
        _scope_text(summary.get("comparison_scope", {})),
        "",
        "## Summary",
        (
            "| model_id | model | provider | status | preflight_status | total_cases | first_pass_pass_rate | "
            "final_pass_rate | repair_used_count | repair_success_count | failed_case_ids | model_errors |"
        ),
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for item in model_summaries:
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(item.get("model_id")),
                    _cell(item.get("model")),
                    _cell(item.get("provider")),
                    _cell(item.get("status")),
                    _cell(item.get("preflight_status")),
                    _cell(item.get("total_cases")),
                    _cell(item.get("first_pass_pass_rate")),
                    _cell(item.get("final_pass_rate")),
                    _cell(item.get("repair_used_count")),
                    _cell(item.get("repair_success_count")),
                    _cell(", ".join(item.get("failed_case_ids", [])) or "None"),
                    _cell(_model_errors_text(item.get("model_errors", []))),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Case Results", ""])
    for item in model_summaries:
        model_id = item.get("model_id")
        lines.extend(
            [
                f"### {model_id}",
                "",
                (
                    "| case_id | category | first_status | first_score | final_status | final_score | "
                    "repair_used | repair_success | raw_answer_has_thinking | final_answer_has_thinking | thinking_removed |"
                ),
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        records = case_results.get(model_id, []) if isinstance(case_results, dict) else []
        if not records:
            lines.append("| No cases run |  |  |  |  |  |  |  |  |  |  |")
            lines.append("")
            continue

        for record in records:
            first_eval = record.get("first_eval_result", {})
            final_eval = record.get("final_eval_result", {})
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(record.get("case_id")),
                        _cell(record.get("category")),
                        _cell(first_eval.get("status")),
                        _cell(first_eval.get("score")),
                        _cell(final_eval.get("status")),
                        _cell(final_eval.get("score")),
                        _cell(record.get("repair_used")),
                        _cell(record.get("repair_success")),
                        _cell(record.get("raw_answer_has_thinking")),
                        _cell(record.get("final_answer_has_thinking")),
                        _cell(record.get("thinking_removed")),
                    ]
                )
                + " |"
            )
        lines.append("")

    lines.extend(
        [
            "## Methodology",
            (
                "Rule-based local evaluation comparing first-pass answers and final answers after "
                "the same local repair flow. It does not prove model correctness; it measures known "
                "boundary-condition adherence for the fixed local eval set."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _load_structured_text(raw_text: str) -> Any:
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass

    if yaml is not None:
        return yaml.safe_load(raw_text)

    return _parse_model_eval_yaml(raw_text)


def _scope_text(scope: Any) -> str:
    if not isinstance(scope, dict) or not scope:
        return "Comparison scope unavailable."
    mode = scope.get("mode", "unknown")
    selected = scope.get("selected_cases", 0)
    total = scope.get("total_eval_cases", 0)
    compact = scope.get("compact_prompt", False)
    text = (
        f"Mode: {mode}. Cases per model: {selected}/{total}. "
        f"compact_prompt={compact}."
    )
    if mode == "smoke":
        text += " This is a smoke comparison, not a full 6-case comparison."
    return text


def _parse_model_eval_yaml(raw_text: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "models": [],
        "comparison": {},
    }
    section: str | None = None
    current_model: dict[str, Any] | None = None

    for raw_line in raw_text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if not raw_line.startswith(" ") and stripped.endswith(":"):
            section = stripped[:-1]
            current_model = None
            if section == "models":
                result["models"] = []
            elif section == "comparison":
                result["comparison"] = {}
            else:
                result[section] = {}
            continue

        if section == "models" and stripped.startswith("- "):
            current_model = {}
            result["models"].append(current_model)
            remainder = stripped[2:].strip()
            if remainder:
                _set_yaml_key_value(current_model, remainder)
            continue

        if section == "models" and current_model is not None and ":" in stripped:
            _set_yaml_key_value(current_model, stripped)
            continue

        if section == "comparison" and ":" in stripped:
            _set_yaml_key_value(result["comparison"], stripped)

    return result


def _set_yaml_key_value(target: dict[str, Any], text: str) -> None:
    key, value = text.split(":", 1)
    target[key.strip()] = _parse_scalar(value.strip())


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


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _average_score(case_results: list[dict[str, Any]], key: str) -> float:
    scores = [
        result.get(key, {}).get("score")
        for result in case_results
        if isinstance(result.get(key, {}).get("score"), (int, float))
    ]
    if not scores:
        return 0.0
    return round(sum(float(score) for score in scores) / len(scores), 2)


def _first_non_empty(values: list[Any], fallback: Any, default: str) -> str:
    for value in values:
        if value:
            return str(value)
    if fallback:
        return str(fallback)
    return default


def _model_errors_text(errors: list[dict[str, Any]]) -> str:
    if not errors:
        return "None"
    parts = []
    for error in errors:
        if not isinstance(error, dict):
            parts.append(str(error))
            continue
        parts.append(
            ": ".join(
                part
                for part in [
                    str(error.get("status") or "error"),
                    str(error.get("error") or error.get("hint") or ""),
                ]
                if part
            )
        )
    return "; ".join(parts)


def _cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")

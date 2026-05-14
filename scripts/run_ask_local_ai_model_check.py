from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from eval.answer_evaluator import load_eval_cases


ASK_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "ask_local_ai.py"
EVAL_CONFIG_PATH = PROJECT_ROOT / "configs" / "eval_questions.yaml"
LATEST_ANSWER_PATH = PROJECT_ROOT / "outputs" / "reports" / "latest_llm_answer.md"
OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "model_eval"

MODELS = [
    {
        "id": "gemma4_e2b",
        "model": "gemma4:e2b",
    },
    {
        "id": "qwen3_4b",
        "model": "qwen3:4b",
    },
]

CASE_IDS = [
    "market_overheat_portfolio",
    "historical_outcome_not_forecast",
    "sample_fallback_real_account",
    "degraded_context_behavior",
    "trade_command_refusal",
]

ASK_OVERRIDES = {
    "num_ctx": 2048,
    "max_context_chars": 5000,
    "compact_prompt": True,
}


def main() -> None:
    loaded_cases = load_eval_cases(str(EVAL_CONFIG_PATH))
    if loaded_cases.get("status") != "ok":
        print(json.dumps(loaded_cases, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    cases_by_id = {
        str(case.get("id")): case
        for case in loaded_cases.get("cases", [])
        if isinstance(case, dict)
    }
    selected_cases = [cases_by_id[case_id] for case_id in CASE_IDS if case_id in cases_by_id]
    missing_case_ids = [case_id for case_id in CASE_IDS if case_id not in cases_by_id]
    if missing_case_ids:
        print(
            json.dumps(
                {
                    "status": "error",
                    "missing_case_ids": missing_case_ids,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(1)

    output_dir = OUTPUT_ROOT / datetime.now().strftime("%Y-%m-%d")
    output_dir.mkdir(parents=True, exist_ok=True)

    model_records = []
    model_summaries = []
    for model in MODELS:
        records = [_run_case(model, case) for case in selected_cases]
        model_records.extend(records)
        model_summaries.append(_summarize_model(model, records))

    generated_at = datetime.now(timezone.utc).isoformat()
    summary = {
        "generated_at": generated_at,
        "scope": {
            "runner": "ask_local_ai.py",
            "questions": len(selected_cases),
            "models": [model["model"] for model in MODELS],
            "ask_overrides": ASK_OVERRIDES,
            "configs_llm_yaml_default_unchanged": True,
        },
        "model_summaries": model_summaries,
        "records": model_records,
        "recommendation": _build_recommendation(model_summaries),
    }

    summary_path = output_dir / "ask_local_ai_model_check.json"
    report_path = output_dir / "ask_local_ai_model_check.md"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_utf8_markdown(report_path, _render_report(summary))

    print(
        json.dumps(
            {
                "generated_at": generated_at,
                "summary_path": str(summary_path),
                "report_path": str(report_path),
                "model_summaries": model_summaries,
                "recommendation": summary["recommendation"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _run_case(model: dict[str, str], case: dict[str, Any]) -> dict[str, Any]:
    if LATEST_ANSWER_PATH.exists():
        LATEST_ANSWER_PATH.unlink()

    question = str(case.get("question", ""))
    args = [
        sys.executable,
        str(ASK_SCRIPT_PATH),
        "--model",
        model["model"],
        "--num-ctx",
        str(ASK_OVERRIDES["num_ctx"]),
        "--max-context-chars",
        str(ASK_OVERRIDES["max_context_chars"]),
        "--eval-case-json",
        json.dumps(case, ensure_ascii=False),
    ]
    if ASK_OVERRIDES["compact_prompt"]:
        args.append("--compact-prompt")
    args.append(question)

    completed = subprocess.run(
        args,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
    )
    summary = _extract_last_json_object(completed.stdout)
    final_answer = _read_latest_answer()
    final_has_thinking = _has_thinking_text(final_answer)
    first_validation = summary.get("first_answer_validation", {}) if isinstance(summary, dict) else {}
    final_validation = summary.get("final_answer_validation", {}) if isinstance(summary, dict) else {}
    archive_paths = summary.get("archive_paths", {}) if isinstance(summary, dict) else {}
    model_error = _model_error_from_summary(summary, completed)
    passed = (
        completed.returncode == 0
        and not model_error
        and final_validation.get("status") == "pass"
        and not final_has_thinking
        and bool(summary.get("answer_path")) if isinstance(summary, dict) else False
    )

    return {
        "model_id": model["id"],
        "model": model["model"],
        "case_id": case.get("id"),
        "question": question,
        "returncode": completed.returncode,
        "status": summary.get("status") if isinstance(summary, dict) else "summary_parse_error",
        "first_answer_validation_status": first_validation.get("status"),
        "final_answer_validation_status": final_validation.get("status"),
        "repair_used": bool(summary.get("repair_used")) if isinstance(summary, dict) else False,
        "repair_success": bool(summary.get("repair_success")) if isinstance(summary, dict) else False,
        "answer_validation_warnings": final_validation.get("warnings", []),
        "final_missing_required_terms": final_validation.get("missing_required_terms", []),
        "final_forbidden_hits": final_validation.get("forbidden_hits", []),
        "removed_thinking": bool(summary.get("removed_thinking")) if isinstance(summary, dict) else False,
        "first_removed_thinking": bool(summary.get("first_removed_thinking")) if isinstance(summary, dict) else False,
        "final_removed_thinking": bool(summary.get("final_removed_thinking")) if isinstance(summary, dict) else False,
        "final_answer_has_thinking": final_has_thinking,
        "latest_answer_saved": LATEST_ANSWER_PATH.exists(),
        "answer_chars": len(final_answer),
        "archive_generated": bool(archive_paths),
        "archive_paths": archive_paths,
        "model_error": model_error,
        "passed": passed,
        "stdout_summary_found": bool(summary),
        "stderr_preview": completed.stderr[-600:],
    }


def _summarize_model(model: dict[str, str], records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    passed = sum(1 for record in records if record.get("passed"))
    failed_records = [record for record in records if not record.get("passed")]
    repair_used_count = sum(1 for record in records if record.get("repair_used"))
    repair_success_count = sum(1 for record in records if record.get("repair_success"))
    thinking_residue_count = sum(1 for record in records if record.get("final_answer_has_thinking"))
    model_errors = [record.get("model_error") for record in records if record.get("model_error")]
    answer_lengths = [record.get("answer_chars", 0) for record in records]
    return {
        "model_id": model["id"],
        "model": model["model"],
        "total_questions": total,
        "passed": passed,
        "failed": len(failed_records),
        "pass_rate": round(passed / total, 4) if total else 0,
        "repair_used_count": repair_used_count,
        "repair_success_count": repair_success_count,
        "thinking_residue_count": thinking_residue_count,
        "failed_questions": [record.get("case_id") for record in failed_records],
        "model_errors": model_errors,
        "average_answer_chars": round(sum(answer_lengths) / total, 2) if total else 0,
        "notes": _model_notes(model, records),
    }


def _build_recommendation(model_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    by_model = {item.get("model"): item for item in model_summaries}
    gemma = by_model.get("gemma4:e2b", {})
    qwen = by_model.get("qwen3:4b", {})
    qwen_errors = qwen.get("model_errors") or []
    should_switch_next_stage = bool(
        qwen
        and gemma
        and qwen.get("pass_rate", 0) >= gemma.get("pass_rate", 0)
        and qwen.get("repair_success_count", 0) >= gemma.get("repair_success_count", 0)
        and qwen.get("thinking_residue_count", 1) == 0
        and not qwen_errors
        and not qwen.get("failed_questions")
        and qwen.get("average_answer_chars", 0) <= max(
            2500,
            float(gemma.get("average_answer_chars", 0)) * 2.0,
        )
    )
    return {
        "should_switch_default_next_stage": should_switch_next_stage,
        "recommended_default_model": "qwen3:4b" if should_switch_next_stage else "gemma4:e2b",
        "reason": (
            "qwen3:4b met the ask_local_ai main-chain comparison gates."
            if should_switch_next_stage
            else "Keep gemma4:e2b until ask_local_ai main-chain gates are met."
        ),
    }


def _model_notes(model: dict[str, str], records: list[dict[str, Any]]) -> list[str]:
    notes = [
        "Used ask_local_ai.py main workflow with --model override; configs/llm.yaml default was not changed.",
        "Used compact prompt and 2048 context for same-context candidate validation.",
    ]
    if any(record.get("archive_generated") for record in records):
        notes.append("Answer archives were generated under outputs/answers and remain git-ignored.")
    if any(record.get("final_answer_has_thinking") for record in records):
        notes.append("At least one final answer still contains Thinking residue.")
    if any(record.get("model_error") for record in records):
        notes.append("At least one model call returned a structured error.")
    return notes


def _render_report(summary: dict[str, Any]) -> str:
    lines = [
        "# ask_local_ai Model Check",
        "",
        f"Generated at: {summary.get('generated_at')}",
        "",
        "## Scope",
        "- Runner: scripts/ask_local_ai.py",
        "- Models: gemma4:e2b, qwen3:4b",
        "- Questions: 5 real user-style questions mapped to the fixed eval cases.",
        "- Overrides: --num-ctx 2048 --max-context-chars 5000 --compact-prompt",
        "- configs/llm.yaml default model was not changed.",
        "",
        "## Summary",
        "| model | total_questions | passed | failed | pass_rate | repair_used_count | repair_success_count | thinking_residue_count | failed_questions |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in summary.get("model_summaries", []):
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(item.get("model")),
                    _cell(item.get("total_questions")),
                    _cell(item.get("passed")),
                    _cell(item.get("failed")),
                    _cell(item.get("pass_rate")),
                    _cell(item.get("repair_used_count")),
                    _cell(item.get("repair_success_count")),
                    _cell(item.get("thinking_residue_count")),
                    _cell(", ".join(item.get("failed_questions", [])) or "None"),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Case Results",
            "| model | case_id | first_validation | final_validation | repair_used | repair_success | thinking_residue | latest_answer_saved | archive_generated | key failures |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for record in summary.get("records", []):
        failures = []
        if record.get("final_missing_required_terms"):
            failures.append("missing: " + "; ".join(record.get("final_missing_required_terms", [])))
        if record.get("final_forbidden_hits"):
            failures.append("forbidden: " + "; ".join(record.get("final_forbidden_hits", [])))
        if record.get("model_error"):
            failures.append("model_error: " + str(record.get("model_error")))
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(record.get("model")),
                    _cell(record.get("case_id")),
                    _cell(record.get("first_answer_validation_status")),
                    _cell(record.get("final_answer_validation_status")),
                    _cell(record.get("repair_used")),
                    _cell(record.get("repair_success")),
                    _cell(record.get("final_answer_has_thinking")),
                    _cell(record.get("latest_answer_saved")),
                    _cell(record.get("archive_generated")),
                    _cell("; ".join(failures) if failures else "None"),
                ]
            )
            + " |"
        )

    recommendation = summary.get("recommendation", {})
    lines.extend(
        [
            "",
            "## Recommendation",
            f"- should_switch_default_next_stage: {recommendation.get('should_switch_default_next_stage')}",
            f"- recommended_default_model: {recommendation.get('recommended_default_model')}",
            f"- reason: {recommendation.get('reason')}",
            "",
            "## Methodology",
            "This is a local, rule-based ask_local_ai main-chain check. It does not prove model correctness; it checks known project boundaries and repair behavior for fixed questions.",
            "",
        ]
    )
    return "\n".join(lines)


def _extract_last_json_object(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    starts = [index for index, char in enumerate(text) if char == "{"]
    decoder = json.JSONDecoder()
    for start in reversed(starts):
        try:
            payload, end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if text[start + end :].strip():
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _read_latest_answer() -> str:
    if not LATEST_ANSWER_PATH.exists():
        return ""
    return LATEST_ANSWER_PATH.read_text(encoding="utf-8-sig")


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


def _model_error_from_summary(
    summary: dict[str, Any],
    completed: subprocess.CompletedProcess[str],
) -> dict[str, Any] | None:
    if completed.returncode != 0:
        return {
            "status": "ask_local_ai_returncode",
            "returncode": completed.returncode,
            "stderr_preview": completed.stderr[-600:],
        }
    if not summary:
        return {
            "status": "summary_parse_error",
            "stderr_preview": completed.stderr[-600:],
        }
    if summary.get("status") != "ok":
        return {
            "status": summary.get("status"),
            "error": summary.get("error"),
            "ollama_health": summary.get("ollama_health"),
        }
    return None


def _cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _write_utf8_markdown(path: Path, content: str) -> None:
    path.write_text("\ufeff" + content, encoding="utf-8")


if __name__ == "__main__":
    main()

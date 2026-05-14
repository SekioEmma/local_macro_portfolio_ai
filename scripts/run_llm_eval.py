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

from eval.answer_evaluator import (
    evaluate_answer,
    load_eval_cases,
    summarize_eval_results,
)


EVAL_CONFIG_PATH = PROJECT_ROOT / "configs" / "eval_questions.yaml"
ASK_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "ask_local_ai.py"
LATEST_ANSWER_PATH = PROJECT_ROOT / "outputs" / "reports" / "latest_llm_answer.md"
EVAL_ROOT = PROJECT_ROOT / "outputs" / "eval"


def main() -> None:
    loaded = load_eval_cases(str(EVAL_CONFIG_PATH))
    if loaded.get("status") != "ok":
        print(json.dumps(loaded, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    cases = loaded.get("cases", [])
    eval_dir = EVAL_ROOT / datetime.now().strftime("%Y-%m-%d")
    eval_dir.mkdir(parents=True, exist_ok=True)

    results = []
    case_records = []
    for case in cases:
        record = _run_case(case, eval_dir)
        results.append(record["eval_result"])
        case_records.append(record)

    summary = summarize_eval_results(results)
    generated_at = datetime.now(timezone.utc).isoformat()
    summary_payload = {
        "generated_at": generated_at,
        **summary,
        "results": results,
    }

    summary_path = eval_dir / "eval_summary.json"
    report_path = eval_dir / "eval_report.md"
    summary_path.write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_utf8_markdown(report_path, render_eval_report(generated_at, summary, case_records))

    print(
        json.dumps(
            {
                **summary,
                "generated_at": generated_at,
                "eval_dir": str(eval_dir),
                "summary_path": str(summary_path),
                "report_path": str(report_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    if summary["failed"] > 0:
        raise SystemExit(1)


def _run_case(case: dict[str, Any], eval_dir: Path) -> dict[str, Any]:
    case_id = str(case.get("id", "unknown"))
    question = str(case.get("question", ""))
    first_completed = _call_ask(question, case)
    first_answer = _answer_from_run(first_completed)
    first_eval_result = _evaluate_with_subprocess_status(first_answer, case, first_completed)

    repair_used = False
    final_answer = first_answer
    final_completed = None
    final_eval_result = first_eval_result

    if first_eval_result.get("status") == "fail":
        repair_used = True
        repair_case = _case_with_repair_context(case, first_answer, first_eval_result)
        final_completed = _call_ask(question, repair_case)
        repaired_answer = _answer_from_run(final_completed)
        if repaired_answer:
            final_answer = repaired_answer
            final_eval_result = _evaluate_with_subprocess_status(
                final_answer,
                case,
                final_completed,
            )

    final_eval_result = {
        **final_eval_result,
        "repair_used": repair_used,
    }

    first_answer_path = eval_dir / f"{case_id}_first_answer.md"
    final_answer_path = eval_dir / f"{case_id}_final_answer.md"
    eval_path = eval_dir / f"{case_id}_eval.json"
    _write_utf8_markdown(first_answer_path, first_answer)
    _write_utf8_markdown(final_answer_path, final_answer)
    eval_path.write_text(
        json.dumps(
            {
                "case": case,
                "repair_used": repair_used,
                "first_eval_result": first_eval_result,
                "final_eval_result": final_eval_result,
                "eval_result": final_eval_result,
                "missing_required_terms": _missing_required_terms_list(first_eval_result),
                "forbidden_hits": first_eval_result.get("forbidden_hits", []),
                "final_missing_required_terms": _missing_required_terms_list(final_eval_result),
                "final_forbidden_hits": final_eval_result.get("forbidden_hits", []),
                "first_ask_returncode": first_completed.returncode,
                "first_ask_stdout_preview": first_completed.stdout[-1200:],
                "first_ask_stderr_preview": first_completed.stderr[-1200:],
                "final_ask_returncode": final_completed.returncode if final_completed else None,
                "final_ask_stdout_preview": final_completed.stdout[-1200:] if final_completed else None,
                "final_ask_stderr_preview": final_completed.stderr[-1200:] if final_completed else None,
                "answer_paths": {
                    "first": str(first_answer_path),
                    "final": str(final_answer_path),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return {
        "case": case,
        "first_answer": first_answer,
        "final_answer": final_answer,
        "first_answer_path": str(first_answer_path),
        "final_answer_path": str(final_answer_path),
        "eval_path": str(eval_path),
        "first_eval_result": first_eval_result,
        "eval_result": final_eval_result,
        "repair_used": repair_used,
    }


def _call_ask(question: str, case: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    if LATEST_ANSWER_PATH.exists():
        LATEST_ANSWER_PATH.unlink()
    case_payload = json.dumps(case, ensure_ascii=False)
    return subprocess.run(
        [
            sys.executable,
            str(ASK_SCRIPT_PATH),
            "--eval-case-json",
            case_payload,
            question,
        ],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _answer_from_run(completed: subprocess.CompletedProcess[str]) -> str:
    answer = _read_latest_answer()
    if completed.returncode != 0 and not answer:
        return (
            "EVAL_RUN_ERROR: ask_local_ai.py failed. "
            f"returncode={completed.returncode}. stderr={completed.stderr.strip()}"
        )
    return answer


def _evaluate_with_subprocess_status(
    answer: str,
    case: dict[str, Any],
    completed: subprocess.CompletedProcess[str],
) -> dict[str, Any]:
    eval_result = evaluate_answer(answer, case)
    if completed.returncode != 0:
        eval_result.setdefault("warnings", []).append(
            f"ask_local_ai.py exited with code {completed.returncode}."
        )
        if eval_result.get("status") == "pass":
            eval_result["status"] = "warning"
    return eval_result


def _case_with_repair_context(
    case: dict[str, Any],
    original_answer: str,
    eval_result: dict[str, Any],
) -> dict[str, Any]:
    return {
        **case,
        "repair_context": {
            "evaluator_status": eval_result.get("status"),
            "original_answer": original_answer,
            "missing_required_terms": _missing_required_terms_list(eval_result),
            "forbidden_hits": eval_result.get("forbidden_hits", []),
            "warnings": eval_result.get("warnings", []),
        },
    }


def _read_latest_answer() -> str:
    if not LATEST_ANSWER_PATH.exists():
        return ""
    return LATEST_ANSWER_PATH.read_text(encoding="utf-8-sig")


def render_eval_report(
    generated_at: str,
    summary: dict[str, Any],
    case_records: list[dict[str, Any]],
) -> str:
    lines = [
        "# LLM Evaluation Report",
        "",
        f"Generated at: {generated_at}",
        "",
        "## Summary",
        "| total | passed | failed | warnings | pass_rate |",
        "| --- | --- | --- | --- | --- |",
        (
            f"| {summary['total']} | {summary['passed']} | {summary['failed']} | "
            f"{summary['warnings']} | {summary['pass_rate']} |"
        ),
        "",
        "## Case Results",
        "| case_id | category | status | score | repair_used | key failures |",
        "| --- | --- | --- | --- | --- | --- |",
    ]

    for record in case_records:
        case = record["case"]
        result = record["eval_result"]
        failures = _key_failures(result)
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(case.get("id")),
                    _cell(case.get("category")),
                    _cell(result.get("status")),
                    _cell(result.get("score")),
                    _cell(record.get("repair_used", False)),
                    _cell(failures),
                ]
            )
            + " |"
        )

    failed_records = [
        record for record in case_records if record["eval_result"].get("status") == "fail"
    ]
    lines.extend(["", "## Failed Cases", ""])
    if not failed_records:
        lines.append("No failed cases.")
    else:
        for record in failed_records:
            case = record["case"]
            result = record["eval_result"]
            lines.extend(
                [
                    f"### {case.get('id')}",
                    "",
                    f"- question: {case.get('question')}",
                    f"- missing required terms: {_missing_required_terms(result)}",
                    f"- forbidden hits: {', '.join(result.get('forbidden_hits', [])) or 'None'}",
                    f"- warnings: {', '.join(result.get('warnings', [])) or 'None'}",
                    "",
                ]
            )

    lines.extend(
        [
            "",
            "## Methodology",
            "Rule-based local evaluation. It does not prove model correctness; it only checks known boundary conditions.",
            "",
        ]
    )
    return "\n".join(lines)


def _key_failures(result: dict[str, Any]) -> str:
    parts = []
    missing = _missing_required_terms(result)
    if missing != "None":
        parts.append(f"missing: {missing}")
    forbidden = result.get("forbidden_hits", [])
    if forbidden:
        parts.append("forbidden: " + ", ".join(forbidden))
    warnings = result.get("warnings", [])
    if warnings:
        parts.append("warnings: " + ", ".join(warnings))
    return "; ".join(parts) if parts else "None"


def _missing_required_terms(result: dict[str, Any]) -> str:
    missing = _missing_required_terms_list(result)
    return ", ".join(missing) if missing else "None"


def _missing_required_terms_list(result: dict[str, Any]) -> list[str]:
    missing = []
    for check in result.get("required_checks", []):
        if check.get("status") == "fail":
            missing.append("/".join(str(term) for term in check.get("terms_any", [])))
    return missing


def _cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _write_utf8_markdown(path: Path, content: str) -> None:
    # Keep Windows PowerShell Get-Content -Raw from treating UTF-8 as ANSI.
    path.write_text("\ufeff" + content, encoding="utf-8")


if __name__ == "__main__":
    main()

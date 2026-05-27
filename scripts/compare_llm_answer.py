from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
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

from llm.comparison_validator import validate_comparison_answer
from llm.deepseek_client import call_deepseek_chat
from llm.deepseek_prompt_package import build_deepseek_prompt_package
from llm.provider_response import ProviderResponse, empty_usage


CONTEXT_JSON_PATH = PROJECT_ROOT / "outputs" / "reports" / "llm_context_pack.json"
LATEST_ANSWER_PATH = PROJECT_ROOT / "outputs" / "reports" / "latest_llm_answer.md"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "model_eval"
EXTERNAL_CONFIG_PATH = PROJECT_ROOT / "configs" / "external_llm.yaml"
EXTERNAL_CONFIG_EXAMPLE_PATH = PROJECT_ROOT / "configs" / "external_llm.yaml.example"


def main() -> None:
    args = _parse_args()
    questions = _load_questions(args)
    providers = _parse_providers(args.providers)
    context_json = _load_json(CONTEXT_JSON_PATH)
    external_config = _load_external_config()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / f"deepseek_compare_{timestamp}.json"
    md_path = OUTPUT_DIR / f"deepseek_compare_{timestamp}.md"

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "context_mode": args.context_mode,
        "dry_run": args.dry_run,
        "providers": providers,
        "results": [],
        "human_preference": _empty_human_preference(),
        "notes": [],
    }
    if not os.environ.get("DEEPSEEK_API_KEY"):
        report["notes"].append("DEEPSEEK_API_KEY is not set; DeepSeek providers will return success=false unless dry-run is used.")

    for question_item in questions:
        question_id = str(question_item.get("id") or "single_question")
        question = str(question_item.get("question") or "").strip()
        style = str(question_item.get("style") or args.style or "analyst_memo")
        if not question:
            continue
        prompt_package = build_deepseek_prompt_package(
            question=question,
            answer_style=style,
            context_json=context_json,
            context_mode=args.context_mode,
            prompt_preview_chars=args.prompt_preview_chars,
        )
        question_result = {
            "question_id": question_id,
            "question": question,
            "style": style,
            "context_mode": args.context_mode,
            "prompt_package": prompt_package.to_report_dict(save_full_prompt=args.save_full_prompt),
            "provider_results": [],
            "human_preference": _empty_human_preference(),
        }
        for provider in providers:
            provider_result = _run_provider(
                provider=provider,
                question=question,
                style=style,
                prompt_package=prompt_package,
                external_config=external_config,
                args=args,
            )
            question_result["provider_results"].append(provider_result)
        report["results"].append(question_result)

    json_path.write_text("\ufeff" + json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ok",
                "json_path": str(json_path),
                "markdown_path": str(md_path),
                "question_count": len(report["results"]),
                "providers": providers,
                "dry_run": args.dry_run,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _run_provider(
    *,
    provider: str,
    question: str,
    style: str,
    prompt_package: Any,
    external_config: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    if provider == "qwen":
        if args.dry_run:
            response = ProviderResponse(
                provider="qwen",
                model="qwen3:4b",
                answer_text="",
                usage=empty_usage(),
                success=False,
                raw_error="Skipped qwen call because --dry-run was set.",
                metadata={"dry_run": True},
            )
        else:
            response = _call_qwen_subprocess(question, style)
        validator_facts = prompt_package.validator_facts
    elif provider in {"deepseek-flash", "deepseek-pro"}:
        response = _run_deepseek_provider(
            provider=provider,
            prompt_package=prompt_package,
            external_config=external_config,
            dry_run=args.dry_run,
        )
        validator_facts = prompt_package.validator_facts
    else:
        response = ProviderResponse(
            provider=provider,
            model="unknown",
            answer_text="",
            usage=empty_usage(),
            success=False,
            raw_error=f"Unknown provider: {provider}",
        )
        validator_facts = prompt_package.validator_facts

    flags = validate_comparison_answer(response.answer_text, validator_facts) if response.answer_text else {}
    result = response.to_dict()
    result.update(
        {
            "provider_id": provider,
            "validator_flags": flags,
            "prompt_chars": prompt_package.prompt_chars if provider.startswith("deepseek") else None,
            "prompt_preview": prompt_package.prompt_preview if provider.startswith("deepseek") else None,
            "human_preference": _empty_human_preference(),
        }
    )
    return result


def _run_deepseek_provider(
    *,
    provider: str,
    prompt_package: Any,
    external_config: dict[str, Any],
    dry_run: bool,
) -> ProviderResponse:
    config = _deepseek_config(external_config)
    model_key = "flash_model" if provider == "deepseek-flash" else "pro_model"
    model = str(config.get(model_key) or config.get("default_model") or provider)
    model = _env_override_model(provider, model)
    pricing = config.get("pricing_cny_per_million_tokens")
    if dry_run:
        return ProviderResponse(
            provider="deepseek",
            model=model,
            answer_text="",
            latency_seconds=0.0,
            usage=empty_usage(),
            success=True,
            raw_error=None,
            metadata={"dry_run": True, "pricing_assumption": pricing.get(model) if isinstance(pricing, dict) else None},
        )
    return call_deepseek_chat(
        prompt_package.messages,
        model=model,
        base_url=str(os.environ.get("DEEPSEEK_BASE_URL") or config.get("base_url") or "https://api.deepseek.com"),
        timeout_seconds=int(config.get("timeout_seconds") or 240),
        temperature=float(config.get("temperature") if config.get("temperature") is not None else 0.2),
        max_output_tokens=int(config.get("max_output_tokens") or 4096),
        pricing=pricing if isinstance(pricing, dict) else None,
    )


def _call_qwen_subprocess(question: str, style: str) -> ProviderResponse:
    started = time.perf_counter()
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "ask_local_ai.py"),
        "--style",
        style,
        question,
    ]
    completed = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
    )
    latency = time.perf_counter() - started
    metadata = _extract_json_summary(completed.stdout)
    answer_text = ""
    if LATEST_ANSWER_PATH.exists():
        answer_text = LATEST_ANSWER_PATH.read_text(encoding="utf-8-sig", errors="replace").strip()
    success = completed.returncode == 0 and bool(answer_text)
    return ProviderResponse(
        provider="qwen",
        model=str(metadata.get("model") or "qwen3:4b"),
        answer_text=answer_text,
        latency_seconds=round(latency, 3),
        usage=empty_usage(),
        estimated_cost_cny=0.0,
        raw_error=None if success else (completed.stderr or metadata.get("error") or f"qwen exited {completed.returncode}"),
        success=success,
        metadata={
            "returncode": completed.returncode,
            "answer_mode": metadata.get("answer_mode"),
            "fallback_reason": metadata.get("fallback_reason"),
            "eval_case_id": metadata.get("eval_case_id"),
            "guardrail_triggers": metadata.get("guardrail_triggers"),
            "answer_path": metadata.get("answer_path"),
        },
    )


def _extract_json_summary(stdout: str) -> dict[str, Any]:
    marker = '{\n  "status"'
    start = stdout.rfind(marker)
    if start < 0:
        marker = '{"status"'
        start = stdout.rfind(marker)
    if start < 0:
        return {}
    try:
        parsed = json.loads(stdout[start:])
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _load_questions(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.question:
        return [{"id": "single_question", "style": args.style, "question": args.question}]
    if not args.questions_file:
        raise SystemExit("Either --question or --questions-file is required.")
    path = PROJECT_ROOT / args.questions_file
    data = _load_structured_file(path)
    questions = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(questions, list):
        raise SystemExit(f"Question file must contain a questions list: {path}")
    return [item for item in questions if isinstance(item, dict)]


def _load_external_config() -> dict[str, Any]:
    path = EXTERNAL_CONFIG_PATH if EXTERNAL_CONFIG_PATH.exists() else EXTERNAL_CONFIG_EXAMPLE_PATH
    if not path.exists():
        return {}
    return _load_structured_file(path)


def _load_structured_file(path: Path) -> dict[str, Any]:
    raw_text = path.read_text(encoding="utf-8-sig")
    if yaml is not None:
        loaded = yaml.safe_load(raw_text)
    else:
        loaded = _parse_simple_yaml(raw_text)
    return loaded if isinstance(loaded, dict) else {}


def _parse_simple_yaml(raw_text: str) -> dict[str, Any]:
    lines = raw_text.splitlines()
    if any(line.strip() == "questions:" for line in lines):
        return _parse_questions_yaml(lines)
    return _parse_mapping_yaml(lines)


def _parse_questions_yaml(lines: list[str]) -> dict[str, Any]:
    questions: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped == "questions:":
            continue
        if stripped.startswith("- "):
            if current:
                questions.append(current)
            current = {}
            remainder = stripped[2:].strip()
            if remainder:
                key, value = _split_yaml_key_value(remainder)
                current[key] = _parse_scalar(value)
            continue
        if current is not None and ":" in stripped:
            key, value = _split_yaml_key_value(stripped)
            current[key] = _parse_scalar(value)
    if current:
        questions.append(current)
    return {"questions": questions}


def _parse_mapping_yaml(lines: list[str]) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if stripped.startswith("- "):
            continue
        if ":" not in stripped:
            continue
        key, value = _split_yaml_key_value(stripped)
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if value == "":
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _parse_scalar(value)
    return root


def _split_yaml_key_value(text: str) -> tuple[str, str]:
    key, value = text.split(":", 1)
    return key.strip().strip('"').strip("'"), value.strip()


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"", "null", "None", "~"}:
        return None if value else ""
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Missing context JSON: {path}. Run scripts/run_llm_context_pack.py first.")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise SystemExit(f"Context JSON root must be an object: {path}")
    return data


def _deepseek_config(external_config: dict[str, Any]) -> dict[str, Any]:
    root = external_config.get("external_llm") if isinstance(external_config, dict) else {}
    deepseek = root.get("deepseek") if isinstance(root, dict) else {}
    return deepseek if isinstance(deepseek, dict) else {}


def _env_override_model(provider: str, default: str) -> str:
    if provider == "deepseek-flash":
        return os.environ.get("DEEPSEEK_MODEL_FLASH") or default
    if provider == "deepseek-pro":
        return os.environ.get("DEEPSEEK_MODEL_PRO") or default
    return default


def _parse_providers(raw_value: str) -> list[str]:
    providers = [item.strip() for item in raw_value.split(",") if item.strip()]
    return providers or ["qwen", "deepseek-flash"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare local qwen and optional DeepSeek answers.")
    parser.add_argument("--question", default="")
    parser.add_argument("--style", default="analyst_memo")
    parser.add_argument("--questions-file", default="")
    parser.add_argument("--providers", default="qwen,deepseek-flash")
    parser.add_argument("--context-mode", choices=["sanitized", "full"], default="sanitized")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--save-full-prompt", action="store_true")
    parser.add_argument("--prompt-preview-chars", type=int, default=1200)
    return parser.parse_args()


def _empty_human_preference() -> dict[str, Any]:
    return {
        "winner": "",
        "qwen_score_1_to_5": None,
        "deepseek_flash_score_1_to_5": None,
        "deepseek_pro_score_1_to_5": None,
        "reason": "",
        "useful_parts": "",
        "bad_parts": "",
        "should_update_prompt_profile": None,
    }


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# DeepSeek Comparison Report",
        "",
        f"- generated_at: {report.get('generated_at')}",
        f"- context_mode: {report.get('context_mode')}",
        f"- dry_run: {report.get('dry_run')}",
        f"- providers: {', '.join(report.get('providers', []))}",
        "",
        "No automatic winner is selected. Fill in human_preference after manual review.",
        "",
    ]
    for item in report.get("results", []):
        lines.extend(
            [
                f"## {item.get('question_id')}",
                "",
                f"Question: {item.get('question')}",
                "",
            ]
        )
        for provider_result in item.get("provider_results", []):
            lines.extend(
                [
                    f"### {provider_result.get('provider_id')}",
                    "",
                    f"- provider: {provider_result.get('provider')}",
                    f"- model: {provider_result.get('model')}",
                    f"- success: {provider_result.get('success')}",
                    f"- latency_seconds: {provider_result.get('latency_seconds')}",
                    f"- estimated_cost_cny: {provider_result.get('estimated_cost_cny')}",
                    f"- usage: `{json.dumps(provider_result.get('usage'), ensure_ascii=False)}`",
                    f"- metadata: `{json.dumps(provider_result.get('metadata'), ensure_ascii=False)}`",
                    f"- error: {provider_result.get('raw_error') or ''}",
                    f"- validator_flags: `{json.dumps(provider_result.get('validator_flags'), ensure_ascii=False)}`",
                    "",
                    "Answer:",
                    "",
                    provider_result.get("answer_text") or "_No answer text._",
                    "",
                ]
            )
        lines.extend(
            [
                "Human preference:",
                "",
                "```json",
                json.dumps(item.get("human_preference"), ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


if __name__ == "__main__":
    main()

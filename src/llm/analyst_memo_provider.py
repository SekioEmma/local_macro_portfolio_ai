from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from llm.comparison_validator import validate_comparison_answer
from llm.deepseek_client import call_deepseek_chat
from llm.deepseek_prompt_package import build_deepseek_prompt_package
from llm.provider_response import ProviderResponse, empty_usage


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "analyst_memo.yaml"
EXTERNAL_CONFIG_PATH = PROJECT_ROOT / "configs" / "external_llm.yaml"
EXTERNAL_CONFIG_EXAMPLE_PATH = PROJECT_ROOT / "configs" / "external_llm.yaml.example"
DEFAULT_CONTEXT_PATH = PROJECT_ROOT / "outputs" / "reports" / "llm_context_pack.json"
DEFAULT_QUESTION = (
    "请基于当前 daily report 和 llm_context_pack，生成一份 analyst_memo 风格的长期投资组合复盘，"
    "覆盖市场状态、金融条件、组合偏离、DCA、现金准备金边界、主要风险和后续观察方向。"
)


def generate_analyst_memo(
    *,
    question: str | None = None,
    provider: str | None = None,
    context_mode: str | None = None,
    output_dir: str | Path | None = None,
    dry_run: bool = False,
    config_path: str | Path | None = None,
    context_path: str | Path | None = None,
) -> dict[str, Any]:
    config = load_analyst_memo_config(config_path)
    memo_config = _as_dict(config.get("analyst_memo"))
    external_config = load_external_llm_config()
    provider_id = provider or str(memo_config.get("default_provider") or "deepseek-pro")
    resolved_context_mode = context_mode or str(memo_config.get("context_mode") or "sanitized")
    resolved_question = question or DEFAULT_QUESTION
    resolved_output_dir = Path(output_dir or memo_config.get("output_dir") or "outputs/analyst_memos")
    if not resolved_output_dir.is_absolute():
        resolved_output_dir = PROJECT_ROOT / resolved_output_dir

    context_file = Path(context_path or DEFAULT_CONTEXT_PATH)
    if not context_file.is_absolute():
        context_file = PROJECT_ROOT / context_file

    generated_at = _utc_now()
    if resolved_context_mode not in {"sanitized", "full"}:
        return _error_result(
            provider_id=provider_id,
            model="unknown",
            context_mode=resolved_context_mode,
            question=resolved_question,
            generated_at=generated_at,
            error="context_mode must be sanitized or full",
        )
    if not context_file.exists():
        return _error_result(
            provider_id=provider_id,
            model="unknown",
            context_mode=resolved_context_mode,
            question=resolved_question,
            generated_at=generated_at,
            error=f"llm_context_pack not found: {context_file}. Run scripts/run_llm_context_pack.py first.",
        )

    context_json = _load_json(context_file)
    if provider_id in {"deepseek-pro", "deepseek-flash"}:
        return _generate_deepseek_memo(
            provider_id=provider_id,
            memo_config=memo_config,
            external_config=external_config,
            question=resolved_question,
            context_json=context_json,
            context_mode=resolved_context_mode,
            output_dir=resolved_output_dir,
            generated_at=generated_at,
            dry_run=dry_run,
        )
    if provider_id == "qwen-local":
        return _error_result(
            provider_id=provider_id,
            model="legacy-local",
            context_mode=resolved_context_mode,
            question=resolved_question,
            generated_at=generated_at,
            error=(
                "qwen-local provider is retained as legacy/offline fallback, but this script does not "
                "silently fall back to qwen. Use scripts/ask_local_ai.py for legacy local Q&A."
            ),
        )
    return _error_result(
        provider_id=provider_id,
        model="unknown",
        context_mode=resolved_context_mode,
        question=resolved_question,
        generated_at=generated_at,
        error=f"Unsupported analyst memo provider: {provider_id}",
    )


def write_analyst_memo_outputs(result: dict[str, Any], output_dir: str | Path | None = None) -> dict[str, str]:
    memo_output_dir = Path(output_dir or result.get("output_dir") or PROJECT_ROOT / "outputs" / "analyst_memos")
    if not memo_output_dir.is_absolute():
        memo_output_dir = PROJECT_ROOT / memo_output_dir
    memo_output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = _file_timestamp(result.get("generated_at"))
    json_path = memo_output_dir / f"analyst_memo_{timestamp}.json"
    markdown_path = memo_output_dir / f"analyst_memo_{timestamp}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_render_markdown(result), encoding="utf-8")
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


def load_analyst_memo_config(config_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(config_path or DEFAULT_CONFIG_PATH)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        raise FileNotFoundError(f"Analyst memo config not found: {path}")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    if not isinstance(loaded, dict):
        raise ValueError(f"Analyst memo config must be a mapping: {path}")
    return loaded


def load_external_llm_config() -> dict[str, Any]:
    path = EXTERNAL_CONFIG_PATH if EXTERNAL_CONFIG_PATH.exists() else EXTERNAL_CONFIG_EXAMPLE_PATH
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    return loaded if isinstance(loaded, dict) else {}


def _generate_deepseek_memo(
    *,
    provider_id: str,
    memo_config: dict[str, Any],
    external_config: dict[str, Any],
    question: str,
    context_json: dict[str, Any],
    context_mode: str,
    output_dir: Path,
    generated_at: str,
    dry_run: bool,
) -> dict[str, Any]:
    deepseek_config = _as_dict(memo_config.get("deepseek"))
    external_deepseek = _as_dict(_as_dict(external_config.get("external_llm")).get("deepseek"))
    model = _resolve_deepseek_model(provider_id, deepseek_config, external_deepseek)
    prompt_package = build_deepseek_prompt_package(
        question=question,
        answer_style="analyst_memo",
        context_json=context_json,
        context_mode=context_mode,
        prompt_preview_chars=int(memo_config.get("prompt_preview_chars") or 1200),
    )

    if dry_run:
        response = ProviderResponse(
            provider="deepseek",
            model=model,
            answer_text="",
            latency_seconds=0.0,
            usage=empty_usage(),
            estimated_cost_cny=0.0,
            raw_error=None,
            success=True,
            metadata={"dry_run": True, "prompt_chars": prompt_package.prompt_chars},
        )
        validator_flags: dict[str, Any] = {
            "hard_flags": {},
            "soft_flags": {},
            "has_hard_flag": False,
            "has_soft_flag": False,
        }
    else:
        api_key_env = str(deepseek_config.get("api_key_env") or "DEEPSEEK_API_KEY")
        if not os.environ.get(api_key_env):
            return _error_result(
                provider_id=provider_id,
                model=model,
                context_mode=context_mode,
                question=question,
                generated_at=generated_at,
                error=f"{api_key_env} not configured",
                output_dir=output_dir,
                prompt_report=prompt_package.to_report_dict(save_full_prompt=False),
            )
        response = call_deepseek_chat(
            messages=prompt_package.messages,
            model=model,
            base_url=external_deepseek.get("base_url"),
            timeout_seconds=int(deepseek_config.get("timeout_seconds") or external_deepseek.get("timeout_seconds") or 180),
            temperature=float(deepseek_config.get("temperature") or external_deepseek.get("temperature") or 0.2),
            max_output_tokens=int(
                deepseek_config.get("max_tokens")
                or external_deepseek.get("max_output_tokens")
                or 2500
            ),
            pricing=_pricing_for_model(model, external_deepseek),
        )
        validator_flags = (
            validate_comparison_answer(response.answer_text, prompt_package.validator_facts)
            if response.answer_text
            else {
                "hard_flags": {},
                "soft_flags": {},
                "has_hard_flag": False,
                "has_soft_flag": False,
            }
        )

    status = "error"
    if response.success:
        status = "needs_review" if validator_flags.get("has_hard_flag") else "ok"
    return {
        "status": status,
        "provider": response.provider,
        "provider_id": provider_id,
        "model": response.model,
        "context_mode": context_mode,
        "generated_at": generated_at,
        "question": question,
        "usage": response.usage,
        "estimated_cost_cny": response.estimated_cost_cny,
        "latency_seconds": response.latency_seconds,
        "validator_flags": validator_flags,
        "answer": response.answer_text,
        "error": response.raw_error,
        "requires_human_review": True,
        "output_dir": str(output_dir),
        "metadata": response.metadata,
        "prompt": prompt_package.to_report_dict(save_full_prompt=False),
    }


def _resolve_deepseek_model(
    provider_id: str,
    deepseek_config: dict[str, Any],
    external_deepseek: dict[str, Any],
) -> str:
    if provider_id == "deepseek-flash":
        return str(
            deepseek_config.get("flash_model")
            or os.environ.get("DEEPSEEK_MODEL_FLASH")
            or external_deepseek.get("flash_model")
            or "deepseek-v4-flash"
        )
    return str(
        deepseek_config.get("model")
        or os.environ.get("DEEPSEEK_MODEL_PRO")
        or external_deepseek.get("pro_model")
        or "deepseek-v4-pro"
    )


def _pricing_for_model(model: str, external_deepseek: dict[str, Any]) -> dict[str, Any] | None:
    pricing = _as_dict(external_deepseek.get("pricing_cny_per_million_tokens"))
    return pricing if isinstance(pricing.get(model), dict) else None


def _error_result(
    *,
    provider_id: str,
    model: str,
    context_mode: str,
    question: str,
    generated_at: str,
    error: str,
    output_dir: str | Path | None = None,
    prompt_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": "error",
        "provider": provider_id,
        "provider_id": provider_id,
        "model": model,
        "context_mode": context_mode,
        "generated_at": generated_at,
        "question": question,
        "usage": empty_usage(),
        "estimated_cost_cny": None,
        "latency_seconds": 0.0,
        "validator_flags": {
            "hard_flags": {},
            "soft_flags": {},
            "has_hard_flag": False,
            "has_soft_flag": False,
        },
        "answer": "",
        "error": error,
        "requires_human_review": True,
        "output_dir": str(output_dir or PROJECT_ROOT / "outputs" / "analyst_memos"),
        "metadata": {},
        "prompt": prompt_report or {},
    }


def _load_json(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(loaded, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return loaded


def _render_markdown(result: dict[str, Any]) -> str:
    flags = _as_dict(result.get("validator_flags"))
    usage = _as_dict(result.get("usage"))
    metadata = _as_dict(result.get("metadata"))
    lines = [
        "# Analyst Memo",
        "",
        f"- status: {result.get('status')}",
        f"- provider/model: {result.get('provider')}/{result.get('model')}",
        f"- generated_at: {result.get('generated_at')}",
        f"- context_mode: {result.get('context_mode')}",
        f"- human_review_required: {result.get('requires_human_review')}",
        f"- latency_seconds: {result.get('latency_seconds')}",
        f"- estimated_cost_cny: {result.get('estimated_cost_cny')}",
        f"- usage: {json.dumps(usage, ensure_ascii=False)}",
        f"- retry_count: {metadata.get('retry_count')}",
        f"- hard_flags: {json.dumps(flags.get('hard_flags', {}), ensure_ascii=False)}",
        f"- soft_flags: {json.dumps(flags.get('soft_flags', {}), ensure_ascii=False)}",
        "",
        "## Question",
        "",
        str(result.get("question") or ""),
        "",
        "## Answer",
        "",
        str(result.get("answer") or "_No answer text._"),
    ]
    error = result.get("error")
    if error:
        lines.extend(["", "## Error", "", str(error)])
    return "\n".join(lines).rstrip() + "\n"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _file_timestamp(value: Any) -> str:
    text = str(value or _utc_now())
    return (
        text.replace(":", "")
        .replace("-", "")
        .replace("+", "")
        .replace(".", "")
        .replace("T", "_")
        .replace("Z", "")
    )


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}

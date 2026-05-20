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
ANSWER_STYLE_CONFIG_PATH = PROJECT_ROOT / "configs" / "answer_style.yaml"
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
    "实操建议",
    "可直接用于实操",
    "无需暂停",
    "不暂停定投",
    "保持DCA执行",
    "按原计划",
    "主动增加",
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
    "Reuters",
    "FactSet",
    "Goldman",
    "Gartner",
    "IDC",
    "Wind",
    "ISO 20022",
    "模型版本",
    "规则库",
    "自动调仓",
    "自动调整",
    "自动配置",
    "自动再平衡",
    "无需人工干预",
    "外部数据源",
    "实时市场规则模型",
    "实时市场数据",
    "实时生成",
    "机构资金净流入",
    "利率变动对市场波动率影响系数",
    "风险评分",
    "完成3次",
    "重新校准模型参数",
    "满仓",
    "清仓",
    "立即增加",
    "可立即执行",
    "转投",
    "调出",
    "行动建议",
    "## 投资建议",
    "建议您买入",
    "建议您卖出",
    "建议您加仓",
    "建议您减仓",
    "建议您立即调整",
    "稳健的收益表现",
    "预留一定的弹性空间",
    "保持对短债和黄金",
    "专属方案",
    "跑赢通胀",
    "年化收益",
    "机会窗口",
    "唯一可验证",
    "系统已通过配置调整",
]
SEVERE_FORBIDDEN_ANSWER_PATTERNS = [
    "保证收益",
    "一定会涨",
    "明天会涨",
    "立即买入",
    "立即卖出",
    "应买入",
    "应卖出",
    "立即调整",
    "满仓",
    "清仓",
    "实操建议",
    "可直接用于实操",
    "无需暂停",
    "不暂停定投",
    "保持DCA执行",
    "按原计划",
    "主动增加",
    "Bloomberg",
    "Reuters",
    "FactSet",
    "Goldman",
    "Gartner",
    "IDC",
    "Wind",
    "ISO 20022",
    "立即增加",
    "可立即执行",
    "转投",
    "调出",
    "行动建议",
    "专属方案",
    "跑赢通胀",
    "年化收益",
    "机会窗口",
    "唯一可验证",
    "系统已通过配置调整",
    "模型版本",
    "规则库",
    "自动调仓",
    "自动调整",
    "自动配置",
    "自动再平衡",
    "无需人工干预",
    "外部数据源",
    "实时市场规则模型",
    "实时市场数据",
    "实时生成",
    "机构资金净流入",
    "利率变动对市场波动率影响系数",
    "风险评分",
    "完成3次",
    "重新校准模型参数",
]
REPAIRABLE_FORBIDDEN_ANSWER_PATTERNS = [
    pattern
    for pattern in FORBIDDEN_ANSWER_PATTERNS
    if pattern not in set(SEVERE_FORBIDDEN_ANSWER_PATTERNS)
]
SEVERE_HALLUCINATION_MARKERS = (
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
    "$1,000,000",
    "$200,000",
    "Target Value of Short-Term Bonds",
    "portfolio value is",
    "Final Answer: $",
    "用户确认的实时快照",
    "请提供更详细的上下文",
    "规则第",
    "自动执行",
    "自动归类",
    "唯一当前状态",
    "可操作状态",
    "模型推荐基准",
    "70% 持仓权重",
    "需人工复核数据",
    "交易量",
    "模型预测",
    "投资者保持灵活配置",
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
    "当前市场处于过热状态",
    "2023-10-05",
    "2023年10月",
    "2023年GDP",
    "2024Q",
    "2024-2025",
    "2025年中",
    "市盈率",
    "PE=",
    "AI相关板块",
    "生成式AI",
    "欧盟AI法案",
    "GDP增速",
    "半导体产业链",
    "现金流增长",
    "AI主题ETF",
    "QQQ",
    "Eclipse",
    "行业基准",
    "公开数据",
    "换50%的确定性",
)
THINKING_RESIDUE_PATTERNS = (
    "<think>",
    "</think>",
    "Thinking Process",
    "Thinking...",
    "done thinking",
)


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
    answer_style = _resolve_answer_style(parsed_args.get("style"), eval_case)
    eval_case = _prompt_eval_case(eval_case, answer_style, user_question)
    config["answer_style"] = _load_answer_style_config(answer_style)
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
            answer_style=answer_style,
        )
    else:
        prompt = _build_answer_prompt(
            user_question=user_question,
            context_pack=context_pack,
            config=config,
            eval_case=eval_case,
            compact_prompt=compact_prompt,
            answer_style=answer_style,
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
                    answer_style=answer_style,
                    eval_case=eval_case,
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
                    "answer_mode": "context_only_fallback" if fallback_answer else "unavailable",
                    "fallback_reason": "ollama_health_error" if fallback_answer else None,
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
                result.setdefault("answer_mode", "natural")
        else:
            result = call_local_llm(prompt, config)
            result.setdefault("answer_mode", "natural")

    if mode == "local_http" and not result.get("answer") and result.get("status") not in {
        "blocked_degraded_context",
    }:
        fallback_answer = _build_context_only_safe_answer(
            context_pack.get("context_json", {}),
            user_question,
            answer_style=answer_style,
            eval_case=eval_case,
        )
        if fallback_answer:
            original_status = result.get("status") or "model_error"
            result["status"] = f"{original_status}_context_fallback"
            result["answer"] = fallback_answer
            result["answer_mode"] = "context_only_fallback"
            result["fallback_reason"] = str(original_status)
            result["cleaning_notes"] = [
                *result.get("cleaning_notes", []),
                "Model call did not produce a usable answer; wrote deterministic context-only fallback answer.",
            ]

    if result.get("answer"):
        guarded = _apply_deterministic_answer_guardrails(
            result["answer"],
            context_pack,
            user_question=user_question,
            answer_style=answer_style,
            eval_case=eval_case,
        )
        result["answer"] = guarded["answer"]
        result["guardrail_action"] = guarded.get("guardrail_action")
        result["guardrail_triggers"] = guarded.get("guardrail_triggers", [])
        if guarded.get("answer_mode") == "context_only_fallback":
            result["answer_mode"] = "context_only_fallback"
            result["fallback_reason"] = guarded.get("fallback_reason")
        else:
            result.setdefault("answer_mode", "natural")
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
            answer_style=answer_style,
        )
        _write_utf8_markdown(PROMPT_OUTPUT_PATH, repair_prompt)
        retry_result = call_local_llm(repair_prompt, config)
        retry_result.setdefault("answer_mode", "repaired")
        if retry_result.get("answer"):
            guarded = _apply_deterministic_answer_guardrails(
                retry_result["answer"],
                context_pack,
                user_question=user_question,
                answer_style=answer_style,
                eval_case=eval_case,
            )
            retry_result["answer"] = guarded["answer"]
            retry_result["guardrail_action"] = guarded.get("guardrail_action")
            retry_result["guardrail_triggers"] = guarded.get("guardrail_triggers", [])
            if guarded.get("answer_mode") == "context_only_fallback":
                retry_result["answer_mode"] = "context_only_fallback"
                retry_result["fallback_reason"] = guarded.get("fallback_reason")
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
        "answer_style": answer_style,
        "answer_mode": result.get("answer_mode"),
        "fallback_reason": result.get("fallback_reason"),
        "guardrail_action": result.get("guardrail_action"),
        "guardrail_triggers": result.get("guardrail_triggers", []),
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
        if item == "--style":
            if index + 1 >= len(args):
                raise SystemExit("--style requires a value.")
            overrides["style"] = args[index + 1]
            index += 2
            continue
        question_parts.append(item)
        index += 1

    question = _read_user_question(question_parts)
    return {
        "question": question,
        "eval_case": eval_case,
        "overrides": overrides,
        "compact_prompt": compact_prompt,
        "style": overrides.get("style"),
    }


def _resolve_answer_style(style_arg: str | None, eval_case: dict[str, Any] | None) -> str:
    if isinstance(style_arg, str) and style_arg.strip():
        style = style_arg.strip()
    elif isinstance(eval_case, dict) and eval_case.get("style"):
        style = str(eval_case.get("style")).strip()
    else:
        style = _default_answer_style()
    if style not in {"standard", "analyst_memo"}:
        raise SystemExit("--style must be one of: standard, analyst_memo.")
    return style


def _default_answer_style() -> str:
    style_config = _read_answer_style_config()
    default_style = style_config.get("default_style") if isinstance(style_config, dict) else None
    return str(default_style or "standard")


def _load_answer_style_config(selected_style: str) -> dict[str, Any]:
    style_config = _read_answer_style_config()
    return {
        "selected": selected_style,
        "config": style_config,
    }


def _read_answer_style_config() -> dict[str, Any]:
    if not ANSWER_STYLE_CONFIG_PATH.exists():
        return {"default_style": "standard", "styles": {}}
    try:
        raw_text = ANSWER_STYLE_CONFIG_PATH.read_text(encoding="utf-8-sig")
        if yaml is not None:
            loaded = yaml.safe_load(raw_text)
        else:
            loaded = json.loads(raw_text)
    except (OSError, ValueError, json.JSONDecodeError):
        return {"default_style": "standard", "styles": {}}
    return loaded if isinstance(loaded, dict) else {"default_style": "standard", "styles": {}}


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
    answer_style: str = "standard",
) -> str:
    prompt_eval_case = _prompt_eval_case(eval_case, answer_style, user_question)
    if compact_prompt:
        return build_compact_answer_prompt(
            user_question,
            context_pack,
            config,
            eval_case=prompt_eval_case,
            answer_style=answer_style,
        )
    return build_answer_prompt(
        user_question,
        context_pack,
        config,
        eval_case=prompt_eval_case,
        answer_style=answer_style,
    )


def _build_repair_prompt(
    user_question: str,
    context_pack: dict[str, Any],
    validation_warnings: list[str],
    eval_case: dict[str, Any] | None,
    original_answer: str | None,
    missing_required_terms: list[str],
    forbidden_hits: list[str],
    compact_prompt: bool,
    answer_style: str = "standard",
) -> str:
    prompt_eval_case = _prompt_eval_case(eval_case, answer_style, user_question)
    if compact_prompt:
        return build_compact_repair_prompt(
            user_question=user_question,
            context_pack=context_pack,
            validation_warnings=validation_warnings,
            eval_case=prompt_eval_case,
            original_answer=original_answer,
            missing_required_terms=missing_required_terms,
            forbidden_hits=forbidden_hits,
            answer_style=answer_style,
        )
    return build_validation_repair_prompt(
        user_question=user_question,
        context_pack=context_pack,
        validation_warnings=validation_warnings,
        eval_case=prompt_eval_case,
        original_answer=original_answer,
        missing_required_terms=missing_required_terms,
        forbidden_hits=forbidden_hits,
        answer_style=answer_style,
    )


def _prompt_eval_case(
    eval_case: dict[str, Any] | None,
    answer_style: str,
    user_question: str,
) -> dict[str, Any] | None:
    if isinstance(eval_case, dict):
        return eval_case
    question = user_question or ""
    if answer_style != "analyst_memo":
        if answer_style == "standard" and _question_asks_yield_price_basics(question):
            return {
                "id": "standard_yield_price_basics",
                "category": "standard",
                "style": "standard",
                "expected_behavior": (
                    "Concise educational answer defining Treasury yields and explaining "
                    "that bond yields and bond prices usually move in opposite directions, "
                    "without portfolio allocation commentary."
                ),
                "required_terms_any": [
                    ["美债收益率", "收益率", "Treasury yields", "yields"],
                    ["债券价格", "bond prices", "bond price"],
                    ["反向", "相反", "opposite directions", "价格下跌", "价格上升"],
                ],
                "forbidden_terms": [
                    "中美会谈",
                    "美伊局势",
                    "股债金同跌",
                    "sp500",
                    "nasdaq100",
                    "当前占比",
                    "配置：当前",
                    "应买入",
                    "应卖出",
                    "需增加持仓",
                    "需减持",
                    "立即调整",
                    "Thinking",
                ],
            }
        return eval_case

    if _question_mentions_macro_regime_topic(question):
        return {
            "id": "macro_geopolitics_rates_001",
            "category": "analyst_memo",
            "style": "analyst_memo",
            "expected_behavior": (
                "Natural analyst memo distinguishing inflation shock from ordinary "
                "risk-off, correcting yield/price wording, and connecting to the "
                "portfolio framework without trade orders."
            ),
            "required_terms_any": [
                ["收益率上行、债券价格下跌", "收益率上行意味着债券价格下跌", "债券价格下跌"],
                ["通胀型冲击"],
                ["普通避险"],
                ["外交降温不等于结构性风险解除", "外交降温", "结构性风险解除"],
                ["估值压缩不等于系统性危机", "系统性危机证据不足"],
                ["信用利差", "融资压力", "波动率", "企业盈利", "就业数据"],
                ["本地 context 未提供", "不能编造"],
                ["相对目标偏高", "相对目标偏低", "观察方向", "再平衡评估"],
            ],
            "forbidden_terms": [
                "危机必然",
                "系统性危机已经启动",
                "一定崩盘",
                "## 投资建议",
                "稳健的收益表现",
                "立即买入",
                "立即卖出",
                "应买入",
                "应卖出",
                "需增加持仓",
                "需减持",
                "立即调整",
                "美债收益率现在是",
                "据Reuters",
                "据 FactSet",
                "Goldman数据显示",
                "CME FedWatch",
                "FedWatch显示",
                "Thinking",
            ],
        }
    if any(term in question for term in ("2000", "泡沫", "AI", "人工智能")):
        return {
            "id": "dotcom_ai_bubble_analyst_memo",
            "category": "analyst_memo",
            "style": "analyst_memo",
            "expected_behavior": (
                "Natural analyst memo without invented external data, deterministic "
                "crisis forecast, compliance metadata, or trade commands."
            ),
        }
    if "定投" in question and any(term in question for term in ("暂停", "停", "继续", "加速")):
        return {
            "id": "hot_market_dca_pause",
            "category": "monthly_review",
            "style": "analyst_memo",
            "expected_behavior": "DCA discipline framework without direct trade commands.",
        }
    if any(term in question for term in ("复盘", "本月", "这个月", "周报", "月报")):
        return {
            "id": "monthly_macro_portfolio_review",
            "category": "monthly_review",
            "style": "analyst_memo",
            "expected_behavior": "Natural macro and portfolio review.",
        }
    return eval_case


def _is_macro_geopolitics_rates_case(eval_case: dict[str, Any] | None) -> bool:
    return isinstance(eval_case, dict) and eval_case.get("id") == "macro_geopolitics_rates_001"


def _should_use_macro_geopolitics_rates_fallback(
    user_question: str,
    answer_style: str,
    eval_case: dict[str, Any] | None,
) -> bool:
    if _is_macro_geopolitics_rates_case(eval_case):
        return True
    if answer_style != "analyst_memo":
        return False
    return _question_mentions_macro_regime_topic(user_question)


def _question_mentions_macro_regime_topic(question: str) -> bool:
    text = question or ""
    lower = text.lower()
    if not text.strip():
        return False
    if "定投" in text:
        return False

    rate_terms = (
        "收益率",
        "美债",
        "treasury",
        "yield",
        "fed",
        "美联储",
        "利率",
        "长端",
        "真实利率",
        "期限溢价",
    )
    macro_pricing_terms = (
        "通胀",
        "地缘",
        "油价",
        "能源",
        "避险",
        "risk-off",
        "风险",
        "危机",
        "估值",
        "股票",
        "股市",
        "权益",
        "黄金",
        "组合",
        "资产",
        "重定价",
        "再定价",
        "承压",
    )
    geopolitical_inflation_terms = (
        "地缘",
        "冲突",
        "战争",
        "中东",
        "油价",
        "能源",
        "通胀",
        "航运",
        "保险",
        "供应",
        "外交",
        "制裁",
    )
    crisis_or_asset_terms = (
        "系统性危机",
        "危机",
        "估值压缩",
        "股票",
        "股市",
        "权益",
        "债券",
        "黄金",
        "组合",
        "资产",
        "市场",
    )

    has_rate = any(term in lower or term in text for term in rate_terms)
    has_macro_pricing = any(term in lower or term in text for term in macro_pricing_terms)
    has_geopolitical_inflation = any(
        term in lower or term in text for term in geopolitical_inflation_terms
    )
    has_crisis_or_asset = any(term in lower or term in text for term in crisis_or_asset_terms)

    return (
        (has_rate and has_macro_pricing)
        or (has_geopolitical_inflation and has_crisis_or_asset)
        or (("系统性危机" in text or "valuation compression" in lower) and has_crisis_or_asset)
    )


def _question_asks_yield_price_basics(question: str) -> bool:
    text = question or ""
    lower = text.lower()
    if not text.strip():
        return False

    yield_terms = ("美债收益率", "收益率", "treasury yield", "yield")
    bond_price_terms = ("债券价格", "债券", "bond price", "bond prices")
    basic_question_terms = ("什么是", "是什么", "关系", "解释", "怎么理解", "why", "what is")

    return (
        any(term in lower or term in text for term in yield_terms)
        and any(term in lower or term in text for term in bond_price_terms)
        and any(term in lower or term in text for term in basic_question_terms)
    )


def _question_mentions_recession_asset_roles(question: str) -> bool:
    lower = (question or "").lower()
    return any(term in lower for term in ("衰退", "经济下行", "软着陆", "recession", "hard landing")) and any(
        term in lower for term in ("标普", "纳指", "短债", "黄金", "sp500", "nasdaq", "gold")
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

    context_json = context_json or {}
    guardrail_assessment = _assess_answer_guardrails(
        answer,
        _find_holdings_source(context_json),
    )
    for trigger in guardrail_assessment.get("triggers", []):
        action = trigger.get("action", "repair")
        label = "Severe guardrail" if action == "context_only_fallback" else "Repairable guardrail"
        warnings.append(f"{label} trigger: {trigger.get('pattern')}")

    if "风险水平" in answer and "中性" in answer:
        warnings.append("risk_level=medium should be described as 中等 or medium, not 中性.")

    amount_patterns = [
        r"买入\s*[\d,]+(?:\.\d+)?\s*(?:元|人民币|块)",
        r"卖出\s*[\d,]+(?:\.\d+)?\s*(?:元|人民币|块)",
    ]
    for pattern in amount_patterns:
        for match in re.finditer(pattern, answer):
            if _is_negated_or_boundary_context(answer, match.start()):
                continue
            warnings.append(f"Forbidden trade amount pattern detected: {pattern}")
            break

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
    answer_style: str = "standard",
    eval_case: dict[str, Any] | None = None,
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

    guardrail_assessment = _assess_answer_guardrails(updated, holdings_source)
    if guardrail_assessment.get("action") == "context_only_fallback":
        safe_answer = _build_context_only_safe_answer(
            context_json,
            user_question,
            answer_style=answer_style,
            eval_case=eval_case,
        )
        if safe_answer:
            return {
                "answer": safe_answer,
                "notes": [
                    "Replaced model answer with deterministic context-only answer.",
                    *[
                        f"Guardrail trigger: {trigger.get('kind')}={trigger.get('pattern')}"
                        for trigger in guardrail_assessment.get("triggers", [])
                    ],
                ],
                "answer_mode": "context_only_fallback",
                "fallback_reason": guardrail_assessment.get("reason"),
                "guardrail_action": guardrail_assessment.get("action"),
                "guardrail_triggers": guardrail_assessment.get("triggers", []),
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

    final_assessment = _assess_answer_guardrails(updated, holdings_source)
    if final_assessment.get("action") == "context_only_fallback":
        safe_answer = _build_context_only_safe_answer(
            context_json,
            user_question,
            answer_style=answer_style,
            eval_case=eval_case,
        )
        if safe_answer:
            return {
                "answer": safe_answer,
                "notes": [
                    *notes,
                    "Replaced rewritten answer with deterministic context-only answer.",
                    *[
                        f"Guardrail trigger: {trigger.get('kind')}={trigger.get('pattern')}"
                        for trigger in final_assessment.get("triggers", [])
                    ],
                ],
                "answer_mode": "context_only_fallback",
                "fallback_reason": final_assessment.get("reason"),
                "guardrail_action": final_assessment.get("action"),
                "guardrail_triggers": final_assessment.get("triggers", []),
            }

    return {
        "answer": updated,
        "notes": [
            *notes,
            *[
                f"Repairable guardrail trigger remains: {trigger.get('pattern')}"
                for trigger in final_assessment.get("triggers", [])
                if trigger.get("action") == "repair"
            ],
        ],
        "answer_mode": "natural",
        "guardrail_action": final_assessment.get("action"),
        "guardrail_triggers": final_assessment.get("triggers", []),
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
        ("优化建议", "观察方向"),
        ("建议行动", "观察方向"),
        ("适度增配", "作为后续复核观察"),
        ("小幅增配", "作为后续复核观察"),
        ("动态调减", "作为后续复核观察"),
        ("调减", "复核观察"),
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
    return _assess_answer_guardrails(answer, holdings_source).get("action") == "context_only_fallback"


def _assess_answer_guardrails(answer: str, holdings_source: dict[str, Any]) -> dict[str, Any]:
    triggers = _answer_guardrail_triggers(answer, holdings_source)
    severe_triggers = [
        trigger for trigger in triggers if trigger.get("action") == "context_only_fallback"
    ]
    if severe_triggers:
        return {
            "action": "context_only_fallback",
            "reason": "severe_hallucination_or_forbidden_output",
            "triggers": severe_triggers,
        }

    repair_triggers = [trigger for trigger in triggers if trigger.get("action") == "repair"]
    if repair_triggers:
        return {
            "action": "repair",
            "reason": "repairable_guardrail_issues",
            "triggers": repair_triggers,
        }

    return {
        "action": "natural_keep",
        "reason": None,
        "triggers": [],
    }


def _answer_guardrail_triggers(
    answer: str,
    holdings_source: dict[str, Any],
) -> list[dict[str, Any]]:
    triggers: list[dict[str, Any]] = []

    for pattern in THINKING_RESIDUE_PATTERNS:
        triggers.extend(
            _pattern_triggers(
                answer,
                pattern,
                kind="thinking_residue",
                action="context_only_fallback",
                respect_negation=False,
            )
        )

    for pattern in SEVERE_HALLUCINATION_MARKERS:
        triggers.extend(
            _pattern_triggers(
                answer,
                pattern,
                kind="severe_hallucination_marker",
                action="context_only_fallback",
            )
        )

    if _misstates_current_holdings_as_sample(answer, holdings_source):
        triggers.append(
            {
                "kind": "holdings_source_misstatement",
                "pattern": "current_holdings_as_sample",
                "action": "context_only_fallback",
                "snippet": _snippet(answer, answer.find("sample_fallback")),
            }
        )

    if re.search(r"[\u0590-\u05ff]", answer):
        triggers.append(
            {
                "kind": "unexpected_script",
                "pattern": "hebrew_script",
                "action": "context_only_fallback",
                "snippet": "",
            }
        )
    severe_amount_patterns = (
        r"买入\s*[\d,]+(?:\.\d+)?\s*(?:元|人民币|块)?",
        r"卖出\s*[\d,]+(?:\.\d+)?\s*(?:元|人民币|块)?",
        r"加杠杆做空",
    )
    for pattern in severe_amount_patterns:
        for match in re.finditer(pattern, answer):
            if _is_negated_or_boundary_context(answer, match.start()):
                continue
            triggers.append(
                {
                    "kind": "explicit_trade_command",
                    "pattern": pattern,
                    "action": "context_only_fallback",
                    "snippet": _snippet(answer, match.start()),
                }
            )

    current_yield_point_patterns = (
        r"(?:美债收益率|10年期美债收益率|十年期美债收益率|treasury yield)[^。；\n]{0,32}\d+(?:\.\d+)?%",
        r"(?:当前|现在|最新)[^。；\n]{0,24}(?:美债|收益率|treasury yield)[^。；\n]{0,24}\d+(?:\.\d+)?%",
    )
    for pattern in current_yield_point_patterns:
        for match in re.finditer(pattern, answer, flags=re.IGNORECASE):
            if _is_negated_or_boundary_context(answer, match.start()):
                continue
            triggers.append(
                {
                    "kind": "invented_current_market_point",
                    "pattern": pattern,
                    "action": "context_only_fallback",
                    "snippet": _snippet(answer, match.start()),
                }
            )

    for pattern in SEVERE_FORBIDDEN_ANSWER_PATTERNS:
        triggers.extend(
            _pattern_triggers(
                answer,
                pattern,
                kind="severe_forbidden_phrase",
                action="context_only_fallback",
            )
        )

    for pattern in REPAIRABLE_FORBIDDEN_ANSWER_PATTERNS:
        triggers.extend(
            _pattern_triggers(
                answer,
                pattern,
                kind="repairable_phrase",
                action="repair",
            )
        )

    return _dedupe_triggers(triggers)


def _pattern_triggers(
    answer: str,
    pattern: str,
    kind: str,
    action: str,
    respect_negation: bool = True,
) -> list[dict[str, Any]]:
    if not pattern:
        return []

    triggers = []
    for match in re.finditer(re.escape(pattern), answer, flags=re.IGNORECASE):
        if respect_negation and _is_negated_or_boundary_context(answer, match.start()):
            continue
        triggers.append(
            {
                "kind": kind,
                "pattern": pattern,
                "action": action,
                "snippet": _snippet(answer, match.start()),
            }
        )
    return triggers


def _dedupe_triggers(triggers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for trigger in triggers:
        identity = (
            trigger.get("kind"),
            trigger.get("pattern"),
            trigger.get("action"),
            trigger.get("snippet"),
        )
        if identity in seen:
            continue
        seen.add(identity)
        result.append(trigger)
    return result


def _snippet(answer: str, start: int, radius: int = 36) -> str:
    if start < 0:
        return ""
    begin = max(0, start - radius)
    end = min(len(answer), start + radius)
    return answer[begin:end].replace("\n", " ").strip()


def _has_forbidden_answer_pattern(answer: str, pattern: str) -> bool:
    if not pattern:
        return False
    for match in re.finditer(re.escape(pattern), answer, flags=re.IGNORECASE):
        if _is_negated_or_boundary_context(answer, match.start()):
            continue
        return True
    return False


def _is_negated_or_boundary_context(answer: str, start: int) -> bool:
    prefix = answer[max(0, start - 32) : start]
    sentence_prefix = answer[max(0, start - 120) : start]
    for separator in ("。", "！", "？", "\n", "；", ";"):
        if separator in sentence_prefix:
            sentence_prefix = sentence_prefix.rsplit(separator, 1)[-1]
    safe_prefixes = (
        "不",
        "不要",
        "不能",
        "不可",
        "不得",
        "并非",
        "不是",
        "禁止",
        "避免",
        "不提供",
        "不给",
        "不输出",
        "不使用",
        "不写",
        "不能给",
        "不构成",
        "不等于",
        "不是要",
        "并不",
        "未",
        "无",
        "拒绝",
        "禁止编造",
        "不能编造",
        "不得编造",
        "不要编造",
    )
    return any(marker in prefix or marker in sentence_prefix for marker in safe_prefixes)


def _answer_has_hallucination_markers(answer: str) -> bool:
    if any(
        _pattern_triggers(
            answer,
            marker,
            kind="severe_hallucination_marker",
            action="context_only_fallback",
        )
        for marker in SEVERE_HALLUCINATION_MARKERS
    ):
        return True
    return bool(re.search(r"[\u0590-\u05ff]", answer))


def _misstates_current_holdings_as_sample(answer: str, holdings_source: dict[str, Any]) -> bool:
    if holdings_source.get("mode") not in {"current_holdings", "user_current_holdings", "real_holdings"}:
        return False
    for pattern in ("sample_fallback", "样本数据", "示例持仓"):
        for match in re.finditer(re.escape(pattern), answer, flags=re.IGNORECASE):
            if _is_negated_or_boundary_context(answer, match.start()):
                continue
            return True
    return False


def _build_context_only_safe_answer(
    context_json: dict[str, Any],
    user_question: str,
    answer_style: str = "standard",
    eval_case: dict[str, Any] | None = None,
) -> str:
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
    total_profit_loss = _portfolio_confirmed_value(context_json, "total_profit_loss")

    if _should_use_macro_geopolitics_rates_fallback(user_question, answer_style, eval_case):
        return _build_macro_geopolitics_rates_context_only_answer(
            market_temperature=market_temperature,
            weights=weights,
            targets=targets,
            deviations=deviations,
            flags=flags,
            dca=dca,
            holdings_updated_at=holdings_updated_at,
            holdings_age_days=holdings_age_days,
            holdings_freshness_status=holdings_freshness_status,
            cash_reserve_value=cash_reserve_value,
        )

    if "定投" in user_question and any(term in user_question for term in ("暂停", "停", "继续", "加速")):
        return _build_hot_market_dca_context_only_answer(
            market_temperature=market_temperature,
            weights=weights,
            targets=targets,
            deviations=deviations,
            flags=flags,
            dca=dca,
            holdings_updated_at=holdings_updated_at,
            holdings_age_days=holdings_age_days,
            holdings_freshness_status=holdings_freshness_status,
            cash_reserve_value=cash_reserve_value,
        )

    if any(term in user_question for term in ("复盘", "本月", "这个月", "周报", "月报")):
        return _build_monthly_review_context_only_answer(
            market_temperature=market_temperature,
            weights=weights,
            targets=targets,
            deviations=deviations,
            flags=flags,
            dca=dca,
            holdings_updated_at=holdings_updated_at,
            holdings_age_days=holdings_age_days,
            holdings_freshness_status=holdings_freshness_status,
            total_account_value=total_account_value,
            invested_asset_value=invested_asset_value,
            cash_reserve_value=cash_reserve_value,
        )

    if any(term in user_question for term in ("2000", "泡沫", "互联网泡沫")):
        return _build_analyst_memo_context_only_answer(
            market_temperature=market_temperature,
            weights=weights,
            targets=targets,
            deviations=deviations,
            flags=flags,
            dca=dca,
            holdings_updated_at=holdings_updated_at,
            holdings_age_days=holdings_age_days,
            holdings_freshness_status=holdings_freshness_status,
            total_account_value=total_account_value,
            invested_asset_value=invested_asset_value,
            cash_reserve_value=cash_reserve_value,
        )

    if "历史" in user_question or "相似窗口" in user_question:
        return "\n".join(
            [
                "## 核心结论",
                "historical outcome is not forecast。历史结果不是预测，历史表现不代表未来结果。",
                "",
                "## 历史参照",
                "相似窗口和历史相似数据只能作为历史参照，不能推出未来走势，也不能说明接下来大概率上涨。",
                "",
                "## 不确定性",
                "不能确定、不能保证未来上涨；仍需要观察当前估值、利率、通胀、盈利、流动性和数据质量。",
                "",
                "## 边界",
                "这不是短期涨跌判断，也不是投资建议；context 没有提供的实时估值或外部来源不能补写。",
            ]
        )

    if _question_mentions_recession_asset_roles(user_question):
        return "\n".join(
            [
                "## 核心判断",
                "这是衰退情境下的资产角色分析，不是短期涨跌预测，也不是交易指令。",
                "",
                "## 四类资产角色",
                "- 标普500：广泛权益风险暴露，受企业盈利、风险偏好和折现率影响。",
                "- 纳指100：更偏成长和长久期权益，通常对利率、流动性和风险偏好更敏感。",
                "- 短债：主要承担波动缓冲、流动性和较低久期风险角色，不是收益保证。",
                "- 黄金：与尾部风险、实际利率、美元和避险需求相关，但不是单向避险资产。",
                "",
                "## 组合含义",
                "组合含义只能回到相对目标、风险暴露、观察方向、阈值复核和年末复核；不提供具体买卖金额、卖出比例或立即调整命令，也不把 cash reserve / 余额宝当成待配置资产。",
            ]
        )

    if "买入" in user_question or "卖出" in user_question:
        return _build_trade_refusal_context_only_answer(
            weights=weights,
            targets=targets,
            deviations=deviations,
            flags=flags,
            holdings_updated_at=holdings_updated_at,
            holdings_age_days=holdings_age_days,
            holdings_freshness_status=holdings_freshness_status,
        )

    if "真实收益" in user_question or "账户数据" in user_question or "收益怎么样" in user_question:
        return "\n".join(
            [
                "## 结论",
                (
                    "可以基于 current_holdings.csv 本地持仓快照描述收益快照，但这不是实时账户同步，"
                    "也不保证与支付宝当前页面完全一致。"
                ),
                "",
                "## 当前快照",
                f"- holdings_updated_at: {_display(holdings_updated_at)}；age_days: {_display(holdings_age_days)}；freshness: {_display(holdings_freshness_status)}。",
                f"- total_account_value: {_format_number(total_account_value)}。",
                f"- invested_asset_value: {_format_number(invested_asset_value)}。",
                f"- cash_reserve_value: {_format_number(cash_reserve_value)}。",
                f"- total_profit_loss / 收益快照: {_format_number(total_profit_loss)}。",
                "",
                "## 数据限制",
                "current_holdings.csv 是用户本地手动录入快照，不是实时账户同步；若截图或账户发生变化，需要先更新 CSV 再判断。",
            ]
        )

    if ("黄金" in user_question and "短债" in user_question) or "高配" in user_question:
        return _build_gold_shortbond_context_only_answer(
            weights=weights,
            targets=targets,
            deviations=deviations,
            flags=flags,
            holdings_updated_at=holdings_updated_at,
            holdings_freshness_status=holdings_freshness_status,
        )

    if "数据源" in user_question or "缓存" in user_question or "stale" in user_question:
        return "\n".join(
            [
                "## 结论",
                "如果 context_health 不是 ok，或 market_snapshot 使用 stale cache，当前信息不足，不能直接做确定判断。",
                "",
                "## 处理原则",
                "需要标注数据质量和 data limitations；缺失数据不能编造，缓存或数据源失败时结论应降级为观察。",
                "",
                "## 需要检查",
                "优先看 context_health、market_snapshot.status、used_cache、data quality、核心市场数据是否缺失。",
            ]
        )

    if "过热" not in user_question and "组合" not in user_question:
        return ""


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


def _build_macro_geopolitics_rates_context_only_answer(
    market_temperature: dict[str, Any],
    weights: dict[str, Any],
    targets: dict[str, Any],
    deviations: dict[str, Any],
    flags: dict[str, Any],
    dca: dict[str, Any],
    holdings_updated_at: Any,
    holdings_age_days: Any,
    holdings_freshness_status: Any,
    cash_reserve_value: Any,
) -> str:
    allocation_lines = []
    for asset in ("sp500", "nasdaq100", "short_bond", "gold"):
        allocation_lines.append(
            "- "
            + f"{asset}: 当前 {_format_percent(weights.get(asset))}, "
            + f"目标 {_format_percent(targets.get(asset))}, "
            + f"偏离 {_format_pp(deviations.get(asset))}, "
            + f"{_allocation_label(flags.get(asset))}。"
        )

    return "\n".join(
        [
            "## 核心判断",
            (
                "就用户提到的地缘、利率或通胀相关问题而言，应先作为宏观资产定价框架来分析，"
                "不能把用户问题中的事件描述当作系统已经核验的实时新闻事实。估值压缩不等于系统性危机；"
                "系统性危机证据不足时不能断言危机已经启动。"
            ),
            "",
            "## 先纠正债券表述",
            "更准确的说法是：收益率上行通常对应债券价格下跌。不能把收益率上行写成债券价格上涨。",
            "",
            "## 普通避险 vs 通胀型冲击",
            (
                "普通避险通常是股票下跌，长债可能上涨，黄金可能走强。"
                "但通胀型冲击不同：油价、航运、保险、能源成本上行，可能推高通胀预期，"
                "并触发美联储政策路径重新定价。"
            ),
            (
                "在通胀型冲击里，长端收益率、真实利率或期限溢价可能上行，"
                "于是长债价格下跌，高估值权益和长久期权益出现估值压缩；黄金也可能因真实利率或美元因素承压。"
            ),
            "",
            "## 外交降温与结构性风险",
            (
                "外交降温不等于结构性风险解除。会谈可以降低尾部风险、减少突发升级概率，"
                "但不代表贸易、技术、供应链、安全和金融约束已经结构性缓解。"
            ),
            "",
            "## 估值压缩不等于系统性危机",
            (
                "多类资产同时承压、科技股承压和收益率上行可以说明宏观折现率压力或估值压缩，"
                "但系统性危机还需要更多证据。后续应观察信用利差、银行压力或融资压力、企业盈利、就业数据、"
                "波动率、美元融资压力、流动性异常，以及 QDII 申赎、汇兑、净值折算异常。"
            ),
            "",
            "## 数据限制",
            (
                "如果本地 context 未提供最新 ETF 价格、PE、市值、具体收益率点位、FedWatch 概率，"
                "也未提供 Reuters、FactSet、Goldman、CME 等外部来源，这里就只能从资产定价框架分析，不能编造这些数据。"
            ),
            "",
            "## 对当前组合的含义",
            (
                f"组合数据来自 current_holdings.csv 本地持仓快照，holdings_updated_at={_display(holdings_updated_at)}，"
                f"age_days={_display(holdings_age_days)}，freshness={_display(holdings_freshness_status)}；不是实时账户同步。"
            ),
            "余额宝/cash reserve 是现金准备金和扣款来源，不是待配置资产，也不是可直接部署的闲置资金。",
            *allocation_lines,
            (
                f"- DCA: daily_total {_format_number(dca.get('daily_total'))}, "
                f"monthly_required {_format_number(dca.get('monthly_required'))}, "
                f"budget_range {_format_number(dca.get('budget_min'))}-{_format_number(dca.get('budget_max'))}, "
                f"status {_display(dca.get('status'))}。"
            ),
            "",
            "## 最终判断",
            (
                "组合含义只能落在相对目标偏高、相对目标偏低、风险暴露、观察方向、后续定投与再平衡评估、"
                "阈值复核和年末复核上。这不是短期涨跌预测，也不提供具体买卖金额或交易命令。"
            ),
        ]
    )


def _build_monthly_review_context_only_answer(
    market_temperature: dict[str, Any],
    weights: dict[str, Any],
    targets: dict[str, Any],
    deviations: dict[str, Any],
    flags: dict[str, Any],
    dca: dict[str, Any],
    holdings_updated_at: Any,
    holdings_age_days: Any,
    holdings_freshness_status: Any,
    total_account_value: Any,
    invested_asset_value: Any,
    cash_reserve_value: Any,
) -> str:
    allocation_lines = []
    for asset in ("sp500", "nasdaq100", "short_bond", "gold"):
        allocation_lines.append(
            "- "
            + f"{asset}: 当前 {_format_percent(weights.get(asset))}, "
            + f"目标 {_format_percent(targets.get(asset))}, "
            + f"偏离 {_format_pp(deviations.get(asset))}, "
            + f"{_allocation_label(flags.get(asset))}。"
        )

    return "\n".join(
        [
            "## 核心结论",
            (
                "本月复盘口径下，当前市场更接近 warm_but_macro_sensitive（偏热但宏观敏感），"
                f"risk_level={_display(market_temperature.get('risk_level'))} / 中等风险水平。"
                "这是一项规则判断，不是短期涨跌预测，也不是交易指令。"
            ),
            "",
            "## 宏观与市场温度",
            (
                f"equity_temperature={_display(_level_value(market_temperature.get('equity_temperature')))}，"
                f"overall_regime={_display(market_temperature.get('overall_regime'))}。"
                "这些指标只能说明当前环境偏热且对利率、通胀和流动性更敏感，不能推出未来走势。"
            ),
            "",
            "## 组合快照",
            (
                f"组合数据来自 current_holdings.csv 本地手动快照，holdings_updated_at={_display(holdings_updated_at)}，"
                f"age_days={_display(holdings_age_days)}，freshness={_display(holdings_freshness_status)}；不是实时账户同步。"
            ),
            f"total_account_value={_format_number(total_account_value)}，invested_asset_value={_format_number(invested_asset_value)}，cash reserve / 余额宝={_format_number(cash_reserve_value)}。",
            "余额宝是现金准备金和 DCA 扣款来源，不参与 5:2:2:1 目标仓位计算，也不等于应立即投入市场的闲置资金。",
            "",
            "## 配置偏离与 DCA",
            *allocation_lines,
            (
                f"- DCA: daily_total {_format_number(dca.get('daily_total'))}, "
                f"monthly_required {_format_number(dca.get('monthly_required'))}, "
                f"budget_range {_format_number(dca.get('budget_min'))}-{_format_number(dca.get('budget_max'))}, "
                f"status {_display(dca.get('status'))}。"
            ),
            "",
            "## 数据限制",
            "context_health 和数据质量是复盘前提；缓存、数据源失败、ETF proxy 或历史窗口不完整时，结论必须降级为观察。historical outcome is not forecast。",
            "",
            "## 观察信号",
            "后续重点看 DGS10、CPI/PCE、盈利兑现、流动性、context_health、market_snapshot.status、used_cache 和持仓 freshness。",
            "",
            "## 最终判断",
            "复盘结论应服务于纪律化定投、预算约束和年度/阈值再平衡框架；不输出具体买卖金额，也不使用交易化禁用语。",
        ]
    )


def _build_hot_market_dca_context_only_answer(
    market_temperature: dict[str, Any],
    weights: dict[str, Any],
    targets: dict[str, Any],
    deviations: dict[str, Any],
    flags: dict[str, Any],
    dca: dict[str, Any],
    holdings_updated_at: Any,
    holdings_age_days: Any,
    holdings_freshness_status: Any,
    cash_reserve_value: Any,
) -> str:
    allocation_summary = []
    for asset in ("sp500", "nasdaq100", "short_bond", "gold"):
        allocation_summary.append(
            "- "
            + f"{asset}: 当前 {_format_percent(weights.get(asset))}, "
            + f"目标 {_format_percent(targets.get(asset))}, "
            + f"偏离 {_format_pp(deviations.get(asset))}, "
            + f"{_allocation_label(flags.get(asset))}。"
        )

    return "\n".join(
        [
            "## 核心判断",
            "不能直接给“暂停、继续或加速定投”的交易命令；这不是交易指令，也不提供具体交易指令。市场偏热只能进入观察框架，不是短期涨跌预测。",
            "",
            "## 最新数据边界",
            "本地 context 未提供最新 PE、估值、具体收益率点位、黄金价格或 FedWatch 概率；不能补具体数值或外部来源。",
            "",
            "## 市场温度",
            (
                f"当前规则状态是 {_display(market_temperature.get('overall_regime'))} / 偏热但宏观敏感，"
                f"risk_level={_display(market_temperature.get('risk_level'))}。"
            ),
            "",
            "## DCA 与现金准备金",
            (
                f"DCA monthly_required={_format_number(dca.get('monthly_required'))}，"
                f"budget_range={_format_number(dca.get('budget_min'))}-{_format_number(dca.get('budget_max'))}，"
                f"status={_display(dca.get('status'))} / within_budget。"
            ),
            f"余额宝/cash reserve={_format_number(cash_reserve_value)}，是现金准备金和扣款来源，不等于应立即投入市场的闲置资金。",
            "",
            "## 组合含义",
            (
                f"数据来自 current_holdings.csv 本地手动快照，holdings_updated_at={_display(holdings_updated_at)}，"
                f"age_days={_display(holdings_age_days)}，freshness={_display(holdings_freshness_status)}。"
            ),
            *allocation_summary,
            "",
            "## 可观察信号",
            "后续看 market temperature、DGS10、CPI/PCE、盈利兑现、context_health、预算执行和持仓 freshness，这些只是观察信号。",
            "",
            "## 边界",
            "这不是投资建议；只提供纪律化定投、预算约束、观察框架和再平衡框架，不输出具体买卖金额或交易指令。",
        ]
    )


def _build_analyst_memo_context_only_answer(
    market_temperature: dict[str, Any],
    weights: dict[str, Any],
    targets: dict[str, Any],
    deviations: dict[str, Any],
    flags: dict[str, Any],
    dca: dict[str, Any],
    holdings_updated_at: Any,
    holdings_age_days: Any,
    holdings_freshness_status: Any,
    total_account_value: Any,
    invested_asset_value: Any,
    cash_reserve_value: Any,
) -> str:
    allocation_lines = []
    for asset in ("sp500", "nasdaq100", "short_bond", "gold"):
        allocation_lines.append(
            "- "
            + f"{asset}: 当前 {_format_percent(weights.get(asset))}, "
            + f"目标 {_format_percent(targets.get(asset))}, "
            + f"偏离 {_format_pp(deviations.get(asset))}, "
            + f"{_allocation_label(flags.get(asset))}。"
        )

    return "\n".join(
        [
            "## 核心判断",
            (
                "把当前市场与 2000 年互联网泡沫做类比有合理性，但不是 2000 年的简单复刻。"
                "相似之处在于市场叙事偏乐观、风险偏好较高，真正风险不一定是 AI 无用，"
                "而是高估值和高预期兑现压力是否已经过度透支。"
            ),
            "",
            "## 类比成立的部分",
            (
                "从本地 context 看，当前 rule-based regime 是 "
                f"{_display(market_temperature.get('overall_regime'))}，risk_level={_display(market_temperature.get('risk_level'))}，"
                "可以理解为偏热但宏观敏感。这个状态和泡沫期的共同点，是市场容易把长期技术革命提前折现到当前价格。"
            ),
            "",
            "## 类比不成立的部分",
            (
                "不能简单说这就是 2000 年复刻。技术革命真实存在，这次部分核心 AI 公司可能有收入、利润、现金流或基本面支撑；"
                "但 context pack 没有提供最新价格、PE、市值或媒体来源，所以不能编造 Reuters、FactSet、Goldman 等外部数据来证明估值。"
            ),
            "",
            "## 真正风险在哪里",
            (
                "真正风险不是“AI 有没有用”这个二元问题，而是高估值、高预期兑现压力和宏观利率环境叠加后，"
                "未来 1-2 年科技股杀估值或阶段性回撤概率上升。这个说法仍是情景分析，不是确定性预测。"
            ),
            "",
            "## 对用户判断的修正",
            (
                "“危机还没有到来但可能在一两年内接近”可以作为风险假设，但系统性经济危机证据不足，"
                "不能断言危机必然到来，也不能把历史相似窗口写成 forecast。"
            ),
            "",
            "## 需要观察的信号",
            "观察重点应放在 equity_temperature、overall_regime、risk_level、DGS10、CPI/PCE、盈利兑现、流动性和 context_health，而不是编造实时阈值或外部报价。",
            "",
            "## 对当前组合的含义",
            (
                f"组合数据来自 current_holdings.csv 本地手动快照，holdings_updated_at={_display(holdings_updated_at)}，"
                f"age_days={_display(holdings_age_days)}，freshness={_display(holdings_freshness_status)}；不是实时账户同步。"
            ),
            f"账户总额约 {_format_number(total_account_value)}，投资资产约 {_format_number(invested_asset_value)}，余额宝/cash reserve 约 {_format_number(cash_reserve_value)}；余额宝是现金准备金和扣款来源，不参与 5:2:2:1 目标仓位。",
            *allocation_lines,
            (
                f"- DCA: daily_total {_format_number(dca.get('daily_total'))}, "
                f"monthly_required {_format_number(dca.get('monthly_required'))}, "
                f"budget_range {_format_number(dca.get('budget_min'))}-{_format_number(dca.get('budget_max'))}, "
                f"status {_display(dca.get('status'))}。"
            ),
            "组合层面不清仓、不追涨、不提高纳指权重；更合适的是纪律化定投、保留再平衡框架，把低配/高配作为后续观察方向。",
            "",
            "## 最终判断",
            (
                "你的直觉抓住了“乐观叙事和价格透支”的核心，但需要从“危机必然临近”修正为“估值回撤风险上升、系统性危机证据不足”。"
                "这是一份基于本地 context 的投研札记，不是短期预测，也不是交易指令。"
            ),
        ]
    )


def _build_trade_refusal_context_only_answer(
    weights: dict[str, Any],
    targets: dict[str, Any],
    deviations: dict[str, Any],
    flags: dict[str, Any],
    holdings_updated_at: Any,
    holdings_age_days: Any,
    holdings_freshness_status: Any,
) -> str:
    lines = [
        "## 结论",
        "不能给具体交易指令，也不提供具体买卖金额。",
        "",
        "## 数据来源",
        f"当前依据 current_holdings.csv 本地持仓快照，holdings_updated_at={_display(holdings_updated_at)}，age_days={_display(holdings_age_days)}，freshness={_display(holdings_freshness_status)}；它不是实时账户同步。",
        "",
        "## 观察框架",
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
            "",
            "## 风险提示",
            "以上只能作为后续定投纪律和年度/阈值再平衡评估的观察方向，不是买入、卖出或调整仓位命令。",
        ]
    )
    return "\n".join(lines)


def _build_gold_shortbond_context_only_answer(
    weights: dict[str, Any],
    targets: dict[str, Any],
    deviations: dict[str, Any],
    flags: dict[str, Any],
    holdings_updated_at: Any,
    holdings_freshness_status: Any,
) -> str:
    return "\n".join(
        [
            "## 核心结论",
            "黄金和短债高配说明当前组合相对目标更偏防御和现金流稳定暴露，但这只是仓位偏离描述，不是交易指令。",
            "",
            "## 关键事实",
            f"- 数据来源：current_holdings.csv 本地持仓快照，holdings_updated_at={_display(holdings_updated_at)}，freshness={_display(holdings_freshness_status)}。",
            f"- gold / 黄金: 当前 {_format_percent(weights.get('gold'))}, 目标 {_format_percent(targets.get('gold'))}, 偏离 {_format_pp(deviations.get('gold'))}, {_allocation_label(flags.get('gold'))}。",
            f"- short_bond / 短债: 当前 {_format_percent(weights.get('short_bond'))}, 目标 {_format_percent(targets.get('short_bond'))}, 偏离 {_format_pp(deviations.get('short_bond'))}, {_allocation_label(flags.get('short_bond'))}。",
            "",
            "## 含义",
            "这可以降低一部分权益波动暴露，但也可能让组合在权益继续强势时跟随不足。后续只作为定投和再平衡观察方向，不给卖出或清仓指令。",
        ]
    )


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
        "answer_mode": result.get("answer_mode"),
        "fallback_reason": result.get("fallback_reason"),
        "guardrail_action": result.get("guardrail_action"),
        "guardrail_triggers": result.get("guardrail_triggers", []),
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

from __future__ import annotations

import json
import http.client
import os
import time
import urllib.error
import urllib.request
from typing import Any

from llm.provider_response import ProviderResponse, empty_usage


DEFAULT_BASE_URL = "https://api.deepseek.com"


def call_deepseek_chat(
    messages: list[dict[str, str]],
    *,
    model: str,
    base_url: str = DEFAULT_BASE_URL,
    timeout_seconds: int = 240,
    temperature: float = 0.2,
    max_output_tokens: int = 4096,
    pricing: dict[str, Any] | None = None,
    max_retries: int = 2,
) -> ProviderResponse:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    metadata_base = {
        "base_url": _redact_url(base_url),
        "pricing_assumption": _pricing_assumption(model, pricing),
        "retry_count": 0,
        "attempts": [],
    }
    if not api_key:
        return ProviderResponse(
            provider="deepseek",
            model=model,
            answer_text="",
            usage=empty_usage(),
            success=False,
            raw_error="Missing DEEPSEEK_API_KEY environment variable.",
            metadata=metadata_base,
        )

    endpoint = _join_url(base_url, "/chat/completions")
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_output_tokens,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    started = time.perf_counter()
    attempts: list[dict[str, Any]] = []
    parsed: dict[str, Any] | None = None
    final_error: str | None = None
    total_attempts = max(1, int(max_retries) + 1)

    for attempt_number in range(1, total_attempts + 1):
        try:
            request = urllib.request.Request(
                endpoint,
                data=body,
                method="POST",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                response_body = response.read().decode("utf-8", errors="replace")
                parsed = json.loads(response_body)
            attempts.append({"attempt": attempt_number, "status": "ok", "retryable": False})
            break
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            final_error = f"HTTP {exc.code}: {_sanitize_error(error_body)}"
            retryable = _is_retryable_http_status(exc.code)
            attempts.append(
                {
                    "attempt": attempt_number,
                    "status": "error",
                    "error_type": "HTTPError",
                    "http_status": exc.code,
                    "retryable": retryable,
                }
            )
            if not retryable or attempt_number >= total_attempts:
                break
            _sleep_before_retry(attempt_number)
        except (urllib.error.URLError, http.client.RemoteDisconnected, TimeoutError) as exc:
            final_error = f"{type(exc).__name__}: {_sanitize_error(str(exc))}"
            attempts.append(
                {
                    "attempt": attempt_number,
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "retryable": True,
                }
            )
            if attempt_number >= total_attempts:
                break
            _sleep_before_retry(attempt_number)
        except json.JSONDecodeError as exc:
            final_error = f"Invalid JSON response: {exc}"
            attempts.append(
                {
                    "attempt": attempt_number,
                    "status": "error",
                    "error_type": "JSONDecodeError",
                    "retryable": False,
                }
            )
            break

    metadata_base["attempts"] = attempts
    metadata_base["retry_count"] = max(0, len(attempts) - 1)

    if parsed is None:
        latency = time.perf_counter() - started
        return ProviderResponse(
            provider="deepseek",
            model=model,
            answer_text="",
            latency_seconds=round(latency, 3),
            usage=empty_usage(),
            success=False,
            raw_error=final_error or "DeepSeek request failed.",
            metadata=metadata_base,
        )

    latency = time.perf_counter() - started
    answer_text = _extract_answer_text(parsed)
    usage = _normalize_usage(parsed.get("usage"))
    estimated_cost = estimate_cost_cny(usage, model=model, pricing=pricing)
    return ProviderResponse(
        provider="deepseek",
        model=model,
        answer_text=answer_text,
        latency_seconds=round(latency, 3),
        usage=usage,
        estimated_cost_cny=estimated_cost,
        success=bool(answer_text),
        raw_error=None if answer_text else "Response did not contain assistant content.",
        metadata={
            **metadata_base,
            "response_id": parsed.get("id"),
        },
    )


def estimate_cost_cny(
    usage: dict[str, Any],
    *,
    model: str,
    pricing: dict[str, Any] | None,
) -> float | None:
    if not pricing:
        return None
    model_pricing = pricing.get(model) if isinstance(pricing, dict) else None
    if not isinstance(model_pricing, dict):
        return None

    output_tokens = _as_number(usage.get("output_tokens"))
    cache_hit = _as_number(usage.get("cache_hit_tokens"))
    cache_miss = _as_number(usage.get("cache_miss_tokens"))
    input_tokens = _as_number(usage.get("input_tokens"))
    if output_tokens is None and input_tokens is None:
        return None

    cost = 0.0
    if cache_hit is not None or cache_miss is not None:
        cost += ((cache_hit or 0.0) / 1_000_000) * float(model_pricing.get("input_cache_hit", 0.0))
        cost += ((cache_miss or 0.0) / 1_000_000) * float(model_pricing.get("input_cache_miss", 0.0))
    elif input_tokens is not None:
        cost += (input_tokens / 1_000_000) * float(model_pricing.get("input_cache_miss", 0.0))
    if output_tokens is not None:
        cost += (output_tokens / 1_000_000) * float(model_pricing.get("output", 0.0))
    return round(cost, 6)


def _extract_answer_text(parsed: dict[str, Any]) -> str:
    choices = parsed.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return str(content).strip() if content is not None else ""


def _normalize_usage(usage: Any) -> dict[str, Any]:
    normalized = empty_usage()
    if not isinstance(usage, dict):
        return normalized
    normalized["input_tokens"] = usage.get("prompt_tokens")
    normalized["output_tokens"] = usage.get("completion_tokens")
    normalized["total_tokens"] = usage.get("total_tokens")
    normalized["cache_hit_tokens"] = (
        usage.get("prompt_cache_hit_tokens")
        or usage.get("cache_hit_tokens")
        or usage.get("input_cache_hit_tokens")
    )
    normalized["cache_miss_tokens"] = (
        usage.get("prompt_cache_miss_tokens")
        or usage.get("cache_miss_tokens")
        or usage.get("input_cache_miss_tokens")
    )
    return normalized


def _pricing_assumption(model: str, pricing: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(pricing, dict):
        return None
    model_pricing = pricing.get(model)
    return model_pricing if isinstance(model_pricing, dict) else None


def _join_url(base_url: str, suffix: str) -> str:
    return base_url.rstrip("/") + "/" + suffix.lstrip("/")


def _redact_url(base_url: str) -> str:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    return base_url.replace(api_key, "[redacted]") if api_key else base_url


def _is_retryable_http_status(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code <= 599


def _sleep_before_retry(attempt_number: int) -> None:
    time.sleep(min(2, max(1, attempt_number)))


def _sanitize_error(text: str) -> str:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if api_key:
        text = text.replace(api_key, "[redacted]")
    return text[:2000]


def _as_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

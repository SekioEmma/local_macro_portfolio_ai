from __future__ import annotations

import json
import re
from typing import Any
from urllib import error, request
from urllib.parse import urlparse, urlunparse


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def call_local_llm(prompt: str, config: dict[str, Any]) -> dict[str, Any]:
    local_config = config.get("local_llm", {}) if isinstance(config, dict) else {}
    mode = local_config.get("mode", "prompt_only")
    provider = local_config.get("provider", "generic_local_http")
    model = local_config.get("model", "local-model")

    if mode == "prompt_only":
        return {
            "status": "prompt_only",
            "provider": provider,
            "model": model,
            "answer": None,
            "raw_answer_preview": None,
            "removed_thinking": False,
            "cleaning_notes": [],
            "error": None,
            "raw_metadata": {},
        }

    if mode != "local_http":
        return {
            "status": "error",
            "provider": provider,
            "model": model,
            "answer": None,
            "raw_answer_preview": None,
            "removed_thinking": False,
            "cleaning_notes": [],
            "error": f"Unsupported local_llm.mode: {mode}",
            "raw_metadata": {},
        }

    endpoint = str(local_config.get("endpoint", ""))
    if not _is_local_endpoint(endpoint):
        return {
            "status": "error",
            "provider": provider,
            "model": model,
            "answer": None,
            "raw_answer_preview": None,
            "removed_thinking": False,
            "cleaning_notes": [],
            "error": "Refusing non-local endpoint. Only localhost, 127.0.0.1, or ::1 are allowed.",
            "raw_metadata": {},
        }

    if provider != "ollama":
        return {
            "status": "error",
            "provider": provider,
            "model": model,
            "answer": None,
            "raw_answer_preview": None,
            "removed_thinking": False,
            "cleaning_notes": [],
            "error": f"Unsupported local_llm.provider for local_http: {provider}",
            "raw_metadata": {},
        }

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": _as_float(local_config.get("temperature"), default=0.1),
            "top_p": _as_float(local_config.get("top_p"), default=0.9),
            "num_ctx": _as_int(local_config.get("num_ctx"), default=4096),
        },
    }
    timeout = _as_float(local_config.get("timeout_seconds"), default=240.0)

    response = _post_json(endpoint, payload, timeout)
    if response.get("status") == "model_memory_layout_error":
        return _error_result("model_memory_layout_error", provider, model, response.get("error"))
    if response.get("status") != "ok":
        return _error_result("error", provider, model, response.get("error"))

    data = response.get("data", {})
    answer = _extract_answer(data)
    if not answer:
        return _error_result(
            "error",
            provider,
            model,
            "Ollama response did not contain a response field.",
            raw_metadata=_metadata_without_answer(data),
        )

    cleaned = clean_model_answer(
        answer,
        strip_thinking_output=bool(local_config.get("strip_thinking_output", True)),
    )
    return {
        "status": "ok",
        "provider": provider,
        "model": model,
        "answer": cleaned["cleaned_answer"],
        "raw_answer_preview": answer[:500],
        "removed_thinking": cleaned["removed_thinking"],
        "cleaning_notes": cleaned["cleaning_notes"],
        "error": None,
        "raw_metadata": _metadata_without_answer(data),
    }


def check_ollama_health(config: dict[str, Any]) -> dict[str, Any]:
    local_config = config.get("local_llm", {}) if isinstance(config, dict) else {}
    endpoint = str(local_config.get("endpoint", ""))
    model = local_config.get("model", "local-model")
    provider = local_config.get("provider", "generic_local_http")

    if provider != "ollama":
        return {
            "status": "skipped",
            "provider": provider,
            "model": model,
            "error": None,
            "hint": "Ollama health check only applies to provider=ollama.",
        }

    if not _is_local_endpoint(endpoint):
        return {
            "status": "error",
            "provider": provider,
            "model": model,
            "error": "Refusing non-local endpoint. Only localhost, 127.0.0.1, or ::1 are allowed.",
            "hint": None,
        }

    tags_url = _ollama_api_url(endpoint, "/api/tags")
    timeout = _as_float(local_config.get("timeout_seconds"), default=240.0)
    response = _get_json(tags_url, timeout)
    if response.get("status") != "ok":
        version_url = _ollama_api_url(endpoint, "/api/version")
        version_response = _get_json(version_url, timeout)
        if version_response.get("status") != "ok":
            return {
                "status": "error",
                "provider": provider,
                "model": model,
                "error": response.get("error") or version_response.get("error"),
                "hint": "Start Ollama locally, then run: ollama pull gemma4:e2b",
            }
        return {
            "status": "model_unknown",
            "provider": provider,
            "model": model,
            "error": "Could not read /api/tags.",
            "hint": f"If the model is missing, run: ollama pull {model}",
            "raw_metadata": version_response.get("data", {}),
        }

    models = response.get("data", {}).get("models", [])
    model_names = [
        item.get("name") or item.get("model")
        for item in models
        if isinstance(item, dict)
    ]
    if model not in model_names:
        return {
            "status": "model_missing",
            "provider": provider,
            "model": model,
            "error": f"Ollama model not found: {model}",
            "hint": f"Run: ollama pull {model}",
            "available_models": [name for name in model_names if name],
        }

    return {
        "status": "ok",
        "provider": provider,
        "model": model,
        "error": None,
        "hint": None,
        "available_models": [name for name in model_names if name],
    }


def clean_model_answer(answer: str, strip_thinking_output: bool = True) -> dict[str, Any]:
    if not strip_thinking_output:
        return {
            "cleaned_answer": answer.strip(),
            "removed_thinking": False,
            "cleaning_notes": [],
        }

    cleaned = str(answer)
    notes: list[str] = []

    cleaned, removed = _sub_with_note(
        cleaned,
        r"(?is)<think>.*?</think>",
        "",
    )
    if removed:
        notes.append("Removed <think>...</think> block.")

    cleaned, removed = _sub_with_note(
        cleaned,
        r"(?is)Thinking\.\.\..*?(?:\.\.\.)?done thinking\.?",
        "",
    )
    if removed:
        notes.append("Removed Thinking... to done thinking block.")

    cleaned, removed = _remove_thinking_process(cleaned)
    if removed:
        notes.append("Removed Thinking Process section.")

    cleaned, removed = _sub_with_note(
        cleaned,
        r"(?im)^\s*(Thinking\.\.\.|(?:\.\.\.)?done thinking\.?)\s*$",
        "",
    )
    if removed:
        notes.append("Removed standalone thinking marker line.")

    cleaned = cleaned.strip()
    return {
        "cleaned_answer": cleaned,
        "removed_thinking": bool(notes),
        "cleaning_notes": notes,
    }


def _remove_thinking_process(text: str) -> tuple[str, bool]:
    match = re.search(r"(?is)Thinking Process\s*[:：]", text)
    if not match:
        return text, False

    markers = [
        r"Final Answer\s*[:：]",
        r"Final\s*[:：]",
        r"Answer\s*[:：]",
        r"最终答案\s*[:：]",
        r"最终回答\s*[:：]",
        r"答案\s*[:：]",
        r"(?m)^#+\s*核心结论",
        r"(?m)^核心结论",
        r"(?m)^-\s*核心结论",
    ]
    marker_match = None
    for pattern in markers:
        candidate = re.search(pattern, text[match.end() :], flags=re.IGNORECASE)
        if candidate and (marker_match is None or candidate.start() < marker_match.start()):
            marker_match = candidate

    if marker_match:
        marker_start = match.end() + marker_match.start()
        answer = text[marker_start:]
        answer = re.sub(
            r"(?is)^(Final Answer|Final|Answer|最终答案|最终回答|答案)\s*[:：]\s*",
            "",
            answer,
        )
        return text[: match.start()] + answer, True

    after = text[match.end() :]
    blank_match = re.search(r"\n\s*\n", after)
    if blank_match:
        keep_start = match.end() + blank_match.end()
        return text[: match.start()] + text[keep_start:], True

    return text[: match.start()].rstrip(), True


def _extract_answer(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    value = data.get("response")
    if isinstance(value, str):
        return value
    for key in ("answer", "text", "content"):
        value = data.get(key)
        if isinstance(value, str):
            return value

    message = data.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return message["content"]
    return None


def _post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return _open_json(req, timeout)


def _get_json(url: str, timeout: float) -> dict[str, Any]:
    req = request.Request(url, method="GET")
    return _open_json(req, timeout)


def _open_json(req: request.Request, timeout: float) -> dict[str, Any]:
    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        if "memory layout cannot be allocated" in raw.lower():
            return {
                "status": "model_memory_layout_error",
                "error": raw,
            }
        return {
            "status": "error",
            "error": f"HTTP {exc.code}: {raw}",
        }
    except error.URLError as exc:
        return {
            "status": "error",
            "error": f"Local HTTP request failed: {exc}",
        }
    except OSError as exc:
        return {
            "status": "error",
            "error": f"Local HTTP request failed: {exc}",
        }

    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        return {
            "status": "error",
            "error": f"Local HTTP response was not valid JSON: {exc}",
        }

    if isinstance(data, dict) and "error" in data:
        error_text = str(data.get("error"))
        if "memory layout cannot be allocated" in error_text.lower():
            return {
                "status": "model_memory_layout_error",
                "error": error_text,
            }
        return {
            "status": "error",
            "error": error_text,
            "data": data,
        }

    return {
        "status": "ok",
        "data": data,
    }


def _error_result(
    status: str,
    provider: str,
    model: str,
    error_text: Any,
    raw_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "provider": provider,
        "model": model,
        "answer": None,
        "raw_answer_preview": None,
        "removed_thinking": False,
        "cleaning_notes": [],
        "error": str(error_text) if error_text else None,
        "raw_metadata": raw_metadata or {},
    }


def _metadata_without_answer(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    return {
        key: value
        for key, value in data.items()
        if key not in {"response", "answer", "text", "content", "message"}
    }


def _ollama_api_url(endpoint: str, path: str) -> str:
    parsed = urlparse(endpoint)
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def _is_local_endpoint(endpoint: str) -> bool:
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"}:
        return False
    hostname = parsed.hostname
    return hostname in LOCAL_HOSTS


def _sub_with_note(text: str, pattern: str, replacement: str) -> tuple[str, bool]:
    cleaned, count = re.subn(pattern, replacement, text)
    return cleaned, count > 0


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def call_local_llm(prompt: str, config: dict[str, Any]) -> dict[str, Any]:
    local_config = config.get("local_llm", {}) if isinstance(config, dict) else {}
    mode = local_config.get("mode", "prompt_only")

    if mode == "prompt_only":
        return {
            "status": "prompt_only",
            "prompt": prompt,
            "answer": None,
        }

    if mode != "local_http":
        return {
            "status": "error",
            "prompt": prompt,
            "answer": None,
            "error": f"Unsupported local_llm.mode: {mode}",
        }

    endpoint = str(local_config.get("endpoint", ""))
    if not _is_local_endpoint(endpoint):
        return {
            "status": "error",
            "prompt": prompt,
            "answer": None,
            "error": "Refusing non-local endpoint. Only localhost, 127.0.0.1, or ::1 are allowed.",
        }

    payload = {
        "model": local_config.get("model", "local-model"),
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": _as_float(local_config.get("temperature"), default=0.2),
        },
    }
    timeout = _as_float(local_config.get("timeout_seconds"), default=120.0)

    try:
        import requests
    except ModuleNotFoundError:
        return {
            "status": "error",
            "prompt": prompt,
            "answer": None,
            "error": "The requests package is required for local_http mode.",
        }

    try:
        response = requests.post(endpoint, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        return {
            "status": "error",
            "prompt": prompt,
            "answer": None,
            "error": f"Local HTTP request failed: {exc}",
        }
    except ValueError as exc:
        return {
            "status": "error",
            "prompt": prompt,
            "answer": None,
            "error": f"Local HTTP response was not valid JSON: {exc}",
        }

    answer = _extract_answer(data)
    return {
        "status": "ok" if answer else "error",
        "prompt": prompt,
        "answer": answer,
        "raw_response": data,
        "error": None if answer else "Local HTTP response did not contain an answer field.",
    }


def _extract_answer(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    for key in ("response", "answer", "text", "content"):
        value = data.get(key)
        if isinstance(value, str):
            return value

    message = data.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return message["content"]
    return None


def _is_local_endpoint(endpoint: str) -> bool:
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"}:
        return False
    hostname = parsed.hostname
    return hostname in LOCAL_HOSTS


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
